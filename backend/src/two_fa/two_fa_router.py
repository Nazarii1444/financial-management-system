import io
import base64
import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.database import get_db
from src.models import User
from src.dependencies import get_current_user
from src.two_fa.schemas import TwoFASetupResponse, TwoFAVerifyRequest

two_fa_router = APIRouter()


@two_fa_router.post("/setup", response_model=TwoFASetupResponse)
async def setup_2fa(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a new TOTP secret and QR code.
    If 2FA is already enabled, returns 409 — disable it first.
    If 2FA was set up but not verified yet, regenerates the secret.
    """
    if current_user.twofa_enabled:
        raise HTTPException(
            status_code=409,
            detail="2FA is already enabled. Disable it first via POST /api/2fa/disable",
        )

    user = (await session.execute(select(User).where(User.id_ == current_user.id_))).scalar_one()
    secret = pyotp.random_base32()
    user.twofa_secret = secret
    await session.commit()

    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="FinanceSystem")
    buf = io.BytesIO()
    qrcode.make(uri).save(buf, format="PNG")
    qr_base64 = base64.b64encode(buf.getvalue()).decode()

    return TwoFASetupResponse(qr_code_base64=qr_base64, secret=secret)


@two_fa_router.post("/verify")
async def verify_2fa(
    payload: TwoFAVerifyRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify TOTP code after /setup and activate 2FA."""
    user = (await session.execute(select(User).where(User.id_ == current_user.id_))).scalar_one()

    if not user.twofa_secret:
        raise HTTPException(status_code=400, detail="2FA not set up — call /setup first")

    if not pyotp.TOTP(user.twofa_secret).verify(payload.code):
        raise HTTPException(status_code=401, detail="Invalid 2FA code")

    user.twofa_enabled = True
    await session.commit()
    return {"message": "2FA enabled successfully"}


@two_fa_router.post("/disable", status_code=status.HTTP_200_OK)
async def disable_2fa(
    payload: TwoFAVerifyRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Disable 2FA. Requires a valid TOTP code to confirm it's the account owner.
    After disabling, login no longer requires a TOTP code.
    """
    user = (await session.execute(select(User).where(User.id_ == current_user.id_))).scalar_one()

    if not user.twofa_enabled:
        raise HTTPException(status_code=409, detail="2FA is not enabled")

    if not pyotp.TOTP(user.twofa_secret).verify(payload.code):
        raise HTTPException(status_code=401, detail="Invalid 2FA code")

    user.twofa_enabled = False
    user.twofa_secret = None
    await session.commit()
    return {"message": "2FA disabled successfully"}
