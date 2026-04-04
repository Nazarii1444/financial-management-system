import re
import hashlib
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from src.auth.schemas import UserCreate
from src.models import User
from src.utils.getters_services import get_user_by_email
from src.utils.auth_services import hash_password, verify_password
from src.auth.password_validator import validate_password


async def create_user(db: AsyncSession, user: UserCreate) -> User:
    """New user creation"""
    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hash_password(user.password),
        capital=0.0
    )

    db.add(new_user)
    await db.flush()
    await db.commit()
    await db.refresh(new_user)
    return new_user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email)
    if not user or not getattr(user, "hashed_password", None):
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user


async def change_password(db: AsyncSession, user: User, old_password: str, new_password: str) -> None:
    """Verify old password then store new hash. Raises ValueError on failure."""
    if not verify_password(old_password, user.hashed_password):
        raise ValueError("Current password is incorrect")

    errors = await check_password_strength(new_password)
    if errors:
        raise ValueError("; ".join(errors))

    user.hashed_password = hash_password(new_password)
    await db.commit()


async def check_password_strength(password: str) -> list[str]:
    """Returns a list of error strings; empty list means password is acceptable.
    Uses httpx (async) for the HIBP check — does NOT block the event loop."""
    errors = []

    if len(password) < 8:
        errors.append("Password must be at least 8 characters")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain an uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain a lowercase letter")
    if not re.search(r"\d", password):
        errors.append("Password must contain a number")
    if not re.search(r"[@$!%*?&]", password):
        errors.append("Password must contain a special character")
    if not validate_password(password):
        errors.append("Password too common")

    # HIBP k-anonymity check (async — no event loop blocking)
    try:
        sha1 = hashlib.sha1(password.encode()).hexdigest().upper()
        prefix, suffix = sha1[:5], sha1[5:]
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"https://api.pwnedpasswords.com/range/{prefix}")
        if suffix in resp.text:
            errors.append("Password found in leaked databases")
    except Exception:
        pass  # HIBP unreachable — skip the check, don't block signup

    return errors
