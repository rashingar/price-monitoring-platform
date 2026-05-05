"""Internal subprocess worker for one Price Monitoring execution."""

from __future__ import annotations

import argparse
import sys

from pricefetcher.price_monitoring import fetch_execution
from pricefetcher.price_monitoring.runs import (
    PRICE_MONITORING_RUNS_DIR,
    resolve_price_monitoring_run_dir,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one internal Price Monitoring execution.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--execution-type", required=True)
    args = parser.parse_args(argv)

    if args.execution_type != "fetch":
        print(f"Unsupported execution type: {args.execution_type}", file=sys.stderr)
        return 2

    run_dir = resolve_price_monitoring_run_dir(args.run_id, PRICE_MONITORING_RUNS_DIR)
    return fetch_execution.run_fetch_execution_child(run_dir, args.execution_id)


if __name__ == "__main__":
    raise SystemExit(main())
