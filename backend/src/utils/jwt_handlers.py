from datetime import datetime, timedelta, timezone

import jwt

from src.utils.config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, REFRESH_TOKEN_EXPIRE_DAYS
from src.config import SECRET_KEY

_2FA_PENDING_EXPIRE_MINUTES = 5


async def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def create_2fa_pending_token(user_id: int) -> str:
    """Short-lived token (5 min) returned when user needs to complete 2FA."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=_2FA_PENDING_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire, "type": "2fa_pending"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
