# Product Factory Test Suite Map

Audit date: 2026-05-02

Baseline commands were run from `apps/product-factory-api/src` with the repo virtual environment:

```powershell
..\.venv\Scripts\python.exe -m pytest --collect-only -q
..\.venv\Scripts\python.exe -m pytest -q --durations=30 --durations-min=0.05
```

Collection found 437 tests. The duration run found 435 passing tests and 2 render authoring failures caused by tests hardcoding the old configured intro range while the editable `resources/settings/product_factory_settings.json` file configured `70-180`. The render tests now derive retry expectations from the active settings policy.

## Layer Strategy

| Layer | Default fast? | Purpose |
| --- | --- | --- |
| Unit | Yes | Pure or near-pure transforms: normalization, deterministic fields, taxonomy helpers, filters, validation helpers. |
| Contract | Yes | Fast API, service, artifact, settings, filter manager, and authoring response shape tests. |
| Stage | Yes when fixture-only and small | Isolated current runtime stages: source acquisition, prepare enrichment, filter review, authoring, render, publish handoff, job lifecycle. |
| Integration | No unless deliberately selected | Local subprocess or broad filesystem behavior for current runtime. These tests are also marked `slow` when excluded from the default fast command. |
| E2E/external | No | Full prepare/render/publish workflows or tests that require live websites, browser automation against live pages, OpenCart, OpenAI, credentials, or network. |
| Legacy | No | Tests tied only to removed runtime entrypoints. No such active tests were found; tests asserting legacy contracts are absent remain current contract tests. |

## Test Inventory

