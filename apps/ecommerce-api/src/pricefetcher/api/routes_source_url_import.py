"""Source URL import reporting and apply API routes."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import distinct, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from pricefetcher.artifacts import ArtifactPathError, ArtifactPathForbiddenError, get_artifact_roots, resolve_artifact_path
from pricefetcher.catalog import DEFAULT_CATALOG_SOURCE
from pricefetcher.db.config import sanitize_database_error
from pricefetcher.db.models import CatalogProductRow, SourceUrl
from pricefetcher.db.policy import require_database_ready_for_catalog
from pricefetcher.db.repositories import json_safe_value
from pricefetcher.db.session import session_scope
from pricefetcher.db.source_url_repository import SOURCE_URL_STATUSES, SOURCE_URL_TYPES
from pricefetcher.file_editor import get_allowed_roots, is_path_allowed
from pricefetcher.product_agent_handoff import ProductAgentHandoffImportResult, import_product_agent_handoff
from pricefetcher.source_url_import import SUMMARY_COUNTERS, SourceUrlImportResult, import_source_urls

router = APIRouter(prefix="/api/catalog/source-urls", tags=["catalog-source-urls"])


class SourceUrlImportRequest(BaseModel):
    catalog_source: str = Field(default=DEFAULT_CATALOG_SOURCE)
    include_observations: bool = True
    include_artifacts: bool = True
    include_legacy_runs: bool = False
    legacy_runs_dir: str | None = None
    limit: int | None = None
    report_items_limit: int = 200


class ProductAgentHandoffImportRequest(BaseModel):
    file: str | None = None
    file_path: str | None = None
    catalog_source: str = Field(default=DEFAULT_CATALOG_SOURCE)
    persist_initial_capture: bool = True
    limit: int | None = None
    report_items_limit: int = 200


class SourceUrlImportSummary(BaseModel):
    candidates_found: int = 0
    imported_count: int = 0
    updated_count: int = 0
    would_import_count: int = 0
    would_update_count: int = 0
    skipped_count: int = 0
    active_count: int = 0
    needs_review_count: int = 0
    invalid_url_count: int = 0
    duplicate_count: int = 0
    unresolved_identity_count: int = 0
    ambiguous_identity_count: int = 0


class SourceUrlImportSourceStats(BaseModel):
    processed: int = 0
    candidates: int = 0


class SourceUrlImportCandidateReport(BaseModel):
    url: str | None = None
    url_normalized: str | None = None
    source_name: str | None = None
    source_domain: str | None = None
    catalog_source: str | None = None
    catalog_product_id: int | None = None
    source_url_id: int | None = None
    model: str | None = None
    mpn: str | None = None
    status: str | None = None
    action: str
    confidence: str | None = None
    evidence_source: str | None = None
    evidence_detail: str | None = None
    reason: str | None = None


class SourceUrlImportResponse(BaseModel):
    mode: str
    applied: bool
    summary: SourceUrlImportSummary
    sources: dict[str, SourceUrlImportSourceStats]
    items: list[SourceUrlImportCandidateReport]
    truncated: bool
    warnings: list[str]


class SourceUrlSummaryResponse(BaseModel):
    catalog_source: str
    catalog_product_count: int
    products_with_active_source_urls: int
    products_without_active_source_urls: int
    coverage_percent: float
    source_url_count: int
    by_status: dict[str, int]
    by_source_name: dict[str, int]
    by_url_type: dict[str, int]
    updated_at: str


@router.get("/summary", response_model=SourceUrlSummaryResponse)
def get_source_url_summary(catalog_source: str = DEFAULT_CATALOG_SOURCE) -> dict[str, Any]:
    _require_catalog_database_ready()
    catalog_source = _validated_catalog_source(catalog_source)
    try:
        with session_scope() as session:
            return _source_url_summary(session, catalog_source)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL summary failed: {_safe_db_error(exc)}") from exc


@router.post("/import/preview", response_model=SourceUrlImportResponse)
def preview_source_url_import(request: SourceUrlImportRequest) -> dict[str, Any]:
    return _run_source_url_import(request, apply=False)


@router.post("/import/apply", response_model=SourceUrlImportResponse)
def apply_source_url_import(request: SourceUrlImportRequest) -> dict[str, Any]:
    return _run_source_url_import(request, apply=True)


@router.post("/import/product-agent/preview", response_model=SourceUrlImportResponse)
def preview_product_agent_handoff_import(request: ProductAgentHandoffImportRequest) -> dict[str, Any]:
    return _run_product_agent_handoff_import(request, apply=False)


@router.post("/import/product-agent/apply", response_model=SourceUrlImportResponse)
def apply_product_agent_handoff_import(request: ProductAgentHandoffImportRequest) -> dict[str, Any]:
    return _run_product_agent_handoff_import(request, apply=True)


@router.get("/import/options")
def get_source_url_import_options() -> dict[str, Any]:
    return {
        "default_catalog_source": DEFAULT_CATALOG_SOURCE,
        "supports_observations": True,
        "supports_artifacts": True,
        "supports_legacy_runs": True,
        "supports_product_agent_handoff": True,
        "legacy_runs_default_enabled": False,
        "requires_apply_confirmation": True,
        "notes": [
            "Preview is a dry-run and does not write database rows.",
            "Apply writes source_urls through the same importer used by the CLI.",
            "Stored source URLs can be captured through DB-backed Vendor Sources capture.",
        ],
    }


def _run_source_url_import(request: SourceUrlImportRequest, *, apply: bool) -> dict[str, Any]:
    _require_catalog_database_ready()
    payload = _validated_import_request(request)
    try:
        with session_scope() as session:
            result = import_source_urls(
                session,
                apply=apply,
                catalog_source=payload["catalog_source"],
                include_observations=payload["include_observations"],
                include_artifacts=payload["include_artifacts"],
                legacy_runs_dir=payload["legacy_runs_dir"],
                limit=payload["limit"],
            )
            return _import_response(result, apply=apply, report_items_limit=payload["report_items_limit"])
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL import failed: {_safe_db_error(exc)}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Source URL import failed: {type(exc).__name__}") from exc


def _run_product_agent_handoff_import(request: ProductAgentHandoffImportRequest, *, apply: bool) -> dict[str, Any]:
    _require_catalog_database_ready()
    payload = _validated_product_agent_handoff_request(request)
    try:
        with session_scope() as session:
            result = import_product_agent_handoff(
                session,
                file_path=payload["file_path"],
                apply=apply,
                catalog_source=payload["catalog_source"],
                persist_initial_capture=payload["persist_initial_capture"],
                limit=payload["limit"],
            )
            return _handoff_import_response(result, apply=apply, report_items_limit=payload["report_items_limit"])
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Product-Agent handoff import failed: {_safe_db_error(exc)}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Product-Agent handoff import failed: {type(exc).__name__}") from exc


def _source_url_summary(session: Session, catalog_source: str) -> dict[str, Any]:
    active_catalog_filter = (
        CatalogProductRow.catalog_source == catalog_source,
        CatalogProductRow.active.is_(True),
    )
    catalog_product_count = int(
        session.execute(select(func.count(CatalogProductRow.id)).where(*active_catalog_filter)).scalar_one()
    )
    active_source_product_count = int(
        session.execute(
            select(func.count(distinct(SourceUrl.catalog_product_id)))
            .join(CatalogProductRow, SourceUrl.catalog_product_id == CatalogProductRow.id)
            .where(*active_catalog_filter, SourceUrl.status == "active")
        ).scalar_one()
    )
    source_url_count = int(
        session.execute(
            select(func.count(SourceUrl.id))
            .join(CatalogProductRow, SourceUrl.catalog_product_id == CatalogProductRow.id)
            .where(*active_catalog_filter)
        ).scalar_one()
    )
    by_status = _grouped_counts(session, SourceUrl.status, catalog_source)
    by_source_name = _grouped_counts(session, SourceUrl.source_name, catalog_source)
    by_url_type = _grouped_counts(session, SourceUrl.url_type, catalog_source)
    updated_at = session.execute(
        select(func.max(SourceUrl.updated_at))
        .join(CatalogProductRow, SourceUrl.catalog_product_id == CatalogProductRow.id)
        .where(*active_catalog_filter)
    ).scalar_one_or_none()
    if updated_at is None:
        updated_at = datetime.now(timezone.utc).replace(microsecond=0)

    products_without = max(catalog_product_count - active_source_product_count, 0)
    coverage = round((active_source_product_count / catalog_product_count) * 100, 2) if catalog_product_count else 0.0
    return {
        "catalog_source": catalog_source,
        "catalog_product_count": catalog_product_count,
        "products_with_active_source_urls": active_source_product_count,
        "products_without_active_source_urls": products_without,
        "coverage_percent": coverage,
        "source_url_count": source_url_count,
        "by_status": {status: int(by_status.get(status, 0)) for status in sorted(SOURCE_URL_STATUSES)},
        "by_source_name": by_source_name,
        "by_url_type": {url_type: int(by_url_type.get(url_type, 0)) for url_type in sorted(SOURCE_URL_TYPES)},
        "updated_at": str(json_safe_value(updated_at)),
    }


def _grouped_counts(session: Session, column, catalog_source: str) -> dict[str, int]:
    rows = session.execute(
        select(column, func.count(SourceUrl.id))
        .join(CatalogProductRow, SourceUrl.catalog_product_id == CatalogProductRow.id)
        .where(
            CatalogProductRow.catalog_source == catalog_source,
            CatalogProductRow.active.is_(True),
        )
        .group_by(column)
        .order_by(column.asc())
    ).all()
    return {str(key or ""): int(value) for key, value in rows}


def _import_response(result: SourceUrlImportResult, *, apply: bool, report_items_limit: int) -> dict[str, Any]:
    items = [_api_report_item(item, apply=apply) for item in result.report_items]
    truncated = len(items) > report_items_limit
    if truncated:
        items = items[:report_items_limit]
    return {
        "mode": "apply" if apply else "preview",
        "applied": apply,
        "summary": _import_summary(result, apply=apply),
        "sources": _source_stats(result),
        "items": items,
        "truncated": truncated,
        "warnings": list(result.warnings),
    }


def _import_summary(result: SourceUrlImportResult, *, apply: bool) -> dict[str, int]:
    counters = {key: int(result.counters.get(key, 0)) for key in SUMMARY_COUNTERS}
    summary = dict(counters)
    if apply:
        summary["would_import_count"] = 0
        summary["would_update_count"] = 0
    else:
        summary["would_import_count"] = counters["imported_count"]
        summary["would_update_count"] = counters["updated_count"]
        summary["imported_count"] = 0
        summary["updated_count"] = 0
    return summary


def _source_stats(result: SourceUrlImportResult) -> dict[str, dict[str, int]]:
    payload = {}
    for key in ("observations", "artifacts", "legacy_runs"):
        stats = result.source_stats.get(key, {})
        payload[key] = {
            "processed": int(stats.get("processed", 0)),
            "candidates": int(stats.get("candidates", 0)),
        }
    return payload


def _api_report_item(item: dict[str, Any], *, apply: bool) -> dict[str, Any]:
    action = str(item.get("action") or "")
    if not apply:
        action = {"created": "would_import", "updated": "would_update"}.get(action, action)
    else:
        action = {"created": "imported"}.get(action, action)
    return {
        "url": item.get("url"),
        "url_normalized": item.get("url_normalized"),
        "source_name": item.get("source_name"),
        "source_domain": item.get("source_domain"),
        "catalog_source": item.get("catalog_source"),
        "catalog_product_id": item.get("catalog_product_id"),
        "source_url_id": item.get("source_url_id"),
        "model": item.get("model"),
        "mpn": item.get("mpn"),
        "status": item.get("status"),
        "action": action or "unknown",
        "confidence": item.get("confidence"),
        "evidence_source": item.get("evidence_source"),
        "evidence_detail": item.get("evidence_detail"),
        "reason": item.get("reason"),
    }


def _handoff_import_response(
    result: ProductAgentHandoffImportResult,
    *,
    apply: bool,
    report_items_limit: int,
) -> dict[str, Any]:
    items = [_api_report_item(item, apply=apply) for item in result.report_items]
    truncated = len(items) > report_items_limit
    if truncated:
        items = items[:report_items_limit]
    return {
        "mode": "apply" if apply else "preview",
        "applied": apply,
        "summary": _handoff_import_summary(result, apply=apply),
        "sources": _handoff_source_stats(result),
        "items": items,
        "truncated": truncated,
        "warnings": list(result.warnings),
    }


def _handoff_import_summary(result: ProductAgentHandoffImportResult, *, apply: bool) -> dict[str, int]:
    counters = {key: int(result.counters.get(key, 0)) for key in SUMMARY_COUNTERS}
    summary = dict(counters)
    if apply:
        summary["would_import_count"] = 0
        summary["would_update_count"] = 0
    else:
        summary["would_import_count"] = counters["imported_count"]
        summary["would_update_count"] = counters["updated_count"]
        summary["imported_count"] = 0
        summary["updated_count"] = 0
    return summary


def _handoff_source_stats(result: ProductAgentHandoffImportResult) -> dict[str, dict[str, int]]:
    stats = result.source_stats.get("product_agent_handoff", {})
    return {
        "product_agent_handoff": {
            "processed": int(stats.get("processed", 0)),
            "candidates": int(stats.get("candidates", 0)),
        }
    }


def _validated_import_request(request: SourceUrlImportRequest) -> dict[str, Any]:
    payload = _model_payload(request, exclude_unset=False)
    catalog_source = _validated_catalog_source(payload.get("catalog_source"))
    include_observations = bool(payload.get("include_observations", True))
    include_artifacts = bool(payload.get("include_artifacts", True))
    include_legacy_runs = bool(payload.get("include_legacy_runs", False))
    if not include_observations and not include_artifacts and not include_legacy_runs:
        raise HTTPException(status_code=400, detail="At least one import source must be enabled.")

    legacy_runs_dir = _optional_text(payload.get("legacy_runs_dir"))
    if legacy_runs_dir and not include_legacy_runs:
        raise HTTPException(status_code=400, detail="include_legacy_runs must be true when legacy_runs_dir is provided.")
    resolved_legacy_runs_dir = _validated_legacy_runs_dir(legacy_runs_dir) if include_legacy_runs else None

    return {
        "catalog_source": catalog_source,
        "include_observations": include_observations,
        "include_artifacts": include_artifacts,
        "legacy_runs_dir": resolved_legacy_runs_dir,
        "limit": _validated_optional_positive_int(payload.get("limit"), "limit"),
        "report_items_limit": _validated_report_items_limit(payload.get("report_items_limit")),
    }


def _validated_product_agent_handoff_request(request: ProductAgentHandoffImportRequest) -> dict[str, Any]:
    payload = _model_payload(request, exclude_unset=False)
    file_path = _optional_text(payload.get("file_path")) or _optional_text(payload.get("file"))
    if not file_path:
        raise HTTPException(status_code=400, detail="file is required.")
    path = _validated_product_agent_handoff_path(file_path)
    return {
        "file_path": path,
        "catalog_source": _validated_catalog_source(payload.get("catalog_source")),
        "persist_initial_capture": bool(payload.get("persist_initial_capture", True)),
        "limit": _validated_optional_positive_int(payload.get("limit"), "limit"),
        "report_items_limit": _validated_report_items_limit(payload.get("report_items_limit")),
    }


def _validated_product_agent_handoff_path(value: str) -> Path:
    requested = Path(value)
    if requested.name != "price_fetcher_source_handoff.json":
        raise HTTPException(status_code=400, detail="file must be a price_fetcher_source_handoff.json artifact.")
    if _contains_parent_reference(requested):
        raise HTTPException(status_code=400, detail="file must not contain path traversal.")
    path = requested.expanduser().resolve(strict=False)
    if not _product_agent_handoff_path_allowed(path):
        allowed = ", ".join(_display_path(root) for root in _product_agent_handoff_allowed_roots())
        raise HTTPException(
            status_code=400,
            detail=f"file must be inside allowed artifact roots or configured file roots. Allowed roots: {allowed}",
        )
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=400, detail="file must be an existing handoff JSON file.")
    return path


def _product_agent_handoff_path_allowed(path: Path) -> bool:
    return is_path_allowed(path, _product_agent_handoff_allowed_roots())


def _product_agent_handoff_allowed_roots() -> list[Path]:
    roots = [root.expanduser().resolve(strict=False) for root in get_artifact_roots()]
    roots.extend(get_allowed_roots())
    return _dedupe_paths(roots)


def _validated_legacy_runs_dir(value: str | None) -> Path | None:
    if not value:
        raise HTTPException(status_code=400, detail="legacy_runs_dir is required when include_legacy_runs is true.")
    try:
        path = resolve_artifact_path(value)
    except ArtifactPathForbiddenError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ArtifactPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=400, detail="legacy_runs_dir must be an existing artifact directory.")
    return path


def _validated_catalog_source(value: object) -> str:
    text = _optional_text(value)
    if not text:
        raise HTTPException(status_code=400, detail="catalog_source is required.")
    return text


def _validated_optional_positive_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{field_name} must be an integer.") from None
    if number < 1:
        raise HTTPException(status_code=400, detail=f"{field_name} must be greater than 0.")
    return number


def _validated_report_items_limit(value: object) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="report_items_limit must be an integer.") from None
    if number < 0 or number > 1000:
        raise HTTPException(status_code=400, detail="report_items_limit must be between 0 and 1000.")
    return number


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _contains_parent_reference(path: Path) -> bool:
    return any(part == ".." for part in path.parts)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path.expanduser().resolve(strict=False)).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _display_path(path: Path) -> str:
    resolved = path.expanduser().resolve(strict=False)
    try:
        return str(resolved.relative_to(Path.cwd().resolve(strict=False)))
    except ValueError:
        return str(resolved)


def _require_catalog_database_ready() -> None:
    require_database_ready_for_catalog()


def _model_payload(model: BaseModel, *, exclude_unset: bool) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=exclude_unset)
    return model.dict(exclude_unset=exclude_unset)


def _safe_db_error(exc: Exception) -> str:
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    return sanitize_database_error(message) or exc.__class__.__name__
