"""add tags notes and recurring_transactions

Revision ID: e5a8c12f4b76
Revises: b8e9f36a3ab8
Create Date: 2026-04-04 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "e5a8c12f4b76"
down_revision: Union[str, Sequence[str], None] = "b8e9f36a3ab8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Add tags + note to existing transactions table ──────────────────
    op.add_column(
        "transactions",
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "transactions",
        sa.Column("note", sa.String(length=512), nullable=True),
    )

    # ── 2. Create recurringfrequency type (safe: skips if already exists) ──
    op.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE recurringfrequency AS ENUM ('DAILY', 'WEEKLY', 'BIWEEKLY', 'MONTHLY', 'YEARLY');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """))

    # ── 3. Create recurring_transactions table ──────────────────────────────
    # Use PgEnum(create_type=False) for every enum column so op.create_table
    # never issues its own CREATE TYPE (both types already exist in the DB).
    op.create_table(
        "recurring_transactions",
        sa.Column("id_", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "kind",
            PgEnum("EXPENSE", "INCOME", "TRANSFER", name="transactionkind", create_type=False),
            nullable=False,
        ),
        sa.Column("category_name", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("note", sa.String(length=512), nullable=True),
        sa.Column(
            "frequency",
            PgEnum("DAILY", "WEEKLY", "BIWEEKLY", "MONTHLY", "YEARLY", name="recurringfrequency", create_type=False),
            nullable=False,
        ),
        sa.Column("next_run", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id_"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id_"),
    )
    op.create_index(
        op.f("ix_recurring_transactions_user_id"),
        "recurring_transactions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_recurring_transactions_user_id"), table_name="recurring_transactions")
    op.drop_table("recurring_transactions")
    op.execute(sa.text("DROP TYPE IF EXISTS recurringfrequency"))

    op.drop_column("transactions", "note")
    op.drop_column("transactions", "tags")
