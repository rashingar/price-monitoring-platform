"""source url provenance

Revision ID: 20260523_0017
Revises: 20260519_0016
Create Date: 2026-05-23 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260523_0017"
down_revision = "20260519_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("source_urls") as batch:
        batch.add_column(sa.Column("provenance", sa.String(), nullable=True))
        batch.create_check_constraint(
            "ck_source_urls_provenance",
            "provenance IS NULL OR provenance IN ('manual', 'discovery', 'import', 'unknown')",
        )


def downgrade() -> None:
    with op.batch_alter_table("source_urls") as batch:
        batch.drop_constraint("ck_source_urls_provenance", type_="check")
        batch.drop_column("provenance")
