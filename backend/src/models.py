from sqlalchemy import Column, Integer, CheckConstraint, Numeric, String, ForeignKey, Float, Boolean, Enum, UniqueConstraint, DateTime, JSON, Text, Index, LargeBinary, SmallInteger
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

    # Password health (src/security/password_policy.py). The plaintext is only seen at
    # signup / change / login, so these are snapshots taken at those moments.
    password_changed_at = Column(DateTime(timezone=True), nullable=True)   # NULL: set before this was tracked
    password_score = Column(SmallInteger, nullable=True)                   # zxcvbn 0..4
    password_breached = Column(Boolean, nullable=True)                     # NULL: never checked / HIBP unreachable
    password_checked_at = Column(DateTime(timezone=True), nullable=True)   # last HIBP check
    # Random WebAuthn user handle (never the numeric id) — set on the first passkey
    webauthn_user_handle = Column(LargeBinary(64), nullable=True, unique=True)

    # relationships
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    owned_budgets = relationship("Budget", back_populates="owner", cascade="all, delete-orphan")
    budget_memberships = relationship("BudgetMember", back_populates="user", cascade="all, delete-orphan")
    recurring_transactions = relationship("RecurringTransaction", back_populates="user", cascade="all, delete-orphan")
    notification_preferences = relationship("NotificationPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan")
    receipts = relationship("Receipt", back_populates="user", cascade="all, delete-orphan")
    transaction_templates = relationship("TransactionTemplate", back_populates="user", cascade="all, delete-orphan")
    security_events = relationship("SecurityEvent", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    passkeys = relationship("WebAuthnCredential", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)

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
    # Every per-user read (list, search, analytics, export) filters by user and usually a date range
    __table_args__ = (Index("ix_transactions_user_id_date", "user_id", "date"),)

    id_ = Column(Integer, primary_key=True, autoincrement=True)  # the primary key is already indexed
    user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    name = Column(String(64), nullable=False, default="")
    kind = Column(Enum(TransactionKind), nullable=False, default=TransactionKind.EXPENSE)
    category_name = Column(String(64), nullable=False)
    currency = Column(String(16), nullable=True)
    tags = Column(ARRAY(String), nullable=False, server_default='{}')
    note = Column(String(512), nullable=True)
    date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Bank-statement import: stable fingerprint of the source row (dedupe on re-import)
    import_ref = Column(String(64), nullable=True, index=True)
    # False for history imported without touching the balance — delete / edit /
    # restore must then leave User.capital alone too.
    counts_in_balance = Column(Boolean, nullable=False, default=True, server_default="true")

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


class ReceiptFile(Base):
    """
    Raw bytes of an uploaded receipt when FILE_STORAGE=database (hosts without a
    persistent disk). file_path matches Receipt.file_path.
    """
    __tablename__ = "receipt_files"

    id_ = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=False, index=True)
    file_path = Column(String(512), nullable=False, unique=True)
    data = Column(LargeBinary, nullable=False)


class TransactionTemplate(Base):
    """
    Saved transaction preset ("morning coffee") used with one click from the
    dashboard. Unlike RecurringTransaction nothing fires automatically — a
    Transaction is created only on `POST /api/templates/{id}/use`.
    """
    __tablename__ = "transaction_templates"

    id_ = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(64), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    kind = Column(Enum(TransactionKind), nullable=False, default=TransactionKind.EXPENSE)
    category_name = Column(String(64), nullable=False)
    currency = Column(String(16), nullable=False)
    tags = Column(ARRAY(String), nullable=False, server_default='{}')
    note = Column(String(512), nullable=True)
    use_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="transaction_templates")


class TemplateSuggestionDismissal(Base):
    """A template suggestion the user rejected; `key` is the suggestion's similarity key."""
    __tablename__ = "template_suggestion_dismissals"

    id_ = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(255), nullable=False)
    dismissed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_template_dismissal_user_key"),
    )


