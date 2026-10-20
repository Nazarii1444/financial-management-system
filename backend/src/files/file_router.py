"""
File / Receipt router  —  /api/files/*

Endpoints
---------
  POST   /receipts                  upload file → OCR → store → transaction draft
                                    (?auto_create=true also creates the transaction)
  GET    /receipts                  list user's receipts
  GET    /receipts/{id}             receipt metadata + OCR result
  GET    /receipts/{id}/draft       transaction draft parsed from the OCR text
  POST   /receipts/{id}/rescan      re-run OCR on the stored file
  POST   /receipts/{id}/transaction confirm (optionally edited) draft → transaction + link
  GET    /receipts/{id}/download    stream the actual file
  PATCH  /receipts/{id}/link        link/unlink to a transaction
  DELETE /receipts/{id}             delete receipt + file on disk

Scan flow: upload → client shows `draft` for review → user confirms with `{}`
(one click) or sends only the edited fields to POST /receipts/{id}/transaction.
"""
import asyncio
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import MAX_UPLOAD_SIZE_MB, UPLOAD_DIR, logger
from src.database import get_db
from src.dependencies import get_current_user
from src.files.schemas import (
    ReceiptLinkRequest,
    ReceiptOut,
    ReceiptScanOut,
    ReceiptTransactionCreate,
    ReceiptTransactionOut,
    TransactionDraft,
)
from src.files.services import ocr_service
from src.files.services.receipt_transaction_service import build_draft, create_transaction_from_receipt
from src.files.services.storage_service import LocalStorageService
from src.models import Receipt, Transaction, User
from src.transactions.schemas import TransactionOut
from src.transactions.services.transaction_service import transaction_to_out

file_router = APIRouter()

_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "application/pdf",
}
_MAX_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# Single shared storage instance (swap to S3Service here if needed)
_storage = LocalStorageService(UPLOAD_DIR)


# ── Guard ─────────────────────────────────────────────────────────────────────

async def _get_user_receipt_or_404(session: AsyncSession, receipt_id: int, user_id: int) -> Receipt:
    stmt = select(Receipt).where(Receipt.id_ == receipt_id, Receipt.user_id == user_id)
    receipt = (await session.execute(stmt)).scalar_one_or_none()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt


def _scan_out(receipt: Receipt, user: User, tx: Optional[Transaction] = None) -> ReceiptScanOut:
    return ReceiptScanOut(
        **ReceiptOut.model_validate(receipt).model_dump(),
        draft=build_draft(receipt, user),
        transaction=TransactionOut(**transaction_to_out(tx, user)) if tx else None,
    )


# ── Upload ────────────────────────────────────────────────────────────────────

@file_router.post(
    "/receipts",
    response_model=ReceiptScanOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a receipt image or PDF, run OCR and return a transaction draft",
)
async def upload_receipt(
    file: UploadFile = File(..., description="JPEG, PNG, WEBP, GIF or PDF — max 20 MB"),
    auto_create: bool = Query(
        False,
        description="Create the transaction right away when the total was detected. "
                    "Default: only return the draft for the user to confirm.",
    ),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ── Validate content type ─────────────────────────────────────────────────
    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{content_type}'. "
                   f"Allowed: {sorted(_ALLOWED_CONTENT_TYPES)}",
        )

    # ── Read + size guard ─────────────────────────────────────────────────────
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(data) // 1024} KB). Max {MAX_UPLOAD_SIZE_MB} MB.",
        )

    # ── Persist file ──────────────────────────────────────────────────────────
    stored_filename, file_path = await _storage.save(
        current_user.id_, file.filename or "upload", data
    )

    # ── OCR (run in thread-pool so it doesn't block the event loop) ───────────
    ocr_result = await asyncio.to_thread(ocr_service.analyse, data, content_type)
    logger.info(
        "Receipt uploaded: user=%s file=%s confidence=%s",
        current_user.id_, stored_filename, ocr_result.get("confidence"),
    )

    # ── Persist metadata ──────────────────────────────────────────────────────
    receipt = Receipt(
        user_id=current_user.id_,
        original_filename=file.filename or stored_filename,
        stored_filename=stored_filename,
        file_path=file_path,
        content_type=content_type,
        file_size=len(data),
        ocr_result=ocr_result,
    )
    session.add(receipt)
    await session.commit()
    await session.refresh(receipt)

    tx: Optional[Transaction] = None
    if auto_create and ocr_result.get("suggested_amount") is not None:
        try:
            tx = await create_transaction_from_receipt(
                session, current_user, receipt, ReceiptTransactionCreate()
            )
            await session.commit()
            await session.refresh(tx)
            await session.refresh(current_user)
            await session.refresh(receipt)
        except HTTPException as exc:
            # Keep the uploaded receipt; the user can still confirm the draft manually.
            await session.rollback()
            await session.refresh(receipt)
            tx = None
            logger.info("Receipt auto-create skipped: receipt=%s reason=%s", receipt.id_, exc.detail)

    return _scan_out(receipt, current_user, tx)


