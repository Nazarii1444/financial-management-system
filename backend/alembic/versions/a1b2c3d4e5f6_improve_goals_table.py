"""improve goals table

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-04-04 16:00:00.000000

Changes
-------
- Rename  summ  -> target_amount  (Float -> Numeric 14,2)
- Rename  saved -> saved_amount   (Float -> Numeric 14,2)
- Add     currency, description, deadline
- Add     is_completed, completed_at, created_at
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename + retype existing columns
    op.alter_column(
        "goals", "summ",
        new_column_name="target_amount",
        type_=sa.Numeric(14, 2),
        postgresql_using="summ::numeric",
        nullable=False,
    )
    op.alter_column(
        "goals", "saved",
        new_column_name="saved_amount",
        type_=sa.Numeric(14, 2),
        postgresql_using="saved::numeric",
        nullable=False,
    )

    # Add index on user_id (was missing)
    op.create_index(op.f("ix_goals_user_id"), "goals", ["user_id"], unique=False)

    # New columns
    op.add_column("goals", sa.Column("currency", sa.String(3), nullable=False, server_default="USD"))
    op.add_column("goals", sa.Column("description", sa.String(512), nullable=True))
    op.add_column("goals", sa.Column("deadline", sa.DateTime(timezone=True), nullable=True))
    op.add_column("goals", sa.Column("is_completed", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("goals", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "goals",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("goals", "created_at")
    op.drop_column("goals", "completed_at")
    op.drop_column("goals", "is_completed")
    op.drop_column("goals", "deadline")
    op.drop_column("goals", "description")
    op.drop_column("goals", "currency")
    op.drop_index(op.f("ix_goals_user_id"), table_name="goals")

    op.alter_column(
        "goals", "saved_amount",
        new_column_name="saved",
        type_=sa.Float(),
        postgresql_using="saved_amount::float",
        nullable=False,
    )
    op.alter_column(
        "goals", "target_amount",
        new_column_name="summ",
        type_=sa.Float(),
        postgresql_using="target_amount::float",
        nullable=False,
    )

