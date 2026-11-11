from typing import List, Optional
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from fastapi.exceptions import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.dependencies import get_current_user
from src.models import Transaction, TransactionKind, User
from src.transactions.schemas import (
    TransactionCreate,
    TransactionDeletedOut,
    TransactionOut,
    TransactionSearchOut,
    TransactionUpdate,
    parse_kind_query,
)
from src.transactions.currency_converter import convert_to_user_currency, get_rates_map
from src.transactions.services.trash_service import move_to_trash
from src.transactions.services.search_service import (
    SearchFilters,
    parse_currencies,
    search_transactions,
    totals as search_totals,
)
from src.transactions.categories import (  # re-exported: import_router uses _validate_category
    ALL_CATEGORIES,
    ALLOWED_EXPENSE_CATEGORIES,
    ALLOWED_INCOME_CATEGORIES,
    ALLOWED_TRANSFER_CATEGORIES,
    validate_category as _validate_category,
)
from src.transactions.services.transaction_service import create_user_transaction, transaction_to_out


transaction_router = APIRouter()


async def _get_user_tx_or_404(
        session: AsyncSession, tx_id: int, user_id: int
) -> Transaction:
    stmt = select(Transaction).where(
        Transaction.id_ == tx_id,
        Transaction.user_id == user_id,
    )
    tx = (await session.execute(stmt)).scalar_one_or_none()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return tx


