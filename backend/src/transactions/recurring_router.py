"""
Recurring Transactions — CRUD + background cron.

Frequency ladder:  DAILY → WEEKLY → BIWEEKLY → MONTHLY → YEARLY
The cron runs every minute; if next_run <= now and is_active, a real
Transaction is created and next_run is advanced by one frequency step.
"""
from datetime import datetime, timezone, timedelta
from typing import List

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from fastapi_utilities import repeat_every
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import logger
from src.database import AsyncSessionLocal, get_db
from src.dependencies import get_current_user
from src.models import RecurringFrequency, RecurringTransaction, Transaction, User
from src.transactions.currency_converter import convert_to_user_currency
from src.transactions.schemas import (
    RecurringTransactionCreate,
    RecurringTransactionOut,
    RecurringTransactionUpdate,
)

recurring_router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _advance_next_run(current: datetime, frequency: RecurringFrequency) -> datetime:
    if frequency == RecurringFrequency.DAILY:
        return current + timedelta(days=1)
    if frequency == RecurringFrequency.WEEKLY:
        return current + timedelta(weeks=1)
    if frequency == RecurringFrequency.BIWEEKLY:
        return current + timedelta(weeks=2)
    if frequency == RecurringFrequency.MONTHLY:
        return current + relativedelta(months=1)
    if frequency == RecurringFrequency.YEARLY:
        return current + relativedelta(years=1)
    return current


async def _get_user_rt_or_404(session: AsyncSession, rt_id: int, user_id: int) -> RecurringTransaction:
    stmt = select(RecurringTransaction).where(
        RecurringTransaction.id_ == rt_id,
        RecurringTransaction.user_id == user_id,
    )
    rt = (await session.execute(stmt)).scalar_one_or_none()
    if not rt:
        raise HTTPException(status_code=404, detail="Recurring transaction not found")
    return rt


# ── CRUD ──────────────────────────────────────────────────────────────────────

@recurring_router.post("", response_model=RecurringTransactionOut, status_code=status.HTTP_201_CREATED)
async def create_recurring(
    payload: RecurringTransactionCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    currency = (payload.currency or current_user.default_currency).strip().upper()
    rt = RecurringTransaction(
        user_id=current_user.id_,
        name=payload.name,
        amount=payload.amount,
        kind=payload.kind,
        category_name=payload.category_name.strip().lower(),
        currency=currency,
        tags=[t.strip().lower() for t in payload.tags if t.strip()],
        note=payload.note,
        frequency=payload.frequency,
        next_run=payload.first_run,
        is_active=True,
    )
    session.add(rt)
    await session.commit()
    await session.refresh(rt)
    return rt


@recurring_router.get("", response_model=List[RecurringTransactionOut])
async def list_recurring(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    is_active: bool = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(RecurringTransaction).where(RecurringTransaction.user_id == current_user.id_)
    if is_active is not None:
        stmt = stmt.where(RecurringTransaction.is_active == is_active)
    stmt = stmt.order_by(RecurringTransaction.next_run.asc()).offset(offset).limit(limit)
    return (await session.execute(stmt)).scalars().all()


@recurring_router.get("/{rt_id}", response_model=RecurringTransactionOut)
async def get_recurring(
    rt_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _get_user_rt_or_404(session, rt_id, current_user.id_)


@recurring_router.patch("/{rt_id}", response_model=RecurringTransactionOut)
async def update_recurring(
    rt_id: int,
    payload: RecurringTransactionUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rt = await _get_user_rt_or_404(session, rt_id, current_user.id_)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return rt

    if "tags" in data and data["tags"] is not None:
        data["tags"] = [t.strip().lower() for t in data["tags"] if t.strip()]
    if "category_name" in data and data["category_name"]:
        data["category_name"] = data["category_name"].strip().lower()

    for field, value in data.items():
        setattr(rt, field, value)

    await session.commit()
    await session.refresh(rt)
    return rt


@recurring_router.delete("/{rt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring(
    rt_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rt = await _get_user_rt_or_404(session, rt_id, current_user.id_)
    await session.delete(rt)
    await session.commit()
    return None


# ── Cron: fire due recurring transactions every minute ───────────────────────

async def _fire_due_recurring() -> None:
    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)
        stmt = select(RecurringTransaction).where(
            RecurringTransaction.is_active.is_(True),
            RecurringTransaction.next_run <= now,
        )
        due: List[RecurringTransaction] = (await session.execute(stmt)).scalars().all()

        for rt in due:
            user = await session.get(User, rt.user_id)
            if not user:
                continue
            try:
                src_currency = (rt.currency or user.default_currency).strip().upper()
                val = await convert_to_user_currency(
                    session, user.default_currency, rt.kind, rt.amount, src_currency
                )
                user.capital = round(float(user.capital) + float(val), 2)

                tx = Transaction(
                    user_id=rt.user_id,
                    name=rt.name,
                    amount=rt.amount,
                    kind=rt.kind,
                    category_name=rt.category_name,
                    currency=rt.currency,
                    tags=rt.tags or [],
                    note=rt.note,
                    date=now,
                )
                session.add(tx)
                rt.next_run = _advance_next_run(now, rt.frequency)
                logger.info("Fired recurring tx id=%s for user_id=%s; next_run=%s", rt.id_, rt.user_id, rt.next_run)
            except Exception:
                logger.exception("Failed to fire recurring tx id=%s", rt.id_)

        if due:
            await session.commit()


def register_recurring_cron(app: FastAPI) -> None:
    @app.on_event("startup")
    @repeat_every(seconds=60, wait_first=False, logger=logger)
    async def _scheduled_recurring() -> None:
        await _fire_due_recurring()

