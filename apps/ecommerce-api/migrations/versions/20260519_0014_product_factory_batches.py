"""product factory csv batch intake

Revision ID: 20260519_0014
Revises: 20260515_0013
Create Date: 2026-05-19 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260519_0014"
down_revision = "20260515_0013"
branch_labels = None
depends_on = None

JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "product_factory_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="uploaded"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "auto_selected_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "manually_selected_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "needs_review_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "no_usable_source_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "resolution_failed_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", JSON_DOCUMENT, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('uploaded', 'resolving', 'resolved', 'resolved_with_errors')",
            name="ck_product_factory_batches_status",
        ),
    )
    op.create_index(
        "ix_product_factory_batches_status", "product_factory_batches", ["status"]
    )
    op.create_index(
        "ix_product_factory_batches_created_at",
        "product_factory_batches",
        ["created_at"],
    )

    op.create_table(
        "product_factory_batch_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("product_factory_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=False, server_default=""),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("queries_json", JSON_DOCUMENT, nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("selected_url", sa.Text(), nullable=True),
        sa.Column("selected_source", sa.String(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("candidate_urls_json", JSON_DOCUMENT, nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("selection_metadata_json", JSON_DOCUMENT, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'auto_selected', 'manually_selected', 'needs_review', 'no_usable_source', 'resolution_failed', 'skipped')",
            name="ck_product_factory_batch_rows_status",
        ),
    )
    op.create_index(
        "ix_product_factory_batch_rows_batch_id",
        "product_factory_batch_rows",
        ["batch_id"],
    )
    op.create_index(
        "ix_product_factory_batch_rows_status", "product_factory_batch_rows", ["status"]
    )
    op.create_index(
        "ix_product_factory_batch_rows_model", "product_factory_batch_rows", ["model"]
    )
    op.create_index(
        "ix_product_factory_batch_rows_created_at",
        "product_factory_batch_rows",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_product_factory_batch_rows_created_at",
        table_name="product_factory_batch_rows",
    )
    op.drop_index(
        "ix_product_factory_batch_rows_model", table_name="product_factory_batch_rows"
    )
    op.drop_index(
        "ix_product_factory_batch_rows_status", table_name="product_factory_batch_rows"
    )
    op.drop_index(
        "ix_product_factory_batch_rows_batch_id",
        table_name="product_factory_batch_rows",
    )
    op.drop_table("product_factory_batch_rows")
    op.drop_index(
        "ix_product_factory_batches_created_at", table_name="product_factory_batches"
    )
    op.drop_index(
        "ix_product_factory_batches_status", table_name="product_factory_batches"
    )
    op.drop_table("product_factory_batches")
