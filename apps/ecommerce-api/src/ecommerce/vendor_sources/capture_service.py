"""DB-backed source URL capture owned by Vendor Sources."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ecommerce.db.config import is_database_configured
from ecommerce.db.models.catalog import CatalogProductRow
from ecommerce.db.models.source_urls import SourceUrl
from ecommerce.db.models.vendor_sources import Vendor
from ecommerce.db.models.products import Product, ProductSource
from ecommerce.price_monitoring.source_url_coverage import compute_source_url_coverage
from ecommerce.source_capture.canonicalize_url import canonical_url_hash, canonicalize_url
from ecommerce.source_capture.detect_vendor import detect_vendor_slug
from ecommerce.source_capture.firecrawl_health import firecrawl_health_reason
from ecommerce.source_capture.runner import CAPTURE_IMPLEMENTED_VENDOR_SLUGS, capture_source_url
from ecommerce.source_urls import infer_source_name
from ecommerce.vendor_sources.payloads import (
    SOURCE_URL_CAPTURE_RESULT_FILENAME,
    VENDOR_SOURCE_CAPTURE_RESULT_FILENAME,
    VENDOR_SOURCE_CAPTURE_RUNS_DIR,
    SourceUrlCaptureRunResult,
)
from ecommerce.db.repositories.vendor_sources import (
    create_vendor_source_capture_run_row,
    get_vendor_source_capture_run,
    list_vendor_source_capture_runs,
    make_vendor_capture_run_id,
    mark_vendor_source_capture_run_failed,
    update_vendor_source_capture_run,
    vendor_source_capture_run_to_dict,
)


def capture_selected_source_urls_for_run(
    run_dir: Path,
    source: str,
    *,
    strict_source_url_capture: bool = False,
    capture_fn=None,
    write_result: bool = True,
) -> SourceUrlCaptureRunResult:
    """Capture active DB source URLs for a monitoring run.

    strict_source_url_capture is an internal option only. It reports products
    without eligible source URLs as strict exclusions, but the public fetch API
    does not expose it yet.
    """

    run_dir = Path(run_dir)
    result_path = run_dir / SOURCE_URL_CAPTURE_RESULT_FILENAME
    normalized_source = _optional_text(source).lower()
    if not is_database_configured():
        result = _empty_result(
            source=normalized_source,
            status="not_configured",
            result_path=result_path,
            warnings=["Source URL capture skipped because ECOMMERCE_DATABASE_URL is not configured."],
        )
        if write_result:
            _write_result(result_path, result)
        return result

    selected_catalog_product_ids = _selected_catalog_product_ids(run_dir / "selection_summary.json")
    if not selected_catalog_product_ids:
        result = _empty_result(
            source=normalized_source,
            status="no_selected_catalog_products",
            result_path=result_path,
            selected_catalog_product_count=0,
            warnings=["Source URL capture skipped because the run has no selected catalog product ids."],
        )
        if write_result:
            _write_result(result_path, result)
        return result

    from ecommerce.db.session import session_scope

    with session_scope() as session:
        vendor_run_id = make_vendor_capture_run_id()
        observation_batch_id = vendor_run_id
        row = create_vendor_source_capture_run_row(
            session,
            run_id=vendor_run_id,
            observation_batch_id=observation_batch_id,
            status="running",
            source_filter=normalized_source,
            catalog_source=None,
            filters={
                "price_monitoring_run_id": run_dir.name,
                "source_filter": normalized_source,
                "catalog_product_ids": selected_catalog_product_ids,
            },
            result_path=result_path,
        )
        try:
            result = capture_selected_source_urls(
                session,
                run_id=run_dir.name,
                source=normalized_source,
                catalog_product_ids=selected_catalog_product_ids,
                strict_source_url_capture=strict_source_url_capture,
                capture_fn=capture_fn,
                result_path=result_path,
                observation_batch_id=observation_batch_id,
            )
            result = _with_vendor_run_metadata(
                result,
                run_id=vendor_run_id,
                observation_batch_id=observation_batch_id,
                source_filter=normalized_source,
                catalog_source=None,
                result_path=result_path,
            )
            update_vendor_source_capture_run(row, result)
        except Exception as exc:
            mark_vendor_source_capture_run_failed(row, error=exc, result_path=result_path)
            session.flush()
            raise
    if write_result:
        _write_result(result_path, result)
    return result


def capture_selected_source_urls(
    session: Session,
    *,
    run_id: str,
    source: str,
    catalog_product_ids: list[int],
    strict_source_url_capture: bool = False,
    capture_fn=None,
    result_path: Path | None = None,
    observation_batch_id: str | None = None,
) -> SourceUrlCaptureRunResult:
    from ecommerce.db.repositories.source_convergence import sync_source_url_to_product_source
    from ecommerce.db.repositories.source_urls import (
        list_active_source_urls_for_catalog_products,
        source_url_to_dict,
    )
    from ecommerce.source_capture.scheduled import capture_due_product_sources

    selected_ids = sorted({int(item) for item in catalog_product_ids if item is not None})
    active_source_urls = [
        row
        for row in list_active_source_urls_for_catalog_products(session, selected_ids)
        if _source_url_matches_source(row, source)
    ]
    eligible_source_urls: list[SourceUrl] = []
    product_source_ids: list[int] = []
    for source_url in active_source_urls:
        existing_product_source = _existing_product_source_for_source_url(session, source_url)
        if existing_product_source is not None and not existing_product_source.active:
            continue
        product_source = sync_source_url_to_product_source(session, source_url)
        if product_source is not None and product_source.active and product_source.id is not None:
            eligible_source_urls.append(source_url)
            product_source_ids.append(int(product_source.id))
    session.flush()
    source_url_payloads = [source_url_to_dict(row) for row in eligible_source_urls]

    warnings: list[str] = []
    if not product_source_ids:
        source_text = source or "Vendor Sources"
        warnings.append(
            f"No active {source_text} source URLs exist for the selected products. "
            "Product is not eligible for Price Monitoring until an active source URL exists."
        )
        if strict_source_url_capture:
            warnings.append("Strict source URL capture would exclude all selected products from DB-backed capture.")
        return SourceUrlCaptureRunResult(
            status="no_active_source_urls",
            used_source_urls=False,
            source=source,
            vendor=source or None,
            selected_catalog_product_count=len(selected_ids),
            selected_source_url_count=0,
            selected_product_source_count=0,
            succeeded_count=0,
            failed_count=0,
            warnings=warnings,
            items=[],
            source_urls=[],
            result_path=result_path,
            observation_batch_id=observation_batch_id or "",
        )

    if strict_source_url_capture:
        missing_count = _missing_source_url_product_count(session, selected_ids, source)
        if missing_count:
            source_text = source or "Vendor Sources"
            warnings.append(f"Strict source URL capture excluded {missing_count} selected products without active {source_text} source URLs.")

    summary = capture_due_product_sources(
        session,
        limit=len(product_source_ids),
        product_source_ids=product_source_ids,
        include_not_due=True,
        run_id=run_id,
        observation_batch_id=observation_batch_id,
        monitoring_run_id=None,
        capture_fn=capture_fn or capture_source_url,
    )
    return _capture_result_from_summary(
        source=source,
        vendor=source or None,
        selected_catalog_product_count=len(selected_ids),
        selected_source_url_count=len(eligible_source_urls),
        selected_product_source_count=len(product_source_ids),
        summary=summary,
        warnings=warnings,
        source_urls=source_url_payloads,
        result_path=result_path,
    )


def capture_due_vendor_sources(
    session: Session,
    *,
    refresh_after_minutes: int = 360,
    limit: int = 50,
    vendor: str | None = None,
    source_name: str | None = None,
    catalog_source: str | None = None,
    catalog_product_ids: list[int] | None = None,
    product_source_ids: list[int] | None = None,
    include_not_due: bool = False,
    capture_fn=None,
    run_id: str | None = None,
    observation_batch_id: str | None = None,
) -> SourceUrlCaptureRunResult:
    """Run capture for due active Vendor Sources without persisting run history."""

    from ecommerce.source_capture.scheduled import capture_due_product_sources

    safe_limit = max(1, min(int(limit), 500))
    safe_refresh_after_minutes = max(0, int(refresh_after_minutes))
    source_filter = _source_filter(source_name=source_name, vendor_slug=vendor)
    eligible_product_source_ids, eligible_source_urls, selected_catalog_product_count = _eligible_product_sources_from_active_source_urls(
        session,
        source_filter=source_filter,
        catalog_source=_optional_text(catalog_source) or None,
        catalog_product_ids=catalog_product_ids or [],
        product_source_ids=product_source_ids or [],
        limit=max(safe_limit, len(product_source_ids or []), 1),
    )
    summary = capture_due_product_sources(
        session,
        refresh_after_minutes=safe_refresh_after_minutes,
        limit=safe_limit,
        vendor_slug=source_filter,
        product_source_ids=eligible_product_source_ids,
        include_not_due=bool(include_not_due),
        run_id=run_id,
        observation_batch_id=observation_batch_id,
        capture_fn=capture_fn or capture_source_url,
    )
    selected_ids = [
        int(item["product_source_id"])
        for item in summary.items
        if isinstance(item, dict) and _int_or_none(item.get("product_source_id")) is not None
    ]
    selected_catalog_product_count, selected_source_urls = _selected_product_source_context(session, selected_ids)
    if not selected_ids:
        selected_source_urls = eligible_source_urls[:0]
        selected_catalog_product_count = 0
    return _capture_result_from_summary(
        source=source_filter or "",
        vendor=source_filter,
        selected_catalog_product_count=selected_catalog_product_count,
        selected_source_url_count=len(selected_source_urls),
        selected_product_source_count=summary.selected_count,
        summary=summary,
        warnings=[],
        source_urls=selected_source_urls,
        result_path=None,
    )


def run_vendor_source_capture(
    session: Session,
    *,
    source_name: str | None = None,
    vendor_slug: str | None = None,
    catalog_source: str | None = None,
    catalog_product_ids: list[int] | None = None,
    product_source_ids: list[int] | None = None,
    refresh_after_minutes: int = 360,
    limit: int = 50,
    include_not_due: bool = False,
    dry_run: bool = False,
    admin_all_sources: bool = False,
    capture_fn=None,
    runs_dir: Path = VENDOR_SOURCE_CAPTURE_RUNS_DIR,
) -> SourceUrlCaptureRunResult:
    """Create a durable Vendor Sources capture run and write its result artifact."""

    run_id = make_vendor_capture_run_id()
    run_dir = Path(runs_dir) / run_id
    result_path = run_dir / VENDOR_SOURCE_CAPTURE_RESULT_FILENAME
    safe_limit = max(1, min(int(limit), 500))
    safe_refresh_after_minutes = max(0, int(refresh_after_minutes))
    source_filter = _source_filter(source_name=source_name, vendor_slug=vendor_slug)
    if source_filter is None and not admin_all_sources:
        raise ValueError("Vendor Sources capture requires one source/vendor unless admin_all_sources=true for diagnostic all-source capture.")
    normalized_catalog_source = _optional_text(catalog_source) or None
    observation_batch_id = run_id
    filters = {
        "source_name": source_name,
        "vendor_slug": vendor_slug,
        "source_filter": source_filter,
        "catalog_source": normalized_catalog_source,
        "catalog_product_ids": [int(item) for item in catalog_product_ids or []],
        "product_source_ids": [int(item) for item in product_source_ids or []],
        "limit": safe_limit,
        "refresh_after_minutes": safe_refresh_after_minutes,
        "include_not_due": bool(include_not_due),
        "dry_run": bool(dry_run),
        "admin_all_sources": bool(admin_all_sources),
        "observation_batch_id": observation_batch_id,
    }
    row = create_vendor_source_capture_run_row(
        session,
        run_id=run_id,
        observation_batch_id=observation_batch_id,
        status="running",
        source_filter=source_filter,
        catalog_source=normalized_catalog_source,
        filters=filters,
        result_path=result_path,
    )

    try:
        eligible_product_source_ids, eligible_source_urls, eligible_catalog_product_count = _eligible_product_sources_from_active_source_urls(
            session,
            source_filter=source_filter,
            catalog_source=normalized_catalog_source,
            catalog_product_ids=catalog_product_ids or [],
            product_source_ids=product_source_ids or [],
            limit=safe_limit,
        )
        if dry_run:
            result = SourceUrlCaptureRunResult(
                status="dry_run",
                used_source_urls=bool(eligible_product_source_ids),
                source=source_filter or "",
                vendor=source_filter,
                run_id=run_id,
                observation_batch_id=observation_batch_id,
                source_filter=source_filter,
                catalog_source=normalized_catalog_source,
                selected_catalog_product_count=eligible_catalog_product_count,
                selected_source_url_count=len(eligible_source_urls),
                selected_product_source_count=len(eligible_product_source_ids),
                succeeded_count=0,
                failed_count=0,
                skipped_count=len(eligible_product_source_ids),
                warnings=[],
                items=[],
                source_urls=eligible_source_urls,
                result_path=result_path,
                artifact_refs=[str(result_path)],
            )
        else:
            result = capture_due_vendor_sources(
                session,
                refresh_after_minutes=safe_refresh_after_minutes,
                limit=safe_limit,
                vendor=source_filter,
                catalog_source=normalized_catalog_source,
                catalog_product_ids=catalog_product_ids or [],
                product_source_ids=eligible_product_source_ids,
                include_not_due=include_not_due,
                run_id=run_id,
                observation_batch_id=observation_batch_id,
                capture_fn=capture_fn,
            )
            result = _with_vendor_run_metadata(
                result,
                run_id=run_id,
                observation_batch_id=observation_batch_id,
                source_filter=source_filter,
                catalog_source=normalized_catalog_source,
                result_path=result_path,
            )

        _write_result(result_path, result)
        update_vendor_source_capture_run(row, result)
    except Exception as exc:
        mark_vendor_source_capture_run_failed(row, error=exc, result_path=result_path)
        session.flush()
        raise
    session.flush()
    return result


def recapture_product_source(
    session: Session,
    *,
    product_source_id: int,
    capture_fn=None,
    runs_dir: Path = VENDOR_SOURCE_CAPTURE_RUNS_DIR,
) -> dict[str, Any]:
    from ecommerce.source_capture.scheduled import capture_due_product_sources

    product_source = session.get(ProductSource, int(product_source_id))
    if product_source is None:
        raise LookupError("Product source not found.")
    if not product_source.active:
        raise LookupError("Product source is inactive.")

    vendor_slug = _product_source_vendor_slug(session, product_source)
    if not vendor_slug or vendor_slug not in CAPTURE_IMPLEMENTED_VENDOR_SLUGS:
        raise ValueError("Product source vendor is not supported for capture.")

    run_id = make_vendor_capture_run_id()
    run_dir = Path(runs_dir) / run_id
    result_path = run_dir / VENDOR_SOURCE_CAPTURE_RESULT_FILENAME
    observation_batch_id = run_id
    row = create_vendor_source_capture_run_row(
        session,
        run_id=run_id,
        observation_batch_id=observation_batch_id,
        status="running",
        source_filter=vendor_slug,
        catalog_source=None,
        filters={
            "product_source_ids": [int(product_source_id)],
            "include_not_due": True,
            "manual_recapture": True,
        },
        result_path=result_path,
    )
    try:
        summary = capture_due_product_sources(
            session,
            refresh_after_minutes=0,
            limit=1,
            vendor_slug=vendor_slug,
            product_source_ids=[int(product_source_id)],
            include_not_due=True,
            run_id=run_id,
            observation_batch_id=observation_batch_id,
            capture_fn=capture_fn or capture_source_url,
        )
        result = _capture_result_from_summary(
            source=vendor_slug,
            vendor=vendor_slug,
            selected_catalog_product_count=1 if summary.selected_count else 0,
            selected_source_url_count=summary.selected_count,
            selected_product_source_count=summary.selected_count,
            summary=summary,
            warnings=[],
            source_urls=[],
            result_path=result_path,
        )
        result = _with_vendor_run_metadata(
            result,
            run_id=run_id,
            observation_batch_id=observation_batch_id,
            source_filter=vendor_slug,
            catalog_source=None,
            result_path=result_path,
        )
        _write_result(result_path, result)
        update_vendor_source_capture_run(row, result)
    except Exception as exc:
        mark_vendor_source_capture_run_failed(row, error=exc, result_path=result_path)
        session.flush()
        raise

    if summary.selected_count != 1:
        raise LookupError("Product source not found or inactive.")

    item = summary.items[0] if summary.items else {}
    session.flush()
    session.refresh(product_source)
    return {
        "product_source_id": int(product_source_id),
        "vendor": vendor_slug,
        "status": item.get("status") or product_source.last_fetch_status or "unknown",
        "snapshot_id": item.get("snapshot_id"),
        "error_code": item.get("error_code") or product_source.last_error_code,
        "health_reason": item.get("health_reason")
        or firecrawl_health_reason(
            vendor_slug=vendor_slug,
            capture_strategy=product_source.last_capture_strategy,
            error_code=product_source.last_error_code,
            data_quality_flags=product_source.data_quality_flags or [],
            error_message=product_source.last_error_message,
        ),
        "capture_run_id": run_id,
        "observation_batch_id": observation_batch_id,
    }

def _capture_result_from_summary(
    *,
    source: str,
    vendor: str | None,
    selected_catalog_product_count: int,
    selected_source_url_count: int,
    selected_product_source_count: int,
    summary: Any,
    warnings: list[str],
    source_urls: list[dict[str, Any]],
    result_path: Path | None,
) -> SourceUrlCaptureRunResult:
    status = "completed"
    if summary.failed_count and not summary.succeeded_count:
        status = "completed_with_failures"
    elif summary.failed_count:
        status = "completed_with_partial_failures"
    return SourceUrlCaptureRunResult(
        status=status,
        used_source_urls=summary.selected_count > 0,
        source=source,
        vendor=vendor,
        selected_catalog_product_count=selected_catalog_product_count,
        selected_source_url_count=selected_source_url_count,
        selected_product_source_count=selected_product_source_count,
        succeeded_count=summary.succeeded_count,
        failed_count=summary.failed_count,
        warnings=warnings,
        items=summary.items,
        source_urls=source_urls,
        result_path=result_path,
    )


def _source_url_matches_source(row: SourceUrl, source: str) -> bool:
    if not source:
        return True
    if str(row.source_name or "").strip().lower() == source:
        return True
    url = row.url_normalized or row.url
    if (detect_vendor_slug(url) or "").lower() == source:
        return True
    return infer_source_name(row.source_domain or "").lower() == source


def _eligible_product_sources_from_active_source_urls(
    session: Session,
    *,
    source_filter: str | None,
    catalog_source: str | None,
    catalog_product_ids: list[int],
    product_source_ids: list[int],
    limit: int,
) -> tuple[list[int], list[dict[str, Any]], int]:
    from ecommerce.db.repositories.source_convergence import sync_product_source_to_source_url, sync_source_url_to_product_source
    from ecommerce.db.repositories.source_urls import source_url_to_dict

    source_urls: list[SourceUrl] = []
    statement = (
        select(SourceUrl)
        .join(CatalogProductRow, CatalogProductRow.id == SourceUrl.catalog_product_id)
        .where(SourceUrl.status == "active", CatalogProductRow.active.is_(True))
        .order_by(SourceUrl.catalog_product_id.asc(), SourceUrl.id.asc())
    )
    if source_filter:
        statement = statement.where(func.lower(SourceUrl.source_name) == source_filter)
    if catalog_source:
        statement = statement.where(SourceUrl.catalog_source == catalog_source)
    if catalog_product_ids:
        statement = statement.where(SourceUrl.catalog_product_id.in_([int(item) for item in catalog_product_ids]))
    source_urls.extend(session.execute(statement.limit(max(1, int(limit)))).scalars().all())

    product_source_rows: list[ProductSource] = []
    if product_source_ids:
        product_source_statement = select(ProductSource).where(
            ProductSource.id.in_([int(item) for item in product_source_ids]),
            ProductSource.active.is_(True),
        )
        if source_filter:
            product_source_statement = product_source_statement.outerjoin(Vendor, Vendor.id == ProductSource.vendor_id).where(Vendor.slug == source_filter)
        product_source_rows = list(session.execute(product_source_statement).scalars().all())

    seen_product_source_ids: set[int] = set()
    eligible_source_urls_by_key: dict[tuple[int | None, str], dict[str, Any]] = {}
    catalog_product_ids_selected: set[int] = set()
    for source_url in source_urls:
        existing_product_source = _existing_product_source_for_source_url(session, source_url)
        if existing_product_source is not None and not existing_product_source.active:
            continue
        product_source = sync_source_url_to_product_source(session, source_url)
        if product_source is None or not product_source.active or product_source.id is None:
            continue
        seen_product_source_ids.add(int(product_source.id))
        catalog_product_ids_selected.add(int(source_url.catalog_product_id))
        payload = source_url_to_dict(source_url)
        eligible_source_urls_by_key[(source_url.catalog_product_id, source_url.url_normalized or source_url.url)] = payload

    for product_source in product_source_rows:
        source_url = sync_product_source_to_source_url(session, product_source)
        if source_url is None or source_url.status != "active":
            continue
        if catalog_source and source_url.catalog_source != catalog_source:
            continue
        if catalog_product_ids and int(source_url.catalog_product_id) not in {int(item) for item in catalog_product_ids}:
            continue
        if source_filter and not _source_url_matches_source(source_url, source_filter):
            continue
        seen_product_source_ids.add(int(product_source.id))
        catalog_product_ids_selected.add(int(source_url.catalog_product_id))
        eligible_source_urls_by_key[(source_url.catalog_product_id, source_url.url_normalized or source_url.url)] = source_url_to_dict(source_url)

    session.flush()
    selected_ids = sorted(seen_product_source_ids)
    source_url_payloads = list(eligible_source_urls_by_key.values())
    return selected_ids[: max(1, int(limit))], source_url_payloads[: max(1, int(limit))], len(catalog_product_ids_selected)


def _existing_product_source_for_source_url(session: Session, source_url: SourceUrl) -> ProductSource | None:
    canonical = canonicalize_url(source_url.url_normalized or source_url.url)
    digest = canonical_url_hash(canonical)
    statement = (
        select(ProductSource)
        .join(Product, Product.id == ProductSource.product_id)
        .where(
            Product.catalog_source == source_url.catalog_source,
            Product.model == source_url.model,
            ProductSource.canonical_url_hash == digest,
        )
    )
    return session.execute(statement).scalar_one_or_none()


def _selected_product_source_context(session: Session, product_source_ids: list[int]) -> tuple[int, list[dict[str, Any]]]:
    if not product_source_ids:
        return 0, []
    from ecommerce.db.repositories.source_convergence import sync_product_source_to_source_url
    from ecommerce.db.repositories.source_urls import source_url_to_dict

    sources = list(
        session.execute(select(ProductSource).where(ProductSource.id.in_(product_source_ids))).scalars().all()
    )
    source_url_payloads: list[dict[str, Any]] = []
    catalog_product_ids: set[int] = set()
    for source in sources:
        source_url = sync_product_source_to_source_url(session, source)
        if source_url is None or source_url.status != "active":
            continue
        source_url_payloads.append(source_url_to_dict(source_url))
        catalog_product_ids.add(int(source_url.catalog_product_id))
    session.flush()
    return len(catalog_product_ids), source_url_payloads


def _product_source_vendor_slug(session: Session, source: ProductSource) -> str | None:
    if source.vendor_id is None:
        return detect_vendor_slug(source.canonical_url or source.source_url)
    vendor = session.get(Vendor, source.vendor_id)
    return vendor.slug if vendor is not None else detect_vendor_slug(source.canonical_url or source.source_url)


def _missing_source_url_product_count(session: Session, catalog_product_ids: list[int], source: str) -> int:
    coverage = compute_source_url_coverage(
        session,
        [_coverage_item(catalog_product_id) for catalog_product_id in catalog_product_ids],
        source,  # type: ignore[arg-type]
    )
    return coverage.summary.products_without_active_source_urls


def _coverage_item(catalog_product_id: int):
    from ecommerce.price_monitoring.selection import SelectedPriceMonitoringProduct

    return SelectedPriceMonitoringProduct(
        model="",
        mpn="",
        name="",
        manufacturer="",
        category="",
        raw_category="",
        family="",
        category_name="",
        sub_category="",
        category_levels=[],
        price=0.0,
        source="skroutz",
        catalog_product_id=catalog_product_id,
    )


def _selected_catalog_product_ids(summary_path: Path) -> list[int]:
    payload = _read_json_object(summary_path)
    ids: list[int] = []
    for key in ("selected_items", "items"):
        value = payload.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            catalog_product_id = _int_or_none(item.get("catalog_product_id"))
            if catalog_product_id is not None:
                ids.append(catalog_product_id)
        if ids:
            break
    return ids


def _empty_result(
    *,
    source: str,
    status: str,
    result_path: Path | None,
    warnings: list[str],
    selected_catalog_product_count: int = 0,
) -> SourceUrlCaptureRunResult:
    return SourceUrlCaptureRunResult(
        status=status,
        used_source_urls=False,
        source=source,
        vendor=source or None,
        selected_catalog_product_count=selected_catalog_product_count,
        selected_source_url_count=0,
        selected_product_source_count=0,
        succeeded_count=0,
        failed_count=0,
        warnings=warnings,
        items=[],
        source_urls=[],
        result_path=result_path,
    )


def _write_result(path: Path, result: SourceUrlCaptureRunResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _with_vendor_run_metadata(
    result: SourceUrlCaptureRunResult,
    *,
    run_id: str,
    observation_batch_id: str,
    source_filter: str | None,
    catalog_source: str | None,
    result_path: Path,
) -> SourceUrlCaptureRunResult:
    return replace(
        result,
        run_id=run_id,
        observation_batch_id=observation_batch_id,
        source_filter=source_filter,
        catalog_source=catalog_source,
        result_path=result_path,
        artifact_refs=[str(result_path)],
    )


def _source_filter(*, source_name: str | None = None, vendor_slug: str | None = None) -> str | None:
    text = _optional_text(source_name) or _optional_text(vendor_slug)
    if not text:
        return None
    normalized = text.lower()
    return None if normalized == "all" else normalized


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _optional_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


