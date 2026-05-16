"""Aggregation service for the combined platform health endpoint."""

from __future__ import annotations

from datetime import datetime, timezone

import ecommerce.platform_health.collectors as collectors
from ecommerce.platform_health.models import HealthStatus, PlatformHealthGroup, PlatformHealthResponse
from ecommerce.platform_health.sanitization import group


def get_platform_health_response() -> PlatformHealthResponse:
    return collect_platform_health()


def collect_platform_health() -> PlatformHealthResponse:
    try:
        catalog_readiness = collectors.collect_readiness(collectors.collect_catalog_database_readiness)
        price_readiness = collectors.collect_readiness(collectors.collect_price_monitoring_database_readiness)
        groups = [
            collectors.collect_ecommerce_api_health(),
            collectors.collect_database_health(catalog_readiness=catalog_readiness, price_readiness=price_readiness),
            collectors.collect_catalog_health(catalog_readiness=catalog_readiness),
            collectors.collect_catalog_update_health(catalog_readiness=catalog_readiness),
            collectors.collect_source_url_agent_health(),
            collectors.collect_price_monitoring_health(price_readiness=price_readiness),
            collectors.collect_vendor_sources_capture_health(),
            collectors.collect_product_factory_health(),
        ]
        status = overall_status(groups)
    except Exception:
        groups = [
            group(
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


def overall_status(groups: list[PlatformHealthGroup]) -> HealthStatus:
    statuses = [item.status for item in groups]
    if "blocked" in statuses:
        return "blocked"
    if any(status in {"warning", "unknown"} for status in statuses):
        return "warning"
    return "ready"
