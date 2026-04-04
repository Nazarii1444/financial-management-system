from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, RedirectResponse

from src.auth.auth_services import create_user
from src.auth.schemas import UserCreate
from src.config import (
    GITHUB_CLIENT_ID,
    GITHUB_CLIENT_SECRET,
    JWT_ACCESS_COOKIE_NAME,
    JWT_REFRESH_COOKIE_NAME
)
from src.database import get_db
from src.utils.getters_services import get_user_by_email
from src.utils.jwt_handlers import create_access_token, create_refresh_token

github_oauth_router = APIRouter(prefix="/auth/github", tags=["auth-github"])

oauth = OAuth()
oauth.register(
    name="github",
    client_id=GITHUB_CLIENT_ID,
    client_secret=GITHUB_CLIENT_SECRET,
    authorize_url="https://github.com/login/oauth/authorize",
    access_token_url="https://github.com/login/oauth/access_token",
    api_base_url="https://api.github.com/",
    client_kwargs={
        "scope": "read:user user:email",
        "token_placement": "header",
    },
)


@github_oauth_router.get("/login")
async def github_login(request: Request):
    redirect_uri = request.url_for("github_callback")
    return await oauth.github.authorize_redirect(
        request,
        redirect_uri,
    )


@github_oauth_router.get("/callback", name="github_callback")
async def github_callback(
        request: Request,
        db: AsyncSession = Depends(get_db),
):
    """
        "message": "Signed in with GitHub",
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxNiIsInVzZXJuYW1lIjoiTmF6YXJpaTE0NDQiLCJleHAiOjE3NTkwODI5OTh9.NCMe0Vxjm53G61Iip_npuzzBuEuJzw_s0rcMgmQaGqI",
        "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxNiIsImV4cCI6MTc2MTY2Nzc5OH0.hYfyv-YhMtqz--od_gGFlWtJB7yUb5Bwx5__pHXrEZQ",
        "token_type": "bearer",
        "user_id": 1,
        "login": "Vitalik2705",
        "name": "Vitalii Yatskiv",
        "avatar_url": "https://avatars.githubusercontent.com/u/171423267?v=4"
    """
    token = await oauth.github.authorize_access_token(request)
    if not token:
        return JSONResponse(status_code=400, content={"detail": "Token exchange failed"})

    resp_user = await oauth.github.get("user", token=token)
    if resp_user.status_code != 200:
        return JSONResponse(status_code=400, content={"detail": "Failed to fetch GitHub user"})
    gh_user = resp_user.json()

    email = None
    resp_emails = await oauth.github.get("user/emails", token=token)
    if resp_emails.status_code == 200:
        emails = resp_emails.json()
        primary_verified = next((e for e in emails if e.get("primary") and e.get("verified")), None)
        if primary_verified:
            email = (primary_verified.get("email") or "").lower()
        else:
            verified_any = next((e for e in emails if e.get("verified")), None)
            if verified_any:
                email = (verified_any.get("email") or "").lower()

    if not email:
        email = (gh_user.get("email") or "").lower()

    if not email:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "No verified email available from GitHub"},
        )

    user = await get_user_by_email(db, email)
    username = gh_user.get("login") or email.split("@")[0]
    if not user:
        user = await create_user(
            db,
            UserCreate(
                username=username,
                email=email,
                password="__github_oauth__",
            )
        )

    access_token = await create_access_token({"sub": str(user.id_), "username": username})
    refresh_token = await create_refresh_token({"sub": str(user.id_)})

    resp = JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": "Signed in with GitHub",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user_id": user.id_,
            "login": gh_user.get("login"),
            "name": gh_user.get("name"),
            "avatar_url": gh_user.get("avatar_url"),
        },
    )
    resp.set_cookie(JWT_ACCESS_COOKIE_NAME, access_token)
    resp.set_cookie(JWT_REFRESH_COOKIE_NAME, refresh_token)

    # return RedirectResponse(url=FRONTEND_SUCCESS_URL, status_code=302)

    return resp
