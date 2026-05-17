"""Group collectors for the combined platform health endpoint."""

from __future__ import annotations

import os

import httpx
from sqlalchemy import distinct, func, select

from ecommerce.catalog_update.config import env_text
from ecommerce.catalog_update.constants import CATALOG_UPDATE_JOB_TYPE
from ecommerce.db.models.catalog import CatalogProductRow
from ecommerce.db.models.source_urls import SourceUrl
from ecommerce.db.policy import (
    collect_catalog_database_readiness,
    collect_price_monitoring_database_readiness,
)
from ecommerce.db.repositories.jobs import job_to_dict, list_jobs
from ecommerce.db.session import session_scope
from ecommerce.jobs.execution_policy import (
    API_EXECUTE_DURABLE_JOBS_INLINE_ENV_VAR,
    api_execute_durable_jobs_inline_enabled,
)
from ecommerce.platform_health.models import PlatformHealthGroup
from ecommerce.platform_health.sanitization import (
    flag_detail,
    group,
    int_or_none,
    link,
    list_strings,
    safe_text,
    unique_strings,
)
from ecommerce.source_capture.runner import CAPTURE_IMPLEMENTED_VENDOR_SLUGS
from ecommerce.source_url_agent.readiness import get_source_url_agent_readiness

OPENCART_REQUIRED_KEYS = (
    "OPENCART_STORE_BASE",
    "OPENCART_ADMIN_PATH",
    "OPENCART_ADMIN_USER",
    "OPENCART_ADMIN_PASS",
)


def collect_ecommerce_api_health() -> PlatformHealthGroup:
    inline_enabled = api_execute_durable_jobs_inline_enabled()
    return group(
        "ecommerce_api",
        "Ecommerce API",
        "ready",
        "Ecommerce API is responding.",
        details=[
            "Durable job executor: worker is canonical.",
            (
                f"API inline durable execution fallback: {'enabled' if inline_enabled else 'disabled'} "
                f"({API_EXECUTE_DURABLE_JOBS_INLINE_ENV_VAR}={'true' if inline_enabled else 'false'})."
            ),
        ],
    )


def collect_database_health(
    *,
    catalog_readiness: dict | None = None,
    price_readiness: dict | None = None,
) -> PlatformHealthGroup:
    catalog_status = catalog_readiness or collect_readiness(collect_catalog_database_readiness)
    price_status = price_readiness or collect_readiness(collect_price_monitoring_database_readiness)
    blocking_reasons = unique_strings(
        [
            *list_strings(catalog_status.get("blocking_reasons")),
            *list_strings(price_status.get("blocking_reasons")),
        ]
    )
    details = [
        flag_detail("Configured", catalog_status.get("configured")),
        flag_detail("Reachable", catalog_status.get("reachable")),
        flag_detail("Required tables present", catalog_status.get("required_tables_present")),
        flag_detail("Migration current", catalog_status.get("alembic_up_to_date")),
    ]
    active_count = catalog_status.get("active_catalog_count")
    if active_count is not None:
        details.append(f"Active catalog rows: {active_count}.")
    imported_at = safe_text(catalog_status.get("active_catalog_imported_at"))
    if imported_at:
        details.append(f"Latest active catalog import: {imported_at}.")

    if blocking_reasons:
        return group(
            "ecommerce_database",
            "Ecommerce DB",
            "blocked",
            "Ecommerce database readiness is blocked.",
            details=details,
            blocking_reasons=blocking_reasons,
            links=[link("Catalog", "/catalog"), link("Price Monitoring", "/price-monitoring")],
        )

    warnings = unique_strings(
        [
            *list_strings(catalog_status.get("warnings")),
            *list_strings(price_status.get("warnings")),
        ]
    )
    return group(
        "ecommerce_database",
        "Ecommerce DB",
        "warning" if warnings else "ready",
        "Ecommerce database is ready for catalog and price monitoring workflows.",
        details=details,
        warnings=warnings,
        links=[link("Catalog", "/catalog"), link("Price Monitoring", "/price-monitoring")],
    )


