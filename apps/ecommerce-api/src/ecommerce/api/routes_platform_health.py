"""Combined read-only platform health endpoint."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import distinct, func, select

from ecommerce.api.source_url_agent.readiness import get_source_url_agent_readiness
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

router = APIRouter(prefix="/api/platform", tags=["platform-health"])

HealthStatus = Literal["ready", "warning", "blocked", "unknown"]

OPENCART_REQUIRED_KEYS = (
    "OPENCART_STORE_BASE",
    "OPENCART_ADMIN_PATH",
    "OPENCART_ADMIN_USER",
    "OPENCART_ADMIN_PASS",
)


class PlatformHealthLink(BaseModel):
    label: str
    url: str


class PlatformHealthGroup(BaseModel):
    id: str
    label: str
    status: HealthStatus
    summary: str
    details: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    links: list[PlatformHealthLink] = Field(default_factory=list)


class PlatformHealthResponse(BaseModel):
    status: HealthStatus
    groups: list[PlatformHealthGroup]
    updated_at: str


@router.get("/health", response_model=PlatformHealthResponse)
def get_platform_health() -> PlatformHealthResponse:
    try:
        catalog_readiness = _collect_readiness(collect_catalog_database_readiness)
        price_readiness = _collect_readiness(collect_price_monitoring_database_readiness)
        groups = [
            collect_ecommerce_api_health(),
            collect_database_health(catalog_readiness=catalog_readiness, price_readiness=price_readiness),
            collect_catalog_health(catalog_readiness=catalog_readiness),
            collect_catalog_update_health(catalog_readiness=catalog_readiness),
            collect_source_url_agent_health(),
            collect_price_monitoring_health(price_readiness=price_readiness),
            collect_product_factory_health(),
        ]
        status = _overall_status(groups)
    except Exception:
        groups = [
            _group(
                "platform_health",
                "Platform Health",
                "unknown",
                "Platform health aggregation could not be completed safely.",
            )
        ]
        status = "unknown"

    return PlatformHealthResponse(
        status=status,
        groups=groups,
        updated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )


def collect_ecommerce_api_health() -> PlatformHealthGroup:
    return _group(
        "ecommerce_api",
        "Ecommerce API",
        "ready",
        "Ecommerce API is responding.",
    )


def collect_database_health(
    *,
    catalog_readiness: dict | None = None,
    price_readiness: dict | None = None,
) -> PlatformHealthGroup:
    catalog_status = catalog_readiness or _collect_readiness(collect_catalog_database_readiness)
    price_status = price_readiness or _collect_readiness(collect_price_monitoring_database_readiness)
    blocking_reasons = _unique_strings(
        [
            *_list_strings(catalog_status.get("blocking_reasons")),
            *_list_strings(price_status.get("blocking_reasons")),
        ]
    )
    details = [
        _flag_detail("Configured", catalog_status.get("configured")),
        _flag_detail("Reachable", catalog_status.get("reachable")),
        _flag_detail("Required tables present", catalog_status.get("required_tables_present")),
        _flag_detail("Migration current", catalog_status.get("alembic_up_to_date")),
    ]
    active_count = catalog_status.get("active_catalog_count")
    if active_count is not None:
        details.append(f"Active catalog rows: {active_count}.")
    imported_at = _safe_text(catalog_status.get("active_catalog_imported_at"))
    if imported_at:
        details.append(f"Latest active catalog import: {imported_at}.")

    if blocking_reasons:
        return _group(
            "ecommerce_database",
            "Ecommerce DB",
            "blocked",
            "Ecommerce database readiness is blocked.",
            details=details,
            blocking_reasons=blocking_reasons,
            links=[_link("Catalog", "/catalog"), _link("Price Monitoring", "/price-monitoring")],
        )

    warnings = _unique_strings(
        [
            *_list_strings(catalog_status.get("warnings")),
            *_list_strings(price_status.get("warnings")),
        ]
    )
    return _group(
        "ecommerce_database",
        "Ecommerce DB",
        "warning" if warnings else "ready",
        "Ecommerce database is ready for catalog and price monitoring workflows.",
        details=details,
        warnings=warnings,
        links=[_link("Catalog", "/catalog"), _link("Price Monitoring", "/price-monitoring")],
    )


def collect_catalog_health(*, catalog_readiness: dict | None = None) -> PlatformHealthGroup:
    readiness = catalog_readiness or _collect_readiness(collect_catalog_database_readiness)
    active_count = _int_or_none(readiness.get("active_catalog_count"))
    details = [
        _flag_detail("Catalog DB ready", readiness.get("ready_for_catalog")),
        f"Active catalog rows: {active_count if active_count is not None else 'unknown'}.",
    ]
    imported_at = _safe_text(readiness.get("active_catalog_imported_at"))
    if imported_at:
        details.append(f"Latest active catalog import: {imported_at}.")
    blocking_reasons = _list_strings(readiness.get("blocking_reasons"))

    if blocking_reasons:
        return _group(
            "catalog",
            "Catalog",
            "blocked",
            "Catalog tables or database readiness are missing.",
            details=details,
            blocking_reasons=blocking_reasons,
            links=[_link("Catalog", "/catalog")],
        )
    if active_count == 0:
        return _group(
            "catalog",
            "Catalog",
            "warning",
            "Catalog tables are ready, but no active catalog rows are imported.",
            details=details,
            warnings=["Active catalog count is zero."],
            links=[_link("Catalog", "/catalog"), _link("Jobs", "/jobs")],
        )
    return _group(
        "catalog",
        "Catalog",
        "ready",
        "Active catalog is available.",
        details=details,
        links=[_link("Catalog", "/catalog")],
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
            f"{_safe_text(latest_job.get('job_id')) or 'unknown'} "
            f"({_safe_text(latest_job.get('status')) or 'unknown'})."
        )
        if str(latest_job.get("status") or "").lower() == "failed":
            warnings.append("Latest catalog update job failed.")

    if missing_keys:
        return _group(
            "catalog_update_opencart",
            "Catalog Update / OpenCart",
            "blocked",
            "OpenCart catalog update configuration is missing required keys.",
            details=details,
            blocking_reasons=[f"Missing required configuration key: {key}." for key in missing_keys],
            warnings=warnings,
            links=[_link("Jobs", "/jobs"), _link("Catalog", "/catalog")],
        )

    return _group(
        "catalog_update_opencart",
        "Catalog Update / OpenCart",
        "warning" if warnings else "ready",
        "OpenCart catalog update configuration is present.",
        details=details,
        warnings=warnings,
        links=[_link("Jobs", "/jobs"), _link("Catalog", "/catalog")],
    )


def collect_source_url_agent_health() -> PlatformHealthGroup:
    try:
        readiness = get_source_url_agent_readiness()
    except Exception:
        return _group(
            "source_url_agent",
            "Source URL Agent",
            "blocked",
            "Source URL Agent provider readiness could not be determined.",
            blocking_reasons=["Source URL Agent readiness check failed."],
            links=[_link("Find Source", "/find-source/runs"), _link("Candidates", "/find-source/candidates")],
        )

    blocking_reasons = [_safe_text(item) for item in readiness.blocking_reasons if _safe_text(item)]
    warnings = [_safe_text(item) for item in readiness.warnings if _safe_text(item)]
    details = [
        f"Provider {provider.provider_name}: "
        f"{'enabled' if provider.enabled else 'disabled'}, "
        f"{'configured' if provider.configured else 'not configured'}."
        for provider in readiness.providers
    ]
    if readiness.default_provider_order:
        details.append("Default provider order: " + ", ".join(readiness.default_provider_order) + ".")

    return _group(
        "source_url_agent",
        "Source URL Agent",
        readiness.status,
        _source_url_agent_summary(readiness.status),
        details=details,
        blocking_reasons=blocking_reasons,
        warnings=warnings,
        links=[_link("Find Source", "/find-source/runs"), _link("Candidates", "/find-source/candidates")],
    )


def collect_price_monitoring_health(*, price_readiness: dict | None = None) -> PlatformHealthGroup:
    readiness = price_readiness or _collect_readiness(collect_price_monitoring_database_readiness)
    blocking_reasons = _list_strings(readiness.get("blocking_reasons"))
    warnings: list[str] = []
    details = [
        _flag_detail("Price monitoring DB ready", readiness.get("ready_for_price_monitoring")),
        f"Active catalog rows: {_int_or_none(readiness.get('active_catalog_count')) if readiness.get('active_catalog_count') is not None else 'unknown'}.",
    ]
    if not blocking_reasons:
        coverage = _source_url_coverage_summary()
        if coverage is not None:
            details.append(f"Products with active source URLs: {coverage['products_with_active_source_urls']}.")
            if int(coverage["catalog_product_count"]) > 0 and int(coverage["products_with_active_source_urls"]) == 0:
                warnings.append("No active source URL coverage is available for Price Monitoring.")
    if blocking_reasons:
        return _group(
            "price_monitoring",
            "Price Monitoring",
            "blocked",
            "Price Monitoring readiness is blocked.",
            details=details,
            blocking_reasons=blocking_reasons,
            links=[_link("Price Monitoring", "/price-monitoring")],
        )
    return _group(
        "price_monitoring",
        "Price Monitoring",
        "warning" if warnings else "ready",
        "Price Monitoring database readiness is available.",
        details=details,
        warnings=warnings,
        links=[_link("Price Monitoring", "/price-monitoring")],
    )


def collect_product_factory_health() -> PlatformHealthGroup:
    base_url, source_key = _product_factory_base_url()
    if not base_url:
        return _group(
            "product_factory_api",
            "Product Factory API",
            "warning",
            "Product Factory API base URL is not configured for backend health checks.",
            details=["Checked configuration keys: PRODUCT_FACTORY_API_BASE_URL, VITE_API_PROXY_TARGET."],
            warnings=["Product Factory API health could not be checked because no base URL key is configured."],
            links=[_link("Product Factory", "/product-factory")],
        )

    try:
        response = httpx.get(_product_factory_health_url(base_url), timeout=1.5)
    except Exception:
        return _group(
            "product_factory_api",
            "Product Factory API",
            "warning",
            "Product Factory API health check did not complete.",
            details=[f"Configured by key: {source_key}."],
            warnings=["Product Factory API health request failed or timed out."],
            links=[_link("Product Factory", "/product-factory")],
        )

    if 200 <= response.status_code < 300:
        return _group(
            "product_factory_api",
            "Product Factory API",
            "ready",
            "Product Factory API health endpoint is responding.",
            details=[f"Configured by key: {source_key}."],
            links=[_link("Product Factory", "/product-factory")],
        )

    return _group(
        "product_factory_api",
        "Product Factory API",
        "warning",
        "Product Factory API health endpoint did not report ready.",
        details=[f"Configured by key: {source_key}.", f"Health HTTP status: {response.status_code}."],
        warnings=["Product Factory API health endpoint returned a non-success status."],
        links=[_link("Product Factory", "/product-factory")],
    )


def _collect_readiness(collector) -> dict:
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
                session.execute(
                    select(func.count(CatalogProductRow.id)).where(*active_catalog_filter)
                ).scalar_one()
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


def _overall_status(groups: list[PlatformHealthGroup]) -> HealthStatus:
    statuses = [group.status for group in groups]
    if "blocked" in statuses:
        return "blocked"
    if any(status in {"warning", "unknown"} for status in statuses):
        return "warning"
    return "ready"


def _source_url_agent_summary(status: str) -> str:
    if status == "ready":
        return "Source URL Agent providers are ready."
    if status == "warning":
        return "Source URL Agent providers are usable with warnings."
    return "Source URL Agent provider readiness is blocked."


def _group(
    group_id: str,
    label: str,
    status: HealthStatus,
    summary: str,
    *,
    details: list[str] | None = None,
    blocking_reasons: list[str] | None = None,
    warnings: list[str] | None = None,
    links: list[PlatformHealthLink] | None = None,
) -> PlatformHealthGroup:
    return PlatformHealthGroup(
        id=group_id,
        label=label,
        status=status,
        summary=_safe_text(summary) or "No summary available.",
        details=[item for item in (_safe_text(value) for value in (details or [])) if item],
        blocking_reasons=[item for item in (_safe_text(value) for value in (blocking_reasons or [])) if item],
        warnings=[item for item in (_safe_text(value) for value in (warnings or [])) if item],
        links=links or [],
    )


def _link(label: str, url: str) -> PlatformHealthLink:
    return PlatformHealthLink(label=label, url=url)


def _list_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_safe_text(item) for item in value if _safe_text(item)]


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _flag_detail(label: str, value: object) -> str:
    if value is True:
        state = "yes"
    elif value is False:
        state = "no"
    else:
        state = "unknown"
    return f"{label}: {state}."


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_text(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*\S+", r"\1=<redacted>", text)
    text = re.sub(r"(?i)\b[a-z][a-z0-9+.-]*://[^@\s]+@[^/\s]+", "<redacted-connection-string>", text)
    return text[:500]
