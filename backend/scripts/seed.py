"""
Seed script — populates the database with realistic test data.

Usage (from repo root / backend/ directory):
    python -m scripts.seed            # insert data (skip existing users by email)
    python -m scripts.seed --clear    # wipe all seeded tables first, then insert
    SEED_CLEAR=1 python -m scripts.seed   # same via env var

All 10 seeded users share the password:  password123
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

# ── Make `src` importable when the script is run directly ────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import DATABASE_URL
from src.models import (
    Budget,
    BudgetMember,
    BudgetRole,
    BudgetType,
    Currencies,
    Currency,
    Goal,
    Notification,
    NotificationPreferences,
    Receipt,
    RecurringFrequency,
    RecurringTransaction,
    SubscriptionPlan,
    Transaction,
    TransactionKind,
    User,
    UserStatus,
)
from src.utils.auth_services import hash_password

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SEED_PASSWORD = "password123"

EXPENSE_CATEGORIES = [
    "shopping", "food", "transportation", "health", "entertainment",
    "housing", "utilities", "education", "clothing", "travel",
    "beauty", "sports", "car", "electronics", "gifts",
]
INCOME_CATEGORIES = ["salary", "freelance", "investment", "bonus", "other"]

TX_NAMES_EXPENSE = [
    "Grocery store", "Coffee shop", "Netflix", "Gym membership", "Electricity bill",
    "Rent payment", "Gas station", "Pharmacy", "Restaurant dinner", "Bus ticket",
    "Amazon order", "Phone bill", "Dentist visit", "Clothes shopping", "Movie tickets",
    "Hotel stay", "Flight ticket", "Book purchase", "Haircut", "Car wash",
    "Online subscription", "Taxi ride", "Supermarket", "Bakery", "Food delivery",
]
TX_NAMES_INCOME = [
    "Monthly salary", "Freelance project", "Stock dividends", "Year-end bonus",
    "Client payment", "Consulting fee", "Side project income", "Rental income",
    "Interest payment", "Business revenue",
]
TX_NAMES_TRANSFER = ["Bank transfer", "Wallet top-up", "Account rebalance", "Savings transfer"]

TX_NOTES = [
    None, None, None,
    "Check receipt", "Monthly expense", "Reimbursement pending",
    "Split with partner", "Work expense", "Recurring payment",
]

GOAL_POOL = [
    ("Emergency Fund",       "Saving for unexpected expenses",                  2000,  8000),
    ("Vacation to Italy",    "Summer trip to Rome and Florence",                1500,  5000),
    ("New Laptop",           "MacBook Pro for work",                            1200,  2500),
    ("Car Down Payment",     "Saving for a new car",                            3000, 12000),
    ("Home Renovation",      "Kitchen and bathroom remodel",                    5000, 20000),
    ("Wedding Fund",         "Planning the perfect wedding",                    8000, 25000),
    ("Investment Portfolio", "Long-term wealth building",                       1000, 50000),
    ("Education Fund",       "Online courses and certifications",                500,  3000),
    ("New Smartphone",       "Latest flagship device",                           500,  1200),
    ("Dream Apartment",      "Moving to a bigger place",                       10000, 30000),
    ("Gaming Setup",         "High-end PC and peripherals",                     1500,  4000),
    ("Health Insurance",     "Private health coverage fund",                     800,  2000),
]

BUDGET_NAMES = [
    "Monthly Expenses", "Family Budget", "Business Operations", "Travel Fund",
    "Groceries", "Entertainment", "Healthcare", "Home Improvement",
    "Tech Gadgets", "Personal Budget", "Q2 Planning", "Side Project",
]

RECURRING_EXPENSE_NAMES = [
    "Netflix subscription", "Spotify Premium", "Gym membership", "Rent",
    "Electricity bill", "Internet bill", "Phone plan", "Cloud storage",
    "Insurance premium", "Software license",
]
RECURRING_INCOME_NAMES = [
    "Monthly salary", "Freelance retainer", "Rental income", "Dividend payment",
]

OCR_MERCHANTS = [
    "Walmart", "McDonald's", "Starbucks", "Amazon", "Target",
    "Costco", "CVS Pharmacy", "Whole Foods", "IKEA", "Best Buy",
    "Aldi", "Lidl", "H&M", "Zara", "KFC",
]

# ── User definitions ──────────────────────────────────────────────────────────

_USER_DEFS = [
    # username       email                      currency  plan                    timezone                 capital
    ("alice_m",   "alice@example.com",   "USD", SubscriptionPlan.PRO,  "America/New_York",  5_200.00),
    ("bob_k",     "bob@example.com",     "EUR", SubscriptionPlan.FREE, "Europe/Berlin",     1_850.00),
    ("carol_p",   "carol@example.com",   "GBP", SubscriptionPlan.PRO,  "Europe/London",     3_100.00),
    ("david_n",   "david@example.com",   "UAH", SubscriptionPlan.FREE, "Europe/Kyiv",      42_000.00),
    ("emma_s",    "emma@example.com",    "PLN", SubscriptionPlan.PRO,  "Europe/Warsaw",     9_800.00),
    ("frank_o",   "frank@example.com",   "CHF", SubscriptionPlan.FREE, "UTC",               7_300.00),
    ("grace_l",   "grace@example.com",   "AUD", SubscriptionPlan.PRO,  "Australia/Sydney",  4_150.00),
    ("henry_t",   "henry@example.com",   "JPY", SubscriptionPlan.FREE, "Asia/Tokyo",      520_000.00),
    ("irene_v",   "irene@example.com",   "NOK", SubscriptionPlan.PRO,  "UTC",              11_000.00),
    ("james_w",   "james@example.com",   "SEK", SubscriptionPlan.FREE, "Europe/Berlin",     6_700.00),
]

_CURRENCY_RATES: dict[str, float] = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 149.50,
    "AUD": 1.53,
    "CHF": 0.90,
    "SEK": 10.42,
    "NOK": 10.57,
    "PLN": 4.01,
    "UAH": 37.25,
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _past(*, days: int = 0, hours: int = 0) -> datetime:
    return _now() - timedelta(days=days, hours=hours)


def _future(*, days: int) -> datetime:
    return _now() + timedelta(days=days)


def _dec(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))


# ─────────────────────────────────────────────────────────────────────────────
# Builders — pure functions, no DB calls
# ─────────────────────────────────────────────────────────────────────────────

def build_users(hashed_pw: str) -> list[User]:
    return [
        User(
            username=uname,
            email=email,
            hashed_password=hashed_pw,
            default_currency=currency,
            timezone=tz,
            capital=capital,
            subscription_plan=plan,
            role=UserStatus.USER,
        )
        for uname, email, currency, plan, tz, capital in _USER_DEFS
    ]


def build_currency_rates() -> list[Currency]:
    return [Currency(name=k, rate=v) for k, v in _CURRENCY_RATES.items()]


def build_transactions(user: User) -> list[Transaction]:
    txs: list[Transaction] = []
    # Weight: 60 % expense, 30 % income, 10 % transfer
    kind_pool = (
        [TransactionKind.EXPENSE] * 6
        + [TransactionKind.INCOME] * 3
        + [TransactionKind.TRANSFER] * 1
    )
    for _ in range(30):
        kind = random.choice(kind_pool)
        if kind == TransactionKind.EXPENSE:
            cat  = random.choice(EXPENSE_CATEGORIES)
            name = random.choice(TX_NAMES_EXPENSE)
        elif kind == TransactionKind.INCOME:
            cat  = random.choice(INCOME_CATEGORIES)
            name = random.choice(TX_NAMES_INCOME)
        else:
            cat  = "transfer"
            name = random.choice(TX_NAMES_TRANSFER)

        tags = random.sample(
            ["bills", "recurring", "important", "reviewed", "personal", "work"],
            k=random.randint(0, 2),
        )
        txs.append(
            Transaction(
                user_id=user.id_,
                amount=_dec(random.uniform(5.0, 2_000.0)),
                name=name,
                kind=kind,
                category_name=cat,
                currency=random.choice([c.value for c in Currencies]),
                tags=tags,
                note=random.choice(TX_NOTES),
                date=_past(days=random.randint(0, 180), hours=random.randint(0, 23)),
            )
        )
    return txs


def build_goals(user: User) -> list[Goal]:
    chosen = random.sample(GOAL_POOL, k=3)
    goals: list[Goal] = []
    for name, desc, lo, hi in chosen:
        target   = _dec(random.uniform(lo, hi))
        raw_pct  = random.uniform(0.0, 1.15)          # allow slight over-save
        saved    = _dec(min(float(target), float(target) * raw_pct))
        completed = saved >= target
        goals.append(
            Goal(
                user_id=user.id_,
                name=name,
                target_amount=target,
                saved_amount=saved,
                currency=random.choice([c.value for c in Currencies]),
                description=desc,
                deadline=None if completed else _future(days=random.randint(30, 730)),
                is_completed=completed,
                completed_at=_past(days=random.randint(1, 60)) if completed else None,
            )
        )
    return goals


def build_budgets(user: User) -> list[Budget]:
    names = random.sample(BUDGET_NAMES, k=3)
    types = [BudgetType.PERSONAL, BudgetType.FAMILY, BudgetType.BUSINESS]
    return [
        Budget(
            owner_user_id=user.id_,
            name=name,
            type=types[i % len(types)],
            currency=random.choice(["USD", "EUR", "GBP", "UAH", "PLN"]),
            limit_amount=_dec(random.uniform(500.0, 5_000.0)) if random.random() > 0.25 else None,
        )
        for i, name in enumerate(names)
    ]


def build_budget_members(budget: Budget, all_users: list[User]) -> list[BudgetMember]:
    """Owner gets OWNER role; 1–2 random other users get EDITOR or VIEWER."""
    members = [
        BudgetMember(budget_id=budget.id_, user_id=budget.owner_user_id, role=BudgetRole.OWNER)
    ]
    candidates = [u for u in all_users if u.id_ != budget.owner_user_id]
    for u in random.sample(candidates, k=min(2, len(candidates))):
        members.append(
            BudgetMember(
                budget_id=budget.id_,
                user_id=u.id_,
                role=random.choice([BudgetRole.EDITOR, BudgetRole.VIEWER]),
            )
        )
    return members


def build_recurring(user: User) -> list[RecurringTransaction]:
    rts: list[RecurringTransaction] = []
    _freq_offset = {
        RecurringFrequency.DAILY:     1,
        RecurringFrequency.WEEKLY:    7,
        RecurringFrequency.BIWEEKLY: 14,
        RecurringFrequency.MONTHLY:  30,
        RecurringFrequency.YEARLY:  365,
    }
    for _ in range(random.randint(2, 3)):
        is_expense = random.random() > 0.25
        if is_expense:
            name = random.choice(RECURRING_EXPENSE_NAMES)
            cat  = random.choice(EXPENSE_CATEGORIES)
            kind = TransactionKind.EXPENSE
        else:
            name = random.choice(RECURRING_INCOME_NAMES)
            cat  = random.choice(INCOME_CATEGORIES)
            kind = TransactionKind.INCOME

        freq = random.choice(list(RecurringFrequency))
        rts.append(
            RecurringTransaction(
                user_id=user.id_,
                name=name,
                amount=_dec(random.uniform(10.0, 600.0)),
                kind=kind,
                category_name=cat,
                currency=user.default_currency,
                tags=random.sample(["recurring", "auto", "subscription"], k=random.randint(0, 1)),
                note="Seeded recurring transaction",
                frequency=freq,
                next_run=_future(days=_freq_offset[freq]),
                is_active=True,
            )
        )
    return rts


def build_notification_prefs(user: User) -> NotificationPreferences:
    return NotificationPreferences(
        user_id=user.id_,
        email_enabled=random.choice([True, True, False]),
        push_enabled=random.choice([True, False, False]),
        budget_limit_alerts=random.choice([True, True, False]),
        recurring_reminders=True,
        goal_milestone_alerts=True,
        monthly_summary=random.choice([True, True, False]),
    )


def build_notifications(user: User) -> list[Notification]:
    return [
        Notification(
            user_id=user.id_,
            deadline=_future(days=random.randint(1, 90)),
        )
        for _ in range(random.randint(1, 3))
    ]


def build_receipts(user: User, txs: list[Transaction]) -> list[Receipt]:
    """3 fake receipt rows linked to random transactions. No actual files on disk."""
    sample_txs = random.sample(txs, k=min(3, len(txs)))
    _exts = {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf"}
    receipts: list[Receipt] = []

    for tx in sample_txs:
        content_type = random.choice(list(_exts.keys()))
        ext          = _exts[content_type]
        fname        = f"{uuid.uuid4().hex}{ext}"
        merchant     = random.choice(OCR_MERCHANTS)
        amount_float = float(tx.amount)

        receipts.append(
            Receipt(
                user_id=user.id_,
                transaction_id=tx.id_,
                original_filename=f"receipt_{tx.id_}{ext}",
                stored_filename=fname,
                file_path=f"{user.id_}/{fname}",
                content_type=content_type,
                file_size=random.randint(30_000, 2_000_000),
                ocr_result={
                    "raw_text": f"{merchant}\nDate: {tx.date.strftime('%Y-%m-%d')}\nTotal: {amount_float:.2f}\nThank you!",
                    "amounts": [amount_float],
                    "suggested_amount": amount_float,
                    "suggested_category": tx.category_name,
                    "merchant": merchant,
                    "confidence": random.choice(["high", "medium", "low"]),
                },
            )
        )
    return receipts


# ─────────────────────────────────────────────────────────────────────────────
# Clear helpers
# ─────────────────────────────────────────────────────────────────────────────

# Deletion order respects FK constraints (most-dependent first)
_CLEAR_ORDER = [
    Receipt,
    BudgetMember,
    NotificationPreferences,
    Notification,
    RecurringTransaction,
    Goal,
    Transaction,
    Budget,
    User,
    Currency,
]


async def _clear_all(session: AsyncSession) -> None:
    print("⚠   Clearing existing rows …")
    for model in _CLEAR_ORDER:
        await session.execute(delete(model))
    await session.commit()
    print("    Done.\n")


# ─────────────────────────────────────────────────────────────────────────────
# Main seed
# ─────────────────────────────────────────────────────────────────────────────

async def seed(*, clear: bool = False) -> None:
    engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        if clear:
            await _clear_all(session)

        # ── 1. Currency rates ──────────────────────────────────────────────────
        print("💱  Seeding currency rates …")
        existing_currencies = (await session.execute(select(Currency))).scalars().all()
        existing_currency_names = {c.name for c in existing_currencies}
        new_currencies = [c for c in build_currency_rates() if c.name not in existing_currency_names]
        if new_currencies:
            session.add_all(new_currencies)
            await session.flush()

        # ── 2. Users ───────────────────────────────────────────────────────────
        print("👤  Seeding 10 users …")
        hashed_pw = hash_password(SEED_PASSWORD)

        existing_emails = {
            row for (row,) in (
                await session.execute(select(User.email))
            ).all()
        }
        all_users = build_users(hashed_pw)
        new_users = [u for u in all_users if u.email not in existing_emails]

        if not new_users:
            print("    All users already exist — run with --clear to reset.\n")
            await engine.dispose()
            return

        session.add_all(new_users)
        await session.flush()   # IDs are now set

        # Re-fetch all users so budget-member cross-linking has complete list
        all_users_db: list[User] = list(
            (await session.execute(select(User).where(User.email.in_([u.email for u in all_users])))).scalars().all()
        )

        # ── 3. Per-user data ───────────────────────────────────────────────────
        all_budgets: list[Budget] = []
        total_txs = 0
        total_receipts = 0

        for user in all_users_db:
            # Transactions (need flush for IDs → receipts reference them)
            txs = build_transactions(user)
            session.add_all(txs)
            await session.flush()
            total_txs += len(txs)

            # Goals
            session.add_all(build_goals(user))

            # Budgets (need flush for IDs → budget_members reference them)
            budgets = build_budgets(user)
            session.add_all(budgets)
            await session.flush()
            all_budgets.extend(budgets)

            # Recurring transactions
            session.add_all(build_recurring(user))

            # Notification preferences (1 row per user)
            session.add(build_notification_prefs(user))

            # Notifications
            session.add_all(build_notifications(user))

            # Receipts (fake metadata, no actual files on disk)
            receipts = build_receipts(user, txs)
            session.add_all(receipts)
            total_receipts += len(receipts)

        # ── 4. Budget members (cross-user linking) ─────────────────────────────
        print("👥  Seeding budget members …")
        for budget in all_budgets:
            session.add_all(build_budget_members(budget, all_users_db))

        # ── 5. Final commit ────────────────────────────────────────────────────
        await session.commit()

    await engine.dispose()

    # ── Summary ────────────────────────────────────────────────────────────────
    n_users = len(all_users_db)
    print()
    print("✅  Seed complete!")
    print(f"   Users                : {n_users}")
    print(f"   Transactions         : {total_txs}  ({total_txs // n_users} per user)")
    print(f"   Goals                : {n_users * 3}  (3 per user)")
    print(f"   Budgets              : {len(all_budgets)}  (3 per user)")
    print(f"   Receipts (metadata)  : {total_receipts}  (~3 per user, no files on disk)")
    print(f"   Recurring rules      : 2–3 per user")
    print(f"   Notification prefs   : {n_users}  (1 per user)")
    print()
    print(f"   Password for all users: {SEED_PASSWORD!r}")
    print()
    print("   Sample logins:")
    for uname, email, *_ in _USER_DEFS[:4]:
        print(f"     email={email}   password={SEED_PASSWORD}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed the database with 10 test users and full entity data."
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        default=os.getenv("SEED_CLEAR", "0") == "1",
        help="Wipe all seeded tables before inserting (default: false).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(seed(clear=args.clear))


