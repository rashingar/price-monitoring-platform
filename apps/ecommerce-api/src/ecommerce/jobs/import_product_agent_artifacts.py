"""Import legacy Product-Agent raw scrape artifacts into source snapshots."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from sqlalchemy.exc import SQLAlchemyError

from ecommerce.catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.config import sanitize_database_error
from ecommerce.db.session import session_scope
from ecommerce.env import load_local_env_if_present
from ecommerce.source_capture.product_agent_import import (
    DEFAULT_PRODUCT_AGENT_WORK_ROOT,
    import_product_agent_artifacts,
)


PRODUCT_AGENT_WORK_ROOT_ENV_VAR = "ECOMMERCE_PRODUCT_AGENT_WORK_ROOT"


def main(argv: Sequence[str] | None = None) -> int:
    load_local_env_if_present()
    parser = argparse.ArgumentParser(description="Import Product-Agent scrape artifacts into source capture snapshots.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Defaults to dry-run.")
    parser.add_argument("--root", type=Path, default=_default_root(), help="Product-Agent work root to scan.")
    parser.add_argument("--catalog-source", default=DEFAULT_CATALOG_SOURCE, help="Product catalog source for created products.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum artifacts to process.")
    parser.add_argument("--json", action="store_true", help="Write JSON output.")
    parser.add_argument("--report-path", type=Path, default=None, help="Optional JSON report path.")
    args = parser.parse_args(argv)

    try:
        with session_scope() as session:
            result = import_product_agent_artifacts(
                session,
                artifact_root=args.root,
                apply=args.apply,
                catalog_source=args.catalog_source,
                limit=args.limit,
            )
    except SQLAlchemyError as exc:
        print(f"Product-Agent artifact import failed: {sanitize_database_error(str(exc)) or exc.__class__.__name__}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Product-Agent artifact import failed: {exc}", file=sys.stderr)
        return 1

    payload = result.to_dict(include_items=bool(args.report_path))
    if args.report_path is not None:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(json.dumps(result.to_dict(include_items=True), ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"mode: {'apply' if args.apply else 'dry-run'}")
        print(f"artifact_root: {payload['artifact_root']}")
        for key, value in payload["counters"].items():
            print(f"{key}: {value}")
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
    return 0


def _default_root() -> Path:
    configured = str(os.environ.get(PRODUCT_AGENT_WORK_ROOT_ENV_VAR) or "").strip()
    return Path(configured) if configured else DEFAULT_PRODUCT_AGENT_WORK_ROOT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
