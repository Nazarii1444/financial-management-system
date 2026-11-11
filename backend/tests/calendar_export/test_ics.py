"""Pure unit tests for the iCalendar export (titles, recurrence, encoding)."""

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from dateutil.rrule import rrulestr

from src.calendar_export import ics
from src.calendar_export.formatting import event_title, format_amount
from src.models import RecurringFrequency, TransactionKind

UTC = timezone.utc
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
NBSP = " "


def _rule(**overrides):
    values = dict(
        id_=7, user_id=3, name="Оренда", amount=Decimal("9000"), kind=TransactionKind.EXPENSE,
        category_name="housing", currency="UAH", tags=[], note=None,
        frequency=RecurringFrequency.MONTHLY, next_run=datetime(2026, 11, 1, 9, 0, tzinfo=UTC),
        created_at=datetime(2026, 9, 20, tzinfo=UTC), is_active=True,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _unfold(text: str) -> str:
    return text.replace("\r\n ", "")


# ── Formatting ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "amount, currency, lang, expected",
    [
        (9000, "UAH", "uk", f"9{NBSP}000 ₴"),
        (Decimal("2100.5"), "UAH", "uk", f"2{NBSP}100,50 ₴"),
        (49, "UAH", "uk", "49 ₴"),
        (Decimal("2100.5"), "USD", "en", "$2,100.50"),
        (300, "PLN", "en", "300 zł"),
        (10, "SEK", "uk", "10 SEK"),
    ],
)
def test_format_amount(amount, currency, lang, expected):
    assert format_amount(amount, currency, lang) == expected


def test_titles_like_the_calendar_screenshot():
    assert event_title(_rule(), "UAH") == f"🏠 Оренда — 9{NBSP}000 ₴"
    salary = _rule(name="Зарплата", amount=25000, kind=TransactionKind.INCOME, category_name="salary")
    assert event_title(salary, "UAH") == f"💰 Зарплата — +25{NBSP}000 ₴"
    assert event_title(_rule(category_name="mystery"), "UAH").startswith("💳 ")


# ── Recurrence ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "frequency, expected",
    [
        (RecurringFrequency.DAILY, "FREQ=DAILY"),
        (RecurringFrequency.WEEKLY, "FREQ=WEEKLY"),
        (RecurringFrequency.BIWEEKLY, "FREQ=WEEKLY;INTERVAL=2"),
        (RecurringFrequency.MONTHLY, "FREQ=MONTHLY"),
        (RecurringFrequency.YEARLY, "FREQ=YEARLY"),
    ],
)
def test_rrule_per_frequency(frequency, expected):
    assert ics.rrule(frequency, date(2026, 10, 5)) == expected


def test_monthly_on_31st_falls_back_to_last_day_like_the_app():
    rule = ics.rrule(RecurringFrequency.MONTHLY, date(2027, 1, 31))
    dates = list(rrulestr(f"RRULE:{rule}", dtstart=datetime(2027, 1, 31)))[:4]
    assert [d.date() for d in dates] == [date(2027, 1, 31), date(2027, 2, 28), date(2027, 3, 31), date(2027, 4, 30)]


def test_series_starts_at_first_occurrence_after_creation():
    # Created Sep 20, next run Nov 1 → Oct 1 already fired (Sep 1 is before creation)
    assert ics.series_start(_rule()) == date(2026, 10, 1)


def test_series_start_is_stable_when_cron_advances():
    before = ics.series_start(_rule(next_run=datetime(2026, 11, 1, 9, tzinfo=UTC)))
    after = ics.series_start(_rule(next_run=datetime(2026, 12, 1, 9, tzinfo=UTC)))
    assert before == after == date(2026, 10, 1)


def test_no_phantom_occurrence_before_the_first_run():
    # Created today at 12:27 with the first charge next month → nothing today
    rule = _rule(next_run=datetime(2026, 11, 18, 9, tzinfo=UTC), created_at=datetime(2026, 10, 18, 12, 27, tzinfo=UTC))
    assert ics.series_start(rule) == date(2026, 11, 18)


def test_occurrence_fired_by_cron_right_after_creation_is_kept():
    # first_run was in the past → cron fired at 12:00:30, next_run = that instant + 1 month
    rule = _rule(next_run=datetime(2026, 11, 18, 12, 0, 30, tzinfo=UTC), created_at=datetime(2026, 10, 18, 12, 0, tzinfo=UTC))
    assert ics.series_start(rule) == date(2026, 10, 18)


def test_series_start_does_not_drift_after_short_month():
    rule = _rule(next_run=datetime(2027, 3, 31, tzinfo=UTC), created_at=datetime(2027, 1, 15, tzinfo=UTC))
    assert ics.series_start(rule) == date(2027, 1, 31)


def test_series_start_uses_user_timezone():
    # 23:30 UTC on Oct 31 is already Nov 1 in Kyiv
    rule = _rule(next_run=datetime(2026, 10, 31, 23, 30, tzinfo=UTC), created_at=datetime(2026, 10, 20, tzinfo=UTC))
    assert ics.series_start(rule, "Europe/Kyiv") == date(2026, 11, 1)
    assert ics.series_start(rule, None) == date(2026, 10, 31)


# ── Encoding ──────────────────────────────────────────────────────────────────

def test_escape_text():
    assert ics.escape_text("a;b,c\\d\ne") == "a\\;b\\,c\\\\d\\ne"


def test_fold_respects_75_octets_and_utf8():
    line = "SUMMARY:" + "Ї" * 100
    folded = ics.fold(line)
    parts = folded.split("\r\n")
    assert all(len(p.encode("utf-8")) <= 75 for p in parts)
    assert all(p.startswith(" ") for p in parts[1:])
    assert _unfold(folded) == line


# ── Calendar ──────────────────────────────────────────────────────────────────

def test_build_calendar_document():
    rules = [
        _rule(),
        _rule(id_=8, name="Зарплата", amount=25000, kind=TransactionKind.INCOME, category_name="salary",
              next_run=datetime(2026, 10, 28, 9, tzinfo=UTC), note="Аванс; премія"),
        _rule(id_=9, name="Paused", is_active=False),
    ]
    text = ics.build_calendar(rules, "UAH", "Europe/Kyiv", "uk", now=NOW)
    body = _unfold(text)

    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert "\n" not in text.replace("\r\n", "")
    assert body.count("BEGIN:VEVENT") == 2                    # paused rule skipped
    assert "X-WR-CALNAME:FinanceHub — платежі" in body
    assert "UID:recurring-7-user-3@financehub" in body
    assert "DTSTART;VALUE=DATE:20261001" in body
    assert "DTEND;VALUE=DATE:20261002" in body
    assert "RRULE:FREQ=MONTHLY" in body
    assert f"SUMMARY:🏠 Оренда — 9{NBSP}000 ₴" in body
    assert f"SUMMARY:💰 Зарплата — +25{NBSP}000 ₴" in body
    assert "Нотатка: Аванс\\; премія" in body
    assert "DTSTAMP:20261018T120000Z" in body
    assert body.count("BEGIN:VALARM") == 1                    # reminders for expenses only


def test_build_calendar_english_and_unknown_lang():
    assert "X-WR-CALNAME:FinanceHub — payments" in ics.build_calendar([], "USD", lang="en", now=NOW)
    assert "платежі" in ics.build_calendar([], "USD", lang="de", now=NOW)
