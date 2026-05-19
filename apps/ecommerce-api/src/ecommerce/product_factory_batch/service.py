"""Resolve-only Product Factory CSV batch intake service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ecommerce.db.models.product_factory_batch import ProductFactoryBatch, ProductFactoryBatchRow
from ecommerce.db.repositories.common import _now
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


class ProductFactoryBatchError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def create_batch_from_csv(session: Session, *, content: bytes, filename: str | None) -> ProductFactoryBatch:
    parsed = parse_product_factory_batch_csv(content)
    return repository.create_batch(session, parsed=parsed, filename=filename)


def resolve_batch(
    session: Session,
    *,
    batch: ProductFactoryBatch,
    resolver: ProductFactorySourceResolver | None = None,
    config_path: str | Path | None = None,
) -> ProductFactoryBatch:
    resolver = resolver or _batch_resolver(config_path)
    for row in repository.list_batch_rows(session, batch.id):
        if row.status == "skipped":
            continue
        _resolve_row(session, row=row, resolver=resolver)
        repository.refresh_batch_counts(session, batch)
        session.flush()
    return repository.refresh_batch_counts(session, batch)


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


def _resolve_row(session: Session, *, row: ProductFactoryBatchRow, resolver: ProductFactorySourceResolver) -> None:
    product = SourceResolutionProduct(model=row.model, name=row.name, brand=row.brand)
    now = _now()
    try:
        result = resolver.resolve(product=product, source_scoped_queries=True)
    except (SourceResolutionConfigError, SourceResolutionError) as exc:
        row.status = "resolution_failed"
        row.error_code = "source_resolution_error"
        row.error_message = str(exc)
        row.updated_at = now
        session.flush()
        return
    except Exception as exc:
        row.status = "resolution_failed"
        row.error_code = "source_resolution_unexpected_error"
        row.error_message = str(exc).strip() or exc.__class__.__name__
        row.updated_at = now
        session.flush()
        return

    candidates = [_candidate_payload(candidate) for candidate in result.candidates]
    row.queries_json = list(result.queries)
    row.candidate_urls_json = candidates
    row.error_code = None
    row.error_message = None
    if result.selected is not None:
        row.status = "auto_selected"
        row.selected_url = result.selected.url
        row.selected_source = result.selected.source_name
        row.confidence = result.selected.confidence
        row.selection_metadata_json = {"selection_method": result.method}
    elif result.candidates:
        row.status = "needs_review"
        row.selected_url = None
        row.selected_source = None
        row.confidence = None
        row.selection_metadata_json = {"selection_method": "review_required"}
    else:
        row.status = "no_usable_source"
        row.selected_url = None
        row.selected_source = None
        row.confidence = None
        row.selection_metadata_json = {"selection_method": "none"}
    row.updated_at = now
    session.flush()


def _batch_resolver(config_path: str | Path | None) -> ProductFactorySourceResolver:
    return ProductFactorySourceResolver(config=_batch_config(config_path), source_scoped_queries=True)


def _batch_config(config_path: str | Path | None = None) -> SourceResolutionConfig:
    return load_source_resolution_config(config_path).with_preferred_sources(SUPPORTED_BATCH_SOURCE_NAMES)


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
    "resolve_batch",
    "select_source_for_row",
    "skip_row",
]
