from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


_MODULE_MARKERS: dict[str, tuple[str, ...]] = {
    "test_contract_smoke.py": ("contract", "smoke"),
    "test_openapi_contract_snapshot.py": ("contract", "golden"),
    "test_artifacts_api.py": ("smoke", "contract"),
    "test_bridge_api.py": ("smoke", "integration"),
    "test_bridge_core.py": ("integration",),
    "test_catalog_api.py": ("smoke", "integration", "db_integration"),
    "test_catalog_db.py": ("integration", "db_contract"),
    "test_category_path.py": ("contract",),
    "test_csv_validation.py": ("contract",),
    "test_fetch_matching.py": ("contract",),
    "test_file_editor.py": ("integration",),
    "test_files_api.py": ("smoke",),
    "test_ignore_api.py": ("smoke",),
    "test_local_env.py": ("contract",),
    "test_output_naming.py": ("contract",),
    "test_paths_api.py": ("smoke",),
    "test_postgres_setup_docs.py": ("contract",),
    "test_price_monitoring_alerts.py": ("integration", "db_integration"),
    "test_price_monitoring_api.py": ("smoke", "integration", "db_integration"),
    "test_price_monitoring_db.py": ("integration", "db_integration", "runtime"),
    "test_price_monitoring_db_policy.py": ("smoke", "integration", "db_contract"),
    "test_price_monitoring_execution_utils.py": ("contract",),
    "test_price_monitoring_fetch_execution.py": ("integration", "runtime"),
    "test_price_monitoring_fetch_run.py": ("integration", "runtime"),
    "test_price_monitoring_review_export.py": ("integration",),
    "test_price_pipeline_lg_fixture.py": ("integration", "golden"),
    "test_pricing_engine.py": ("contract", "golden"),
    "test_product_factory_handoff_import.py": ("contract", "integration", "golden"),
    "test_product_ignore.py": ("contract",),
    "test_source_capture_unified.py": ("integration", "db_integration", "runtime"),
    "test_source_catalog.py": ("contract",),
    "test_source_url_agent.py": ("integration", "db_integration", "runtime"),
    "test_source_url_agent_api.py": ("smoke", "integration", "db_integration"),
    "test_source_url_import.py": ("integration", "db_contract"),
    "test_source_url_import_api.py": ("smoke", "integration", "db_integration"),
    "test_source_urls_api.py": ("smoke",),
    "test_vendor_sources_capture.py": ("integration", "db_integration", "runtime"),
}

_TEST_MARKERS: dict[tuple[str, str], tuple[str, ...]] = {
    ("test_price_monitoring_alerts.py", "test_fetch_integration_evaluates_active_alert_rules"): ("runtime",),
    ("test_price_monitoring_alerts.py", "test_fetch_integration_skips_when_no_active_rules"): ("runtime",),
    ("test_source_url_agent_api.py", "test_source_url_agent_run_api_dry_run_from_catalog_persists_run_and_candidates"): ("runtime",),
    ("test_source_url_agent_api.py", "test_vendor_sources_agent_run_namespace_delegates_to_source_url_agent"): ("runtime",),
    ("test_source_url_agent_api.py", "test_source_url_agent_run_api_enforces_bounded_default_limit"): ("runtime",),
    ("test_source_url_agent_api.py", "test_source_url_agent_run_artifact_endpoint_returns_safe_metadata"): ("runtime",),
}

_FAST_EXCLUDED_MARKERS = {
    "slow",
    "external",
    "e2e",
    "legacy",
    "runtime",
    "db_integration",
    "postgres_required",
}
_RUNTIME_GUARD_ALLOWED_MARKERS = {"runtime", "integration", "slow", "e2e", "external", "postgres_required"}
_RUNTIME_GUARD_MESSAGE = (
    "subprocess calls are blocked in fast tests. "
    "If this runtime behavior is intentional, mark the test as runtime, integration, slow, e2e, external, "
    "or postgres_required."
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    for item in items:
        path = Path(str(getattr(item, "path", item.fspath)))
        test_name = getattr(item, "originalname", None) or item.name.split("[", 1)[0]
        markers = (*_MODULE_MARKERS.get(path.name, ()), *_TEST_MARKERS.get((path.name, test_name), ()))
        for marker in dict.fromkeys(markers):
            item.add_marker(getattr(pytest.mark, marker))

        marker_names = {marker.name for marker in item.iter_markers()}
        if marker_names.isdisjoint(_FAST_EXCLUDED_MARKERS):
            item.add_marker(pytest.mark.fast)


@pytest.fixture(autouse=True)
def _block_runtime_subprocess_calls_in_fast_tests(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    marker_names = {marker.name for marker in request.node.iter_markers()}
    if not marker_names.isdisjoint(_RUNTIME_GUARD_ALLOWED_MARKERS):
        yield
        return

    def blocked_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        del args, kwargs
        pytest.fail(_RUNTIME_GUARD_MESSAGE, pytrace=False)

    def blocked_run(*args, **kwargs):  # noqa: ANN002, ANN003
        del args, kwargs
        pytest.fail(_RUNTIME_GUARD_MESSAGE, pytrace=False)

    monkeypatch.setattr(subprocess, "Popen", blocked_popen)
    monkeypatch.setattr(subprocess, "run", blocked_run)
    yield
