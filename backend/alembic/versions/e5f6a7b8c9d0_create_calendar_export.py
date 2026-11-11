"""create calendar export tables

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-18 16:00:00.000000

Changes
-------
- Create calendar_feeds (secret iCalendar subscription token per user)
- Create google_calendar_links (Google Calendar API connection per user)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calendar_feeds",
        sa.Column("id_", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("lang", sa.String(length=8), nullable=False, server_default="uk"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id_"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id_"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_calendar_feeds_token"), "calendar_feeds", ["token"], unique=True)

    op.create_table(
        "google_calendar_links",
        sa.Column("id_", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calendar_id", sa.String(length=255), nullable=True),
        sa.Column("lang", sa.String(length=8), nullable=False, server_default="uk"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id_"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id_"),
        sa.UniqueConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("google_calendar_links")
    op.drop_index(op.f("ix_calendar_feeds_token"), table_name="calendar_feeds")
    op.drop_table("calendar_feeds")
