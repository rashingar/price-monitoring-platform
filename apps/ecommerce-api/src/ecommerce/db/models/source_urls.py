"""Source URL lifecycle, discovery run, task, and candidate models."""

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


class SourceUrl(Base):
    __tablename__ = "source_urls"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'disabled', 'broken', 'redirected', 'needs_review')",
            name="ck_source_urls_status",
        ),
        CheckConstraint(
            "url_type IN ('manual', 'imported', 'discovered')",
            name="ck_source_urls_url_type",
        ),
        CheckConstraint(
            "provenance IS NULL OR provenance IN ('manual', 'discovery', 'import', 'unknown')",
            name="ck_source_urls_provenance",
        ),
        UniqueConstraint(
            "catalog_product_id",
            "url_normalized",
            name="uq_source_urls_catalog_product_url_normalized",
        ),
        Index("ix_source_urls_catalog_product_id", "catalog_product_id"),
        Index("ix_source_urls_catalog_source_model", "catalog_source", "model"),
        Index("ix_source_urls_source_name", "source_name"),
        Index("ix_source_urls_source_domain", "source_domain"),
        Index("ix_source_urls_status", "status"),
        Index(
            "ix_source_urls_catalog_product_status_source",
            "catalog_product_id",
            "status",
            "source_name",
        ),
        Index("ix_source_urls_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    catalog_product_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_products.id", ondelete="CASCADE"), nullable=False
    )
    catalog_source: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    mpn: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default=""
    )
    manufacturer: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default=""
    )
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    source_domain: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="active", server_default="active"
    )
    url_type: Mapped[str] = mapped_column(
        String, nullable=False, default="manual", server_default="manual"
    )
    provenance: Mapped[str | None] = mapped_column(String, nullable=True)
    trust_level: Mapped[str] = mapped_column(
        String, nullable=False, default="manual", server_default="manual"
    )
    added_by: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    catalog_product: Mapped[CatalogProductRow] = relationship(
        back_populates="source_urls"
    )


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
    filters_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON_DOCUMENT, nullable=True
    )
    selected_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    candidate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    matched_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    needs_review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    not_found_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
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
    catalog_product_id: Mapped[int | None] = mapped_column(
        ForeignKey("catalog_products.id", ondelete="SET NULL"), nullable=True
    )
    model: Mapped[str] = mapped_column(String, nullable=False)
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="queued", server_default="queued"
    )
    match_status: Mapped[str | None] = mapped_column(String, nullable=True)
    candidate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    catalog_product_id: Mapped[int | None] = mapped_column(
        ForeignKey("catalog_products.id", ondelete="SET NULL"), nullable=True
    )
    catalog_source: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    mpn: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default=""
    )
    manufacturer: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default=""
    )
    product_name: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    category: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    own_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    source_domain: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    expected_listing: Mapped[str | None] = mapped_column(String, nullable=True)
    candidate_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    match_status: Mapped[str] = mapped_column(String, nullable=False)
    confidence_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    match_method: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default=""
    )
    evidence_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON_DOCUMENT, nullable=True
    )
    competing_candidates_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    searched_queries_json: Mapped[list[str] | None] = mapped_column(
        JSON_DOCUMENT, nullable=True
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default="pending"
    )
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
