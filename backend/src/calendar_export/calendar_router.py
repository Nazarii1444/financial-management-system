"""
Recurring payments → calendars.

Three ways, all built from the same rules:
- `GET /recurring.ics`            one-off .ics download (any calendar, no account access)
- `/feed` + `GET /feed/{token}.ics` secret subscription URL (iPhone / macOS `webcal://`,
                                   Google "From URL"); the calendar app re-fetches it
- `/google/*`                      Google Calendar API: events pushed and kept in sync
"""
import base64
import io
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote, urlencode

import httpx
import jwt
import qrcode
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.calendar_export import google_calendar as gcal
from src.calendar_export.formatting import normalize_lang
from src.calendar_export.ics import build_calendar
from src.calendar_export.schemas import (
    CalendarFeedOut,
    GoogleCalendarStatusOut,
    GoogleConnectOut,
    GoogleSyncOut,
)
from src.config import (
    ALGORITHM,
    FRONTEND_URL,
    GOOGLE_CALENDAR_REDIRECT_URI,
    PUBLIC_API_URL,
    SECRET_KEY,
    logger,
)
from src.database import get_db
from src.dependencies import get_current_user
from src.models import CalendarFeed, GoogleCalendarLink, RecurringTransaction, User

calendar_router = APIRouter()

_ICS_MEDIA_TYPE = "text/calendar; charset=utf-8"
_STATE_TYPE = "gcal_state"   # never carries "sub", so it can't pass as an access token


def _api_base(request: Request) -> str:
    return PUBLIC_API_URL or str(request.base_url).rstrip("/")


async def _user_rules(session: AsyncSession, user_id: int):
    stmt = (
        select(RecurringTransaction)
        .where(RecurringTransaction.user_id == user_id, RecurringTransaction.is_active.is_(True))
        .order_by(RecurringTransaction.id_)
    )
    return (await session.execute(stmt)).scalars().all()


def _ics_response(body: str, filename: Optional[str] = None) -> Response:
    headers = {"Cache-Control": "no-cache"}
    if filename:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return Response(content=body.encode("utf-8"), media_type=_ICS_MEDIA_TYPE, headers=headers)


# ── 1. One-off .ics download ──────────────────────────────────────────────────

