"""e-mail notifications, password reset codes, receipt_files

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-11-08 12:00:00.000000

Changes
-------
- password_reset_codes — e-mailed one-time codes (HMAC only) for /api/auth/password-reset/*
- sent_notifications — at-most-once log of notification e-mails, unique (user_id, key)
- notification_preferences.language — language of notification e-mails
- receipt_files — receipt bytes for FILE_STORAGE=database. The model was added without a
  migration; databases created by `scripts/init_db` (create_all) already have it, so it is
  created only when missing.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("receipt_files"):
        op.create_table(
            "receipt_files",
            sa.Column("id_", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id_", ondelete="CASCADE"), nullable=False),
            sa.Column("file_path", sa.String(length=512), nullable=False, unique=True),
            sa.Column("data", sa.LargeBinary(), nullable=False),
        )
        op.create_index("ix_receipt_files_user_id", "receipt_files", ["user_id"])

    op.add_column(
        "notification_preferences",
        sa.Column("language", sa.String(length=8), nullable=False, server_default="uk"),
    )

    op.create_table(
        "password_reset_codes",
        sa.Column("id_", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id_", ondelete="CASCADE"), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_password_reset_codes_user_id_created_at", "password_reset_codes", ["user_id", "created_at"])

    op.create_table(
        "sent_notifications",
        sa.Column("id_", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id_", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "key", name="uq_sent_notifications_user_key"),
    )


def downgrade() -> None:
    op.drop_table("sent_notifications")
    op.drop_index("ix_password_reset_codes_user_id_created_at", table_name="password_reset_codes")
    op.drop_table("password_reset_codes")
    op.drop_column("notification_preferences", "language")
    # receipt_files is left in place: older revisions' models expect it too
