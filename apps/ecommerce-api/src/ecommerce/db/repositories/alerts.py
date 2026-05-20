"""Repository helpers for dashboard-only price monitoring alerts."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ecommerce.db.models.alerts import AlertEvent, AlertRule
from ecommerce.db.repositories.common import json_safe_value

SUPPORTED_ALERT_RULE_TYPES = {"competitor_below_own_price"}
ALERT_EVENT_STATUSES = {"open", "acknowledged", "resolved"}


def create_alert_rule(session: Session, payload: dict[str, Any]) -> AlertRule:
    values = _validated_rule_values(payload)
    now = _now()
    rule = AlertRule(**values, created_at=now, updated_at=now)
    session.add(rule)
    session.flush()
    return rule


def update_alert_rule(
    session: Session, rule_id: int, payload: dict[str, Any]
) -> AlertRule | None:
    rule = get_alert_rule(session, rule_id)
    if rule is None:
        return None
    current = alert_rule_to_dict(rule)
    current.update(
        {key: value for key, value in payload.items() if key in _RULE_UPDATE_FIELDS}
    )
    values = _validated_rule_values(current)
    for key, value in values.items():
        setattr(rule, key, value)
    rule.updated_at = _now()
    session.flush()
    return rule


def list_alert_rules(
    session: Session,
    *,
    active: bool | None = None,
    rule_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    statement = _alert_rule_filters(
        select(AlertRule), active=active, rule_type=rule_type
    )
    count_statement = _alert_rule_filters(
        select(func.count(AlertRule.id)), active=active, rule_type=rule_type
    )
    statement = (
        statement.order_by(AlertRule.created_at.desc(), AlertRule.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        alert_rule_to_dict(rule) for rule in session.execute(statement).scalars().all()
    ], int(session.execute(count_statement).scalar_one())


def get_alert_rule(session: Session, rule_id: int) -> AlertRule | None:
    return session.get(AlertRule, rule_id)


def delete_or_deactivate_alert_rule(session: Session, rule_id: int) -> AlertRule | None:
    rule = get_alert_rule(session, rule_id)
    if rule is None:
        return None
    rule.active = False
    rule.updated_at = _now()
    session.flush()
    return rule


def has_active_alert_rules(session: Session) -> bool:
    statement = select(AlertRule.id).where(AlertRule.active.is_(True)).limit(1)
    return session.execute(statement).scalar_one_or_none() is not None


def evaluate_alert_rules_for_run(session: Session, run_id: str):
    from ecommerce.price_monitoring.alerts import (
        evaluate_alert_rules_for_run as evaluate,
    )

    return evaluate(session, run_id)


def list_alert_events(
    session: Session,
    *,
    status: str | None = None,
    run_id: str | None = None,
    product_id: int | None = None,
    model: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    safe_status = _validate_optional_status(status)
    statement = _alert_event_filters(
        select(AlertEvent),
        status=safe_status,
        run_id=run_id,
        product_id=product_id,
        model=model,
    )
    count_statement = _alert_event_filters(
        select(func.count(AlertEvent.id)),
        status=safe_status,
        run_id=run_id,
        product_id=product_id,
        model=model,
    )
    statement = (
        statement.order_by(AlertEvent.triggered_at.desc(), AlertEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        alert_event_to_dict(event)
        for event in session.execute(statement).scalars().all()
    ], int(session.execute(count_statement).scalar_one())


def acknowledge_alert_event(
    session: Session, event_id: int, acknowledged_by: str | None = None
) -> AlertEvent | None:
    event = session.get(AlertEvent, event_id)
    if event is None:
        return None
    now = _now()
    event.status = "acknowledged"
    event.acknowledged_at = now
    event.acknowledged_by = _optional_text(acknowledged_by)
    event.updated_at = now
    session.flush()
    return event


def resolve_alert_event(
    session: Session, event_id: int, resolved_by: str | None = None
) -> AlertEvent | None:
    event = session.get(AlertEvent, event_id)
    if event is None:
        return None
    now = _now()
    event.status = "resolved"
    event.resolved_at = now
    event.resolved_by = _optional_text(resolved_by)
    event.updated_at = now
    session.flush()
    return event


def alert_rule_to_dict(rule: AlertRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "name": rule.name,
        "rule_type": rule.rule_type,
        "product_id": rule.product_id,
        "catalog_source": rule.catalog_source,
        "model": rule.model,
        "mpn": rule.mpn,
        "threshold_amount": json_safe_value(rule.threshold_amount),
        "threshold_percent": json_safe_value(rule.threshold_percent),
        "active": rule.active,
        "created_at": json_safe_value(rule.created_at),
        "updated_at": json_safe_value(rule.updated_at),
    }


def alert_event_to_dict(event: AlertEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "alert_rule_id": event.alert_rule_id,
        "monitoring_run_id": event.monitoring_run_id,
        "price_observation_id": event.price_observation_id,
        "product_id": event.product_id,
        "run_id": event.run_id,
        "catalog_source": event.catalog_source,
        "model": event.model,
        "mpn": event.mpn,
        "source": event.source,
        "competitor_name": event.competitor_name,
        "competitor_price": json_safe_value(event.competitor_price),
        "own_price": json_safe_value(event.own_price),
        "price_delta": json_safe_value(event.price_delta),
        "price_delta_percent": json_safe_value(event.price_delta_percent),
        "severity": event.severity,
        "status": event.status,
        "message": event.message,
        "dedupe_key": event.dedupe_key,
        "triggered_at": json_safe_value(event.triggered_at),
        "acknowledged_at": json_safe_value(event.acknowledged_at),
        "acknowledged_by": event.acknowledged_by,
        "resolved_at": json_safe_value(event.resolved_at),
        "resolved_by": event.resolved_by,
        "raw_context": json_safe_value(event.raw_context),
        "created_at": json_safe_value(event.created_at),
        "updated_at": json_safe_value(event.updated_at),
    }


_RULE_UPDATE_FIELDS = {
    "name",
    "rule_type",
    "product_id",
    "catalog_source",
    "model",
    "mpn",
    "threshold_amount",
    "threshold_percent",
    "active",
}


def _validated_rule_values(payload: dict[str, Any]) -> dict[str, Any]:
    rule_type = _optional_text(payload.get("rule_type")) or "competitor_below_own_price"
    if rule_type not in SUPPORTED_ALERT_RULE_TYPES:
        raise ValueError("rule_type must be competitor_below_own_price.")

    product_id = _int_or_none(payload.get("product_id"))
    catalog_source = _optional_text(payload.get("catalog_source"))
    model = _optional_text(payload.get("model"))
    mpn = _optional_text(payload.get("mpn"))
    if product_id is None and not (catalog_source and (model or mpn)):
        raise ValueError(
            "Alert rule target must include product_id, catalog_source + model, or catalog_source + mpn."
        )

    threshold_amount = _positive_decimal_or_none(
        payload.get("threshold_amount"), "threshold_amount"
    )
    threshold_percent = _positive_decimal_or_none(
        payload.get("threshold_percent"), "threshold_percent"
    )
    active = payload.get("active")
    return {
        "name": _optional_text(payload.get("name")),
        "rule_type": rule_type,
        "product_id": product_id,
        "catalog_source": catalog_source,
        "model": model,
        "mpn": mpn,
        "threshold_amount": threshold_amount,
        "threshold_percent": threshold_percent,
        "active": True if active is None else bool(active),
    }


def _alert_rule_filters(
    statement: Select, *, active: bool | None, rule_type: str | None
) -> Select:
    if active is not None:
        statement = statement.where(AlertRule.active.is_(active))
    if rule_type:
        statement = statement.where(AlertRule.rule_type == rule_type)
    return statement


def _alert_event_filters(
    statement: Select,
    *,
    status: str | None,
    run_id: str | None,
    product_id: int | None,
    model: str | None,
) -> Select:
    if status:
        statement = statement.where(AlertEvent.status == status)
    if run_id:
        statement = statement.where(AlertEvent.run_id == run_id)
    if product_id is not None:
        statement = statement.where(AlertEvent.product_id == product_id)
    if model:
        statement = statement.where(AlertEvent.model == model)
    return statement


def _validate_optional_status(value: str | None) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    if text not in ALERT_EVENT_STATUSES:
        raise ValueError("status must be one of: open, acknowledged, resolved.")
    return text


def _positive_decimal_or_none(value: object, field_name: str) -> Decimal | None:
    text = _optional_text(value)
    if text is None:
        return None
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive number.") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} must be positive.")
    return parsed


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: object) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("product_id must be an integer.") from exc
    if parsed <= 0:
        raise ValueError("product_id must be a positive integer.")
    return parsed


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
