"""Product-level ignore API routes."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ecommerce.ignore import (
    IgnoredProduct,
    IgnoredProductInput,
    InvalidIgnoredModelError,
    MissingIgnoreColumnsError,
    load_ignored_products,
    remove_ignored_product,
    upsert_ignored_product,
)

router = APIRouter(prefix="/api/ignore", tags=["ignore"])

SortBy = Literal["model", "name", "manufacturer", "mpn", "ignored_at"]
SortDir = Literal["asc", "desc"]


class IgnoredProductRequest(BaseModel):
    model: str | None = None
    name: str = ""
    manufacturer: str = ""
    mpn: str = ""
    reason: str = ""
    ignored_at: str = ""
    notes: str = ""


@router.get("/products")
def get_ignored_products(
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    sort_by: SortBy | None = None,
    sort_dir: SortDir = "asc",
) -> dict:
    products = _load_ignored_or_raise()
    filtered = _filter_products(products, q)
    if sort_by:
        filtered = sorted(filtered, key=lambda item: _sort_value(item, sort_by), reverse=sort_dir == "desc")

    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": [product.to_dict() for product in filtered[start:end]],
        "page": page,
        "page_size": page_size,
        "total": len(products),
        "filtered_total": len(filtered),
    }


@router.post("/products")
def post_ignored_product(request: IgnoredProductRequest) -> dict:
    try:
        stored = upsert_ignored_product(
            IgnoredProductInput(
                model=request.model or "",
                name=request.name,
                manufacturer=request.manufacturer,
                mpn=request.mpn,
                reason=request.reason,
                ignored_at=request.ignored_at,
                notes=request.notes,
            )
        )
    except InvalidIgnoredModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MissingIgnoreColumnsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Ignore list write failed.") from exc
    return stored.to_dict()


@router.delete("/products/{model}")
def delete_ignored_product(model: str) -> dict:
    normalized_model = str(model or "").strip()
    try:
        removed = remove_ignored_product(normalized_model)
    except MissingIgnoreColumnsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Ignore list write failed.") from exc
    return {"model": normalized_model, "removed": removed}


def _load_ignored_or_raise() -> list[IgnoredProduct]:
    try:
        return load_ignored_products()
    except MissingIgnoreColumnsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Ignore list loading failed.") from exc


def _filter_products(products: list[IgnoredProduct], q: str | None) -> list[IgnoredProduct]:
    q_norm = q.strip().casefold() if q else ""
    if not q_norm:
        return products
    return [product for product in products if _matches_query(product, q_norm)]


def _matches_query(product: IgnoredProduct, q_norm: str) -> bool:
    values = (product.model, product.mpn, product.name, product.manufacturer, product.reason, product.notes)
    return any(q_norm in value.casefold() for value in values)


def _sort_value(product: IgnoredProduct, sort_by: SortBy) -> str:
    return getattr(product, sort_by).casefold()
