from sqlalchemy import Column, Integer, CheckConstraint, Numeric, String, ForeignKey, Float, Boolean, Enum, UniqueConstraint, DateTime, JSON, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.database import Base

import enum


class UserStatus(enum.Enum):
    USER = 0
    ADMIN = 1


class TransactionKind(enum.Enum):
    EXPENSE = 0
    INCOME = 1
    TRANSFER = 2


class Currencies(enum.Enum):
    USD = "USD"
    EUR = "EUR"
    JPY = "JPY"
    GBP = "GBP"
    AUD = "AUD"
    CHF = "CHF"
    SEK = "SEK"
    NOK = "NOK"
    PLN = "PLN"
    UAH = "UAH"


class BudgetType(enum.Enum):
    PERSONAL = "PERSONAL"
    FAMILY = "FAMILY"
    BUSINESS = "BUSINESS"


class BudgetRole(enum.Enum):
    OWNER = "OWNER"
    EDITOR = "EDITOR"
    VIEWER = "VIEWER"


class RecurringFrequency(enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


class SubscriptionPlan(enum.Enum):
    FREE = "FREE"
    PRO = "PRO"


class User(Base):
    __tablename__ = "users"

    id_ = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False, unique=True)
    email = Column(String(255), nullable=False, unique=True)
    hashed_password = Column(String(255), nullable=False)
    default_currency = Column(String(3), nullable=False, default=Currencies.USD.value)
    timezone = Column(String(64), nullable=True)
    capital = Column(Float, nullable=False, default=0.0)
    role = Column(Enum(UserStatus), nullable=False, default=UserStatus.USER)
    twofa_secret = Column(String(32), nullable=True)
    twofa_enabled = Column(Boolean, nullable=False, default=False)
    avatar_url = Column(String(512), nullable=True)
    subscription_plan = Column(Enum(SubscriptionPlan), nullable=False, default=SubscriptionPlan.FREE)

    # relationships
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    owned_budgets = relationship("Budget", back_populates="owner", cascade="all, delete-orphan")
    budget_memberships = relationship("BudgetMember", back_populates="user", cascade="all, delete-orphan")
    recurring_transactions = relationship("RecurringTransaction", back_populates="user", cascade="all, delete-orphan")
    notification_preferences = relationship("NotificationPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan")
    receipts = relationship("Receipt", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "default_currency IN ('USD','EUR','JPY','GBP','AUD','CHF','SEK','NOK','PLN','UAH')",
            name="chk_users_default_currency",
        ),
    )


class Currency(Base):
    __tablename__ = "currencies"

    name = Column(String(16), primary_key=True)
    rate = Column(Float, nullable=False, default=1.0)


class Transaction(Base):
    __tablename__ = "transactions"

    id_ = Column(Integer, primary_key=True, autoincrement=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    name = Column(String(64), nullable=False, default="")
    kind = Column(Enum(TransactionKind), nullable=False, default=TransactionKind.EXPENSE)
    category_name = Column(String(64), nullable=False)
    currency = Column(String(16), nullable=True)
    tags = Column(ARRAY(String), nullable=False, server_default='{}')
    note = Column(String(512), nullable=True)
    date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="transactions")
    receipts = relationship("Receipt", back_populates="transaction")


class Goal(Base):
    __tablename__ = "goals"

    id_ = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    target_amount = Column(Numeric(14, 2), nullable=False)
    saved_amount = Column(Numeric(14, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default=Currencies.USD.value)
    description = Column(String(512), nullable=True)
    deadline = Column(DateTime(timezone=True), nullable=True)
    is_completed = Column(Boolean, nullable=False, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="goals")


class Notification(Base):
    __tablename__ = "notifications"

    id_ = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=False)
    deadline = Column(DateTime(timezone=True), nullable=False)

    user = relationship("User", back_populates="notifications")


class Budget(Base):
    __tablename__ = "budgets"

    id_ = Column(Integer, primary_key=True, autoincrement=True)
    owner_user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    type = Column(Enum(BudgetType), nullable=False)
    currency = Column(String(3), nullable=False, default=Currencies.USD.value)
    limit_amount = Column(Numeric(14, 2), nullable=True)          # optional monthly/periodic spending cap
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    owner = relationship("User", back_populates="owned_budgets")
    members = relationship("BudgetMember", back_populates="budget", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "currency IN ('USD','EUR','JPY','GBP','AUD','CHF','SEK','NOK','PLN','UAH')",
            name="chk_budgets_currency",
        ),
    )


class BudgetMember(Base):
    __tablename__ = "budget_members"

    id_ = Column(Integer, primary_key=True, autoincrement=True)
    budget_id = Column(Integer, ForeignKey("budgets.id_", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(Enum(BudgetRole), nullable=False, default=BudgetRole.VIEWER)

    budget = relationship("Budget", back_populates="members")
    user = relationship("User", back_populates="budget_memberships")

    __table_args__ = (
        UniqueConstraint("budget_id", "user_id", name="uq_budget_member_budget_user"),
    )


class RecurringTransaction(Base):
    __tablename__ = "recurring_transactions"

    id_ = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(64), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    kind = Column(Enum(TransactionKind), nullable=False, default=TransactionKind.EXPENSE)
    category_name = Column(String(64), nullable=False)
    currency = Column(String(16), nullable=True)
    tags = Column(ARRAY(String), nullable=False, server_default='{}')
    note = Column(String(512), nullable=True)
    frequency = Column(Enum(RecurringFrequency), nullable=False)
    next_run = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="recurring_transactions")


class NotificationPreferences(Base):
    """One row per user (1:1). Created lazily on first GET /settings/notifications."""
    __tablename__ = "notification_preferences"

    id_ = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=False, unique=True)

    # ── Channel toggles ───────────────────────────────────────────────────────
    email_enabled = Column(Boolean, nullable=False, default=True)
    push_enabled = Column(Boolean, nullable=False, default=False)

    # ── Event toggles ─────────────────────────────────────────────────────────
    budget_limit_alerts = Column(Boolean, nullable=False, default=True)   # spending near budget limit
    recurring_reminders = Column(Boolean, nullable=False, default=True)   # before recurring tx fires
    goal_milestone_alerts = Column(Boolean, nullable=False, default=True) # 25 / 50 / 75 / 100 % goal
    monthly_summary = Column(Boolean, nullable=False, default=True)       # end-of-month digest

    user = relationship("User", back_populates="notification_preferences")


class Receipt(Base):
    """
    Uploaded receipt file (image or PDF) with optional OCR analysis.

    file_path  — relative path inside UPLOAD_DIR, e.g. "7/a1b2c3.jpg"
    ocr_result — JSON blob produced by OcrService; None when OCR skipped/failed.
    """
    __tablename__ = "receipts"

    id_ = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=False, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id_", ondelete="SET NULL"), nullable=True, index=True)

    original_filename = Column(String(255), nullable=False)
    stored_filename   = Column(String(255), nullable=False)   # UUID-based, no path traversal
    file_path         = Column(String(512), nullable=False)   # relative to UPLOAD_DIR
    content_type      = Column(String(64),  nullable=False)
    file_size         = Column(Integer,     nullable=False)   # bytes

    ocr_result = Column(JSON, nullable=True)   # see OcrService for schema

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user        = relationship("User",        back_populates="receipts")
    transaction = relationship("Transaction", back_populates="receipts")




