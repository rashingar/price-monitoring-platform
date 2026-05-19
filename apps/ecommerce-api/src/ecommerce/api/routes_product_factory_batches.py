"""Resolve-only Product Factory CSV batch intake API routes."""

from __future__ import annotations

from email.parser import BytesParser
from email.policy import default as email_policy
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError

from ecommerce.db.config import DatabaseNotConfiguredError, sanitize_database_error
from ecommerce.db.session import session_scope
from ecommerce.product_factory_batch import repository
from ecommerce.product_factory_batch.csv_parser import ProductFactoryBatchCsvError
from ecommerce.product_factory_batch.models import (
    ProductFactoryBatchEnqueueResponse,
    ProductFactoryBatchJobStatusRefreshResponse,
    ProductFactoryBatchListResponse,
    ProductFactoryBatchResolveRequest,
    ProductFactoryBatchResolveResponse,
    ProductFactoryBatchResponse,
    ProductFactoryBatchRowsResponse,
    ProductFactoryBatchRowResponse,
    ProductFactoryBatchUploadResponse,
    SelectSourceRequest,
)
from ecommerce.product_factory_batch.enqueue import (
    enqueue_batch_row,
    enqueue_batch_selected,
    product_factory_client_from_env,
    refresh_batch_job_statuses,
)
from ecommerce.product_factory_batch.service import (
    ProductFactoryBatchError,
    create_batch_from_csv,
    prepare_batch_resolution,
    run_batch_resolution_background,
    select_source_for_row,
    skip_row,
)
from ecommerce.product_factory_source_resolution.config import SourceResolutionConfigError

router = APIRouter(prefix="/api/product-factory-batches", tags=["product-factory-batches"])


@router.post(
    "/upload",
    response_model=ProductFactoryBatchUploadResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {"file": {"type": "string", "format": "binary"}},
                    }
                }
            },
        }
    },
)
async def upload_product_factory_batch(request: Request) -> dict[str, Any]:
    try:
        content, filename = await _multipart_csv_upload(request)
        with session_scope() as session:
            batch = create_batch_from_csv(session, content=content, filename=filename)
            preview = [repository.row_to_dict(row) for row in batch.rows[:10]]
            return {**repository.batch_to_dict(batch), "preview_rows": preview}
    except ProductFactoryBatchCsvError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc
    except DatabaseNotConfiguredError as exc:
        raise _database_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable(exc) from exc


