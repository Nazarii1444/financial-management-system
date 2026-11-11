"""
/api/passkeys/* — passkey (WebAuthn) management and passwordless sign-in.

    POST   /register/options     (auth)  creation options for navigator.credentials.create()
    POST   /register             (auth)  verify the new credential and store its public key
    GET    /                     (auth)  list
    PATCH  /{id}                 (auth)  rename
    DELETE /{id}                 (auth)  remove
    POST   /login/options                request options for navigator.credentials.get()
    POST   /login                        verify → access / refresh tokens (skips TOTP: the
                                         passkey already proves possession + user verification)

Errors: 400 with a code in `detail` — challenge_expired, verification_failed,
unknown_passkey, already_registered, too_many_passkeys.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import TokenPair
from src.config import logger
from src.database import get_db
from src.dependencies import get_current_user
from src.models import User, WebAuthnCredential
from src.security import passkeys
from src.security.events import EventType, record_event
from src.utils.jwt_handlers import create_access_token, create_refresh_token

passkey_router = APIRouter()


class OptionsOut(BaseModel):
    challenge_id: str
    public_key: Dict[str, Any]      # PublicKeyCredential{Creation,Request}Options as JSON (base64url)


class RegisterIn(BaseModel):
    challenge_id: str = Field(max_length=64)
    credential: Dict[str, Any]      # PublicKeyCredential serialised by the browser (toJSON shape)
    name: Optional[str] = Field(None, max_length=64)


class LoginIn(BaseModel):
    challenge_id: str = Field(max_length=64)
    credential: Dict[str, Any]


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class PasskeyOut(BaseModel):
    id_: int
    name: str
    created_at: datetime
    last_used_at: Optional[datetime]
    backed_up: bool                 # synced across devices (iCloud Keychain, Google Password Manager…)
    transports: Optional[List[str]]


def _out(p: WebAuthnCredential) -> PasskeyOut:
    return PasskeyOut(id_=p.id_, name=p.name, created_at=p.created_at, last_used_at=p.last_used_at,
                      backed_up=p.backed_up, transports=p.transports)


def _bad(exc: passkeys.PasskeyError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.code)


async def _own_passkey(db: AsyncSession, user: User, passkey_id: int) -> WebAuthnCredential:
    passkey = (await db.execute(select(WebAuthnCredential).where(
        WebAuthnCredential.id_ == passkey_id, WebAuthnCredential.user_id == user.id_,
    ))).scalar_one_or_none()
    if passkey is None:
        raise HTTPException(status_code=404, detail="Passkey not found")
    return passkey


@passkey_router.post("/register/options", response_model=OptionsOut)
async def register_options(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        return await passkeys.registration_options(db, current_user)
    except passkeys.PasskeyError as exc:
        raise _bad(exc)


@passkey_router.post("/register", response_model=PasskeyOut, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterIn, request: Request, db: AsyncSession = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    try:
        passkey = await passkeys.register(db, current_user, payload.challenge_id, payload.credential, payload.name)
    except passkeys.PasskeyError as exc:
        raise _bad(exc)
    await record_event(db, current_user.id_, EventType.PASSKEY_ADDED, request, method="passkey",
                       details={"name": passkey.name})
    logger.info("Passkey registered for user id=%s", current_user.id_)
    return _out(passkey)


@passkey_router.get("", response_model=List[PasskeyOut])
async def list_passkeys(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (await db.execute(select(WebAuthnCredential).where(WebAuthnCredential.user_id == current_user.id_)
                             .order_by(WebAuthnCredential.created_at))).scalars().all()
    return [_out(p) for p in rows]


@passkey_router.patch("/{passkey_id}", response_model=PasskeyOut)
async def rename_passkey(passkey_id: int, payload: RenameIn, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    passkey = await _own_passkey(db, current_user, passkey_id)
    passkey.name = payload.name.strip() or passkey.name
    await db.commit()
    await db.refresh(passkey)
    return _out(passkey)


@passkey_router.delete("/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_passkey(passkey_id: int, request: Request, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    passkey = await _own_passkey(db, current_user, passkey_id)
    name = passkey.name
    await db.delete(passkey)
    await db.commit()
    await record_event(db, current_user.id_, EventType.PASSKEY_REMOVED, request, method="passkey", details={"name": name})


@passkey_router.post("/login/options", response_model=OptionsOut)
async def login_options(db: AsyncSession = Depends(get_db)):
    return await passkeys.login_options(db)


@passkey_router.post("/login", response_model=TokenPair)
async def login(payload: LoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        user, passkey = await passkeys.authenticate(db, payload.challenge_id, payload.credential)
    except passkeys.PasskeyError as exc:
        # A known credential with a bad signature is an attempt on that account — show it in its history
        if exc.code == "verification_failed":
            await _record_failed(db, payload.credential, request)
        raise _bad(exc)
    await record_event(db, user.id_, EventType.LOGIN, request, method="passkey", details={"passkey": passkey.name})
    logger.info("Passkey sign-in: user id=%s", user.id_)
    return TokenPair(
        access_token=await create_access_token({"sub": str(user.id_)}),
        refresh_token=await create_refresh_token({"sub": str(user.id_)}),
    )


async def _record_failed(db: AsyncSession, credential: Dict[str, Any], request: Request) -> None:
    try:
        raw_id = passkeys.base64url_to_bytes(credential["rawId"])
    except Exception:
        return
    passkey = (await db.execute(select(WebAuthnCredential).where(WebAuthnCredential.credential_id == raw_id))).scalar_one_or_none()
    if passkey:
        await record_event(db, passkey.user_id, EventType.LOGIN, request, success=False, method="passkey",
                           details={"reason": "verification_failed", "passkey": passkey.name})
