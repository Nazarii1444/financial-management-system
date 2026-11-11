"""
Report data (no rendering): monthly statement, expense structure, budget
plans and recurring payments. `pdf.py` turns these dicts into PDFs; the
recurring summary is also served as JSON for the UI.

All money is converted to the user's default currency with current NBU rates
(`search_service.convert`). Historical balances are reconstructed from the
current capital minus later transactions, so they are approximate when rates
moved — the PDF says so.
"""
from calendar import monthrange
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.services.budget_comparison_service import BudgetComparisonService
from src.models import (
    Budget,
    BudgetMember,
    RecurringFrequency,
    RecurringTransaction,
    Transaction,
    TransactionKind,
    User,
)
from src.transactions.currency_converter import get_rates_map
from src.transactions.services.search_service import convert

# Occurrences per year for each frequency
ANNUAL_FACTOR = {
    RecurringFrequency.DAILY: Decimal(365),
    RecurringFrequency.WEEKLY: Decimal(52),
    RecurringFrequency.BIWEEKLY: Decimal(26),
    RecurringFrequency.MONTHLY: Decimal(12),
    RecurringFrequency.YEARLY: Decimal(1),
}

# Recurring expenses in these categories are shown as "subscriptions"
SUBSCRIPTION_CATEGORIES = {"entertainment", "phone", "education", "sports", "electronics", "beauty"}

_CENT = Decimal("0.01")


# ── Periods ───────────────────────────────────────────────────────────────────

def month_bounds(month: str) -> Tuple[datetime, datetime]:
    """'2026-10' → [Oct 1 00:00 UTC, Nov 1 00:00 UTC)."""
    try:
        year, mon = (int(x) for x in month.split("-"))
        start = datetime(year, mon, 1, tzinfo=timezone.utc)
    except (ValueError, TypeError):
        raise ValueError("month must look like YYYY-MM")
    end = start + timedelta(days=monthrange(year, mon)[1])
    return start, end


def current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


# ── Shared helpers ────────────────────────────────────────────────────────────

class _Money:
    def __init__(self, user: User, rates: Dict[str, float]):
        self.currency = user.default_currency.upper()
        self.rates = rates

    def __call__(self, amount, currency: Optional[str]) -> Decimal:
        return convert(Decimal(str(amount)), (currency or self.currency).upper(), self.currency, self.rates)

    def signed(self, tx) -> Decimal:
        value = self(tx.amount, tx.currency)
        if tx.kind == TransactionKind.EXPENSE:
            return -value
        if tx.kind == TransactionKind.INCOME:
            return value
        return Decimal("0")


async def _transactions(session: AsyncSession, user: User, start: datetime, end: Optional[datetime] = None,
                        kind: Optional[TransactionKind] = None) -> List[Transaction]:
    stmt = select(Transaction).where(Transaction.user_id == user.id_, Transaction.date >= start)
    if end is not None:
        stmt = stmt.where(Transaction.date < end)
    if kind is not None:
        stmt = stmt.where(Transaction.kind == kind)
    stmt = stmt.order_by(Transaction.date.asc(), Transaction.id_.asc())
    return list((await session.execute(stmt)).scalars().all())


# ── 1. Monthly statement ──────────────────────────────────────────────────────

async def statement(session: AsyncSession, user: User, month: str) -> dict:
    start, end = month_bounds(month)
    money = _Money(user, await get_rates_map(session))
    txs = await _transactions(session, user, start, end)
    later = await _transactions(session, user, end)

    closing = Decimal(str(user.capital)) - sum((money.signed(t) for t in later), Decimal("0"))
    income = sum((money(t.amount, t.currency) for t in txs if t.kind == TransactionKind.INCOME), Decimal("0"))
    expense = sum((money(t.amount, t.currency) for t in txs if t.kind == TransactionKind.EXPENSE), Decimal("0"))
    opening = closing - income + expense

    rows = [{
        "date": t.date,
        "name": t.name,
        "category": t.category_name,
        "kind": t.kind,
        "amount": Decimal(str(t.amount)),
        "currency": (t.currency or money.currency).upper(),
        "converted": money.signed(t) if t.kind != TransactionKind.TRANSFER else money(t.amount, t.currency),
        "note": t.note,
    } for t in txs]
    return {
        "month": month, "start": start, "end": end - timedelta(seconds=1),
        "currency": money.currency,
        "opening": opening.quantize(_CENT), "income": income, "expense": expense,
        "closing": closing.quantize(_CENT), "count": len(txs), "rows": rows,
    }


# ── 2. Expense structure ──────────────────────────────────────────────────────

def _by_category(txs, money: _Money) -> Dict[str, Dict[str, Decimal]]:
    out: Dict[str, Dict] = defaultdict(lambda: {"amount": Decimal("0"), "count": 0})
    for t in txs:
        out[t.category_name]["amount"] += money(t.amount, t.currency)
        out[t.category_name]["count"] += 1
    return out


