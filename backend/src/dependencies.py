from fastapi import Depends, HTTPException, status
from typing import Optional

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from src.database import get_db
from src.models import User
from src.utils.security import decode_token

# Plain bearer scheme: Swagger's "Authorize" shows a single box for the access
# token returned by POST /api/auth/login (which takes JSON, not an OAuth2 form).
# auto_error=False so a missing token is a 401 (HTTPBearer's default is 403).
oauth2_scheme = HTTPBearer(bearerFormat="JWT", auto_error=False)

# Token types that are NOT valid for regular API access
_BLOCKED_TOKEN_TYPES = {"refresh", "2fa_pending"}


async def get_current_user_id_from_token(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(oauth2_scheme),
) -> int:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
        token_type = payload.get("type")
        # Allow tokens without 'type' for backward compatibility
        if token_type in _BLOCKED_TOKEN_TYPES:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token type '{token_type}' cannot be used for API access",
            )
        sub = payload.get("sub")
        exp = int(payload.get("exp"))
        now = int(datetime.now(timezone.utc).timestamp())
        if now > exp:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
        user_id = int(sub)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token")
    return user_id


async def get_current_user(
        db: AsyncSession = Depends(get_db),
        user_id: int = Depends(get_current_user_id_from_token),
) -> User:
    user = (await db.execute(select(User).where(User.id_ == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
