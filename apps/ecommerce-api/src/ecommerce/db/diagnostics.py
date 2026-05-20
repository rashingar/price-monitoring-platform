"""Read-only PostgreSQL setup and persistence diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

from ecommerce.db.config import (
    get_database_url,
    sanitize_database_error,
    sanitize_database_url,
)
from ecommerce.db.session import get_engine

PRICE_MONITORING_DB_REQUIRED_FUTURE = True

REQUIRED_PRICE_MONITORING_TABLES = (
    "catalog_products",
    "source_urls",
    "products",
    "monitoring_runs",
    "catalog_snapshots",
    "price_observations",
    "alert_rules",
    "alert_events",
    "vendors",
    "product_sources",
    "source_capture_snapshots",
    "offer_observations",
    "price_observation_listings",
    "source_url_discovery_runs",
    "source_url_candidates",
    "ecommerce_jobs",
)


def get_alembic_head_revision() -> str | None:
    try:
        script = ScriptDirectory.from_config(_alembic_config())
        heads = script.get_heads()
    except Exception:
        return None
    if len(heads) != 1:
        return None
    return heads[0]


def collect_database_status(database_url: str | None = None) -> dict[str, Any]:
    raw_url = database_url or get_database_url()
    head_revision = get_alembic_head_revision()
    if raw_url is None:
        return _base_status(
            configured=False,
            reachable=False,
            sanitized_database_url=None,
            alembic_head_revision=head_revision,
            price_monitoring_database_mode="not_configured",
        )

    sanitized_url = sanitize_database_url(raw_url)
    try:
        engine = get_engine(raw_url)
        with engine.connect() as connection:
            connection.execute(text("select 1"))
            try:
                return _reachable_status(
                    connection, engine, raw_url, sanitized_url, head_revision
                )
            except Exception as exc:
                return _base_status(
                    configured=True,
                    reachable=True,
                    dialect=engine.dialect.name,
                    sanitized_database_url=sanitized_url,
                    alembic_head_revision=head_revision,
                    price_monitoring_database_mode="error",
                    error=sanitize_database_error(_first_line(exc), raw_url)
                    or exc.__class__.__name__,
                )
    except Exception as exc:
        return _base_status(
            configured=True,
            reachable=False,
            sanitized_database_url=sanitized_url,
            alembic_head_revision=head_revision,
            price_monitoring_database_mode="unreachable",
            error=sanitize_database_error(_first_line(exc), raw_url)
            or exc.__class__.__name__,
        )


def collect_run_persistence_status(
    run_id: str, database_url: str | None = None
) -> dict[str, Any]:
    raw_url = database_url or get_database_url()
    if raw_url is None:
        return {
            "configured": False,
            "reachable": False,
            "monitoring_run_exists": False,
            "observation_count": 0,
            "matched_observation_count": 0,
            "unmatched_observation_count": 0,
            "alert_event_count": 0,
            "persistence_status": "not_configured",
        }

    try:
        engine = get_engine(raw_url)
        with engine.connect() as connection:
            connection.execute(text("select 1"))
            inspector = inspect(connection)
            table_names = set(inspector.get_table_names())
            needed = {"monitoring_runs", "price_observations"}
            if not needed.issubset(table_names):
                return {
                    "configured": True,
                    "reachable": True,
                    "monitoring_run_exists": False,
                    "observation_count": 0,
                    "matched_observation_count": 0,
                    "unmatched_observation_count": 0,
                    "alert_event_count": 0,
                    "persistence_status": "unknown",
                    "warning": "Required persistence tables are missing.",
                }
            return _run_persistence_counts(connection, run_id, table_names)
    except Exception as exc:
        return {
            "configured": True,
            "reachable": False,
            "persistence_status": "error",
            "error": sanitize_database_error(_first_line(exc), raw_url)
            or exc.__class__.__name__,
        }


def _reachable_status(
    connection: Connection,
    engine: Engine,
    raw_url: str,
    sanitized_url: str | None,
    head_revision: str | None,
) -> dict[str, Any]:
    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())
    required_tables = {
        table_name: table_name in existing_tables
        for table_name in REQUIRED_PRICE_MONITORING_TABLES
    }
    required_tables_present = all(required_tables.values())
    current_revision = _current_alembic_revision(connection, raw_url)
    alembic_up_to_date = (
        current_revision == head_revision
        if current_revision and head_revision
        else None
    )
    row_counts = (
        _row_counts(connection, required_tables) if required_tables_present else None
    )
    active_catalog_count = _active_catalog_count(connection, existing_tables)
    active_catalog_imported_at = _active_catalog_imported_at(
        connection, existing_tables
    )

    mode = "incomplete"
    if required_tables_present and alembic_up_to_date and row_counts is not None:
        has_price_monitoring_data = any(int(count) > 0 for count in row_counts.values())
        mode = "ready" if has_price_monitoring_data else "configured_empty"

    return _base_status(
        configured=True,
        reachable=True,
        dialect=engine.dialect.name,
        sanitized_database_url=sanitized_url,
        alembic_current_revision=current_revision,
        alembic_head_revision=head_revision,
        alembic_up_to_date=alembic_up_to_date,
        required_tables=required_tables,
        required_tables_present=required_tables_present,
        row_counts=row_counts,
        active_catalog_count=active_catalog_count,
        active_catalog_imported_at=active_catalog_imported_at,
        price_monitoring_database_mode=mode,
    )


def _base_status(
    *,
    configured: bool,
    reachable: bool,
    dialect: str | None = None,
    sanitized_database_url: str | None = None,
    alembic_current_revision: str | None = None,
    alembic_head_revision: str | None = None,
    alembic_up_to_date: bool | None = None,
    required_tables: dict[str, bool] | None = None,
    required_tables_present: bool = False,
    row_counts: dict[str, int] | None = None,
    active_catalog_count: int | None = None,
    active_catalog_imported_at: str | None = None,
    price_monitoring_database_mode: str,
    error: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    normalized_required_tables = required_tables or {
        table_name: False for table_name in REQUIRED_PRICE_MONITORING_TABLES
    }
    missing_tables = [
        table_name
        for table_name in REQUIRED_PRICE_MONITORING_TABLES
        if not normalized_required_tables.get(table_name)
    ]
    setup_hints = _setup_hints(
        configured=configured,
        reachable=reachable,
        required_tables_present=required_tables_present,
        alembic_up_to_date=alembic_up_to_date,
        error=error,
    )
    db_ready = (
        configured
        and reachable
        and required_tables_present
        and alembic_up_to_date is not False
    )
    catalog_ready = db_ready
    price_monitoring_ready = db_ready and int(active_catalog_count or 0) > 0
    return {
        "configured": configured,
        "reachable": reachable,
        "dialect": dialect,
        "sanitized_database_url": sanitized_database_url,
        "alembic_current_revision": alembic_current_revision,
        "alembic_head_revision": alembic_head_revision,
        "alembic_up_to_date": alembic_up_to_date,
        "required_tables": normalized_required_tables,
        "required_tables_present": required_tables_present,
        "missing_tables": missing_tables,
        "row_counts": row_counts,
        "catalog_requires_database": True,
        "ready_for_catalog": catalog_ready,
        "active_catalog_count": active_catalog_count,
        "active_catalog_imported_at": active_catalog_imported_at,
        "price_monitoring_database_mode": price_monitoring_database_mode,
        "price_monitoring_database_required_future": PRICE_MONITORING_DB_REQUIRED_FUTURE,
        "price_monitoring_requires_database": True,
        "ready_for_price_monitoring": price_monitoring_ready,
        "blocking_reasons": _blocking_reasons(
            configured=configured,
            reachable=reachable,
            required_tables_present=required_tables_present,
            alembic_up_to_date=alembic_up_to_date,
        ),
        "non_db_workflows_available": True,
        "required_for": [
            "catalog",
            "price_monitoring",
            "alerts",
            "observations",
            "history",
        ],
        "error": error,
        "setup_hints": setup_hints,
        "warnings": warnings or [],
    }


def _current_alembic_revision(connection: Connection, raw_url: str) -> str | None:
    try:
        return MigrationContext.configure(connection).get_current_revision()
    except Exception as exc:
        message = sanitize_database_error(_first_line(exc), raw_url)
        if message:
            return None
        return None


def _row_counts(
    connection: Connection, required_tables: dict[str, bool]
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in REQUIRED_PRICE_MONITORING_TABLES:
        if required_tables.get(table_name):
            counts[table_name] = int(
                connection.execute(
                    text(f"select count(*) from {table_name}")
                ).scalar_one()
            )
    return counts


def _active_catalog_count(connection: Connection, table_names: set[str]) -> int | None:
    if "catalog_products" not in table_names:
        return None
    return int(
        connection.execute(
            text("select count(*) from catalog_products where active = true")
        ).scalar_one()
    )


def _active_catalog_imported_at(
    connection: Connection, table_names: set[str]
) -> str | None:
    if "catalog_products" not in table_names:
        return None
    value = connection.execute(
        text("select max(imported_at) from catalog_products where active = true")
    ).scalar_one()
    return str(value) if value is not None else None


def _run_persistence_counts(
    connection: Connection, run_id: str, table_names: set[str]
) -> dict[str, Any]:
    monitoring_run_id = connection.execute(
        text("select id from monitoring_runs where run_id = :run_id limit 1"),
        {"run_id": run_id},
    ).scalar_one_or_none()
    observation_count = int(
        connection.execute(
            text("select count(*) from price_observations where run_id = :run_id"),
            {"run_id": run_id},
        ).scalar_one()
    )
    matched_count = int(
        connection.execute(
            text(
                "select count(*) from price_observations where run_id = :run_id and match_status = 'matched'"
            ),
            {"run_id": run_id},
        ).scalar_one()
    )
    unmatched_count = int(
        connection.execute(
            text(
                "select count(*) from price_observations where run_id = :run_id and match_status = 'unmatched'"
            ),
            {"run_id": run_id},
        ).scalar_one()
    )
    alert_event_count = 0
    if "alert_events" in table_names:
        alert_event_count = int(
            connection.execute(
                text("select count(*) from alert_events where run_id = :run_id"),
                {"run_id": run_id},
            ).scalar_one()
        )
    monitoring_run_exists = monitoring_run_id is not None
    persistence_status = (
        "persisted" if monitoring_run_exists and observation_count > 0 else "missing"
    )
    return {
        "configured": True,
        "reachable": True,
        "monitoring_run_exists": monitoring_run_exists,
        "observation_count": observation_count,
        "matched_observation_count": matched_count,
        "unmatched_observation_count": unmatched_count,
        "alert_event_count": alert_event_count,
        "persistence_status": persistence_status,
    }


def _alembic_config() -> Config:
    project_root = Path(__file__).resolve().parents[3]
    return Config(str(project_root / "alembic.ini"))


def _first_line(exc: Exception) -> str:
    text_value = str(exc).strip()
    return text_value.splitlines()[0] if text_value else exc.__class__.__name__


def _setup_hints(
    *,
    configured: bool,
    reachable: bool,
    required_tables_present: bool,
    alembic_up_to_date: bool | None,
    error: str | None,
) -> list[str]:
    hints: list[str] = []
    if not configured:
        hints.extend(
            [
                "Set ECOMMERCE_DATABASE_URL.",
                "Run alembic upgrade head from the ecommerce-api backend repo.",
                "Restart ecommerce-api.",
            ]
        )
        return hints
    if not reachable:
        hints.append(
            "Check that PostgreSQL is running and that ECOMMERCE_DATABASE_URL credentials are correct."
        )
        if error:
            hints.append(
                "Review the sanitized connection error shown in this response."
            )
        return hints
    if not required_tables_present:
        hints.append("Run alembic upgrade head from the ecommerce-api backend repo.")
    if alembic_up_to_date is False:
        hints.append("Run alembic upgrade head from the ecommerce-api backend repo.")
    if alembic_up_to_date is None:
        hints.append(
            "Migration revision could not be confirmed; run alembic current and alembic heads if needed."
        )
    return list(dict.fromkeys(hints))


def _blocking_reasons(
    *,
    configured: bool,
    reachable: bool,
    required_tables_present: bool,
    alembic_up_to_date: bool | None,
) -> list[str]:
    reasons: list[str] = []
    if not configured:
        reasons.append("database_not_configured")
    elif not reachable:
        reasons.append("database_unreachable")
    if not required_tables_present:
        reasons.append("required_tables_missing")
    if alembic_up_to_date is False:
        reasons.append("alembic_not_up_to_date")
    return reasons
