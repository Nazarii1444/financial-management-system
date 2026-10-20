"""
Recurring rules → iCalendar (RFC 5545).

Each active RecurringTransaction becomes one all-day VEVENT with an RRULE, so
any calendar (Google, Apple, Outlook) expands it into future occurrences.

Series anchor
-------------
The cron advances `next_run` after every fire. Using `next_run` as DTSTART
would make past payments disappear from the calendar, so the series starts at
the earliest occurrence on or after the rule's `created_at`, found by
stepping back from `next_run` one frequency step at a time. That anchor stays
the same while the cron advances the rule, so event UIDs/dates are stable.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, List, Optional

from dateutil.relativedelta import relativedelta

from src.models import RecurringFrequency, TransactionKind
from src.calendar_export.formatting import TEXT, event_description, event_title, normalize_lang

_MAX_STEPS_BACK = 1000
PRODID = "-//FinanceHub//Recurring payments//EN"


# ── Dates & recurrence ────────────────────────────────────────────────────────

def _tz(tzname: Optional[str]):
    """User's timezone; pytz fallback for hosts without tzdata (e.g. Windows)."""
    if tzname:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(tzname)
        except Exception:
            try:
                import pytz
                return pytz.timezone(tzname)
            except Exception:
                pass
    return timezone.utc


def local_date(value: datetime, tzname: Optional[str]) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_tz(tzname)).date()


def _step(d, frequency: RecurringFrequency, n: int):
    if frequency == RecurringFrequency.DAILY:
        return d + timedelta(days=n)
    if frequency == RecurringFrequency.WEEKLY:
        return d + timedelta(weeks=n)
    if frequency == RecurringFrequency.BIWEEKLY:
        return d + timedelta(weeks=2 * n)
    if frequency == RecurringFrequency.MONTHLY:
        return d + relativedelta(months=n)
    if frequency == RecurringFrequency.YEARLY:
        return d + relativedelta(years=n)
    return d


def series_start(rule, tzname: Optional[str] = None) -> date:
    """
    Earliest occurrence that actually fired, i.e. stepping back from next_run
    while the instant is not before `created_at` (see module doc). Compared as
    datetimes: a rule created today with its first run next month must not get
    a phantom occurrence today.
    """
    next_run = rule.next_run if rule.next_run.tzinfo else rule.next_run.replace(tzinfo=timezone.utc)
    created = getattr(rule, "created_at", None)
    if created is None:
        return local_date(next_run, tzname)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    # Step back from the original next_run (not the previous step) so monthly
    # rules on the 31st don't drift to the 28th after February.
    first = next_run
    for n in range(1, _MAX_STEPS_BACK):
        prev = _step(next_run, rule.frequency, -n)
        if prev < created or prev == next_run:
            break
        first = prev
    return local_date(first, tzname)


def rrule(frequency: RecurringFrequency, start: date, month_day: Optional[int] = None) -> str:
    """RRULE value; *month_day* is the rule's real day of month (start may be clamped)."""
    if frequency == RecurringFrequency.DAILY:
        return "FREQ=DAILY"
    if frequency == RecurringFrequency.WEEKLY:
        return "FREQ=WEEKLY"
    if frequency == RecurringFrequency.BIWEEKLY:
        return "FREQ=WEEKLY;INTERVAL=2"
    if frequency == RecurringFrequency.MONTHLY:
        day = month_day or start.day
        if day > 28:
            # RFC 5545 skips months without that day; the app clamps to the
            # month's last day instead → pick the first of {day, last day}.
            return f"FREQ=MONTHLY;BYMONTHDAY={day},-1;BYSETPOS=1"
        return "FREQ=MONTHLY"
    if frequency == RecurringFrequency.YEARLY:
        return "FREQ=YEARLY"
    raise ValueError(f"Unsupported frequency: {frequency}")


def event_uid(rule) -> str:
    return f"recurring-{rule.id_}-user-{rule.user_id}@financehub"


# ── Text encoding ─────────────────────────────────────────────────────────────

def escape_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold(line: str) -> str:
    """Fold a content line at 75 octets without splitting UTF-8 characters."""
    out, current, size = [], "", 0
    for ch in line:
        width = len(ch.encode("utf-8"))
        limit = 75 if not out else 74  # continuation lines start with a space
        if size + width > limit:
            out.append(current)
            current, size = "", 0
        current += ch
        size += width
    out.append(current)
    return "\r\n ".join(out)


def _fmt_date(d: date) -> str:
    return d.strftime("%Y%m%d")


def _fmt_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ── Calendar ──────────────────────────────────────────────────────────────────

def build_event_lines(rule, currency: str, tzname: Optional[str], lang: str, stamp: datetime) -> List[str]:
    start = series_start(rule, tzname)
    month_day = local_date(rule.next_run, tzname).day
    lines = [
        "BEGIN:VEVENT",
        f"UID:{event_uid(rule)}",
        f"DTSTAMP:{_fmt_utc(stamp)}",
        f"DTSTART;VALUE=DATE:{_fmt_date(start)}",
        f"DTEND;VALUE=DATE:{_fmt_date(start + timedelta(days=1))}",
        f"RRULE:{rrule(rule.frequency, start, month_day)}",
        f"SUMMARY:{escape_text(event_title(rule, currency, lang))}",
        f"DESCRIPTION:{escape_text(event_description(rule, lang))}",
        f"CATEGORIES:{escape_text(rule.category_name or '')}",
        "TRANSP:TRANSPARENT",
    ]
    if rule.kind == TransactionKind.EXPENSE:
        # All-day event starts at 00:00 → remind at 09:00 the day before
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{escape_text(TEXT[lang]['reminder'])}",
            "TRIGGER:-PT15H",
            "END:VALARM",
        ]
    lines.append("END:VEVENT")
    return lines


def build_calendar(
        rules: Iterable,
        default_currency: str,
        tzname: Optional[str] = None,
        lang: Optional[str] = None,
        now: Optional[datetime] = None,
) -> str:
    """Render active rules as a complete VCALENDAR document (CRLF line endings)."""
    lang = normalize_lang(lang)
    stamp = now or datetime.now(timezone.utc)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_text(TEXT[lang]['calendar_name'])}",
        f"X-WR-CALDESC:{escape_text(TEXT[lang]['calendar_description'])}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]
    if tzname:
        lines.append(f"X-WR-TIMEZONE:{tzname}")
    for rule in rules:
        if not getattr(rule, "is_active", True):
            continue
        currency = (rule.currency or default_currency or "").upper()
        lines += build_event_lines(rule, currency, tzname, lang, stamp)
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"
