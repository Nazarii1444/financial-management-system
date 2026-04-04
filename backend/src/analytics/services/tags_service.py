from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select

from src.models import Transaction, TransactionKind
from .base import BaseAnalyticsService


class TagBreakdownService(BaseAnalyticsService):
    """
    Spending / income grouped by tag — a transaction contributes its
    full converted amount to **each** of its tags.

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

        tag_totals: dict = {}   # tag -> {amount, count}
        grand_total = Decimal("0")

        for tx in txs:
            amt = self._convert(Decimal(str(tx.amount)), self._effective_currency(tx.currency))
            grand_total += amt
            tags = tx.tags or []
            if not tags:
                # Untagged bucket
                key = "(untagged)"
                if key not in tag_totals:
                    tag_totals[key] = {"amount": Decimal("0"), "count": 0}
                tag_totals[key]["amount"] += amt
                tag_totals[key]["count"] += 1
            else:
                for tag in tags:
                    if tag not in tag_totals:
                        tag_totals[tag] = {"amount": Decimal("0"), "count": 0}
                    tag_totals[tag]["amount"] += amt
                    tag_totals[tag]["count"] += 1

        items = []
        for tag, d in sorted(tag_totals.items(), key=lambda x: x[1]["amount"], reverse=True):
            pct = float(d["amount"] / grand_total * 100) if grand_total else 0.0
            items.append({
                "tag": tag,
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

