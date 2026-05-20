"""Source URL coverage metrics for Price Monitoring selections."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ecommerce.db.models.catalog import CatalogProductRow
from ecommerce.db.models.source_urls import SourceUrl
from ecommerce.db.models.vendor_sources import Vendor
from ecommerce.db.models.products import Product, ProductSource
from ecommerce.source_capture.detect_vendor import detect_vendor_slug
from ecommerce.source_urls import extract_source_domain, infer_source_name
from ecommerce.price_monitoring.selection import (
    PriceMonitoringSelectionResult,
    SelectedPriceMonitoringProduct,
    SkippedPriceMonitoringProduct,
    SourceUrlCoverageSummary,
    SourceUrlProductCoverage,
)

SOURCE_URL_STATUS_KEYS = ("active", "needs_review", "broken", "disabled", "redirected")


@dataclass(frozen=True)
class SourceUrlCoverageResult:
    product_coverage: dict[int, SourceUrlProductCoverage]
    item_coverage: list[SourceUrlProductCoverage]
    summary: SourceUrlCoverageSummary


def compute_source_url_coverage(
    session: Session,
    items: list[SelectedPriceMonitoringProduct],
    source: str | None,
) -> SourceUrlCoverageResult:
    source_filter = _source_filter(source)
    source_label = source_filter or "all"
    catalog_product_ids = sorted(
        {
            int(item.catalog_product_id)
            for item in items
            if item.catalog_product_id is not None
        }
    )
    urls_by_product_id: dict[int, list[SourceUrl]] = defaultdict(list)
    product_source_urls_by_catalog_product_id: dict[int, list[dict[str, Any]]] = (
        defaultdict(list)
    )
    if catalog_product_ids:
        statement = (
            select(SourceUrl)
            .where(SourceUrl.catalog_product_id.in_(catalog_product_ids))
            .order_by(SourceUrl.catalog_product_id.asc(), SourceUrl.id.asc())
        )
        if source_filter:
            statement = statement.where(
                func.lower(SourceUrl.source_name) == source_filter
            )
        for row in session.execute(statement).scalars().all():
            urls_by_product_id[int(row.catalog_product_id)].append(row)
        product_source_urls_by_catalog_product_id = (
            _product_sources_by_catalog_product_id(
                session,
                catalog_product_ids,
                source_filter,
            )
        )

    item_coverage: list[SourceUrlProductCoverage] = []
    coverage_by_catalog_product_id: dict[int, SourceUrlProductCoverage] = {}
    products_with_active = 0
    status_totals: Counter[str] = Counter()
    missing_models: list[str] = []
    missing_catalog_product_ids: list[int] = []

    for item in items:
        coverage = _product_coverage(
            item,
            urls_by_product_id.get(int(item.catalog_product_id or 0), []),
            source_label,
            product_source_urls_by_catalog_product_id.get(
                int(item.catalog_product_id or 0), []
            ),
        )
        item_coverage.append(coverage)
        if item.catalog_product_id is not None:
            coverage_by_catalog_product_id[int(item.catalog_product_id)] = coverage
        status_totals.update(coverage.source_url_status_counts)
        if coverage.has_active_source_url:
            products_with_active += 1
            continue
        missing_models.append(item.model)
        if item.catalog_product_id is not None:
            missing_catalog_product_ids.append(int(item.catalog_product_id))

    selected_count = len(items)
    products_without_active = selected_count - products_with_active
    coverage_percent = (
        round((products_with_active / selected_count) * 100, 2)
        if selected_count
        else 0.0
    )
    summary = SourceUrlCoverageSummary(
        source=source_label,
        source_filter=source_filter,
        selected_count=selected_count,
        products_with_active_source_urls=products_with_active,
        products_without_active_source_urls=products_without_active,
        coverage_percent=coverage_percent,
        active_source_url_count=int(status_totals["active"]),
        needs_review_source_url_count=int(status_totals["needs_review"]),
        broken_source_url_count=int(status_totals["broken"]),
        disabled_source_url_count=int(status_totals["disabled"]),
        redirected_source_url_count=int(status_totals["redirected"]),
        missing_source_url_models=missing_models,
        missing_source_url_catalog_product_ids=missing_catalog_product_ids,
        warning=_summary_warning(products_without_active, source_filter),
    )
    return SourceUrlCoverageResult(
        product_coverage=coverage_by_catalog_product_id,
        item_coverage=item_coverage,
        summary=summary,
    )


def attach_source_url_coverage(
    selection_result: PriceMonitoringSelectionResult,
    coverage_result: SourceUrlCoverageResult,
) -> PriceMonitoringSelectionResult:
    items = [
        replace(item, source_url_coverage=coverage)
        for item, coverage in zip(
            selection_result.items, coverage_result.item_coverage, strict=True
        )
    ]
    return replace(
        selection_result, items=items, source_url_coverage=coverage_result.summary
    )


def require_active_source_url_coverage(
    selection_result: PriceMonitoringSelectionResult,
    coverage_result: SourceUrlCoverageResult,
) -> PriceMonitoringSelectionResult:
    items: list[SelectedPriceMonitoringProduct] = []
    skipped = list(selection_result.skipped)
    for item, coverage in zip(
        selection_result.items, coverage_result.item_coverage, strict=True
    ):
        item_with_coverage = replace(item, source_url_coverage=coverage)
        if coverage.has_active_source_url:
            items.append(item_with_coverage)
            continue
        skipped.append(
            SkippedPriceMonitoringProduct(
                model=item.model,
                reasons=["missing_active_source_url"],
            )
        )
    return replace(
        selection_result,
        items=items,
        skipped=skipped,
        source_url_coverage=coverage_result.summary,
    )


def _product_coverage(
    item: SelectedPriceMonitoringProduct,
    source_urls: list[SourceUrl],
    source: str,
    product_source_urls: list[dict[str, Any]] | None = None,
) -> SourceUrlProductCoverage:
    status_counts = {status: 0 for status in SOURCE_URL_STATUS_KEYS}
    active_urls: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for row in source_urls:
        status = str(row.status or "")
        if status in status_counts:
            status_counts[status] += 1
        if status == "active":
            payload = _source_url_payload(row)
            seen_urls.add(str(payload["url"]))
            active_urls.append(payload)
    for payload in product_source_urls or []:
        if str(payload["url"]) in seen_urls:
            continue
        seen_urls.add(str(payload["url"]))
        active_urls.append(payload)
        status_counts["active"] += 1

    active_count = status_counts["active"]
    warning = None
    if item.catalog_product_id is None:
        warning = f"Catalog product id is unavailable; {_source_text(source)} source URL coverage cannot be checked."
    elif active_count == 0:
        warning = (
            f"Selected product does not have active {_source_text(source)} source URLs. "
            "Product is not eligible for Price Monitoring until an active source URL exists in Vendor Sources."
        )
    return SourceUrlProductCoverage(
        catalog_product_id=item.catalog_product_id,
        active_source_url_count=active_count,
        active_source_urls=active_urls,
        has_active_source_url=active_count > 0,
        source_url_status_counts=status_counts,
        source_url_warning=warning,
    )


def _source_url_payload(row: SourceUrl) -> dict[str, Any]:
    return {
        "id": row.id,
        "catalog_product_id": row.catalog_product_id,
        "source_name": row.source_name,
        "source_domain": row.source_domain,
        "url": row.url,
        "url_normalized": row.url_normalized,
        "status": row.status,
        "url_type": row.url_type,
        "trust_level": row.trust_level,
    }


def _product_sources_by_catalog_product_id(
    session: Session,
    catalog_product_ids: list[int],
    source_filter: str | None,
) -> dict[int, list[dict[str, Any]]]:
    catalog_rows = (
        session.execute(
            select(CatalogProductRow).where(
                CatalogProductRow.id.in_(catalog_product_ids)
            )
        )
        .scalars()
        .all()
    )
    product_ids_by_catalog_id: dict[int, set[int]] = defaultdict(set)
    for catalog_row in catalog_rows:
        product_statement = select(Product.id).where(
            Product.catalog_source == catalog_row.catalog_source
        )
        if catalog_row.model:
            product_statement = product_statement.where(
                Product.model == catalog_row.model
            )
        elif catalog_row.mpn:
            product_statement = product_statement.where(Product.mpn == catalog_row.mpn)
        else:
            continue
        for product_id in session.execute(product_statement).scalars().all():
            product_ids_by_catalog_id[int(catalog_row.id)].add(int(product_id))

    product_ids = sorted(
        {product_id for ids in product_ids_by_catalog_id.values() for product_id in ids}
    )
    if not product_ids:
        return {}

    sources_by_product_id: dict[int, list[ProductSource]] = defaultdict(list)
    rows = (
        session.execute(
            select(ProductSource)
            .where(
                ProductSource.product_id.in_(product_ids),
                ProductSource.active.is_(True),
            )
            .order_by(ProductSource.product_id.asc(), ProductSource.id.asc())
        )
        .scalars()
        .all()
    )
    for row in rows:
        if source_filter and _product_source_name(session, row) != source_filter:
            continue
        sources_by_product_id[int(row.product_id)].append(row)

    result: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for catalog_product_id, ids in product_ids_by_catalog_id.items():
        for product_id in ids:
            result[catalog_product_id].extend(
                _product_source_payload(row, catalog_product_id)
                for row in sources_by_product_id[product_id]
            )
    return result


def _product_source_payload(
    row: ProductSource, catalog_product_id: int
) -> dict[str, Any]:
    url = row.canonical_url or row.source_url
    source_domain = extract_source_domain(url)
    return {
        "id": None,
        "product_source_id": row.id,
        "catalog_product_id": catalog_product_id,
        "source_name": detect_vendor_slug(url) or infer_source_name(source_domain),
        "source_domain": source_domain,
        "url": url,
        "url_normalized": url,
        "status": "active",
        "url_type": "imported",
        "trust_level": "product_source",
    }


def _product_source_name(session: Session, row: ProductSource) -> str:
    if row.vendor_id is not None:
        vendor = session.get(Vendor, row.vendor_id)
        if vendor is not None:
            return vendor.slug
    url = row.canonical_url or row.source_url
    return detect_vendor_slug(url) or infer_source_name(extract_source_domain(url))


def _summary_warning(
    products_without_active: int, source_filter: str | None
) -> str | None:
    if products_without_active <= 0:
        return None
    suffix = "product" if products_without_active == 1 else "products"
    return (
        f"{products_without_active} selected {suffix} do not have active {_source_text(source_filter)} source URLs. "
        "Products without active source URLs are not eligible for Price Monitoring; add URLs in Vendor Sources."
    )


def _source_filter(source: str | None) -> str | None:
    text = str(source or "").strip().lower()
    if not text or text == "all":
        return None
    return text


def _source_text(source: str | None) -> str:
    return source if source else "Vendor Sources"
