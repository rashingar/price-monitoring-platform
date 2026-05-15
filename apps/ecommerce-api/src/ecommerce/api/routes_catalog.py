"""Catalog API routes backed by the active database catalog."""

from __future__ import annotations

from collections import Counter
from numbers import Number
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from ecommerce.catalog import CatalogProduct
from ecommerce.catalog_db import load_active_catalog_products
from ecommerce.db.config import sanitize_database_error
from ecommerce.db.models.source_urls import SourceUrl
from ecommerce.db.policy import require_database_ready_for_catalog
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
) -> dict:
    products = _load_catalog_or_raise()
    ignored_models = _load_ignored_models_or_raise()
    source_filter = _source_filter(source_name)
    source_url_product_ids = _load_active_source_url_product_ids_or_raise(source_filter) if has_source_url is not None else None
    filtered = _filter_products(
        products,
        ignored_models=ignored_models,
        source_url_product_ids=source_url_product_ids,
        q=q,
        category=category,
        family=family,
        category_name=category_name,
        sub_category=sub_category,
        manufacturer=manufacturer,
        marketplace=marketplace,
        has_mpn=has_mpn,
        has_source_url=has_source_url,
        has_quantity=has_quantity,
        ignored=ignored,
        atomic_only=atomic_only,
        automation_eligible_only=automation_eligible_only,
    )

    if sort_by:
        filtered = sorted(filtered, key=lambda item: _sort_value(item, sort_by), reverse=sort_dir == "desc")

    start = (page - 1) * page_size
    end = start + page_size
    page_items = filtered[start:end]
    source_url_status_counts = _load_source_url_status_counts_or_raise(
        [product.catalog_product_id for product in page_items],
        source_filter,
    )
    return {
        "items": [
            _product_to_response(
                product,
                ignored_models,
                source_url_status_counts.get(product.catalog_product_id),
                source_filter,
            )
            for product in page_items
        ],
        "page": page,
        "page_size": page_size,
        "total": len(products),
        "filtered_total": len(filtered),
        **_empty_catalog_warning(products),
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


def _load_active_source_url_product_ids_or_raise(source_filter: str | None) -> set[int]:
    try:
        with session_scope() as session:
            statement = select(SourceUrl.catalog_product_id).where(SourceUrl.status == "active").distinct()
            if source_filter:
                statement = statement.where(SourceUrl.source_name.ilike(source_filter))
            return {int(product_id) for product_id in session.execute(statement).scalars().all() if product_id is not None}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL query failed: {_safe_db_error(exc)}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Source URL query failed.") from exc


def _load_source_url_status_counts_or_raise(
    catalog_product_ids: list[int | None],
    source_filter: str | None,
) -> dict[int, dict[str, int]]:
    product_ids = sorted({int(product_id) for product_id in catalog_product_ids if product_id is not None})
    if not product_ids:
        return {}
    try:
        with session_scope() as session:
            statement = (
                select(SourceUrl.catalog_product_id, SourceUrl.status, func.count(SourceUrl.id))
                .where(SourceUrl.catalog_product_id.in_(product_ids))
                .group_by(SourceUrl.catalog_product_id, SourceUrl.status)
            )
            if source_filter:
                statement = statement.where(SourceUrl.source_name.ilike(source_filter))
            counts: dict[int, dict[str, int]] = {}
            for product_id, status, count in session.execute(statement).all():
                if product_id is None:
                    continue
                product_counts = counts.setdefault(
                    int(product_id),
                    {"active": 0, "needs_review": 0, "broken": 0, "disabled": 0, "redirected": 0},
                )
                status_text = str(status or "")
                if status_text in product_counts:
                    product_counts[status_text] = int(count or 0)
            return counts
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL query failed: {_safe_db_error(exc)}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Source URL query failed.") from exc


def _filter_products(
    products: list[CatalogProduct],
    *,
    ignored_models: set[str],
    source_url_product_ids: set[int] | None,
    q: str | None,
    category: str | None,
    family: str | None,
    category_name: str | None,
    sub_category: str | None,
    manufacturer: str | None,
    marketplace: MarketplaceFilter | None,
    has_mpn: bool | None,
    has_source_url: bool | None,
    has_quantity: bool | None,
    ignored: IgnoredFilter,
    atomic_only: bool,
    automation_eligible_only: bool,
) -> list[CatalogProduct]:
    q_norm = q.strip().casefold() if q else ""
    category_norm = _trimmed_or_none(category)
    family_norm = _trimmed_or_none(family)
    category_name_norm = _trimmed_or_none(category_name)
    sub_category_norm = _trimmed_or_none(sub_category)
    manufacturer_norm = _trimmed_or_none(manufacturer)

    filtered: list[CatalogProduct] = []
    for product in products:
        is_ignored = product.model in ignored_models
        if ignored == "exclude" and is_ignored:
            continue
        if ignored == "only" and not is_ignored:
            continue
        if q_norm and not _matches_query(product, q_norm):
            continue
        if category_norm is not None and product.category != category_norm:
            continue
        if family_norm is not None and product.family != family_norm:
            continue
        if category_name_norm is not None and product.category_name != category_name_norm:
            continue
        if sub_category_norm is not None and product.sub_category != sub_category_norm:
            continue
        if manufacturer_norm is not None and product.manufacturer != manufacturer_norm:
            continue
        if marketplace and not _matches_marketplace(product, marketplace):
            continue
        if has_mpn is not None and bool(product.mpn) is not has_mpn:
            continue
        if has_source_url is not None:
            product_id = product.catalog_product_id
            product_has_source_url = (
                isinstance(product_id, int)
                and source_url_product_ids is not None
                and product_id in source_url_product_ids
            )
            if product_has_source_url is not has_source_url:
                continue
        if has_quantity is True and not _has_positive_active_quantity(product):
            continue
        if atomic_only and not product.is_atomic_model:
            continue
        if automation_eligible_only and not _is_automation_eligible(product, is_ignored):
            continue
        filtered.append(product)
    return filtered


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


def _product_to_response(
    product: CatalogProduct,
    ignored_models: set[str],
    source_url_status_counts: dict[str, int] | None = None,
    source_filter: str | None = None,
) -> dict:
    is_ignored = product.model in ignored_models
    status_counts = source_url_status_counts or {
        "active": 0,
        "needs_review": 0,
        "broken": 0,
        "disabled": 0,
        "redirected": 0,
    }
    active_count = int(status_counts.get("active") or 0)
    payload = product.to_dict()
    payload["ignored"] = is_ignored
    payload["automation_eligible"] = _is_automation_eligible(product, is_ignored)
    payload["source_url_coverage"] = {
        "catalog_product_id": product.catalog_product_id,
        "source": source_filter or "all",
        "has_active_source_url": active_count > 0,
        "active_source_url_count": active_count,
        "needs_review_source_url_count": int(status_counts.get("needs_review") or 0),
        "broken_source_url_count": int(status_counts.get("broken") or 0),
        "disabled_source_url_count": int(status_counts.get("disabled") or 0),
        "redirected_source_url_count": int(status_counts.get("redirected") or 0),
        "status_counts": dict(status_counts),
    }
    return payload


def _is_automation_eligible(product: CatalogProduct, is_ignored: bool) -> bool:
    return product.automation_eligible and not is_ignored


def _has_positive_active_quantity(product: CatalogProduct) -> bool:
    quantity = product.quantity
    return product.status == 1 and isinstance(quantity, Number) and not isinstance(quantity, bool) and quantity > 0


def _matches_query(product: CatalogProduct, q_norm: str) -> bool:
    values = (product.model, product.mpn, product.name, product.manufacturer)
    return any(q_norm in value.casefold() for value in values)


def _matches_marketplace(product: CatalogProduct, marketplace: MarketplaceFilter) -> bool:
    bestprice = product.bestprice_status == 1
    skroutz = product.skroutz_status == 1
    if marketplace == "bestprice":
        return bestprice
    if marketplace == "skroutz":
        return skroutz
    if marketplace == "both":
        return bestprice and skroutz
    return not bestprice and not skroutz


def _trimmed_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text if text else None


def _source_filter(value: str | None) -> str | None:
    text = _trimmed_or_none(value)
    if not text or text.casefold() == "all":
        return None
    return text.casefold()


def _sort_value(product: CatalogProduct, sort_by: SortBy) -> tuple[bool, object]:
    value = getattr(product, sort_by)
    if isinstance(value, str):
        return (False, value.casefold())
    return (value is None, value if value is not None else 0)


def _empty_catalog_warning(products: list[CatalogProduct]) -> dict[str, str]:
    if products:
        return {}
    return {"warning": "Active catalog is empty. Run python -m ecommerce.jobs.ingest_catalog."}


def _safe_db_error(exc: Exception) -> str:
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    return sanitize_database_error(message) or exc.__class__.__name__
