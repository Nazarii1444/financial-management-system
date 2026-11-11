"""create transaction trash

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-18 18:00:00.000000

Changes
-------
- Create transaction_trash (soft-deleted transactions, restorable for 30 days)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transaction_trash",
        sa.Column("id_", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("receipt_ids", sa.JSON(), nullable=False),
        sa.Column("capital_effect", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("capital_currency", sa.String(length=3), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id_"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id_"),
    )
    op.create_index(op.f("ix_transaction_trash_user_id"), "transaction_trash", ["user_id"], unique=False)
    op.create_index(op.f("ix_transaction_trash_expires_at"), "transaction_trash", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_transaction_trash_expires_at"), table_name="transaction_trash")
    op.drop_index(op.f("ix_transaction_trash_user_id"), table_name="transaction_trash")
    op.drop_table("transaction_trash")
