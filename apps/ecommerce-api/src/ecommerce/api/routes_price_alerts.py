"""Dashboard-only Price Monitoring alert API routes."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from ecommerce.db.repositories.alerts import (
    acknowledge_alert_event,
    alert_event_to_dict,
    alert_rule_to_dict,
    create_alert_rule,
    delete_or_deactivate_alert_rule,
    evaluate_alert_rules_for_run,
    get_alert_rule,
    list_alert_events,
    list_alert_rules,
    resolve_alert_event,
    update_alert_rule,
)
from ecommerce.db.config import sanitize_database_error
from ecommerce.db.policy import require_database_ready_for_price_monitoring
from ecommerce.db.session import session_scope
from ecommerce.price_monitoring.runs import InvalidPriceMonitoringRunIdError, validate_price_monitoring_run_id

router = APIRouter(prefix="/api/price-monitoring/alerts", tags=["price-monitoring-alerts"])


class AlertRuleCreateRequest(BaseModel):
    name: str | None = None
    rule_type: str = "competitor_below_own_price"
    product_id: int | None = None
    catalog_source: str | None = None
    model: str | None = None
    mpn: str | None = None
    threshold_amount: Decimal | str | float | int | None = None
    threshold_percent: Decimal | str | float | int | None = None
    active: bool = True


class AlertRuleUpdateRequest(BaseModel):
    name: str | None = Field(default=None)
    threshold_amount: Decimal | str | float | int | None = Field(default=None)
    threshold_percent: Decimal | str | float | int | None = Field(default=None)
    active: bool | None = Field(default=None)
    product_id: int | None = Field(default=None)
    catalog_source: str | None = Field(default=None)
    model: str | None = Field(default=None)
    mpn: str | None = Field(default=None)


class AlertEventAcknowledgeRequest(BaseModel):
    acknowledged_by: str | None = None


class AlertEventResolveRequest(BaseModel):
    resolved_by: str | None = None


@router.get("/rules")
def get_alert_rules(
    active: bool | None = None,
    rule_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    _require_database_configured()
    safe_limit, safe_offset = _limit_offset(limit, offset)
    try:
        with session_scope() as session:
            items, count = list_alert_rules(
                session,
                active=active,
                rule_type=_optional_query_text(rule_type),
                limit=safe_limit,
                offset=safe_offset,
            )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Alert rule query failed: {_safe_db_error(exc)}") from exc
    return {"items": items, "count": count, "limit": safe_limit, "offset": safe_offset}


@router.post("/rules")
def post_alert_rule(request: AlertRuleCreateRequest) -> dict:
    _require_database_configured()
    try:
        with session_scope() as session:
            rule = create_alert_rule(session, _model_payload(request, exclude_unset=False))
            payload = alert_rule_to_dict(rule)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Alert rule creation failed: {_safe_db_error(exc)}") from exc
    return payload


@router.get("/rules/{rule_id}")
def get_alert_rule_by_id(rule_id: int) -> dict:
    _require_database_configured()
    try:
        with session_scope() as session:
            rule = get_alert_rule(session, rule_id)
            if rule is None:
                raise HTTPException(status_code=404, detail="Alert rule not found.")
            payload = alert_rule_to_dict(rule)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Alert rule query failed: {_safe_db_error(exc)}") from exc
    return payload


@router.patch("/rules/{rule_id}")
def patch_alert_rule(rule_id: int, request: AlertRuleUpdateRequest) -> dict:
    _require_database_configured()
    try:
        with session_scope() as session:
            rule = update_alert_rule(session, rule_id, _model_payload(request, exclude_unset=True))
            if rule is None:
                raise HTTPException(status_code=404, detail="Alert rule not found.")
            payload = alert_rule_to_dict(rule)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Alert rule update failed: {_safe_db_error(exc)}") from exc
    return payload


@router.post("/rules/{rule_id}/deactivate")
def deactivate_alert_rule(rule_id: int) -> dict:
    _require_database_configured()
    try:
        with session_scope() as session:
            rule = delete_or_deactivate_alert_rule(session, rule_id)
            if rule is None:
                raise HTTPException(status_code=404, detail="Alert rule not found.")
            payload = alert_rule_to_dict(rule)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Alert rule deactivation failed: {_safe_db_error(exc)}") from exc
    return payload


@router.get("/events")
def get_alert_events(
    status: str | None = None,
    run_id: str | None = None,
    product_id: int | None = None,
    model: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    _require_database_configured()
    safe_limit, safe_offset = _limit_offset(limit, offset)
    try:
        with session_scope() as session:
            items, count = list_alert_events(
                session,
                status=_optional_query_text(status),
                run_id=_optional_query_text(run_id),
                product_id=product_id,
                model=_optional_query_text(model),
                limit=safe_limit,
                offset=safe_offset,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Alert event query failed: {_safe_db_error(exc)}") from exc
    return {"items": items, "count": count, "limit": safe_limit, "offset": safe_offset}


@router.post("/events/{event_id}/acknowledge")
def acknowledge_event(event_id: int, request: AlertEventAcknowledgeRequest) -> dict:
    _require_database_configured()
    try:
        with session_scope() as session:
            event = acknowledge_alert_event(session, event_id, request.acknowledged_by)
            if event is None:
                raise HTTPException(status_code=404, detail="Alert event not found.")
            payload = alert_event_to_dict(event)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Alert event acknowledgement failed: {_safe_db_error(exc)}") from exc
    return payload


@router.post("/events/{event_id}/resolve")
def resolve_event(event_id: int, request: AlertEventResolveRequest) -> dict:
    _require_database_configured()
    try:
        with session_scope() as session:
            event = resolve_alert_event(session, event_id, request.resolved_by)
            if event is None:
                raise HTTPException(status_code=404, detail="Alert event not found.")
            payload = alert_event_to_dict(event)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Alert event resolution failed: {_safe_db_error(exc)}") from exc
    return payload


@router.post("/evaluate/{run_id}")
def evaluate_run_alerts(run_id: str) -> dict:
    _require_database_configured()
    _validate_run_id(run_id)
    try:
        with session_scope() as session:
            result = evaluate_alert_rules_for_run(session, run_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Alert evaluation failed: {_safe_db_error(exc)}") from exc
    return {"run_id": run_id, "status": "evaluated", **result.to_dict()}


def _require_database_configured() -> None:
    require_database_ready_for_price_monitoring()


def _limit_offset(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(int(limit), 1000)), max(0, int(offset))


def _optional_query_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _validate_run_id(run_id: str) -> None:
    try:
        validate_price_monitoring_run_id(run_id)
    except InvalidPriceMonitoringRunIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _model_payload(model: BaseModel, *, exclude_unset: bool) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=exclude_unset)
    return model.dict(exclude_unset=exclude_unset)


def _safe_db_error(exc: Exception) -> str:
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    return sanitize_database_error(message) or exc.__class__.__name__