async def expense_structure(session: AsyncSession, user: User, start: datetime, end: datetime) -> dict:
    money = _Money(user, await get_rates_map(session))
    txs = await _transactions(session, user, start, end, TransactionKind.EXPENSE)
    prev_start = start - (end - start)
    prev = _by_category(await _transactions(session, user, prev_start, start, TransactionKind.EXPENSE), money)
    cur = _by_category(txs, money)
    total = sum((c["amount"] for c in cur.values()), Decimal("0"))

    categories = []
    for cat, data in sorted(cur.items(), key=lambda kv: kv[1]["amount"], reverse=True):
        before = prev.get(cat, {}).get("amount", Decimal("0"))
        categories.append({
            "category": cat,
            "amount": data["amount"],
            "count": data["count"],
            "share": float(data["amount"] / total * 100) if total else 0.0,
            "previous": before,
            "change": float((data["amount"] - before) / before * 100) if before else None,
        })
    top = sorted(txs, key=lambda t: money(t.amount, t.currency), reverse=True)[:5]
    return {
        "start": start, "end": end - timedelta(seconds=1), "currency": money.currency,
        "total": total,
        "previous_total": sum((c["amount"] for c in prev.values()), Decimal("0")),
        "count": len(txs),
        "categories": categories,
        "top": [{"date": t.date, "name": t.name, "category": t.category_name,
                 "amount": money(t.amount, t.currency)} for t in top],
    }


# ── 3. Budget plans ───────────────────────────────────────────────────────────

async def budget_plans(session: AsyncSession, user: User, month: str) -> dict:
    start, end = month_bounds(month)
    rates = await get_rates_map(session)
    budgets = (await session.execute(
        select(Budget)
        .join(BudgetMember, BudgetMember.budget_id == Budget.id_)
        .where(BudgetMember.user_id == user.id_)
        .order_by(Budget.name)
    )).scalars().all()

    items = []
    for budget in budgets:
        data = await BudgetComparisonService(session, user, rates).compute(
            budget_id=budget.id_, date_from=start, date_to=end - timedelta(microseconds=1),
        )
        items.append({**data, "currency": budget.currency})
    return {"month": month, "start": start, "end": end - timedelta(seconds=1), "budgets": items}


# ── 4. Recurring payments ─────────────────────────────────────────────────────

def annualize(rule, money) -> Tuple[Decimal, Decimal]:
    """(per year, per month) of a rule in the user's currency."""
    per_year = (money(rule.amount, rule.currency) * ANNUAL_FACTOR.get(rule.frequency, Decimal(1))).quantize(_CENT)
    return per_year, (per_year / 12).quantize(_CENT)


def recurring_summary_from_rules(rules, money) -> dict:
    expenses, incomes = [], []
    for rule in rules:
        if not rule.is_active or rule.kind == TransactionKind.TRANSFER:
            continue
        per_year, per_month = annualize(rule, money)
        row = {
            "id_": rule.id_,
            "name": rule.name,
            "category": rule.category_name,
            "frequency": rule.frequency.value,
            "amount": Decimal(str(rule.amount)),
            "currency": (rule.currency or money.currency).upper(),
            "per_month": per_month,
            "per_year": per_year,
            "next_run": rule.next_run,
            "subscription": rule.kind == TransactionKind.EXPENSE and rule.category_name in SUBSCRIPTION_CATEGORIES,
        }
        (expenses if rule.kind == TransactionKind.EXPENSE else incomes).append(row)
    expenses.sort(key=lambda r: r["per_year"], reverse=True)
    incomes.sort(key=lambda r: r["per_year"], reverse=True)

    def total(rows, key):
        return sum((r[key] for r in rows), Decimal("0"))

    subs = [r for r in expenses if r["subscription"]]
    income_year = total(incomes, "per_year")
    expense_year = total(expenses, "per_year")
    return {
        "currency": money.currency,
        "expenses": expenses,
        "incomes": incomes,
        "expense_per_month": total(expenses, "per_month"),
        "expense_per_year": expense_year,
        "subscriptions_per_month": total(subs, "per_month"),
        "subscriptions_per_year": total(subs, "per_year"),
        "subscriptions_count": len(subs),
        "income_per_year": income_year,
        "income_share": float(expense_year / income_year * 100) if income_year else None,
    }


async def recurring_summary(session: AsyncSession, user: User) -> dict:
    money = _Money(user, await get_rates_map(session))
    rules = (await session.execute(
        select(RecurringTransaction).where(RecurringTransaction.user_id == user.id_)
    )).scalars().all()
    return recurring_summary_from_rules(rules, money)
