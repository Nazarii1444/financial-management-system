"""transaction import fields

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-18 19:00:00.000000

Changes
-------
- transactions.import_ref — fingerprint of a bank-statement row (dedupe)
- transactions.counts_in_balance — False for history imported without changing the balance
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("import_ref", sa.String(length=64), nullable=True))
    op.add_column("transactions", sa.Column("counts_in_balance", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.create_index(op.f("ix_transactions_import_ref"), "transactions", ["import_ref"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_transactions_import_ref"), table_name="transactions")
    op.drop_column("transactions", "counts_in_balance")
    op.drop_column("transactions", "import_ref")
