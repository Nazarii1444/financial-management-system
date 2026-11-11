"""
Shared transaction-creation logic.

Used by the manual `POST /api/transactions` endpoint and by receipt-driven
creation in `src/files/file_router.py`, so both paths validate categories,
convert currency and update `User.capital` identically.
"""
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Transaction, User
from src.transactions.categories import validate_category
from src.transactions.currency_converter import convert_to_user_currency
from src.transactions.schemas import TransactionCreate


async def create_user_transaction(
        session: AsyncSession,
        user: User,
        payload: TransactionCreate,
) -> Transaction:
    """
    Validate *payload*, add the transaction to the session and adjust the
    user's capital. Flushes (so `tx.id_` is set) but does **not** commit —
    the caller owns the unit of work.
    """
    validate_category(payload.kind, payload.category_name)

    currency = (payload.currency or user.default_currency).strip().upper()

    values = {
        "user_id": user.id_,
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

    try:
        val = await convert_to_user_currency(session, user.default_currency, payload.kind, payload.amount, currency)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    user.capital = round(float(user.capital) + float(val), 2)

    tx = Transaction(**values)
    session.add(tx)
    await session.flush()
    return tx


def transaction_to_out(tx: Transaction, user: User) -> dict:
    """Shape a freshly created transaction like `TransactionOut` (incl. new_capital)."""
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
        "new_capital": user.capital,
    }
