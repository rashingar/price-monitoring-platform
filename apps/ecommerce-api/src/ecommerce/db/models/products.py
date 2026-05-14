"""Product, product source, and source capture snapshot models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, false, text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ecommerce.db.models.base import Base, JSON_DOCUMENT


class ProductSource(Base):
    __tablename__ = "product_sources"
    __table_args__ = (
        UniqueConstraint("product_id", "canonical_url_hash", name="uq_product_sources_product_canonical_url_hash"),
        Index("ix_product_sources_product_id", "product_id"),
        Index("ix_product_sources_vendor_id", "vendor_id"),
        Index("ix_product_sources_canonical_url_hash", "canonical_url_hash"),
        Index("ix_product_sources_active", "active"),
        Index("ix_product_sources_last_seen_at", "last_seen_at"),
        Index("ix_product_sources_last_success_at", "last_success_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url_hash: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False, default="direct_product_url", server_default="direct_product_url")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_fetch_status: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_parser_version: Mapped[str | None] = mapped_column(String, nullable=True)
    last_capture_strategy: Mapped[str | None] = mapped_column(String, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    data_quality_flags: Mapped[list[str] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index(
            "uq_products_catalog_source_model_present",
            "catalog_source",
            "model",
            unique=True,
            postgresql_where=text("model IS NOT NULL AND model <> ''"),
            sqlite_where=text("model IS NOT NULL AND model <> ''"),
        ),
        Index("ix_products_catalog_source_mpn", "catalog_source", "mpn"),
        Index("ix_products_manufacturer", "manufacturer"),
        Index("ix_products_family", "family"),
        Index("ix_products_category_name", "category_name"),
        Index("ix_products_sub_category", "sub_category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    catalog_source: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    mpn: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String, nullable=True)
    family: Mapped[str | None] = mapped_column(String, nullable=True)
    category_name: Mapped[str | None] = mapped_column(String, nullable=True)
    sub_category: Mapped[str | None] = mapped_column(String, nullable=True)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="EUR", server_default="EUR")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    raw_catalog_row: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    catalog_snapshots: Mapped[list["CatalogSnapshot"]] = relationship(back_populates="product")
    price_observations: Mapped[list["PriceObservation"]] = relationship(back_populates="product")
    alert_rules: Mapped[list["AlertRule"]] = relationship(back_populates="product")
    alert_events: Mapped[list["AlertEvent"]] = relationship(back_populates="product")
class SourceCaptureSnapshot(Base):
    __tablename__ = "source_capture_snapshots"
    __table_args__ = (
        Index("ix_source_capture_snapshots_product_source_id_captured_at", "product_source_id", "captured_at"),
        Index("ix_source_capture_snapshots_product_id", "product_id"),
        Index("ix_source_capture_snapshots_vendor_id", "vendor_id"),
        Index("ix_source_capture_snapshots_content_hash", "content_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_source_id: Mapped[int | None] = mapped_column(ForeignKey("product_sources.id", ondelete="SET NULL"), nullable=True)
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True)
    capture_strategy: Mapped[str] = mapped_column(String, nullable=False)
    page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_method: Mapped[str | None] = mapped_column(String, nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    response_body_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    response_body_text_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_html_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String, nullable=True)
    capture_version: Mapped[str | None] = mapped_column(String, nullable=True)
    playwright_version: Mapped[str | None] = mapped_column(String, nullable=True)
    fetch_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetch_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    network_event_type: Mapped[str | None] = mapped_column(String, nullable=True)
    trigger_action: Mapped[str | None] = mapped_column(String, nullable=True)
    data_quality_flags: Mapped[list[str] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
