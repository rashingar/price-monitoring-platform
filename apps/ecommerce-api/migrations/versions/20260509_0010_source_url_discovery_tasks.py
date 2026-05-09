"""source url discovery task progress

Revision ID: 20260509_0010
Revises: 20260505_0009
Create Date: 2026-05-09 00:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260509_0010"
down_revision = "20260505_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_url_discovery_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("catalog_product_id", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("match_status", sa.String(), nullable=True),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["catalog_product_id"], ["catalog_products.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_source_url_discovery_tasks_run_id", "source_url_discovery_tasks", ["run_id"])
    op.create_index("ix_source_url_discovery_tasks_status", "source_url_discovery_tasks", ["status"])
    op.create_index("ix_source_url_discovery_tasks_model", "source_url_discovery_tasks", ["model"])
    op.create_index("ix_source_url_discovery_tasks_source_name", "source_url_discovery_tasks", ["source_name"])


def downgrade() -> None:
    op.drop_index("ix_source_url_discovery_tasks_source_name", table_name="source_url_discovery_tasks")
    op.drop_index("ix_source_url_discovery_tasks_model", table_name="source_url_discovery_tasks")
    op.drop_index("ix_source_url_discovery_tasks_status", table_name="source_url_discovery_tasks")
    op.drop_index("ix_source_url_discovery_tasks_run_id", table_name="source_url_discovery_tasks")
    op.drop_table("source_url_discovery_tasks")
