"""
Transaction search shared by `GET /api/transactions/search` and the CSV export.

Structured filters (kind, category, tags, period, amount, currency, receipt)
run in SQL; the free-text query is matched in Python with `fuzzy.match_score`
against name, note, category (raw + uk/en display names) and tags, so it is
typo-, case- and keyboard-layout tolerant without a DB extension.

Rows are fetched as plain column tuples, not ORM entities: building ~2000
`Transaction` instances per request was the dominant cost, and callers only
read attributes (`TransactionOut.model_validate`, CSV export, totals).

With a text query the search runs in two steps: SQL groups the filtered rows
by their searchable texts (name, note, category, tags — merchants repeat, so
~2000 rows collapse to a few hundred), Python scores each distinct group once,
and only the rows of matching groups are loaded in full.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import Integer, any_, bindparam, exists, func, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from src.calendar_export.formatting import CATEGORY_NAMES
from src.models import Currencies, Receipt, Transaction, TransactionKind, User
from src.transactions.services.fuzzy import compile_query, match_compiled

_SUPPORTED_CURRENCIES = {c.value for c in Currencies}
_CENT = Decimal("0.01")

# Field weights: the name matters most, then the note, then category / tags
_W_NAME, _W_NOTE, _W_META = 1.0, 0.9, 0.8


@dataclass
class SearchFilters:
    q: Optional[str] = None
    kind: Optional[TransactionKind] = None
    category: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    currencies: List[str] = field(default_factory=list)
    has_receipt: Optional[bool] = None


# Every column of Transaction; rows expose them as attributes (`row.name`, …)
_TX_COLUMNS = [getattr(Transaction, c.key) for c in Transaction.__table__.columns]


@dataclass
class SearchHit:
    tx: Any  # Row with Transaction's columns as attributes (read-only)
    has_receipt: bool
    score: float


def parse_currencies(raw: Optional[str]) -> List[str]:
    codes = [c.strip().upper() for c in (raw or "").split(",") if c.strip()]
    unknown = [c for c in codes if c not in _SUPPORTED_CURRENCIES]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unsupported currency: {', '.join(unknown)}")
    return codes


def searchable_fields(tx) -> List[Tuple[Optional[str], float]]:
    cat = (tx.category_name or "").lower()
    meta = " ".join([cat, CATEGORY_NAMES["uk"].get(cat, ""), CATEGORY_NAMES["en"].get(cat, ""), *(tx.tags or [])])
    return [(tx.name, _W_NAME), (tx.note, _W_NOTE), (meta, _W_META)]


def convert(amount: Decimal, src: str, dst: str, rates: Dict[str, float]) -> Decimal:
    """USD-pivot conversion; 0 when a rate is missing (mirrors BaseAnalyticsService)."""
    if src == dst:
        return amount.quantize(_CENT, rounding=ROUND_HALF_UP)
    if src not in rates or dst not in rates:
        return Decimal("0")
    value = amount / Decimal(str(rates[src])) * Decimal(str(rates[dst]))
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def totals(hits: List[SearchHit], user: User, rates: Dict[str, float]) -> dict:
    target = user.default_currency.upper()
    expense = income = Decimal("0")
    for hit in hits:
        tx = hit.tx
        value = convert(Decimal(str(tx.amount)), (tx.currency or target).upper(), target, rates)
        if tx.kind == TransactionKind.EXPENSE:
            expense += value
        elif tx.kind == TransactionKind.INCOME:
            income += value
    return {
        "expense": float(expense),
        "income": float(income),
        "net": float(income - expense),
        "currency": target,
    }


async def search_transactions(session: AsyncSession, user: User, f: SearchFilters) -> List[SearchHit]:
    """All matching transactions of *user*, newest first (callers paginate)."""
    receipt_exists = exists().where(Receipt.transaction_id == Transaction.id_)
    conditions = [Transaction.user_id == user.id_]

    if f.kind is not None:
        conditions.append(Transaction.kind == f.kind)
    if f.category:
        conditions.append(Transaction.category_name == f.category.strip().lower())
    for tag in f.tags:
        conditions.append(Transaction.tags.contains([tag]))
    if f.date_from:
        conditions.append(Transaction.date >= f.date_from)
    if f.date_to:
        conditions.append(Transaction.date <= f.date_to)
    if f.amount_min is not None:
        conditions.append(Transaction.amount >= f.amount_min)
    if f.amount_max is not None:
        conditions.append(Transaction.amount <= f.amount_max)
    if f.currencies:
        # NULL currency means the user's default currency
        if user.default_currency.upper() in f.currencies:
            conditions.append(Transaction.currency.in_(f.currencies) | Transaction.currency.is_(None))
        else:
            conditions.append(Transaction.currency.in_(f.currencies))
    if f.has_receipt is True:
        conditions.append(receipt_exists)
    elif f.has_receipt is False:
        conditions.append(~receipt_exists)

    query = (f.q or "").strip()
    scores: Dict[int, float] = {}
    if query:
        # Step 1: distinct searchable texts + their ids; score each text group once
        text_cols = (Transaction.name, Transaction.note, Transaction.category_name, Transaction.tags)
        groups = (await session.execute(
            select(*text_cols, func.array_agg(Transaction.id_).label("ids")).where(*conditions).group_by(*text_cols)
        )).all()
        variants = compile_query(query)
        for group in groups:
            score = match_compiled(variants, searchable_fields(group))
            if score > 0:
                scores.update(dict.fromkeys(group.ids, score))
        if not scores:
            return []
        # Step 2: full rows of the matches only (one array parameter, not one per id)
        conditions = [Transaction.id_ == any_(bindparam("ids", list(scores), type_=ARRAY(Integer)))]

    stmt = (
        select(*_TX_COLUMNS, receipt_exists.label("has_receipt"))
        .where(*conditions)
        .order_by(Transaction.date.desc(), Transaction.id_.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        SearchHit(tx=row, has_receipt=bool(row.has_receipt), score=scores.get(row.id_, 1.0))
        for row in rows
    ]
