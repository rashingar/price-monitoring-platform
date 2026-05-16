"""SQL-backed catalog product listing queries."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import and_, case, desc, exists, false, func, or_, select
from sqlalchemy.orm import Session

from ecommerce.catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.models.catalog import CatalogProductRow
from ecommerce.db.models.products import Product, ProductSource, SourceCaptureSnapshot
from ecommerce.db.models.source_urls import SourceUrl
from ecommerce.db.repositories.common import json_safe_value
from ecommerce.source_capture.canonicalize_url import canonical_url_hash, canonicalize_url

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


@dataclass(frozen=True)
class CatalogProductDetailResult:
    product: dict[str, Any]
    source_urls: list[dict[str, Any]]
    source_url_summary: dict[str, Any]
    warnings: list[str]


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


def get_catalog_product_detail(
    session: Session,
    catalog_product_id: int,
    *,
    ignored_models: set[str],
    catalog_source: str = DEFAULT_CATALOG_SOURCE,
) -> CatalogProductDetailResult | None:
    row = session.execute(
        select(CatalogProductRow).where(
            CatalogProductRow.id == catalog_product_id,
            CatalogProductRow.catalog_source == catalog_source,
            CatalogProductRow.active.is_(True),
        )
    ).scalar_one_or_none()
    if row is None:
        return None

    source_urls = list(
        session.execute(
            select(SourceUrl)
            .where(SourceUrl.catalog_product_id == row.id)
            .order_by(SourceUrl.updated_at.desc(), SourceUrl.id.desc())
        )
        .scalars()
        .all()
    )
    source_filter = None
    status_counts = _source_url_status_counts(session, [int(row.id)], source_filter).get(
        int(row.id),
        _empty_status_counts(),
    )
    product_payload = _catalog_product_payload(
        row,
        is_ignored=row.model in ignored_models,
        status_counts=status_counts,
        source_filter=source_filter,
    )
    product_sources = _product_sources_for_catalog_product(session, row)
    latest_snapshots = _latest_snapshots_by_product_source(session, product_sources)
    product_source_by_hash = {source.canonical_url_hash: source for source in product_sources}
    source_url_payloads = [
        _source_url_lifecycle_payload(
            source_url,
            product_source_by_hash=product_source_by_hash,
            latest_snapshots=latest_snapshots,
        )
        for source_url in source_urls
    ]
    return CatalogProductDetailResult(
        product=product_payload,
        source_urls=source_url_payloads,
        source_url_summary=_source_url_summary(source_url_payloads),
        warnings=_string_list(row.warnings),
    )


def get_catalog_categories(session: Session, *, catalog_source: str = DEFAULT_CATALOG_SOURCE) -> dict[str, Any]:
    rows = _active_catalog_rows(session, catalog_source=catalog_source)
    counts = Counter(str(row.category or "") for row in rows if row.category)
    first_row_by_category: dict[str, CatalogProductRow] = {}
    for row in rows:
        category = str(row.category or "")
        if category and category not in first_row_by_category:
            first_row_by_category[category] = row
    return {
        "items": [
            _category_to_response(first_row_by_category[category], category, counts[category])
            for category in sorted(counts)
        ],
        **_empty_catalog_warning_from_total(len(rows)),
    }


def get_catalog_category_hierarchy(session: Session, *, catalog_source: str = DEFAULT_CATALOG_SOURCE) -> dict[str, Any]:
    rows = _active_catalog_rows(session, catalog_source=catalog_source)
    hierarchy: dict[str, dict[str, dict[str, dict[str, object]]]] = {}

    for row in rows:
        family = _row_text(row.family)
        if not family:
            continue
        category_name = _row_text(row.category_name)
        sub_category = _row_text(row.sub_category)
        family_node = hierarchy.setdefault(family, {})
        category_node = family_node.setdefault(category_name, {})
        sub_node = category_node.setdefault(sub_category, {"count": 0, "raw_categories": set()})
        sub_node["count"] = int(sub_node["count"]) + 1
        raw_category = _row_text(row.raw_category)
        if raw_category:
            raw_categories = sub_node["raw_categories"]
            if isinstance(raw_categories, set):
                raw_categories.add(raw_category)

    items: list[dict[str, Any]] = []
    for family in sorted(hierarchy):
        category_items: list[dict[str, Any]] = []
        family_count = 0
        for category_name in sorted(hierarchy[family]):
            sub_category_items: list[dict[str, Any]] = []
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

    return {"items": items, **_empty_catalog_warning_from_total(len(rows))}


def get_catalog_brands(session: Session, *, catalog_source: str = DEFAULT_CATALOG_SOURCE) -> dict[str, Any]:
    rows = _active_catalog_rows(session, catalog_source=catalog_source)
    counts = Counter(str(row.manufacturer or "") for row in rows if row.manufacturer)
    return {
        "items": [
            {"manufacturer": manufacturer, "count": counts[manufacturer]}
            for manufacturer in sorted(counts)
        ],
        **_empty_catalog_warning_from_total(len(rows)),
    }


def get_catalog_summary(session: Session, *, catalog_source: str = DEFAULT_CATALOG_SOURCE) -> dict[str, Any]:
    rows = _active_catalog_rows(session, catalog_source=catalog_source)
    categories = {_row_text(row.category) for row in rows if row.category}
    families = {_row_text(row.family) for row in rows if row.family}
    category_names = {_row_text(row.category_name) for row in rows if row.category_name}
    sub_categories = {_row_text(row.sub_category) for row in rows if row.sub_category}
    manufacturers = {_row_text(row.manufacturer) for row in rows if row.manufacturer}
    return {
        "total_products": len(rows),
        "active_products": sum(1 for row in rows if row.status == 1),
        "atomic_products": sum(1 for row in rows if bool(row.is_atomic_model)),
        "composite_or_invalid_models": sum(1 for row in rows if not bool(row.is_atomic_model)),
        "bestprice_products": sum(1 for row in rows if row.bestprice_status == 1),
        "skroutz_products": sum(1 for row in rows if row.skroutz_status == 1),
        "missing_mpn": sum(1 for row in rows if not row.mpn),
        "category_count": len(categories),
        "family_count": len(families),
        "category_name_count": len(category_names),
        "sub_category_count": len(sub_categories),
        "manufacturer_count": len(manufacturers),
        **_empty_catalog_warning_from_total(len(rows)),
    }


def _count_products(session: Session, clauses: list[Any]) -> int:
    return int(session.execute(select(func.count(CatalogProductRow.id)).where(*clauses)).scalar_one())


def _active_catalog_rows(session: Session, *, catalog_source: str) -> list[CatalogProductRow]:
    return list(
        session.execute(
            select(CatalogProductRow)
            .where(
                CatalogProductRow.catalog_source == catalog_source,
                CatalogProductRow.active.is_(True),
            )
            .order_by(CatalogProductRow.id.asc())
        )
        .scalars()
        .all()
    )


def _category_to_response(row: CatalogProductRow, category: str, count: int) -> dict[str, Any]:
    return {
        "category": category,
        "raw_category": _row_text(row.raw_category),
        "family": _row_text(row.family),
        "category_name": _row_text(row.category_name),
        "sub_category": _row_text(row.sub_category),
        "category_levels": _string_list(row.category_levels),
        "count": count,
    }


def _empty_catalog_warning_from_total(total: int) -> dict[str, str]:
    if total:
        return {}
    return {"warning": "Active catalog is empty. Run python -m ecommerce.jobs.ingest_catalog."}


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


def _product_sources_for_catalog_product(session: Session, row: CatalogProductRow) -> list[ProductSource]:
    product = None
    if row.model:
        product = session.execute(
            select(Product).where(
                Product.catalog_source == row.catalog_source,
                Product.model == row.model,
            )
        ).scalar_one_or_none()
    if product is None and row.mpn:
        product = session.execute(
            select(Product)
            .where(
                Product.catalog_source == row.catalog_source,
                Product.mpn == row.mpn,
            )
            .limit(1)
        ).scalar_one_or_none()
    if product is None:
        return []

    return list(
        session.execute(
            select(ProductSource)
            .where(ProductSource.product_id == product.id)
            .order_by(ProductSource.updated_at.desc(), ProductSource.id.desc())
        )
        .scalars()
        .all()
    )


def _latest_snapshots_by_product_source(
    session: Session,
    product_sources: list[ProductSource],
) -> dict[int, SourceCaptureSnapshot]:
    source_ids = [int(source.id) for source in product_sources if source.id is not None]
    if not source_ids:
        return {}
    rows = list(
        session.execute(
            select(SourceCaptureSnapshot)
            .where(SourceCaptureSnapshot.product_source_id.in_(source_ids))
            .order_by(
                SourceCaptureSnapshot.product_source_id.asc(),
                SourceCaptureSnapshot.captured_at.desc().nullslast(),
                SourceCaptureSnapshot.fetched_at.desc().nullslast(),
                SourceCaptureSnapshot.created_at.desc(),
                SourceCaptureSnapshot.id.desc(),
            )
        )
        .scalars()
        .all()
    )
    latest: dict[int, SourceCaptureSnapshot] = {}
    for snapshot in rows:
        source_id = snapshot.product_source_id
        if source_id is not None and int(source_id) not in latest:
            latest[int(source_id)] = snapshot
    return latest


def _source_url_lifecycle_payload(
    row: SourceUrl,
    *,
    product_source_by_hash: dict[str, ProductSource],
    latest_snapshots: dict[int, SourceCaptureSnapshot],
) -> dict[str, Any]:
    product_source = _matching_product_source(row, product_source_by_hash)
    snapshot = latest_snapshots.get(int(product_source.id)) if product_source is not None else None
    source_capture_snapshot_id = snapshot.id if snapshot is not None else None
    artifact_ref = _artifact_ref(snapshot)
    last_fetch_status = product_source.last_fetch_status if product_source is not None else None
    payload: dict[str, Any] = {
        "id": row.id,
        "source_url_id": row.id,
        "catalog_product_id": row.catalog_product_id,
        "product_source_id": product_source.id if product_source is not None else None,
        "catalog_source": row.catalog_source,
        "model": row.model,
        "mpn": row.mpn,
        "manufacturer": row.manufacturer,
        "source_name": row.source_name,
        "source_domain": row.source_domain,
        "url": row.url,
        "url_normalized": row.url_normalized,
        "status": row.status,
        "url_type": row.url_type,
        "trust_level": row.trust_level,
        "added_by": row.added_by,
        "notes": row.notes,
        "last_seen_at": json_safe_value(row.last_seen_at),
        "last_success_at": json_safe_value(row.last_success_at),
        "last_failed_at": json_safe_value(row.last_failed_at),
        "failure_count": row.failure_count,
        "last_error": _safe_operator_error(row.last_error),
        "capture_status": last_fetch_status,
        "last_fetch_status": last_fetch_status,
        "last_capture_status": last_fetch_status,
        "last_capture_strategy": product_source.last_capture_strategy if product_source is not None else None,
        "last_capture_at": json_safe_value(snapshot.captured_at if snapshot is not None else None),
        "last_fetched_at": json_safe_value(snapshot.fetched_at if snapshot is not None else None),
        "source_capture_snapshot_id": source_capture_snapshot_id,
        "last_capture_snapshot_id": source_capture_snapshot_id,
        "artifact_ref": artifact_ref,
        "snapshot_ref": artifact_ref,
        "full_snapshot_ref": artifact_ref,
        "artifact_refs": [artifact_ref] if artifact_ref is not None else [],
        "created_at": json_safe_value(row.created_at),
        "updated_at": json_safe_value(row.updated_at),
    }
    return payload


def _matching_product_source(
    row: SourceUrl,
    product_source_by_hash: dict[str, ProductSource],
) -> ProductSource | None:
    try:
        canonical = canonicalize_url(row.url_normalized or row.url)
        digest = canonical_url_hash(canonical)
    except Exception:
        return None
    return product_source_by_hash.get(digest)


def _artifact_ref(snapshot: SourceCaptureSnapshot | None) -> dict[str, Any] | None:
    if snapshot is None or not snapshot.artifact_ref:
        return None
    path = snapshot.artifact_ref
    return {
        "name": str(path).rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
        "path": path,
        "is_allowed": True,
        "can_read": True,
        "can_download": True,
    }


def _source_url_summary(source_urls: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for row in source_urls:
        _increment(by_status, row.get("status"))
        _increment(by_source, row.get("source_name"))
        _increment(by_type, row.get("url_type"))
    return {
        "total_count": len(source_urls),
        "by_status": by_status,
        "by_source": by_source,
        "by_type": by_type,
    }


def _increment(counter: dict[str, int], key: object) -> None:
    text = str(key or "").strip()
    if not text:
        return
    counter[text] = counter.get(text, 0) + 1


def _empty_status_counts() -> dict[str, int]:
    return {status: 0 for status in SOURCE_URL_STATUSES}


def _row_text(value: object) -> str:
    return str(value or "")


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _json_safe_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _safe_operator_error(value: object) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    redacted = text
    for marker in ("token=", "api_key=", "apikey=", "password=", "secret="):
        lowered = redacted.casefold()
        index = lowered.find(marker)
        while index >= 0:
            end = redacted.find(" ", index)
            if end < 0:
                end = len(redacted)
            redacted = f"{redacted[:index]}{marker}<redacted>{redacted[end:]}"
            lowered = redacted.casefold()
            index = lowered.find(marker, index + len(marker) + len("<redacted>"))
    if len(redacted) <= 500:
        return redacted
    return f"{redacted[:497]}..."


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
