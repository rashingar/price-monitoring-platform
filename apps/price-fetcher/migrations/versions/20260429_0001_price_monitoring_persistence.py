"""price monitoring persistence

Revision ID: 20260429_0001
Revises:
Create Date: 2026-04-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260429_0001"
down_revision = None
branch_labels = None
depends_on = None


def _json_document() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("catalog_source", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("mpn", sa.String(), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("manufacturer", sa.String(), nullable=True),
        sa.Column("family", sa.String(), nullable=True),
        sa.Column("category_name", sa.String(), nullable=True),
        sa.Column("sub_category", sa.String(), nullable=True),
        sa.Column("current_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(), nullable=False, server_default="EUR"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("raw_catalog_row", _json_document(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_products_catalog_source_model_present",
        "products",
        ["catalog_source", "model"],
        unique=True,
        postgresql_where=sa.text("model IS NOT NULL AND model <> ''"),
    )
    op.create_index("ix_products_catalog_source_mpn", "products", ["catalog_source", "mpn"])
    op.create_index("ix_products_manufacturer", "products", ["manufacturer"])
    op.create_index("ix_products_family", "products", ["family"])
    op.create_index("ix_products_category_name", "products", ["category_name"])
    op.create_index("ix_products_sub_category", "products", ["sub_category"])

    op.create_table(
        "monitoring_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("trigger_type", sa.String(), nullable=False, server_default="manual"),
        sa.Column("output_dir", sa.Text(), nullable=True),
        sa.Column("input_csv_path", sa.Text(), nullable=True),
        sa.Column("selection_summary_path", sa.Text(), nullable=True),
        sa.Column("fetch_result_path", sa.Text(), nullable=True),
        sa.Column("enriched_csv_path", sa.Text(), nullable=True),
        sa.Column("fetch_summary_path", sa.Text(), nullable=True),
        sa.Column("selected_count", sa.Integer(), nullable=True),
        sa.Column("skipped_count", sa.Integer(), nullable=True),
        sa.Column("fetch_attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_was_refetch", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_monitoring_runs_run_id", "monitoring_runs", ["run_id"], unique=True)
    op.create_index("ix_monitoring_runs_created_at", "monitoring_runs", ["created_at"])
    op.create_index("ix_monitoring_runs_source", "monitoring_runs", ["source"])
    op.create_index("ix_monitoring_runs_status", "monitoring_runs", ["status"])

    op.create_table(
        "catalog_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "monitoring_run_id",
            sa.Integer(),
            sa.ForeignKey("monitoring_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("catalog_source", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("mpn", sa.String(), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("manufacturer", sa.String(), nullable=True),
        sa.Column("family", sa.String(), nullable=True),
        sa.Column("category_name", sa.String(), nullable=True),
        sa.Column("sub_category", sa.String(), nullable=True),
        sa.Column("marketplace", sa.String(), nullable=True),
        sa.Column("own_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(), nullable=False, server_default="EUR"),
        sa.Column("raw_catalog_row", _json_document(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_catalog_snapshots_run_id", "catalog_snapshots", ["run_id"])
    op.create_index("ix_catalog_snapshots_product_id", "catalog_snapshots", ["product_id"])
    op.create_index("ix_catalog_snapshots_catalog_source_model", "catalog_snapshots", ["catalog_source", "model"])
    op.create_index("ix_catalog_snapshots_catalog_source_mpn", "catalog_snapshots", ["catalog_source", "mpn"])
    op.create_index("ix_catalog_snapshots_category_name", "catalog_snapshots", ["category_name"])
    op.create_index("ix_catalog_snapshots_family", "catalog_snapshots", ["family"])
    op.create_index("ix_catalog_snapshots_manufacturer", "catalog_snapshots", ["manufacturer"])
    op.create_index("ix_catalog_snapshots_sub_category", "catalog_snapshots", ["sub_category"])
    op.create_index(
        "uq_catalog_snapshots_run_catalog_model_present",
        "catalog_snapshots",
        ["run_id", "catalog_source", "model"],
        unique=True,
        postgresql_where=sa.text("model IS NOT NULL AND model <> ''"),
    )
    op.create_index(
        "uq_catalog_snapshots_run_catalog_mpn_present",
        "catalog_snapshots",
        ["run_id", "catalog_source", "mpn"],
        unique=True,
        postgresql_where=sa.text("(model IS NULL OR model = '') AND mpn IS NOT NULL AND mpn <> ''"),
    )

    op.create_table(
        "price_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "monitoring_run_id",
            sa.Integer(),
            sa.ForeignKey("monitoring_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("catalog_source", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("mpn", sa.String(), nullable=True),
        sa.Column("product_name", sa.Text(), nullable=True),
        sa.Column("competitor_name", sa.String(), nullable=True),
        sa.Column("competitor_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(), nullable=False, server_default="EUR"),
        sa.Column("availability", sa.String(), nullable=True),
        sa.Column("product_url", sa.Text(), nullable=True),
        sa.Column("own_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("price_delta", sa.Numeric(12, 2), nullable=True),
        sa.Column("price_delta_percent", sa.Numeric(12, 4), nullable=True),
        sa.Column("raw_observation", _json_document(), nullable=True),
        sa.Column("matched_by", sa.String(), nullable=True),
        sa.Column("match_status", sa.String(), nullable=False, server_default="unmatched"),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_price_observations_run_id", "price_observations", ["run_id"])
    op.create_index("ix_price_observations_product_id", "price_observations", ["product_id"])
    op.create_index("ix_price_observations_catalog_source_model", "price_observations", ["catalog_source", "model"])
    op.create_index("ix_price_observations_catalog_source_mpn", "price_observations", ["catalog_source", "mpn"])
    op.create_index("ix_price_observations_source", "price_observations", ["source"])
    op.create_index("ix_price_observations_observed_at", "price_observations", ["observed_at"])
    op.create_index("ix_price_observations_competitor_price", "price_observations", ["competitor_price"])
    op.create_index("ix_price_observations_match_status", "price_observations", ["match_status"])


def downgrade() -> None:
    op.drop_index("ix_price_observations_match_status", table_name="price_observations")
    op.drop_index("ix_price_observations_competitor_price", table_name="price_observations")
    op.drop_index("ix_price_observations_observed_at", table_name="price_observations")
    op.drop_index("ix_price_observations_source", table_name="price_observations")
    op.drop_index("ix_price_observations_catalog_source_mpn", table_name="price_observations")
    op.drop_index("ix_price_observations_catalog_source_model", table_name="price_observations")
    op.drop_index("ix_price_observations_product_id", table_name="price_observations")
    op.drop_index("ix_price_observations_run_id", table_name="price_observations")
    op.drop_table("price_observations")

    op.drop_index("uq_catalog_snapshots_run_catalog_mpn_present", table_name="catalog_snapshots")
    op.drop_index("uq_catalog_snapshots_run_catalog_model_present", table_name="catalog_snapshots")
    op.drop_index("ix_catalog_snapshots_sub_category", table_name="catalog_snapshots")
    op.drop_index("ix_catalog_snapshots_manufacturer", table_name="catalog_snapshots")
    op.drop_index("ix_catalog_snapshots_family", table_name="catalog_snapshots")
    op.drop_index("ix_catalog_snapshots_category_name", table_name="catalog_snapshots")
    op.drop_index("ix_catalog_snapshots_catalog_source_mpn", table_name="catalog_snapshots")
    op.drop_index("ix_catalog_snapshots_catalog_source_model", table_name="catalog_snapshots")
    op.drop_index("ix_catalog_snapshots_product_id", table_name="catalog_snapshots")
    op.drop_index("ix_catalog_snapshots_run_id", table_name="catalog_snapshots")
    op.drop_table("catalog_snapshots")

    op.drop_index("ix_monitoring_runs_status", table_name="monitoring_runs")
    op.drop_index("ix_monitoring_runs_source", table_name="monitoring_runs")
    op.drop_index("ix_monitoring_runs_created_at", table_name="monitoring_runs")
    op.drop_index("uq_monitoring_runs_run_id", table_name="monitoring_runs")
    op.drop_table("monitoring_runs")

    op.drop_index("ix_products_sub_category", table_name="products")
    op.drop_index("ix_products_category_name", table_name="products")
    op.drop_index("ix_products_family", table_name="products")
    op.drop_index("ix_products_manufacturer", table_name="products")
    op.drop_index("ix_products_catalog_source_mpn", table_name="products")
    op.drop_index("uq_products_catalog_source_model_present", table_name="products")
    op.drop_table("products")
