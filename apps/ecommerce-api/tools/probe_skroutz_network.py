from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.source_capture.skroutz_network_diagnostic import (  # noqa: E402
    PlaywrightUnavailableError,
    run_skroutz_network_diagnostic,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture sanitized Skroutz browser network diagnostics.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", default="work/skroutz_network_probe.json")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    args = parser.parse_args()

    try:
        report = run_skroutz_network_diagnostic(
            args.url,
            headed=bool(args.headed),
            timeout_seconds=int(args.timeout_seconds),
        )
    except PlaywrightUnavailableError as exc:
        print(f"Playwright unavailable: {exc}", file=sys.stderr)
        return 2

    payload = report.to_dict()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"captured_response_count: {len(payload.get('captured_responses') or [])}")
    print("derived_endpoints:")
    for key, value in (payload.get("derived_endpoints") or {}).items():
        print(f"  {key}: {value}")
    print(f"filter_products_observed: {bool(payload.get('observed_filter_products_url'))}")
    print(f"shops_details_observed: {bool(payload.get('observed_shops_details_url'))}")
    print(f"best_product_data_endpoint: {payload.get('product_data_candidate_url') or '-'}")
    print(f"output: {output_path}")
    return 0 if payload.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
