"""Dashboard-only alert evaluation for price monitoring observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy.orm import Session, aliased

from ecommerce.db.models import AlertEvent, AlertRule, PriceObservation
from ecommerce.db.repositories import json_safe_value


@dataclass(frozen=True)
class AlertEvaluationResult:
    evaluated_observation_count: int = 0
    evaluated_rule_count: int = 0
    created_event_count: int = 0
    duplicate_event_count: int = 0
    skipped_count: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "evaluated_observation_count": self.evaluated_observation_count,
            "evaluated_rule_count": self.evaluated_rule_count,
            "created_event_count": self.created_event_count,
            "duplicate_event_count": self.duplicate_event_count,
            "skipped_count": self.skipped_count,
            "warnings": list(self.warnings),
        }


def evaluate_alert_rules_for_run(session: Session, run_id: str) -> AlertEvaluationResult:
    rules = session.execute(
        select(AlertRule).where(AlertRule.active.is_(True)).order_by(AlertRule.id.asc())
    ).scalars().all()
    if not rules:
        return AlertEvaluationResult(warnings=["No active alert rules configured."])

    latest_observation = aliased(PriceObservation)
    latest_created_at = (
        select(func.max(latest_observation.created_at))
        .where(latest_observation.run_id == run_id)
        .scalar_subquery()
    )
    observations = session.execute(
        select(PriceObservation)
        .where(
            PriceObservation.run_id == run_id,
            PriceObservation.created_at == latest_created_at,
        )
        .order_by(PriceObservation.id.asc())
    ).scalars().all()
    if not observations:
        return AlertEvaluationResult(evaluated_rule_count=len(rules), warnings=[f"No price observations found for run_id {run_id}."])

    existing_dedupe_keys = {
        str(key)
        for key in session.execute(select(AlertEvent.dedupe_key).where(AlertEvent.run_id == run_id)).scalars().all()
    }
    created = 0
    duplicates = 0
    skipped = 0
    evaluated_observation_ids: set[int] = set()
    warnings: list[str] = []
    now = _now()

    for rule in rules:
        if rule.rule_type != "competitor_below_own_price":
            skipped += 1
            warnings.append(f"Unsupported alert rule type skipped: {rule.rule_type}.")
            continue
        for observation in _matched_observations(rule, observations):
            if observation.id is not None:
                evaluated_observation_ids.add(observation.id)
            event, reason = evaluate_competitor_below_own_price(rule, observation, triggered_at=now)
            if event is None:
                skipped += 1
                if reason:
                    warnings.append(reason)
                continue
            if event.dedupe_key in existing_dedupe_keys:
                duplicates += 1
                continue
            existing_dedupe_keys.add(event.dedupe_key)
            session.add(event)
            created += 1

    session.flush()
    return AlertEvaluationResult(
        evaluated_observation_count=len(evaluated_observation_ids),
        evaluated_rule_count=len(rules),
        created_event_count=created,
        duplicate_event_count=duplicates,
        skipped_count=skipped,
        warnings=warnings,
    )


def evaluate_competitor_below_own_price(
    rule: AlertRule,
    observation: PriceObservation,
    *,
    triggered_at: datetime | None = None,
) -> tuple[AlertEvent | None, str | None]:
    if observation.competitor_price is None or observation.own_price is None:
        return None, None
    if observation.competitor_price >= observation.own_price:
        return None, None

    price_delta = observation.own_price - observation.competitor_price
    if rule.threshold_amount is not None and price_delta < rule.threshold_amount:
        return None, None

    price_delta_percent = observation.price_delta_percent
    if price_delta_percent is None and observation.own_price != 0:
        price_delta_percent = (price_delta / observation.own_price) * Decimal("100")
    if rule.threshold_percent is not None:
        if price_delta_percent is None or price_delta_percent < rule.threshold_percent:
            return None, None

    now = triggered_at or _now()
    dedupe_key = _dedupe_key(rule, observation)
    model_label = observation.model or observation.mpn or f"product {observation.product_id}"
    message = (
        f"Competitor price is below own price for {model_label}: "
        f"own EUR {_money(observation.own_price)} vs competitor EUR {_money(observation.competitor_price)}."
    )
    return (
        AlertEvent(
            alert_rule_id=rule.id,
            monitoring_run_id=observation.monitoring_run_id,
            price_observation_id=observation.id,
            product_id=observation.product_id,
            run_id=observation.run_id,
            catalog_source=observation.catalog_source,
            model=observation.model,
            mpn=observation.mpn,
            source=observation.source,
            competitor_name=observation.competitor_name,
            competitor_price=observation.competitor_price,
            own_price=observation.own_price,
            price_delta=price_delta,
            price_delta_percent=price_delta_percent,
            severity="warning",
            status="open",
            message=message,
            dedupe_key=dedupe_key,
            triggered_at=now,
            raw_context={
                "rule": {
                    "id": rule.id,
                    "name": rule.name,
                    "rule_type": rule.rule_type,
                    "threshold_amount": json_safe_value(rule.threshold_amount),
                    "threshold_percent": json_safe_value(rule.threshold_percent),
                },
                "observation": {
                    "id": observation.id,
                    "run_id": observation.run_id,
                    "source": observation.source,
                    "catalog_source": observation.catalog_source,
                    "model": observation.model,
                    "mpn": observation.mpn,
                    "competitor_name": observation.competitor_name,
                    "competitor_price": json_safe_value(observation.competitor_price),
                    "own_price": json_safe_value(observation.own_price),
                },
            },
            created_at=now,
            updated_at=now,
        ),
        None,
    )


def _matched_observations(rule: AlertRule, observations: list[PriceObservation]) -> list[PriceObservation]:
    if rule.product_id is not None:
        return [observation for observation in observations if observation.product_id == rule.product_id]
    if rule.catalog_source and rule.model:
        return [
            observation
            for observation in observations
            if observation.catalog_source == rule.catalog_source and observation.model == rule.model
        ]
    if rule.catalog_source and rule.mpn:
        return [
            observation
            for observation in observations
            if observation.catalog_source == rule.catalog_source and observation.mpn == rule.mpn
        ]
    return []


def _dedupe_key(rule: AlertRule, observation: PriceObservation) -> str:
    if observation.product_id is not None:
        target = f"product:{observation.product_id}"
    elif observation.catalog_source and observation.model:
        target = f"catalog_model:{observation.catalog_source}:{observation.model}"
    elif observation.catalog_source and observation.mpn:
        target = f"catalog_mpn:{observation.catalog_source}:{observation.mpn}"
    else:
        target = f"observation:{observation.id}"
    source = observation.source or ""
    return f"alert_rule:{rule.id}|run:{observation.run_id}|{target}|source:{source}"


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
