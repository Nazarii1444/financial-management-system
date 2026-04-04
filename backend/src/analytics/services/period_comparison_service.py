"""
PeriodComparisonService
────────────────────────
Compares income/expenses between two consecutive periods of equal length.

Modes
-----
  monthly  – current calendar month  vs previous calendar month
  yearly   – current calendar year   vs previous calendar year
  custom   – caller supplies date_from / date_to for the CURRENT window;
             the PREVIOUS window is automatically shifted back by the same
             duration (e.g. last 30 days vs the 30 days before that)

compute(mode="monthly")
compute(mode="yearly")
compute(mode="custom", date_from=datetime(...), date_to=datetime(...))
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from dateutil.relativedelta import relativedelta
from sqlalchemy import select

from src.models import Transaction, TransactionKind
from .base import BaseAnalyticsService


class PeriodComparisonService(BaseAnalyticsService):

    async def compute(
        self,
        mode: str = "monthly",
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        **_,
    ) -> dict:
        now = datetime.now(timezone.utc)

        # ── Resolve current / previous window ────────────────────────────────
        if mode == "yearly":
            cur_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            cur_end   = now
            prev_start = cur_start - relativedelta(years=1)
            prev_end   = cur_start  # exclusive upper-bound for previous year

        elif mode == "custom":
            if not date_from or not date_to:
                raise ValueError("mode='custom' requires both date_from and date_to")
            if date_from.tzinfo is None:
                date_from = date_from.replace(tzinfo=timezone.utc)
            if date_to.tzinfo is None:
                date_to = date_to.replace(tzinfo=timezone.utc)
            duration = date_to - date_from
            cur_start  = date_from
            cur_end    = date_to
            prev_start = date_from - duration
            prev_end   = date_from

        else:  # monthly (default)
            cur_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            cur_end   = now
            prev_start = cur_start - relativedelta(months=1)
            prev_end   = cur_start  # exclusive upper-bound for previous month

        # ── Fetch and aggregate ───────────────────────────────────────────────
        current  = await self._aggregate(cur_start,  cur_end)
        previous = await self._aggregate(prev_start, prev_end)

        # ── Compute change ────────────────────────────────────────────────────
        def _pct(new: float, old: float) -> Optional[float]:
            if old == 0:
                return None
            return round((new - old) / abs(old) * 100, 1)

        change = {
            "income_diff":   round(current["income"]   - previous["income"],   2),
            "income_pct":    _pct(current["income"],   previous["income"]),
            "expenses_diff": round(current["expenses"] - previous["expenses"], 2),
            "expenses_pct":  _pct(current["expenses"], previous["expenses"]),
            "net_diff":      round(current["net"]      - previous["net"],      2),
            "net_pct":       _pct(current["net"],      previous["net"]),
        }

        return {
            "current":  {**current,  "from_": cur_start.isoformat(),  "to": cur_end.isoformat()},
            "previous": {**previous, "from_": prev_start.isoformat(), "to": prev_end.isoformat()},
            "change":   change,
            "currency": self.target_currency,
        }

    # ── Private ───────────────────────────────────────────────────────────────

    async def _aggregate(self, start: datetime, end: datetime) -> dict:
        txs = (
            await self.session.execute(
                select(Transaction).where(
                    Transaction.user_id == self.user.id_,
                    Transaction.date >= start,
                    Transaction.date < end,
                )
            )
        ).scalars().all()

        income   = Decimal("0")
        expenses = Decimal("0")

        for tx in txs:
            amt = self._convert(Decimal(str(tx.amount)), self._effective_currency(tx.currency))
            if tx.kind == TransactionKind.INCOME:
                income   += amt
            elif tx.kind == TransactionKind.EXPENSE:
                expenses += amt

        return {
            "income":            float(income),
            "expenses":          float(expenses),
            "net":               float(income - expenses),
            "transaction_count": len(txs),
        }

