"""Product Factory CSV batch intake persistence models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ecommerce.db.models.base import Base, JSON_DOCUMENT


class ProductFactoryBatch(Base):
    __tablename__ = "product_factory_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('uploaded', 'resolving', 'resolved', 'partially_resolved', 'failed')",
            name="ck_product_factory_batches_status",
        ),
        Index("ix_product_factory_batches_status", "status"),
        Index("ix_product_factory_batches_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="uploaded", server_default="uploaded")
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    pending_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    auto_selected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    manually_selected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    needs_review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    no_usable_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    resolution_failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    rows: Mapped[list["ProductFactoryBatchRow"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="ProductFactoryBatchRow.row_number",
    )


class ProductFactoryBatchRow(Base):
    __tablename__ = "product_factory_batch_rows"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'resolving_source', 'auto_selected', 'manually_selected', 'needs_review', 'no_usable_source', 'resolution_failed', 'skipped')",
            name="ck_product_factory_batch_rows_status",
        ),
        Index("ix_product_factory_batch_rows_batch_id", "batch_id"),
        Index("ix_product_factory_batch_rows_status", "status"),
        Index("ix_product_factory_batch_rows_model", "model"),
        Index("ix_product_factory_batch_rows_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("product_factory_batches.id", ondelete="CASCADE"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    brand: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    name: Mapped[str] = mapped_column(Text, nullable=False)
    queries_json: Mapped[list[str] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", server_default="pending")
    selected_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_source: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_urls_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    selection_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    product_factory_job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    product_factory_job_status: Mapped[str | None] = mapped_column(String, nullable=True)
    product_factory_job_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_factory_error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    product_factory_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    job_status_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    batch: Mapped[ProductFactoryBatch] = relationship(back_populates="rows")
