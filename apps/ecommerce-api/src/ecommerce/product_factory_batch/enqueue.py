"""Manual Product Factory enqueue support for batch intake rows."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.orm import Session

from ecommerce.db.models.product_factory_batch import (
    ProductFactoryBatch,
    ProductFactoryBatchRow,
)
from ecommerce.db.repositories.common import _now
from ecommerce.product_factory_batch import repository
from ecommerce.product_factory_batch.service import ProductFactoryBatchError
from ecommerce.product_factory_telegram.client import (
    ProductFactoryClient,
    ProductFactoryClientError,
    ProductFactoryJob,
)
from ecommerce.product_factory_telegram.config import (
    product_factory_telegram_config_from_env,
)

AUTO_ENQUEUE_CONFIDENCE_THRESHOLD_ENV = (
    "PRODUCT_FACTORY_BATCH_AUTO_ENQUEUE_CONFIDENCE_THRESHOLD"
)
DEFAULT_AUTO_ENQUEUE_CONFIDENCE_THRESHOLD = 85


class ProductFactoryJobClient(Protocol):
    def start_full_pipeline(self, payload: dict[str, Any]) -> ProductFactoryJob: ...

    def get_job(self, job_id: str) -> ProductFactoryJob: ...


@dataclass(frozen=True)
class BatchEnqueueResult:
    batch_id: int
    threshold: int
    enqueued_count: int
    skipped_count: int
    forced_needs_review_count: int
    failed_count: int
    rows: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class JobStatusRefreshResult:
    batch_id: int
    refreshed_count: int
    failed_count: int
    rows: list[dict[str, Any]]
    errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class BatchJobResetResult:
    batch_id: int
    reset_count: int
    rows: list[dict[str, Any]]


def batch_auto_enqueue_confidence_threshold() -> int:
    try:
        threshold = int(os.getenv(AUTO_ENQUEUE_CONFIDENCE_THRESHOLD_ENV, "").strip())
    except ValueError:
        threshold = DEFAULT_AUTO_ENQUEUE_CONFIDENCE_THRESHOLD
    if threshold < 1 or threshold > 100:
        return DEFAULT_AUTO_ENQUEUE_CONFIDENCE_THRESHOLD
    return threshold


def product_factory_client_from_env() -> ProductFactoryClient:
    return ProductFactoryClient(
        product_factory_telegram_config_from_env().product_factory_api_base_url
    )


def row_is_enqueueable(
    row: ProductFactoryBatchRow, *, threshold: int | None = None
) -> bool:
    effective_threshold = (
        threshold
        if threshold is not None
        else batch_auto_enqueue_confidence_threshold()
    )
    if not row.selected_url:
        return False
    if row.status == "manually_selected":
        return True
    if row.status == "auto_selected":
        return (row.confidence or 0) >= effective_threshold
    return False


def build_full_pipeline_payload(
    row: ProductFactoryBatchRow, batch: ProductFactoryBatch, *, threshold: int
) -> dict[str, Any]:
    return {
        "model": row.model,
        "product_name": row.name,
        "source_url": row.selected_url,
        "photos": 100,
        "sections": 20,
        "gallery_mode": "all",
        "bestprice_status": 1,
        "skroutz_status": 0,
        "boxnow": 0,
        "trigger_source": "csv_batch",
        "source_resolution": {
            "method": "batch_intake",
            "batch_id": batch.id,
            "row_id": row.id,
            "row_number": row.row_number,
            "brand": row.brand,
            "csv_name": row.name,
            "selected_source": row.selected_source,
            "selected_url": row.selected_url,
            "confidence": row.confidence,
            "selection_metadata": row.selection_metadata_json,
            "enqueue_threshold": threshold,
        },
    }


def enqueue_batch_selected(
    session: Session,
    *,
    batch: ProductFactoryBatch,
    product_factory_client: ProductFactoryJobClient | None = None,
    threshold: int | None = None,
) -> BatchEnqueueResult:
    client = product_factory_client or product_factory_client_from_env()
    effective_threshold = (
        threshold
        if threshold is not None
        else batch_auto_enqueue_confidence_threshold()
    )
    rows = repository.list_batch_rows(session, batch.id)
    forced = _force_low_confidence_auto_selected_rows(
        session, rows=rows, threshold=effective_threshold
    )
    enqueued_count = 0
    failed_count = 0
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []

    for row in rows:
        if row.product_factory_job_id:
            continue
        if not row_is_enqueueable(row, threshold=effective_threshold):
            continue
        try:
            _enqueue_row(
                session,
                batch=batch,
                row=row,
                product_factory_client=client,
                threshold=effective_threshold,
            )
            enqueued_count += 1
        except ProductFactoryClientError as exc:
            failed_count += 1
            message = str(exc)
            _store_enqueue_error(
                row, code="product_factory_enqueue_failed", message=message
            )
            errors.append(
                {
                    "row_id": row.id,
                    "row_number": row.row_number,
                    "code": "product_factory_enqueue_failed",
                    "message": message,
                }
            )
    skipped_count = max(0, len(rows) - enqueued_count - failed_count)
    if forced:
        warnings.append(
            f"{forced} low-confidence auto-selected row(s) were moved to needs_review before enqueue."
        )
    repository.refresh_batch_counts(session, batch)
    return BatchEnqueueResult(
        batch_id=batch.id,
        threshold=effective_threshold,
        enqueued_count=enqueued_count,
        skipped_count=skipped_count,
        forced_needs_review_count=forced,
        failed_count=failed_count,
        rows=[
            repository.row_to_dict(row)
            for row in repository.list_batch_rows(session, batch.id)
        ],
        warnings=warnings,
        errors=errors,
    )


def enqueue_batch_row(
    session: Session,
    *,
    batch: ProductFactoryBatch,
    row: ProductFactoryBatchRow,
    product_factory_client: ProductFactoryJobClient | None = None,
    threshold: int | None = None,
) -> ProductFactoryBatchRow:
    effective_threshold = (
        threshold
        if threshold is not None
        else batch_auto_enqueue_confidence_threshold()
    )
    _force_low_confidence_auto_selected_rows(
        session, rows=[row], threshold=effective_threshold
    )
    if row.product_factory_job_id:
        return row
    if not row_is_enqueueable(row, threshold=effective_threshold):
        repository.refresh_batch_counts(session, batch)
        session.commit()
        raise ProductFactoryBatchError(
            "batch_row_not_enqueueable",
            "Batch row is not eligible for Product Factory enqueue. Select or review a source URL first.",
        )
    client = product_factory_client or product_factory_client_from_env()
    try:
        _enqueue_row(
            session,
            batch=batch,
            row=row,
            product_factory_client=client,
            threshold=effective_threshold,
        )
    except ProductFactoryClientError as exc:
        message = str(exc)
        _store_enqueue_error(
            row, code="product_factory_enqueue_failed", message=message
        )
        session.flush()
        session.commit()
        raise ProductFactoryBatchError(
            "product_factory_enqueue_failed", message, status_code=502
        ) from exc
    repository.refresh_batch_counts(session, batch)
    return row


def refresh_batch_job_statuses(
    session: Session,
    *,
    batch: ProductFactoryBatch,
    product_factory_client: ProductFactoryJobClient | None = None,
) -> JobStatusRefreshResult:
    client = product_factory_client or product_factory_client_from_env()
    rows = repository.list_batch_rows(session, batch.id)
    refreshed_count = 0
    failed_count = 0
    errors: list[dict[str, Any]] = []
    for row in rows:
        if not row.product_factory_job_id:
            continue
        try:
            job = client.get_job(row.product_factory_job_id)
        except ProductFactoryClientError as exc:
            failed_count += 1
            message = str(exc)
            _store_enqueue_error(
                row, code="product_factory_status_refresh_failed", message=message
            )
            row.job_status_refreshed_at = _now()
            errors.append(
                {
                    "row_id": row.id,
                    "row_number": row.row_number,
                    "code": "product_factory_status_refresh_failed",
                    "message": message,
                }
            )
            continue
        _store_job(row, job=job, set_enqueued_at=False)
        refreshed_count += 1
    session.flush()
    return JobStatusRefreshResult(
        batch_id=batch.id,
        refreshed_count=refreshed_count,
        failed_count=failed_count,
        rows=[
            repository.row_to_dict(row)
            for row in repository.list_batch_rows(session, batch.id)
        ],
        errors=errors,
    )


def reset_batch_product_factory_jobs(
    session: Session,
    *,
    batch: ProductFactoryBatch,
) -> BatchJobResetResult:
    rows = repository.list_batch_rows(session, batch.id)
    reset_count = 0
    for row in rows:
        if not _row_has_product_factory_tracking(row):
            continue
        _clear_product_factory_tracking(row)
        reset_count += 1
    session.flush()
    return BatchJobResetResult(
        batch_id=batch.id,
        reset_count=reset_count,
        rows=[
            repository.row_to_dict(row)
            for row in repository.list_batch_rows(session, batch.id)
        ],
    )


def _force_low_confidence_auto_selected_rows(
    session: Session,
    *,
    rows: list[ProductFactoryBatchRow],
    threshold: int,
) -> int:
    forced = 0
    for row in rows:
        if (
            row.status != "auto_selected"
            or not row.selected_url
            or (row.confidence or 0) >= threshold
        ):
            continue
        metadata = dict(row.selection_metadata_json or {})
        metadata.update(
            {
                "selection_method": "auto_selected_below_enqueue_threshold",
                "enqueue_threshold": threshold,
                "requires_manual_review": True,
            }
        )
        row.status = "needs_review"
        row.selection_metadata_json = metadata
        row.updated_at = _now()
        forced += 1
    if forced:
        session.flush()
    return forced


def _enqueue_row(
    session: Session,
    *,
    batch: ProductFactoryBatch,
    row: ProductFactoryBatchRow,
    product_factory_client: ProductFactoryJobClient,
    threshold: int,
) -> None:
    job = product_factory_client.start_full_pipeline(
        build_full_pipeline_payload(row, batch, threshold=threshold)
    )
    _store_job(row, job=job, set_enqueued_at=True)
    session.flush()


def _store_job(
    row: ProductFactoryBatchRow, *, job: ProductFactoryJob, set_enqueued_at: bool
) -> None:
    now = _now()
    row.product_factory_job_id = job.job_id
    row.product_factory_job_status = job.status
    row.product_factory_job_message = job.message or job.error
    row.product_factory_error_code = job.error_code
    row.product_factory_error_message = job.error
    if set_enqueued_at and row.enqueued_at is None:
        row.enqueued_at = now
    row.job_status_refreshed_at = now
    row.updated_at = now


def _store_enqueue_error(
    row: ProductFactoryBatchRow, *, code: str, message: str
) -> None:
    now = _now()
    row.product_factory_error_code = code
    row.product_factory_error_message = message
    row.updated_at = now


def _row_has_product_factory_tracking(row: ProductFactoryBatchRow) -> bool:
    return any(
        value is not None
        for value in (
            row.product_factory_job_id,
            row.product_factory_job_status,
            row.product_factory_job_message,
            row.product_factory_error_code,
            row.product_factory_error_message,
            row.enqueued_at,
            row.job_status_refreshed_at,
        )
    )


def _clear_product_factory_tracking(row: ProductFactoryBatchRow) -> None:
    row.product_factory_job_id = None
    row.product_factory_job_status = None
    row.product_factory_job_message = None
    row.product_factory_error_code = None
    row.product_factory_error_message = None
    row.enqueued_at = None
    row.job_status_refreshed_at = None
    row.updated_at = _now()
