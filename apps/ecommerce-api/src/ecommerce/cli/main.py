"""Command-line entrypoint for the Phase 1-2 scaffolding."""

from __future__ import annotations

import argparse
from pathlib import Path

from ecommerce.core.price_workflow import run_price
from ecommerce.catalog.source_catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.session import session_scope
from ecommerce.env import load_local_env_if_present
from ecommerce.source_capture.product_agent_import import DEFAULT_PRODUCT_AGENT_WORK_ROOT, import_product_agent_artifacts
from ecommerce.source_capture.scheduled import capture_due_product_sources


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ecommerce")
    subparsers = parser.add_subparsers(dest="command", required=True)

    price_parser = subparsers.add_parser("price")
    price_parser.add_argument("--input", required=True, type=Path)
    price_parser.add_argument("--rule-config", required=True, type=Path)
    price_parser.add_argument("--output-dir", required=False)
    price_parser.set_defaults(handler=_handle_price)

    capture_parser = subparsers.add_parser("capture-sources")
    capture_parser.add_argument("--refresh-after-minutes", type=int, default=360)
    capture_parser.add_argument("--limit", type=int, default=50)
    capture_parser.add_argument("--vendor", required=False)
    capture_parser.add_argument("--product-source-id", action="append", type=int, default=[])
    capture_parser.add_argument("--include-not-due", action="store_true")
    capture_parser.set_defaults(handler=_handle_capture_sources)

    import_product_agent_parser = subparsers.add_parser("import-product-agent-artifacts")
    import_product_agent_parser.add_argument("--apply", action="store_true")
    import_product_agent_parser.add_argument("--root", type=Path, default=DEFAULT_PRODUCT_AGENT_WORK_ROOT)
    import_product_agent_parser.add_argument("--catalog-source", default=DEFAULT_CATALOG_SOURCE)
    import_product_agent_parser.add_argument("--limit", type=int, default=None)
    import_product_agent_parser.set_defaults(handler=_handle_import_product_agent_artifacts)
    return parser

def _handle_price(args: argparse.Namespace) -> int:
    run_price(
        input_path=args.input,
        rule_config_path=args.rule_config,
        output_dir_override=args.output_dir,
    )
    return 0


def _handle_capture_sources(args: argparse.Namespace) -> int:
    with session_scope() as session:
        summary = capture_due_product_sources(
            session,
            refresh_after_minutes=max(0, int(args.refresh_after_minutes)),
            limit=max(1, int(args.limit)),
            vendor_slug=str(args.vendor).strip() if args.vendor else None,
            product_source_ids=[int(item) for item in args.product_source_id],
            include_not_due=bool(args.include_not_due),
        )
    print(
        "source capture completed: "
        f"selected={summary.selected_count} succeeded={summary.succeeded_count} failed={summary.failed_count}"
    )
    return 0


def _handle_import_product_agent_artifacts(args: argparse.Namespace) -> int:
    with session_scope() as session:
        result = import_product_agent_artifacts(
            session,
            artifact_root=args.root,
            apply=bool(args.apply),
            catalog_source=str(args.catalog_source),
            limit=args.limit,
        )
    counters = result.to_dict(include_items=False)["counters"]
    print(
        "product-agent artifact import completed: "
        f"mode={'apply' if args.apply else 'dry-run'} "
        f"discovered={counters.get('artifacts_discovered', 0)} "
        f"imported_snapshots={counters.get('imported_snapshot_count', 0)} "
        f"price_observations={counters.get('price_observation_count', 0)} "
        f"skipped={counters.get('skipped_count', 0)}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    load_local_env_if_present()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
