"""
Google Calendar sync against a fake Google API (httpx.MockTransport).

Covers event mapping, upsert (PUT → insert fallback), stale-event cleanup,
token refresh, calendar recreation and token encryption.
"""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from src.calendar_export import google_calendar as gcal
from src.models import GoogleCalendarLink, RecurringFrequency, TransactionKind

UTC = timezone.utc


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setattr(gcal, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(gcal, "GOOGLE_CLIENT_SECRET", "client-secret")


def _rule(id_=7, **overrides):
    values = dict(
        id_=id_, user_id=3, name="Netflix", amount=Decimal("299"), kind=TransactionKind.EXPENSE,
        category_name="entertainment", currency="UAH", tags=[], note=None,
        frequency=RecurringFrequency.MONTHLY, next_run=datetime(2026, 11, 12, 9, tzinfo=UTC),
        created_at=datetime(2026, 10, 1, tzinfo=UTC), is_active=True,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _user():
    return SimpleNamespace(id_=3, default_currency="UAH", timezone="Europe/Kyiv")


def _link(**overrides):
    values = dict(
        user_id=3, refresh_token=gcal.encrypt("refresh-1"), access_token=gcal.encrypt("access-1"),
        token_expires_at=datetime.now(UTC) + timedelta(hours=1), calendar_id="cal-1", lang="uk",
    )
    values.update(overrides)
    return GoogleCalendarLink(**values)


class FakeGoogle:
    """In-memory Calendar API: calendars → {event_id: body}."""

    def __init__(self, calendars=None):
        self.calendars = calendars if calendars is not None else {"cal-1": {}}
        self.calls = []
        self.refreshes = 0
        self.created = len(self.calendars)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        if request.url.host == "oauth2.googleapis.com":
            form = parse_qs(request.content.decode())
            if form["grant_type"] == ["refresh_token"]:
                self.refreshes += 1
                if form["refresh_token"] != ["refresh-1"]:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return httpx.Response(200, json={"access_token": "access-2", "expires_in": 3600})
            return httpx.Response(200, json={"access_token": "access-1", "refresh_token": "refresh-1", "expires_in": 3600})

        parts = request.url.path.split("/")  # /calendar/v3/calendars/{cid}/events/{eid}
        if request.method == "POST" and request.url.path.endswith("/calendars"):
            self.created += 1
            cid = f"cal-{self.created}"
            self.calendars[cid] = {}
            return httpx.Response(200, json={"id": cid})
        cid = parts[4]
        if cid not in self.calendars:
            return httpx.Response(404, json={"error": "notFound"})
        events = self.calendars[cid]
        if len(parts) == 6:  # collection
            if request.method == "GET":
                return httpx.Response(200, json={"items": [{"id": eid} for eid in events]})
            body = json.loads(request.content)
            events[body["id"]] = body
            return httpx.Response(200, json=body)
        eid = parts[6]
        if request.method == "PUT":
            if eid not in events:
                return httpx.Response(404, json={"error": "notFound"})
            events[eid] = json.loads(request.content)
            return httpx.Response(200, json=events[eid])
        if request.method == "DELETE":
            events.pop(eid, None)
            return httpx.Response(204)
        return httpx.Response(405)

    def client(self):
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


# ── Mapping ───────────────────────────────────────────────────────────────────

def test_event_id_uses_base32hex_alphabet():
    eid = gcal.event_id(_rule(id_=42))
    assert eid == "fms3r42"
    assert set(eid) <= set("abcdefghijklmnopqrstuv0123456789")


def test_build_event():
    body = gcal.build_event(_rule(), "UAH", "Europe/Kyiv", "uk")

    assert body["id"] == "fms3r7"
    assert body["summary"] == "🎬 Netflix — 299 ₴"
    assert body["start"] == {"date": "2026-10-12"}
    assert body["end"] == {"date": "2026-10-13"}
    assert body["recurrence"] == ["RRULE:FREQ=MONTHLY"]
    assert body["colorId"] == gcal.EXPENSE_COLOR
    assert body["reminders"]["overrides"] == [{"method": "popup", "minutes": 900}]
    assert body["extendedProperties"]["private"] == {"fms": "1", "rule_id": "7"}


def test_income_event_is_green_without_reminder():
    body = gcal.build_event(_rule(kind=TransactionKind.INCOME, category_name="salary"), "UAH", None, "en")
    assert body["colorId"] == gcal.INCOME_COLOR
    assert body["reminders"]["overrides"] == []


def test_authorization_url_requests_offline_access_with_narrow_scope():
    url = gcal.authorization_url("http://api/cb", "state-1")
    q = parse_qs(urlparse(url).query)
    assert q["scope"] == [gcal.SCOPE]
    assert q["access_type"] == ["offline"]
    assert q["redirect_uri"] == ["http://api/cb"]
    assert q["state"] == ["state-1"]


def test_tokens_are_encrypted_at_rest():
    stored = gcal.encrypt("secret-token")
    assert "secret-token" not in stored
    assert gcal.decrypt(stored) == "secret-token"
    assert gcal.decrypt("garbage") is None


# ── Sync ──────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_sync_inserts_updates_and_removes_stale_events():
    google = FakeGoogle({"cal-1": {"fms3r99": {"id": "fms3r99"}}})   # rule 99 was deleted in the app
    link = _link()
    async with google.client() as http:
        client = gcal.GoogleCalendarClient(link, http)

        result = await gcal.sync_rules(client, _user(), [_rule(7), _rule(8, name="Spotify", is_active=False)])
        assert result == {"synced": 1, "deleted": 1}
        assert set(google.calendars["cal-1"]) == {"fms3r7"}

        # Price change → same event updated in place
        result = await gcal.sync_rules(client, _user(), [_rule(7, amount=Decimal("349"))])
        assert result == {"synced": 1, "deleted": 0}
        assert google.calendars["cal-1"]["fms3r7"]["summary"] == "🎬 Netflix — 349 ₴"
        assert ("PUT", "/calendar/v3/calendars/cal-1/events/fms3r7") in google.calls


@pytest.mark.anyio
async def test_sync_creates_calendar_on_first_run_and_recreates_if_deleted():
    google = FakeGoogle({})
    link = _link(calendar_id=None)
    async with google.client() as http:
        client = gcal.GoogleCalendarClient(link, http)
        await gcal.sync_rules(client, _user(), [_rule()])
        assert link.calendar_id == "cal-1"

        del google.calendars["cal-1"]          # user removed the calendar in Google
        await gcal.sync_rules(client, _user(), [_rule()])
        assert link.calendar_id == "cal-2"
        assert set(google.calendars["cal-2"]) == {"fms3r7"}


@pytest.mark.anyio
async def test_expired_access_token_is_refreshed():
    google = FakeGoogle()
    link = _link(token_expires_at=datetime.now(UTC) - timedelta(minutes=1))
    async with google.client() as http:
        await gcal.sync_rules(gcal.GoogleCalendarClient(link, http), _user(), [_rule()])
    assert google.refreshes == 1
    assert gcal.decrypt(link.access_token) == "access-2"
    assert link.token_expires_at > datetime.now(UTC)


@pytest.mark.anyio
async def test_revoked_refresh_token_raises_reconnect_error():
    google = FakeGoogle()
    link = _link(token_expires_at=None, refresh_token=gcal.encrypt("revoked"))
    async with google.client() as http:
        with pytest.raises(gcal.GoogleCalendarError, match="reconnect"):
            await gcal.sync_rules(gcal.GoogleCalendarClient(link, http), _user(), [_rule()])


@pytest.mark.anyio
async def test_exchange_code_and_store_tokens():
    google = FakeGoogle()
    link = _link(refresh_token="", access_token=None)
    async with google.client() as http:
        tokens = await gcal.GoogleCalendarClient.exchange_code(http, "code-1", "http://api/cb")
        gcal.GoogleCalendarClient(link, http).store_tokens(tokens)
    assert gcal.decrypt(link.refresh_token) == "refresh-1"
    assert gcal.decrypt(link.access_token) == "access-1"
