"""Import Product Factory ecommerce_source_handoff.json artifacts."""

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
from ecommerce.product_factory_handoff import import_product_factory_handoff


def main(argv: Sequence[str] | None = None) -> int:
    load_local_env_if_present()
    parser = argparse.ArgumentParser(
        description="Import Product Factory source URL handoff artifacts."
    )
    parser.add_argument(
        "--file",
        required=True,
        type=Path,
        help="Path to ecommerce_source_handoff.json.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing. This is the default.",
    )
    mode.add_argument("--apply", action="store_true", help="Write changes.")
    parser.add_argument(
        "--catalog-source",
        default=DEFAULT_CATALOG_SOURCE,
        help="Catalog source override.",
    )
    parser.add_argument(
        "--no-initial-capture",
        action="store_true",
        help="Skip source_capture_snapshot and price observation import.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Maximum source URLs to process."
    )
    parser.add_argument("--json", action="store_true", help="Write JSON output.")
    parser.add_argument(
        "--report-path", type=Path, default=None, help="Optional JSON report path."
    )
    args = parser.parse_args(argv)

    try:
        with session_scope() as session:
            result = import_product_factory_handoff(
                session,
                file_path=args.file,
                apply=bool(args.apply),
                catalog_source=args.catalog_source,
                persist_initial_capture=not bool(args.no_initial_capture),
                limit=args.limit,
            )
    except SQLAlchemyError as exc:
        print(
            f"Product Factory handoff import failed: {sanitize_database_error(str(exc)) or exc.__class__.__name__}",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(f"Product Factory handoff import failed: {exc}", file=sys.stderr)
        return 1

    payload = result.to_dict(include_items=bool(args.report_path))
    if args.report_path is not None:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(
            json.dumps(
                result.to_dict(include_items=True), ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        counters = payload["counters"]
        print(f"mode: {'apply' if args.apply else 'dry-run'}")
        print(f"file_path: {payload['file_path']}")
        for key in sorted(counters):
            print(f"{key}: {counters[key]}")
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
