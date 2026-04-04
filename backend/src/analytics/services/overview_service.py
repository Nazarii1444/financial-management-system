from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select

from src.models import Transaction, TransactionKind
from .base import BaseAnalyticsService


class OverviewService(BaseAnalyticsService):
    """Balance card: total income, total expenses, net change for a period."""

    async def compute(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        **_,
    ) -> dict:
        stmt = select(Transaction).where(Transaction.user_id == self.user.id_)
        if date_from:
            stmt = stmt.where(Transaction.date >= date_from)
        if date_to:
            stmt = stmt.where(Transaction.date <= date_to)

        txs = (await self.session.execute(stmt)).scalars().all()

        total_income = Decimal("0")
        total_expenses = Decimal("0")

        for tx in txs:
            amt = self._convert(Decimal(str(tx.amount)), self._effective_currency(tx.currency))
            if tx.kind == TransactionKind.INCOME:
                total_income += amt
            elif tx.kind == TransactionKind.EXPENSE:
                total_expenses += amt

        net = total_income - total_expenses

        return {
            "balance": round(float(self.user.capital), 2),
            "total_income": float(total_income),
            "total_expenses": float(total_expenses),
            "net": float(net),
            "currency": self.target_currency,
            "period": {
                "from": date_from.isoformat() if date_from else None,
                "to": date_to.isoformat() if date_to else None,
            },
        }

