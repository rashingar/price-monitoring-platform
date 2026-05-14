"""Price Monitoring run, snapshot, observation, and listing models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, false, text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ecommerce.db.models.base import Base, JSON_DOCUMENT


class MonitoringRun(Base):
    __tablename__ = "monitoring_runs"
    __table_args__ = (
        Index("uq_monitoring_runs_run_id", "run_id", unique=True),
        Index("ix_monitoring_runs_source", "source"),
        Index("ix_monitoring_runs_status", "status"),
        Index("ix_monitoring_runs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String, nullable=False, default="manual", server_default="manual")
    output_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_csv_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    selection_summary_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetch_result_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    enriched_csv_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetch_summary_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skipped_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetch_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_was_refetch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    catalog_snapshots: Mapped[list["CatalogSnapshot"]] = relationship(
        back_populates="monitoring_run",
        cascade="all, delete-orphan",
    )
    price_observations: Mapped[list["PriceObservation"]] = relationship(
        back_populates="monitoring_run",
        cascade="all, delete-orphan",
    )
    alert_events: Mapped[list["AlertEvent"]] = relationship(back_populates="monitoring_run")
class CatalogSnapshot(Base):
    __tablename__ = "catalog_snapshots"
    __table_args__ = (
        Index("ix_catalog_snapshots_run_id", "run_id"),
        Index("ix_catalog_snapshots_product_id", "product_id"),
        Index("ix_catalog_snapshots_catalog_source_model", "catalog_source", "model"),
        Index("ix_catalog_snapshots_catalog_source_mpn", "catalog_source", "mpn"),
        Index("ix_catalog_snapshots_manufacturer", "manufacturer"),
        Index("ix_catalog_snapshots_family", "family"),
        Index("ix_catalog_snapshots_category_name", "category_name"),
        Index("ix_catalog_snapshots_sub_category", "sub_category"),
        Index(
            "uq_catalog_snapshots_run_catalog_model_present",
            "run_id",
            "catalog_source",
            "model",
            unique=True,
            postgresql_where=text("model IS NOT NULL AND model <> ''"),
            sqlite_where=text("model IS NOT NULL AND model <> ''"),
        ),
        Index(
            "uq_catalog_snapshots_run_catalog_mpn_present",
            "run_id",
            "catalog_source",
            "mpn",
            unique=True,
            postgresql_where=text("(model IS NULL OR model = '') AND mpn IS NOT NULL AND mpn <> ''"),
            sqlite_where=text("(model IS NULL OR model = '') AND mpn IS NOT NULL AND mpn <> ''"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monitoring_run_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    catalog_source: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    mpn: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String, nullable=True)
    family: Mapped[str | None] = mapped_column(String, nullable=True)
    category_name: Mapped[str | None] = mapped_column(String, nullable=True)
    sub_category: Mapped[str | None] = mapped_column(String, nullable=True)
    marketplace: Mapped[str | None] = mapped_column(String, nullable=True)
    own_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="EUR", server_default="EUR")
    raw_catalog_row: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    monitoring_run: Mapped[MonitoringRun] = relationship(back_populates="catalog_snapshots")
    product: Mapped[Product | None] = relationship(back_populates="catalog_snapshots")
class PriceObservation(Base):
    __tablename__ = "price_observations"
    __table_args__ = (
        Index("ix_price_observations_run_id", "run_id"),
        Index("ix_price_observations_observation_batch_id", "observation_batch_id"),
        Index("ix_price_observations_product_id", "product_id"),
        Index("ix_price_observations_product_source_id_observed_at", "product_source_id", "observed_at"),
        Index("ix_price_observations_vendor_id_observed_at", "vendor_id", "observed_at"),
        Index("ix_price_observations_catalog_source_model", "catalog_source", "model"),
        Index("ix_price_observations_catalog_source_mpn", "catalog_source", "mpn"),
        Index("ix_price_observations_source", "source"),
        Index("ix_price_observations_observed_at", "observed_at"),
        Index("ix_price_observations_competitor_price", "competitor_price"),
        Index("ix_price_observations_match_status", "match_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monitoring_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("monitoring_runs.id", ondelete="CASCADE"),
        nullable=True,
    )
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_source_id: Mapped[int | None] = mapped_column(ForeignKey("product_sources.id", ondelete="SET NULL"), nullable=True)
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True)
    source_capture_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_capture_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    observation_batch_id: Mapped[str | None] = mapped_column(String, nullable=True)
    catalog_source: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    mpn: Mapped[str | None] = mapped_column(String, nullable=True)
    product_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    competitor_name: Mapped[str | None] = mapped_column(String, nullable=True)
    competitor_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="EUR", server_default="EUR")
    availability: Mapped[str | None] = mapped_column(String, nullable=True)
    stock_status: Mapped[str | None] = mapped_column(String, nullable=True)
    shipping_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    delivery_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    seller_name: Mapped[str | None] = mapped_column(String, nullable=True)
    product_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    own_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_delta: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_delta_percent: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    raw_observation: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    matched_by: Mapped[str | None] = mapped_column(String, nullable=True)
    match_status: Mapped[str] = mapped_column(String, nullable=False, default="unmatched", server_default="unmatched")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timestamp_source: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp_quality: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    monitoring_run: Mapped[MonitoringRun] = relationship(back_populates="price_observations")
    product: Mapped[Product | None] = relationship(back_populates="price_observations")
    listings: Mapped[list["PriceObservationListing"]] = relationship(
        back_populates="price_observation",
        cascade="all, delete-orphan",
    )
    alert_events: Mapped[list["AlertEvent"]] = relationship(back_populates="price_observation")
class PriceObservationListing(Base):
    __tablename__ = "price_observation_listings"
    __table_args__ = (
        Index("ix_price_observation_listings_price_observation_id", "price_observation_id"),
        Index("ix_price_observation_listings_run_id", "run_id"),
        Index("ix_price_observation_listings_observation_batch_id", "observation_batch_id"),
        Index("ix_price_observation_listings_product_id", "product_id"),
        Index("ix_price_observation_listings_source_capture_snapshot_id", "source_capture_snapshot_id"),
        Index("ix_price_observation_listings_run_product_price", "run_id", "product_id", "price"),
        Index("ix_price_observation_listings_observation_rank", "price_observation_id", "rank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    price_observation_id: Mapped[int] = mapped_column(ForeignKey("price_observations.id", ondelete="CASCADE"), nullable=False)
    monitoring_run_id: Mapped[int | None] = mapped_column(ForeignKey("monitoring_runs.id", ondelete="CASCADE"), nullable=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    observation_batch_id: Mapped[str | None] = mapped_column(String, nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_source_id: Mapped[int | None] = mapped_column(ForeignKey("product_sources.id", ondelete="SET NULL"), nullable=True)
    source_capture_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_capture_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    seller_name: Mapped[str | None] = mapped_column(String, nullable=True)
    seller_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="EUR", server_default="EUR")
    availability: Mapped[str | None] = mapped_column(String, nullable=True)
    stock_status: Mapped[str | None] = mapped_column(String, nullable=True)
    shipping_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    delivery_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_listing: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    price_observation: Mapped[PriceObservation] = relationship(back_populates="listings")
class OfferObservation(Base):
    __tablename__ = "offer_observations"
    __table_args__ = (
        Index("ix_offer_observations_product_id_observed_at", "product_id", "observed_at"),
        Index("ix_offer_observations_observation_batch_id", "observation_batch_id"),
        Index("ix_offer_observations_product_source_id_observed_at", "product_source_id", "observed_at"),
        Index("ix_offer_observations_aggregator_vendor_id", "aggregator_vendor_id"),
        Index("ix_offer_observations_seller_vendor_id", "seller_vendor_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_source_id: Mapped[int | None] = mapped_column(ForeignKey("product_sources.id", ondelete="SET NULL"), nullable=True)
    aggregator_vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True)
    source_capture_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_capture_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    observation_batch_id: Mapped[str | None] = mapped_column(String, nullable=True)
    seller_name: Mapped[str | None] = mapped_column(String, nullable=True)
    seller_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    seller_vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="EUR", server_default="EUR")
    availability: Mapped[str | None] = mapped_column(String, nullable=True)
    stock_status: Mapped[str | None] = mapped_column(String, nullable=True)
    shipping_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    delivery_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_observation: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timestamp_source: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp_quality: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