@router.get("", response_model=ProductFactoryBatchListResponse)
def list_product_factory_batches(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    try:
        with session_scope() as session:
            return {"items": [repository.batch_to_dict(batch) for batch in repository.list_batches(session, limit=limit, offset=offset)]}
    except DatabaseNotConfiguredError as exc:
        raise _database_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable(exc) from exc


@router.get("/{batch_id}", response_model=ProductFactoryBatchResponse)
def get_product_factory_batch(batch_id: int) -> dict[str, Any]:
    try:
        with session_scope() as session:
            batch = repository.get_batch(session, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found.")
            return repository.batch_to_dict(batch)
    except DatabaseNotConfiguredError as exc:
        raise _database_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable(exc) from exc


@router.get("/{batch_id}/rows", response_model=ProductFactoryBatchRowsResponse)
def get_product_factory_batch_rows(batch_id: int) -> dict[str, Any]:
    try:
        with session_scope() as session:
            batch = repository.get_batch(session, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found.")
            rows = repository.list_batch_rows(session, batch_id)
            return {"items": [repository.row_to_dict(row) for row in rows]}
    except DatabaseNotConfiguredError as exc:
        raise _database_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable(exc) from exc


@router.post("/{batch_id}/resolve", response_model=ProductFactoryBatchResolveResponse)
def resolve_product_factory_batch(
    batch_id: int,
    background_tasks: BackgroundTasks,
    request: ProductFactoryBatchResolveRequest | None = None,
) -> dict[str, Any]:
    should_start = False
    source_names: tuple[str, ...] = ()
    try:
        with session_scope() as session:
            batch = repository.get_batch(session, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found.")
            start = prepare_batch_resolution(session, batch=batch, source_names=request.source_names if request else None)
            batch = start.batch
            source_names = start.source_names
            should_start = start.should_start
            rows = repository.list_batch_rows(session, batch.id)
            payload = {**repository.batch_to_dict(batch), "rows": [repository.row_to_dict(row) for row in rows]}
        if should_start:
            _schedule_batch_resolution(background_tasks, batch_id=batch_id, source_names=source_names)
        return payload
    except ProductFactoryBatchError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    except SourceResolutionConfigError as exc:
        raise HTTPException(status_code=500, detail={"code": "source_resolution_config_error", "message": str(exc)}) from exc
    except DatabaseNotConfiguredError as exc:
        raise _database_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable(exc) from exc


@router.post("/{batch_id}/rows/{row_id}/select-source", response_model=ProductFactoryBatchRowResponse)
def select_product_factory_batch_row_source(batch_id: int, row_id: int, request: SelectSourceRequest) -> dict[str, Any]:
    try:
        with session_scope() as session:
            batch = repository.get_batch(session, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found.")
            row = repository.get_batch_row(session, batch_id=batch_id, row_id=row_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Batch row not found.")
            row = select_source_for_row(
                session,
                batch=batch,
                row=row,
                candidate_url=request.candidate_url,
                manual_url=request.manual_url,
            )
            return repository.row_to_dict(row)
    except ProductFactoryBatchError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc
    except SourceResolutionConfigError as exc:
        raise HTTPException(status_code=500, detail={"code": "source_resolution_config_error", "message": str(exc)}) from exc
    except DatabaseNotConfiguredError as exc:
        raise _database_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable(exc) from exc


@router.post("/{batch_id}/rows/{row_id}/skip", response_model=ProductFactoryBatchRowResponse)
def skip_product_factory_batch_row(batch_id: int, row_id: int) -> dict[str, Any]:
    try:
        with session_scope() as session:
            batch = repository.get_batch(session, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found.")
            row = repository.get_batch_row(session, batch_id=batch_id, row_id=row_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Batch row not found.")
            return repository.row_to_dict(skip_row(session, batch=batch, row=row))
    except DatabaseNotConfiguredError as exc:
        raise _database_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable(exc) from exc


@router.post("/{batch_id}/enqueue-selected", response_model=ProductFactoryBatchEnqueueResponse)
def enqueue_selected_product_factory_batch_rows(batch_id: int) -> dict[str, Any]:
    try:
        with session_scope() as session:
            batch = repository.get_batch(session, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found.")
            result = enqueue_batch_selected(session, batch=batch, product_factory_client=_product_factory_client())
            return {
                "batch_id": result.batch_id,
                "threshold": result.threshold,
                "enqueued_count": result.enqueued_count,
                "skipped_count": result.skipped_count,
                "forced_needs_review_count": result.forced_needs_review_count,
                "failed_count": result.failed_count,
                "rows": result.rows,
                "warnings": result.warnings,
                "errors": result.errors,
            }
    except DatabaseNotConfiguredError as exc:
        raise _database_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable(exc) from exc


@router.post("/{batch_id}/rows/{row_id}/enqueue", response_model=ProductFactoryBatchRowResponse)
def enqueue_product_factory_batch_row(batch_id: int, row_id: int) -> dict[str, Any]:
    try:
        with session_scope() as session:
            batch = repository.get_batch(session, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found.")
            row = repository.get_batch_row(session, batch_id=batch_id, row_id=row_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Batch row not found.")
            row = enqueue_batch_row(session, batch=batch, row=row, product_factory_client=_product_factory_client())
            return repository.row_to_dict(row)
    except ProductFactoryBatchError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    except DatabaseNotConfiguredError as exc:
        raise _database_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable(exc) from exc


@router.post("/{batch_id}/refresh-job-statuses", response_model=ProductFactoryBatchJobStatusRefreshResponse)
def refresh_product_factory_batch_job_statuses(batch_id: int) -> dict[str, Any]:
    try:
        with session_scope() as session:
            batch = repository.get_batch(session, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found.")
            result = refresh_batch_job_statuses(session, batch=batch, product_factory_client=_product_factory_client())
            return {
                "batch_id": result.batch_id,
                "refreshed_count": result.refreshed_count,
                "failed_count": result.failed_count,
                "rows": result.rows,
                "errors": result.errors,
            }
    except DatabaseNotConfiguredError as exc:
        raise _database_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable(exc) from exc


def _database_unavailable(exc: Exception) -> HTTPException:
    detail = {
        "message": "Product Factory batch intake requires the Ecommerce database.",
        "code": "product_factory_batch_database_required",
        "error": sanitize_database_error(exc),
    }
    return HTTPException(status_code=503, detail=detail)


async def _multipart_csv_upload(request: Request) -> tuple[bytes, str | None]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type.casefold():
        raise HTTPException(status_code=400, detail={"code": "expected_multipart_csv", "message": "Upload must be multipart/form-data."})
    body = await request.body()
    message = BytesParser(policy=email_policy).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    )
    if not message.is_multipart():
        raise HTTPException(status_code=400, detail={"code": "invalid_multipart_csv", "message": "Upload body is not valid multipart data."})
    for part in message.iter_parts():
        if part.get_param("name", header="content-disposition") != "file":
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            break
        return payload, part.get_filename()
    raise HTTPException(status_code=400, detail={"code": "missing_csv_file", "message": "Multipart upload must include a file field."})


def _schedule_batch_resolution(
    background_tasks: BackgroundTasks,
    *,
    batch_id: int,
    source_names: tuple[str, ...],
) -> None:
    background_tasks.add_task(run_batch_resolution_background, batch_id=batch_id, source_names=source_names)


def _product_factory_client():
    return product_factory_client_from_env()
