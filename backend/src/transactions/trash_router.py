"""
Trash — deleted transactions, restorable for 30 days.

`DELETE /api/transactions/{id}` moves a transaction here (see
`services/trash_service.py`). Restoring re-inserts it with the same id,
re-links its receipts and adds back the exact capital effect recorded at
deletion. A daily cron purges expired entries.
"""
from typing import List

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Response, status
from fastapi_utilities import repeat_every
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import logger
from src.database import AsyncSessionLocal, get_db
from src.dependencies import get_current_user
from src.models import TransactionTrash, User
from src.transactions.schemas import TransactionOut, TrashItemOut
from src.transactions.services.trash_service import purge_expired, restore_from_trash, trash_view
from src.transactions.services.transaction_service import transaction_to_out

trash_router = APIRouter()


async def _get_user_item_or_404(session: AsyncSession, item_id: int, user_id: int) -> TransactionTrash:
    item = (await session.execute(
        select(TransactionTrash).where(TransactionTrash.id_ == item_id, TransactionTrash.user_id == user_id)
    )).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Trash item not found")
    return item


@trash_router.get("", response_model=List[TrashItemOut])
async def list_trash(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await purge_expired(session)
    await session.commit()
    items = (await session.execute(
        select(TransactionTrash)
        .where(TransactionTrash.user_id == current_user.id_)
        .order_by(TransactionTrash.deleted_at.desc(), TransactionTrash.id_.desc())
    )).scalars().all()
    return [trash_view(item) for item in items]


@trash_router.post("/{item_id}/restore", response_model=TransactionOut)
async def restore(
    item_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await _get_user_item_or_404(session, item_id, current_user.id_)
    tx = await restore_from_trash(session, current_user, item)
    await session.commit()
    await session.refresh(tx)
    await session.refresh(current_user)
    return transaction_to_out(tx, current_user)


@trash_router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete permanently")
async def delete_forever(
    item_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await _get_user_item_or_404(session, item_id, current_user.id_)
    await session.delete(item)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@trash_router.delete("", status_code=status.HTTP_204_NO_CONTENT, summary="Empty the trash")
async def empty_trash(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await session.execute(delete(TransactionTrash).where(TransactionTrash.user_id == current_user.id_))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def register_trash_cron(app: FastAPI) -> None:
    @app.on_event("startup")
    @repeat_every(seconds=6 * 60 * 60, wait_first=False, logger=logger)
    async def _purge_trash() -> None:
        async with AsyncSessionLocal() as session:
            removed = await purge_expired(session)
            await session.commit()
            if removed:
                logger.info("Trash purge: %s expired transactions removed", removed)
