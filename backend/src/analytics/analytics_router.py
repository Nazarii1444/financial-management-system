"""
Analytics router  —  /api/analytics/*

All heavy work is delegated to service classes that subclass
BaseAnalyticsService.  Adding a new analytics metric means:
  1. Create services/<name>_service.py
  2. Add one endpoint here that instantiates the service and calls .compute()
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.dependencies import get_current_user
from src.models import TransactionKind, User
from src.transactions.currency_converter import get_rates_map

from .schemas import (
    BudgetComparisonOut,
    CategoryBreakdownOut,
    MonthlyTrendsOut,
    OverviewOut,
    PeriodComparisonOut,
    TagBreakdownOut,
    YearlyTrendsOut,
)
from .services.budget_comparison_service import BudgetComparisonService
from .services.category_service import CategoryBreakdownService
from .services.overview_service import OverviewService
from .services.period_comparison_service import PeriodComparisonService
from .services.tags_service import TagBreakdownService
from .services.trends_service import TrendsService

analytics_router = APIRouter()


# ── Shared dependency: load rates once per request ────────────────────────────

async def _ctx(
    currency: Optional[str] = Query(None, description="Override reporting currency (ISO-4217, e.g. EUR)"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rates = await get_rates_map(session)
    return session, current_user, rates, currency


# ── 1. Overview ───────────────────────────────────────────────────────────────

@analytics_router.get(
    "/overview",
    response_model=OverviewOut,
    summary="Balance, total income & expenses for a period",
)
async def get_overview(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    ctx=Depends(_ctx),
):
    session, user, rates, currency = ctx
    result = await OverviewService(session, user, rates, currency).compute(
        date_from=date_from, date_to=date_to
    )
    return result


# ── 2. Monthly trends ─────────────────────────────────────────────────────────

@analytics_router.get(
    "/trends/monthly",
    response_model=MonthlyTrendsOut,
    summary="Income vs expenses per month for the last N months",
)
async def get_monthly_trends(
    months: int = Query(12, ge=1, le=60, description="Number of months to look back"),
    ctx=Depends(_ctx),
):
    session, user, rates, currency = ctx
    result = await TrendsService(session, user, rates, currency).compute(mode="monthly", months=months)
    return result


# ── 3. Yearly trends ──────────────────────────────────────────────────────────

@analytics_router.get(
    "/trends/yearly",
    response_model=YearlyTrendsOut,
    summary="Year-over-year income vs expenses comparison",
)
async def get_yearly_trends(
    years: int = Query(3, ge=1, le=10, description="Number of years to include"),
    ctx=Depends(_ctx),
):
    session, user, rates, currency = ctx
    result = await TrendsService(session, user, rates, currency).compute(mode="yearly", years=years)
    return result


# ── 4. Period-over-period comparison ─────────────────────────────────────────

@analytics_router.get(
    "/comparison/period",
    response_model=PeriodComparisonOut,
    summary="Current period vs previous equivalent period",
    description=(
        "**mode=monthly** (default) — current calendar month vs previous month.\n\n"
        "**mode=yearly** — current calendar year vs previous year.\n\n"
        "**mode=custom** — supply `date_from` + `date_to`; the previous window is "
        "automatically shifted back by the same duration."
    ),
)
async def get_period_comparison(
    mode: str = Query("monthly", regex="^(monthly|yearly|custom)$"),
    date_from: Optional[datetime] = Query(None, description="Required for mode=custom"),
    date_to: Optional[datetime] = Query(None, description="Required for mode=custom"),
    ctx=Depends(_ctx),
):
    session, user, rates, currency = ctx
    result = await PeriodComparisonService(session, user, rates, currency).compute(
        mode=mode, date_from=date_from, date_to=date_to
    )
    return result


# ── 5. Category breakdown ─────────────────────────────────────────────────────

@analytics_router.get(
    "/breakdown/categories",
    response_model=CategoryBreakdownOut,
    summary="Spending breakdown by category (pie / bar chart data)",
)
async def get_category_breakdown(
    kind: Optional[TransactionKind] = Query(None, description="EXPENSE | INCOME — omit for all"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    ctx=Depends(_ctx),
):
    session, user, rates, currency = ctx
    result = await CategoryBreakdownService(session, user, rates, currency).compute(
        kind=kind, date_from=date_from, date_to=date_to
    )
    return result


# ── 6. Tags breakdown ─────────────────────────────────────────────────────────

@analytics_router.get(
    "/breakdown/tags",
    response_model=TagBreakdownOut,
    summary="Spending breakdown by tag",
)
async def get_tag_breakdown(
    kind: Optional[TransactionKind] = Query(None, description="EXPENSE | INCOME — omit for all"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    ctx=Depends(_ctx),
):
    session, user, rates, currency = ctx
    result = await TagBreakdownService(session, user, rates, currency).compute(
        kind=kind, date_from=date_from, date_to=date_to
    )
    return result


# ── 7. Budget vs actual ───────────────────────────────────────────────────────

@analytics_router.get(
    "/budgets/{budget_id}",
    response_model=BudgetComparisonOut,
    summary="Budget limit vs actual spending for a period",
)
async def get_budget_comparison(
    budget_id: int,
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    ctx=Depends(_ctx),
):
    session, user, rates, currency = ctx
    result = await BudgetComparisonService(session, user, rates, currency).compute(
        budget_id=budget_id, date_from=date_from, date_to=date_to
    )
    return result

