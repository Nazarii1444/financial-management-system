"""
Password reset by e-mailed code.

    request  → a fresh 6-digit code is stored (HMAC only) and e-mailed; previous codes expire
    verify   → checks the code without using it (the UI moves on to the "new password" step)
    confirm  → checks the code again, applies the password policy, sets the password, burns the code

Guards:
- the answer to `request` never reveals whether the e-mail is registered;
- a code lives PASSWORD_RESET_CODE_TTL_MINUTES, is single-use and dies after MAX_ATTEMPTS wrong tries;
- at most one code per RESEND_INTERVAL and MAX_CODES_PER_HOUR per account (no mail bombing);
- the code is bound to the account in its HMAC, so a code can't be replayed for another user.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src import config
from src.models import PasswordResetCode, User

CODE_DIGITS = 6
MAX_ATTEMPTS = 5
RESEND_INTERVAL = timedelta(seconds=60)
MAX_CODES_PER_HOUR = 5

INVALID_CODE = "Invalid or expired code"
TOO_MANY_ATTEMPTS = "Too many attempts. Request a new code"


class ResetError(ValueError):
    pass


def generate_code() -> str:
    return f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"


def hash_code(user_id: int, code: str) -> str:
    return hmac.new(config.SECRET_KEY.encode(), f"{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def code_matches(user_id: int, code: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_code(user_id, code), stored_hash)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def issue_code(session: AsyncSession, user: User, now: Optional[datetime] = None) -> Optional[str]:
    """
    Store a new code for *user* and return it (the caller e-mails it), or None when the
    rate limit says no. Earlier codes are expired so only the newest one works.
    """
    now = now or _utcnow()
    recent = (await session.execute(
        select(func.count(PasswordResetCode.id_), func.max(PasswordResetCode.created_at)).where(
            PasswordResetCode.user_id == user.id_,
            PasswordResetCode.created_at > now - timedelta(hours=1),
        )
    )).one()
    count, last = recent
    if count >= MAX_CODES_PER_HOUR or (last is not None and now - last < RESEND_INTERVAL):
        return None

    await session.execute(
        update(PasswordResetCode)
        .where(PasswordResetCode.user_id == user.id_, PasswordResetCode.used_at.is_(None),
               PasswordResetCode.expires_at > now)
        .values(expires_at=now)
    )
    code = generate_code()
    session.add(PasswordResetCode(
        user_id=user.id_,
        code_hash=hash_code(user.id_, code),
        created_at=now,
        expires_at=now + timedelta(minutes=config.PASSWORD_RESET_CODE_TTL_MINUTES),
    ))
    await session.commit()
    return code


async def check_code(session: AsyncSession, user: Optional[User], code: str,
                     now: Optional[datetime] = None) -> PasswordResetCode:
    """
    Return the active code row when *code* is right; otherwise count the attempt and raise
    ResetError. An unknown user gets the same error as a wrong code.
    """
    now = now or _utcnow()
    if user is None or not code.isdigit() or len(code) != CODE_DIGITS:
        raise ResetError(INVALID_CODE)
    row = (await session.execute(
        select(PasswordResetCode)
        .where(PasswordResetCode.user_id == user.id_, PasswordResetCode.used_at.is_(None),
               PasswordResetCode.expires_at > now)
        .order_by(PasswordResetCode.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if row is None:
        raise ResetError(INVALID_CODE)
    if row.attempts >= MAX_ATTEMPTS:
        raise ResetError(TOO_MANY_ATTEMPTS)
    if not code_matches(user.id_, code, row.code_hash):
        row.attempts += 1
        if row.attempts >= MAX_ATTEMPTS:
            row.expires_at = now
        await session.commit()
        raise ResetError(TOO_MANY_ATTEMPTS if row.attempts >= MAX_ATTEMPTS else INVALID_CODE)
    return row


async def consume(session: AsyncSession, row: PasswordResetCode, now: Optional[datetime] = None) -> None:
    """Mark the code used and expire any other live code of the same user (flush only)."""
    now = now or _utcnow()
    row.used_at = now
    await session.execute(
        update(PasswordResetCode)
        .where(PasswordResetCode.user_id == row.user_id, PasswordResetCode.id_ != row.id_,
               PasswordResetCode.used_at.is_(None))
        .values(expires_at=now)
    )
