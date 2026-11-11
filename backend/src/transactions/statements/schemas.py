from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from src.models import TransactionKind
from src.transactions.schemas import Money


class StatementPreviewRow(BaseModel):
    ref: Optional[str]                 # fingerprint for dedupe; send back unchanged
    date: Optional[datetime]
    name: str                          # suggested transaction name (≤ 64 chars)
    description: str                   # full text from the statement
    amount: Decimal                    # positive; direction is in `kind`
    currency: str
    kind: TransactionKind
    category_name: str                 # suggested from MCC / description
    note: Optional[str] = None
    tags: List[str] = []
    mcc: Optional[str] = None
    balance_after: Optional[Decimal] = None
    duplicate: bool = False            # already imported earlier
    similar: bool = False              # a manual transaction with the same day / amount exists
    selected: bool = True              # suggested default for the checkbox


class StatementPreviewOut(BaseModel):
    bank: str                          # monobank | generic
    bank_name: str
    file_format: str
    currency: Optional[str]
    period_from: Optional[date]
    period_to: Optional[date]
    opening_balance: Optional[Decimal]
    closing_balance: Optional[Decimal]
    rows: List[StatementPreviewRow]
    warnings: List[str] = []


class StatementImportRow(BaseModel):
    ref: Optional[str] = Field(default=None, max_length=64)
    date: datetime
    name: str = Field(min_length=1, max_length=64)
    amount: Money
    currency: Optional[str] = Field(default=None, max_length=3)
    kind: TransactionKind
    category_name: str = Field(min_length=1, max_length=64)
    note: Optional[str] = Field(default=None, max_length=512)
    tags: List[str] = []


class StatementImportIn(BaseModel):
    bank: str = Field(default="generic", max_length=32)
    update_balance: bool = False       # False: history only, balance stays as is
    rows: List[StatementImportRow]


class StatementImportOut(BaseModel):
    imported: int
    skipped_duplicates: int
    errors: List[str]
    new_capital: float
