from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from src.models import BudgetRole, BudgetType


class BudgetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    type: BudgetType
    currency: str = Field(default="USD", min_length=3, max_length=3)
    limit_amount: Optional[Decimal] = Field(default=None, gt=0, description="Optional spending cap")


class BudgetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    limit_amount: Optional[Decimal] = Field(default=None, gt=0)


class BudgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_: int
    owner_user_id: int
    name: str
    type: BudgetType
    currency: str
    limit_amount: Optional[Decimal] = None


class BudgetMemberCreate(BaseModel):
    """Identify the new member either by user_id or by email."""
    user_id: Optional[int] = None
    email: Optional[EmailStr] = None
    role: BudgetRole

    @model_validator(mode="after")
    def _user_or_email(self):
        if self.user_id is None and self.email is None:
            raise ValueError("Either user_id or email is required")
        return self


class BudgetMemberRoleUpdate(BaseModel):
    role: BudgetRole


class BudgetMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_: int
    budget_id: int
    user_id: int
    role: BudgetRole
    username: Optional[str] = None
    email: Optional[str] = None

