"""Password policy (length, zxcvbn score, personal info, blocklists, HIBP) and password health."""
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.auth import auth_services
from src.security import password_policy
from src.security.security_router import password_health

NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize("password, code", [
    ("Short1!x", "too_short"),
    ("Password1!", "weak"),           # passes the old composition rules, guessed in seconds
    ("qwertyuiop12", "weak"),         # keyboard walk
    ("1234567890", "common"),
    ("olena-loves-rain-2026", "personal"),
    ("ї" * 40, "too_long"),            # 80 bytes > bcrypt's 72
])
def test_rejected(password, code):
    report = password_policy.evaluate(password, "olena", "olena.k@example.com")
    assert code in report.codes and not report.acceptable


@pytest.mark.parametrize("password", [
    "correct horse battery staple",
    "сонячний кіт спить на даху",     # Cyrillic passphrases count too
    "Bench#Load2026!x7Q",
    "violet-tractor-umbrella-41",
])
def test_accepted(password):
    report = password_policy.evaluate(password, "olena", "olena.k@example.com")
    assert report.acceptable, report.errors
    assert report.score >= password_policy.MIN_SCORE


def test_email_parts_count_as_personal():
    assert "personal" in password_policy.evaluate("kovalenko-sunny-river", "olena", "o.kovalenko@example.com").codes


def test_report_explains_weak_passwords():
    report = password_policy.evaluate("Password1!")
    assert report.score <= 1 and report.crack_time
    assert report.warning or report.suggestions


class _FakeClient:
    def __init__(self, body=None, error=None):
        self.body, self.error, self.calls = body, error, []

    def __call__(self, *a, **kw):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        self.calls.append((url, headers))
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.body, raise_for_status=lambda: None)


def _hibp_body(password, count):
    suffix = hashlib.sha1(password.encode()).hexdigest().upper()[5:]
    return f"0018A45C4D1DEF81644B54AB7F969B88D65:1\r\n{suffix}:{count}\r\nFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF:0"


@pytest.mark.anyio
async def test_hibp_sends_only_the_prefix_and_reads_counts(monkeypatch):
    client = _FakeClient(_hibp_body("hunter2hunter2", 1234))
    monkeypatch.setattr(password_policy.httpx, "AsyncClient", client)
    assert await password_policy.is_breached("hunter2hunter2") is True
    url, headers = client.calls[0]
    prefix = hashlib.sha1(b"hunter2hunter2").hexdigest().upper()[:5]
    assert url.endswith("/range/" + prefix) and headers == {"Add-Padding": "true"}


@pytest.mark.anyio
async def test_hibp_padding_rows_are_not_matches(monkeypatch):
    monkeypatch.setattr(password_policy.httpx, "AsyncClient", _FakeClient(_hibp_body("violet-tractor", 0)))
    assert await password_policy.is_breached("violet-tractor") is False


@pytest.mark.anyio
async def test_hibp_unreachable_is_unknown(monkeypatch):
    monkeypatch.setattr(password_policy.httpx, "AsyncClient", _FakeClient(error=OSError("offline")))
    assert await password_policy.is_breached("anything") is None


@pytest.mark.anyio
async def test_check_password_adds_leak_error(monkeypatch):
    monkeypatch.setattr(password_policy.httpx, "AsyncClient", _FakeClient(_hibp_body("correct horse battery staple", 99)))
    report = await password_policy.check_password("correct horse battery staple")
    assert report.codes == ["leaked"] and report.errors == [password_policy.MSG_LEAKED]


def test_legacy_oauth_placeholders_never_authenticate():
    assert "__google_oauth__" in auth_services._LEGACY_OAUTH_PASSWORDS
    assert len(auth_services.oauth_placeholder_password()) >= 40
    assert auth_services.oauth_placeholder_password() != auth_services.oauth_placeholder_password()


def test_breach_recheck_interval():
    user = SimpleNamespace(password_checked_at=None)
    assert auth_services.needs_breach_recheck(user, NOW)
    user.password_checked_at = NOW - timedelta(days=2)
    assert not auth_services.needs_breach_recheck(user, NOW)
    user.password_checked_at = NOW - timedelta(days=8)
    assert auth_services.needs_breach_recheck(user, NOW)


def _user(**kw):
    base = dict(password_changed_at=NOW - timedelta(days=30), password_score=4, password_breached=False,
                password_checked_at=NOW - timedelta(days=1), twofa_enabled=True)
    return SimpleNamespace(**{**base, **kw})


def test_health_good_with_passkey():
    health = password_health(_user(), passkeys=1, now=NOW)
    assert health.level == "good" and health.recommendations == [] and health.age_days == 30


def test_health_breached_is_weak_and_first():
    health = password_health(_user(password_breached=True), passkeys=1, now=NOW)
    assert health.level == "weak" and health.recommendations[0] == "change_breached"


def test_health_old_password_without_second_factor():
    health = password_health(_user(password_changed_at=NOW - timedelta(days=400), twofa_enabled=False), passkeys=0, now=NOW)
    assert health.level == "fair"
    assert {"password_old", "enable_2fa_or_passkey"} <= set(health.recommendations)


def test_health_unknown_history_asks_for_a_check():
    health = password_health(_user(password_changed_at=None, password_score=None, password_checked_at=None), passkeys=0, now=NOW)
    assert health.age_days is None and "run_check" in health.recommendations


@pytest.mark.anyio
async def test_old_oauth_account_cannot_be_opened_with_the_placeholder(monkeypatch):
    from src.utils.auth_services import hash_password
    victim = SimpleNamespace(hashed_password=hash_password("__google_oauth__"))

    async def fake_lookup(db, email):
        return victim
    monkeypatch.setattr(auth_services, "get_user_by_email", fake_lookup)
    assert await auth_services.authenticate_user(None, "victim@gmail.com", "__google_oauth__") is None
    assert await auth_services.authenticate_user(None, "victim@gmail.com", "x" * 73) is None   # > 72 bytes: no bcrypt error
