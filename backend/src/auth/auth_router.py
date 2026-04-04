"""
Auth router  —  /api/auth/*

Endpoints
---------
  POST /signup              register new user
  POST /login               email + password login (handles 2FA gate)
  POST /refresh             exchange refresh token for new access token
  POST /logout              instructs client to discard tokens
  PATCH /password           change password (requires current password)
  POST /2fa/complete        finish login when requires_2fa=True
"""
from datetime import datetime, timezone

import pyotp
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.auth_services import (
    authenticate_user,
    change_password,
    check_password_strength,
    create_user
)
from src.auth.schemas import (
    LoginResponse,
    PasswordChangeRequest,
    RefreshRequest,
    TwoFACompleteRequest,
    TokenPair,
    UserCreate,
    UserLogin,
)
from src.config import logger
from src.database import get_db
from src.dependencies import get_current_user
from src.models import User
from src.utils.exceptions import (
    email_already_registered_exception,
    invalid_credentials_exception,
    username_already_registered_exception,
)
from src.utils.getters_services import (
    get_user_by_email,
    get_user_by_username,
)
from src.utils.jwt_handlers import (
    create_2fa_pending_token,
    create_access_token,
    create_refresh_token,
)
from src.utils.security import decode_token

auth_router = APIRouter()


# ── Register ──────────────────────────────────────────────────────────────────

@auth_router.post("/signup", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def sign_up(user: UserCreate, db: AsyncSession = Depends(get_db)):
    if await get_user_by_email(db, user.email):
        raise email_already_registered_exception
    if await get_user_by_username(db, user.username):
        raise username_already_registered_exception

    errors = await check_password_strength(user.password)   # now async
    if errors:
        raise HTTPException(status_code=400, detail=errors)

    new_user = await create_user(db, user)
    access_token  = await create_access_token({"sub": str(new_user.id_)})
    refresh_token = await create_refresh_token({"sub": str(new_user.id_)})
    logger.info("New user registered: id=%s email=%s", new_user.id_, new_user.email)
    return LoginResponse(access_token=access_token, refresh_token=refresh_token)


# ── Login ─────────────────────────────────────────────────────────────────────

@auth_router.post("/login", response_model=LoginResponse)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    email = payload.email.strip().lower()
    db_user = await authenticate_user(db, email, payload.password)
    if not db_user:
        logger.info("Login failed for email=%s", email)
        raise invalid_credentials_exception

    # ── 2FA gate ──────────────────────────────────────────────────────────────
    if db_user.twofa_enabled:
        temp_token = await create_2fa_pending_token(db_user.id_)
        logger.info("2FA required for user id=%s", db_user.id_)
        return LoginResponse(requires_2fa=True, temp_token=temp_token)

    access_token  = await create_access_token({"sub": str(db_user.id_)})
    refresh_token = await create_refresh_token({"sub": str(db_user.id_)})
    logger.info("User signed in: id=%s email=%s", db_user.id_, email)
    return LoginResponse(access_token=access_token, refresh_token=refresh_token)


# ── Complete 2FA login ────────────────────────────────────────────────────────

@auth_router.post("/2fa/complete", response_model=TokenPair)
async def complete_2fa_login(payload: TwoFACompleteRequest, db: AsyncSession = Depends(get_db)):
    """
    Second step when login returns requires_2fa=True.
    Send the temp_token + TOTP code to receive full access/refresh tokens.
    """
    try:
        token_data = decode_token(payload.temp_token)
        if token_data.get("type") != "2fa_pending":
            raise ValueError("wrong type")
        exp = int(token_data.get("exp", 0))
        if int(datetime.now(timezone.utc).timestamp()) > exp:
            raise ValueError("expired")
        user_id = int(token_data["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired 2FA session token")

    user = (await db.execute(select(User).where(User.id_ == user_id))).scalar_one_or_none()
    if not user or not user.twofa_secret:
        raise HTTPException(status_code=401, detail="User not found or 2FA not configured")

    if not pyotp.TOTP(user.twofa_secret).verify(payload.code):
        raise HTTPException(status_code=401, detail="Invalid 2FA code")

    access_token  = await create_access_token({"sub": str(user.id_)})
    refresh_token = await create_refresh_token({"sub": str(user.id_)})
    logger.info("2FA login completed for user id=%s", user.id_)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


# ── Refresh ───────────────────────────────────────────────────────────────────

@auth_router.post("/refresh", response_model=TokenPair)
async def refresh_token(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """
    Exchange a valid refresh token for a new access token (+ rotated refresh token).
    Clients should call this before the access token expires.
    """
    try:
        token_data = decode_token(payload.refresh_token)
        token_type = token_data.get("type")
        if token_type not in ("refresh", None):    # allow legacy tokens without type
            raise ValueError("not a refresh token")
        exp = int(token_data.get("exp", 0))
        if int(datetime.now(timezone.utc).timestamp()) > exp:
            raise ValueError("expired")
        user_id = int(token_data["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = (await db.execute(select(User).where(User.id_ == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    new_access  = await create_access_token({"sub": str(user.id_)})
    new_refresh = await create_refresh_token({"sub": str(user.id_)})
    return TokenPair(access_token=new_access, refresh_token=new_refresh)


# ── Logout ────────────────────────────────────────────────────────────────────

@auth_router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(current_user: User = Depends(get_current_user)):
    """
    Stateless logout — instructs the client to discard both tokens.
    JWT tokens are not server-side revocable without a token blacklist (Redis).
    TODO: add Redis token blacklist for instant revocation.
    """
    logger.info("User logged out: id=%s", current_user.id_)
    return {"message": "Logged out successfully. Please discard your tokens."}


# ── Change password ───────────────────────────────────────────────────────────

@auth_router.patch("/password", status_code=status.HTTP_200_OK)
async def change_password_endpoint(
    payload: PasswordChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change password. Requires the current password for verification."""
    try:
        await change_password(db, current_user, payload.current_password, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    logger.info("Password changed for user id=%s", current_user.id_)
    return {"message": "Password updated successfully"}
