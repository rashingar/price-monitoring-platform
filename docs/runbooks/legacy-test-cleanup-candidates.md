# Legacy Test Cleanup Candidates

This list tracks tests and folders that are preserved but should be reviewed
before they are trusted as part of the default fast suite. Do not delete these
casually; mark or rewrite first unless a file is clearly generated, duplicate,
or impossible after the monorepo/rename changes.

| Path | Why it is a candidate | Recommended action | Blocks fast suite |
| --- | --- | --- | --- |
| `apps/product-factory-api/tools/tests/test_opencart_upload_images.py` | Tool-level OpenCart image upload coverage sits outside the active Product Factory pytest root and may require real OpenCart/operator setup depending on how it is invoked. | Keep available as external tool coverage; mark `external` if it is brought into an active pytest config. | No |
| `apps/product-factory-api/tools/schema_registry/tests/` | Schema registry tool tests are outside the active Product Factory runtime pytest root. They may still be useful tool coverage, but they are not part of the current fast backend suite. | Keep; decide whether to add a separate tool test script or document as diagnostics-only. | No |
| `apps/product-factory-api/src/pipeline/tests/test_skroutz_taxonomy.py::test_taxonomy_regression_fixture_resolves_expected_categories` | Valuable taxonomy regression loop over many captured cases, but intentionally slower than routine Codex checks. | Keep marked `slow`; run explicitly for taxonomy changes. | No |
| `apps/product-factory-api/src/pipeline/tests/test_skroutz_taxonomy.py::test_representative_taxonomy_html_fixtures_cover_supported_skroutz_combos` | Uses representative captured HTML fixture coverage and is slower than routine fast checks. | Keep marked `slow`; run explicitly for parser/taxonomy fixture work. | No |
| `apps/product-factory-api/src/pipeline/tests/test_skroutz_integration.py::test_prepare_and_render_workflow_with_skroutz_fixtures` | Full fixture workflow is current behavior, but it is broader than a deterministic fast check. | Keep marked `integration`, `slow`, and `e2e`; run for broad workflow changes. | No |
| `apps/product-factory-api/src/pipeline/tests/test_skroutz_sections.py::test_143481_rendered_description_preserves_locked_wrappers` | Full prepare/render-style section fixture workflow is useful but intentionally outside fast default. | Keep marked `integration`, `slow`, and `e2e`; run for section rendering changes. | No |
| `apps/ecommerce-api/tests/test_price_monitoring_fetch_execution.py` | Local execution scheduler and worker coverage is current, but it exercises multi-module execution state and worker timing, so failures can be more diagnostic than unit-like. | Keep as `integration`; split out any future genuinely slow worker/process cases with test-level `slow` markers. | No |
| `apps/ecommerce-api/tests/test_source_capture_unified.py` | Uses local fakes for browser/XHR capture and does not hit live pages, but it is close to browser-marketplace behavior. | Keep as `integration`; mark future real-browser or live marketplace cases `external` and likely `slow`. | No |
| `apps/ecommerce-api/tests/test_source_url_agent.py` | Covers source URL discovery/scoring with local fixtures and embedded HTML, but it is close to marketplace-discovery behavior. | Keep as `integration`; mark future live search/browser/network cases `external`. | No |

No active tests were deleted during the test-strategy normalization. No active
Ecommerce rename-era tests were found that are impossible after the landed
rename; tests mentioning legacy payload fields currently assert supported
backward-compatible behavior or old behavior removal.
