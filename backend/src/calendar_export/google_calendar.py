"""
Google Calendar API sync for recurring rules.

Flow
----
1. `POST /api/calendar/google/connect` → consent URL (scope `calendar.app.created`:
   the app may only see/manage calendars it created itself).
2. Google redirects to `GET /api/calendar/google/callback` → code exchanged for
   tokens, a dedicated "FinanceHub — payments" calendar is created and a full
   sync runs.
3. Every create/update/delete of a recurring rule triggers `sync_user` in the
   background, so a changed subscription price updates the event in place.

Sync is idempotent: each rule maps to a deterministic event id
(`event_id(rule)`), upserted with PUT (falling back to insert on 404).
Events in the app's calendar whose rule no longer exists or is paused are
deleted. If the user deleted the calendar, it is recreated.
"""
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from urllib.parse import quote, urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.calendar_export.formatting import TEXT, event_description, event_title, normalize_lang
from src.calendar_export.ics import rrule, series_start, local_date
from src.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SECRET_KEY, logger
from src.models import GoogleCalendarLink, RecurringTransaction, TransactionKind, User

SCOPE = "https://www.googleapis.com/auth/calendar.app.created"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/calendar/v3"

EXPENSE_COLOR = "8"   # graphite
INCOME_COLOR = "10"   # basil (green)
REMINDER_MINUTES = 15 * 60  # 09:00 the day before an all-day event


class GoogleCalendarError(Exception):
    pass


def is_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


# ── Token encryption ──────────────────────────────────────────────────────────

def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(f"gcal:{SECRET_KEY}".encode()).digest())
    return Fernet(key)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None


# ── Pure mapping ──────────────────────────────────────────────────────────────

def event_id(rule) -> str:
    """Deterministic Google event id (base32hex alphabet: a–v, 0–9)."""
    return f"fms{rule.user_id}r{rule.id_}"


def build_event(rule, default_currency: str, tzname: Optional[str], lang: str) -> dict:
    start = series_start(rule, tzname)
    month_day = local_date(rule.next_run, tzname).day
    currency = (rule.currency or default_currency or "").upper()
    body = {
        "id": event_id(rule),
        "summary": event_title(rule, currency, lang),
        "description": event_description(rule, lang),
        "start": {"date": start.isoformat()},
        "end": {"date": (start + timedelta(days=1)).isoformat()},
        "recurrence": [f"RRULE:{rrule(rule.frequency, start, month_day)}"],
        "transparency": "transparent",
        "colorId": INCOME_COLOR if rule.kind == TransactionKind.INCOME else EXPENSE_COLOR,
        "extendedProperties": {"private": {"fms": "1", "rule_id": str(rule.id_)}},
        "status": "confirmed",
    }
    if rule.kind == TransactionKind.EXPENSE:
        body["reminders"] = {"useDefault": False, "overrides": [{"method": "popup", "minutes": REMINDER_MINUTES}]}
    else:
        body["reminders"] = {"useDefault": False, "overrides": []}
    return body


def authorization_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",          # always return a refresh token
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


# ── HTTP client ───────────────────────────────────────────────────────────────

