"""
Statement import: preview (parse + classify + dedupe, no writes) and confirm.

The flow is stateless: `preview` returns rows with a suggested kind /
category / name and flags; the client may edit them and sends the chosen rows
back to `confirm`, which re-checks duplicates and creates the transactions.

Balance: with `update_balance=False` (the default) rows are stored with
`counts_in_balance=False`, so importing history never moves `User.capital`
— and deleting / editing / restoring those rows later doesn't either.
"""
import hashlib
from datetime import timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Currencies, Transaction, TransactionKind, User
from src.transactions.categories import validate_category
from src.transactions.schemas import TransactionCreate
from src.transactions.services.transaction_service import create_user_transaction
from src.transactions.statements.base import ParsedStatement, StatementRow, row_ref
from src.transactions.statements.mcc import classify

MAX_ROWS = 5000
_SUPPORTED_CURRENCIES = {c.value for c in Currencies}


def _fmt(value: Decimal) -> str:
    return f"{abs(value):.2f}"


def build_note(row: StatementRow) -> Optional[str]:
    parts = []
    if row.operation_currency and row.operation_currency != row.currency and row.operation_amount is not None:
        rate = f" за курсом {row.rate}" if row.rate else ""
        parts.append(f"{_fmt(row.operation_amount)} {row.operation_currency}{rate}")
    if row.commission:
        parts.append(f"комісія {_fmt(row.commission)} {row.currency}")
    if row.cashback:
        parts.append(f"кешбек {_fmt(row.cashback)} {row.currency}")
    if row.mcc:
        parts.append(f"MCC {row.mcc}")
    return "; ".join(parts) or None


def preview_rows(statement: ParsedStatement) -> List[dict]:
    rows = []
    for row in statement.rows[:MAX_ROWS]:
        kind, category = classify(-1 if row.amount < 0 else 1, row.mcc, row.description)
        rows.append({
            "ref": row_ref(statement.bank, row),
            "date": row.date,
            "name": row.description[:64],
            "description": row.description,
            "amount": abs(row.amount),
            "currency": row.currency,
            "kind": kind,
            "category_name": category,
            "note": build_note(row),
            "mcc": row.mcc,
            "balance_after": row.balance_after,
        })
    return rows


def generic_preview_rows(valid_rows: List[dict], default_currency: str) -> List[dict]:
    """Rows of the app's own CSV / XLSX format (see import_router) → preview rows."""
    rows = []
    for r in valid_rows[:MAX_ROWS]:
        key = "|".join(["generic", r["date"].isoformat() if r["date"] else "", f"{r['amount']:.2f}",
                        r["name"].casefold(), r["kind"].name])
        rows.append({
            "ref": hashlib.sha256(key.encode()).hexdigest()[:40] if r["date"] else None,
            "date": r["date"],
            "name": r["name"],
            "description": r["name"],
            "amount": r["amount"],
            "currency": (r["currency"] or default_currency).upper(),
            "kind": r["kind"],
            "category_name": r["category_name"],
            "note": r["note"],
            "tags": r["tags"],
            "mcc": None,
            "balance_after": None,
        })
    return rows


async def flag_existing(session: AsyncSession, user: User, rows: List[dict]) -> None:
    """
    duplicate — this exact row was imported before (same `import_ref`);
    similar   — a manually entered transaction with the same day, amount and kind
                exists (e.g. the coffee already added by hand). Both start unselected.
    """
    refs = [r["ref"] for r in rows if r["ref"]]
    existing_refs = set()
    if refs:
        existing_refs = set((await session.execute(
            select(Transaction.import_ref).where(Transaction.user_id == user.id_, Transaction.import_ref.in_(refs))
        )).scalars().all())

    dated = [r["date"] for r in rows if r["date"]]
    manual: Dict[tuple, int] = {}
    if dated:
        txs = (await session.execute(
            select(Transaction).where(
                Transaction.user_id == user.id_,
                Transaction.import_ref.is_(None),
                Transaction.date >= min(dated) - timedelta(days=1),
                Transaction.date <= max(dated) + timedelta(days=1),
            )
        )).scalars().all()
        for tx in txs:
            key = (tx.date.date(), f"{Decimal(str(tx.amount)):.2f}", tx.kind)
            manual[key] = manual.get(key, 0) + 1

    for r in rows:
        r["duplicate"] = bool(r["ref"]) and r["ref"] in existing_refs
        key = (r["date"].date(), f"{r['amount']:.2f}", r["kind"]) if r["date"] else None
        r["similar"] = not r["duplicate"] and key is not None and manual.get(key, 0) > 0
        r["selected"] = not r["duplicate"] and not r["similar"]


async def confirm_import(session: AsyncSession, user: User, bank: str, rows: List, update_balance: bool) -> dict:
    """Create the chosen rows. Flushes; the caller commits."""
    if len(rows) > MAX_ROWS:
        raise HTTPException(status_code=422, detail=f"Too many rows (max {MAX_ROWS})")

    refs = [r.ref for r in rows if r.ref]
    taken = set()
    if refs:
        taken = set((await session.execute(
            select(Transaction.import_ref).where(Transaction.user_id == user.id_, Transaction.import_ref.in_(refs))
        )).scalars().all())

    bank_tag = "".join(ch for ch in (bank or "").lower() if ch.isalnum())[:32]
    created, skipped, errors = 0, 0, []
    seen = set()
    for i, row in enumerate(rows, start=1):
        if row.ref and (row.ref in taken or row.ref in seen):
            skipped += 1
            continue
        currency = (row.currency or user.default_currency).strip().upper()
        if currency not in _SUPPORTED_CURRENCIES:
            errors.append(f"Row {i}: unsupported currency {currency}")
            continue
        try:
            validate_category(row.kind, row.category_name)
        except HTTPException as exc:
            errors.append(f"Row {i}: {exc.detail}")
            continue
        tags = sorted({t.strip().lower() for t in [*(row.tags or []), "import", bank_tag] if t and t.strip()})

        if update_balance:
            try:
                tx = await create_user_transaction(session, user, TransactionCreate(
                    name=row.name, amount=row.amount, kind=row.kind, category_name=row.category_name,
                    currency=currency, date=row.date, tags=tags, note=row.note,
                ))
            except HTTPException as exc:   # e.g. no exchange rate for the currency
                errors.append(f"Row {i}: {exc.detail}")
                continue
        else:
            tx = Transaction(
                user_id=user.id_, name=row.name, amount=row.amount, kind=row.kind,
                category_name=row.category_name.strip().lower(), currency=currency, date=row.date,
                tags=tags, note=row.note, counts_in_balance=False,
            )
            session.add(tx)
        tx.import_ref = row.ref
        if row.ref:
            seen.add(row.ref)
        created += 1

    await session.flush()
    return {"imported": created, "skipped_duplicates": skipped, "errors": errors}
