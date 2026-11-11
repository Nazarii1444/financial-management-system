"""add settings fields: avatar_url, subscription_plan, notification_preferences

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-04 17:00:00.000000

Changes
-------
- users: add avatar_url (String 512, nullable)
- users: add subscription_plan enum column (default FREE)
- create notification_preferences table (1:1 with users)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

subscription_plan_enum = sa.Enum("FREE", "PRO", name="subscriptionplan")


def upgrade() -> None:
    # ── 1. New columns on users ───────────────────────────────────────────────
    op.add_column("users", sa.Column("avatar_url", sa.String(512), nullable=True))

    subscription_plan_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "users",
        sa.Column(
            "subscription_plan",
            subscription_plan_enum,
            nullable=False,
            server_default="FREE",
        ),
    )

    # ── 2. notification_preferences table ────────────────────────────────────
    op.create_table(
        "notification_preferences",
        sa.Column("id_", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        # channel toggles
        sa.Column("email_enabled",         sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("push_enabled",          sa.Boolean(), nullable=False, server_default="false"),
        # event toggles
        sa.Column("budget_limit_alerts",   sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("recurring_reminders",   sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("goal_milestone_alerts", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("monthly_summary",       sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id_"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id_"),
        sa.UniqueConstraint("user_id", name="uq_notification_preferences_user_id"),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_column("users", "subscription_plan")
    subscription_plan_enum.drop(op.get_bind(), checkfirst=True)
    op.drop_column("users", "avatar_url")

