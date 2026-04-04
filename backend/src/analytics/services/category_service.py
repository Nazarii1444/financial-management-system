from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select

from src.models import Transaction, TransactionKind
from .base import BaseAnalyticsService


class CategoryBreakdownService(BaseAnalyticsService):
    """
    Spending / income grouped by category_name — data for pie/bar charts.

    compute(kind=TransactionKind.EXPENSE, date_from=..., date_to=...)
    """

    async def compute(
        self,
        kind: Optional[TransactionKind] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        **_,
    ) -> dict:
        stmt = select(Transaction).where(Transaction.user_id == self.user.id_)
        if kind is not None:
            stmt = stmt.where(Transaction.kind == kind)
        if date_from:
            stmt = stmt.where(Transaction.date >= date_from)
        if date_to:
            stmt = stmt.where(Transaction.date <= date_to)

        txs = (await self.session.execute(stmt)).scalars().all()

        cat_totals: dict = {}   # category -> {amount, count}
        grand_total = Decimal("0")

        for tx in txs:
            amt = self._convert(Decimal(str(tx.amount)), self._effective_currency(tx.currency))
            cat = tx.category_name
            if cat not in cat_totals:
                cat_totals[cat] = {"amount": Decimal("0"), "count": 0}
            cat_totals[cat]["amount"] += amt
            cat_totals[cat]["count"] += 1
            grand_total += amt

        items = []
        for cat, d in sorted(cat_totals.items(), key=lambda x: x[1]["amount"], reverse=True):
            pct = float(d["amount"] / grand_total * 100) if grand_total else 0.0
            items.append({
                "category": cat,
                "amount": float(d["amount"]),
                "percent": round(pct, 1),
                "count": d["count"],
            })

        return {
            "kind": kind.name if kind else "ALL",
            "total": float(grand_total),
            "items": items,
            "currency": self.target_currency,
        }

