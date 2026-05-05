"""ui view preferences

Revision ID: 20260504_0007
Revises: 20260503_0006
Create Date: 2026-05-04 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260504_0007"
down_revision = "20260503_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ui_view_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("view_key", sa.String(), nullable=False),
        sa.Column("user_key", sa.String(), nullable=False, server_default="default"),
        sa.Column("preferences_json", _json_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("view_key", "user_key", name="uq_ui_view_preferences_view_user"),
    )
    op.create_index("ix_ui_view_preferences_view_key", "ui_view_preferences", ["view_key"])


def downgrade() -> None:
    op.drop_index("ix_ui_view_preferences_view_key", table_name="ui_view_preferences")
    op.drop_table("ui_view_preferences")


def _json_type() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
