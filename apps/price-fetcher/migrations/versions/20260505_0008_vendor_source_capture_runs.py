"""vendor source capture run history

Revision ID: 20260505_0008
Revises: 20260504_0007
Create Date: 2026-05-05 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260505_0008"
down_revision = "20260504_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vendor_source_capture_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source_filter", sa.String(), nullable=True),
        sa.Column("catalog_source", sa.String(), nullable=True),
        sa.Column("selected_catalog_product_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selected_source_url_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selected_product_source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warnings_json", _json_type(), nullable=True),
        sa.Column("filters_json", _json_type(), nullable=True),
        sa.Column("artifact_refs_json", _json_type(), nullable=True),
        sa.Column("result_path", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_vendor_source_capture_runs_run_id", "vendor_source_capture_runs", ["run_id"], unique=True)
    op.create_index("ix_vendor_source_capture_runs_status", "vendor_source_capture_runs", ["status"])
    op.create_index("ix_vendor_source_capture_runs_source_filter", "vendor_source_capture_runs", ["source_filter"])
    op.create_index("ix_vendor_source_capture_runs_catalog_source", "vendor_source_capture_runs", ["catalog_source"])
    op.create_index("ix_vendor_source_capture_runs_created_at", "vendor_source_capture_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_vendor_source_capture_runs_created_at", table_name="vendor_source_capture_runs")
    op.drop_index("ix_vendor_source_capture_runs_catalog_source", table_name="vendor_source_capture_runs")
    op.drop_index("ix_vendor_source_capture_runs_source_filter", table_name="vendor_source_capture_runs")
    op.drop_index("ix_vendor_source_capture_runs_status", table_name="vendor_source_capture_runs")
    op.drop_index("uq_vendor_source_capture_runs_run_id", table_name="vendor_source_capture_runs")
    op.drop_table("vendor_source_capture_runs")


def _json_type() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
