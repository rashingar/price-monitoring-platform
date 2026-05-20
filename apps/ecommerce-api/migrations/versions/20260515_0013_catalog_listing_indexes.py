"""catalog listing source url coverage index

Revision ID: 20260515_0013
Revises: 20260513_0012
Create Date: 2026-05-15 12:00:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "20260515_0013"
down_revision = "20260513_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_source_urls_catalog_product_status_source",
        "source_urls",
        ["catalog_product_id", "status", "source_name"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_urls_catalog_product_status_source", table_name="source_urls"
    )
