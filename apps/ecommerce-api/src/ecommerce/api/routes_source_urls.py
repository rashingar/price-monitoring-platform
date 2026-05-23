"""Catalog source URL API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from ecommerce.db.config import sanitize_database_error
from ecommerce.db.policy import require_database_ready_for_catalog
from ecommerce.db.session import session_scope
from ecommerce.db.repositories.source_urls import (
    apply_source_url_validation_result,
    create_or_update_manual_source_url,
    get_active_catalog_product,
    get_source_url,
    list_source_urls_for_catalog_product,
    source_url_to_dict,
    update_source_url,
)
from ecommerce.source_urls import validate_source_url_reachability

router = APIRouter(prefix="/api/catalog", tags=["catalog-source-urls"])


class SourceUrlCreateRequest(BaseModel):
    url: str = Field(...)
    source_name: str | None = None
    url_type: str | None = "manual"
    provenance: str | None = None
    trust_level: str | None = None
    added_by: str | None = None
    notes: str | None = None


class SourceUrlUpdateRequest(BaseModel):
    url: str | None = None
    source_name: str | None = None
    status: str | None = None
    trust_level: str | None = None
    notes: str | None = None


@router.get("/products/{catalog_product_id}/source-urls")
def get_product_source_urls(catalog_product_id: int) -> dict:
    _require_catalog_database_ready()
    try:
        with session_scope() as session:
            product = get_active_catalog_product(session, catalog_product_id)
            if product is None:
                raise HTTPException(
                    status_code=404, detail="Catalog product not found."
                )
            items = [
                source_url_to_dict(item)
                for item in list_source_urls_for_catalog_product(
                    session, catalog_product_id
                )
            ]
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500, detail=f"Source URL query failed: {_safe_db_error(exc)}"
        ) from exc
    return {"items": items}


@router.post("/products/{catalog_product_id}/source-urls")
def post_product_source_url(
    catalog_product_id: int, request: SourceUrlCreateRequest
) -> dict:
    _require_catalog_database_ready()
    try:
        with session_scope() as session:
            row = create_or_update_manual_source_url(
                session, catalog_product_id, _model_payload(request, exclude_unset=True)
            )
            payload = source_url_to_dict(row)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500, detail=f"Source URL creation failed: {_safe_db_error(exc)}"
        ) from exc
    return payload


@router.patch("/source-urls/{source_url_id}")
def patch_source_url(source_url_id: int, request: SourceUrlUpdateRequest) -> dict:
    _require_catalog_database_ready()
    try:
        with session_scope() as session:
            row = update_source_url(
                session, source_url_id, _model_payload(request, exclude_unset=True)
            )
            if row is None:
                raise HTTPException(status_code=404, detail="Source URL not found.")
            payload = source_url_to_dict(row)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500, detail=f"Source URL update failed: {_safe_db_error(exc)}"
        ) from exc
    return payload


@router.post("/source-urls/{source_url_id}/validate")
def validate_source_url(source_url_id: int) -> dict:
    _require_catalog_database_ready()
    try:
        with session_scope() as session:
            row = get_source_url(session, source_url_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Source URL not found.")
            url = row.url_normalized
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500, detail=f"Source URL query failed: {_safe_db_error(exc)}"
        ) from exc

    result = validate_source_url_reachability(url)

    try:
        with session_scope() as session:
            row = apply_source_url_validation_result(session, source_url_id, result)
            if row is None:
                raise HTTPException(status_code=404, detail="Source URL not found.")
            payload = source_url_to_dict(row)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Source URL validation update failed: {_safe_db_error(exc)}",
        ) from exc
    return {"item": payload, "validation": result.to_dict()}


def _require_catalog_database_ready() -> None:
    require_database_ready_for_catalog()


def _model_payload(model: BaseModel, *, exclude_unset: bool) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=exclude_unset)
    return model.dict(exclude_unset=exclude_unset)


def _safe_db_error(exc: Exception) -> str:
    message = (
        str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    )
    return sanitize_database_error(message) or exc.__class__.__name__
