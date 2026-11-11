"""create receipts table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-04 18:00:00.000000

Changes
-------
- Create receipts table with FK to users (CASCADE) and transactions (SET NULL)
- Add JSON column for OCR result
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "receipts",
        sa.Column("id_",               sa.Integer(),     autoincrement=True, nullable=False),
        sa.Column("user_id",           sa.Integer(),     nullable=False),
        sa.Column("transaction_id",    sa.Integer(),     nullable=True),
        sa.Column("original_filename", sa.String(255),   nullable=False),
        sa.Column("stored_filename",   sa.String(255),   nullable=False),
        sa.Column("file_path",         sa.String(512),   nullable=False),
        sa.Column("content_type",      sa.String(64),    nullable=False),
        sa.Column("file_size",         sa.Integer(),     nullable=False),
        sa.Column("ocr_result",        sa.JSON(),        nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"],        ["users.id_"],        ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id_"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id_"),
    )
    op.create_index(op.f("ix_receipts_user_id"),        "receipts", ["user_id"],        unique=False)
    op.create_index(op.f("ix_receipts_transaction_id"), "receipts", ["transaction_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_receipts_transaction_id"), table_name="receipts")
    op.drop_index(op.f("ix_receipts_user_id"),        table_name="receipts")
    op.drop_table("receipts")