class CalendarFeed(Base):
    """
    Secret subscription URL for the user's recurring payments as iCalendar
    (`GET /api/calendar/feed/{token}.ics`, no auth header — calendar apps
    can't send one). Rotating the token invalidates old subscriptions.
    """
    __tablename__ = "calendar_feeds"

    id_ = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=False, unique=True)
    token = Column(String(64), nullable=False, unique=True, index=True)
    lang = Column(String(8), nullable=False, default="uk")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GoogleCalendarLink(Base):
    """
    Google Calendar API connection: recurring rules are pushed as events into a
    dedicated calendar created by the app (scope `calendar.app.created`).
    Tokens are encrypted with a key derived from SECRET_KEY.
    """
    __tablename__ = "google_calendar_links"

    id_ = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=False, unique=True)
    refresh_token = Column(Text, nullable=False)      # encrypted
    access_token = Column(Text, nullable=True)        # encrypted
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    calendar_id = Column(String(255), nullable=True)
    lang = Column(String(8), nullable=False, default="uk")
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TransactionTrash(Base):
    """
    Soft-deleted transaction (the "trash"). The Transaction row itself is
    removed, so analytics/budgets/search need no `deleted_at` filters; the
    snapshot here is enough to re-insert it with the same `id_`.

    `capital_effect` is the exact signed amount the transaction contributed to
    `User.capital` (in `capital_currency`) at deletion time — restoring adds it
    back verbatim, so the balance returns exactly even if FX rates moved.
    Rows are purged after `expires_at` (30 days).
    """
    __tablename__ = "transaction_trash"

    id_ = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=False, index=True)
    transaction_id = Column(Integer, nullable=False)          # original Transaction.id_
    data = Column(JSON, nullable=False)                       # name, amount, kind, category_name, currency, tags, note, date
    receipt_ids = Column(JSON, nullable=False, default=list)  # receipts to re-link on restore
    capital_effect = Column(Numeric(14, 2), nullable=False)
    capital_currency = Column(String(3), nullable=False)
    deleted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)


class SecurityEvent(Base):
    """
    Login / security activity shown to the user (SEC-S1): sign-ins (password,
    2FA, passkey, OAuth), failed attempts on an existing account and sensitive
    changes. Written by `src/security/events.py::record_event`.
    """
    __tablename__ = "security_events"
    __table_args__ = (Index("ix_security_events_user_id_created_at", "user_id", "created_at"),)

    id_ = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(32), nullable=False)          # see events.EventType
    success = Column(Boolean, nullable=False, default=True)
    method = Column(String(16), nullable=True)               # password | totp | passkey | google | github
    ip = Column(String(45), nullable=True)                   # IPv6 max length
    user_agent = Column(String(512), nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="security_events")


class WebAuthnCredential(Base):
    """A registered passkey (SEC-A1). Only the public key is stored."""
    __tablename__ = "webauthn_credentials"

    id_ = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=False, index=True)
    credential_id = Column(LargeBinary, nullable=False, unique=True)
    public_key = Column(LargeBinary, nullable=False)            # COSE key
    sign_count = Column(Integer, nullable=False, default=0)
    transports = Column(JSON, nullable=True)                    # ["internal", "hybrid", ...] — hints for the browser
    aaguid = Column(String(36), nullable=True)                  # authenticator model
    backed_up = Column(Boolean, nullable=False, default=False)  # synced passkey (iCloud / Google / password manager)
    name = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="passkeys")


class WebAuthnChallenge(Base):
    """Single-use WebAuthn challenge (deleted when verified; expires after 5 minutes)."""
    __tablename__ = "webauthn_challenges"

    id_ = Column(String(43), primary_key=True)                  # random URL-safe id handed to the client
    challenge = Column(LargeBinary, nullable=False)
    purpose = Column(String(16), nullable=False)                # register | login
    user_id = Column(Integer, ForeignKey("users.id_", ondelete="CASCADE"), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
