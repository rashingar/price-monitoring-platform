"""Alert rule and alert event models."""

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


class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        CheckConstraint(
            "rule_type = 'competitor_below_own_price'", name="ck_alert_rules_rule_type"
        ),
        CheckConstraint(
            "threshold_amount IS NULL OR threshold_amount > 0",
            name="ck_alert_rules_threshold_amount_positive",
        ),
        CheckConstraint(
            "threshold_percent IS NULL OR threshold_percent > 0",
            name="ck_alert_rules_threshold_percent_positive",
        ),
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
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    catalog_source: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    mpn: Mapped[str | None] = mapped_column(String, nullable=True)
    threshold_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    threshold_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    product: Mapped[Product | None] = relationship(back_populates="alert_rules")
    alert_events: Mapped[list["AlertEvent"]] = relationship(
        back_populates="alert_rule",
        cascade="all, delete-orphan",
    )


class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved')",
            name="ck_alert_events_status",
        ),
        CheckConstraint("severity = 'warning'", name="ck_alert_events_severity"),
        Index("ix_alert_events_alert_rule_id", "alert_rule_id"),
        Index("ix_alert_events_product_id", "product_id"),
        Index("ix_alert_events_run_id", "run_id"),
        Index("ix_alert_events_status", "status"),
        Index("ix_alert_events_triggered_at", "triggered_at"),
        Index("uq_alert_events_dedupe_key", "dedupe_key", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_rule_id: Mapped[int] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False
    )
    monitoring_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("monitoring_runs.id", ondelete="SET NULL"), nullable=True
    )
    price_observation_id: Mapped[int | None] = mapped_column(
        ForeignKey("price_observations.id", ondelete="SET NULL"), nullable=True
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    catalog_source: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    mpn: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    competitor_name: Mapped[str | None] = mapped_column(String, nullable=True)
    competitor_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    own_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_delta: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_delta_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    severity: Mapped[str] = mapped_column(
        String, nullable=False, default="warning", server_default="warning"
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="open", server_default="open"
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_context: Mapped[dict[str, Any] | None] = mapped_column(
        JSON_DOCUMENT, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    alert_rule: Mapped[AlertRule] = relationship(back_populates="alert_events")
    monitoring_run: Mapped[MonitoringRun | None] = relationship(
        back_populates="alert_events"
    )
    price_observation: Mapped[PriceObservation | None] = relationship(
        back_populates="alert_events"
    )
    product: Mapped[Product | None] = relationship(back_populates="alert_events")
