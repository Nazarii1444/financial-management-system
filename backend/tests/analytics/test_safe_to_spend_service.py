"""
Unit tests for SafeToSpendService.

The DB session is replaced by an in-memory fake, and the module's `datetime`
is frozen so month boundaries and `days_remaining` are deterministic.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.analytics.services import safe_to_spend_service as sts
from src.analytics.services.safe_to_spend_service import SafeToSpendService
from src.models import (
    Goal,
    RecurringFrequency,
    RecurringTransaction,
    Transaction,
    TransactionKind,
)

UTC = timezone.utc
NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)          # 17 days left in Sept, incl. today
MONTH_END = datetime(2026, 10, 1, tzinfo=UTC)           # exclusive upper bound


# ── Fakes & helpers ───────────────────────────────────────────────────────────

class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class FakeSession:
    """Returns canned rows per selected entity and records executed statements."""

    def __init__(self, recurring=(), transactions=(), goals=()):
        self._rows = {RecurringTransaction: recurring, Transaction: transactions, Goal: goals}
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        entity = stmt.column_descriptions[0]["entity"]
        return _Result(self._rows[entity])


def make_service(
    *,
    capital=3000.0,
    currency="UAH",
    tz=None,
    user_id=1,
    recurring=(),
    transactions=(),
    goals=(),
    rates=None,
    target=None,
):
    user = SimpleNamespace(
        id_=user_id, capital=capital, default_currency=currency, timezone=tz
    )
    session = FakeSession(recurring, transactions, goals)
    return SafeToSpendService(session, user, rates or {}, target), session


def rule(amount, kind, frequency, next_run, currency=None):
    return SimpleNamespace(
        amount=amount, kind=kind, frequency=frequency,
        next_run=next_run, currency=currency,
    )


def expense_tx(amount, currency=None, date=NOW - timedelta(days=2)):
    return SimpleNamespace(amount=amount, currency=currency, date=date)


def goal(target, saved, deadline=None, currency="UAH", goal_id=1, name="Jar"):
    return SimpleNamespace(
        id_=goal_id, name=name, target_amount=target, saved_amount=saved,
        currency=currency, deadline=deadline,
    )


@pytest.fixture
def freeze_now(monkeypatch):
    """Freeze `datetime.now()` inside the service module at a given UTC instant."""

    def _freeze(instant: datetime):
        class _Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

        monkeypatch.setattr(sts, "datetime", _Frozen)

    return _freeze


# ── _advance ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "frequency, expected",
    [
        (RecurringFrequency.DAILY, datetime(2026, 2, 1, tzinfo=UTC)),
        (RecurringFrequency.WEEKLY, datetime(2026, 2, 7, tzinfo=UTC)),
        (RecurringFrequency.BIWEEKLY, datetime(2026, 2, 14, tzinfo=UTC)),
        (RecurringFrequency.MONTHLY, datetime(2026, 2, 28, tzinfo=UTC)),  # clamped
        (RecurringFrequency.YEARLY, datetime(2027, 1, 31, tzinfo=UTC)),
    ],
)
def test_advance_steps_one_frequency(frequency, expected):
    start = datetime(2026, 1, 31, tzinfo=UTC)
    assert SafeToSpendService._advance(start, frequency) == expected


def test_advance_unknown_frequency_returns_same_instant():
    start = datetime(2026, 1, 31, tzinfo=UTC)
    assert SafeToSpendService._advance(start, None) == start


# ── _count_occurrences ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "frequency, next_run, expected",
    [
        (RecurringFrequency.DAILY, datetime(2026, 9, 15, tzinfo=UTC), 16),     # 15..30
        (RecurringFrequency.WEEKLY, datetime(2026, 9, 16, tzinfo=UTC), 3),     # 16, 23, 30
        (RecurringFrequency.BIWEEKLY, datetime(2026, 9, 16, tzinfo=UTC), 2),   # 16, 30
        (RecurringFrequency.MONTHLY, datetime(2026, 9, 20, tzinfo=UTC), 1),
        (RecurringFrequency.YEARLY, datetime(2026, 9, 20, tzinfo=UTC), 1),
    ],
)
def test_count_occurrences_per_frequency(frequency, next_run, expected):
    assert SafeToSpendService._count_occurrences(next_run, NOW, MONTH_END, frequency) == expected


def test_count_occurrences_skips_past_runs_and_includes_now():
    # Fires on 10..13 are before `now` and skipped; 14th 12:00 == now is counted.
    next_run = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    count = SafeToSpendService._count_occurrences(
        next_run, NOW, MONTH_END, RecurringFrequency.DAILY
    )
    assert count == 17  # 14..30


def test_count_occurrences_until_is_exclusive():
    count = SafeToSpendService._count_occurrences(
        MONTH_END, NOW, MONTH_END, RecurringFrequency.DAILY
    )
    assert count == 0


def test_count_occurrences_zero_when_first_run_after_window():
    # A yearly rule that last fired before now next fires after month end.
    next_run = datetime(2025, 10, 1, tzinfo=UTC)
    count = SafeToSpendService._count_occurrences(
        next_run, NOW, MONTH_END, RecurringFrequency.YEARLY
    )
    assert count == 0


def test_count_occurrences_treats_naive_next_run_as_utc():
    # now = 12:00 in UTC+9 == 03:00 UTC. A naive 05:00 is 05:00 UTC, i.e. *after*
    # now, so today's fire counts. If it were read as local time it would not.
    tokyo = timezone(timedelta(hours=9))
    now = datetime(2026, 9, 14, 12, 0, tzinfo=tokyo)
    until = datetime(2026, 10, 1, tzinfo=tokyo)
    naive = datetime(2026, 9, 14, 5, 0)

    count = SafeToSpendService._count_occurrences(
        naive, now, until, RecurringFrequency.DAILY
    )
    assert count == 17  # 14..30 at 05:00 UTC, all before Oct 1 00:00 Tokyo


def test_count_occurrences_is_capped():
    until = NOW + timedelta(days=1000)
    count = SafeToSpendService._count_occurrences(
        NOW, NOW, until, RecurringFrequency.DAILY
    )
    assert count == sts._MAX_OCCURRENCES


def test_count_occurrences_unknown_frequency_counts_once():
    # `_advance` documents unknown frequencies as a "single occurrence".
    count = SafeToSpendService._count_occurrences(
        datetime(2026, 9, 20, tzinfo=UTC), NOW, MONTH_END, None
    )
    assert count == 1


# ── _money ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "value, expected",
    [
        (Decimal("1.005"), 1.01),
        (Decimal("2.675"), 2.68),
        (Decimal("-1.005"), -1.01),
        (Decimal("176.470588"), 176.47),
        (Decimal("0"), 0.0),
    ],
)
def test_money_rounds_half_up_to_cents(value, expected):
    result = SafeToSpendService._money(value)
    assert isinstance(result, float)
    assert result == expected


# ── _resolve_now ──────────────────────────────────────────────────────────────

def test_resolve_now_defaults_to_utc(freeze_now):
    freeze_now(NOW)
    service, _ = make_service(tz=None)
    now = service._resolve_now()
    assert now == NOW
    assert now.utcoffset() == timedelta(0)


def test_resolve_now_invalid_timezone_falls_back_to_utc(freeze_now):
    freeze_now(NOW)
    service, _ = make_service(tz="Not/AZone")
    now = service._resolve_now()
    assert now == NOW
    assert now.utcoffset() == timedelta(0)


def test_resolve_now_uses_user_timezone(freeze_now):
    freeze_now(NOW)
    service, _ = make_service(tz="Asia/Tokyo")
    now = service._resolve_now()
    assert now == NOW                       # same instant...
    assert now.utcoffset() == timedelta(hours=9)  # ...on the user's wall clock


def test_resolve_now_falls_back_to_pytz_when_zoneinfo_fails(freeze_now, monkeypatch):
    import zoneinfo

    def _boom(_name):
        raise zoneinfo.ZoneInfoNotFoundError("no tzdata")

    monkeypatch.setattr(zoneinfo, "ZoneInfo", _boom)
    freeze_now(NOW)
    service, _ = make_service(tz="Asia/Tokyo")
    now = service._resolve_now()
    assert now == NOW
    assert now.utcoffset() == timedelta(hours=9)


# ── compute ───────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_compute_balance_only(freeze_now):
    freeze_now(NOW)
    service, _ = make_service(capital=3000.0)

    result = await service.compute()

    assert result == {
        "safe_to_spend_per_day": 176.47,   # 3000 / 17
        "available_to_spend": 3000.0,
        "balance": 3000.0,
        "expected_income": 0.0,
        "upcoming_expenses": 0.0,
        "spent_this_month": 0.0,
        "goal_reserved": 0.0,
        "goal_contributions": 0.0,
        "goals": [],
        "spent_today": 0.0,
        "daily_limit": 176.47,
        "left_today": 176.47,
        "per_day_after_today": 187.5,      # 3000 / 16
        "days_remaining": 17,
        "month_end": "2026-09-30",
        "currency": "UAH",
        "as_of": NOW.isoformat(),
    }


@pytest.mark.anyio
async def test_compute_expands_recurring_income_and_expenses(freeze_now):
    freeze_now(NOW)
    service, _ = make_service(
        capital=3000.0,
        recurring=[
            rule(5000, TransactionKind.INCOME, RecurringFrequency.MONTHLY,
                 datetime(2026, 9, 25, tzinfo=UTC)),                      # x1 = 5000
            rule(100, TransactionKind.EXPENSE, RecurringFrequency.DAILY,
                 datetime(2026, 9, 15, tzinfo=UTC)),                      # x16 = 1600
            rule(250, TransactionKind.EXPENSE, RecurringFrequency.WEEKLY,
                 datetime(2026, 9, 16, tzinfo=UTC)),                      # x3 = 750
            rule(999, TransactionKind.TRANSFER, RecurringFrequency.DAILY,
                 datetime(2026, 9, 15, tzinfo=UTC)),                      # ignored
        ],
    )

    result = await service.compute()

    assert result["expected_income"] == 5000.0
    assert result["upcoming_expenses"] == 2350.0
    assert result["available_to_spend"] == 5650.0           # 3000 + 5000 - 2350
    assert result["safe_to_spend_per_day"] == 332.35        # 5650 / 17


@pytest.mark.anyio
async def test_compute_skips_rules_with_no_occurrences_in_window(freeze_now):
    freeze_now(NOW)
    service, _ = make_service(
        capital=1000.0,
        recurring=[
            rule(500, TransactionKind.EXPENSE, RecurringFrequency.YEARLY,
                 datetime(2025, 10, 1, tzinfo=UTC)),  # next real fire is Oct 1
        ],
    )

    result = await service.compute()

    assert result["upcoming_expenses"] == 0.0
    assert result["available_to_spend"] == 1000.0


@pytest.mark.anyio
async def test_compute_clamps_negative_available_to_zero_per_day(freeze_now):
    freeze_now(NOW)
    service, _ = make_service(
        capital=100.0,
        recurring=[
            rule(2000, TransactionKind.EXPENSE, RecurringFrequency.MONTHLY,
                 datetime(2026, 9, 20, tzinfo=UTC)),
        ],
    )

    result = await service.compute()

    assert result["available_to_spend"] == -1900.0
    assert result["safe_to_spend_per_day"] == 0.0


@pytest.mark.anyio
async def test_compute_reports_spent_this_month_without_affecting_budget(freeze_now):
    freeze_now(NOW)
    service, _ = make_service(
        capital=3000.0,
        transactions=[expense_tx(120.5), expense_tx(79.5)],
    )

    result = await service.compute()

    assert result["spent_this_month"] == 200.0
    # Spending is already reflected in capital, so it must not be subtracted again.
    assert result["available_to_spend"] == 3000.0
    assert result["safe_to_spend_per_day"] == 176.47


@pytest.mark.anyio
async def test_compute_converts_all_amounts_to_target_currency(freeze_now):
    freeze_now(NOW)
    service, _ = make_service(
        capital=4150.0,                                   # UAH -> 100 USD
        currency="UAH",
        target="usd",
        rates={"USD": 1.0, "UAH": 41.5, "EUR": 0.92},
        recurring=[
            rule(92, TransactionKind.INCOME, RecurringFrequency.MONTHLY,
                 datetime(2026, 9, 20, tzinfo=UTC), currency="EUR"),   # 100 USD
            rule(830, TransactionKind.EXPENSE, RecurringFrequency.MONTHLY,
                 datetime(2026, 9, 20, tzinfo=UTC), currency=None),    # UAH -> 20 USD
        ],
        transactions=[
            expense_tx(46, currency="eur"),                            # 50 USD
            expense_tx(415, currency=None),                            # UAH -> 10 USD
        ],
    )

    result = await service.compute()

    assert result["currency"] == "USD"
    assert result["balance"] == 100.0
    assert result["expected_income"] == 100.0
    assert result["upcoming_expenses"] == 20.0
    assert result["spent_this_month"] == 60.0
    assert result["available_to_spend"] == 180.0
    assert result["safe_to_spend_per_day"] == 10.59        # 180 / 17


@pytest.mark.anyio
async def test_compute_missing_rate_contributes_zero(freeze_now):
    freeze_now(NOW)
    service, _ = make_service(
        capital=1000.0,
        rates={"UAH": 41.5},
        recurring=[
            rule(50, TransactionKind.EXPENSE, RecurringFrequency.MONTHLY,
                 datetime(2026, 9, 20, tzinfo=UTC), currency="GBP"),
        ],
    )

    result = await service.compute()

    assert result["upcoming_expenses"] == 0.0
    assert result["available_to_spend"] == 1000.0


@pytest.mark.anyio
@pytest.mark.parametrize(
    "instant, days_remaining, month_end",
    [
        (datetime(2026, 9, 1, 0, 0, tzinfo=UTC), 30, "2026-09-30"),     # first day
        (datetime(2027, 2, 1, 8, 0, tzinfo=UTC), 28, "2027-02-28"),     # non-leap Feb
        (datetime(2028, 2, 29, 12, 0, tzinfo=UTC), 1, "2028-02-29"),    # leap day
        (datetime(2026, 12, 31, 23, 59, tzinfo=UTC), 1, "2026-12-31"),  # year rollover
    ],
)
async def test_compute_month_boundaries(freeze_now, instant, days_remaining, month_end):
    freeze_now(instant)
    service, _ = make_service(capital=900.0)

    result = await service.compute()

    assert result["days_remaining"] == days_remaining
    assert result["month_end"] == month_end
    assert result["safe_to_spend_per_day"] == round(900.0 / days_remaining, 2)


@pytest.mark.anyio
async def test_compute_month_boundary_follows_user_timezone(freeze_now):
    # Sept 30 20:00 UTC is already Oct 1 05:00 in Tokyo.
    instant = datetime(2026, 9, 30, 20, 0, tzinfo=UTC)
    freeze_now(instant)

    utc_service, _ = make_service(tz=None)
    tokyo_service, _ = make_service(tz="Asia/Tokyo")

    utc_result = await utc_service.compute()
    tokyo_result = await tokyo_service.compute()

    assert (utc_result["days_remaining"], utc_result["month_end"]) == (1, "2026-09-30")
    assert (tokyo_result["days_remaining"], tokyo_result["month_end"]) == (31, "2026-10-31")
    assert tokyo_result["as_of"] == "2026-10-01T05:00:00+09:00"


@pytest.mark.anyio
async def test_compute_queries_are_scoped_to_user(freeze_now):
    freeze_now(NOW)
    service, session = make_service(user_id=42)

    await service.compute()

    assert len(session.statements) == 3  # recurring, goals, transactions
    for stmt in session.statements:
        assert 42 in stmt.compile().params.values()


# ── Goals ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "deadline, expected",
    [
        (datetime(2026, 9, 30, tzinfo=UTC), 1),     # this month
        (datetime(2026, 12, 1, tzinfo=UTC), 4),     # Sep, Oct, Nov, Dec
        (datetime(2026, 8, 1, tzinfo=UTC), 1),      # overdue → all now
        (datetime(2026, 10, 15), 2),                # naive treated as UTC
    ],
)
def test_months_left(deadline, expected):
    assert SafeToSpendService.months_left(NOW, deadline) == expected


@pytest.mark.anyio
async def test_compute_subtracts_goal_jars_and_monthly_contributions(freeze_now):
    freeze_now(NOW)
    service, _ = make_service(
        capital=12000.0,
        goals=[
            goal(10000, 2000, deadline=datetime(2026, 12, 31, tzinfo=UTC), goal_id=1, name="Laptop"),  # 8000 / 4
            goal(5000, 500, deadline=None, goal_id=2, name="Someday"),                                # jar only
        ],
    )

    result = await service.compute()

    assert result["goal_reserved"] == 2500.0
    assert result["goal_contributions"] == 2000.0
    assert result["available_to_spend"] == 7500.0          # 12000 - 2500 - 2000
    assert result["safe_to_spend_per_day"] == 441.18       # 7500 / 17
    assert [g["name"] for g in result["goals"]] == ["Laptop", "Someday"]
    assert result["goals"][0] == {
        "goal_id": 1, "name": "Laptop", "saved": 2000.0,
        "monthly_contribution": 2000.0, "deadline": "2026-12-31",
    }


@pytest.mark.anyio
async def test_compute_reached_goal_needs_no_contribution(freeze_now):
    freeze_now(NOW)
    service, _ = make_service(
        capital=1000.0,
        goals=[goal(300, 300, deadline=datetime(2026, 9, 30, tzinfo=UTC))],
    )
    result = await service.compute()
    assert result["goal_contributions"] == 0.0
    assert result["available_to_spend"] == 700.0


# ── Today vs. the rest of the month ───────────────────────────────────────────

@pytest.mark.anyio
async def test_overspending_today_lowers_the_following_days(freeze_now):
    freeze_now(NOW)
    # Started the day with 1700 → 100/day for 17 days; spent 300 today.
    service, _ = make_service(
        capital=1400.0,
        transactions=[expense_tx(300, date=NOW - timedelta(hours=2)), expense_tx(50)],
    )

    result = await service.compute()

    assert result["spent_today"] == 300.0
    assert result["spent_this_month"] == 350.0
    assert result["daily_limit"] == 100.0
    assert result["left_today"] == -200.0
    assert result["per_day_after_today"] == 87.5          # 1400 / 16


@pytest.mark.anyio
async def test_underspending_today_keeps_allowance(freeze_now):
    freeze_now(NOW)
    service, _ = make_service(capital=1660.0, transactions=[expense_tx(40, date=NOW)])

    result = await service.compute()

    assert result["daily_limit"] == 100.0
    assert result["left_today"] == 60.0
    assert result["per_day_after_today"] == 103.75        # 1660 / 16


@pytest.mark.anyio
async def test_last_day_of_month_has_nothing_after_today(freeze_now):
    freeze_now(datetime(2026, 9, 30, 18, 0, tzinfo=UTC))
    service, _ = make_service(capital=500.0)

    result = await service.compute()

    assert result["days_remaining"] == 1
    assert result["left_today"] == 500.0
    assert result["per_day_after_today"] == 0.0