| Test path | Area | Stage/layer | Runtime relevance | Dependency profile | Speed profile | Recommendation | Rationale |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `src/product_factory/tests/test_api_health.py` | API health | contract | current | pure | fast | keep contract | Covers `/api/health` schema and TestClient response. |
| `src/product_factory/tests/test_api_jobs.py` | Jobs API | contract, job_lifecycle | current | tmp_path/filesystem | fast | keep contract | Covers enqueue, stop, logs, and artifact resolver paths without real subprocesses. |
| `src/product_factory/tests/test_category_filters_runtime.py` | Category filters runtime | stage, filters, render | current | tmp_path/filesystem | fast | keep stage | Covers resolver, CSV writer ordering, validation diagnostics, and render-style filter output. |
| `src/product_factory/tests/test_characteristics_pipeline.py` | Characteristics normalization | unit, filters | current | pure | fast | keep fast | Covers label normalization, schema matching, and characteristics fallback behavior. |
| `src/product_factory/tests/test_characteristics_robot_vacuum.py` | Characteristics schema | unit, filters | current | pure | fast | keep fast | Covers robot vacuum schema selection. |
| `src/product_factory/tests/test_characteristics_skroutz_built_in_oven.py` | Characteristics enrichment | unit, filters | current | pure | fast | keep fast | Covers Skroutz oven alias enrichment. |
| `src/product_factory/tests/test_characteristics_skroutz_microwave.py` | Characteristics enrichment | unit, filters | current | pure | fast | keep fast | Covers Skroutz microwave alias enrichment. |
| `src/product_factory/tests/test_csv_writer.py` | Render CSV/HTML assembly | stage, render | current | pure | fast | keep stage | Covers header order and deterministic description/section HTML assembly. |
| `src/product_factory/tests/test_deterministic_fields.py` | Deterministic product fields | unit, prepare | current | pure | fast | keep fast | Protects name, meta title, SEO keyword, and differentiator rules. |
| `src/product_factory/tests/test_deterministic_fields_ice_cream_maker.py` | Deterministic product fields | unit, prepare | current | pure | fast | keep fast | Covers ice cream maker family output rules. |
| `src/product_factory/tests/test_dev_start.py` | Dev launcher contract | contract | current | pure | fast | keep contract | Dry-run only; no server process. |
| `src/product_factory/tests/test_eprel.py` | EPREL enrichment | stage, source_acquisition | current | pure | fast | keep stage | Uses local stubs and parser fixtures, not live EPREL. |
| `src/product_factory/tests/test_execution_models.py` | Service execution models | contract, prepare, render, publish | current | tmp_path/filesystem | fast | keep contract | Covers current prepare/render artifact payload contracts. |
| `src/product_factory/tests/test_fetcher_gallery_download.py` | Image acquisition persistence | stage, source_acquisition | current | tmp_path/filesystem | fast | keep stage | Uses stubbed binary fetches and local image conversion. |
| `src/product_factory/tests/test_filter_review_service.py` | Product filter review API/service | contract, stage, filters, filter_review | current | tmp_path/filesystem | fast | keep stage | Covers review generation, save, approval, and metadata paths with local artifacts. |
| `src/product_factory/tests/test_filters_manager_api.py` | Global filters API | contract, filters | current | tmp_path/filesystem | fast | keep contract | Covers filter manager request/response shape and manual override persistence. |
| `src/product_factory/tests/test_job_runner.py` | Job runner lifecycle | job_lifecycle | current | tmp_path/filesystem, subprocess for selected tests | fast to slow | keep stage; mark integration/slow selected tests | Fast fake-service lifecycle tests stay in default; child process tests move out. |
| `src/product_factory/tests/test_job_store.py` | Job store lifecycle | unit, job_lifecycle | current | tmp_path/filesystem | fast | keep fast | Covers persisted statuses including failed, cancelled, and killed. |
| `src/product_factory/tests/test_job_worker_cli.py` | Worker CLI | contract, job_lifecycle | current | tmp_path/filesystem, subprocess for one test | fast to moderate | keep contract; mark integration/slow selected test | Direct worker contract tests stay fast; module subprocess smoke test is quarantined. |
| `src/product_factory/tests/test_llm_contract.py` | Authoring artifact contracts | unit, contract, authoring | current | pure | fast | keep contract | Covers intro and SEO output shape without OpenAI. |
| `src/product_factory/tests/test_llm_stage_execution.py` | Authoring stage | stage, authoring | current | tmp_path/filesystem | fast | keep stage | Uses fake OpenAI client/resolvers and validates retry/artifact behavior. |
| `src/product_factory/tests/test_manufacturer_enrichment.py` | Manufacturer enrichment | stage, source_acquisition | current | pure | fast | keep stage | Covers local PDF/HTML enrichment candidates without network. |
| `src/product_factory/tests/test_manufacturer_enrichment_tefal.py` | Manufacturer enrichment | stage, source_acquisition | current | tmp_path/filesystem | fast | keep stage | Uses saved Tefal fixture. |
| `src/product_factory/tests/test_metadata.py` | Run metadata | contract | current | tmp_path/filesystem | fast | keep contract | Covers metadata report and artifact serialization contracts. |
| `src/product_factory/tests/test_normalize.py` | Text normalization | unit | current | pure | fast | keep fast | Pure normalization helper tests. |
| `src/product_factory/tests/test_parser_product_manufacturer.py` | Manufacturer parser | stage, source_acquisition | current | pure | fast | keep stage | Covers supported manufacturer parsing using local HTML. |
| `src/product_factory/tests/test_prepare_provider_resolution.py` | Prepare provider resolution | stage, prepare, source_acquisition | current | pure | fast | keep stage | Covers provider identity, scope, and error mapping. |
| `src/product_factory/tests/test_prepare_result_assembly_module.py` | Prepare assembly | stage, prepare, filters, authoring | current | tmp_path/filesystem | fast | keep stage | Covers prepared normalized/report/LLM artifact assembly. |
| `src/product_factory/tests/test_prepare_scrape_persistence.py` | Prepare artifact persistence | stage, prepare, authoring | current | tmp_path/filesystem | fast | keep stage | Covers scrape/LLM file layout and stale cleanup. |
| `src/product_factory/tests/test_prepare_section_assets.py` | Section asset resolution | stage, prepare, source_acquisition | current | tmp_path/filesystem | fast | keep stage | Uses fake fetchers and local section inputs. |
| `src/product_factory/tests/test_prepare_section_assets_module.py` | Section asset module | stage, prepare, source_acquisition | current | tmp_path/filesystem | fast | keep stage | Covers deterministic section asset selection. |
| `src/product_factory/tests/test_prepare_skroutz_section_assets_module.py` | Skroutz section assets | stage, prepare, source_acquisition | current | tmp_path/filesystem | fast | keep stage | Covers local rendered-section fixtures and section image mapping. |
| `src/product_factory/tests/test_prepare_stage_result_assembly.py` | Prepare stage seams | stage, prepare | current | tmp_path/filesystem | fast | keep stage | Covers prepare stage seam inputs and persistence output routing. |
| `src/product_factory/tests/test_prepare_taxonomy_enrichment.py` | Taxonomy enrichment | stage, prepare, filters | current | pure | fast | keep stage | Covers taxonomy enrichment behavior with local data. |
| `src/product_factory/tests/test_prepare_taxonomy_enrichment_module.py` | Taxonomy enrichment module | stage, prepare, filters | current | pure | fast | keep stage | Covers enrichment contract and diagnostics. |
| `src/product_factory/tests/test_presentation_sections.py` | Render section normalization | unit, render | current | pure | fast | keep fast | Covers deterministic section cleanup, metrics, and wording preservation. |
| `src/product_factory/tests/test_price.py` | Price parsing | unit | current | pure | fast | keep fast | Pure Euro price parsing. |
| `src/product_factory/tests/test_product_parser.py` | Product parser | stage, source_acquisition | current | pure | fast | keep stage | Covers source parser output shape and asset extraction. |
| `src/product_factory/tests/test_provider_selection.py` | Provider/source selection | stage, prepare, source_acquisition | current | tmp_path/filesystem | fast | keep stage | Uses fixtures and fake live fetchers; no network. |
| `src/product_factory/tests/test_schema_matcher.py` | Characteristics schema matcher | unit, filters | current | pure | fast | keep fast | Protects template selection boundaries. |
| `src/product_factory/tests/test_schema_matcher_compiled_library_regressions.py` | Schema matcher regressions | unit, filters | current | pure | fast | keep fast | Protects compiled schema-library family constraints. |
| `src/product_factory/tests/test_services.py` | Service contracts | contract, stage, prepare, render, publish | current | tmp_path/filesystem | fast | keep contract | Covers workflow-only service surface and service error mapping. |
| `src/product_factory/tests/test_settings_authoring.py` | Settings and authoring API | contract, authoring | current | tmp_path/filesystem | fast | keep contract | Covers `/api/settings` and `/api/authoring` using local files. |
| `src/product_factory/tests/test_skroutz_built_in_family_override.py` | Skroutz taxonomy override | stage, source_acquisition, filters | current | pure | fast | keep stage | Covers built-in oven family override. |
| `src/product_factory/tests/test_skroutz_integration.py` | Skroutz parser/render workflow | stage, source_acquisition, render | current | tmp_path/filesystem | fast to slow | keep stage; mark e2e/slow selected test | Parser/field tests stay fast; full fixture workflow is e2e. |
| `src/product_factory/tests/test_skroutz_robot_vacuum.py` | Skroutz taxonomy | stage, source_acquisition, filters | current | pure | fast | keep stage | Covers robot vacuum category resolution. |
| `src/product_factory/tests/test_skroutz_sections.py` | Skroutz section parsing/render | stage, source_acquisition, prepare, render | current | tmp_path/filesystem, fake playwright | fast to slow | keep stage; mark e2e/slow selected test | Local section parsing stays fast; one prepare/render fixture workflow is e2e. |
| `src/product_factory/tests/test_skroutz_taxonomy.py` | Skroutz taxonomy | stage, source_acquisition, filters | current | pure | fast to slow | keep stage; mark slow selected tests | Representative loops are valuable but dominate suite time. |
| `src/product_factory/tests/test_skroutz_taxonomy_microwave.py` | Skroutz taxonomy | stage, source_acquisition, filters | current | pure | fast | keep stage | Focused microwave taxonomy regression. |
| `src/product_factory/tests/test_source_acquisition_stage.py` | Source acquisition stage | stage, source_acquisition | current | tmp_path/filesystem | fast | keep stage | Covers acquisition-owned output and gallery warning semantics. |
| `src/product_factory/tests/test_sync_filter_map.py` | Filter map sync | unit, stage, filters | current | tmp_path/filesystem | fast | keep stage | Covers stable IDs and manual override merge. |
| `src/product_factory/tests/test_taxonomy.py` | Taxonomy resolution | unit, filters | current | pure | fast | keep fast | Covers taxonomy serialization and focused rules. |
| `src/product_factory/tests/test_utils_support_paths.py` | Support path contracts | unit, contract, filters | current | pure | fast | keep contract | Covers resources layout and object-style filter map contract. |
| `src/product_factory/tests/test_validator.py` | Candidate validation | unit, render | current | tmp_path/filesystem | fast | keep fast | Covers validation errors and baseline comparison. |
| `src/product_factory/tests/test_workflow.py` | Current workflow services | contract, stage, prepare, render, publish, authoring | current | tmp_path/filesystem, fake subprocess | fast | keep stage | Covers workflow CLI, render retry, render assembly, and publish handoff with stubs. |

