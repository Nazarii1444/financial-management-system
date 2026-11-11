"""
Passkeys / WebAuthn (SEC-A1) — registration and passwordless sign-in.

Ceremonies (py_webauthn does the cryptography and the checks of origin, RP id,
challenge, signature and flags):

    register:  options (logged in) → navigator.credentials.create() → verify → store public key
    sign in:   options (anonymous) → navigator.credentials.get()    → verify → tokens

Sign-in uses discoverable credentials (no email first): the browser offers the
passkeys it has for this site and the credential id identifies the account.
User verification (biometrics / device PIN) is required, so a passkey is
"something you have" + "something you are/know" and replaces password + TOTP.

Challenges are random, stored server-side, single use (deleted when verified)
and expire after 5 minutes — a replayed response finds no challenge.
"""
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, options_to_json_dict
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from src.config import WEBAUTHN_ORIGINS, WEBAUTHN_RP_ID, WEBAUTHN_RP_NAME
from src.models import User, WebAuthnChallenge, WebAuthnCredential

CHALLENGE_TTL = timedelta(minutes=5)
MAX_PASSKEYS = 10
REGISTER, LOGIN = "register", "login"


class PasskeyError(Exception):
    """`code` is returned to the client as the error detail."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RelyingParty:
    rp_id: str
    name: str
    origins: Tuple[str, ...]


def relying_party() -> RelyingParty:
    return RelyingParty(WEBAUTHN_RP_ID, WEBAUTHN_RP_NAME, tuple(WEBAUTHN_ORIGINS))


# ── Challenges ────────────────────────────────────────────────────────────────

async def _new_challenge(db: AsyncSession, purpose: str, user_id: Optional[int] = None) -> Tuple[str, bytes]:
    now = datetime.now(timezone.utc)
    await db.execute(delete(WebAuthnChallenge).where(WebAuthnChallenge.expires_at < now))
    challenge_id, challenge = secrets.token_urlsafe(32), secrets.token_bytes(32)
    db.add(WebAuthnChallenge(id_=challenge_id, challenge=challenge, purpose=purpose, user_id=user_id,
                             expires_at=now + CHALLENGE_TTL))
    await db.commit()
    return challenge_id, challenge


async def _take_challenge(db: AsyncSession, challenge_id: str, purpose: str, user_id: Optional[int] = None) -> bytes:
    """Fetch and delete (single use) — even a failed verification burns the challenge."""
    row = (await db.execute(select(WebAuthnChallenge).where(WebAuthnChallenge.id_ == challenge_id))).scalar_one_or_none()
    if row is None:
        raise PasskeyError("challenge_expired")
    challenge, row_purpose, row_user, expires_at = row.challenge, row.purpose, row.user_id, row.expires_at
    await db.delete(row)
    await db.commit()
    if row_purpose != purpose or row_user != user_id or expires_at < datetime.now(timezone.utc):
        raise PasskeyError("challenge_expired")
    return challenge


# ── Registration (logged in) ──────────────────────────────────────────────────

async def registration_options(db: AsyncSession, user: User, rp: Optional[RelyingParty] = None) -> Dict[str, Any]:
    rp = rp or relying_party()
    existing = (await db.execute(select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id_))).scalars().all()
    if len(existing) >= MAX_PASSKEYS:
        raise PasskeyError("too_many_passkeys")
    if user.webauthn_user_handle is None:
        user.webauthn_user_handle = secrets.token_bytes(32)
        await db.commit()
    challenge_id, challenge = await _new_challenge(db, REGISTER, user.id_)
    options = generate_registration_options(
        rp_id=rp.rp_id,
        rp_name=rp.name,
        user_id=user.webauthn_user_handle,
        user_name=user.email,
        user_display_name=user.username,
        challenge=challenge,
        timeout=int(CHALLENGE_TTL.total_seconds() * 1000),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,          # discoverable → sign in without email
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        # The same authenticator can't be registered twice
        exclude_credentials=[PublicKeyCredentialDescriptor(id=c.credential_id) for c in existing],
    )
    return {"challenge_id": challenge_id, "public_key": options_to_json_dict(options)}


async def register(db: AsyncSession, user: User, challenge_id: str, credential: Dict[str, Any], name: Optional[str],
                   rp: Optional[RelyingParty] = None) -> WebAuthnCredential:
    rp = rp or relying_party()
    challenge = await _take_challenge(db, challenge_id, REGISTER, user.id_)
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp.rp_id,
            expected_origin=list(rp.origins),
            require_user_verification=True,
        )
    except Exception:
        raise PasskeyError("verification_failed")
    taken = (await db.execute(
        select(WebAuthnCredential.id_).where(WebAuthnCredential.credential_id == verified.credential_id)
    )).scalar_one_or_none()
    if taken:
        raise PasskeyError("already_registered")
    transports = (credential.get("response") or {}).get("transports")
    passkey = WebAuthnCredential(
        user_id=user.id_,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        transports=transports if isinstance(transports, list) else None,
        aaguid=verified.aaguid,
        backed_up=verified.credential_backed_up,
        name=(name or "").strip()[:64] or "Passkey",
    )
    db.add(passkey)
    await db.commit()
    await db.refresh(passkey)
    return passkey


# ── Sign in (anonymous) ───────────────────────────────────────────────────────

async def login_options(db: AsyncSession, rp: Optional[RelyingParty] = None) -> Dict[str, Any]:
    rp = rp or relying_party()
    challenge_id, challenge = await _new_challenge(db, LOGIN)
    options = generate_authentication_options(
        rp_id=rp.rp_id,
        challenge=challenge,
        timeout=int(CHALLENGE_TTL.total_seconds() * 1000),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return {"challenge_id": challenge_id, "public_key": options_to_json_dict(options)}


async def authenticate(db: AsyncSession, challenge_id: str, credential: Dict[str, Any],
                       rp: Optional[RelyingParty] = None) -> Tuple[User, WebAuthnCredential]:
    rp = rp or relying_party()
    challenge = await _take_challenge(db, challenge_id, LOGIN)
    try:
        raw_id = base64url_to_bytes(credential["rawId"])
    except Exception:
        raise PasskeyError("verification_failed")
    passkey = (await db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.credential_id == raw_id)
    )).scalar_one_or_none()
    if passkey is None:
        raise PasskeyError("unknown_passkey")
    user = (await db.execute(select(User).where(User.id_ == passkey.user_id))).scalar_one()

    # Discoverable credentials return the user handle — it must be this account's
    handle = (credential.get("response") or {}).get("userHandle")
    if handle and user.webauthn_user_handle and base64url_to_bytes(handle) != user.webauthn_user_handle:
        raise PasskeyError("verification_failed")
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp.rp_id,
            expected_origin=list(rp.origins),
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except Exception:
        # Includes a sign counter that went backwards (a cloned authenticator)
        raise PasskeyError("verification_failed")
    passkey.sign_count = verified.new_sign_count
    passkey.backed_up = verified.credential_backed_up
    passkey.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return user, passkey


def credential_id_b64(passkey: WebAuthnCredential) -> str:
    return bytes_to_base64url(passkey.credential_id)
