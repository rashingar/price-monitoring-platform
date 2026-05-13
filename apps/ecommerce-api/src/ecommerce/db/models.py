"""SQLAlchemy models for durable price monitoring storage."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, false, text, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

JSON_DOCUMENT = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    pass


class CatalogProductRow(Base):
    __tablename__ = "catalog_products"
    __table_args__ = (
        Index("uq_catalog_products_catalog_source_model", "catalog_source", "model", unique=True),
        Index("ix_catalog_products_catalog_source_active", "catalog_source", "active"),
        Index("ix_catalog_products_model", "model"),
        Index("ix_catalog_products_mpn", "mpn"),
        Index("ix_catalog_products_manufacturer", "manufacturer"),
        Index("ix_catalog_products_family", "family"),
        Index("ix_catalog_products_category_name", "category_name"),
        Index("ix_catalog_products_sub_category", "sub_category"),
        Index("ix_catalog_products_bestprice_status", "bestprice_status"),
        Index("ix_catalog_products_skroutz_status", "skroutz_status"),
        Index("ix_catalog_products_imported_at", "imported_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    catalog_source: Mapped[str] = mapped_column(String, nullable=False, default="sourceCata", server_default="sourceCata")
    model: Mapped[str] = mapped_column(String, nullable=False)
    mpn: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    name: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    category: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    raw_category: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    family: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    category_name: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    sub_category: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    category_levels: Mapped[list[str] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    manufacturer: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bestprice_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skroutz_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_atomic_model: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    automation_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_catalog_row: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    warnings: Mapped[list[str] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    source_urls: Mapped[list["SourceUrl"]] = relationship(back_populates="catalog_product")


class Vendor(Base):
    __tablename__ = "vendors"
    __table_args__ = (
        Index("uq_vendors_slug", "slug", unique=True),
        Index("ix_vendors_active", "active"),
        Index("ix_vendors_vendor_type", "vendor_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    vendor_type: Mapped[str] = mapped_column(String, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    supports_direct_product_url: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    supports_search: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    supports_xhr_capture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SourceUrl(Base):
    __tablename__ = "source_urls"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'disabled', 'broken', 'redirected', 'needs_review')",
            name="ck_source_urls_status",
        ),
        CheckConstraint("url_type IN ('manual', 'imported', 'discovered')", name="ck_source_urls_url_type"),
        UniqueConstraint("catalog_product_id", "url_normalized", name="uq_source_urls_catalog_product_url_normalized"),
        Index("ix_source_urls_catalog_product_id", "catalog_product_id"),
        Index("ix_source_urls_catalog_source_model", "catalog_source", "model"),
        Index("ix_source_urls_source_name", "source_name"),
        Index("ix_source_urls_source_domain", "source_domain"),
        Index("ix_source_urls_status", "status"),
        Index("ix_source_urls_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    catalog_product_id: Mapped[int] = mapped_column(ForeignKey("catalog_products.id", ondelete="CASCADE"), nullable=False)
    catalog_source: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    mpn: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    manufacturer: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    source_domain: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active", server_default="active")
    url_type: Mapped[str] = mapped_column(String, nullable=False, default="manual", server_default="manual")
    trust_level: Mapped[str] = mapped_column(String, nullable=False, default="manual", server_default="manual")
    added_by: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    catalog_product: Mapped[CatalogProductRow] = relationship(back_populates="source_urls")


class SourceUrlDiscoveryRun(Base):
    __tablename__ = "source_url_discovery_runs"
    __table_args__ = (
        Index("uq_source_url_discovery_runs_run_id", "run_id", unique=True),
        Index("ix_source_url_discovery_runs_source_name", "source_name"),
        Index("ix_source_url_discovery_runs_status", "status"),
        Index("ix_source_url_discovery_runs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    input_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    filters_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    selected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    needs_review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    not_found_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SourceUrlDiscoveryTask(Base):
    __tablename__ = "source_url_discovery_tasks"
    __table_args__ = (
        Index("ix_source_url_discovery_tasks_run_id", "run_id"),
        Index("ix_source_url_discovery_tasks_status", "status"),
        Index("ix_source_url_discovery_tasks_model", "model"),
        Index("ix_source_url_discovery_tasks_source_name", "source_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    catalog_product_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_products.id", ondelete="SET NULL"), nullable=True)
    model: Mapped[str] = mapped_column(String, nullable=False)
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued", server_default="queued")
    match_status: Mapped[str | None] = mapped_column(String, nullable=True)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SourceUrlCandidate(Base):
    __tablename__ = "source_url_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'needs_review', 'not_found', 'error')",
            name="ck_source_url_candidates_status",
        ),
        Index("ix_source_url_candidates_run_id", "run_id"),
        Index("ix_source_url_candidates_catalog_product_id", "catalog_product_id"),
        Index("ix_source_url_candidates_source_name", "source_name"),
        Index("ix_source_url_candidates_match_status", "match_status"),
        Index("ix_source_url_candidates_status", "status"),
        Index("ix_source_url_candidates_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    catalog_product_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_products.id", ondelete="SET NULL"), nullable=True)
    catalog_source: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    mpn: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    manufacturer: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    product_name: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    category: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    own_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    source_domain: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    expected_listing: Mapped[str | None] = mapped_column(String, nullable=True)
    candidate_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    match_status: Mapped[str] = mapped_column(String, nullable=False)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    match_method: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    evidence_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    competing_candidates_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    searched_queries_json: Mapped[list[str] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", server_default="pending")
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class VendorSourceCaptureRun(Base):
    __tablename__ = "vendor_source_capture_runs"
    __table_args__ = (
        Index("uq_vendor_source_capture_runs_run_id", "run_id", unique=True),
        Index("ix_vendor_source_capture_runs_observation_batch_id", "observation_batch_id"),
        Index("ix_vendor_source_capture_runs_status", "status"),
        Index("ix_vendor_source_capture_runs_source_filter", "source_filter"),
        Index("ix_vendor_source_capture_runs_catalog_source", "catalog_source"),
        Index("ix_vendor_source_capture_runs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    observation_batch_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    source_filter: Mapped[str | None] = mapped_column(String, nullable=True)
    catalog_source: Mapped[str | None] = mapped_column(String, nullable=True)
    selected_catalog_product_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    selected_source_url_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    selected_product_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    succeeded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    warnings_json: Mapped[list[str] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    filters_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    artifact_refs_json: Mapped[list[str] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    result_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EcommerceJob(Base):
    __tablename__ = "ecommerce_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_ecommerce_jobs_status",
        ),
        Index("uq_ecommerce_jobs_job_id", "job_id", unique=True),
        Index("ix_ecommerce_jobs_job_type", "job_type"),
        Index("ix_ecommerce_jobs_status", "status"),
        Index("ix_ecommerce_jobs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String, nullable=False)
    job_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued", server_default="queued")
    payload_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    result_json: Mapped[dict[str, Any] | list[Any] | str | int | float | bool | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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


class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        CheckConstraint("rule_type = 'competitor_below_own_price'", name="ck_alert_rules_rule_type"),
        CheckConstraint("threshold_amount IS NULL OR threshold_amount > 0", name="ck_alert_rules_threshold_amount_positive"),
        CheckConstraint("threshold_percent IS NULL OR threshold_percent > 0", name="ck_alert_rules_threshold_percent_positive"),
        Index("ix_alert_rules_active", "active"),
        Index("ix_alert_rules_rule_type", "rule_type"),
        Index("ix_alert_rules_product_id", "product_id"),
        Index("ix_alert_rules_catalog_source_model", "catalog_source", "model"),
        Index("ix_alert_rules_catalog_source_mpn", "catalog_source", "mpn"),
        Index("ix_alert_rules_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    rule_type: Mapped[str] = mapped_column(String, nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    catalog_source: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    mpn: Mapped[str | None] = mapped_column(String, nullable=True)
    threshold_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    threshold_percent: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    product: Mapped[Product | None] = relationship(back_populates="alert_rules")
    alert_events: Mapped[list["AlertEvent"]] = relationship(
        back_populates="alert_rule",
        cascade="all, delete-orphan",
    )


class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'acknowledged', 'resolved')", name="ck_alert_events_status"),
        CheckConstraint("severity = 'warning'", name="ck_alert_events_severity"),
        Index("ix_alert_events_alert_rule_id", "alert_rule_id"),
        Index("ix_alert_events_product_id", "product_id"),
        Index("ix_alert_events_run_id", "run_id"),
        Index("ix_alert_events_status", "status"),
        Index("ix_alert_events_triggered_at", "triggered_at"),
        Index("uq_alert_events_dedupe_key", "dedupe_key", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_rule_id: Mapped[int] = mapped_column(ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False)
    monitoring_run_id: Mapped[int | None] = mapped_column(ForeignKey("monitoring_runs.id", ondelete="SET NULL"), nullable=True)
    price_observation_id: Mapped[int | None] = mapped_column(ForeignKey("price_observations.id", ondelete="SET NULL"), nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    catalog_source: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    mpn: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    competitor_name: Mapped[str | None] = mapped_column(String, nullable=True)
    competitor_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    own_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_delta: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_delta_percent: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    severity: Mapped[str] = mapped_column(String, nullable=False, default="warning", server_default="warning")
    status: Mapped[str] = mapped_column(String, nullable=False, default="open", server_default="open")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_context: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    alert_rule: Mapped[AlertRule] = relationship(back_populates="alert_events")
    monitoring_run: Mapped[MonitoringRun | None] = relationship(back_populates="alert_events")
    price_observation: Mapped[PriceObservation | None] = relationship(back_populates="alert_events")
    product: Mapped[Product | None] = relationship(back_populates="alert_events")