def collect_catalog_health(*, catalog_readiness: dict | None = None) -> PlatformHealthGroup:
    readiness = catalog_readiness or collect_readiness(collect_catalog_database_readiness)
    active_count = int_or_none(readiness.get("active_catalog_count"))
    details = [
        flag_detail("Catalog DB ready", readiness.get("ready_for_catalog")),
        f"Active catalog rows: {active_count if active_count is not None else 'unknown'}.",
    ]
    imported_at = safe_text(readiness.get("active_catalog_imported_at"))
    if imported_at:
        details.append(f"Latest active catalog import: {imported_at}.")
    blocking_reasons = list_strings(readiness.get("blocking_reasons"))

    if blocking_reasons:
        return group(
            "catalog",
            "Catalog",
            "blocked",
            "Catalog tables or database readiness are missing.",
            details=details,
            blocking_reasons=blocking_reasons,
            links=[link("Catalog", "/catalog")],
        )
    if active_count == 0:
        return group(
            "catalog",
            "Catalog",
            "warning",
            "Catalog tables are ready, but no active catalog rows are imported.",
            details=details,
            warnings=["Active catalog count is zero."],
            links=[link("Catalog", "/catalog"), link("Jobs", "/jobs")],
        )
    return group(
        "catalog",
        "Catalog",
        "ready",
        "Active catalog is available.",
        details=details,
        links=[link("Catalog", "/catalog")],
    )


def collect_catalog_update_health(*, catalog_readiness: dict | None = None) -> PlatformHealthGroup:
    del catalog_readiness
    missing_keys = [key for key in OPENCART_REQUIRED_KEYS if not env_text(key)]
    details = [
        "Required config keys: " + ", ".join(OPENCART_REQUIRED_KEYS) + ".",
    ]
    configured_keys = [key for key in OPENCART_REQUIRED_KEYS if key not in missing_keys]
    if configured_keys:
        details.append("Configured key names: " + ", ".join(configured_keys) + ".")
    if missing_keys:
        details.append("Missing key names: " + ", ".join(missing_keys) + ".")

    warnings: list[str] = []
    latest_job = _latest_catalog_update_job()
    if latest_job is not None:
        details.append(
            "Latest catalog update job: "
            f"{safe_text(latest_job.get('job_id')) or 'unknown'} "
            f"({safe_text(latest_job.get('status')) or 'unknown'})."
        )
        if str(latest_job.get("status") or "").lower() == "failed":
            warnings.append("Latest catalog update job failed.")

    if missing_keys:
        return group(
            "catalog_update_opencart",
            "Catalog Update / OpenCart",
            "blocked",
            "OpenCart catalog update configuration is missing required keys.",
            details=details,
            blocking_reasons=[f"Missing required configuration key: {key}." for key in missing_keys],
            warnings=warnings,
            links=[link("Jobs", "/jobs"), link("Catalog", "/catalog")],
        )

    return group(
        "catalog_update_opencart",
        "Catalog Update / OpenCart",
        "warning" if warnings else "ready",
        "OpenCart catalog update configuration is present.",
        details=details,
        warnings=warnings,
        links=[link("Jobs", "/jobs"), link("Catalog", "/catalog")],
    )


def collect_source_url_agent_health() -> PlatformHealthGroup:
    try:
        readiness = get_source_url_agent_readiness()
    except Exception:
        return group(
            "source_url_agent",
            "Source URL Agent",
            "blocked",
            "Source URL Agent provider readiness could not be determined.",
            blocking_reasons=["Source URL Agent readiness check failed."],
            links=[link("Find Source", "/find-source/runs"), link("Candidates", "/find-source/candidates")],
        )

    blocking_reasons = [safe_text(item) for item in readiness.blocking_reasons if safe_text(item)]
    warnings = [safe_text(item) for item in readiness.warnings if safe_text(item)]
    details = [
        f"Provider {provider.provider_name}: "
        f"{'enabled' if provider.enabled else 'disabled'}, "
        f"{'configured' if provider.configured else 'not configured'}."
        for provider in readiness.providers
    ]
    if readiness.default_provider_order:
        details.append("Default provider order: " + ", ".join(readiness.default_provider_order) + ".")

    return group(
        "source_url_agent",
        "Source URL Agent",
        readiness.status,
        _source_url_agent_summary(readiness.status),
        details=details,
        blocking_reasons=blocking_reasons,
        warnings=warnings,
        links=[link("Find Source", "/find-source/runs"), link("Candidates", "/find-source/candidates")],
    )


