"""security events, password health, passkeys

Revision ID: c1d2e3f4a5b6
Revises: b9c0d1e2f3a4
Create Date: 2026-10-18 22:00:00.000000

Changes
-------
- security_events — login / security activity history (SEC-S1)
- users.password_changed_at / password_score / password_breached / password_checked_at (SEC-S4)
- users.webauthn_user_handle, webauthn_credentials, webauthn_challenges — passkeys (SEC-A1)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("password_score", sa.SmallInteger(), nullable=True))
    op.add_column("users", sa.Column("password_breached", sa.Boolean(), nullable=True))
    op.add_column("users", sa.Column("password_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("webauthn_user_handle", sa.LargeBinary(length=64), nullable=True))
    op.create_unique_constraint("uq_users_webauthn_user_handle", "users", ["webauthn_user_handle"])

    op.create_table(
        "security_events",
        sa.Column("id_", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id_", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("method", sa.String(length=16), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_security_events_user_id_created_at", "security_events", ["user_id", "created_at"])

    op.create_table(
        "webauthn_credentials",
        sa.Column("id_", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id_", ondelete="CASCADE"), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transports", sa.JSON(), nullable=True),
        sa.Column("aaguid", sa.String(length=36), nullable=True),
        sa.Column("backed_up", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_webauthn_credentials_user_id", "webauthn_credentials", ["user_id"])

    op.create_table(
        "webauthn_challenges",
        sa.Column("id_", sa.String(length=43), primary_key=True),
        sa.Column("challenge", sa.LargeBinary(), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id_", ondelete="CASCADE"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_webauthn_challenges_expires_at", "webauthn_challenges", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_webauthn_challenges_expires_at", table_name="webauthn_challenges")
    op.drop_table("webauthn_challenges")
    op.drop_index("ix_webauthn_credentials_user_id", table_name="webauthn_credentials")
    op.drop_table("webauthn_credentials")
    op.drop_index("ix_security_events_user_id_created_at", table_name="security_events")
    op.drop_table("security_events")
    op.drop_constraint("uq_users_webauthn_user_handle", "users", type_="unique")
    for column in ("webauthn_user_handle", "password_checked_at", "password_breached", "password_score", "password_changed_at"):
        op.drop_column("users", column)
