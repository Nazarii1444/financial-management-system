"""
Template → Transaction.

`use_template` goes through `create_user_transaction` (the same path as
`POST /api/transactions`), so category validation, currency conversion and
the `User.capital` update are identical to a manually entered transaction.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Currencies, Transaction, TransactionTemplate, User
from src.transactions.schemas import TransactionCreate
from src.transactions.services.transaction_service import create_user_transaction

_SUPPORTED_CURRENCIES = {c.value for c in Currencies}


def normalize_currency(currency: Optional[str], user: User) -> str:
    code = (currency or user.default_currency).strip().upper()
    if code not in _SUPPORTED_CURRENCIES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported currency '{code}'. Allowed: {sorted(_SUPPORTED_CURRENCIES)}",
        )
    return code


def normalize_tags(tags) -> list:
    return [t.strip().lower() for t in tags if t.strip()]


async def use_template(
        session: AsyncSession,
        user: User,
        template: TransactionTemplate,
        amount: Optional[Decimal] = None,
        now: Optional[datetime] = None,
        remember_amount: bool = False,
) -> Transaction:
    """
    Create a transaction from *template* dated *now* (default: current UTC time),
    optionally with an overridden *amount* (kept in the template when
    *remember_amount*). Flushes but does not commit.
    """
    now = now or datetime.now(timezone.utc)
    payload = TransactionCreate(
        name=template.name,
        amount=template.amount if amount is None else amount,
        kind=template.kind,
        category_name=template.category_name,
        currency=template.currency,
        date=now,
        tags=list(template.tags or []),
        note=template.note,
    )
    tx = await create_user_transaction(session, user, payload)
    template.use_count = (template.use_count or 0) + 1
    template.last_used_at = now
    if remember_amount and amount is not None:
        template.amount = amount
    return tx
