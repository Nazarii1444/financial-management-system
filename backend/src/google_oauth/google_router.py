from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, status
from starlette.responses import JSONResponse, RedirectResponse
from authlib.integrations.starlette_client import OAuth
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import (
    FRONTEND_URL,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    JWT_ACCESS_COOKIE_NAME,
    JWT_REFRESH_COOKIE_NAME
)
from src.database import get_db
from src.utils.getters_services import get_user_by_email
from src.auth.auth_services import create_user, oauth_placeholder_password
from src.security.events import EventType, record_event
from src.auth.schemas import UserCreate
from src.utils.jwt_handlers import create_access_token, create_refresh_token

google_oauth_router = APIRouter(prefix="/auth/google")

oauth = OAuth()
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

@google_oauth_router.get("/login")
async def google_login(request: Request):
    redirect_uri = request.url_for("google_callback")
    return await oauth.google.authorize_redirect(
        request,
        redirect_uri,
        prompt="select_account",
    )

@google_oauth_router.get("/callback", name="google_callback")
async def google_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Response example
    {
      "message": "Signed in with Google",
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxNiIsInVzZXJuYW1lIjoicm9zYWthMTQyOSIsImV4cCI6MTc1OTA4MjA2NH0.o9srHWLPNDsL2FY0b9S-rtezuknus3zlvlWBgevFg_Q",
      "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxNiIsImV4cCI6MTc2MTY2Njg2NH0.wH2uNM0MUaOaIW4X7go-9X31hBy3kKY5S9J6GryPxqI",
      "token_type": "bearer",
      "user_id": 1,
      "email": "user1@example.com",
      "name": "Vitalii Yatskiv",
      "picture": "https://lh3.googleusercontent.com/a/ACg8ocL-l2MBdKSbsG6mlh1V_Teng9vUhVy_BnsIAiDbGTPL4jE0LD0=s96-c"
    }
    """

    token = await oauth.google.authorize_access_token(request)
    if not token:
        return JSONResponse(status_code=400, content={"detail": "Token exchange failed"})

    userinfo = token.get("userinfo") or await oauth.google.parse_id_token(request, token)
    if not userinfo:
        return JSONResponse(status_code=400, content={"detail": "Failed to retrieve Google user info"})

    email = (userinfo.get("email") or "").lower()
    email_verified = userinfo.get("email_verified", False)
    full_name = userinfo.get("name")
    picture = userinfo.get("picture")

    if not email or not email_verified:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Google account email not available or not verified"},
        )

    user = await get_user_by_email(db, email)
    username = email.split("@")[0]
    if not user:
        user = await create_user(
            db,
            UserCreate(
                username=username,
                email=email,
                password=oauth_placeholder_password(),
            ),
            oauth=True,
        )

    await record_event(db, user.id_, EventType.LOGIN, request, method="google")
    access_token = await create_access_token({"sub": str(user.id_), "username": username})
    refresh_token = await create_refresh_token({"sub": str(user.id_)})

    # Hand the tokens back to the SPA (fragment is never sent to servers / logs)
    fragment = urlencode({"access_token": access_token, "refresh_token": refresh_token})
    redirect = RedirectResponse(url=f"{FRONTEND_URL}/oauth/callback#{fragment}", status_code=302)
    redirect.set_cookie(JWT_ACCESS_COOKIE_NAME, access_token, httponly=True, secure=True, samesite="lax")
    redirect.set_cookie(JWT_REFRESH_COOKIE_NAME, refresh_token, httponly=True, secure=True, samesite="lax")
    return redirect