@transaction_router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
async def create_transaction(
        payload: TransactionCreate,
        session: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    tx = await create_user_transaction(session, current_user, payload)
    await session.commit()
    await session.refresh(tx)
    await session.refresh(current_user)
    return transaction_to_out(tx, current_user)


def search_filters(
        q: Optional[str] = Query(None, max_length=100, description="Text in name / note / category / tags; typo- and case-tolerant"),
        kind: Optional[str] = Query(None, description="EXPENSE / INCOME / TRANSFER (or 0 / 1 / 2)"),
        category: Optional[str] = Query(None),
        tags: Optional[str] = Query(None, description="Comma-separated; all must be present"),
        date_from: Optional[datetime] = Query(None),
        date_to: Optional[datetime] = Query(None),
        amount_min: Optional[Decimal] = Query(None, ge=0, description="In the transaction's own currency"),
        amount_max: Optional[Decimal] = Query(None, ge=0),
        currency: Optional[str] = Query(None, description="Comma-separated ISO codes, e.g. UAH,EUR"),
        has_receipt: Optional[bool] = Query(None),
) -> SearchFilters:
    """Query-string → SearchFilters; shared with the CSV export."""
    if amount_min is not None and amount_max is not None and amount_min > amount_max:
        raise HTTPException(status_code=422, detail="amount_min must not exceed amount_max")
    return SearchFilters(
        q=q,
        kind=parse_kind_query(kind),
        category=category,
        tags=[t.strip().lower() for t in (tags or "").split(",") if t.strip()],
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
        currencies=parse_currencies(currency),
        has_receipt=has_receipt,
    )


@transaction_router.get("/search", response_model=TransactionSearchOut, summary="Search with filters + totals")
async def search(
        filters: SearchFilters = Depends(search_filters),
        limit: int = Query(50, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        session: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    hits = await search_transactions(session, current_user, filters)
    rates = await get_rates_map(session)
    page = hits[offset:offset + limit]
    return {
        "items": [
            {**TransactionOut.model_validate(h.tx).model_dump(), "has_receipt": h.has_receipt}
            for h in page
        ],
        "total": len(hits),
        "totals": search_totals(hits, current_user, rates),
    }


@transaction_router.patch("/{tx_id}", response_model=TransactionOut, status_code=status.HTTP_200_OK)
async def update_transaction(
        tx_id: int,
        payload: TransactionUpdate,
        session: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    tx = await _get_user_tx_or_404(session, tx_id, current_user.id_)

    data = payload.model_dump(exclude_unset=True)
    if not data:
        return tx

    if "kind" in data and data["kind"] is not None:
        try:
            data["kind"] = TransactionKind(data["kind"])
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid 'kind' value")

    new_kind = data.get("kind", tx.kind)
    new_category = data.get("category_name", tx.category_name)
    if new_category:
        _validate_category(new_kind, new_category)
        data["category_name"] = new_category.strip().lower()

    if "tags" in data and data["tags"] is not None:
        data["tags"] = [t.strip().lower() for t in data["tags"] if t.strip()]

    if "currency" in data and data["currency"]:
        data["currency"] = data["currency"].strip().upper()

    # Keep user's capital in sync: revert the old effect, apply the new one
    # (history imported without touching the balance never affects it)
    affects_capital = tx.counts_in_balance and {"amount", "kind", "currency"} & data.keys()
    if affects_capital:
        old_val = await convert_to_user_currency(
            session, current_user.default_currency, tx.kind, tx.amount, tx.currency or current_user.default_currency
        )

    for field, value in data.items():
        setattr(tx, field, value)

    if affects_capital:
        new_val = await convert_to_user_currency(
            session, current_user.default_currency, tx.kind, tx.amount, tx.currency or current_user.default_currency
        )
        current_user.capital = round(float(current_user.capital) - float(old_val) + float(new_val), 2)

    await session.commit()
    await session.refresh(tx)
    return tx


@transaction_router.get("/{tx_id}", response_model=TransactionOut, status_code=status.HTTP_200_OK)
async def get_transaction_by_id(
        tx_id: int,
        session: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    return await _get_user_tx_or_404(session, tx_id, current_user.id_)


@transaction_router.delete("/{tx_id}", response_model=TransactionDeletedOut, status_code=status.HTTP_200_OK)
async def delete_transaction(
        tx_id: int,
        session: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Moves the transaction to the trash (restorable for 30 days, see `/trash`)."""
    tx = await _get_user_tx_or_404(session, tx_id, current_user.id_)
    out = TransactionOut.model_validate(tx).model_dump()
    item = await move_to_trash(session, current_user, tx)
    await session.commit()
    await session.refresh(current_user)
    return {
        **out,
        "message": "Transaction moved to trash",
        "new_capital": current_user.capital,
        "trash_id": item.id_,
        "expires_at": item.expires_at,
    }


@transaction_router.get("", response_model=List[TransactionOut], status_code=status.HTTP_200_OK)
async def list_my_transactions(
        limit: int = Query(50, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        kind: Optional[str] = Query(None, description="Filter by kind: EXPENSE / INCOME / TRANSFER (or 0 / 1 / 2)"),
        category: Optional[str] = Query(None, description="Filter by category_name (case-insensitive)"),
        tags: Optional[str] = Query(None, description="Comma-separated tags; returns transactions that have ALL listed tags"),
        date_from: Optional[datetime] = Query(None),
        date_to: Optional[datetime] = Query(None),
        session: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    stmt = (
        select(Transaction)
        .where(Transaction.user_id == current_user.id_)
    )

    kind_value = parse_kind_query(kind)
    if kind_value is not None:
        stmt = stmt.where(Transaction.kind == kind_value)

    if category:
        stmt = stmt.where(Transaction.category_name == category.strip().lower())

    if date_from:
        stmt = stmt.where(Transaction.date >= date_from)

    if date_to:
        stmt = stmt.where(Transaction.date <= date_to)

    if tags:
        for tag in [t.strip().lower() for t in tags.split(",") if t.strip()]:
            stmt = stmt.where(Transaction.tags.contains([tag]))

    stmt = stmt.order_by(Transaction.date.desc(), Transaction.id_.desc()).offset(offset).limit(limit)

    result = await session.execute(stmt)
    return result.scalars().all()


@transaction_router.get("/categories/list", status_code=status.HTTP_200_OK)
async def get_allowed_categories():
    """Returns the full set of valid category names grouped by transaction kind."""
    return {
        "expense": sorted(ALLOWED_EXPENSE_CATEGORIES),
        "income": sorted(ALLOWED_INCOME_CATEGORIES),
        "transfer": sorted(ALLOWED_TRANSFER_CATEGORIES),
    }