def collect_price_monitoring_health(*, price_readiness: dict | None = None) -> PlatformHealthGroup:
    readiness = price_readiness or collect_readiness(collect_price_monitoring_database_readiness)
    blocking_reasons = list_strings(readiness.get("blocking_reasons"))
    warnings: list[str] = []
    details = [
        flag_detail("Price monitoring DB ready", readiness.get("ready_for_price_monitoring")),
        (
            "Active catalog rows: "
            f"{int_or_none(readiness.get('active_catalog_count')) if readiness.get('active_catalog_count') is not None else 'unknown'}."
        ),
    ]
    if not blocking_reasons:
        coverage = _source_url_coverage_summary()
        if coverage is not None:
            details.append(f"Products with active source URLs: {coverage['products_with_active_source_urls']}.")
            if int(coverage["catalog_product_count"]) > 0 and int(coverage["products_with_active_source_urls"]) == 0:
                warnings.append("No active source URL coverage is available for Price Monitoring.")
    if blocking_reasons:
        return group(
            "price_monitoring",
            "Price Monitoring",
            "blocked",
            "Price Monitoring readiness is blocked.",
            details=details,
            blocking_reasons=blocking_reasons,
            links=[link("Price Monitoring", "/price-monitoring")],
        )
    return group(
        "price_monitoring",
        "Price Monitoring",
        "warning" if warnings else "ready",
        "Price Monitoring database readiness is available.",
        details=details,
        warnings=warnings,
        links=[link("Price Monitoring", "/price-monitoring")],
    )


def collect_vendor_sources_capture_health() -> PlatformHealthGroup:
    firecrawl_key_configured = bool(str(os.environ.get("FIRECRAWL_API_KEY") or "").strip())
    skroutz_count = _active_skroutz_source_url_count()
    details = [
        "Skroutz capture strategy: Firecrawl.",
        f"Firecrawl API key configured: {'yes' if firecrawl_key_configured else 'no'}.",
        "Direct JSON fallback: removed.",
        "Supported capture vendors: " + ", ".join(sorted(CAPTURE_IMPLEMENTED_VENDOR_SLUGS)) + ".",
    ]
    if skroutz_count is not None:
        details.append(f"Active Skroutz source URLs: {skroutz_count}.")

    if firecrawl_key_configured:
        return group(
            "vendor_sources_capture",
            "Vendor Sources Capture",
            "ready",
            "Vendor Sources capture configuration is ready.",
            details=details,
            links=[link("Source Health", "/vendor-sources/source-health"), link("Capture Runs", "/vendor-sources/captures")],
        )

    reason = "FIRECRAWL_API_KEY is missing for Skroutz Firecrawl capture."
    if skroutz_count is not None and skroutz_count > 0:
        return group(
            "vendor_sources_capture",
            "Vendor Sources Capture",
            "blocked",
            "Vendor Sources capture is blocked for active Skroutz source URLs.",
            details=details,
            blocking_reasons=[reason],
            links=[link("Source Health", "/vendor-sources/source-health"), link("Capture Runs", "/vendor-sources/captures")],
        )

    return group(
        "vendor_sources_capture",
        "Vendor Sources Capture",
        "warning",
        "Skroutz Firecrawl capture is not configured.",
        details=details,
        warnings=[reason],
        links=[link("Source Health", "/vendor-sources/source-health"), link("Capture Runs", "/vendor-sources/captures")],
    )


