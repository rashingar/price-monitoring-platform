"""CLI for local supervised Source URL Agent Mode."""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Sequence

from sqlalchemy.exc import SQLAlchemyError

from pricefetcher.catalog.source_catalog import DEFAULT_CATALOG_SOURCE
from pricefetcher.db.config import is_database_configured, sanitize_database_error
from pricefetcher.db.session import session_scope
from pricefetcher.env import load_local_env_if_present
from pricefetcher.source_url_agent.agent import SourceUrlAgentOptions, run_source_url_agent
from pricefetcher.source_url_agent.analysis import analyze_run_artifacts
from pricefetcher.source_url_agent.candidate_transfer import export_source_url_candidates, import_source_url_candidates
from pricefetcher.source_url_agent.products import read_products_from_catalog, read_products_from_csv
from pricefetcher.source_url_agent.review import apply_review_csv
from pricefetcher.source_url_agent.sources import SOURCE_CHOICES


def main(argv: Sequence[str] | None = None) -> int:
    load_local_env_if_present()
    parser = argparse.ArgumentParser(description="Run supervised source URL discovery.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run from a CSV input file.")
    run_parser.add_argument("--input", type=Path, required=True)
    _add_common_run_options(run_parser)

    catalog_parser = subparsers.add_parser("from-catalog", help="Run from DB-backed catalog_products.")
    _add_common_run_options(catalog_parser)

    review_parser = subparsers.add_parser("apply-review", help="Apply a reviewed needs_review CSV.")
    review_parser.add_argument("--review-file", type=Path, required=True)
    review_parser.add_argument("--dry-run", action="store_true", help="Preview review actions without DB writes.")
    review_parser.add_argument("--apply", action="store_true", help="Write accepted/replaced review URLs.")
    review_parser.add_argument("--json", action="store_true")

    analyze_parser = subparsers.add_parser("analyze", help="Analyze run artifacts and write analysis_summary.json.")
    analyze_parser.add_argument("--run-id", required=True)
    analyze_parser.add_argument("--output-dir", type=Path, default=None)
    analyze_parser.add_argument("--json", action="store_true")

    export_parser = subparsers.add_parser("export-candidates", help="Export all DB source URL candidates to one JSON file.")
    export_parser.add_argument("--output", type=Path, default=Path("output/source_url_agent/source_url_candidates_export.json"))
    export_parser.add_argument("--json", action="store_true")

    import_parser = subparsers.add_parser("import-candidates", help="Import a source URL candidate JSON export.")
    import_parser.add_argument("--input", type=Path, required=True)
    import_parser.add_argument("--dry-run", action="store_true", help="Preview import actions without DB writes.")
    import_parser.add_argument("--apply", action="store_true", help="Write imported candidates into the configured DB.")
    import_parser.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            return _run_from_csv(args)
        if args.command == "from-catalog":
            return _run_from_catalog(args)
        if args.command == "apply-review":
            return _apply_review(args)
        if args.command == "analyze":
            return _analyze(args)
        if args.command == "export-candidates":
            return _export_candidates(args)
        if args.command == "import-candidates":
            return _import_candidates(args)
    except SQLAlchemyError as exc:
        print(f"Source URL Agent DB error: {sanitize_database_error(str(exc)) or exc.__class__.__name__}", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as exc:
        print(f"Source URL Agent failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Source URL Agent interrupted.", file=sys.stderr)
        return 130
    return 2


def _run_from_csv(args: argparse.Namespace) -> int:
    if not is_database_configured():
        print("Source URL Agent requires PRICEFETCHER_DATABASE_URL so runs and candidates are written to PostgreSQL.", file=sys.stderr)
        return 1
    active_only = _bool_arg(args.active_only)
    products = read_products_from_csv(
        args.input,
        catalog_source=DEFAULT_CATALOG_SOURCE,
        active_only=active_only,
        limit=args.limit,
        offset=args.offset,
        model=args.model,
    )
    with session_scope() as session:
        result = run_source_url_agent(
            products=products,
            options=_options(args, mode="csv", input_path=args.input, active_only=active_only),
            session=session,
        )
    _print_run_result(result, json_output=args.json)
    return 0


def _run_from_catalog(args: argparse.Namespace) -> int:
    if not is_database_configured():
        print("from-catalog requires PRICEFETCHER_DATABASE_URL.", file=sys.stderr)
        return 1
    active_only = _bool_arg(args.active_only)
    with session_scope() as session:
        products = read_products_from_catalog(
            session,
            catalog_source=DEFAULT_CATALOG_SOURCE,
            active_only=active_only,
            limit=args.limit,
            offset=args.offset,
            catalog_product_id=args.catalog_product_id,
            model=args.model,
        )
        result = run_source_url_agent(
            products=products,
            options=_options(args, mode="catalog", input_path=None, active_only=active_only),
            session=session,
        )
    _print_run_result(result, json_output=args.json)
    return 0


def _apply_review(args: argparse.Namespace) -> int:
    apply = bool(args.apply and not args.dry_run)
    if apply and not is_database_configured():
        print("apply-review --apply requires PRICEFETCHER_DATABASE_URL.", file=sys.stderr)
        return 1
    session_cm = session_scope() if is_database_configured() else nullcontext(None)
    with session_cm as session:
        result = apply_review_csv(session, review_file=args.review_file, apply=apply)
    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"mode: {'apply' if apply else 'dry-run'}")
        for key, value in payload["counters"].items():
            print(f"{key}: {value}")
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
    return 0


