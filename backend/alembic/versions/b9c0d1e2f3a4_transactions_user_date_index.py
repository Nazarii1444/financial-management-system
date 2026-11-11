"""transactions (user_id, date) index

Revision ID: b9c0d1e2f3a4
Revises: a7b8c9d0e1f2
Create Date: 2026-10-18 20:00:00.000000

Changes
-------
- ix_transactions_user_id_date — transactions had no index on user_id, so every
  per-user read (list, search, analytics, export) scanned the whole table
- drop ix_transactions_id_ — duplicate of the primary-key index; keeps the
  number of indexes updated on each insert the same
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_transactions_user_id_date", "transactions", ["user_id", "date"], unique=False)
    op.drop_index("ix_transactions_id_", table_name="transactions")


def downgrade() -> None:
    op.create_index("ix_transactions_id_", "transactions", ["id_"], unique=False)
    op.drop_index("ix_transactions_user_id_date", table_name="transactions")
