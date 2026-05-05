"""Run one existing price monitoring fetch from a script-friendly entrypoint."""

from __future__ import annotations

import argparse
import sys

from sqlalchemy.exc import SQLAlchemyError

from pricefetcher.env import load_local_env_if_present
from pricefetcher.price_monitoring.fetch_run import PriceMonitoringFetchError, run_price_monitoring_fetch
from pricefetcher.price_monitoring.persistence import persist_fetch_result_if_configured
from pricefetcher.price_monitoring.runs import (
    PRICE_MONITORING_RUNS_DIR,
    InvalidPriceMonitoringRunIdError,
    resolve_price_monitoring_run_dir,
)


def main(argv: list[str] | None = None) -> int:
    load_local_env_if_present()
    parser = argparse.ArgumentParser(description="Run an existing PriceFetcher monitoring fetch now.")
    parser.add_argument("--source", default=None, help="Stored source/vendor for the run. Source all is not allowed.")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--catalog-url", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--trigger-type", choices=("manual", "scheduled"), default="scheduled")
    args = parser.parse_args(argv)

    if not args.run_id.strip():
        print("--run-id is required until a safe default selection mechanism exists.", file=sys.stderr)
        return 2

    try:
        run_dir = resolve_price_monitoring_run_dir(args.run_id, PRICE_MONITORING_RUNS_DIR)
    except InvalidPriceMonitoringRunIdError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    source_label = args.source or "selection_summary"
    print(f"Starting price monitoring fetch: run_id={args.run_id} source={source_label}")
    try:
        result = run_price_monitoring_fetch(run_dir, source=args.source, catalog_url=args.catalog_url)
        persistence = persist_fetch_result_if_configured(result, trigger_type=args.trigger_type)
    except (FileNotFoundError, ValueError, PriceMonitoringFetchError, SQLAlchemyError) as exc:
        print(f"Price monitoring fetch failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Completed price monitoring fetch: "
        f"status={result.status} enriched_csv_path={result.enriched_csv_path} "
        f"observation_count={persistence.observation_count}"
    )
    for warning in persistence.warnings:
        print(f"Warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