def _analyze(args: argparse.Namespace) -> int:
    payload = analyze_run_artifacts(args.run_id, output_dir=args.output_dir)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"run_id: {payload['run_id']}")
        print(f"candidate_count: {payload['candidate_count']}")
        print(f"by_status: {payload['by_status']}")
        for recommendation in payload["recommendations"]:
            print(f"recommendation: {recommendation['type']} - {recommendation['message']}")
    return 0


def _export_candidates(args: argparse.Namespace) -> int:
    if not is_database_configured():
        print("export-candidates requires PRICEFETCHER_DATABASE_URL.", file=sys.stderr)
        return 1
    with session_scope() as session:
        result = export_source_url_candidates(session, args.output)
    _print_transfer_result(result.to_dict(), json_output=args.json)
    return 0


def _import_candidates(args: argparse.Namespace) -> int:
    if not is_database_configured():
        print("import-candidates requires PRICEFETCHER_DATABASE_URL.", file=sys.stderr)
        return 1
    apply = bool(args.apply and not args.dry_run)
    with session_scope() as session:
        result = import_source_url_candidates(session, args.input, apply=apply)
    payload = result.to_dict()
    payload["mode"] = "apply" if apply else "dry-run"
    _print_transfer_result(payload, json_output=args.json)
    return 0


def _add_common_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", choices=SOURCE_CHOICES, default="all")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--catalog-product-id", type=int, default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--missing-only", action="store_true")
    parser.add_argument("--active-only", nargs="?", const="true", default="true")
    parser.add_argument("--dry-run", action="store_true", help="Do not write source_urls. Default unless --apply-high-confidence is used.")
    parser.add_argument("--apply-high-confidence", action="store_true", help="Write high-confidence matches to source_urls.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--max-products-per-batch", type=int, default=None)
    parser.add_argument("--max-searches-per-product-source", type=int, default=None)
    parser.add_argument("--rate-limit-seconds", type=float, default=None)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--no-browser-cache", action="store_true")
    parser.add_argument("--json", action="store_true")


def _options(
    args: argparse.Namespace,
    *,
    mode: str,
    input_path: Path | None,
    active_only: bool,
) -> SourceUrlAgentOptions:
    dry_run = bool(args.dry_run or not args.apply_high_confidence)
    return SourceUrlAgentOptions(
        mode=mode,
        source=args.source,
        input_path=input_path,
        output_dir=args.output_dir,
        limit=args.limit,
        offset=args.offset,
        catalog_product_id=args.catalog_product_id,
        model=args.model,
        missing_only=args.missing_only,
        active_only=active_only,
        dry_run=dry_run,
        apply_high_confidence=bool(args.apply_high_confidence),
        max_products_per_batch=args.max_products_per_batch,
        max_searches_per_product_source=args.max_searches_per_product_source,
        rate_limit_seconds=args.rate_limit_seconds,
        headed=bool(args.headed),
        no_browser_cache=bool(args.no_browser_cache),
    )


def _print_run_result(result, *, json_output: bool) -> None:
    payload = {**result.summary, "artifacts": result.artifacts.to_dict()}
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"run_id: {result.run_id}")
    print(f"mode: {'apply-high-confidence' if payload['apply_high_confidence'] else 'dry-run'}")
    for key in ("selected_count", "candidate_count", "matched_count", "needs_review_count", "not_found_count", "error_count"):
        print(f"{key}: {payload[key]}")
    print(f"run_dir: {result.artifacts.run_dir}")
    for warning in result.warnings:
        print(f"warning: {warning}")


def _print_transfer_result(payload: dict, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if "mode" in payload:
        print(f"mode: {payload['mode']}")
    print(f"path: {payload['path']}")
    for key, value in payload["counters"].items():
        print(f"{key}: {value}")
    for warning in payload["warnings"]:
        print(f"warning: {warning}")


def _bool_arg(value: object) -> bool:
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("boolean value must be true or false")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
