from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.models import TransactionKind
from src.transactions.schemas import Money, TransactionOut


class OcrResultOut(BaseModel):
    raw_text:           Optional[str]   = None
    ocr_passes:         List[Dict[str, Any]] = []
    qr_codes:           List[str]       = []
    ocr_quality:        Optional[float] = None
    amounts:            List[float]     = []
    suggested_amount:   Optional[float] = None
    amount_source:      Optional[str]   = None
    amount_confirmed:   bool            = False
    fiscal:             Optional[Dict[str, Optional[str]]] = None
    text_unreadable:    bool            = False
    retake_recommended: bool            = False
    suggested_currency: Optional[str]   = None
    suggested_date:     Optional[str]   = None
    suggested_category: Optional[str]   = None
    merchant:           Optional[str]   = None
    confidence:         str             = "none"
    confidence_score:   float           = 0.0
    field_confidence:   Dict[str, float] = {}
    parser_version:     Optional[int]   = None
    pipeline:           Optional[str]   = None   # opencv | pillow_fallback | qr_only | none | pdf_text


class ReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_:               int
    user_id:           int
    transaction_id:    Optional[int]     = None
    original_filename: str
    content_type:      str
    file_size:         int               # bytes
    ocr_result:        Optional[Dict[str, Any]] = None
    created_at:        datetime


class ReceiptLinkRequest(BaseModel):
    """Body for PATCH /receipts/{id}/link."""
    transaction_id: Optional[int] = None   # None → unlink


# ── Receipt → transaction ─────────────────────────────────────────────────────

class TransactionDraft(BaseModel):
    """
    Transaction pre-filled from the receipt's OCR text. The client shows it
    for review; confirming sends it (optionally edited) to
    POST /receipts/{id}/transaction.
    """
    amount:           Optional[Decimal]  = None      # None → OCR found no amount; user must enter it
    name:             str
    kind:             TransactionKind    = TransactionKind.EXPENSE
    category_name:    str
    currency:         str
    date:             Optional[datetime] = None      # None → server uses "now" on creation
    tags:             List[str]          = []
    note:             Optional[str]      = None
    merchant:         Optional[str]      = None
    confidence:       str                = "none"    # high | medium | low | none
    confidence_score: float              = 0.0
    field_confidence: Dict[str, float]   = {}        # amount / date / merchant / category → 0..1
    amount_source:    Optional[str]      = None      # "fiscal_qr" (exact, from the tax QR) | "ocr"
    is_complete:      bool               = False     # True → can be confirmed with an empty body
    retake_recommended: bool             = False     # no total found → suggest a clearer photo


class ReceiptTransactionCreate(BaseModel):
    """
    Body for POST /receipts/{id}/transaction. Every field is optional:
    send `{}` to accept the draft as-is, or only the fields the user edited.
    """
    amount:        Optional[Money]              = None
    name:          Optional[str]                = Field(default=None, min_length=1, max_length=64)
    kind:          Optional[TransactionKind]    = None
    category_name: Optional[str]                = Field(default=None, min_length=1, max_length=64)
    currency:      Optional[str]                = Field(default=None, max_length=16)
    date:          Optional[datetime]           = None
    tags:          Optional[List[str]]          = None
    note:          Optional[str]                = Field(default=None, max_length=512)


class ReceiptScanOut(ReceiptOut):
    """Receipt + the parsed transaction draft (+ the transaction if auto-created)."""
    draft:       TransactionDraft
    transaction: Optional[TransactionOut] = None


class ReceiptTransactionOut(BaseModel):
    receipt:     ReceiptOut
    transaction: TransactionOut
