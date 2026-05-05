"""Optional DB persistence helpers for price monitoring workflows."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ecommerce.db.config import is_database_configured
from ecommerce.db.repositories import (
    count_price_observations,
    ensure_catalog_snapshots_from_rows,
    persist_monitoring_run_creation,
    match_product_for_observation,
    replace_price_observations,
    update_monitoring_run_from_fetch,
)
from ecommerce.db.session import session_scope
from ecommerce.db.models import PriceObservation
from ecommerce.price_monitoring.fetch_run import PriceMonitoringFetchResult
from ecommerce.price_monitoring.observations import parse_price_observations_csv
from ecommerce.price_monitoring.runs import PriceMonitoringRunRecord


@dataclass(frozen=True)
class FetchPersistenceResult:
    observation_count: int
    replaced_observation_count: int
    catalog_snapshot_count: int | None
    matched_observation_count: int
    unmatched_observation_count: int
    was_refetch: bool
    fetch_attempt: int
    persistence_status: str
    warnings: list[str]


def persist_run_creation_if_configured(
    record: PriceMonitoringRunRecord,
    *,
    trigger_type: str = "manual",
) -> bool:
    if not is_database_configured():
        return False
    with session_scope() as session:
        persist_monitoring_run_creation(session, record, trigger_type=trigger_type)
    return True


def persist_fetch_result_if_configured(
    result: PriceMonitoringFetchResult,
    *,
    trigger_type: str | None = None,
) -> FetchPersistenceResult:
    if not is_database_configured():
        return FetchPersistenceResult(
            observation_count=0,
            replaced_observation_count=0,
            catalog_snapshot_count=None,
            matched_observation_count=0,
            unmatched_observation_count=0,
            was_refetch=False,
            fetch_attempt=0,
            persistence_status="not_configured",
            warnings=["Database persistence is disabled because ECOMMERCE_DATABASE_URL is not configured."],
        )

    warnings: list[str] = []
    observations = []
    if result.enriched_csv_path is not None and Path(result.enriched_csv_path).exists():
        parsed = parse_price_observations_csv(
            result.enriched_csv_path,
            run_id=result.run_id,
            source=result.source,
            default_observed_at=result.completed_at,
        )
        observations = parsed.observations
        warnings.extend(parsed.warnings)
    elif result.status == "fetch_completed" and result.fetch_input_mode != "source_urls":
        warnings.append("Fetch completed without an enriched CSV path to persist.")

    run_dir = Path(result.input_csv_path).parent
    catalog_rows = _recover_catalog_rows(run_dir)

    with session_scope() as session:
        monitoring_run = update_monitoring_run_from_fetch(session, result, trigger_type=trigger_type)
        _apply_selection_summary_metadata(monitoring_run, _read_json_object(run_dir / "selection_summary.json"))
        catalog_snapshot_count = ensure_catalog_snapshots_from_rows(session, monitoring_run, catalog_rows)
        if result.fetch_input_mode == "source_urls" and result.enriched_csv_path is None:
            previous_count = _count_attached_source_url_observations(session, monitoring_run)
            fetch_attempt = int(monitoring_run.fetch_attempt or 0) + 1
            was_refetch = previous_count > 0
            observation_count = _attach_source_url_capture_observations(
                session,
                monitoring_run,
                result.observation_batch_id,
                fetch_attempt=fetch_attempt,
                was_refetch=was_refetch,
            )
            monitoring_run.fetch_attempt = fetch_attempt
            monitoring_run.last_was_refetch = was_refetch
            return FetchPersistenceResult(
                observation_count=observation_count,
                replaced_observation_count=previous_count,
                catalog_snapshot_count=catalog_snapshot_count,
                matched_observation_count=observation_count,
                unmatched_observation_count=0,
                was_refetch=bool(monitoring_run.last_was_refetch),
                fetch_attempt=int(monitoring_run.fetch_attempt or 0),
                persistence_status="persisted",
                warnings=warnings,
            )
        replacement = replace_price_observations(session, monitoring_run, observations)
    return FetchPersistenceResult(
        observation_count=replacement.observation_count,
        replaced_observation_count=replacement.replaced_observation_count,
        catalog_snapshot_count=catalog_snapshot_count,
        matched_observation_count=replacement.matched_observation_count,
        unmatched_observation_count=replacement.unmatched_observation_count,
        was_refetch=replacement.was_refetch,
        fetch_attempt=replacement.fetch_attempt,
        persistence_status="persisted",
        warnings=warnings,
    )


def _attach_source_url_capture_observations(
    session,
    monitoring_run,
    observation_batch_id: str | None = None,
    *,
    fetch_attempt: int,
    was_refetch: bool,
) -> int:
    query = session.query(PriceObservation)
    if observation_batch_id:
        rows = query.filter(PriceObservation.observation_batch_id == observation_batch_id).all()
    else:
        rows = query.filter(
            PriceObservation.run_id == monitoring_run.run_id,
            PriceObservation.monitoring_run_id.is_(None),
        ).all()
    attached_at = datetime.now(timezone.utc)
    for row in rows:
        if row.product_id is None:
            product, matched_by = match_product_for_observation(
                session,
                catalog_source=row.catalog_source,
                model=row.model,
                mpn=row.mpn,
            )
            if product is not None:
                row.product_id = product.id
                row.matched_by = row.matched_by or matched_by
        row.monitoring_run_id = monitoring_run.id
        row.run_id = monitoring_run.run_id
        raw_observation = dict(row.raw_observation or {})
        raw_observation["persistence"] = {
            "fetch_attempt": fetch_attempt,
            "was_refetch": was_refetch,
        }
        row.raw_observation = raw_observation
        row.created_at = attached_at
    session.flush()
    return count_price_observations(session, monitoring_run.run_id)


def _count_attached_source_url_observations(session, monitoring_run) -> int:
    return int(
        session.query(PriceObservation)
        .filter(
            PriceObservation.run_id == monitoring_run.run_id,
            PriceObservation.monitoring_run_id == monitoring_run.id,
        )
        .count()
    )


def _recover_catalog_rows(run_dir: Path) -> list[dict[str, Any]]:
    summary = _read_json_object(run_dir / "selection_summary.json")
    for key in ("selected_items", "items"):
        value = summary.get(key)
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return [dict(item) for item in value]
    input_path = run_dir / "input.csv"
    if input_path.exists():
        return _read_csv(input_path)
    return []


def _apply_selection_summary_metadata(monitoring_run, summary: dict[str, Any]) -> None:
    if not summary:
        return
    monitoring_run.selection_summary_path = monitoring_run.selection_summary_path or str(
        Path(str(monitoring_run.output_dir or "")) / "selection_summary.json"
    )
    if "selected_count" in summary:
        monitoring_run.selected_count = _int_or_none(summary.get("selected_count"))
    elif isinstance(summary.get("selected_models"), list):
        monitoring_run.selected_count = len(summary["selected_models"])
    if "skipped_count" in summary:
        monitoring_run.skipped_count = _int_or_none(summary.get("skipped_count"))
    elif isinstance(summary.get("skipped_models"), list):
        monitoring_run.skipped_count = len(summary["skipped_models"])


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        reader = csv.DictReader(f, delimiter=_detect_delimiter(sample))
        return [{key: value if value is not None else "" for key, value in row.items()} for row in reader]


def _detect_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        if dialect.delimiter in {",", ";", "\t"}:
            return dialect.delimiter
    except csv.Error:
        pass
    return ";" if sample.count(";") > sample.count(",") else ","


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
