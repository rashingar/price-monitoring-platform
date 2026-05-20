from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from ecommerce.db.config import sanitize_database_error
from ecommerce.db.policy import require_database_ready_for_catalog
from ecommerce.db.repositories.products import create_product_from_source_urls
from ecommerce.db.repositories.products import product_to_dict
from ecommerce.db.session import session_scope

router = APIRouter(prefix="/api/products", tags=["product-sources"])


class ProductFromSourceRequest(BaseModel):
    model: str = Field(...)
    source_urls: list[str] = Field(...)
    capture: bool = True


@router.post("/from-source")
def post_product_from_source(request: ProductFromSourceRequest) -> dict[str, Any]:
    require_database_ready_for_catalog()
    try:
        with session_scope() as session:
            result = create_product_from_source_urls(
                session,
                model=request.model,
                source_urls=request.source_urls,
                capture=request.capture,
            )
            return {
                "product": product_to_dict(result.product),
                "sources": result.source_results,
            }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Product source ingestion failed: {_safe_db_error(exc)}",
        ) from exc


def _safe_db_error(exc: Exception) -> str:
    message = (
        str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    )
    return sanitize_database_error(message) or exc.__class__.__name__
