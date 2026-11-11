"""
Transaction trash: delete → restorable snapshot → purge after 30 days.

`move_to_trash` / `restore_from_trash` flush but don't commit (the caller owns
the unit of work), like `create_user_transaction`.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Receipt, Transaction, TransactionKind, TransactionTrash, User
from src.transactions.currency_converter import convert_to_user_currency, get_rates_map

RETENTION_DAYS = 30
_CENT = Decimal("0.01")


def snapshot(tx: Transaction) -> dict:
    return {
        "name": tx.name,
        "amount": str(tx.amount),
        "kind": tx.kind.name,
        "category_name": tx.category_name,
        "currency": tx.currency,
        "tags": list(tx.tags or []),
        "note": tx.note,
        "date": tx.date.isoformat() if tx.date else None,
        "import_ref": tx.import_ref,
        "counts_in_balance": tx.counts_in_balance is not False,
    }


def from_snapshot(item: TransactionTrash) -> Transaction:
    data = item.data
    return Transaction(
        id_=item.transaction_id,
        user_id=item.user_id,
        name=data["name"],
        amount=Decimal(data["amount"]),
        kind=TransactionKind[data["kind"]],
        category_name=data["category_name"],
        currency=data.get("currency"),
        tags=list(data.get("tags") or []),
        note=data.get("note"),
        date=datetime.fromisoformat(data["date"]) if data.get("date") else None,
        import_ref=data.get("import_ref"),
        counts_in_balance=data.get("counts_in_balance", True),
    )


def trash_view(item: TransactionTrash) -> dict:
    """Shape for `TrashItemOut`: the transaction fields + trash metadata."""
    data = item.data
    return {
        "id_": item.id_,
        "transaction_id": item.transaction_id,
        "name": data["name"],
        "amount": Decimal(data["amount"]),
        "kind": TransactionKind[data["kind"]],
        "category_name": data["category_name"],
        "currency": data.get("currency"),
        "date": data.get("date"),
        "tags": data.get("tags") or [],
        "note": data.get("note"),
        "has_receipt": bool(item.receipt_ids),
        "deleted_at": item.deleted_at,
        "expires_at": item.expires_at,
    }


async def move_to_trash(session: AsyncSession, user: User, tx: Transaction, now: Optional[datetime] = None) -> TransactionTrash:
    """Revert the transaction's effect on capital, snapshot it and delete the row."""
    now = now or datetime.now(timezone.utc)
    if tx.counts_in_balance is False:
        effect = Decimal("0.00")      # imported history: never touched the balance
    else:
        try:
            effect = await convert_to_user_currency(session, user.default_currency, tx.kind, tx.amount, tx.currency or user.default_currency)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        effect = Decimal(str(effect)).quantize(_CENT, rounding=ROUND_HALF_UP)

    receipt_ids = (await session.execute(
        select(Receipt.id_).where(Receipt.transaction_id == tx.id_, Receipt.user_id == user.id_)
    )).scalars().all()

    item = TransactionTrash(
        user_id=user.id_,
        transaction_id=tx.id_,
        data=snapshot(tx),
        receipt_ids=list(receipt_ids),
        capital_effect=effect,
        capital_currency=user.default_currency.upper(),
        deleted_at=now,
        expires_at=now + timedelta(days=RETENTION_DAYS),
    )
    user.capital = round(float(Decimal(str(user.capital)) - effect), 2)
    session.add(item)
    await session.delete(tx)
    await session.flush()
    return item


async def _effect_in_current_currency(session: AsyncSession, user: User, item: TransactionTrash) -> Decimal:
    """The stored effect as-is; converted only if the user changed their default currency since."""
    effect = Decimal(str(item.capital_effect))
    src, dst = item.capital_currency.upper(), user.default_currency.upper()
    if src == dst:
        return effect
    rates = await get_rates_map(session)
    if src not in rates or dst not in rates:
        raise HTTPException(status_code=422, detail=f"Rate for '{src}' or '{dst}' not found")
    return (effect / Decimal(str(rates[src])) * Decimal(str(rates[dst]))).quantize(_CENT, rounding=ROUND_HALF_UP)


async def restore_from_trash(session: AsyncSession, user: User, item: TransactionTrash) -> Transaction:
    if await session.get(Transaction, item.transaction_id) is not None:
        raise HTTPException(status_code=409, detail="Transaction already exists")
    effect = await _effect_in_current_currency(session, user, item)

    tx = from_snapshot(item)
    session.add(tx)
    await session.flush()  # the row must exist before receipts point at it
    user.capital = round(float(Decimal(str(user.capital)) + effect), 2)

    if item.receipt_ids:
        receipts = (await session.execute(
            select(Receipt).where(
                Receipt.id_.in_(item.receipt_ids),
                Receipt.user_id == user.id_,
                Receipt.transaction_id.is_(None),
            )
        )).scalars().all()
        for receipt in receipts:
            receipt.transaction_id = tx.id_

    await session.delete(item)
    await session.flush()
    return tx


async def purge_expired(session: AsyncSession, now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc)
    result = await session.execute(delete(TransactionTrash).where(TransactionTrash.expires_at < now))
    return result.rowcount or 0