# ── List ──────────────────────────────────────────────────────────────────────

@file_router.get("/receipts", response_model=List[ReceiptOut])
async def list_receipts(
    transaction_id: Optional[int] = Query(None, description="Filter by linked transaction"),
    limit:  int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Receipt).where(Receipt.user_id == current_user.id_)
    if transaction_id is not None:
        stmt = stmt.where(Receipt.transaction_id == transaction_id)
    stmt = stmt.order_by(Receipt.created_at.desc()).offset(offset).limit(limit)
    return (await session.execute(stmt)).scalars().all()


# ── Get one ───────────────────────────────────────────────────────────────────

@file_router.get("/receipts/{receipt_id}", response_model=ReceiptOut)
async def get_receipt(
    receipt_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _get_user_receipt_or_404(session, receipt_id, current_user.id_)


# ── Draft ─────────────────────────────────────────────────────────────────────

@file_router.get(
    "/receipts/{receipt_id}/draft",
    response_model=TransactionDraft,
    summary="Transaction draft parsed from the receipt's OCR text",
)
async def get_receipt_draft(
    receipt_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    receipt = await _get_user_receipt_or_404(session, receipt_id, current_user.id_)
    return build_draft(receipt, current_user)


# ── Rescan ────────────────────────────────────────────────────────────────────

@file_router.post(
    "/receipts/{receipt_id}/rescan",
    response_model=ReceiptScanOut,
    summary="Re-run OCR on the stored file (e.g. after installing Tesseract language packs)",
)
async def rescan_receipt(
    receipt_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    receipt = await _get_user_receipt_or_404(session, receipt_id, current_user.id_)
    try:
        data = await _storage.read(receipt.file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found on disk")

    receipt.ocr_result = await asyncio.to_thread(ocr_service.analyse, data, receipt.content_type)
    await session.commit()
    await session.refresh(receipt)
    return _scan_out(receipt, current_user)


# ── Confirm draft → transaction ───────────────────────────────────────────────

@file_router.post(
    "/receipts/{receipt_id}/transaction",
    response_model=ReceiptTransactionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a transaction from the receipt draft and link it",
)
async def create_receipt_transaction(
    receipt_id: int,
    payload: ReceiptTransactionCreate = Body(default_factory=ReceiptTransactionCreate),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Send `{}` (or no body) to accept the draft as-is, or only the fields the
    user changed — they override the parsed values.
    409 if the receipt is already linked; 422 if no amount was detected or given.
    """
    receipt = await _get_user_receipt_or_404(session, receipt_id, current_user.id_)
    tx = await create_transaction_from_receipt(session, current_user, receipt, payload)
    await session.commit()
    await session.refresh(tx)
    await session.refresh(current_user)
    await session.refresh(receipt)
    return ReceiptTransactionOut(
        receipt=ReceiptOut.model_validate(receipt),
        transaction=TransactionOut(**transaction_to_out(tx, current_user)),
    )


# ── Download ──────────────────────────────────────────────────────────────────

@file_router.get("/receipts/{receipt_id}/download", summary="Stream the raw file")
async def download_receipt(
    receipt_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    receipt = await _get_user_receipt_or_404(session, receipt_id, current_user.id_)
    abs_path = _storage.absolute_path(receipt.file_path)

    import os
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=abs_path,
        media_type=receipt.content_type,
        filename=receipt.original_filename,
    )


# ── Link / unlink to transaction ──────────────────────────────────────────────

@file_router.patch("/receipts/{receipt_id}/link", response_model=ReceiptOut)
async def link_receipt(
    receipt_id: int,
    payload: ReceiptLinkRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Link receipt to a transaction (or pass transaction_id=null to unlink).
    The transaction must belong to the same user.
    """
    receipt = await _get_user_receipt_or_404(session, receipt_id, current_user.id_)

    if payload.transaction_id is not None:
        tx = (
            await session.execute(
                select(Transaction).where(
                    Transaction.id_ == payload.transaction_id,
                    Transaction.user_id == current_user.id_,
                )
            )
        ).scalar_one_or_none()
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found")

    receipt.transaction_id = payload.transaction_id
    await session.commit()
    await session.refresh(receipt)
    return receipt


# ── Delete ────────────────────────────────────────────────────────────────────

@file_router.delete("/receipts/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_receipt(
    receipt_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    receipt = await _get_user_receipt_or_404(session, receipt_id, current_user.id_)
    await _storage.delete(receipt.file_path)
    await session.delete(receipt)
    await session.commit()
    return None