class GoogleCalendarClient:
    """Thin async wrapper around the endpoints we use. `http` is injectable for tests."""

    def __init__(self, link: GoogleCalendarLink, http: httpx.AsyncClient):
        self.link = link
        self.http = http

    @staticmethod
    async def exchange_code(http: httpx.AsyncClient, code: str, redirect_uri: str) -> dict:
        resp = await http.post(TOKEN_URL, data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
        if resp.status_code != 200:
            raise GoogleCalendarError(f"Token exchange failed ({resp.status_code})")
        return resp.json()

    @staticmethod
    async def revoke(http: httpx.AsyncClient, token: str) -> None:
        try:
            await http.post(REVOKE_URL, data={"token": token})
        except httpx.HTTPError:
            logger.warning("Google token revoke failed", exc_info=True)

    def store_tokens(self, tokens: dict) -> None:
        if tokens.get("refresh_token"):
            self.link.refresh_token = encrypt(tokens["refresh_token"])
        self.link.access_token = encrypt(tokens["access_token"])
        self.link.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(tokens.get("expires_in", 3600)) - 60)

    async def _access_token(self) -> str:
        token = decrypt(self.link.access_token)
        expires = self.link.token_expires_at
        if token and expires and expires > datetime.now(timezone.utc):
            return token
        refresh = decrypt(self.link.refresh_token)
        if not refresh:
            raise GoogleCalendarError("Google connection lost — reconnect the calendar")
        resp = await self.http.post(TOKEN_URL, data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        })
        if resp.status_code != 200:
            raise GoogleCalendarError("Google access was revoked — reconnect the calendar")
        self.store_tokens(resp.json())
        return decrypt(self.link.access_token)

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        token = await self._access_token()
        headers = {"Authorization": f"Bearer {token}"}
        return await self.http.request(method, f"{API}{path}", headers=headers, **kwargs)

    async def create_calendar(self, lang: str, tzname: Optional[str]) -> str:
        body = {"summary": TEXT[lang]["calendar_name"], "description": TEXT[lang]["calendar_description"]}
        if tzname:
            body["timeZone"] = tzname
        resp = await self.request("POST", "/calendars", json=body)
        if resp.status_code not in (200, 201):
            raise GoogleCalendarError(f"Could not create calendar ({resp.status_code})")
        return resp.json()["id"]

    async def delete_calendar(self) -> None:
        if self.link.calendar_id:
            await self.request("DELETE", f"/calendars/{quote(self.link.calendar_id, safe='')}")

    def _events_path(self, eid: str = "") -> str:
        path = f"/calendars/{quote(self.link.calendar_id, safe='')}/events"
        return f"{path}/{eid}" if eid else path

    async def upsert_event(self, body: dict) -> None:
        resp = await self.request("PUT", self._events_path(body["id"]), json=body)
        if resp.status_code == 404:
            resp = await self.request("POST", self._events_path(), json=body)
        if resp.status_code == 404:
            raise CalendarMissing()
        if resp.status_code not in (200, 201):
            raise GoogleCalendarError(f"Event sync failed ({resp.status_code})")

    async def list_event_ids(self) -> List[str]:
        ids, page = [], None
        while True:
            params = {"privateExtendedProperty": "fms=1", "maxResults": 2500, "showDeleted": "false"}
            if page:
                params["pageToken"] = page
            resp = await self.request("GET", self._events_path(), params=params)
            if resp.status_code == 404:
                raise CalendarMissing()
            if resp.status_code != 200:
                raise GoogleCalendarError(f"Listing events failed ({resp.status_code})")
            data = resp.json()
            ids += [item["id"] for item in data.get("items", [])]
            page = data.get("nextPageToken")
            if not page:
                return ids

    async def delete_event(self, eid: str) -> None:
        resp = await self.request("DELETE", self._events_path(eid))
        if resp.status_code not in (200, 204, 404, 410):
            raise GoogleCalendarError(f"Deleting event failed ({resp.status_code})")


class CalendarMissing(GoogleCalendarError):
    """The app's calendar was deleted on Google's side."""


# ── Sync ──────────────────────────────────────────────────────────────────────

async def sync_rules(client: GoogleCalendarClient, user: User, rules: List[RecurringTransaction]) -> Dict[str, int]:
    """Push active rules, delete stale events. Recreates the calendar once if it vanished."""
    link = client.link
    lang = normalize_lang(link.lang)
    for attempt in range(2):
        try:
            if not link.calendar_id:
                link.calendar_id = await client.create_calendar(lang, user.timezone)
            active = [r for r in rules if r.is_active]
            for rule in active:
                await client.upsert_event(build_event(rule, user.default_currency, user.timezone, lang))
            wanted = {event_id(r) for r in active}
            stale = [eid for eid in await client.list_event_ids() if eid not in wanted]
            for eid in stale:
                await client.delete_event(eid)
            return {"synced": len(active), "deleted": len(stale)}
        except CalendarMissing:
            if attempt:
                raise
            link.calendar_id = None
    return {"synced": 0, "deleted": 0}


async def sync_user(session: AsyncSession, user: User, http: Optional[httpx.AsyncClient] = None) -> Optional[Dict[str, int]]:
    """Full sync for *user* if they connected Google Calendar. Commits link state; never raises."""
    link = (await session.execute(
        select(GoogleCalendarLink).where(GoogleCalendarLink.user_id == user.id_)
    )).scalar_one_or_none()
    if link is None or not is_configured():
        return None
    rules = (await session.execute(
        select(RecurringTransaction).where(RecurringTransaction.user_id == user.id_)
    )).scalars().all()

    own_http = http is None
    http = http or httpx.AsyncClient(timeout=20)
    try:
        result = await sync_rules(GoogleCalendarClient(link, http), user, rules)
        link.last_synced_at = datetime.now(timezone.utc)
        link.last_error = None
        return result
    except (GoogleCalendarError, httpx.HTTPError) as exc:
        logger.warning("Google Calendar sync failed for user_id=%s: %s", user.id_, exc)
        link.last_error = str(exc)[:512] or exc.__class__.__name__
        return None
    finally:
        await session.commit()
        if own_http:
            await http.aclose()


async def sync_user_in_background(user_id: int) -> None:
    """BackgroundTasks entry point — opens its own DB session."""
    from src.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user is not None:
            await sync_user(session, user)
