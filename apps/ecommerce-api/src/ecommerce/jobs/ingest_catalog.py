"""Import sourceCata.csv into the active PostgreSQL catalog."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from sqlalchemy.exc import SQLAlchemyError

from ecommerce.catalog import DEFAULT_CATALOG_SOURCE, MissingCatalogColumnsError
from ecommerce.catalog_db import ingest_source_catalog
from ecommerce.db.config import sanitize_database_error
from ecommerce.db.policy import collect_catalog_database_readiness
from ecommerce.db.session import session_scope


def ingest_catalog_file(
    *,
    source_cata_path: Path | None = None,
    catalog_source: str = DEFAULT_CATALOG_SOURCE,
):
    readiness = collect_catalog_database_readiness()
    if not readiness.get("ready_for_catalog", False):
        reasons = ", ".join(str(reason) for reason in readiness.get("blocking_reasons", []))
        raise RuntimeError(f"PostgreSQL is required for Catalog and is not ready: {reasons or 'unknown'}")
    with session_scope() as session:
        return ingest_source_catalog(
            session,
            source_cata_path=source_cata_path,
            catalog_source=catalog_source,
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import sourceCata.csv into the active database catalog.")
    parser.add_argument("--source-cata-path", type=Path, default=None, help="Optional sourceCata.csv path.")
    parser.add_argument("--catalog-source", default=DEFAULT_CATALOG_SOURCE, help="Catalog source name.")
    args = parser.parse_args(argv)

    readiness = collect_catalog_database_readiness()
    if not readiness.get("ready_for_catalog", False):
        print("PostgreSQL is required for Catalog and is not ready.", file=sys.stderr)
        for reason in readiness.get("blocking_reasons", []):
            print(f"- {reason}", file=sys.stderr)
        for hint in readiness.get("setup_hints", []):
            print(f"hint: {hint}", file=sys.stderr)
        return 1

    try:
        result = ingest_catalog_file(
            source_cata_path=args.source_cata_path,
            catalog_source=args.catalog_source,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except MissingCatalogColumnsError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except SQLAlchemyError as exc:
        print(f"Catalog ingestion failed: {sanitize_database_error(str(exc)) or exc.__class__.__name__}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Catalog ingestion failed: {exc}", file=sys.stderr)
        return 1

    for key, value in result.to_dict().items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
