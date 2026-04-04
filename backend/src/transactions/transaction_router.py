from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from fastapi.exceptions import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.dependencies import get_current_user
from src.models import Transaction, TransactionKind, User
from src.transactions.schemas import TransactionOut, TransactionCreate, TransactionUpdate
from src.transactions.currency_converter import convert_to_user_currency

# ── Category lists ──────────────────────────────────────────────────────────

ALLOWED_EXPENSE_CATEGORIES = {
    "shopping", "food", "phone", "entertainment", "education",
    "beauty", "sports", "social", "transportation", "clothing",
    "car", "alcohol", "cigarettes", "electronics", "travel",
    "health", "pets", "repairs", "housing", "home", "gifts",
    "donations", "lottery", "kids", "utilities",
}

ALLOWED_INCOME_CATEGORIES = {
    "salary", "freelance", "investment", "gift", "bonus",
    "rental", "interest", "dividend", "business", "other",
}

ALLOWED_TRANSFER_CATEGORIES = {"transfer", "other"}

ALL_CATEGORIES = ALLOWED_EXPENSE_CATEGORIES | ALLOWED_INCOME_CATEGORIES | ALLOWED_TRANSFER_CATEGORIES


def _validate_category(kind: TransactionKind, category_name: str) -> None:
    cat = category_name.strip().lower()
    if kind == TransactionKind.EXPENSE and cat not in ALLOWED_EXPENSE_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown expense category '{category_name}'. Allowed: {sorted(ALLOWED_EXPENSE_CATEGORIES)}",
        )
    if kind == TransactionKind.INCOME and cat not in ALLOWED_INCOME_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown income category '{category_name}'. Allowed: {sorted(ALLOWED_INCOME_CATEGORIES)}",
        )


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
    _validate_category(payload.kind, payload.category_name)

    currency = (payload.currency or current_user.default_currency).strip().upper()

    values = {
        "user_id": current_user.id_,
        "name": payload.name,
        "amount": payload.amount,
        "kind": payload.kind,
        "category_name": payload.category_name.strip().lower(),
        "currency": currency,
        "tags": [t.strip().lower() for t in payload.tags if t.strip()],
        "note": payload.note,
    }
    if payload.date is not None:
        values["date"] = payload.date

    val = await convert_to_user_currency(session, current_user.default_currency, payload.kind, payload.amount, currency)
    current_user.capital = round(float(current_user.capital) + float(val), 2)

    tx = Transaction(**values)
    session.add(tx)
    await session.commit()
    await session.refresh(tx)
    await session.refresh(current_user)
    return {
        "id_": tx.id_,
        "name": tx.name,
        "amount": tx.amount,
        "kind": tx.kind,
        "category_name": tx.category_name,
        "currency": tx.currency,
        "date": tx.date,
        "tags": tx.tags or [],
        "note": tx.note,
        "new_capital": current_user.capital,
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

    for field, value in data.items():
        setattr(tx, field, value)

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


@transaction_router.delete("/{tx_id}", status_code=status.HTTP_200_OK)
async def delete_transaction(
        tx_id: int,
        session: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    tx = await _get_user_tx_or_404(session, tx_id, current_user.id_)

    val = await convert_to_user_currency(session, current_user.default_currency, tx.kind, tx.amount, tx.currency)
    current_user.capital = round(float(current_user.capital) - float(val), 2)

    await session.delete(tx)
    await session.commit()
    await session.refresh(current_user)
    return {
        "message": "Transaction has been deleted",
        "id_": tx.id_,
        "amount": tx.amount,
        "name": tx.name,
        "kind": tx.kind,
        "category_name": tx.category_name,
        "currency": tx.currency,
        "date": tx.date,
        "tags": tx.tags or [],
        "note": tx.note,
        "new_capital": current_user.capital,
    }


@transaction_router.get("", response_model=List[TransactionOut], status_code=status.HTTP_200_OK)
async def list_my_transactions(
        limit: int = Query(50, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        kind: Optional[TransactionKind] = Query(None, description="Filter by kind: EXPENSE / INCOME / TRANSFER"),
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

    if kind is not None:
        stmt = stmt.where(Transaction.kind == kind)

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
