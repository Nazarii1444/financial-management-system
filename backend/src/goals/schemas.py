from decimal import Decimal
from typing import Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


class GoalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    target_amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    description: Optional[str] = Field(default=None, max_length=512)
    deadline: Optional[datetime] = None


class GoalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    target_amount: Optional[Decimal] = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    description: Optional[str] = Field(default=None, max_length=512)
    deadline: Optional[datetime] = None


class GoalDepositWithdraw(BaseModel):
    """Used for both /deposit and /withdraw endpoints."""
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_: int
    user_id: int
    name: str
    target_amount: Decimal
    saved_amount: Decimal
    currency: str
    description: Optional[str] = None
    deadline: Optional[datetime] = None
    is_completed: bool
    completed_at: Optional[datetime] = None
    created_at: datetime

    @computed_field  # type: ignore[misc]
    @property
    def progress_percent(self) -> float:
        if not self.target_amount or self.target_amount <= 0:
            return 0.0
        return round(min(float(self.saved_amount) / float(self.target_amount) * 100, 100.0), 1)
