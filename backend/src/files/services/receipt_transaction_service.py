"""
Receipt → transaction
─────────────────────
  build_draft                     — OCR result → TransactionDraft for user review
  create_transaction_from_receipt — draft + user edits → Transaction, linked to the receipt
"""
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.files.schemas import ReceiptTransactionCreate, TransactionDraft
from src.files.services import ocr_service, receipt_parser
from src.models import Receipt, Transaction, User
from src.transactions.schemas import TransactionCreate
from src.transactions.services.transaction_service import create_user_transaction

DEFAULT_NAME = "Receipt"
RECEIPT_TAG = "receipt"

# Fields that may be explicitly cleared to null in the override body.
_NULLABLE_OVERRIDES = {"date", "note"}


def build_draft(receipt: Receipt, user: User) -> TransactionDraft:
    """
    Re-parse the stored raw OCR text (so receipts uploaded before a parser
    improvement benefit from it) and fill gaps with sensible defaults.
    """
    ocr = receipt.ocr_result or {}
    parsed = receipt_parser.parse_multi(
        ocr_service.stored_passes(ocr),
        reference=receipt.created_at,
        qr_codes=ocr.get("qr_codes") or (),
    )

    return TransactionDraft(
        amount=parsed.amount,
        name=(parsed.merchant or DEFAULT_NAME)[:64],
        category_name=parsed.category or receipt_parser.FALLBACK_CATEGORY,
        currency=parsed.currency or user.default_currency,
        date=parsed.date,
        tags=[RECEIPT_TAG],
        merchant=parsed.merchant,
        confidence=parsed.confidence_label,
        confidence_score=parsed.confidence_score,
        field_confidence=parsed.field_confidence,
        amount_source=parsed.amount_source,
        is_complete=parsed.amount is not None,
        retake_recommended=parsed.retake_recommended,
    )


async def create_transaction_from_receipt(
        session: AsyncSession,
        user: User,
        receipt: Receipt,
        overrides: ReceiptTransactionCreate,
) -> Transaction:
    """
    Merge the user's edits over the draft, create the transaction and link the
    receipt to it. Flushes but does not commit — the caller owns the unit of work.
    """
    if receipt.transaction_id is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Receipt is already linked to transaction {receipt.transaction_id}",
        )

    draft = build_draft(receipt, user)
    data = draft.model_dump(include=set(TransactionCreate.model_fields))
    data.update({
        k: v for k, v in overrides.model_dump(exclude_unset=True).items()
        if v is not None or k in _NULLABLE_OVERRIDES
    })

    if data.get("amount") is None:
        raise HTTPException(
            status_code=422,
            detail="Could not detect the total on this receipt — please provide 'amount'",
        )

    try:
        payload = TransactionCreate(**data)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors())

    tx = await create_user_transaction(session, user, payload)
    receipt.transaction_id = tx.id_
    return tx
