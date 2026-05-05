from __future__ import annotations

from pathlib import Path

import pytest


_MODULE_MARKERS: dict[str, tuple[str, ...]] = {
    "test_contract_smoke.py": ("contract", "smoke"),
    "test_openapi_contract_snapshot.py": ("contract",),
    "test_artifacts_api.py": ("smoke", "contract"),
    "test_bridge_api.py": ("smoke", "integration"),
    "test_bridge_core.py": ("integration",),
    "test_catalog_api.py": ("smoke", "integration"),
    "test_catalog_db.py": ("integration",),
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
    "test_price_monitoring_alerts.py": ("integration",),
    "test_price_monitoring_api.py": ("smoke", "integration"),
    "test_price_monitoring_db.py": ("integration",),
    "test_price_monitoring_db_policy.py": ("smoke", "integration"),
    "test_price_monitoring_execution_utils.py": ("contract",),
    "test_price_monitoring_fetch_execution.py": ("integration",),
    "test_price_monitoring_fetch_run.py": ("integration",),
    "test_price_monitoring_review_export.py": ("integration",),
    "test_price_pipeline_lg_fixture.py": ("integration",),
    "test_pricing_engine.py": ("contract",),
    "test_product_agent_artifact_import.py": ("contract", "integration"),
    "test_product_agent_handoff_import.py": ("contract", "integration"),
    "test_product_ignore.py": ("contract",),
    "test_source_capture_unified.py": ("integration",),
    "test_source_catalog.py": ("contract",),
    "test_source_url_agent.py": ("integration",),
    "test_source_url_agent_api.py": ("smoke", "integration"),
    "test_source_url_import.py": ("integration",),
    "test_source_url_import_api.py": ("smoke", "integration"),
    "test_source_urls_api.py": ("smoke",),
    "test_vendor_sources_capture.py": ("integration",),
}

_FAST_EXCLUDED_MARKERS = {"slow", "external", "e2e", "legacy"}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    for item in items:
        path = Path(str(getattr(item, "path", item.fspath)))
        for marker in dict.fromkeys(_MODULE_MARKERS.get(path.name, ())):
            item.add_marker(getattr(pytest.mark, marker))

        marker_names = {marker.name for marker in item.iter_markers()}
        if marker_names.isdisjoint(_FAST_EXCLUDED_MARKERS):
            item.add_marker(pytest.mark.fast)
