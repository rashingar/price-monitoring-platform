"""SQL-backed catalog product listing queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import and_, case, desc, exists, false, func, or_, select
from sqlalchemy.orm import Session

from ecommerce.catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.models.catalog import CatalogProductRow
from ecommerce.db.models.source_urls import SourceUrl

MarketplaceFilter = Literal["bestprice", "skroutz", "both", "none"]
SortBy = Literal["model", "name", "manufacturer", "category", "price", "quantity"]
SortDir = Literal["asc", "desc"]
IgnoredFilter = Literal["include", "exclude", "only"]

SOURCE_URL_STATUSES = ("active", "needs_review", "broken", "disabled", "redirected")


@dataclass(frozen=True)
class CatalogProductListFilters:
    q: str | None = None
    category: str | None = None
    family: str | None = None
    category_name: str | None = None
    sub_category: str | None = None
    manufacturer: str | None = None
    marketplace: MarketplaceFilter | None = None
    source_name: str | None = None
    has_mpn: bool | None = None
    has_source_url: bool | None = None
    has_quantity: bool | None = None
    ignored: IgnoredFilter = "exclude"
    atomic_only: bool = False
    automation_eligible_only: bool = False
    page: int = 1
    page_size: int = 100
    sort_by: SortBy | None = None
    sort_dir: SortDir = "asc"
    catalog_source: str = DEFAULT_CATALOG_SOURCE


@dataclass(frozen=True)
class CatalogProductListResult:
    items: list[dict[str, Any]]
    page: int
    page_size: int
    total: int
    filtered_total: int
    filters_applied: list[str] = field(default_factory=list)


def list_catalog_products_page(
    session: Session,
    filters: CatalogProductListFilters,
    *,
    ignored_models: set[str],
) -> CatalogProductListResult:
    """Return a filtered catalog page without materializing the full catalog."""

    source_filter = _source_filter(filters.source_name)
    base_filters = [
        CatalogProductRow.catalog_source == filters.catalog_source,
        CatalogProductRow.active.is_(True),
    ]
    total = _count_products(session, base_filters)
    product_filters, filters_applied = _product_filters(filters, ignored_models, source_filter)
    filtered_clauses = [*base_filters, *product_filters]
    filtered_total = _count_products(session, filtered_clauses)

    statement = (
        select(CatalogProductRow)
        .where(*filtered_clauses)
        .order_by(*_sort_expressions(filters.sort_by, filters.sort_dir))
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    )
    rows = list(session.execute(statement).scalars().all())
    status_counts = _source_url_status_counts(session, [row.id for row in rows], source_filter)
    items = [
        _catalog_product_payload(
            row,
            is_ignored=row.model in ignored_models,
            status_counts=status_counts.get(int(row.id)),
            source_filter=source_filter,
        )
        for row in rows
    ]
    return CatalogProductListResult(
        items=items,
        page=filters.page,
        page_size=filters.page_size,
        total=total,
        filtered_total=filtered_total,
        filters_applied=filters_applied,
    )


def _count_products(session: Session, clauses: list[Any]) -> int:
    return int(session.execute(select(func.count(CatalogProductRow.id)).where(*clauses)).scalar_one())


def _product_filters(
    filters: CatalogProductListFilters,
    ignored_models: set[str],
    source_filter: str | None,
) -> tuple[list[Any], list[str]]:
    clauses: list[Any] = []
    applied: list[str] = []

    q = _trimmed_or_none(filters.q)
    if q:
        pattern = f"%{_escape_like(q.casefold())}%"
        clauses.append(
            or_(
                func.lower(CatalogProductRow.model).like(pattern, escape="\\"),
                func.lower(CatalogProductRow.mpn).like(pattern, escape="\\"),
                func.lower(CatalogProductRow.name).like(pattern, escape="\\"),
                func.lower(CatalogProductRow.manufacturer).like(pattern, escape="\\"),
            )
        )
        applied.append("q")

    for name, column, value in (
        ("category", CatalogProductRow.category, filters.category),
        ("family", CatalogProductRow.family, filters.family),
        ("category_name", CatalogProductRow.category_name, filters.category_name),
        ("sub_category", CatalogProductRow.sub_category, filters.sub_category),
        ("manufacturer", CatalogProductRow.manufacturer, filters.manufacturer),
    ):
        text = _trimmed_or_none(value)
        if text is not None:
            clauses.append(column == text)
            applied.append(name)

    if filters.marketplace:
        clauses.append(_marketplace_filter(filters.marketplace))
        applied.append("marketplace")

    if filters.has_mpn is not None:
        clauses.append(CatalogProductRow.mpn != "" if filters.has_mpn else CatalogProductRow.mpn == "")
        applied.append("has_mpn")

    if filters.has_source_url is not None:
        has_source_url_clause = _has_active_source_url_clause(source_filter)
        clauses.append(has_source_url_clause if filters.has_source_url else ~has_source_url_clause)
        applied.append("has_source_url")
        if source_filter:
            applied.append("source_name")
    elif source_filter:
        applied.append("source_name")

    if filters.has_quantity is True:
        clauses.extend(
            (
                CatalogProductRow.status == 1,
                CatalogProductRow.quantity.is_not(None),
                CatalogProductRow.quantity > 0,
            )
        )
        applied.append("has_quantity")

    if filters.ignored == "exclude":
        if ignored_models:
            clauses.append(CatalogProductRow.model.notin_(ignored_models))
        applied.append("ignored")
    elif filters.ignored == "only":
        clauses.append(CatalogProductRow.model.in_(ignored_models) if ignored_models else false())
        applied.append("ignored")

    if filters.atomic_only:
        clauses.append(CatalogProductRow.is_atomic_model.is_(True))
        applied.append("atomic_only")

    if filters.automation_eligible_only:
        clauses.append(CatalogProductRow.automation_eligible.is_(True))
        if ignored_models:
            clauses.append(CatalogProductRow.model.notin_(ignored_models))
        applied.append("automation_eligible_only")

    return clauses, applied


def _marketplace_filter(marketplace: MarketplaceFilter) -> Any:
    bestprice = CatalogProductRow.bestprice_status == 1
    skroutz = CatalogProductRow.skroutz_status == 1
    if marketplace == "bestprice":
        return bestprice
    if marketplace == "skroutz":
        return skroutz
    if marketplace == "both":
        return and_(bestprice, skroutz)
    return and_(
        or_(CatalogProductRow.bestprice_status != 1, CatalogProductRow.bestprice_status.is_(None)),
        or_(CatalogProductRow.skroutz_status != 1, CatalogProductRow.skroutz_status.is_(None)),
    )


def _has_active_source_url_clause(source_filter: str | None) -> Any:
    clauses = [
        SourceUrl.catalog_product_id == CatalogProductRow.id,
        SourceUrl.status == "active",
    ]
    if source_filter:
        clauses.append(func.lower(SourceUrl.source_name) == source_filter)
    return exists(select(SourceUrl.id).where(*clauses))


def _sort_expressions(sort_by: SortBy | None, sort_dir: SortDir) -> list[Any]:
    if sort_by is None:
        return [CatalogProductRow.id.asc()]

    column = {
        "model": CatalogProductRow.model,
        "name": CatalogProductRow.name,
        "manufacturer": CatalogProductRow.manufacturer,
        "category": CatalogProductRow.category,
        "price": CatalogProductRow.price,
        "quantity": CatalogProductRow.quantity,
    }[sort_by]
    null_rank = case((column.is_(None), 1), else_=0)
    if sort_dir == "desc":
        value_expr = (
            func.lower(column).desc()
            if sort_by in {"model", "name", "manufacturer", "category"}
            else column.desc()
        )
        return [desc(null_rank), value_expr, CatalogProductRow.id.asc()]
    value_expr = func.lower(column).asc() if sort_by in {"model", "name", "manufacturer", "category"} else column.asc()
    return [null_rank.asc(), value_expr, CatalogProductRow.id.asc()]


def _source_url_status_counts(
    session: Session,
    catalog_product_ids: list[int],
    source_filter: str | None,
) -> dict[int, dict[str, int]]:
    product_ids = sorted({int(product_id) for product_id in catalog_product_ids if product_id is not None})
    if not product_ids:
        return {}
    statement = (
        select(SourceUrl.catalog_product_id, SourceUrl.status, func.count(SourceUrl.id))
        .where(SourceUrl.catalog_product_id.in_(product_ids))
        .group_by(SourceUrl.catalog_product_id, SourceUrl.status)
    )
    if source_filter:
        statement = statement.where(func.lower(SourceUrl.source_name) == source_filter)

    counts: dict[int, dict[str, int]] = {}
    for product_id, status, count in session.execute(statement).all():
        product_counts = counts.setdefault(int(product_id), _empty_status_counts())
        status_text = str(status or "")
        if status_text in product_counts:
            product_counts[status_text] = int(count or 0)
    return counts


def _catalog_product_payload(
    row: CatalogProductRow,
    *,
    is_ignored: bool,
    status_counts: dict[str, int] | None,
    source_filter: str | None,
) -> dict[str, Any]:
    source_counts = status_counts or _empty_status_counts()
    active_count = int(source_counts.get("active") or 0)
    automation_eligible = bool(row.automation_eligible) and not is_ignored
    return {
        "catalog_product_id": row.id,
        "model": row.model or "",
        "mpn": row.mpn or "",
        "name": row.name or "",
        "category": row.category or "",
        "raw_category": row.raw_category or "",
        "family": row.family or "",
        "category_name": row.category_name or "",
        "sub_category": row.sub_category or "",
        "category_levels": _string_list(row.category_levels),
        "manufacturer": row.manufacturer or "",
        "price": _json_safe_value(row.price),
        "quantity": row.quantity,
        "status": row.status,
        "bestprice_status": row.bestprice_status,
        "skroutz_status": row.skroutz_status,
        "is_atomic_model": bool(row.is_atomic_model),
        "automation_eligible": automation_eligible,
        "warnings": _string_list(row.warnings),
        "ignored": is_ignored,
        "source_url_coverage": {
            "catalog_product_id": row.id,
            "source": source_filter or "all",
            "has_active_source_url": active_count > 0,
            "active_source_url_count": active_count,
            "needs_review_source_url_count": int(source_counts.get("needs_review") or 0),
            "broken_source_url_count": int(source_counts.get("broken") or 0),
            "disabled_source_url_count": int(source_counts.get("disabled") or 0),
            "redirected_source_url_count": int(source_counts.get("redirected") or 0),
            "status_counts": dict(source_counts),
        },
    }


def _empty_status_counts() -> dict[str, int]:
    return {status: 0 for status in SOURCE_URL_STATUSES}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _json_safe_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    return value


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


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
