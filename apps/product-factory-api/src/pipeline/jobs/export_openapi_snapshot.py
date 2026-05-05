from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pipeline.api.app import create_app
from pipeline.repo_paths import REPO_ROOT


DEFAULT_SNAPSHOT_PATH = REPO_ROOT / "docs" / "contracts" / "openapi.product-factory.json"


def normalize_openapi_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic OpenAPI payload suitable for snapshot tests."""
    return _normalize(schema)


def export_openapi_snapshot(output_path: Path = DEFAULT_SNAPSHOT_PATH) -> Path:
    normalized = normalize_openapi_schema(create_app().openapi())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the Product Factory FastAPI OpenAPI snapshot.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_SNAPSHOT_PATH,
        help="OpenAPI snapshot output path.",
    )
    args = parser.parse_args(argv)
    written_path = export_openapi_snapshot(args.output)
    print(written_path)
    return 0


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