@calendar_router.get("/recurring.ics", response_class=Response, summary="Download recurring rules as .ics")
async def download_ics(
    lang: Optional[str] = Query(None, description="uk | en"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rules = await _user_rules(session, current_user.id_)
    body = build_calendar(rules, current_user.default_currency, current_user.timezone, lang)
    return _ics_response(body, "financehub-payments.ics")


# ── 2. Subscription feed ──────────────────────────────────────────────────────

def _feed_out(request: Request, feed: Optional[CalendarFeed]) -> CalendarFeedOut:
    if feed is None:
        return CalendarFeedOut(active=False)
    url = f"{_api_base(request)}/api/calendar/feed/{feed.token}.ics"
    webcal = "webcal://" + url.split("://", 1)[1]
    google = "https://calendar.google.com/calendar/r?" + urlencode({"cid": webcal})
    buf = io.BytesIO()
    qrcode.make(webcal).save(buf, format="PNG")
    return CalendarFeedOut(
        active=True, url=url, webcal_url=webcal, google_add_url=google,
        qr_code_base64=base64.b64encode(buf.getvalue()).decode(),
        lang=feed.lang, created_at=feed.created_at,
    )


async def _get_feed(session: AsyncSession, user_id: int) -> Optional[CalendarFeed]:
    return (await session.execute(
        select(CalendarFeed).where(CalendarFeed.user_id == user_id)
    )).scalar_one_or_none()


@calendar_router.get("/feed", response_model=CalendarFeedOut)
async def get_feed(
    request: Request,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _feed_out(request, await _get_feed(session, current_user.id_))


@calendar_router.post("/feed", response_model=CalendarFeedOut, summary="Create the subscription URL, or rotate it")
async def create_or_rotate_feed(
    request: Request,
    lang: Optional[str] = Query(None),
    rotate: bool = Query(False, description="Issue a new token; old subscriptions stop updating"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    feed = await _get_feed(session, current_user.id_)
    if feed is None:
        feed = CalendarFeed(user_id=current_user.id_, token=secrets.token_urlsafe(32), lang=normalize_lang(lang))
        session.add(feed)
    else:
        if rotate:
            feed.token = secrets.token_urlsafe(32)
        if lang:
            feed.lang = normalize_lang(lang)
    await session.commit()
    await session.refresh(feed)
    return _feed_out(request, feed)


@calendar_router.delete("/feed", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_feed(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    feed = await _get_feed(session, current_user.id_)
    if feed is not None:
        await session.delete(feed)
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@calendar_router.get("/feed/{token}.ics", response_class=Response, summary="Public iCalendar feed (secret token)")
async def public_feed(token: str, session: AsyncSession = Depends(get_db)):
    feed = (await session.execute(select(CalendarFeed).where(CalendarFeed.token == token))).scalar_one_or_none()
    if feed is None:
        raise HTTPException(status_code=404, detail="Calendar feed not found")
    user = await session.get(User, feed.user_id)
    rules = await _user_rules(session, feed.user_id)
    return _ics_response(build_calendar(rules, user.default_currency, user.timezone, feed.lang))


# ── 3. Google Calendar API ────────────────────────────────────────────────────

def _redirect_uri(request: Request) -> str:
    return GOOGLE_CALENDAR_REDIRECT_URI or f"{_api_base(request)}/api/calendar/google/callback"


async def _get_link(session: AsyncSession, user_id: int) -> Optional[GoogleCalendarLink]:
    return (await session.execute(
        select(GoogleCalendarLink).where(GoogleCalendarLink.user_id == user_id)
    )).scalar_one_or_none()


def _status_out(link: Optional[GoogleCalendarLink]) -> GoogleCalendarStatusOut:
    if link is None:
        return GoogleCalendarStatusOut(configured=gcal.is_configured(), connected=False)
    url = None
    if link.calendar_id:
        url = "https://calendar.google.com/calendar/r?" + urlencode({"cid": link.calendar_id})
    return GoogleCalendarStatusOut(
        configured=gcal.is_configured(), connected=True, calendar_id=link.calendar_id,
        calendar_url=url, last_synced_at=link.last_synced_at, last_error=link.last_error,
    )


@calendar_router.get("/google/status", response_model=GoogleCalendarStatusOut)
async def google_status(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _status_out(await _get_link(session, current_user.id_))


@calendar_router.post("/google/connect", response_model=GoogleConnectOut)
async def google_connect(
    request: Request,
    lang: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    if not gcal.is_configured():
        raise HTTPException(status_code=503, detail="Google Calendar is not configured on the server")
    state = jwt.encode(
        {
            "type": _STATE_TYPE,
            "uid": current_user.id_,
            "lang": normalize_lang(lang),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        SECRET_KEY,
        algorithm=ALGORITHM or "HS256",
    )
    return GoogleConnectOut(auth_url=gcal.authorization_url(_redirect_uri(request), state))


def _back_to_app(result: str) -> RedirectResponse:
    return RedirectResponse(f"{FRONTEND_URL}/transactions?gcal={quote(result)}", status_code=302)


@calendar_router.get("/google/callback", name="google_calendar_callback", include_in_schema=False)
async def google_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    session: AsyncSession = Depends(get_db),
):
    if error or not code or not state:
        return _back_to_app("denied" if error == "access_denied" else "error")
    try:
        claims = jwt.decode(state, SECRET_KEY, algorithms=[ALGORITHM or "HS256"])
        if claims.get("type") != _STATE_TYPE:
            raise jwt.InvalidTokenError("wrong state type")
    except jwt.PyJWTError:
        return _back_to_app("error")

    user = await session.get(User, int(claims["uid"]))
    if user is None:
        return _back_to_app("error")

    async with httpx.AsyncClient(timeout=20) as http:
        try:
            tokens = await gcal.GoogleCalendarClient.exchange_code(http, code, _redirect_uri(request))
        except (gcal.GoogleCalendarError, httpx.HTTPError):
            logger.warning("Google Calendar code exchange failed for user_id=%s", user.id_, exc_info=True)
            return _back_to_app("error")

        link = await _get_link(session, user.id_)
        if link is None:
            if not tokens.get("refresh_token"):
                return _back_to_app("error")
            link = GoogleCalendarLink(user_id=user.id_, refresh_token=gcal.encrypt(tokens["refresh_token"]))
            session.add(link)
        link.lang = claims.get("lang") or link.lang or "uk"
        gcal.GoogleCalendarClient(link, http).store_tokens(tokens)
        await session.commit()

        result = await gcal.sync_user(session, user, http)
    return _back_to_app("connected" if result is not None else "sync_error")


@calendar_router.post("/google/sync", response_model=GoogleSyncOut)
async def google_sync(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    link = await _get_link(session, current_user.id_)
    if link is None:
        raise HTTPException(status_code=404, detail="Google Calendar is not connected")
    result = await gcal.sync_user(session, current_user)
    if result is None:
        await session.refresh(link)
        raise HTTPException(status_code=502, detail=link.last_error or "Google Calendar sync failed")
    await session.refresh(link)
    return GoogleSyncOut(**result, last_synced_at=link.last_synced_at)


@calendar_router.delete("/google", status_code=status.HTTP_204_NO_CONTENT)
async def google_disconnect(
    delete_calendar: bool = Query(True, description="Also remove the FinanceHub calendar from Google"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    link = await _get_link(session, current_user.id_)
    if link is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    async with httpx.AsyncClient(timeout=20) as http:
        client = gcal.GoogleCalendarClient(link, http)
        try:
            if delete_calendar:
                await client.delete_calendar()
        except (gcal.GoogleCalendarError, httpx.HTTPError):
            logger.warning("Could not delete Google calendar for user_id=%s", current_user.id_, exc_info=True)
        refresh = gcal.decrypt(link.refresh_token)
        if refresh:
            await gcal.GoogleCalendarClient.revoke(http, refresh)
    await session.delete(link)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def schedule_google_sync(background: BackgroundTasks, user_id: int) -> None:
    """Called by the recurring router after a rule changes."""
    if gcal.is_configured():
        background.add_task(gcal.sync_user_in_background, user_id)
