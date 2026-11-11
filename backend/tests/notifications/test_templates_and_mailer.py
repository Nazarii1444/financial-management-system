"""E-mail texts and the delivery backends (no network)."""
from datetime import date, datetime, timezone

import pytest

from src import config
from src.notifications import mailer, templates
from src.notifications.mailer import Email, brevo_payload, mime_message, send_email

URL = "https://app.example"


def test_reset_code_email_uk_and_en():
    uk = templates.password_reset_code(to="a@b.c", name="Оля", code="042917", ttl_minutes=15, lang="uk", frontend_url=URL)
    assert "042917" in uk.subject and "042917" in uk.text and "042917" in uk.html
    assert "15 хвилин" in uk.text
    assert "Керувати сповіщеннями" not in uk.text          # account e-mails have no opt-out link
    en = templates.password_reset_code(to="a@b.c", name="Ann", code="042917", ttl_minutes=15, lang="en", frontend_url=URL)
    assert en.subject == "Your password reset code: 042917"
    assert "15 minutes" in en.text


def test_unknown_language_falls_back_to_ukrainian():
    msg = templates.password_reset_code(to="a@b.c", name="X", code="000001", ttl_minutes=5, lang="de", frontend_url=URL)
    assert msg.subject.startswith("Код для відновлення")


def test_user_values_are_escaped_in_html():
    msg = templates.budget_alert(to="a@b.c", name="<b>x</b>", budget="<script>alert(1)</script>", percent=90,
                                 spent=900, limit=1000, currency="UAH", exceeded=False, lang="en", frontend_url=URL)
    assert "<script>" not in msg.html
    assert "&lt;script&gt;" in msg.html
    assert "<script>alert(1)</script>" in msg.text     # plain text keeps the original


def test_budget_alert_texts():
    near = templates.budget_alert(to="a@b.c", name="A", budget="Дім", percent=87.4, spent=8740, limit=10000,
                                  currency="UAH", exceeded=False, lang="uk", frontend_url=URL)
    assert near.subject == "Бюджет «Дім» використано на 87 %"
    assert "10 000 ₴" in near.text
    over = templates.budget_alert(to="a@b.c", name="A", budget="Home", percent=120, spent=1200, limit=1000,
                                  currency="USD", exceeded=True, lang="en", frontend_url=URL)
    assert over.subject == "Budget “Home” exceeded"
    assert "/settings?tab=notifications" in over.text      # notification e-mails can be turned off


def test_recurring_reminder_uses_calendar_formatting():
    msg = templates.recurring_reminder(to="a@b.c", name="A", payment="Оренда", amount=9000, currency="UAH",
                                       category="housing", due=date(2026, 11, 9), lang="uk", frontend_url=URL)
    assert msg.subject == "Завтра платіж: Оренда — 9 000 ₴"
    assert "09.11.2026" in msg.text and "Житло" in msg.text


def test_goal_milestone_and_completion():
    half = templates.goal_milestone(to="a@b.c", name="A", goal="Trip", milestone=50, saved=500, target=1000,
                                    currency="EUR", lang="en", frontend_url=URL)
    assert half.subject == "Goal “Trip”: 50% saved"
    done = templates.goal_milestone(to="a@b.c", name="A", goal="Trip", milestone=100, saved=1000, target=1000,
                                    currency="EUR", lang="en", frontend_url=URL)
    assert "reached" in done.subject


def test_monthly_summary():
    msg = templates.monthly_summary(to="a@b.c", name="A", year=2026, month=10, income=30000, expenses=21500.5,
                                    net=8499.5, currency="UAH", top_categories=[("food", 6000), ("housing", 9000)],
                                    lang="uk", frontend_url=URL)
    assert msg.subject == "Підсумок за жовтень 2026"
    assert "+8 499,50 ₴" in msg.text
    assert "Їжа та ресторани" in msg.text
    negative = templates.monthly_summary(to="a@b.c", name="A", year=2026, month=10, income=0, expenses=100, net=-100,
                                         currency="USD", top_categories=[], lang="en", frontend_url=URL)
    assert "−$100" in negative.text


def test_password_changed_mentions_time():
    msg = templates.password_changed(to="a@b.c", name="A", when=datetime(2026, 11, 8, 9, 30, tzinfo=timezone.utc),
                                     lang="en", frontend_url=URL)
    assert "2026-11-08 09:30 UTC" in msg.text


# ── Delivery ─────────────────────────────────────────────────────────────────

MSG = Email(to="user@example.com", to_name="User", subject="Hi", text="plain", html="<p>html</p>")


def test_brevo_payload():
    assert brevo_payload(MSG, "from@example.com", "FinanceHub") == {
        "sender": {"email": "from@example.com", "name": "FinanceHub"},
        "to": [{"email": "user@example.com", "name": "User"}],
        "subject": "Hi",
        "htmlContent": "<p>html</p>",
        "textContent": "plain",
    }


def test_mime_message_has_text_and_html():
    mime = mime_message(MSG, "from@example.com", "FinanceHub")
    assert mime["To"] == "User <user@example.com>"
    assert [part.get_content_type() for part in mime.iter_parts()] == ["text/plain", "text/html"]


@pytest.mark.anyio
async def test_console_backend_logs(monkeypatch):
    monkeypatch.setattr(config, "EMAIL_BACKEND", "console")
    assert await send_email(MSG) is True


@pytest.mark.anyio
async def test_failed_delivery_returns_false(monkeypatch):
    monkeypatch.setattr(config, "EMAIL_BACKEND", "brevo")
    monkeypatch.setattr(config, "BREVO_API_KEY", "")         # misconfigured → must not raise
    assert await send_email(MSG) is False


@pytest.mark.anyio
async def test_brevo_backend_posts_payload(monkeypatch):
    calls = []

    class _Resp:
        status_code = 201
        text = "{}"

    class _Client:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers, json):
            calls.append((url, headers, json))
            return _Resp()

    monkeypatch.setattr(config, "EMAIL_BACKEND", "brevo")
    monkeypatch.setattr(config, "BREVO_API_KEY", "key-123")
    monkeypatch.setattr(mailer.httpx, "AsyncClient", _Client)
    assert await send_email(MSG) is True
    url, headers, payload = calls[0]
    assert url == mailer.BREVO_URL
    assert headers["api-key"] == "key-123"
    assert payload["to"] == [{"email": "user@example.com", "name": "User"}]
