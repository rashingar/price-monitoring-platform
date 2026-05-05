"""Database readiness policy for Price Monitoring workflows."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ecommerce.db.diagnostics import collect_database_status

PRICE_MONITORING_DATABASE_REQUIRED_MESSAGE = "PostgreSQL is required for Price Monitoring."
PRICE_MONITORING_DATABASE_REQUIRED_CODE = "price_monitoring_database_required"
CATALOG_DATABASE_REQUIRED_MESSAGE = "PostgreSQL is required for Catalog."
CATALOG_DATABASE_REQUIRED_CODE = "catalog_database_required"
PRICE_MONITORING_DATABASE_REQUIRED_FOR = ["catalog", "price_monitoring", "alerts", "observations", "history"]


def is_database_required_for_price_monitoring() -> bool:
    return True


def collect_price_monitoring_database_readiness(database_url: str | None = None) -> dict[str, Any]:
    status = dict(collect_database_status(database_url))
    blocking_reasons = _blocking_reasons(status, require_active_catalog=True)
    status.update(
        {
            "catalog_requires_database": True,
            "ready_for_catalog": not _blocking_reasons(status, require_active_catalog=False),
            "price_monitoring_requires_database": True,
            "ready_for_price_monitoring": not blocking_reasons,
            "blocking_reasons": blocking_reasons,
            "non_db_workflows_available": True,
            "required_for": list(PRICE_MONITORING_DATABASE_REQUIRED_FOR),
        }
    )
    return status


def collect_catalog_database_readiness(database_url: str | None = None) -> dict[str, Any]:
    status = dict(collect_database_status(database_url))
    blocking_reasons = _blocking_reasons(status, require_active_catalog=False)
    status.update(
        {
            "catalog_requires_database": True,
            "ready_for_catalog": not blocking_reasons,
            "price_monitoring_requires_database": True,
            "ready_for_price_monitoring": not _blocking_reasons(status, require_active_catalog=True),
            "blocking_reasons": blocking_reasons,
            "non_db_workflows_available": True,
            "required_for": list(PRICE_MONITORING_DATABASE_REQUIRED_FOR),
        }
    )
    return status


def require_database_ready_for_price_monitoring() -> None:
    readiness = collect_price_monitoring_database_readiness()
    if not bool(readiness.get("ready_for_price_monitoring", False)):
        raise HTTPException(status_code=503, detail=price_monitoring_database_unavailable_detail(readiness))


def require_database_ready_for_catalog() -> None:
    readiness = collect_catalog_database_readiness()
    if not bool(readiness.get("ready_for_catalog", False)):
        raise HTTPException(status_code=503, detail=catalog_database_unavailable_detail(readiness))


def catalog_database_unavailable_detail(readiness: dict[str, Any] | None = None) -> dict[str, Any]:
    status = readiness or collect_catalog_database_readiness()
    return {
        "message": CATALOG_DATABASE_REQUIRED_MESSAGE,
        "code": CATALOG_DATABASE_REQUIRED_CODE,
        "configured": bool(status.get("configured", False)),
        "reachable": bool(status.get("reachable", False)),
        "required_tables_present": bool(status.get("required_tables_present", False)),
        "alembic_up_to_date": bool(status.get("alembic_up_to_date", False)),
        "ready_for_catalog": bool(status.get("ready_for_catalog", False)),
        "active_catalog_count": status.get("active_catalog_count"),
        "active_catalog_imported_at": status.get("active_catalog_imported_at"),
        "blocking_reasons": [str(item) for item in _list_value(status.get("blocking_reasons"))],
        "setup_hints": [str(item) for item in _list_value(status.get("setup_hints"))],
    }


def price_monitoring_database_unavailable_detail(readiness: dict[str, Any] | None = None) -> dict[str, Any]:
    status = readiness or collect_price_monitoring_database_readiness()
    return {
        "message": PRICE_MONITORING_DATABASE_REQUIRED_MESSAGE,
        "code": PRICE_MONITORING_DATABASE_REQUIRED_CODE,
        "configured": bool(status.get("configured", False)),
        "reachable": bool(status.get("reachable", False)),
        "required_tables_present": bool(status.get("required_tables_present", False)),
        "alembic_up_to_date": bool(status.get("alembic_up_to_date", False)),
        "ready_for_price_monitoring": bool(status.get("ready_for_price_monitoring", False)),
        "active_catalog_count": status.get("active_catalog_count"),
        "active_catalog_imported_at": status.get("active_catalog_imported_at"),
        "blocking_reasons": [str(item) for item in _list_value(status.get("blocking_reasons"))],
        "setup_hints": [str(item) for item in _list_value(status.get("setup_hints"))],
    }


def _blocking_reasons(status: dict[str, Any], *, require_active_catalog: bool) -> list[str]:
    reasons: list[str] = []
    if not bool(status.get("configured", False)):
        reasons.append("database_not_configured")
    elif not bool(status.get("reachable", False)):
        reasons.append("database_unreachable")

    if not bool(status.get("required_tables_present", False)):
        reasons.append("required_tables_missing")

    # Treat an explicit False as blocking. A None value means diagnostics could
    # not determine the revision, so setup hints can guide the operator without
    # making lightweight tests require a live Alembic-managed PostgreSQL server.
    if status.get("alembic_up_to_date") is False:
        reasons.append("alembic_not_up_to_date")
    if require_active_catalog and not reasons and int(status.get("active_catalog_count") or 0) <= 0:
        reasons.append("active_catalog_empty")
    return reasons


def _list_value(value: object) -> list:
    return value if isinstance(value, list) else []
