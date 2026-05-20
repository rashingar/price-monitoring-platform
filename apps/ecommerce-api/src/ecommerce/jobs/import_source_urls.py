"""Import known product URLs into source_urls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from sqlalchemy.exc import SQLAlchemyError

from ecommerce.catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.config import sanitize_database_error
from ecommerce.db.session import session_scope
from ecommerce.env import load_local_env_if_present
from ecommerce.source_url_import import SUMMARY_COUNTERS, import_source_urls


def main(argv: Sequence[str] | None = None) -> int:
    load_local_env_if_present()
    parser = argparse.ArgumentParser(
        description="Import known product URLs into source_urls."
    )
    parser.add_argument(
        "--apply", action="store_true", help="Write changes. Defaults to dry-run."
    )
    parser.add_argument(
        "--catalog-source",
        default=DEFAULT_CATALOG_SOURCE,
        help="Catalog source to resolve candidates against.",
    )
    parser.add_argument(
        "--observations", action="store_true", help="Include DB price_observations."
    )
    parser.add_argument(
        "--artifacts",
        action="store_true",
        help="Include DB-referenced enriched CSV artifacts.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Maximum candidates to process."
    )
    parser.add_argument("--json", action="store_true", help="Write JSON output.")
    parser.add_argument(
        "--report-path", type=Path, default=None, help="Optional JSON report path."
    )
    args = parser.parse_args(argv)

    include_observations = args.observations or not args.artifacts
    include_artifacts = args.artifacts or not args.observations

    try:
        with session_scope() as session:
            result = import_source_urls(
                session,
                apply=args.apply,
                catalog_source=args.catalog_source,
                include_observations=include_observations,
                include_artifacts=include_artifacts,
                limit=args.limit,
            )
    except SQLAlchemyError as exc:
        print(
            f"Source URL import failed: {sanitize_database_error(str(exc)) or exc.__class__.__name__}",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(f"Source URL import failed: {exc}", file=sys.stderr)
        return 1

    payload = result.to_dict(include_candidates=bool(args.report_path))
    if args.report_path is not None:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(
            json.dumps(
                result.to_dict(include_candidates=True), ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"mode: {'apply' if args.apply else 'dry-run'}")
        for key in SUMMARY_COUNTERS:
            print(f"{key}: {payload[key]}")
        print(f"sources_processed: {', '.join(payload['sources_processed'])}")
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