## Targeted Quarantine Markers

| Test path | Added markers | Rationale |
| --- | --- | --- |
| `src/product_factory/tests/test_skroutz_taxonomy.py::test_taxonomy_regression_fixture_resolves_expected_categories` | `slow` | 164-case taxonomy regression took about 45 seconds; useful but not a default Codex check. |
| `src/product_factory/tests/test_skroutz_taxonomy.py::test_representative_taxonomy_html_fixtures_cover_supported_skroutz_combos` | `slow` | Representative fixture loop took about 9 seconds. |
| `src/product_factory/tests/test_skroutz_integration.py::test_prepare_and_render_workflow_with_skroutz_fixtures` | `integration`, `slow`, `e2e` | Runs full prepare and render workflow over multiple fixture products. |
| `src/product_factory/tests/test_skroutz_sections.py::test_143481_rendered_description_preserves_locked_wrappers` | `integration`, `slow`, `e2e` | Runs prepare and render workflow for a rendered-section fixture. |
| `src/product_factory/tests/test_job_runner.py::test_subprocess_runner_launches_child_and_records_process_metadata` | `integration`, `slow` | Launches a child process. |
| `src/product_factory/tests/test_job_runner.py::test_nonzero_child_exit_marks_failed_when_no_terminal_status_exists` | `integration`, `slow` | Launches a child process. |
| `src/product_factory/tests/test_job_runner.py::test_parent_preserves_terminal_status_written_by_child_on_nonzero_exit` | `integration`, `slow` | Launches a child process. |
| `src/product_factory/tests/test_job_runner.py::test_stop_queued_job_in_runner_queue_marks_cancelled_and_never_launches` | `integration`, `slow` | Exercises runner queue timing with a sleeping child command. |
| `src/product_factory/tests/test_job_runner.py::test_stop_running_child_graceful_terminate_marks_cancelled` | `integration`, `slow` | Exercises process termination. |
| `src/product_factory/tests/test_job_runner.py::test_stop_running_child_force_kills_after_timeout` | `integration`, `slow` | Exercises forced kill timeout behavior. |
| `src/product_factory/tests/test_job_runner.py::test_same_model_jobs_do_not_run_concurrently_with_multiple_workers` | `integration`, `slow` | Exercises multi-worker subprocess scheduling. |
| `src/product_factory/tests/test_job_worker_cli.py::test_worker_cli_missing_job_returns_nonzero` | `integration`, `slow` | Runs the worker module in a subprocess. |

No active tests were marked `external` or `legacy`. No tests were deleted.
