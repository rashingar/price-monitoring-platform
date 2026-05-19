"""Resolve-only Product Factory CSV batch intake service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ecommerce.db.models.product_factory_batch import ProductFactoryBatch, ProductFactoryBatchRow
from ecommerce.db.repositories.common import _now
from ecommerce.db.session import session_scope
from ecommerce.product_factory_batch import repository
from ecommerce.product_factory_batch.csv_parser import ProductFactoryBatchCsvError, parse_product_factory_batch_csv
from ecommerce.product_factory_source_resolution import (
    ProductFactorySourceResolver,
    SourceResolutionCandidate,
    SourceResolutionConfig,
    SourceResolutionError,
    SourceResolutionProduct,
    classify_supported_product_url,
    load_source_resolution_config,
)
from ecommerce.product_factory_source_resolution.config import SourceResolutionConfigError


SUPPORTED_BATCH_SOURCE_NAMES = ("skroutz", "bestprice", "electronet")
SOURCE_LABELS = {
    "skroutz": "Skroutz",
    "bestprice": "BestPrice",
    "electronet": "Electronet",
}
ELIGIBLE_RERESOLVE_STATUSES = {"pending", "resolving_source", "resolution_failed", "no_usable_source", "needs_review"}
RESOLUTION_STALE_AFTER = timedelta(minutes=30)


class ProductFactoryBatchError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class BatchResolutionStart:
    batch: ProductFactoryBatch
    source_names: tuple[str, ...]
    should_start: bool


@dataclass(frozen=True)
class RowResolutionSnapshot:
    id: int
    model: str
    brand: str
    name: str


def create_batch_from_csv(session: Session, *, content: bytes, filename: str | None) -> ProductFactoryBatch:
    parsed = parse_product_factory_batch_csv(content)
    return repository.create_batch(session, parsed=parsed, filename=filename)


def normalize_batch_source_names(source_names: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if source_names is None:
        return SUPPORTED_BATCH_SOURCE_NAMES
    normalized: list[str] = []
    unsupported: list[str] = []
    for value in source_names:
        source_name = str(value or "").strip().casefold()
        if not source_name:
            continue
        if source_name not in SUPPORTED_BATCH_SOURCE_NAMES:
            unsupported.append(source_name)
            continue
        if source_name not in normalized:
            normalized.append(source_name)
    if unsupported:
        raise ProductFactoryBatchError(
            "invalid_batch_source_names",
            f"Unsupported Product Factory batch source name(s): {', '.join(sorted(set(unsupported)))}.",
        )
    if not normalized:
        raise ProductFactoryBatchError(
            "invalid_batch_source_names",
            "Select at least one supported Product Factory batch source.",
        )
    return tuple(normalized)


def prepare_batch_resolution(
    session: Session,
    *,
    batch: ProductFactoryBatch,
    source_names: list[str] | tuple[str, ...] | None = None,
) -> BatchResolutionStart:
    selected_source_names = normalize_batch_source_names(source_names)
    metadata = dict(batch.metadata_json or {})
    existing_source_names = tuple(str(item).casefold() for item in metadata.get("selected_source_names") or [])
    now = _now()
    if batch.status == "resolving" and not _is_stale_resolving_batch(batch):
        if existing_source_names == selected_source_names:
            return BatchResolutionStart(batch=batch, source_names=selected_source_names, should_start=False)
        raise ProductFactoryBatchError(
            "batch_resolution_conflict",
            "This batch is already resolving with different search sources.",
            status_code=409,
        )

    metadata.update(
        {
            "selected_source_names": list(selected_source_names),
            "selected_source_labels": [SOURCE_LABELS[source_name] for source_name in selected_source_names],
            "source_selection_updated_at": now.isoformat(),
        }
    )
    if batch.status == "resolving":
        metadata["stale_resolution_restarted_at"] = now.isoformat()
    batch.metadata_json = metadata
    batch.status = "resolving"
    batch.updated_at = now
    session.flush()
    return BatchResolutionStart(batch=batch, source_names=selected_source_names, should_start=True)


def resolve_batch(
    session: Session,
    *,
    batch: ProductFactoryBatch,
    resolver: ProductFactorySourceResolver | None = None,
    config_path: str | Path | None = None,
    source_names: list[str] | tuple[str, ...] | None = None,
) -> ProductFactoryBatch:
    selected_source_names = normalize_batch_source_names(source_names)
    resolver = resolver or _batch_resolver(config_path, source_names=selected_source_names)
    for row in repository.list_batch_rows(session, batch.id):
        if not _row_is_eligible_for_resolution(row, selected_source_names):
            continue
        _mark_row_resolving(session, row=row)
        _apply_resolved_row(session, row=row, result=_resolve_snapshot(_snapshot_row(row), resolver))
        repository.refresh_batch_counts(session, batch)
        session.flush()
    return repository.refresh_batch_counts(session, batch)


def run_batch_resolution_background(
    *,
    batch_id: int,
    source_names: list[str] | tuple[str, ...],
    config_path: str | Path | None = None,
) -> None:
    selected_source_names = normalize_batch_source_names(source_names)
    try:
        resolver = _batch_resolver(config_path, source_names=selected_source_names)
    except Exception as exc:
        _mark_batch_failed(batch_id=batch_id, code="source_resolution_config_error", message=str(exc))
        return

    progressed = False
    try:
        for row_id in _eligible_row_ids(batch_id=batch_id, source_names=selected_source_names):
            snapshot = _mark_row_resolving_by_id(batch_id=batch_id, row_id=row_id)
            if snapshot is None:
                continue
            result = _resolve_snapshot(snapshot, resolver)
            _store_resolved_row(batch_id=batch_id, row_id=row_id, result=result)
            progressed = True
        _finalize_batch_resolution(batch_id=batch_id)
    except Exception as exc:
        _mark_batch_failed(
            batch_id=batch_id,
            code="batch_resolution_unexpected_error",
            message=str(exc).strip() or exc.__class__.__name__,
            progressed=progressed,
        )


def select_source_for_row(
    session: Session,
    *,
    batch: ProductFactoryBatch,
    row: ProductFactoryBatchRow,
    candidate_url: str | None = None,
    manual_url: str | None = None,
    config_path: str | Path | None = None,
) -> ProductFactoryBatchRow:
    if bool(candidate_url) == bool(manual_url):
        raise ProductFactoryBatchError("invalid_selection_request", "Provide exactly one of candidate_url or manual_url.")
    config = _batch_config(config_path)
    now = _now()
    if candidate_url:
        candidate = _candidate_by_url(row, candidate_url)
        if candidate is None:
            raise ProductFactoryBatchError("candidate_not_found", "Selected candidate URL does not exist on this row.")
        classified = classify_supported_product_url(str(candidate.get("url") or ""), config)
        if classified is None:
            raise ProductFactoryBatchError("unsupported_source_url", "Selected candidate URL is not a supported Product Factory product URL.")
        source, normalized_url = classified
        row.selected_url = normalized_url
        row.selected_source = source.source_name
        row.confidence = _int_or_none(candidate.get("confidence"))
        row.selection_metadata_json = {"selection_method": "candidate_manual", "candidate": candidate}
    else:
        classified = classify_supported_product_url(str(manual_url or ""), config)
        if classified is None:
            raise ProductFactoryBatchError("unsupported_source_url", "Manual URL is not a supported Product Factory product URL.")
        source, normalized_url = classified
        row.selected_url = normalized_url
        row.selected_source = source.source_name
        row.confidence = 100
        row.selection_metadata_json = {"selection_method": "manual_url"}
    row.status = "manually_selected"
    row.error_code = None
    row.error_message = None
    row.updated_at = now
    session.flush()
    repository.refresh_batch_counts(session, batch)
    return row


def skip_row(session: Session, *, batch: ProductFactoryBatch, row: ProductFactoryBatchRow) -> ProductFactoryBatchRow:
    row.status = "skipped"
    row.updated_at = _now()
    row.selection_metadata_json = {"selection_method": "skipped"}
    session.flush()
    repository.refresh_batch_counts(session, batch)
    return row


def _snapshot_row(row: ProductFactoryBatchRow) -> RowResolutionSnapshot:
    return RowResolutionSnapshot(id=row.id, model=row.model, brand=row.brand, name=row.name)


def _resolve_snapshot(snapshot: RowResolutionSnapshot, resolver: ProductFactorySourceResolver) -> dict[str, Any]:
    product = SourceResolutionProduct(model=snapshot.model, name=snapshot.name, brand=snapshot.brand)
    try:
        result = resolver.resolve(product=product, source_scoped_queries=True)
    except (SourceResolutionConfigError, SourceResolutionError) as exc:
        return {
            "status": "resolution_failed",
            "error_code": "source_resolution_error",
            "error_message": str(exc),
        }
    except Exception as exc:
        return {
            "status": "resolution_failed",
            "error_code": "source_resolution_unexpected_error",
            "error_message": str(exc).strip() or exc.__class__.__name__,
        }

    candidates = [_candidate_payload(candidate) for candidate in result.candidates]
    if result.selected is not None:
        return {
            "status": "auto_selected",
            "queries": list(result.queries),
            "candidates": candidates,
            "selected_url": result.selected.url,
            "selected_source": result.selected.source_name,
            "confidence": result.selected.confidence,
            "selection_metadata": {
                "selection_method": result.method,
                "source_names": list(result.config.preferred_source_names),
            },
        }
    elif result.candidates:
        return {
            "status": "needs_review",
            "queries": list(result.queries),
            "candidates": candidates,
            "selection_metadata": {
                "selection_method": "review_required",
                "source_names": list(result.config.preferred_source_names),
            },
        }
    return {
        "status": "no_usable_source",
        "queries": list(result.queries),
        "candidates": candidates,
        "selection_metadata": {
            "selection_method": "none",
            "source_names": list(result.config.preferred_source_names),
        },
    }


def _mark_row_resolving(session: Session, *, row: ProductFactoryBatchRow) -> None:
    now = _now()
    row.status = "resolving_source"
    row.selected_url = None
    row.selected_source = None
    row.confidence = None
    row.error_code = None
    row.error_message = None
    row.selection_metadata_json = {"selection_method": "resolving"}
    row.updated_at = now
    session.flush()


def _apply_resolved_row(session: Session, *, row: ProductFactoryBatchRow, result: dict[str, Any]) -> None:
    row.status = str(result.get("status") or "resolution_failed")
    row.queries_json = list(result.get("queries") or [])
    row.candidate_urls_json = list(result.get("candidates") or [])
    row.selected_url = result.get("selected_url") if isinstance(result.get("selected_url"), str) else None
    row.selected_source = result.get("selected_source") if isinstance(result.get("selected_source"), str) else None
    row.confidence = _int_or_none(result.get("confidence"))
    row.error_code = result.get("error_code") if isinstance(result.get("error_code"), str) else None
    row.error_message = result.get("error_message") if isinstance(result.get("error_message"), str) else None
    metadata = result.get("selection_metadata")
    row.selection_metadata_json = metadata if isinstance(metadata, dict) else None
    row.updated_at = _now()
    session.flush()


def _eligible_row_ids(*, batch_id: int, source_names: tuple[str, ...]) -> list[int]:
    with session_scope() as session:
        batch = repository.get_batch(session, batch_id)
        if batch is None:
            return []
        return [
            row.id
            for row in repository.list_batch_rows(session, batch_id)
            if _row_is_eligible_for_resolution(row, source_names)
        ]


def _mark_row_resolving_by_id(*, batch_id: int, row_id: int) -> RowResolutionSnapshot | None:
    with session_scope() as session:
        row = repository.get_batch_row(session, batch_id=batch_id, row_id=row_id)
        batch = repository.get_batch(session, batch_id)
        if row is None or batch is None or row.status in {"skipped", "manually_selected"}:
            return None
        _mark_row_resolving(session, row=row)
        repository.refresh_batch_counts(session, batch)
        return _snapshot_row(row)


def _store_resolved_row(*, batch_id: int, row_id: int, result: dict[str, Any]) -> None:
    with session_scope() as session:
        row = repository.get_batch_row(session, batch_id=batch_id, row_id=row_id)
        batch = repository.get_batch(session, batch_id)
        if row is None or batch is None or row.status in {"skipped", "manually_selected"}:
            return
        _apply_resolved_row(session, row=row, result=result)
        repository.refresh_batch_counts(session, batch)


def _finalize_batch_resolution(*, batch_id: int) -> None:
    with session_scope() as session:
        batch = repository.get_batch(session, batch_id)
        if batch is None:
            return
        repository.refresh_batch_counts(session, batch)


def _mark_batch_failed(*, batch_id: int, code: str, message: str, progressed: bool = False) -> None:
    with session_scope() as session:
        batch = repository.get_batch(session, batch_id)
        if batch is None:
            return
        metadata = dict(batch.metadata_json or {})
        metadata["resolution_error"] = {"code": code, "message": message, "progressed": progressed}
        metadata["resolution_failed_at"] = _now().isoformat()
        batch.metadata_json = metadata
        if progressed:
            repository.refresh_batch_counts(session, batch)
            batch.status = "partially_resolved"
            batch.updated_at = _now()
            session.flush()
        else:
            batch.status = "failed"
            batch.updated_at = _now()
            session.flush()


def _row_is_eligible_for_resolution(row: ProductFactoryBatchRow, source_names: tuple[str, ...]) -> bool:
    if row.status in ELIGIBLE_RERESOLVE_STATUSES:
        return True
    if row.status != "auto_selected":
        return False
    metadata = row.selection_metadata_json or {}
    previous_sources = tuple(str(item).casefold() for item in metadata.get("source_names") or [])
    return previous_sources != source_names


def _is_stale_resolving_batch(batch: ProductFactoryBatch) -> bool:
    updated_at = batch.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=_now().tzinfo)
    return _now() - updated_at > RESOLUTION_STALE_AFTER


def _batch_resolver(config_path: str | Path | None, *, source_names: list[str] | tuple[str, ...] | None = None) -> ProductFactorySourceResolver:
    return ProductFactorySourceResolver(config=_batch_config(config_path, source_names=source_names), source_scoped_queries=True)


def _batch_config(
    config_path: str | Path | None = None,
    *,
    source_names: list[str] | tuple[str, ...] | None = None,
) -> SourceResolutionConfig:
    return load_source_resolution_config(config_path).with_preferred_sources(normalize_batch_source_names(source_names))


def _candidate_payload(candidate: SourceResolutionCandidate) -> dict[str, Any]:
    payload = candidate.to_metadata()
    if candidate.description:
        payload["description"] = candidate.description
    return payload


def _candidate_by_url(row: ProductFactoryBatchRow, url: str) -> dict[str, Any] | None:
    requested = str(url or "").strip()
    for candidate in row.candidate_urls_json or []:
        if str(candidate.get("url") or "").strip() == requested:
            return candidate
    return None


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


__all__ = [
    "ProductFactoryBatchCsvError",
    "ProductFactoryBatchError",
    "SUPPORTED_BATCH_SOURCE_NAMES",
    "create_batch_from_csv",
    "normalize_batch_source_names",
    "prepare_batch_resolution",
    "resolve_batch",
    "run_batch_resolution_background",
    "select_source_for_row",
    "skip_row",
]
