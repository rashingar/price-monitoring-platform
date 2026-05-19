"""Resolve-only Product Factory CSV batch intake API routes."""

from __future__ import annotations

from email.parser import BytesParser
from email.policy import default as email_policy
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError

from ecommerce.db.config import DatabaseNotConfiguredError, sanitize_database_error
from ecommerce.db.session import session_scope
from ecommerce.product_factory_batch import repository
from ecommerce.product_factory_batch.csv_parser import ProductFactoryBatchCsvError
from ecommerce.product_factory_batch.models import (
    ProductFactoryBatchListResponse,
    ProductFactoryBatchResolveResponse,
    ProductFactoryBatchResponse,
    ProductFactoryBatchRowsResponse,
    ProductFactoryBatchRowResponse,
    ProductFactoryBatchUploadResponse,
    SelectSourceRequest,
)
from ecommerce.product_factory_batch.service import (
    ProductFactoryBatchError,
    create_batch_from_csv,
    resolve_batch,
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
def resolve_product_factory_batch(batch_id: int) -> dict[str, Any]:
    try:
        with session_scope() as session:
            batch = repository.get_batch(session, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="Batch not found.")
            batch = resolve_batch(session, batch=batch)
            rows = repository.list_batch_rows(session, batch.id)
            return {**repository.batch_to_dict(batch), "rows": [repository.row_to_dict(row) for row in rows]}
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
