"""Catalog API routes backed by the active database catalog."""

from __future__ import annotations

from time import perf_counter
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from ecommerce.db.config import sanitize_database_error
from ecommerce.db.policy import require_database_ready_for_catalog
from ecommerce.db.repositories.catalog import (
    CatalogProductListFilters,
    get_catalog_brands,
    get_catalog_categories,
    get_catalog_category_hierarchy,
    get_catalog_product_detail,
    get_catalog_summary,
    list_catalog_products_page,
)
from ecommerce.db.session import session_scope
from ecommerce.ignore import MissingIgnoreColumnsError, load_ignored_products
from ecommerce.source_url_agent.candidate_history_service import (
    product_source_url_candidate_history_payload,
)

router = APIRouter(prefix="/api/catalog", tags=["catalog"])

MarketplaceFilter = Literal["bestprice", "skroutz", "both", "none"]
SortBy = Literal["model", "name", "manufacturer", "category", "price", "quantity"]
SortDir = Literal["asc", "desc"]
IgnoredFilter = Literal["include", "exclude", "only"]


@router.get("/products")
def get_products(
    q: str | None = None,
    category: str | None = None,
    family: str | None = None,
    category_name: str | None = None,
    sub_category: str | None = None,
    manufacturer: str | None = None,
    marketplace: MarketplaceFilter | None = None,
    source_name: str | None = None,
    has_mpn: bool | None = None,
    has_source_url: bool | None = None,
    has_quantity: bool | None = None,
    ignored: IgnoredFilter = "exclude",
    atomic_only: bool = False,
    automation_eligible_only: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    sort_by: SortBy | None = None,
    sort_dir: SortDir = "asc",
    debug: bool = False,
) -> dict:
    require_database_ready_for_catalog()
    ignored_models = _load_ignored_models_or_raise()
    filters = CatalogProductListFilters(
        q=q,
        category=category,
        family=family,
        category_name=category_name,
        sub_category=sub_category,
        manufacturer=manufacturer,
        marketplace=marketplace,
        source_name=source_name,
        has_mpn=has_mpn,
        has_source_url=has_source_url,
        has_quantity=has_quantity,
        ignored=ignored,
        atomic_only=atomic_only,
        automation_eligible_only=automation_eligible_only,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    started_at = perf_counter()
    try:
        with session_scope() as session:
            result = list_catalog_products_page(
                session, filters, ignored_models=ignored_models
            )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500, detail=f"Catalog DB query failed: {_safe_db_error(exc)}"
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Catalog DB query failed.") from exc

    payload = {
        "items": result.items,
        "page": result.page,
        "page_size": result.page_size,
        "total": result.total,
        "filtered_total": result.filtered_total,
        **_empty_catalog_warning_from_total(result.total),
    }
    if debug:
        payload["debug"] = {
            "query_mode": "database",
            "elapsed_ms": round((perf_counter() - started_at) * 1000, 3),
            "filters_applied": result.filters_applied,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "page": page,
            "page_size": page_size,
        }
    return payload


@router.get("/products/{catalog_product_id}")
def get_product_detail(catalog_product_id: int) -> dict:
    require_database_ready_for_catalog()
    ignored_models = _load_ignored_models_or_raise()
    try:
        with session_scope() as session:
            result = get_catalog_product_detail(
                session,
                catalog_product_id,
                ignored_models=ignored_models,
            )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500, detail=f"Catalog DB query failed: {_safe_db_error(exc)}"
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Catalog DB query failed.") from exc

    if result is None:
        raise HTTPException(status_code=404, detail="Catalog product not found.")
    return {
        "product": result.product,
        "source_urls": result.source_urls,
        "source_url_summary": result.source_url_summary,
        "warnings": result.warnings,
    }


@router.get("/products/{catalog_product_id}/source-url-candidates")
def get_product_source_url_candidate_history(catalog_product_id: int) -> dict:
    require_database_ready_for_catalog()
    try:
        with session_scope() as session:
            payload = product_source_url_candidate_history_payload(
                session, catalog_product_id
            )
            if not payload.product_exists:
                raise HTTPException(
                    status_code=404, detail="Catalog product not found."
                )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500, detail=f"Catalog DB query failed: {_safe_db_error(exc)}"
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Catalog DB query failed.") from exc

    return payload.to_dict()


@router.get("/categories")
def get_categories() -> dict:
    return _catalog_query_or_raise(get_catalog_categories)


@router.get("/category-hierarchy")
def get_category_hierarchy() -> dict:
    return _catalog_query_or_raise(get_catalog_category_hierarchy)


@router.get("/brands")
def get_brands() -> dict:
    return _catalog_query_or_raise(get_catalog_brands)


@router.get("/summary")
def get_summary() -> dict:
    return _catalog_query_or_raise(get_catalog_summary)


def _catalog_query_or_raise(query_func) -> dict:
    require_database_ready_for_catalog()
    try:
        with session_scope() as session:
            return query_func(session)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500, detail=f"Catalog DB query failed: {_safe_db_error(exc)}"
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Catalog DB query failed.") from exc


def _load_ignored_models_or_raise() -> set[str]:
    try:
        return {product.model for product in load_ignored_products()}
    except MissingIgnoreColumnsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Ignore list loading failed."
        ) from exc


def _empty_catalog_warning_from_total(total: int) -> dict[str, str]:
    if total:
        return {}
    return {
        "warning": "Active catalog is empty. Run python -m ecommerce.jobs.ingest_catalog."
    }


def _safe_db_error(exc: Exception) -> str:
    message = (
        str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    )
    return sanitize_database_error(message) or exc.__class__.__name__
