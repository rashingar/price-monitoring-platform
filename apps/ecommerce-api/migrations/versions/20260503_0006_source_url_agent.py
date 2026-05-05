"""source url discovery agent tables

Revision ID: 20260503_0006
Revises: 20260503_0005
Create Date: 2026-05-03 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260503_0006"
down_revision = "20260503_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_url_discovery_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_path", sa.Text(), nullable=True),
        sa.Column("filters_json", _json_type(), nullable=True),
        sa.Column("selected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("needs_review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("not_found_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_source_url_discovery_runs_run_id", "source_url_discovery_runs", ["run_id"], unique=True)
    op.create_index("ix_source_url_discovery_runs_source_name", "source_url_discovery_runs", ["source_name"])
    op.create_index("ix_source_url_discovery_runs_status", "source_url_discovery_runs", ["status"])
    op.create_index("ix_source_url_discovery_runs_created_at", "source_url_discovery_runs", ["created_at"])

    op.create_table(
        "source_url_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("catalog_product_id", sa.Integer(), nullable=True),
        sa.Column("catalog_source", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("mpn", sa.String(), nullable=False, server_default=""),
        sa.Column("manufacturer", sa.String(), nullable=False, server_default=""),
        sa.Column("product_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.Text(), nullable=False, server_default=""),
        sa.Column("own_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("source_domain", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("expected_listing", sa.String(), nullable=True),
        sa.Column("candidate_url", sa.Text(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("candidate_title", sa.Text(), nullable=True),
        sa.Column("candidate_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("match_status", sa.String(), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("match_method", sa.String(), nullable=False, server_default=""),
        sa.Column("evidence_json", _json_type(), nullable=True),
        sa.Column("competing_candidates_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("searched_queries_json", _json_type(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'needs_review', 'not_found', 'error')",
            name="ck_source_url_candidates_status",
        ),
        sa.ForeignKeyConstraint(["catalog_product_id"], ["catalog_products.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_source_url_candidates_run_id", "source_url_candidates", ["run_id"])
    op.create_index("ix_source_url_candidates_catalog_product_id", "source_url_candidates", ["catalog_product_id"])
    op.create_index("ix_source_url_candidates_source_name", "source_url_candidates", ["source_name"])
    op.create_index("ix_source_url_candidates_match_status", "source_url_candidates", ["match_status"])
    op.create_index("ix_source_url_candidates_status", "source_url_candidates", ["status"])
    op.create_index("ix_source_url_candidates_created_at", "source_url_candidates", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_source_url_candidates_created_at", table_name="source_url_candidates")
    op.drop_index("ix_source_url_candidates_status", table_name="source_url_candidates")
    op.drop_index("ix_source_url_candidates_match_status", table_name="source_url_candidates")
    op.drop_index("ix_source_url_candidates_source_name", table_name="source_url_candidates")
    op.drop_index("ix_source_url_candidates_catalog_product_id", table_name="source_url_candidates")
    op.drop_index("ix_source_url_candidates_run_id", table_name="source_url_candidates")
    op.drop_table("source_url_candidates")
    op.drop_index("ix_source_url_discovery_runs_created_at", table_name="source_url_discovery_runs")
    op.drop_index("ix_source_url_discovery_runs_status", table_name="source_url_discovery_runs")
    op.drop_index("ix_source_url_discovery_runs_source_name", table_name="source_url_discovery_runs")
    op.drop_index("uq_source_url_discovery_runs_run_id", table_name="source_url_discovery_runs")
    op.drop_table("source_url_discovery_runs")


def _json_type() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
