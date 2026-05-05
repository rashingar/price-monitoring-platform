from __future__ import annotations

from pathlib import Path

import pytest

_TESTS_ROOT = Path(__file__).resolve().parent
_FIXTURES_ROOT = _TESTS_ROOT / "fixtures"
_PROVIDERS_FIXTURES_ROOT = _FIXTURES_ROOT / "providers"


@pytest.fixture(scope="session")
def tests_root() -> Path:
    return _TESTS_ROOT


@pytest.fixture(scope="session")
def fixtures_root() -> Path:
    return _FIXTURES_ROOT


@pytest.fixture(scope="session")
def providers_fixtures_root() -> Path:
    return _PROVIDERS_FIXTURES_ROOT


@pytest.fixture(scope="session")
def skroutz_provider_fixtures_root(providers_fixtures_root: Path) -> Path:
    return providers_fixtures_root / "skroutz"


@pytest.fixture(scope="session")
def electronet_provider_fixtures_root(providers_fixtures_root: Path) -> Path:
    return providers_fixtures_root / "electronet"


@pytest.fixture(scope="session")
def manufacturer_tefal_provider_fixtures_root(providers_fixtures_root: Path) -> Path:
    return providers_fixtures_root / "manufacturer_tefal"


@pytest.fixture(scope="session")
def pipeline_run_fixtures_root(fixtures_root: Path) -> Path:
    return fixtures_root / "pipeline_runs"


@pytest.fixture(scope="session")
def golden_outputs_root(fixtures_root: Path) -> Path:
    return fixtures_root / "golden_outputs"


@pytest.fixture(scope="session")
def skroutz_golden_outputs_root(golden_outputs_root: Path) -> Path:
    return golden_outputs_root / "skroutz"


@pytest.fixture(scope="session")
def skroutz_fixtures_root(skroutz_provider_fixtures_root: Path) -> Path:
    return skroutz_provider_fixtures_root


