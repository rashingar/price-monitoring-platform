"""unified product sources and source capture

Revision ID: 20260503_0005
Revises: 20260429_0004
Create Date: 2026-05-03 00:00:00.000000
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260503_0005"
down_revision = "20260429_0004"
branch_labels = None
depends_on = None


VENDORS = [
    ("electronet", "Electronet", "https://www.electronet.gr", "direct_vendor", True, True, False, False),
    ("skroutz", "Skroutz", "https://www.skroutz.gr", "marketplace_or_aggregator", True, True, True, True),
    ("bestprice", "BestPrice", "https://www.bestprice.gr", "marketplace_or_aggregator", True, True, True, False),
    ("plaisio", "Plaisio", "https://www.plaisio.gr", "direct_vendor", False, True, False, False),
    ("public", "Public", "https://www.public.gr", "direct_vendor", False, True, False, False),
    ("kotsovolos", "Kotsovolos", "https://www.kotsovolos.gr", "direct_vendor", False, True, False, False),
]


def upgrade() -> None:
    op.create_table(
        "vendors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("vendor_type", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("supports_direct_product_url", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("supports_search", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("supports_xhr_capture", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_vendors_slug", "vendors", ["slug"], unique=True)
    op.create_index("ix_vendors_active", "vendors", ["active"])
    op.create_index("ix_vendors_vendor_type", "vendors", ["vendor_type"])
    _seed_vendors()

    op.create_table(
        "product_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("vendor_id", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("canonical_url_hash", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False, server_default="direct_product_url"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_fetch_status", sa.String(), nullable=True),
        sa.Column("last_error_code", sa.String(), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("last_parser_version", sa.String(), nullable=True),
        sa.Column("last_capture_strategy", sa.String(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(), nullable=True),
        sa.Column("data_quality_flags", _json_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("product_id", "canonical_url_hash", name="uq_product_sources_product_canonical_url_hash"),
    )
    op.create_index("ix_product_sources_product_id", "product_sources", ["product_id"])
    op.create_index("ix_product_sources_vendor_id", "product_sources", ["vendor_id"])
    op.create_index("ix_product_sources_canonical_url_hash", "product_sources", ["canonical_url_hash"])
    op.create_index("ix_product_sources_active", "product_sources", ["active"])
    op.create_index("ix_product_sources_last_seen_at", "product_sources", ["last_seen_at"])
    op.create_index("ix_product_sources_last_success_at", "product_sources", ["last_success_at"])

    op.create_table(
        "source_capture_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("product_source_id", sa.Integer(), nullable=True),
        sa.Column("vendor_id", sa.Integer(), nullable=True),
        sa.Column("capture_strategy", sa.String(), nullable=False),
        sa.Column("page_url", sa.Text(), nullable=True),
        sa.Column("final_url", sa.Text(), nullable=True),
        sa.Column("request_url", sa.Text(), nullable=True),
        sa.Column("request_method", sa.String(), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_content_type", sa.String(), nullable=True),
        sa.Column("response_body_json", _json_type(), nullable=True),
        sa.Column("response_body_text_ref", sa.Text(), nullable=True),
        sa.Column("raw_html_ref", sa.Text(), nullable=True),
        sa.Column("artifact_ref", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=True),
        sa.Column("parser_version", sa.String(), nullable=True),
        sa.Column("capture_version", sa.String(), nullable=True),
        sa.Column("playwright_version", sa.String(), nullable=True),
        sa.Column("fetch_status_code", sa.Integer(), nullable=True),
        sa.Column("fetch_latency_ms", sa.Integer(), nullable=True),
        sa.Column("candidate_score", sa.Integer(), nullable=True),
        sa.Column("candidate_reason", sa.Text(), nullable=True),
        sa.Column("network_event_type", sa.String(), nullable=True),
        sa.Column("trigger_action", sa.String(), nullable=True),
        sa.Column("data_quality_flags", _json_type(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_source_id"], ["product_sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_source_capture_snapshots_product_source_id_captured_at",
        "source_capture_snapshots",
        ["product_source_id", "captured_at"],
    )
    op.create_index("ix_source_capture_snapshots_product_id", "source_capture_snapshots", ["product_id"])
    op.create_index("ix_source_capture_snapshots_vendor_id", "source_capture_snapshots", ["vendor_id"])
    op.create_index("ix_source_capture_snapshots_content_hash", "source_capture_snapshots", ["content_hash"])

    with op.batch_alter_table("price_observations") as batch:
        batch.alter_column("monitoring_run_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("product_source_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("vendor_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("source_capture_snapshot_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("original_price", sa.Numeric(12, 2), nullable=True))
        batch.add_column(sa.Column("discount_percent", sa.Numeric(6, 2), nullable=True))
        batch.add_column(sa.Column("stock_status", sa.String(), nullable=True))
        batch.add_column(sa.Column("shipping_cost", sa.Numeric(12, 2), nullable=True))
        batch.add_column(sa.Column("delivery_text", sa.Text(), nullable=True))
        batch.add_column(sa.Column("seller_name", sa.String(), nullable=True))
        batch.add_column(sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("timestamp_source", sa.String(), nullable=True))
        batch.add_column(sa.Column("timestamp_quality", sa.String(), nullable=True))
        batch.create_foreign_key("fk_price_observations_product_source_id", "product_sources", ["product_source_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_price_observations_vendor_id", "vendors", ["vendor_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key(
            "fk_price_observations_source_capture_snapshot_id",
            "source_capture_snapshots",
            ["source_capture_snapshot_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_price_observations_product_source_id_observed_at", ["product_source_id", "observed_at"])
        batch.create_index("ix_price_observations_vendor_id_observed_at", ["vendor_id", "observed_at"])

    op.create_table(
        "offer_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("product_source_id", sa.Integer(), nullable=True),
        sa.Column("aggregator_vendor_id", sa.Integer(), nullable=True),
        sa.Column("source_capture_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("seller_name", sa.String(), nullable=True),
        sa.Column("seller_url", sa.Text(), nullable=True),
        sa.Column("seller_vendor_id", sa.Integer(), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("original_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(), nullable=False, server_default="EUR"),
        sa.Column("availability", sa.String(), nullable=True),
        sa.Column("stock_status", sa.String(), nullable=True),
        sa.Column("shipping_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("delivery_text", sa.Text(), nullable=True),
        sa.Column("raw_observation", _json_type(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timestamp_source", sa.String(), nullable=True),
        sa.Column("timestamp_quality", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_source_id"], ["product_sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["aggregator_vendor_id"], ["vendors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_capture_snapshot_id"], ["source_capture_snapshots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["seller_vendor_id"], ["vendors.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_offer_observations_product_id_observed_at", "offer_observations", ["product_id", "observed_at"])
    op.create_index("ix_offer_observations_product_source_id_observed_at", "offer_observations", ["product_source_id", "observed_at"])
    op.create_index("ix_offer_observations_aggregator_vendor_id", "offer_observations", ["aggregator_vendor_id"])
    op.create_index("ix_offer_observations_seller_vendor_id", "offer_observations", ["seller_vendor_id"])


def downgrade() -> None:
    op.drop_index("ix_offer_observations_seller_vendor_id", table_name="offer_observations")
    op.drop_index("ix_offer_observations_aggregator_vendor_id", table_name="offer_observations")
    op.drop_index("ix_offer_observations_product_source_id_observed_at", table_name="offer_observations")
    op.drop_index("ix_offer_observations_product_id_observed_at", table_name="offer_observations")
    op.drop_table("offer_observations")
    with op.batch_alter_table("price_observations") as batch:
        batch.drop_index("ix_price_observations_vendor_id_observed_at")
        batch.drop_index("ix_price_observations_product_source_id_observed_at")
        batch.drop_constraint("fk_price_observations_source_capture_snapshot_id", type_="foreignkey")
        batch.drop_constraint("fk_price_observations_vendor_id", type_="foreignkey")
        batch.drop_constraint("fk_price_observations_product_source_id", type_="foreignkey")
        batch.drop_column("timestamp_quality")
        batch.drop_column("timestamp_source")
        batch.drop_column("parsed_at")
        batch.drop_column("fetched_at")
        batch.drop_column("seller_name")
        batch.drop_column("delivery_text")
        batch.drop_column("shipping_cost")
        batch.drop_column("stock_status")
        batch.drop_column("discount_percent")
        batch.drop_column("original_price")
        batch.drop_column("source_capture_snapshot_id")
        batch.drop_column("vendor_id")
        batch.drop_column("product_source_id")
        batch.alter_column("monitoring_run_id", existing_type=sa.Integer(), nullable=False)
    op.drop_index("ix_source_capture_snapshots_content_hash", table_name="source_capture_snapshots")
    op.drop_index("ix_source_capture_snapshots_vendor_id", table_name="source_capture_snapshots")
    op.drop_index("ix_source_capture_snapshots_product_id", table_name="source_capture_snapshots")
    op.drop_index("ix_source_capture_snapshots_product_source_id_captured_at", table_name="source_capture_snapshots")
    op.drop_table("source_capture_snapshots")
    op.drop_index("ix_product_sources_last_success_at", table_name="product_sources")
    op.drop_index("ix_product_sources_last_seen_at", table_name="product_sources")
    op.drop_index("ix_product_sources_active", table_name="product_sources")
    op.drop_index("ix_product_sources_canonical_url_hash", table_name="product_sources")
    op.drop_index("ix_product_sources_vendor_id", table_name="product_sources")
    op.drop_index("ix_product_sources_product_id", table_name="product_sources")
    op.drop_table("product_sources")
    op.drop_index("ix_vendors_vendor_type", table_name="vendors")
    op.drop_index("ix_vendors_active", table_name="vendors")
    op.drop_index("uq_vendors_slug", table_name="vendors")
    op.drop_table("vendors")


def _seed_vendors() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = [
        {
            "slug": slug,
            "name": name,
            "base_url": base_url,
            "vendor_type": vendor_type,
            "active": active,
            "supports_direct_product_url": direct,
            "supports_search": search,
            "supports_xhr_capture": xhr,
            "created_at": now,
            "updated_at": now,
        }
        for slug, name, base_url, vendor_type, active, direct, search, xhr in VENDORS
    ]
    op.bulk_insert(sa.table("vendors", *[sa.column(key) for key in rows[0].keys()]), rows)


def _json_type() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
