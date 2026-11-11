"""Pure decision rules of the notification scheduler (src/notifications/service.py)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.notifications.service import (
    Kind,
    Prefs,
    budget_threshold,
    crossed_milestones,
    is_due_for_reminder,
    month_bounds,
    progress_percent,
    summary_month,
)

UTC = timezone.utc
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("before, after, expected", [
    (0, 10, []),
    (20, 30, [25]),
    (20, 60, [25, 50]),
    (0, 100, [25, 50, 75, 100]),
    (25, 49.9, []),          # 25 was already passed before
    (74.99, 75, [75]),       # reaching the milestone exactly counts
    (80, 50, []),            # a withdrawal never announces anything
])
def test_crossed_milestones(before, after, expected):
    assert crossed_milestones(before, after) == expected


def test_progress_percent():
    assert progress_percent(Decimal("250"), Decimal("1000")) == 25.0
    assert progress_percent(0, 0) == 100.0          # a zero target is trivially reached


@pytest.mark.parametrize("utilization, expected", [
    (None, None),            # budget without a limit
    (0, None),
    (84.9, None),
    (85, 85),
    (99.9, 85),
    (100, 100),
    (180, 100),
])
def test_budget_threshold(utilization, expected):
    assert budget_threshold(utilization) == expected


@pytest.mark.parametrize("delta, expected", [
    (timedelta(minutes=-1), False),      # already due — the cron fires it, no reminder any more
    (timedelta(0), False),
    (timedelta(hours=1), True),
    (timedelta(hours=24), True),
    (timedelta(hours=24, seconds=1), False),
    (timedelta(days=3), False),
])
def test_is_due_for_reminder(delta, expected):
    assert is_due_for_reminder(NOW + delta, NOW) is expected


def test_is_due_for_reminder_treats_naive_datetime_as_utc():
    assert is_due_for_reminder((NOW + timedelta(hours=2)).replace(tzinfo=None), NOW)


@pytest.mark.parametrize("now, expected", [
    (datetime(2026, 11, 1, 0, 5, tzinfo=UTC), (2026, 10)),
    (datetime(2026, 11, 7, 23, 0, tzinfo=UTC), (2026, 10)),   # still inside the grace week
    (datetime(2026, 11, 8, 0, 0, tzinfo=UTC), None),
    (datetime(2027, 1, 3, tzinfo=UTC), (2026, 12)),          # across the year boundary
])
def test_summary_month(now, expected):
    assert summary_month(now) == expected


def test_month_bounds():
    start, end = month_bounds(2026, 12)
    assert start == datetime(2026, 12, 1, tzinfo=UTC)
    assert end == datetime(2027, 1, 1, tzinfo=UTC)


def test_prefs_need_both_channel_and_event():
    assert Prefs().wants(Kind.BUDGET_ALERT)                       # defaults: everything on
    assert not Prefs(email_enabled=False).wants(Kind.BUDGET_ALERT)
    assert not Prefs(budget_limit_alerts=False).wants(Kind.BUDGET_ALERT)
    assert Prefs(budget_limit_alerts=False).wants(Kind.MONTHLY_SUMMARY)
    assert not Prefs(recurring_reminders=False).wants(Kind.RECURRING_REMINDER)
    assert not Prefs(goal_milestone_alerts=False).wants(Kind.GOAL_MILESTONE)
    assert not Prefs(monthly_summary=False).wants(Kind.MONTHLY_SUMMARY)
