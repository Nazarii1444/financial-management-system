"""
SafeToSpendService
──────────────────
Answers the everyday question: *"How much can I safely spend per day for the
rest of this month?"*

Model
-----
    available_to_spend = balance
                       + expected recurring income  (before month end)
                       − committed recurring expenses (before month end)
                       − money already set aside in active goals (jars)
                       − this month's required goal contributions

    safe_to_spend_per_day = max(0, available_to_spend / days_remaining)

Goal jars are virtual: `POST /api/goals/{id}/deposit` does not touch
`User.capital`, so the saved amount is still inside the balance and must be
taken out. A goal with a deadline needs `(target − saved) / months_left`
this month (months_left counts the current month; overdue → everything now).
Goals without a deadline have no mandatory contribution.

"Today" view (what the dashboard shows):

    daily_limit         = (available_to_spend + spent_today) / days_remaining
    left_today          = daily_limit − spent_today          (negative = overspent)
    per_day_after_today = available_to_spend / (days_remaining − 1)

Overspending today shrinks `per_day_after_today`; underspending grows it.

`days_remaining` counts today through the last day of the current calendar
month (inclusive). The month boundary is computed in the user's timezone when
one is set (falls back to UTC), so "the rest of the month" matches what the user
sees on their own calendar.

Committed recurring transactions are *expanded* across the remaining days — a
DAILY rule that fires ten more times this month counts ten times, mirroring how
the recurring cron actually behaves.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple

from dateutil.relativedelta import relativedelta
from sqlalchemy import select

from src.models import (
    Goal,
    RecurringFrequency,
    RecurringTransaction,
    Transaction,
    TransactionKind,
)
from .base import BaseAnalyticsService

# Safety cap on how many occurrences of a single recurring rule we expand,
# so a malformed DAILY rule can never spin the loop.
_MAX_OCCURRENCES = 400


class SafeToSpendService(BaseAnalyticsService):

    async def compute(self, **_) -> dict:
        now = self._resolve_now()

        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month_start = month_start + relativedelta(months=1)
        last_day = (next_month_start - timedelta(days=1)).day
        days_remaining = max(1, last_day - now.day + 1)  # incl. today

        # ── Current balance (capital is stored in the user's default currency) ──
        balance = self._convert(
            Decimal(str(self.user.capital)), self.user.default_currency
        )

        # ── Upcoming recurring cash-flow before month end ──────────────────────
        expected_income, upcoming_expenses = await self._upcoming_recurring(
            now, next_month_start
        )

        # ── Goals: money already in jars + what this month must add ────────────
        goal_reserved, goal_contributions, goals = await self._goal_commitments(now)

        # ── Actual spending so far this month / today (already in balance) ─────
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        spent_this_month, spent_today = await self._spent_this_month(month_start, day_start, now)

        # ── Derived figures ────────────────────────────────────────────────────
        available = balance + expected_income - upcoming_expenses - goal_reserved - goal_contributions
        per_day = available / Decimal(days_remaining)
        safe_per_day = per_day if per_day > 0 else Decimal("0")

        daily_limit = (available + spent_today) / Decimal(days_remaining)
        if daily_limit < 0:
            daily_limit = Decimal("0")
        left_today = daily_limit - spent_today
        after_today = available / Decimal(days_remaining - 1) if days_remaining > 1 else Decimal("0")
        if after_today < 0:
            after_today = Decimal("0")

        return {
            "safe_to_spend_per_day": self._money(safe_per_day),
            "available_to_spend": self._money(available),
            "balance": self._money(balance),
            "expected_income": self._money(expected_income),
            "upcoming_expenses": self._money(upcoming_expenses),
            "spent_this_month": self._money(spent_this_month),
            "goal_reserved": self._money(goal_reserved),
            "goal_contributions": self._money(goal_contributions),
            "goals": goals,
            "spent_today": self._money(spent_today),
            "daily_limit": self._money(daily_limit),
            "left_today": self._money(left_today),
            "per_day_after_today": self._money(after_today),
            "days_remaining": days_remaining,
            "month_end": (next_month_start - timedelta(days=1)).date().isoformat(),
            "currency": self.target_currency,
            "as_of": now.isoformat(),
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _resolve_now(self) -> datetime:
        """Current time in the user's timezone, falling back to UTC."""
        tzname = self.user.timezone
        if tzname:
            try:
                from zoneinfo import ZoneInfo
                return datetime.now(ZoneInfo(tzname))
            except Exception:
                try:
                    import pytz
                    return datetime.now(pytz.timezone(tzname))
                except Exception:
                    pass
        return datetime.now(timezone.utc)

    async def _upcoming_recurring(
        self, now: datetime, until: datetime
    ) -> Tuple[Decimal, Decimal]:
        rules = (
            await self.session.execute(
                select(RecurringTransaction).where(
                    RecurringTransaction.user_id == self.user.id_,
                    RecurringTransaction.is_active.is_(True),
                    RecurringTransaction.next_run < until,
                )
            )
        ).scalars().all()

        income = Decimal("0")
        expenses = Decimal("0")

        for rt in rules:
            occurrences = self._count_occurrences(rt.next_run, now, until, rt.frequency)
            if occurrences <= 0:
                continue
            amt = self._convert(
                Decimal(str(rt.amount)), self._effective_currency(rt.currency)
            ) * occurrences
            if rt.kind == TransactionKind.INCOME:
                income += amt
            elif rt.kind == TransactionKind.EXPENSE:
                expenses += amt

        return income, expenses

    @classmethod
    def _count_occurrences(
        cls,
        next_run: datetime,
        now: datetime,
        until: datetime,
        frequency: RecurringFrequency,
    ) -> int:
        """How many times a recurring rule fires within [now, until)."""
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=timezone.utc)
        cursor = next_run
        count = 0
        for _ in range(_MAX_OCCURRENCES):
            if cursor >= until:
                break
            if cursor >= now:
                count += 1
            nxt = cls._advance(cursor, frequency)
            if nxt <= cursor:  # unknown frequency never advances: single occurrence
                break
            cursor = nxt
        return count

    @staticmethod
    def _advance(current: datetime, frequency: RecurringFrequency) -> datetime:
        """Mirror of the recurring cron's step so counts match real firing."""
        if frequency == RecurringFrequency.DAILY:
            return current + timedelta(days=1)
        if frequency == RecurringFrequency.WEEKLY:
            return current + timedelta(weeks=1)
        if frequency == RecurringFrequency.BIWEEKLY:
            return current + timedelta(weeks=2)
        if frequency == RecurringFrequency.MONTHLY:
            return current + relativedelta(months=1)
        if frequency == RecurringFrequency.YEARLY:
            return current + relativedelta(years=1)
        return current  # unknown frequency: treat as single occurrence

    async def _goal_commitments(self, now: datetime) -> Tuple[Decimal, Decimal, list]:
        """(saved in active jars, contributions required this month, per-goal breakdown)."""
        goals = (
            await self.session.execute(
                select(Goal).where(
                    Goal.user_id == self.user.id_,
                    Goal.is_completed.is_(False),
                )
            )
        ).scalars().all()

        reserved = Decimal("0")
        required = Decimal("0")
        breakdown = []
        for goal in goals:
            currency = self._effective_currency(goal.currency)
            saved = self._convert(Decimal(str(goal.saved_amount or 0)), currency)
            reserved += saved

            monthly = Decimal("0")
            if goal.deadline is not None:
                remaining = Decimal(str(goal.target_amount)) - Decimal(str(goal.saved_amount or 0))
                if remaining > 0:
                    monthly = self._convert(remaining, currency) / self.months_left(now, goal.deadline)
            required += monthly
            breakdown.append({
                "goal_id": goal.id_,
                "name": goal.name,
                "saved": self._money(saved),
                "monthly_contribution": self._money(monthly),
                "deadline": goal.deadline.date().isoformat() if goal.deadline else None,
            })

        breakdown.sort(key=lambda g: -g["monthly_contribution"])
        return reserved, required, breakdown

    @staticmethod
    def months_left(now: datetime, deadline: datetime) -> int:
        """Calendar months from the current one to the deadline's, inclusive (≥ 1)."""
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        deadline = deadline.astimezone(now.tzinfo) if now.tzinfo else deadline
        months = (deadline.year - now.year) * 12 + deadline.month - now.month + 1
        return max(1, months)

    async def _spent_this_month(
        self, start: datetime, day_start: datetime, end: datetime
    ) -> Tuple[Decimal, Decimal]:
        """Expenses month-to-date and today (both already reflected in the balance)."""
        txs = (
            await self.session.execute(
                select(Transaction).where(
                    Transaction.user_id == self.user.id_,
                    Transaction.kind == TransactionKind.EXPENSE,
                    Transaction.date >= start,
                    Transaction.date <= end,
                )
            )
        ).scalars().all()

        total = Decimal("0")
        today = Decimal("0")
        for tx in txs:
            amount = self._convert(
                Decimal(str(tx.amount)), self._effective_currency(tx.currency)
            )
            total += amount
            tx_date = tx.date if tx.date.tzinfo else tx.date.replace(tzinfo=timezone.utc)
            if tx_date >= day_start:
                today += amount
        return total, today

    @staticmethod
    def _money(value: Decimal) -> float:
        return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
