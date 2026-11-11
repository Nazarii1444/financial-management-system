"""Security history helpers: user-agent description and client IP."""
from types import SimpleNamespace

import pytest

from src.security import events

CHROME_WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
EDGE_WIN = CHROME_WIN + " Edg/141.0.0.0"
SAFARI_IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
                 "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1")
FIREFOX_ANDROID = "Mozilla/5.0 (Android 15; Mobile; rv:131.0) Gecko/131.0 Firefox/131.0"
CHROME_MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"


@pytest.mark.parametrize("ua, label, device", [
    (CHROME_WIN, "Chrome · Windows", "desktop"),
    (EDGE_WIN, "Edge · Windows", "desktop"),
    (SAFARI_IPHONE, "Safari · iOS", "mobile"),
    (FIREFOX_ANDROID, "Firefox · Android", "mobile"),
    (CHROME_MAC, "Chrome · macOS", "desktop"),
    ("python-httpx/0.28.1", "API client", None),
    (None, None, None),
])
def test_describe_user_agent(ua, label, device):
    described = events.describe_user_agent(ua)
    assert described["label"] == label and described["device"] == device


def _request(host="10.0.0.5", forwarded=None):
    headers = {"x-forwarded-for": forwarded} if forwarded else {}
    return SimpleNamespace(client=SimpleNamespace(host=host), headers=headers)


def test_client_ip_ignores_forwarded_header_by_default(monkeypatch):
    monkeypatch.setattr(events, "TRUST_PROXY_HEADERS", False)
    assert events.client_ip(_request(forwarded="1.2.3.4")) == "10.0.0.5"   # spoofable header ignored


def test_client_ip_behind_trusted_proxy(monkeypatch):
    monkeypatch.setattr(events, "TRUST_PROXY_HEADERS", True)
    assert events.client_ip(_request(forwarded="203.0.113.9, 10.0.0.2")) == "203.0.113.9"
    assert events.client_ip(_request()) == "10.0.0.5"


class _Session:
    def __init__(self, fail=False):
        self.added, self.fail, self.rolled_back = [], fail, False

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        if self.fail:
            raise RuntimeError("db down")

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.anyio
async def test_record_event_stores_request_details():
    db = _Session()
    req = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={"user-agent": CHROME_WIN})
    await events.record_event(db, 3, events.EventType.LOGIN, req, success=False, method="password", details={"reason": "x"})
    event = db.added[0]
    assert (event.user_id, event.event_type, event.success, event.method, event.ip) == (3, "login", False, "password", "127.0.0.1")
    assert event.user_agent == CHROME_WIN


@pytest.mark.anyio
async def test_record_event_never_breaks_the_caller():
    db = _Session(fail=True)
    await events.record_event(db, 3, events.EventType.LOGIN)
    assert db.rolled_back
