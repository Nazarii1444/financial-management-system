from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select

from src.models import Budget, BudgetMember, Transaction, TransactionKind
from .base import BaseAnalyticsService


class BudgetComparisonService(BaseAnalyticsService):
    """
    Budget vs actual:
      - Sums EXPENSE transactions for all budget members in the period.
      - Compares against budget.limit_amount (if set).

    compute(budget_id=1, date_from=..., date_to=...)
    """

    async def compute(
        self,
        budget_id: int,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        **_,
    ) -> dict:
        # ── 1. Load budget & verify membership ───────────────────────────────
        budget: Optional[Budget] = await self.session.get(Budget, budget_id)
        if not budget:
            raise HTTPException(status_code=404, detail="Budget not found")

        check = (
            await self.session.execute(
                select(BudgetMember).where(
                    BudgetMember.budget_id == budget_id,
                    BudgetMember.user_id == self.user.id_,
                )
            )
        ).scalar_one_or_none()
        if not check:
            raise HTTPException(status_code=403, detail="Not a member of this budget")

        # ── 2. All member user IDs ────────────────────────────────────────────
        member_rows = (
            await self.session.execute(
                select(BudgetMember.user_id).where(BudgetMember.budget_id == budget_id)
            )
        ).all()
        member_ids = [r[0] for r in member_rows]

        # ── 3. Expense transactions for those members in the period ───────────
        stmt = select(Transaction).where(
            Transaction.user_id.in_(member_ids),
            Transaction.kind == TransactionKind.EXPENSE,
        )
        if date_from:
            stmt = stmt.where(Transaction.date >= date_from)
        if date_to:
            stmt = stmt.where(Transaction.date <= date_to)

        txs = (await self.session.execute(stmt)).scalars().all()

        # ── 4. Aggregate ─────────────────────────────────────────────────────
        # Use the budget's own currency as target when comparing against limit
        target = (budget.currency or self.target_currency).upper()
        cat_totals: dict = {}
        total_spent = Decimal("0")

        for tx in txs:
            src = self._effective_currency(tx.currency)
            amt = self._convert(Decimal(str(tx.amount)), src)
            # Re-convert using budget currency if it differs from user default
            if target != self.target_currency:
                # convert from target_currency to budget.currency
                # _convert always goes → self.target_currency; patch the pivot
                src_rate = self.rates.get(src)
                bgt_rate = self.rates.get(target)
                if src_rate and bgt_rate:
                    amt = (Decimal(str(tx.amount)) / Decimal(str(src_rate)) * Decimal(str(bgt_rate))).quantize(
                        Decimal("0.01")
                    )
            total_spent += amt
            cat = tx.category_name
            cat_totals[cat] = cat_totals.get(cat, Decimal("0")) + amt

        # ── 5. Compare against limit ─────────────────────────────────────────
        limit = Decimal(str(budget.limit_amount)) if budget.limit_amount else None
        remaining = float((limit - total_spent)) if limit is not None else None
        utilization = round(float(total_spent / limit * 100), 1) if limit else None

        by_category = [
            {"category": cat, "amount": float(amt)}
            for cat, amt in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)
        ]

        return {
            "budget_id": budget.id_,
            "budget_name": budget.name,
            "budget_type": budget.type.value,
            "limit_amount": float(limit) if limit is not None else None,
            "actual_spent": float(total_spent),
            "remaining": remaining,
            "utilization_percent": utilization,
            "by_category": by_category,
            "currency": target,
            "period": {
                "from": date_from.isoformat() if date_from else None,
                "to": date_to.isoformat() if date_to else None,
            },
        }

