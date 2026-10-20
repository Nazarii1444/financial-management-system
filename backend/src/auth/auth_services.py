import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import UserCreate
from src.models import User
from src.security import password_policy
from src.utils.getters_services import get_user_by_email
from src.utils.auth_services import hash_password, verify_password

# Placeholders older Google / GitHub sign-ups were created with. They were hashed like real
# passwords, so "email + __google_oauth__" logged anyone in — refuse them explicitly.
_LEGACY_OAUTH_PASSWORDS = {"__google_oauth__", "__github_oauth__"}

# Re-check the stored password against HIBP at most this often (done on successful login)
BREACH_RECHECK_INTERVAL = timedelta(days=7)


def oauth_placeholder_password() -> str:
    """Random, never shown: OAuth accounts sign in through the provider (or a passkey)."""
    return secrets.token_urlsafe(32)


def _set_password(user: User, password: str, score: Optional[int], breached: Optional[bool]) -> None:
    now = datetime.now(timezone.utc)
    user.hashed_password = hash_password(password)
    user.password_changed_at = now
    user.password_score = score
    user.password_breached = breached
    user.password_checked_at = now if breached is not None else None


async def create_user(db: AsyncSession, user: UserCreate, oauth: bool = False) -> User:
    """New user creation. *oauth*: password is a random placeholder, not tracked as a real one."""
    new_user = User(username=user.username, email=user.email, capital=0.0)
    if oauth:
        new_user.hashed_password = hash_password(user.password)
    else:
        report = password_policy.evaluate(user.password, user.username, user.email)
        # Signup already passed check_password (incl. HIBP) — the password is known not to be leaked
        _set_password(new_user, user.password, report.score, False if report.acceptable else None)

    db.add(new_user)
    await db.flush()
    await db.commit()
    await db.refresh(new_user)
    return new_user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email)
    if not user or not getattr(user, "hashed_password", None):
        return None
    if password in _LEGACY_OAUTH_PASSWORDS or len(password.encode("utf-8")) > password_policy.MAX_BYTES:
        return None   # bcrypt refuses > 72 bytes; such a password was never accepted
    if not verify_password(password, user.hashed_password):
        return None
    return user


def needs_breach_recheck(user: User, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return user.password_checked_at is None or now - user.password_checked_at > BREACH_RECHECK_INTERVAL


async def refresh_password_health(db: AsyncSession, user: User, password: str) -> None:
    """
    After a successful password login: the plaintext is available for a moment, so
    re-check it against HIBP (new breaches appear over time) and back-fill the
    strength score for passwords set before it was tracked.
    """
    if user.password_score is None:
        user.password_score = password_policy.evaluate(password, user.username, user.email).score
    breached = await password_policy.is_breached(password)
    if breached is not None:
        user.password_breached = breached
        user.password_checked_at = datetime.now(timezone.utc)
    await db.commit()


async def change_password(db: AsyncSession, user: User, old_password: str, new_password: str) -> None:
    """Verify old password then store new hash. Raises ValueError on failure."""
    if not verify_password(old_password, user.hashed_password):
        raise ValueError("Current password is incorrect")

    report = await password_policy.check_password(new_password, user.username, user.email)
    if report.errors:
        raise ValueError("; ".join(report.errors))
    if verify_password(new_password, user.hashed_password):
        raise ValueError("New password must differ from the current one")

    _set_password(user, new_password, report.score, False)
    await db.commit()


async def check_password_strength(password: str, username: Optional[str] = None, email: Optional[str] = None) -> list[str]:
    """Returns a list of error strings; empty list means password is acceptable."""
    return (await password_policy.check_password(password, username, email)).errors
