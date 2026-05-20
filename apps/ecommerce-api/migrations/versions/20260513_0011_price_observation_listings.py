"""price observation listings

Revision ID: 20260513_0011
Revises: 20260509_0010
Create Date: 2026-05-13 00:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260513_0011"
down_revision = "20260509_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_observation_listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("price_observation_id", sa.Integer(), nullable=False),
        sa.Column("monitoring_run_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("observation_batch_id", sa.String(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("product_source_id", sa.Integer(), nullable=True),
        sa.Column("source_capture_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("vendor_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("seller_name", sa.String(), nullable=True),
        sa.Column("seller_url", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("original_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(), nullable=False, server_default="EUR"),
        sa.Column("availability", sa.String(), nullable=True),
        sa.Column("stock_status", sa.String(), nullable=True),
        sa.Column("shipping_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("delivery_text", sa.Text(), nullable=True),
        sa.Column("product_url", sa.Text(), nullable=True),
        sa.Column(
            "raw_listing",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["price_observation_id"], ["price_observations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["monitoring_run_id"], ["monitoring_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["product_source_id"], ["product_sources.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_capture_snapshot_id"],
            ["source_capture_snapshots.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_price_observation_listings_price_observation_id",
        "price_observation_listings",
        ["price_observation_id"],
    )
    op.create_index(
        "ix_price_observation_listings_run_id", "price_observation_listings", ["run_id"]
    )
    op.create_index(
        "ix_price_observation_listings_observation_batch_id",
        "price_observation_listings",
        ["observation_batch_id"],
    )
    op.create_index(
        "ix_price_observation_listings_product_id",
        "price_observation_listings",
        ["product_id"],
    )
    op.create_index(
        "ix_price_observation_listings_source_capture_snapshot_id",
        "price_observation_listings",
        ["source_capture_snapshot_id"],
    )
    op.create_index(
        "ix_price_observation_listings_run_product_price",
        "price_observation_listings",
        ["run_id", "product_id", "price"],
    )
    op.create_index(
        "ix_price_observation_listings_observation_rank",
        "price_observation_listings",
        ["price_observation_id", "rank"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_price_observation_listings_observation_rank",
        table_name="price_observation_listings",
    )
    op.drop_index(
        "ix_price_observation_listings_run_product_price",
        table_name="price_observation_listings",
    )
    op.drop_index(
        "ix_price_observation_listings_source_capture_snapshot_id",
        table_name="price_observation_listings",
    )
    op.drop_index(
        "ix_price_observation_listings_product_id",
        table_name="price_observation_listings",
    )
    op.drop_index(
        "ix_price_observation_listings_observation_batch_id",
        table_name="price_observation_listings",
    )
    op.drop_index(
        "ix_price_observation_listings_run_id", table_name="price_observation_listings"
    )
    op.drop_index(
        "ix_price_observation_listings_price_observation_id",
        table_name="price_observation_listings",
    )
    op.drop_table("price_observation_listings")
