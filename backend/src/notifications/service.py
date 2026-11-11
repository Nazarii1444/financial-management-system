"""
Notification e-mails: who gets what, and when.

Four events, each behind its own toggle in `notification_preferences` (plus the
`email_enabled` channel switch):

  recurring_reminder  — an active recurring *expense* fires within the next 24 hours
  budget_alert        — this month's spending reached 85 % / 100 % of a budget's limit
                        (sent to every member of the budget)
  goal_milestone      — a deposit carried a goal past 25 / 50 / 75 / 100 %
  monthly_summary     — last month's income, expenses and top categories (first week of the month)

The first three of `run_*` jobs are driven by the hourly scheduler (`register_notification_cron`);
goal milestones are event-driven from `POST /api/goals/{id}/deposit`.

Every notification is at-most-once: before sending, `claim` inserts (user_id, key) into
`sent_notifications`, and only the caller whose insert succeeded sends. Keys name the
event, so re-runs, several workers and withdraw → deposit cycles never repeat an e-mail.

The decision rules (`crossed_milestones`, `budget_threshold`, `is_due_for_reminder`,
`summary_month`) are pure functions, unit-tested without a database.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from fastapi import FastAPI
from fastapi_utilities import repeat_every
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src import config
from src.analytics.services.budget_comparison_service import BudgetComparisonService
from src.analytics.services.category_service import CategoryBreakdownService
from src.analytics.services.overview_service import OverviewService
from src.config import logger
from src.database import AsyncSessionLocal
from src.models import (
    Budget,
    BudgetMember,
    Goal,
    NotificationPreferences,
    RecurringTransaction,
    SentNotification,
    Transaction,
    TransactionKind,
    User,
)
from src.notifications import templates
from src.notifications.mailer import send_email
from src.transactions.currency_converter import get_rates_map

MILESTONES = (25, 50, 75, 100)
BUDGET_WARNING_PERCENT = 85
REMINDER_WINDOW = timedelta(hours=24)
SUMMARY_GRACE_DAYS = 7          # the summary for last month may go out until the 7th
TOP_CATEGORIES = 3


class Kind:
    RECURRING_REMINDER = "recurring_reminder"
    BUDGET_ALERT = "budget_alert"
    GOAL_MILESTONE = "goal_milestone"
    MONTHLY_SUMMARY = "monthly_summary"


# Which preference toggle governs which event
_PREFERENCE_FIELD = {
    Kind.RECURRING_REMINDER: "recurring_reminders",
    Kind.BUDGET_ALERT: "budget_limit_alerts",
    Kind.GOAL_MILESTONE: "goal_milestone_alerts",
    Kind.MONTHLY_SUMMARY: "monthly_summary",
}


# ── Pure rules ────────────────────────────────────────────────────────────────

def progress_percent(saved, target) -> float:
    target = Decimal(str(target))
    if target <= 0:
        return 100.0
    return float(Decimal(str(saved)) / target * 100)


def crossed_milestones(before_percent: float, after_percent: float) -> List[int]:
    """Milestones passed by moving from *before* to *after* (e.g. 20 → 60 gives [25, 50])."""
    return [m for m in MILESTONES if before_percent < m <= after_percent]


def budget_threshold(utilization_percent: Optional[float]) -> Optional[int]:
    """100 when the limit is reached, 85 when close to it, otherwise None."""
    if utilization_percent is None:
        return None
    if utilization_percent >= 100:
        return 100
    if utilization_percent >= BUDGET_WARNING_PERCENT:
        return BUDGET_WARNING_PERCENT
    return None


def is_due_for_reminder(next_run: datetime, now: datetime) -> bool:
    """A payment gets its reminder once it is less than 24 hours away (and not yet past)."""
    if next_run.tzinfo is None:
        next_run = next_run.replace(tzinfo=timezone.utc)
    return now < next_run <= now + REMINDER_WINDOW


def summary_month(now: datetime) -> Optional[Tuple[int, int]]:
    """(year, month) whose summary is due at *now*: last month, during the first week only."""
    if now.day > SUMMARY_GRACE_DAYS:
        return None
    previous = now.replace(day=1) - timedelta(days=1)
    return previous.year, previous.month


def month_bounds(year: int, month: int) -> Tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    return start, start + relativedelta(months=1)


def user_zone(user: User):
    try:
        return ZoneInfo(user.timezone) if user.timezone else timezone.utc
    except Exception:
        return timezone.utc


# ── Preferences and de-duplication ───────────────────────────────────────────

@dataclass
class Prefs:
    email_enabled: bool = True
    budget_limit_alerts: bool = True
    recurring_reminders: bool = True
    goal_milestone_alerts: bool = True
    monthly_summary: bool = True
    language: str = "uk"

    def wants(self, kind: str) -> bool:
        return self.email_enabled and getattr(self, _PREFERENCE_FIELD[kind])


async def load_prefs(session: AsyncSession, user_ids: Iterable[int]) -> Dict[int, Prefs]:
    """Preferences per user; users who never opened the settings get the defaults (all on)."""
    ids = list(set(user_ids))
    result = {uid: Prefs() for uid in ids}
    if not ids:
        return result
    rows = (await session.execute(
        select(NotificationPreferences).where(NotificationPreferences.user_id.in_(ids))
    )).scalars().all()
    for row in rows:
        result[row.user_id] = Prefs(
            email_enabled=row.email_enabled,
            budget_limit_alerts=row.budget_limit_alerts,
            recurring_reminders=row.recurring_reminders,
            goal_milestone_alerts=row.goal_milestone_alerts,
            monthly_summary=row.monthly_summary,
            language=row.language or "uk",
        )
    return result


async def claim(session: AsyncSession, user_id: int, kind: str, key: str) -> bool:
    """Record the notification; True only for the first caller (the one that should send it)."""
    stmt = (
        pg_insert(SentNotification)
        .values(user_id=user_id, kind=kind, key=key)
        .on_conflict_do_nothing(constraint="uq_sent_notifications_user_key")
        .returning(SentNotification.id_)
    )
    claimed = (await session.execute(stmt)).scalar_one_or_none() is not None
    await session.commit()
    return claimed


# ── Jobs ──────────────────────────────────────────────────────────────────────

async def run_recurring_reminders(session: AsyncSession, now: datetime) -> int:
    rules = (await session.execute(
        select(RecurringTransaction, User)
        .join(User, User.id_ == RecurringTransaction.user_id)
        .where(
            RecurringTransaction.is_active.is_(True),
            RecurringTransaction.kind == TransactionKind.EXPENSE,
            RecurringTransaction.next_run > now,
            RecurringTransaction.next_run <= now + REMINDER_WINDOW,
        )
    )).all()
    prefs = await load_prefs(session, (user.id_ for _, user in rules))
    sent = 0
    for rule, user in rules:
        p = prefs[user.id_]
        if not p.wants(Kind.RECURRING_REMINDER):
            continue
        due = rule.next_run.astimezone(user_zone(user)).date()
        if not await claim(session, user.id_, Kind.RECURRING_REMINDER, f"recurring:{rule.id_}:{due.isoformat()}"):
            continue
        sent += await send_email(templates.recurring_reminder(
            to=user.email, name=user.username, payment=rule.name, amount=rule.amount,
            currency=rule.currency or user.default_currency, category=rule.category_name, due=due,
            lang=p.language, frontend_url=config.FRONTEND_URL,
        ))
    return sent


async def run_budget_alerts(session: AsyncSession, now: datetime) -> int:
    budgets = (await session.execute(
        select(Budget, User).join(User, User.id_ == Budget.owner_user_id).where(Budget.limit_amount.is_not(None))
    )).all()
    if not budgets:
        return 0
    rates = await get_rates_map(session)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_key = month_start.strftime("%Y-%m")
    sent = 0
    for budget, owner in budgets:
        try:
            result = await BudgetComparisonService(session, owner, rates).compute(
                budget_id=budget.id_, date_from=month_start, date_to=now)
        except Exception:
            logger.exception("Budget alert: comparison failed for budget id=%s", budget.id_)
            continue
        threshold = budget_threshold(result.get("utilization_percent"))
        if threshold is None:
            continue
        members = (await session.execute(
            select(User).join(BudgetMember, BudgetMember.user_id == User.id_).where(BudgetMember.budget_id == budget.id_)
        )).scalars().all()
        prefs = await load_prefs(session, (m.id_ for m in members))
        for member in members:
            p = prefs[member.id_]
            if not p.wants(Kind.BUDGET_ALERT):
                continue
            key = f"budget:{budget.id_}:{month_key}:{threshold}"
            if not await claim(session, member.id_, Kind.BUDGET_ALERT, key):
                continue
            if threshold == 100:
                # The "close to the limit" warning would be stale now (and must not follow later)
                await claim(session, member.id_, Kind.BUDGET_ALERT, f"budget:{budget.id_}:{month_key}:{BUDGET_WARNING_PERCENT}")
            sent += await send_email(templates.budget_alert(
                to=member.email, name=member.username, budget=budget.name,
                percent=result["utilization_percent"], spent=result["actual_spent"],
                limit=result["limit_amount"], currency=result["currency"], exceeded=threshold == 100,
                lang=p.language, frontend_url=config.FRONTEND_URL,
            ))
    return sent


async def run_monthly_summaries(session: AsyncSession, now: datetime) -> int:
    due = summary_month(now)
    if due is None:
        return 0
    year, month = due
    start, end = month_bounds(year, month)
    users = (await session.execute(
        select(User).where(User.id_.in_(
            select(Transaction.user_id).where(Transaction.date >= start, Transaction.date < end).distinct()
        ))
    )).scalars().all()
    if not users:
        return 0
    prefs = await load_prefs(session, (u.id_ for u in users))
    rates = await get_rates_map(session)
    sent = 0
    for user in users:
        p = prefs[user.id_]
        if not p.wants(Kind.MONTHLY_SUMMARY):
            continue
        if not await claim(session, user.id_, Kind.MONTHLY_SUMMARY, f"monthly:{year:04d}-{month:02d}"):
            continue
        last_moment = end - timedelta(microseconds=1)
        overview = await OverviewService(session, user, rates).compute(date_from=start, date_to=last_moment)
        categories = await CategoryBreakdownService(session, user, rates).compute(
            kind=TransactionKind.EXPENSE, date_from=start, date_to=last_moment)
        top = [(item["category"], item["amount"]) for item in categories["items"][:TOP_CATEGORIES]]
        sent += await send_email(templates.monthly_summary(
            to=user.email, name=user.username, year=year, month=month,
            income=overview["total_income"], expenses=overview["total_expenses"], net=overview["net"],
            currency=overview["currency"], top_categories=top, lang=p.language, frontend_url=config.FRONTEND_URL,
        ))
    return sent


async def notify_goal_progress(goal_id: int, before_percent: float) -> None:
    """Background task after a deposit: e-mail the highest milestone the deposit crossed."""
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            select(Goal, User).join(User, User.id_ == Goal.user_id).where(Goal.id_ == goal_id)
        )).first()
        if row is None:
            return
        goal, user = row
        crossed = crossed_milestones(before_percent, progress_percent(goal.saved_amount, goal.target_amount))
        if not crossed:
            return
        p = (await load_prefs(session, [user.id_]))[user.id_]
        if not p.wants(Kind.GOAL_MILESTONE):
            return
        # Claim every crossed milestone so none of them is announced later; announce the highest new one
        new = [m for m in crossed if await claim(session, user.id_, Kind.GOAL_MILESTONE, f"goal:{goal.id_}:{m}")]
        if not new:
            return
        await send_email(templates.goal_milestone(
            to=user.email, name=user.username, goal=goal.name, milestone=max(new),
            saved=goal.saved_amount, target=goal.target_amount, currency=goal.currency,
            lang=p.language, frontend_url=config.FRONTEND_URL,
        ))


async def run_scheduled_notifications(now: Optional[datetime] = None) -> Dict[str, int]:
    """One scheduler tick; each job uses its own session so one failure doesn't stop the others."""
    now = now or datetime.now(timezone.utc)
    stats: Dict[str, int] = {}
    for name, job in (("recurring_reminders", run_recurring_reminders),
                      ("budget_alerts", run_budget_alerts),
                      ("monthly_summaries", run_monthly_summaries)):
        try:
            async with AsyncSessionLocal() as session:
                stats[name] = await job(session, now)
        except Exception:
            logger.exception("Notification job %s failed", name)
            stats[name] = 0
    return stats


def register_notification_cron(app: FastAPI) -> None:
    if not config.NOTIFICATIONS_ENABLED:
        logger.info("Notification scheduler disabled (NOTIFICATIONS_ENABLED=false)")
        return

    @app.on_event("startup")
    @repeat_every(seconds=60 * 60, wait_first=False, logger=logger)
    async def _scheduled_notifications() -> None:
        stats = await run_scheduled_notifications()
        if any(stats.values()):
            logger.info("Notification e-mails sent: %s", stats)
