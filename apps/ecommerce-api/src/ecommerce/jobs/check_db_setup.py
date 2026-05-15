"""Read-only PostgreSQL setup verification for Ecommerce."""

from __future__ import annotations

import sys
from typing import Sequence

from ecommerce.db.config import DATABASE_URL_ENV_VAR
from ecommerce.db.diagnostics import REQUIRED_PRICE_MONITORING_TABLES, collect_database_status
from ecommerce.env import describe_local_env_warnings, load_local_env_if_present


def main(argv: Sequence[str] | None = None) -> int:
    _ = argv
    env_status = load_local_env_if_present()
    status = collect_database_status()
    print(f"{DATABASE_URL_ENV_VAR} configured: {status['configured']}")
    print(f"{DATABASE_URL_ENV_VAR} source: {_database_url_source(env_status, bool(status['configured']))}")
    for warning in describe_local_env_warnings(env_status):
        print(f"Local env warning: {warning}")
    print(f"Sanitized database URL: {status['sanitized_database_url'] or '(not configured)'}")
    print(f"Reachable: {status['reachable']}")
    print(f"Dialect: {status['dialect'] or '(unknown)'}")
    print(f"Alembic current revision: {status['alembic_current_revision'] or '(none)'}")
    print(f"Alembic head revision: {status['alembic_head_revision'] or '(unknown)'}")
    print(f"Alembic up to date: {status['alembic_up_to_date']}")
    print(f"Required tables present: {status['required_tables_present']}")

    required_tables = status["required_tables"]
    for table_name in REQUIRED_PRICE_MONITORING_TABLES:
        print(f"  {table_name}: {required_tables.get(table_name, False)}")

    row_counts = status["row_counts"]
    if row_counts is not None:
        print("Row counts:")
        for table_name in REQUIRED_PRICE_MONITORING_TABLES:
            print(f"  {table_name}: {row_counts.get(table_name, 0)}")
        print("Zero row counts are valid before the first Price Monitoring run.")

    print(f"Price Monitoring database mode: {status['price_monitoring_database_mode']}")
    if status["error"]:
        print(f"Error: {status['error']}")

    if (
        status["configured"]
        and status["reachable"]
        and status["required_tables_present"]
        and status["alembic_up_to_date"]
    ):
        return 0
    return 1


def _database_url_source(env_status: dict[str, object], configured: bool) -> str:
    if DATABASE_URL_ENV_VAR in env_status.get("keys_loaded_from_root", []):
        return "repo-root .env"
    if DATABASE_URL_ENV_VAR in env_status.get("keys_loaded_from_deprecated_app", []):
        return "deprecated app-local .env"
    if configured:
        return "environment"
    return "not_configured"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
