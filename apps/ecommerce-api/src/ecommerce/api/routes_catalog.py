"""Catalog API routes backed by the active database catalog."""

from __future__ import annotations

from collections import Counter
from time import perf_counter
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from ecommerce.catalog import CatalogProduct
from ecommerce.catalog_db import load_active_catalog_products
from ecommerce.db.config import sanitize_database_error
from ecommerce.db.policy import require_database_ready_for_catalog
from ecommerce.db.repositories.catalog import (
    CatalogProductListFilters,
    get_catalog_product_detail,
    list_catalog_products_page,
)
from ecommerce.db.session import session_scope
from ecommerce.ignore import MissingIgnoreColumnsError, load_ignored_products

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
            result = list_catalog_products_page(session, filters, ignored_models=ignored_models)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Catalog DB query failed: {_safe_db_error(exc)}") from exc
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
        raise HTTPException(status_code=500, detail=f"Catalog DB query failed: {_safe_db_error(exc)}") from exc
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


@router.get("/categories")
def get_categories() -> dict:
    products = _load_catalog_or_raise()
    counts = Counter(product.category for product in products if product.category)
    return {
        "items": [
            _category_to_response(category, counts[category], products)
            for category in sorted(counts)
        ],
        **_empty_catalog_warning(products),
    }


@router.get("/category-hierarchy")
def get_category_hierarchy() -> dict:
    products = _load_catalog_or_raise()
    hierarchy: dict[str, dict[str, dict[str, dict[str, object]]]] = {}

    for product in products:
        if not product.family:
            continue
        family_node = hierarchy.setdefault(product.family, {})
        category_node = family_node.setdefault(product.category_name, {})
        sub_node = category_node.setdefault(product.sub_category, {"count": 0, "raw_categories": set()})
        sub_node["count"] = int(sub_node["count"]) + 1
        if product.raw_category:
            raw_categories = sub_node["raw_categories"]
            if isinstance(raw_categories, set):
                raw_categories.add(product.raw_category)

    items: list[dict] = []
    for family in sorted(hierarchy):
        category_items: list[dict] = []
        family_count = 0
        for category_name in sorted(hierarchy[family]):
            sub_category_items: list[dict] = []
            category_count = 0
            for sub_category in sorted(hierarchy[family][category_name]):
                sub_node = hierarchy[family][category_name][sub_category]
                sub_count = int(sub_node["count"])
                category_count += sub_count
                raw_categories = sub_node["raw_categories"]
                sub_category_items.append(
                    {
                        "sub_category": sub_category,
                        "count": sub_count,
                        "raw_categories": sorted(raw_categories) if isinstance(raw_categories, set) else [],
                    }
                )
            family_count += category_count
            category_items.append(
                {
                    "category_name": category_name,
                    "count": category_count,
                    "sub_categories": sub_category_items,
                }
            )
        items.append({"family": family, "count": family_count, "categories": category_items})

    return {"items": items, **_empty_catalog_warning(products)}


@router.get("/brands")
def get_brands() -> dict:
    products = _load_catalog_or_raise()
    counts = Counter(product.manufacturer for product in products if product.manufacturer)
    return {
        "items": [
            {"manufacturer": manufacturer, "count": counts[manufacturer]}
            for manufacturer in sorted(counts)
        ],
        **_empty_catalog_warning(products),
    }


@router.get("/summary")
def get_summary() -> dict:
    products = _load_catalog_or_raise()
    categories = {product.category for product in products if product.category}
    families = {product.family for product in products if product.family}
    category_names = {product.category_name for product in products if product.category_name}
    sub_categories = {product.sub_category for product in products if product.sub_category}
    manufacturers = {product.manufacturer for product in products if product.manufacturer}
    return {
        "total_products": len(products),
        "active_products": sum(1 for product in products if product.status == 1),
        "atomic_products": sum(1 for product in products if product.is_atomic_model),
        "composite_or_invalid_models": sum(1 for product in products if not product.is_atomic_model),
        "bestprice_products": sum(1 for product in products if product.bestprice_status == 1),
        "skroutz_products": sum(1 for product in products if product.skroutz_status == 1),
        "missing_mpn": sum(1 for product in products if not product.mpn),
        "category_count": len(categories),
        "family_count": len(families),
        "category_name_count": len(category_names),
        "sub_category_count": len(sub_categories),
        "manufacturer_count": len(manufacturers),
        **_empty_catalog_warning(products),
    }


def _load_catalog_or_raise() -> list[CatalogProduct]:
    require_database_ready_for_catalog()
    try:
        return load_active_catalog_products()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Catalog DB query failed: {_safe_db_error(exc)}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Catalog DB query failed.") from exc


def _load_ignored_models_or_raise() -> set[str]:
    try:
        return {product.model for product in load_ignored_products()}
    except MissingIgnoreColumnsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Ignore list loading failed.") from exc


def _category_to_response(category: str, count: int, products: list[CatalogProduct]) -> dict:
    product = next(item for item in products if item.category == category)
    return {
        "category": category,
        "raw_category": product.raw_category,
        "family": product.family,
        "category_name": product.category_name,
        "sub_category": product.sub_category,
        "category_levels": product.category_levels,
        "count": count,
    }


def _empty_catalog_warning(products: list[CatalogProduct]) -> dict[str, str]:
    if products:
        return {}
    return {"warning": "Active catalog is empty. Run python -m ecommerce.jobs.ingest_catalog."}


def _empty_catalog_warning_from_total(total: int) -> dict[str, str]:
    if total:
        return {}
    return {"warning": "Active catalog is empty. Run python -m ecommerce.jobs.ingest_catalog."}


def _safe_db_error(exc: Exception) -> str:
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    return sanitize_database_error(message) or exc.__class__.__name__
