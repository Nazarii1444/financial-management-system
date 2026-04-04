from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class OcrResultOut(BaseModel):
    raw_text:           Optional[str]   = None
    amounts:            List[float]     = []
    suggested_amount:   Optional[float] = None
    suggested_category: Optional[str]   = None
    merchant:           Optional[str]   = None
    confidence:         str             = "none"


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