_MODULE_MARKERS: dict[str, tuple[str, ...]] = {
    "test_api_contract_smoke.py": ("smoke", "contract"),
    "test_api_health.py": ("contract",),
    "test_api_jobs.py": ("contract", "job_lifecycle"),
    "test_api_public_schema_shapes.py": ("contract",),
    "test_category_filters_runtime.py": ("stage", "filters", "render"),
    "test_characteristics_pipeline.py": ("unit", "filters"),
    "test_characteristics_robot_vacuum.py": ("unit", "filters"),
    "test_characteristics_skroutz_built_in_oven.py": ("unit", "filters"),
    "test_characteristics_skroutz_microwave.py": ("unit", "filters"),
    "test_csv_writer.py": ("stage", "render"),
    "test_deterministic_fields.py": ("unit", "prepare"),
    "test_deterministic_fields_ice_cream_maker.py": ("unit", "prepare"),
    "test_dev_start.py": ("contract",),
    "test_eprel.py": ("stage", "source_acquisition"),
    "test_execution_models.py": ("contract", "prepare", "render", "publish"),
    "test_fetcher_gallery_download.py": ("stage", "source_acquisition"),
    "test_filter_review_service.py": ("contract", "stage", "filters", "filter_review"),
    "test_filters_manager_api.py": ("contract", "filters"),
    "test_filters_manager_persistence.py": ("contract", "filters"),
    "test_job_runner.py": ("job_lifecycle",),
    "test_job_store.py": ("unit", "job_lifecycle"),
    "test_job_worker_cli.py": ("contract", "job_lifecycle"),
    "test_llm_contract.py": ("unit", "contract", "authoring"),
    "test_llm_stage_execution.py": ("stage", "authoring"),
    "test_manufacturer_enrichment.py": ("stage", "source_acquisition"),
    "test_manufacturer_enrichment_tefal.py": ("stage", "source_acquisition"),
    "test_metadata.py": ("contract",),
    "test_normalize.py": ("unit",),
    "test_openapi_contract_routes.py": ("contract",),
    "test_openapi_contract_snapshot.py": ("contract",),
    "test_parser_product_manufacturer.py": ("stage", "source_acquisition"),
    "test_prepare_provider_resolution.py": ("stage", "prepare", "source_acquisition"),
    "test_prepare_result_assembly_module.py": ("stage", "prepare", "filters", "authoring"),
    "test_prepare_scrape_persistence.py": ("stage", "prepare", "authoring"),
    "test_prepare_section_assets.py": ("stage", "prepare", "source_acquisition"),
    "test_prepare_section_assets_module.py": ("stage", "prepare", "source_acquisition"),
    "test_prepare_skroutz_section_assets_module.py": ("stage", "prepare", "source_acquisition"),
    "test_prepare_stage_result_assembly.py": ("stage", "prepare"),
    "test_prepare_taxonomy_enrichment.py": ("stage", "prepare", "filters"),
    "test_prepare_taxonomy_enrichment_module.py": ("stage", "prepare", "filters"),
    "test_presentation_sections.py": ("unit", "render"),
    "test_price.py": ("unit",),
    "test_product_parser.py": ("stage", "source_acquisition"),
    "test_provider_selection.py": ("stage", "prepare", "source_acquisition"),
    "test_schema_matcher.py": ("unit", "filters"),
    "test_schema_matcher_compiled_library_regressions.py": ("unit", "filters"),
    "test_services.py": ("contract", "stage", "prepare", "render", "publish"),
    "test_settings_authoring.py": ("contract", "authoring"),
    "test_skroutz_built_in_family_override.py": ("stage", "source_acquisition", "filters"),
    "test_skroutz_integration.py": ("stage", "source_acquisition", "render"),
    "test_skroutz_robot_vacuum.py": ("stage", "source_acquisition", "filters"),
    "test_skroutz_sections.py": ("stage", "source_acquisition", "prepare", "render"),
    "test_skroutz_taxonomy.py": ("stage", "source_acquisition", "filters"),
    "test_skroutz_taxonomy_microwave.py": ("stage", "source_acquisition", "filters"),
    "test_source_acquisition_stage.py": ("stage", "source_acquisition"),
    "test_sync_filter_map.py": ("unit", "stage", "filters"),
    "test_taxonomy.py": ("unit", "filters"),
    "test_utils_support_paths.py": ("unit", "contract", "filters"),
    "test_validator.py": ("unit", "render"),
    "test_workflow.py": ("contract", "stage", "prepare", "render", "publish", "authoring"),
}

_TEST_MARKERS: dict[tuple[str, str], tuple[str, ...]] = {
    ("test_job_runner.py", "test_subprocess_runner_launches_child_and_records_process_metadata"): ("integration", "slow"),
    ("test_job_runner.py", "test_nonzero_child_exit_marks_failed_when_no_terminal_status_exists"): ("integration", "slow"),
    ("test_job_runner.py", "test_parent_preserves_terminal_status_written_by_child_on_nonzero_exit"): ("integration", "slow"),
    ("test_job_runner.py", "test_stop_queued_job_in_runner_queue_marks_cancelled_and_never_launches"): ("integration", "slow"),
    ("test_job_runner.py", "test_stop_running_child_graceful_terminate_marks_cancelled"): ("integration", "slow"),
    ("test_job_runner.py", "test_stop_running_child_force_kills_after_timeout"): ("integration", "slow"),
    ("test_job_runner.py", "test_same_model_jobs_do_not_run_concurrently_with_multiple_workers"): ("integration", "slow"),
    ("test_job_worker_cli.py", "test_worker_cli_missing_job_returns_nonzero"): ("integration", "slow"),
    ("test_skroutz_integration.py", "test_prepare_and_render_workflow_with_skroutz_fixtures"): ("integration", "slow", "e2e"),
    ("test_skroutz_sections.py", "test_143481_rendered_description_preserves_locked_wrappers"): ("integration", "slow", "e2e"),
    ("test_skroutz_taxonomy.py", "test_taxonomy_regression_fixture_resolves_expected_categories"): ("slow",),
    ("test_skroutz_taxonomy.py", "test_representative_taxonomy_html_fixtures_cover_supported_skroutz_combos"): ("slow",),
}

_FAST_EXCLUDED_MARKERS = {"slow", "external", "e2e", "legacy"}


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
