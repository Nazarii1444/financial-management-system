"""create transaction templates

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-18 12:00:00.000000

Changes
-------
- Create transaction_templates (one-click transaction presets)
- Create template_suggestion_dismissals (rejected "make a template" suggestions)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transaction_templates",
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
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("note", sa.String(length=512), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id_"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id_"),
    )
    op.create_index(op.f("ix_transaction_templates_user_id"), "transaction_templates", ["user_id"], unique=False)

    op.create_table(
        "template_suggestion_dismissals",
        sa.Column("id_", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id_"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id_"),
        sa.UniqueConstraint("user_id", "key", name="uq_template_dismissal_user_key"),
    )
    op.create_index(op.f("ix_template_suggestion_dismissals_user_id"),
                    "template_suggestion_dismissals", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_template_suggestion_dismissals_user_id"), table_name="template_suggestion_dismissals")
    op.drop_table("template_suggestion_dismissals")
    op.drop_index(op.f("ix_transaction_templates_user_id"), table_name="transaction_templates")
    op.drop_table("transaction_templates")
