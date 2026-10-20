from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from src.models import TransactionKind
from src.transactions.schemas import Money


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    amount: Money
    kind: TransactionKind = TransactionKind.EXPENSE
    category_name: str = Field(min_length=1, max_length=64)
    currency: Optional[str] = Field(default=None, max_length=16)  # None → user's default currency
    tags: List[str] = Field(default_factory=list)
    note: Optional[str] = Field(default=None, max_length=512)


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    amount: Optional[Money] = None
    kind: Optional[TransactionKind] = None
    category_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    currency: Optional[str] = Field(default=None, max_length=16)
    tags: Optional[List[str]] = None
    note: Optional[str] = Field(default=None, max_length=512)


class TemplateOut(BaseModel):
    id_: int
    name: str
    amount: Decimal
    kind: TransactionKind
    category_name: str
    currency: str
    tags: List[str] = []
    note: Optional[str] = None
    use_count: int
    last_used_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TemplateUse(BaseModel):
    """Body of `POST /{id}/use`; every field is optional (`{}` = use the template as-is)."""
    amount: Optional[Money] = None
    remember_amount: bool = False  # also store the overridden amount in the template


class TemplateSuggestionOut(BaseModel):
    key: str                     # similarity key; send it back to dismiss the suggestion
    name: str
    amount: Decimal              # proposed template amount (most common value or median)
    kind: TransactionKind
    category_name: str
    currency: str
    count: int                   # similar transactions in the window
    min_amount: Decimal
    max_amount: Decimal
    last_date: datetime


class TemplateSuggestionDismiss(BaseModel):
    key: str = Field(min_length=1, max_length=255)
