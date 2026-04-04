from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from dateutil.relativedelta import relativedelta
from sqlalchemy import select

from src.models import Transaction, TransactionKind
from .base import BaseAnalyticsService


class TrendsService(BaseAnalyticsService):
    """
    Monthly and yearly income vs expense trends.

    compute(mode="monthly", months=12)
    compute(mode="yearly",  years=3)
    """

    async def compute(self, mode: str = "monthly", months: int = 12, years: int = 3, **_) -> Any:
        if mode == "yearly":
            return await self._yearly(years)
        return await self._monthly(months)

    # ── Monthly ───────────────────────────────────────────────────────────────

    async def _monthly(self, months: int) -> dict:
        now = datetime.now(timezone.utc)
        start = (now - relativedelta(months=months - 1)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        txs = (
            await self.session.execute(
                select(Transaction).where(
                    Transaction.user_id == self.user.id_,
                    Transaction.date >= start,
                )
            )
        ).scalars().all()

        # Accumulate by (year, month)
        data: dict = {}
        for tx in txs:
            key = (tx.date.year, tx.date.month)
            if key not in data:
                data[key] = {"income": Decimal("0"), "expenses": Decimal("0")}
            amt = self._convert(Decimal(str(tx.amount)), self._effective_currency(tx.currency))
            if tx.kind == TransactionKind.INCOME:
                data[key]["income"] += amt
            elif tx.kind == TransactionKind.EXPENSE:
                data[key]["expenses"] += amt

        # Build ordered result — fill empty months with zeros
        result = []
        cursor = start
        for _ in range(months):
            key = (cursor.year, cursor.month)
            entry = data.get(key, {"income": Decimal("0"), "expenses": Decimal("0")})
            income = entry["income"]
            expenses = entry["expenses"]
            result.append({
                "year": cursor.year,
                "month": cursor.month,
                "income": float(income),
                "expenses": float(expenses),
                "net": float(income - expenses),
            })
            cursor += relativedelta(months=1)

        return {"months": result, "currency": self.target_currency}

    # ── Yearly ────────────────────────────────────────────────────────────────

    async def _yearly(self, years: int) -> dict:
        now = datetime.now(timezone.utc)
        start_year = now.year - years + 1
        start = datetime(start_year, 1, 1, tzinfo=timezone.utc)

        txs = (
            await self.session.execute(
                select(Transaction).where(
                    Transaction.user_id == self.user.id_,
                    Transaction.date >= start,
                )
            )
        ).scalars().all()

        data: dict = {}
        for tx in txs:
            year = tx.date.year
            if year not in data:
                data[year] = {"income": Decimal("0"), "expenses": Decimal("0")}
            amt = self._convert(Decimal(str(tx.amount)), self._effective_currency(tx.currency))
            if tx.kind == TransactionKind.INCOME:
                data[year]["income"] += amt
            elif tx.kind == TransactionKind.EXPENSE:
                data[year]["expenses"] += amt

        result = []
        for year in range(start_year, now.year + 1):
            entry = data.get(year, {"income": Decimal("0"), "expenses": Decimal("0")})
            income = entry["income"]
            expenses = entry["expenses"]
            result.append({
                "year": year,
                "income": float(income),
                "expenses": float(expenses),
                "net": float(income - expenses),
            })

        return {"years": result, "currency": self.target_currency}

