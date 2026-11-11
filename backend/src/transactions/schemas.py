from pydantic import BaseModel, Field, condecimal
from decimal import Decimal
from src.models import TransactionKind, RecurringFrequency
from typing import Optional, Union, List
from datetime import datetime


Money = condecimal(max_digits=14, decimal_places=2, ge=0)


class TransactionCreate(BaseModel):
    amount: Money
    name: str = Field(min_length=1, max_length=64)
    kind: TransactionKind = TransactionKind.EXPENSE
    category_name: str = Field(min_length=1, max_length=64)
    currency: Optional[str] = Field(default=None, max_length=16)
    date: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list)
    note: Optional[str] = Field(default=None, max_length=512)


class TransactionUpdate(BaseModel):
    amount: Optional[Money] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    kind: Optional[Union[int, TransactionKind]] = None
    category_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    currency: Optional[str] = Field(default=None, max_length=16)
    date: Optional[datetime] = None
    tags: Optional[List[str]] = None
    note: Optional[str] = Field(default=None, max_length=512)


class TransactionOut(BaseModel):
    id_: int
    name: str
    amount: Decimal      # fixed: was declared twice (Money then Decimal)
    kind: TransactionKind
    category_name: str
    currency: Optional[str]
    date: datetime
    tags: List[str] = []
    note: Optional[str] = None
    new_capital: Optional[float] = None

    class Config:
        from_attributes = True
        orm_mode = True


class TransactionSearchItem(TransactionOut):
    has_receipt: bool = False


class SearchTotals(BaseModel):
    expense: float      # in the user's default currency
    income: float
    net: float
    currency: str


class TransactionSearchOut(BaseModel):
    items: List[TransactionSearchItem]
    total: int          # matches before pagination
    totals: SearchTotals


class TrashItemOut(BaseModel):
    id_: int                       # trash entry id (use for restore / purge)
    transaction_id: int            # original transaction id (kept on restore)
    name: str
    amount: Decimal
    kind: TransactionKind
    category_name: str
    currency: Optional[str]
    date: Optional[datetime]
    tags: List[str] = []
    note: Optional[str] = None
    has_receipt: bool = False
    deleted_at: datetime
    expires_at: datetime


class TransactionDeletedOut(TransactionOut):
    message: str
    trash_id: int
    expires_at: datetime


# ── Recurring transactions ──────────────────────────────────────────────────

class RecurringTransactionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    amount: Money
    kind: TransactionKind = TransactionKind.EXPENSE
    category_name: str = Field(min_length=1, max_length=64)
    currency: Optional[str] = Field(default=None, max_length=16)
    tags: List[str] = Field(default_factory=list)
    note: Optional[str] = Field(default=None, max_length=512)
    frequency: RecurringFrequency
    first_run: datetime  # when to fire the first time (becomes next_run)


class RecurringTransactionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    amount: Optional[Money] = None
    kind: Optional[TransactionKind] = None
    category_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    currency: Optional[str] = Field(default=None, max_length=16)
    tags: Optional[List[str]] = None
    note: Optional[str] = Field(default=None, max_length=512)
    frequency: Optional[RecurringFrequency] = None
    next_run: Optional[datetime] = None
    is_active: Optional[bool] = None


class RecurringTransactionOut(BaseModel):
    id_: int
    user_id: int
    name: str
    amount: Decimal
    kind: TransactionKind
    category_name: str
    currency: Optional[str]
    tags: List[str] = []
    note: Optional[str] = None
    frequency: RecurringFrequency
    next_run: datetime
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
        orm_mode = True



# ── Query helpers ───────────────────────────────────────────────────────────

_KIND_ALIASES = {
    "0": TransactionKind.EXPENSE, "EXPENSE": TransactionKind.EXPENSE,
    "1": TransactionKind.INCOME, "INCOME": TransactionKind.INCOME,
    "2": TransactionKind.TRANSFER, "TRANSFER": TransactionKind.TRANSFER,
}


def parse_kind_query(raw: Optional[str]) -> Optional[TransactionKind]:
    """Parse ?kind= query param. Accepts 0/1/2 or EXPENSE/INCOME/TRANSFER (case-insensitive).

    FastAPI can't coerce a query string into an int-valued Enum, so the routers
    take a plain string and convert it here.
    """
    if raw is None or raw.strip() == "":
        return None
    kind = _KIND_ALIASES.get(raw.strip().upper())
    if kind is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Invalid 'kind' value. Use EXPENSE / INCOME / TRANSFER")
    return kind
