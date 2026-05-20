"""Vendor and Vendor Sources capture run models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ecommerce.db.models.base import Base, JSON_DOCUMENT


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
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    supports_direct_product_url: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    supports_search: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    supports_xhr_capture: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class VendorSourceCaptureRun(Base):
    __tablename__ = "vendor_source_capture_runs"
    __table_args__ = (
        Index("uq_vendor_source_capture_runs_run_id", "run_id", unique=True),
        Index(
            "ix_vendor_source_capture_runs_observation_batch_id", "observation_batch_id"
        ),
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
    selected_catalog_product_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    selected_source_url_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    selected_product_source_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    succeeded_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    skipped_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    warnings_json: Mapped[list[str] | None] = mapped_column(
        JSON_DOCUMENT, nullable=True
    )
    filters_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON_DOCUMENT, nullable=True
    )
    artifact_refs_json: Mapped[list[str] | None] = mapped_column(
        JSON_DOCUMENT, nullable=True
    )
    result_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
