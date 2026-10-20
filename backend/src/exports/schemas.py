from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


class RecurringCostRow(BaseModel):
    id_: int
    name: str
    category: str
    frequency: str
    amount: Decimal
    currency: str
    per_month: Decimal       # in the user's default currency
    per_year: Decimal
    next_run: datetime
    subscription: bool


class RecurringSummaryOut(BaseModel):
    currency: str
    expenses: List[RecurringCostRow]
    incomes: List[RecurringCostRow]
    expense_per_month: Decimal
    expense_per_year: Decimal
    subscriptions_per_month: Decimal
    subscriptions_per_year: Decimal
    subscriptions_count: int
    income_per_year: Decimal
    income_share: Optional[float]   # % of recurring income spent on recurring expenses
