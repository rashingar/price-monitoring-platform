from __future__ import annotations

import json
from pathlib import Path

from pipeline.api.app import create_app
from pipeline.jobs.export_openapi_snapshot import normalize_openapi_schema


REPO_ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT_PATH = REPO_ROOT / "docs" / "contracts" / "openapi.product-factory.json"
REGENERATE_COMMAND = r"..\.venv\Scripts\python.exe -m pipeline.jobs.export_openapi_snapshot"


def test_openapi_snapshot_matches_current_api_contract() -> None:
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    current = normalize_openapi_schema(create_app().openapi())

    assert current == expected, (
        "Product Factory API contract changed. Regenerate the canonical OpenAPI snapshot "
        f"from apps/product-factory-api/src/ with: {REGENERATE_COMMAND}"
    )
