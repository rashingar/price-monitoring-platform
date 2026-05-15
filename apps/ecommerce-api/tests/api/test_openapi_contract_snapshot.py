import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.jobs.export_openapi_snapshot import normalize_openapi_schema  # noqa: E402

SNAPSHOT_PATH = PROJECT_ROOT / "docs" / "contracts" / "openapi.ecommerce.json"
REGENERATE_COMMAND = "python -m ecommerce.jobs.export_openapi_snapshot"


@pytest.mark.contract
def test_openapi_contract_snapshot_is_current() -> None:
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    actual = normalize_openapi_schema(create_app().openapi())

    assert actual == expected, (
        "Ecommerce OpenAPI contract changed. If this backend API change is intentional, "
        f"review the diff and regenerate the canonical snapshot with `{REGENERATE_COMMAND}`. "
        "Then update downstream UI fixtures/tests in a separate UI patch."
    )


@pytest.mark.contract
def test_openapi_snapshot_contains_ui_facing_routes() -> None:
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    paths = snapshot["paths"]
    required_routes = {
        ("GET", "/api/health"),
        ("GET", "/api/catalog/products"),
        ("GET", "/api/catalog/categories"),
        ("GET", "/api/catalog/category-hierarchy"),
        ("GET", "/api/catalog/brands"),
        ("GET", "/api/catalog/summary"),
        ("GET", "/api/catalog/products/{catalog_product_id}"),
        ("GET", "/api/catalog/products/{catalog_product_id}/source-url-candidates"),
        ("GET", "/api/catalog/products/{catalog_product_id}/source-urls"),
        ("POST", "/api/catalog/products/{catalog_product_id}/source-urls"),
        ("PATCH", "/api/catalog/source-urls/{source_url_id}"),
        ("POST", "/api/catalog/source-urls/{source_url_id}/validate"),
        ("GET", "/api/catalog/source-urls/summary"),
        ("GET", "/api/catalog/source-urls/import/options"),
        ("POST", "/api/catalog/source-urls/import/preview"),
        ("POST", "/api/catalog/source-urls/import/apply"),
        ("POST", "/api/catalog/source-urls/import/product-factory/preview"),
        ("POST", "/api/catalog/source-urls/import/product-factory/apply"),
        ("GET", "/api/vendor-sources/sources"),
        ("GET", "/api/vendor-sources/source-urls/summary"),
        ("GET", "/api/vendor-sources/source-health"),
        ("POST", "/api/vendor-sources/captures/runs"),
        ("GET", "/api/vendor-sources/captures/runs"),
        ("GET", "/api/vendor-sources/captures/runs/{run_id}"),
        ("GET", "/api/vendor-sources/captures/runs/{run_id}/artifacts"),
        ("GET", "/api/source-url-agent/sources"),
        ("POST", "/api/source-url-agent/runs"),
        ("POST", "/api/source-url-agent/runs/sync"),
        ("GET", "/api/source-url-agent/runs"),
        ("GET", "/api/source-url-agent/runs/{run_id}"),
        ("GET", "/api/source-url-agent/runs/{run_id}/artifacts"),
        ("GET", "/api/source-url-agent/candidates"),
        ("GET", "/api/source-url-agent/candidates/{candidate_id}"),
        ("PATCH", "/api/source-url-agent/candidates/{candidate_id}/review"),
        ("GET", "/api/files/roots"),
        ("GET", "/api/files/list"),
        ("POST", "/api/files/read"),
        ("POST", "/api/files/save"),
        ("POST", "/api/files/save-copy"),
        ("GET", "/api/paths/roots"),
        ("GET", "/api/artifacts/roots"),
        ("GET", "/api/artifacts/price-monitoring/runs/{run_id}"),
        ("GET", "/api/artifacts/read"),
        ("GET", "/api/artifacts/download"),
        ("GET", "/api/jobs"),
        ("GET", "/api/jobs/{job_id}"),
        ("POST", "/api/jobs/{job_id}/cancel"),
        ("POST", "/api/price-monitoring/selection/preview"),
        ("POST", "/api/price-monitoring/runs"),
        ("GET", "/api/price-monitoring/runs"),
        ("GET", "/api/price-monitoring/runs/{run_id}"),
        ("POST", "/api/price-monitoring/runs/{run_id}/fetch"),
        ("GET", "/api/price-monitoring/runs/{run_id}/fetch"),
        ("GET", "/api/price-monitoring/runs/{run_id}/fetch/executions"),
        ("GET", "/api/price-monitoring/runs/{run_id}/fetch/logs"),
        ("GET", "/api/price-monitoring/runs/{run_id}/fetch/{execution_id}"),
        ("GET", "/api/price-monitoring/runs/{run_id}/fetch/{execution_id}/logs"),
        ("POST", "/api/price-monitoring/runs/{run_id}/fetch/cancel"),
        ("POST", "/api/price-monitoring/runs/{run_id}/fetch/{execution_id}/cancel"),
        ("GET", "/api/price-monitoring/runs/{run_id}/review"),
        ("POST", "/api/price-monitoring/runs/{run_id}/backfill-listings"),
        ("POST", "/api/price-monitoring/runs/{run_id}/review/actions"),
        ("POST", "/api/price-monitoring/runs/{run_id}/export-price-update"),
        ("GET", "/api/price-monitoring/db/status"),
        ("GET", "/api/price-monitoring/observations"),
        ("GET", "/api/price-monitoring/runs/{run_id}/observations"),
        ("GET", "/api/price-monitoring/runs/{run_id}/catalog-snapshot"),
        ("GET", "/api/price-monitoring/products/{product_id}/price-history"),
        ("GET", "/api/price-monitoring/products/by-model/{model}/price-history"),
        ("GET", "/api/price-monitoring/alerts/rules"),
        ("POST", "/api/price-monitoring/alerts/rules"),
        ("GET", "/api/price-monitoring/alerts/rules/{rule_id}"),
        ("PATCH", "/api/price-monitoring/alerts/rules/{rule_id}"),
        ("POST", "/api/price-monitoring/alerts/rules/{rule_id}/deactivate"),
        ("GET", "/api/price-monitoring/alerts/events"),
        ("POST", "/api/price-monitoring/alerts/events/{event_id}/acknowledge"),
        ("POST", "/api/price-monitoring/alerts/events/{event_id}/resolve"),
        ("POST", "/api/price-monitoring/alerts/evaluate/{run_id}"),
    }

    missing = sorted(
        f"{method} {path}"
        for method, path in required_routes
        if path not in paths or method.lower() not in paths[path]
    )
    assert missing == [], f"OpenAPI snapshot is missing UI-facing routes: {missing}"