def collect_product_factory_health() -> PlatformHealthGroup:
    base_url, source_key = _product_factory_base_url()
    if not base_url:
        return group(
            "product_factory_api",
            "Product Factory API",
            "warning",
            "Product Factory API base URL is not configured for backend health checks.",
            details=["Checked configuration keys: PRODUCT_FACTORY_API_BASE_URL, VITE_API_PROXY_TARGET."],
            warnings=["Product Factory API health could not be checked because no base URL key is configured."],
            links=[link("Product Factory", "/product-factory")],
        )

    try:
        response = httpx.get(_product_factory_health_url(base_url), timeout=1.5)
    except Exception:
        return group(
            "product_factory_api",
            "Product Factory API",
            "warning",
            "Product Factory API health check did not complete.",
            details=[f"Configured by key: {source_key}."],
            warnings=["Product Factory API health request failed or timed out."],
            links=[link("Product Factory", "/product-factory")],
        )

    if 200 <= response.status_code < 300:
        return group(
            "product_factory_api",
            "Product Factory API",
            "ready",
            "Product Factory API health endpoint is responding.",
            details=[f"Configured by key: {source_key}."],
            links=[link("Product Factory", "/product-factory")],
        )

    return group(
        "product_factory_api",
        "Product Factory API",
        "warning",
        "Product Factory API health endpoint did not report ready.",
        details=[f"Configured by key: {source_key}.", f"Health HTTP status: {response.status_code}."],
        warnings=["Product Factory API health endpoint returned a non-success status."],
        links=[link("Product Factory", "/product-factory")],
    )


def collect_readiness(collector) -> dict:
    try:
        value = collector()
    except Exception:
        return {
            "configured": False,
            "reachable": False,
            "ready_for_catalog": False,
            "ready_for_price_monitoring": False,
            "blocking_reasons": ["readiness_check_failed"],
            "warnings": [],
        }
    return value if isinstance(value, dict) else {}


def _latest_catalog_update_job() -> dict | None:
    try:
        with session_scope() as session:
            jobs = list_jobs(session, job_type=CATALOG_UPDATE_JOB_TYPE, limit=1)
            if not jobs:
                return None
            payload = job_to_dict(jobs[0])
    except Exception:
        return None
    return {
        "job_id": payload.get("job_id"),
        "status": payload.get("status"),
        "updated_at": payload.get("updated_at"),
    }


def _source_url_coverage_summary() -> dict[str, int] | None:
    try:
        with session_scope() as session:
            active_catalog_filter = (CatalogProductRow.active.is_(True),)
            catalog_product_count = int(
                session.execute(select(func.count(CatalogProductRow.id)).where(*active_catalog_filter)).scalar_one()
            )
            active_source_product_count = int(
                session.execute(
                    select(func.count(distinct(SourceUrl.catalog_product_id)))
                    .join(CatalogProductRow, SourceUrl.catalog_product_id == CatalogProductRow.id)
                    .where(*active_catalog_filter, SourceUrl.status == "active")
                ).scalar_one()
            )
    except Exception:
        return None
    return {
        "catalog_product_count": catalog_product_count,
        "products_with_active_source_urls": active_source_product_count,
    }


def _active_skroutz_source_url_count() -> int | None:
    try:
        with session_scope() as session:
            return int(
                session.execute(
                    select(func.count(SourceUrl.id)).where(
                        SourceUrl.status == "active",
                        func.lower(SourceUrl.source_name) == "skroutz",
                    )
                ).scalar_one()
            )
    except Exception:
        return None


def _product_factory_base_url() -> tuple[str | None, str | None]:
    for key in ("PRODUCT_FACTORY_API_BASE_URL", "VITE_API_PROXY_TARGET"):
        value = os.environ.get(key)
        text = str(value or "").strip().rstrip("/")
        if text:
            return text, key
    return None, None


def _product_factory_health_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/api"):
        return f"{normalized}/health"
    return f"{normalized}/api/health"


def _source_url_agent_summary(status: str) -> str:
    if status == "ready":
        return "Source URL Agent providers are ready."
    if status == "warning":
        return "Source URL Agent providers are usable with warnings."
    return "Source URL Agent provider readiness is blocked."
