"""Portable Source URL Agent candidate export/import helpers."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecommerce.db.models.catalog import CatalogProductRow
from ecommerce.db.models.source_urls import SourceUrl, SourceUrlCandidate, SourceUrlDiscoveryRun
from ecommerce.db.repositories.source_convergence import sync_source_url_to_product_source
from ecommerce.source_urls import SourceUrlValidationError, normalize_source_url

EXPORT_FORMAT = "ecommerce.source_url_candidates.v1"
SOURCE_URL_TRANSFER_FORMAT = "ecommerce.source_urls_and_candidates.v1"

RUN_FIELDS = (
    "run_id",
    "source_name",
    "mode",
    "status",
    "input_path",
    "filters_json",
    "selected_count",
    "candidate_count",
    "matched_count",
    "needs_review_count",
    "not_found_count",
    "error_count",
    "started_at",
    "completed_at",
    "created_at",
    "updated_at",
)

CANDIDATE_FIELDS = (
    "run_id",
    "catalog_product_id",
    "catalog_source",
    "model",
    "mpn",
    "manufacturer",
    "product_name",
    "category",
    "own_price",
    "source_name",
    "source_domain",
    "source_type",
    "expected_listing",
    "candidate_url",
    "canonical_url",
    "candidate_title",
    "candidate_price",
    "match_status",
    "confidence_score",
    "match_method",
    "evidence_json",
    "competing_candidates_count",
    "searched_queries_json",
    "status",
    "reviewed_by",
    "reviewed_at",
    "notes",
    "created_at",
    "updated_at",
)

SOURCE_URL_FIELDS = (
    "catalog_product_id",
    "catalog_source",
    "model",
    "mpn",
    "manufacturer",
    "source_name",
    "source_domain",
    "url",
    "url_normalized",
    "status",
    "url_type",
    "trust_level",
    "added_by",
    "notes",
    "last_seen_at",
    "last_success_at",
    "last_failed_at",
    "failure_count",
    "last_error",
    "created_at",
    "updated_at",
)

DECIMAL_FIELDS = {"own_price", "candidate_price", "confidence_score"}
DATETIME_FIELDS = {
    "started_at",
    "completed_at",
    "created_at",
    "updated_at",
    "reviewed_at",
    "last_seen_at",
    "last_success_at",
    "last_failed_at",
}
INT_FIELDS = {
    "catalog_product_id",
    "selected_count",
    "candidate_count",
    "matched_count",
    "needs_review_count",
    "not_found_count",
    "error_count",
    "competing_candidates_count",
    "failure_count",
}


@dataclass
class CandidateTransferResult:
    path: str
    counters: Counter[str] = field(default_factory=Counter)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "counters": {key: int(value) for key, value in sorted(self.counters.items())},
            "warnings": list(self.warnings),
        }


def export_source_url_candidates(session: Session, output_path: Path) -> CandidateTransferResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    runs = list(session.execute(select(SourceUrlDiscoveryRun).order_by(SourceUrlDiscoveryRun.created_at, SourceUrlDiscoveryRun.id)).scalars())
    candidates = list(session.execute(select(SourceUrlCandidate).order_by(SourceUrlCandidate.created_at, SourceUrlCandidate.id)).scalars())
    payload = {
        "format": EXPORT_FORMAT,
        "exported_at": _json_value(_now()),
        "run_count": len(runs),
        "candidate_count": len(candidates),
        "runs": [_row_payload(row, RUN_FIELDS, original_id=True) for row in runs],
        "candidates": [_row_payload(row, CANDIDATE_FIELDS, original_id=True) for row in candidates],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result = CandidateTransferResult(path=str(output_path))
    result.counters["run_count"] = len(runs)
    result.counters["candidate_count"] = len(candidates)
    return result


def export_source_url_transfer(session: Session, output_path: Path) -> CandidateTransferResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_urls = list(session.execute(select(SourceUrl).order_by(SourceUrl.catalog_source, SourceUrl.model, SourceUrl.id)).scalars())
    runs = list(session.execute(select(SourceUrlDiscoveryRun).order_by(SourceUrlDiscoveryRun.created_at, SourceUrlDiscoveryRun.id)).scalars())
    candidates = list(session.execute(select(SourceUrlCandidate).order_by(SourceUrlCandidate.created_at, SourceUrlCandidate.id)).scalars())
    payload = {
        "format": SOURCE_URL_TRANSFER_FORMAT,
        "exported_at": _json_value(_now()),
        "source_url_count": len(source_urls),
        "run_count": len(runs),
        "candidate_count": len(candidates),
        "source_urls": [_row_payload(row, SOURCE_URL_FIELDS, original_id=True) for row in source_urls],
        "runs": [_row_payload(row, RUN_FIELDS, original_id=True) for row in runs],
        "candidates": [_row_payload(row, CANDIDATE_FIELDS, original_id=True) for row in candidates],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result = CandidateTransferResult(path=str(output_path))
    result.counters["source_url_count"] = len(source_urls)
    result.counters["run_count"] = len(runs)
    result.counters["candidate_count"] = len(candidates)
    return result


def import_source_url_candidates(session: Session, input_path: Path, *, apply: bool = False) -> CandidateTransferResult:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if payload.get("format") != EXPORT_FORMAT:
        raise ValueError(f"Unsupported source URL candidate export format: {payload.get('format')!r}")

    result = CandidateTransferResult(path=str(input_path))
    for run_payload in payload.get("runs") or []:
        _import_run(session, run_payload, result=result, apply=apply)
    for candidate_payload in payload.get("candidates") or []:
        _import_candidate(session, candidate_payload, result=result, apply=apply)
    if apply:
        session.flush()
    return result


def import_source_url_transfer(session: Session, input_path: Path, *, apply: bool = False) -> CandidateTransferResult:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if payload.get("format") != SOURCE_URL_TRANSFER_FORMAT:
        raise ValueError(f"Unsupported source URL transfer export format: {payload.get('format')!r}")

    result = CandidateTransferResult(path=str(input_path))
    for source_url_payload in payload.get("source_urls") or []:
        _import_source_url(session, source_url_payload, result=result, apply=apply)
    for run_payload in payload.get("runs") or []:
        _import_run(session, run_payload, result=result, apply=apply)
    for candidate_payload in payload.get("candidates") or []:
        _import_candidate(session, candidate_payload, result=result, apply=apply)
    if apply:
        session.flush()
    return result


def _import_source_url(
    session: Session,
    payload: dict[str, Any],
    *,
    result: CandidateTransferResult,
    apply: bool,
) -> None:
    product = _resolve_catalog_product(session, payload)
    if product is None:
        result.counters["missing_source_url_product_count"] += 1
        result.warnings.append(
            f"No catalog product matched {payload.get('catalog_source')}/{payload.get('model')}; skipped source URL original_id={payload.get('id')!r}."
        )
        return

    url = str(payload.get("url") or "").strip()
    normalized = str(payload.get("url_normalized") or "").strip()
    if not url:
        result.counters["invalid_source_url_count"] += 1
        result.warnings.append(f"Skipped source URL original_id={payload.get('id')!r} without url.")
        return
    if not normalized:
        try:
            normalized = normalize_source_url(url)
        except SourceUrlValidationError as exc:
            result.counters["invalid_source_url_count"] += 1
            result.warnings.append(f"Skipped source URL original_id={payload.get('id')!r}: {exc}")
            return

    row = session.execute(
        select(SourceUrl).where(
            SourceUrl.catalog_product_id == product.id,
            SourceUrl.url_normalized == normalized,
        )
    ).scalar_one_or_none()
    action = "updated_source_url_count" if row is not None else "created_source_url_count"
    if apply:
        if row is None:
            row = SourceUrl(**_default_source_url_values(payload, product, normalized))
            session.add(row)
        _assign_source_url_fields(row, payload, product, normalized)
        session.flush()
        sync_source_url_to_product_source(session, row)
    result.counters[action] += 1


def _import_run(
    session: Session,
    payload: dict[str, Any],
    *,
    result: CandidateTransferResult,
    apply: bool,
) -> None:
    run_id = str(payload.get("run_id") or "").strip()
    if not run_id:
        result.counters["invalid_run_count"] += 1
        result.warnings.append("Skipped discovery run without run_id.")
        return
    row = session.execute(select(SourceUrlDiscoveryRun).where(SourceUrlDiscoveryRun.run_id == run_id)).scalar_one_or_none()
    action = "updated_run_count" if row is not None else "created_run_count"
    if apply:
        if row is None:
            row = SourceUrlDiscoveryRun(run_id=run_id, created_at=_now(), updated_at=_now())
            session.add(row)
        _assign_fields(row, payload, RUN_FIELDS)
    result.counters[action] += 1


def _import_candidate(
    session: Session,
    payload: dict[str, Any],
    *,
    result: CandidateTransferResult,
    apply: bool,
) -> None:
    run_id = str(payload.get("run_id") or "").strip()
    source_name = str(payload.get("source_name") or "").strip()
    model = str(payload.get("model") or "").strip()
    catalog_source = str(payload.get("catalog_source") or "").strip()
    if not run_id or not source_name or not model or not catalog_source:
        result.counters["invalid_candidate_count"] += 1
        result.warnings.append(f"Skipped invalid candidate original_id={payload.get('id')!r}.")
        return

    product = _resolve_catalog_product(session, payload)
    if product is None:
        result.counters["missing_product_count"] += 1
        result.warnings.append(f"No catalog product matched {catalog_source}/{model}; candidate will import without promotion support.")

    row = _find_existing_candidate(session, payload)
    action = "updated_candidate_count" if row is not None else "created_candidate_count"
    if apply:
        if row is None:
            row = SourceUrlCandidate(**_default_candidate_values(payload))
            session.add(row)
        _assign_fields(row, payload, CANDIDATE_FIELDS)
        row.catalog_product_id = product.id if product is not None else None
    result.counters[action] += 1


def _find_existing_candidate(session: Session, payload: dict[str, Any]) -> SourceUrlCandidate | None:
    statement = select(SourceUrlCandidate).where(
        SourceUrlCandidate.run_id == str(payload.get("run_id") or "").strip(),
        SourceUrlCandidate.catalog_source == str(payload.get("catalog_source") or "").strip(),
        SourceUrlCandidate.model == str(payload.get("model") or "").strip(),
        SourceUrlCandidate.source_name == str(payload.get("source_name") or "").strip(),
    )
    candidate_url = str(payload.get("candidate_url") or "").strip()
    canonical_url = str(payload.get("canonical_url") or "").strip()
    if candidate_url:
        statement = statement.where(SourceUrlCandidate.candidate_url == candidate_url)
    elif canonical_url:
        statement = statement.where(SourceUrlCandidate.canonical_url == canonical_url)
    else:
        statement = statement.where(
            SourceUrlCandidate.match_status == str(payload.get("match_status") or "").strip(),
            SourceUrlCandidate.match_method == str(payload.get("match_method") or "").strip(),
        )
    return session.execute(statement.order_by(SourceUrlCandidate.id).limit(1)).scalar_one_or_none()


def _resolve_catalog_product(session: Session, payload: dict[str, Any]) -> CatalogProductRow | None:
    catalog_source = str(payload.get("catalog_source") or "").strip()
    model = str(payload.get("model") or "").strip()
    if catalog_source and model:
        row = session.execute(
            select(CatalogProductRow)
            .where(CatalogProductRow.catalog_source == catalog_source, CatalogProductRow.model == model)
            .order_by(CatalogProductRow.active.desc(), CatalogProductRow.id)
            .limit(1)
        ).scalar_one_or_none()
        if row is not None:
            return row
    product_id = _int_or_none(payload.get("catalog_product_id"))
    if product_id is None:
        return None
    row = session.get(CatalogProductRow, product_id)
    if row is not None and (not catalog_source or row.catalog_source == catalog_source):
        return row
    return None


def _assign_fields(row: object, payload: dict[str, Any], fields: tuple[str, ...]) -> None:
    for field_name in fields:
        if field_name == "catalog_product_id":
            continue
        if field_name not in payload:
            continue
        setattr(row, field_name, _db_value(field_name, payload.get(field_name)))


def _assign_source_url_fields(row: SourceUrl, payload: dict[str, Any], product: CatalogProductRow, normalized_url: str) -> None:
    _assign_fields(row, payload, SOURCE_URL_FIELDS)
    row.catalog_product_id = product.id
    row.catalog_source = product.catalog_source
    row.model = product.model
    row.mpn = product.mpn or ""
    row.manufacturer = product.manufacturer or ""
    row.url = str(payload.get("url") or "").strip()
    row.url_normalized = normalized_url


def _default_candidate_values(payload: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    return {
        "run_id": str(payload.get("run_id") or ""),
        "catalog_source": str(payload.get("catalog_source") or ""),
        "model": str(payload.get("model") or ""),
        "mpn": str(payload.get("mpn") or ""),
        "manufacturer": str(payload.get("manufacturer") or ""),
        "product_name": str(payload.get("product_name") or ""),
        "category": str(payload.get("category") or ""),
        "source_name": str(payload.get("source_name") or ""),
        "source_domain": str(payload.get("source_domain") or ""),
        "source_type": str(payload.get("source_type") or ""),
        "match_status": str(payload.get("match_status") or "needs_review"),
        "match_method": str(payload.get("match_method") or ""),
        "status": str(payload.get("status") or "needs_review"),
        "competing_candidates_count": _int_or_none(payload.get("competing_candidates_count")) or 0,
        "created_at": _db_value("created_at", payload.get("created_at")) or now,
        "updated_at": _db_value("updated_at", payload.get("updated_at")) or now,
    }


def _default_source_url_values(payload: dict[str, Any], product: CatalogProductRow, normalized_url: str) -> dict[str, Any]:
    now = _now()
    return {
        "catalog_product_id": product.id,
        "catalog_source": product.catalog_source,
        "model": product.model,
        "mpn": product.mpn or "",
        "manufacturer": product.manufacturer or "",
        "source_name": str(payload.get("source_name") or ""),
        "source_domain": str(payload.get("source_domain") or ""),
        "url": str(payload.get("url") or "").strip(),
        "url_normalized": normalized_url,
        "status": str(payload.get("status") or "needs_review"),
        "url_type": str(payload.get("url_type") or "imported"),
        "trust_level": str(payload.get("trust_level") or "imported"),
        "failure_count": _int_or_none(payload.get("failure_count")) or 0,
        "created_at": _db_value("created_at", payload.get("created_at")) or now,
        "updated_at": _db_value("updated_at", payload.get("updated_at")) or now,
    }


def _row_payload(row: object, fields: tuple[str, ...], *, original_id: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if original_id:
        payload["id"] = getattr(row, "id")
    for field_name in fields:
        payload[field_name] = _json_value(getattr(row, field_name))
    return payload


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _db_value(field_name: str, value: object) -> object:
    if value is None:
        return None
    if field_name in DECIMAL_FIELDS:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    if field_name in DATETIME_FIELDS:
        return _datetime_or_none(value)
    if field_name in INT_FIELDS:
        return _int_or_none(value)
    return value


def _datetime_or_none(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        text = str(value).strip()
        return int(text) if text else None
    except ValueError:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
