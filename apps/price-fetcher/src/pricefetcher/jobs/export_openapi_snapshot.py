"""Export the canonical PriceFetcher OpenAPI contract snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pricefetcher.api.app import create_app

DEFAULT_OUTPUT_PATH = Path("docs") / "contracts" / "openapi.pricefetcher.json"


def normalize_openapi_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic, JSON-serializable OpenAPI schema."""

    return _normalize(schema)


def export_openapi_snapshot(output_path: Path = DEFAULT_OUTPUT_PATH) -> Path:
    schema = normalize_openapi_schema(create_app().openapi())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export the PriceFetcher OpenAPI contract snapshot.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output JSON path. Defaults to {DEFAULT_OUTPUT_PATH.as_posix()}.",
    )
    args = parser.parse_args(argv)
    output_path = export_openapi_snapshot(args.output)
    print(f"Wrote OpenAPI snapshot: {output_path}")


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


if __name__ == "__main__":
    main()
