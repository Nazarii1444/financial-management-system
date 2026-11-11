from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ── Shared primitives ────────────────────────────────────────────────────────

class PeriodSchema(BaseModel):
    from_: Optional[str] = None
    to: Optional[str] = None


# ── Overview ─────────────────────────────────────────────────────────────────

class OverviewOut(BaseModel):
    balance: float
    total_income: float
    total_expenses: float
    net: float
    currency: str
    period: Dict[str, Optional[str]]


# ── Monthly trends ───────────────────────────────────────────────────────────

class MonthlyPointOut(BaseModel):
    year: int
    month: int
    income: float
    expenses: float
    net: float


class MonthlyTrendsOut(BaseModel):
    months: List[MonthlyPointOut]
    currency: str


# ── Yearly trends ────────────────────────────────────────────────────────────

class YearlyPointOut(BaseModel):
    year: int
    income: float
    expenses: float
    net: float


class YearlyTrendsOut(BaseModel):
    years: List[YearlyPointOut]
    currency: str


# ── Category breakdown ────────────────────────────────────────────────────────

class CategoryItemOut(BaseModel):
    category: str
    amount: float
    percent: float
    count: int


class CategoryBreakdownOut(BaseModel):
    kind: str
    total: float
    items: List[CategoryItemOut]
    currency: str


# ── Tags breakdown ────────────────────────────────────────────────────────────

class TagItemOut(BaseModel):
    tag: str
    amount: float
    percent: float
    count: int


class TagBreakdownOut(BaseModel):
    kind: str
    total: float
    items: List[TagItemOut]
    currency: str


# ── Period-over-period comparison ────────────────────────────────────────────

class PeriodSnapshotOut(BaseModel):
    """Income / expense summary for one period window."""
    from_: str
    to: str
    income: float
    expenses: float
    net: float
    transaction_count: int


class PeriodChangeOut(BaseModel):
    """Absolute and relative change between two periods."""
    income_diff: float
    income_pct: Optional[float]       # None when previous == 0
    expenses_diff: float
    expenses_pct: Optional[float]
    net_diff: float
    net_pct: Optional[float]


class PeriodComparisonOut(BaseModel):
    current: PeriodSnapshotOut
    previous: PeriodSnapshotOut
    change: PeriodChangeOut
    currency: str


# ── Safe-to-spend ─────────────────────────────────────────────────────────────

class SafeToSpendGoalOut(BaseModel):
    goal_id: int
    name: str
    saved: float                      # already in the jar (reporting currency)
    monthly_contribution: float       # needed this month to hit the deadline
    deadline: Optional[str]


class SafeToSpendOut(BaseModel):
    safe_to_spend_per_day: float      # how much can be spent per remaining day
    available_to_spend: float         # balance + expected income − committed expenses
    balance: float                    # current capital in the reporting currency
    expected_income: float            # recurring income scheduled before month end
    upcoming_expenses: float          # recurring expenses scheduled before month end
    spent_this_month: float           # actual expenses month-to-date (context)
    goal_reserved: float              # saved in active goal jars (still inside balance)
    goal_contributions: float         # required goal contributions this month
    goals: List[SafeToSpendGoalOut] = []
    spent_today: float                # expenses dated today (user's timezone)
    daily_limit: float                # today's allowance as of the start of the day
    left_today: float                 # daily_limit − spent_today; negative = overspent
    per_day_after_today: float        # allowance for each remaining day after today
    days_remaining: int               # today through last day of month, inclusive
    month_end: str                    # ISO date of the last day of the month
    currency: str
    as_of: str                        # ISO datetime the figures were computed


# ── Budget comparison ─────────────────────────────────────────────────────────

class BudgetCategorySpendOut(BaseModel):
    category: str
    amount: float


class BudgetComparisonOut(BaseModel):
    budget_id: int
    budget_name: str
    budget_type: str
    limit_amount: Optional[float]
    actual_spent: float
    remaining: Optional[float]
    utilization_percent: Optional[float]
    by_category: List[BudgetCategorySpendOut]
    currency: str
    period: Dict[str, Optional[str]]

