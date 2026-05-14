"""Catalog-owned product catalog rows."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, false, text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ecommerce.db.models.base import Base, JSON_DOCUMENT


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
