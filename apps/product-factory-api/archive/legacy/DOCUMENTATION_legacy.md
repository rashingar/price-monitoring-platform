# Product-Agent Engineering Log

## Current milestone
Structured debug reporting for category-scoped schema matching is now implemented. Schema selection results now expose resolved category, pool shape, selected template, fail reason, gate failures, discriminator hits/misses, and overlap scores through the existing report artifacts.

## 2026-04-03 - Fix Electronet EPREL asset extraction and preserve legal-note presentation blocks

Goal:
- capture the actual EPREL energy-label asset from Electronet product modals instead of the small arrow thumbnail
- preserve source footnotes and regulation blocks exactly enough for deterministic rendering, including small italic styling for `*` notes and untitled legal appendix content
- unblock live Electronet TV runs that need direct size-bucket taxonomy resolution

Files changed:
- `DOCUMENTATION.md`
- `scraper/pipeline/html_builders.py`
- `scraper/pipeline/parser_product_electronet.py`
- `scraper/pipeline/taxonomy.py`
- `scraper/pipeline/tests/test_csv_writer.py`
- `scraper/pipeline/tests/test_product_parser.py`
- `scraper/pipeline/tests/test_taxonomy.py`

What changed:
- Electronet asset extraction now prefers `.eprel-modal-trigger` metadata and resolves `data-label-url` / `data-pdf-url` against `https://eprel.ec.europa.eu`, so the scraped source stores the actual EPREL energy-label and fiche URLs instead of the on-page arrow asset
- deterministic presentation rendering now preserves small-font footnotes and star-prefixed notes as small italic copy while keeping their source wording intact
- deterministic description rendering now appends untitled appendix/legal blocks that appear after the normal Electronet presentation sections, so bottom-of-page regulation text and its paired image remain in the rendered description
- taxonomy resolution now applies a direct television size-bucket heuristic for Electronet TV runs, allowing a 50-inch model to resolve to the existing `33''-50''` branch and CTA without relying on a provider-specific hardcoded rule
- added focused regression coverage for EPREL modal asset extraction, preserved legal-note rendering, and TV size-bucket taxonomy selection

Commands run:
- `python -m pytest -q pipeline/tests/test_product_parser.py -k "video_block or eprel_modal_assets"`
- `python -m pytest -q pipeline/tests/test_csv_writer.py -k "video_embed_and_list_markup or split_description_preserves_small_footnotes_and_regulation_appendix"`
- `python -m pytest -q pipeline/tests/test_taxonomy.py pipeline/tests/test_skroutz_taxonomy.py -q`
- `python -m pipeline.workflow prepare --model 000001 --url "https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-samsung-qe50qn80f-50-smart-4k-mini-led-ai" --photos 3 --sections 35 --skroutz-status 1 --boxnow 0 --price 699`
- `python -m pipeline.workflow render --model 000001`

Validation:
- live scrape output now records `energy_label_asset_url = https://eprel.ec.europa.eu/labels/electronicdisplays/Label_2204959.png`
- live scrape output now records `product_sheet_asset_url = https://eprel.ec.europa.eu/fiches/electronicdisplays/Fiche_2204959_EL.pdf`
- live render completed successfully for model `000001`
- `work/000001/candidate/000001.validation.json` reported `ok: true`
- OpenCart publish completed successfully with `publish_status: success` at stage `csv_import`

Risks, blockers, or skipped items:
- the appended regulation QR image is still rendered from the source URL rather than downloaded into a repo-managed asset path
- note preservation is intentionally scoped to the current Electronet legal-note shapes; if another provider uses different markers or richer inline formatting, the renderer will need a separate extension

## 2026-04-03 - Insert Electronet EPREL label into gallery slot two and keep weak presentation sections in render output

Goal:
- make the extracted EPREL label participate in the actual gallery/download/upload pipeline instead of existing only as metadata
- keep Electronet section-to-Besco indexing aligned when one deterministic section is weak but still operator-usable
- render the appendix regulation QR as a small responsive image on the same row as its text

Files changed:
- `DOCUMENTATION.md`
- `scraper/pipeline/html_builders.py`
- `scraper/pipeline/prepare_stage.py`
- `scraper/pipeline/services/render_execution.py`
- `scraper/pipeline/tests/test_csv_writer.py`
- `scraper/pipeline/tests/test_prepare_section_assets.py`
- `scraper/pipeline/tests/test_workflow.py`

What changed:
- prepare-stage gallery assembly now injects the EPREL energy-label asset immediately after the primary product image, so it downloads as `{model}-2.jpg` and flows into the normal OpenCart gallery upload
- render-stage section resolution now backfills requested sections with weak deterministic sections before reducing the section count, preserving section image continuity for Electronet products like the live TV run where one section was previously dropped
- appendix rendering now constrains the regulation QR image to a responsive `min(75px, 18vw)` width cap with `max-width: 75px`, keeping it visually small while remaining in the same row layout as the appendix text

Commands run:
- `python -m pytest -q pipeline/tests/test_prepare_section_assets.py -k "injects_energy_label_into_gallery_slot_two"`
- `python -m pytest -q pipeline/tests/test_csv_writer.py -k "split_description_preserves_small_footnotes_and_regulation_appendix"`
- `python -m pytest -q pipeline/tests/test_workflow.py -k "backfills_with_weak_sections_before_reducing"`
- `python -m pipeline.workflow prepare --model 000001 --url "https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-samsung-qe50qn80f-50-smart-4k-mini-led-ai" --photos 3 --sections 35 --skroutz-status 1 --boxnow 0 --price 699`
- `python -m pipeline.workflow render --model 000001`

Validation:
- live gallery output now includes `work/000001/scrape/gallery/000001-2.jpg` as the injected EPREL label image
- live OpenCart upload plan now publishes `catalog/01_main/000001/000001-2.jpg` as part of the product gallery
- live rendered description now includes `Object Tracking Sound Lite` with `besco22.jpg`
- live validation remains `ok: true` and the earlier `requested_sections_reduced:34` warning is gone

Risks, blockers, or skipped items:
- the current gallery behavior keeps the operator-requested gallery count fixed, so inserting the EPREL label into slot two pushes one source gallery image out when `photos` is capped
- the appendix QR still renders from the source URL rather than a repo-managed downloaded asset

## 2026-04-03 - Keep requested source-photo count when injecting the EPREL label and make appendix QR truly inline

Goal:
- preserve the operator-requested source gallery count while still inserting the EPREL label into gallery slot two
- ensure the appendix regulation QR renders as a small inline element instead of a separate side block

Files changed:
- `DOCUMENTATION.md`
- `scraper/pipeline/html_builders.py`
- `scraper/pipeline/prepare_stage.py`
- `scraper/pipeline/tests/test_csv_writer.py`
- `scraper/pipeline/tests/test_prepare_section_assets.py`

What changed:
- prepare-stage gallery download count now adds the EPREL label on top of the requested `photos` count, so a `photos: 3` run with a label produces four gallery files: main image, EPREL label, and the three requested source photos in total
- appendix rendering now inserts the QR image inline inside the appendix text container with a smaller responsive cap of `min(60px, 14vw)` and `max-width: 60px`
- reran the live `000001` product after the prepare artifacts were complete so the published CSV and OpenCart import now reference all four gallery files correctly

Commands run:
- `python -m pytest -q pipeline/tests/test_prepare_section_assets.py -k "energy_label"`
- `python -m pytest -q pipeline/tests/test_csv_writer.py -k "split_description_preserves_small_footnotes_and_regulation_appendix"`
- `python -m pipeline.workflow prepare --model 000001 --url "https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-samsung-qe50qn80f-50-smart-4k-mini-led-ai" --photos 3 --sections 35 --skroutz-status 1 --boxnow 0 --price 699`
- `python -m pipeline.workflow render --model 000001`
- `python -m pipeline.workflow render --model 000001`

Validation:
- live gallery output now includes `work/000001/scrape/gallery/000001-1.jpg` through `work/000001/scrape/gallery/000001-4.jpg`
- live published CSV now references `catalog/01_main/000001/000001-2.jpg:::catalog/01_main/000001/000001-3.jpg:::catalog/01_main/000001/000001-4.jpg` in `additional_image`
- live OpenCart upload plan reports `gallery_count: 4`
- live appendix QR now renders inline with `display:inline-block; vertical-align:middle; width:min(60px, 14vw); max-width:60px`

Risks, blockers, or skipped items:
- one rerun was required because `render` was started before the updated `prepare` artifacts had finished writing; the final successful rerun used the completed scrape artifacts and no runtime code change was needed for that
- the appendix QR still uses the source URL rather than a repo-managed downloaded asset

## 2026-04-02 - Preserve Electronet presentation lists, video embeds, and Besco GIF assets

Goal:
- improve Electronet presentation fidelity so deterministic output preserves source list formatting and the leading embedded video block instead of flattening them away
- preserve animated Besco assets as `.gif` when Electronet serves them that way instead of converting them to `.jpg`

Files changed:
- `DOCUMENTATION.md`
- `scraper/pipeline/fetcher.py`
- `scraper/pipeline/html_builders.py`
- `scraper/pipeline/mapping.py`
- `scraper/pipeline/parser_product_electronet.py`
- `scraper/pipeline/tests/test_csv_writer.py`
- `scraper/pipeline/tests/test_fetcher_gallery_download.py`
- `scraper/pipeline/tests/test_product_parser.py`

What changed:
- Electronet presentation-source extraction now keeps `.ck-text.whole` blocks in the captured HTML so leading source video blocks survive into downstream rendering, while the reported presentation-section count still reflects only `.ck-text.inline` sections
- presentation block extraction now preserves sanitized source body HTML for paragraph and list content
- deterministic description rendering now prefers preserved source body HTML, so source bullet lists remain bullet lists in the final description instead of being flattened into a single paragraph
- deterministic description rendering now inserts preserved source video/embed blocks ahead of the rendered section stack
- Besco downloads now preserve `.gif` assets as `.gif`; other non-jpg formats still follow the existing conversion path

Commands run:
- `python -m pytest -q pipeline/tests/test_csv_writer.py -k "presentation_blocks_extract or preserves_video_embed"`
- `python -m pytest -q pipeline/tests/test_product_parser.py -k "presentation_source_html or extracts_visible_code"`
- `python -m pytest -q pipeline/tests/test_fetcher_gallery_download.py`

Validation:
- focused HTML builder tests now cover preserved list markup, preserved video embeds, and non-jpg Besco filename passthrough
- focused parser test verifies the leading Electronet video block is retained in `presentation_source_html` while inline section counting remains stable
- focused fetcher tests verify Besco `.gif` assets are preserved without conversion

Risks, blockers, or skipped items:
- preserved source body HTML is intentionally limited to safe presentation tags (`p`, `ul`, `ol`, `li`, `br`, emphasis tags`) and preserved media tags (`video`, `source`, `iframe`) rather than arbitrary source markup

## 2026-04-02 - Fix Electronet presentation extraction for list-based sections

Goal:
- fix the actual Electronet extraction bug on product pages that still expose the expected four presentation sections but render three of them as bullet lists instead of paragraph tags
- keep compatibility with the newer site layout where a video block may appear before the image-and-text section blocks

Files changed:
- `DOCUMENTATION.md`
- `scraper/pipeline/html_builders.py`
- `scraper/pipeline/tests/test_csv_writer.py`

What changed:
- updated container-based presentation extraction so Electronet `.ck-text.inline` blocks now treat `<li>` items as valid deterministic body text in addition to `<p>` tags
- kept the extractor scoped to `.ck-text.inline` blocks, so the leading video-only `.ck-text.whole` block does not displace the actual four image-and-text sections
- added regression coverage for the live page shape:
  - one leading video block
  - four `.ck-text.inline` sections
  - three sections using list-only copy

Commands run:
- `python -m pytest -q pipeline/tests/test_csv_writer.py -k "presentation_blocks_extract"`

Validation:
- focused presentation-block tests cover paragraph-based sections, alternating left/right banner layouts, and the current Electronet list-based section layout

Risks, blockers, or skipped items:
- this change does not attempt to render the leading video block as a product section; it preserves the current deterministic section contract and fixes the dropped text/image sections only

## 2026-04-02 - Allow render to reduce deterministic presentation sections when source exposes fewer than requested

Goal:
- unblock live workflow runs where Electronet or other supported sources expose fewer usable deterministic presentation sections than the operator requested
- keep the fail-fast behavior only for cases with zero usable deterministic sections

Files changed:
- `DOCUMENTATION.md`
- `scraper/pipeline/services/render_execution.py`
- `scraper/pipeline/tests/test_workflow.py`

What changed:
- removed the fatal render guard that raised when more than one normalized presentation section was missing
- kept render failure behavior unchanged when no presentation source sections exist or none are usable
- changed warning emission so any positive missing count is surfaced as `presentation_sections_missing:{n}`
- added a workflow regression proving a `sections=4` request still renders successfully when only one deterministic section is usable

Commands run:
- `python -m pytest -q scraper/pipeline/tests/test_workflow.py -k "multiple_requested_sections_are_missing or one_requested_section_is_missing"`

Validation:
- the focused workflow regression covers the exact reduction path from four requested deterministic sections down to one usable section

Risks, blockers, or skipped items:
- render now degrades more permissively for section-short products by design; downstream consumers should rely on validation warnings rather than assuming requested section count always equals rendered section count

## 2026-04-02 - Fix OpenCart publish wrapper module resolution under WSL

Goal:
- unblock the repo-native OpenCart publish phase after a successful render
- fix the failure generically in the wrapper layer instead of patching individual Python scripts

Files changed:
- `DOCUMENTATION.md`
- `tools/run_opencart_image_upload.sh`
- `tools/run_opencart_import_csv.sh`

What changed:
- exported `PYTHONPATH` from both OpenCart Bash wrappers so repo-root imports such as `from tools.opencart_config ...` resolve correctly when the scripts are executed by path under Bash/WSL
- normalized OpenCart admin-path inputs inside both Python publish entrypoints so MSYS/Git Bash path rewriting like `C:/Program Files/Git/ipadmin/index.php` is converted back to `/ipadmin/index.php` before login URLs are built
- kept the existing wrapper contract, argument shape, and publish flow unchanged

Why this was needed:
- the publish phase invoked `tools/opencart_upload_images.py` directly from Bash
- under WSL that process did not have the repo root on `sys.path`
- the upload stage failed immediately with `ModuleNotFoundError: No module named 'tools'`
- after fixing module resolution, the next live failure showed `/ipadmin/index.php` being rewritten into a Windows path and appended to the storefront base URL, producing a 404 admin login route

Commands run:
- `python -m pipeline.workflow prepare --model 000015 --url "https://www.skroutz.gr/s/60276903/tcl-smart-tileorasi-115-4k-uhd-mini-led-c7k-hdr-2025-115c7k.html" --photos 7 --sections 7 --skroutz-status 1 --boxnow 0 --price 9999`
- `python -m pipeline.workflow render --model 000015`
- `python -m pipeline.workflow render --model 000015`

Validation:
- render completed successfully for model `000015`
- candidate validation reported `Validation ok: True`
- the initial publish failure cause was isolated to wrapper module resolution at `image_upload`
- the second publish failure cause was isolated to admin login URL construction after shell path rewriting of `OPENCART_ADMIN_PATH`

Risks, blockers, or skipped items:
- OpenCart publish still needs a rerun after this wrapper fix to confirm the next stage outcome in the live admin environment

## 2026-04-02 - Fix stale compiled-schema id assertion after Electronet label-set registry merge

Goal:
- unblock the local `main` merge of `feat/electronet-label-set-registry`
- keep the branch behavior intact by fixing a stale test assertion rather than changing runtime schema selection

Files changed:
- `DOCUMENTATION.md`
- `scraper/pipeline/tests/test_characteristics_pipeline.py`

What changed:
- replaced the hardcoded Skroutz soundbar schema id assertion with the same compiled-library lookup helper already used by the neighboring characteristics tests
- kept the actual behavior under test unchanged:
  - `sound_bars.json` remains the preferred schema source file
  - the selected template remains `schema_library_with_custom_overrides`
  - `skroutz_soundbar_v1` remains the custom overlay id

Why this was needed:
- the Electronet label-set registry branch regenerated the compiled schema library
- the soundbar schema id changed in `resources/schemas/electronet_schema_library.json`
- the old test still asserted a stale hardcoded `sha1:...` value and was the only remaining scraper-suite failure after merging the branch locally

Commands run:
- `python -m pytest -q scraper/pipeline/tests/test_characteristics_pipeline.py -k soundbar`
- `python -m pytest -q` from `scraper/`
- `python -m pytest -q tools/schema_registry/tests`

Validation:
- the soundbar characteristics regression now resolves against the current compiled schema library
- the full scraper suite passes after the test fix
- the schema-registry tool tests pass from repo root

## 2026-04-02 - Regenerate stale schema index artifact

Goal:
- bring the checked-in schema index back into sync with the current compiled Electronet library and index contract
- keep the fix limited to the stale derived artifact identified in merge review
- avoid any matcher, compiler-policy, or coverage-report behavior changes

Files changed:
- `DOCUMENTATION.md`
- `resources/schemas/schema_index.csv`

What changed:
- regenerated `resources/schemas/schema_index.csv` from the current compiled library using the existing schema-index tool
- confirmed the checked-in compiled library did not change during regeneration
- updated stale `subcategory_match_policy` rows in the index so the mixed air-conditioner and fan families now match the current compiled metadata

Commands run:
- `python -m tools.schema_registry.build_electronet_schema_library`
- `python -m tools.schema_registry.build_schema_index`
- `python -m pytest tools/schema_registry/tests/test_build_schema_index.py tools/schema_registry/tests/test_build_electronet_schema_library.py -q`

Validation:
- regenerated schema index diff is limited to stale `subcategory_match_policy` values in mixed-family rows
- focused schema-index and compiler tests passed
- no matcher/runtime/tool logic changed in this blocker-fix commit

Risks, blockers, or skipped items:
- no additional repo-state guard was added in this commit to keep the pre-merge fix minimal

## 2026-04-02 - Disambiguate ambiguous coverage labels only when needed

Goal:
- keep the Electronet template coverage report compact while removing any chance of misleading duplicate-looking labels across taxonomy branches
- make label disambiguation conditional on the actual rendered coverage rows instead of precomputing display labels during taxonomy load
- keep matcher, compiler, and runtime workflow behavior unchanged

Files changed:
- `DOCUMENTATION.md`
- `tools/schema_registry/refresh_template_coverage.py`
- `tools/schema_registry/tests/test_refresh_template_coverage.py`

What changed:
- moved coverage-label rendering into a focused helper that counts collisions across the expected rows being rendered
- kept unique labels compact and unchanged
- kept colliding labels in the compact contextual format `label [parent > leaf]`
- stopped storing pre-disambiguated labels in `ExpectedCategory.key`; coverage rows now derive their visible label at render time from taxonomy context
- expanded focused tests to cover:
  - unique labels staying compact
  - Android/iOS-style branch collisions disambiguating deterministically
  - non-colliding rows not being expanded when some labels in the report do collide
- regenerated the live Electronet coverage report; the file content stayed stable because the already-rendered ambiguous branch labels still resolve to the same visible strings

Commands run:
- `python -m pytest tools/schema_registry/tests/test_refresh_template_coverage.py -q`
- `python -m tools.schema_registry.refresh_template_coverage`

Validation:
- focused coverage tests passed: `5 passed`
- coverage report regeneration completed successfully
- no matcher, compiler, or runtime files changed

Risks, blockers, or skipped items:
- this commit intentionally keeps disambiguation context at `parent > leaf`; if a future taxonomy ever collides within the same parent/leaf branch, the coverage helper would need a narrower context format

## 2026-04-02 - Remove compiled-library state reuse from Electronet schema compilation

Goal:
- make the Electronet schema compiler source-of-truth pure so compiled schema structure never depends on prior generated library state
- ensure compiled `sections` come only from authored templates and `schema_id` is derived deterministically from current authored inputs

Files edited:
- `DOCUMENTATION.md`
- `docs/specs/2026-04-01-category-scoped-schema-matching-contract.md`
- `tools/schema_registry/README.md`
- `tools/schema_registry/build_electronet_schema_library.py`
- `tools/schema_registry/tests/test_build_electronet_schema_library.py`

What changed:
- removed the builder path that loaded prior compiled library entries to recover legacy `sections` or `schema_id`
- deleted the legacy helper functions that matched compiled entries by source filename and reused prior compatibility sections
- added pure helpers so compiled `sections` are emitted directly from authored template sections with authored section and label order preserved
- `schema_id` is now always derived from a deterministic hash of current authored structure plus resolved taxonomy binding, not recovered from an existing compiled artifact
- kept the existing category binding and matcher metadata generation behavior intact
- added a regression test proving:
  - `build_library_payload(...)` returns the same payload whether or not an existing compiled library path is provided
  - emitted `sections` come from the authored template, not a stale compiled artifact
  - changing authored template structure changes `schema_id`
- tightened schema-registry docs so they state explicitly that compiled structure and ids are derived from current authored templates rather than prior compiled outputs

Commands run:
- `python -m pytest -q tools/schema_registry/tests/test_build_electronet_schema_library.py`

Validation:
- targeted Electronet schema builder tests passed after the refactor

Risks, blockers, or skipped items:
- `existing_library_path` remains in `build_library_payload(...)` for call-site compatibility, but it is now explicitly ignored for compiled schema semantics

## 2026-04-01 - Finalize category-scoped schema matching docs to match landed behavior

Goal:
- align the branch docs with the implementation that actually shipped
- document the compiled runtime metadata shape, landed `match_mode` values, hard-gating rules, fail-closed semantics, and runtime debug inspection path
- remove stale wording that still implied planned-state names or allowed global schema similarity fallback

Files edited:
- `DOCUMENTATION.md`
- `docs/specs/2026-04-01-category-scoped-schema-matching-contract.md`
- `tools/schema_registry/README.md`

What changed:
- the category-scoped contract spec is now marked `implemented` instead of `planned`
- stale planned-state matcher names such as `direct_only` / `sibling_scored` were replaced with the landed values:
  - `direct_single`
  - `category_pool`
  - `manual_only`
- the docs now describe the landed matcher flow:
  - category-path scoped candidate pool
  - same-family leaf-only fallback only when needed
  - active-template filtering
  - hard gates before sibling scoring
  - bounded intra-category scoring only
  - fail-closed `no_safe_template_match`
- the docs now spell out where to inspect runtime matcher diagnostics:
  - `work/{model}/scrape/{model}.normalized.json`
  - `work/{model}/scrape/{model}.report.json`

Validation:
- docs updated to match the current implementation and regression coverage
- stale wording implying global schema fallback or old matcher mode names was removed from the schema-matching spec and schema-registry runbook

## 2026-04-01 - Add focused regression coverage for category-scoped schema safety

Goal:
- lock the new category-scoped schema safety behavior so correct category resolution cannot silently drift to the wrong characteristics template in future changes
- cover the key direct-single template families from the compiled Electronet schema library
- keep the coverage deterministic, cheap, and synthetic where runtime fixture extraction is sufficient

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/tests/test_schema_matcher_compiled_library_regressions.py`

What changed:
- added compiled-library matcher regressions for these direct-single template families:
  - `tileoraseis`
  - `koyzines`
  - `plyntiria_piaton`
  - `entoixizomena_plyntiria_piaton`
  - `plyntiria_rouxwn`
  - `entoixizomena_plyntiria_royxon`
  - `entoixizomena_psygeia`
- each regression test drives `SchemaMatcher` with deterministic synthetic extracted specs derived from the compiled schema metadata and asserts that the resolved family selects its own template
- added compiled-library negative-path regressions proving that:
  - generic washing-machine-family labels cannot escape the resolved washing-machine category
  - kitchen/cooker-shaped extracted specs cannot override a washing-machine category binding
- existing bounded sibling behavior remains pinned by:
  - `scraper/pipeline/tests/test_schema_matcher.py` synthetic `category_pool` matcher tests
  - `tools/schema_registry/tests/test_build_electronet_schema_library.py` compiler-side `category_pool` metadata test

Commands run:
- `python -m pytest scraper/pipeline/tests/test_schema_matcher_compiled_library_regressions.py`
- `python -m pytest tools/schema_registry/tests/test_build_electronet_schema_library.py scraper/pipeline/tests/test_schema_matcher.py`
- `python -m pytest scraper/pipeline/tests tools/schema_registry/tests`

Validation:
- `python -m pytest scraper/pipeline/tests/test_schema_matcher_compiled_library_regressions.py` passed
- `python -m pytest tools/schema_registry/tests/test_build_electronet_schema_library.py scraper/pipeline/tests/test_schema_matcher.py` passed
- `python -m pytest scraper/pipeline/tests tools/schema_registry/tests` passed with `232 passed`

Notes:
- no schema-result field names or fail-reason enums changed in this milestone
- the new coverage intentionally keeps the listed family tests on direct-single categories from the real compiled library and leaves sibling-pool behavior pinned by the existing synthetic matcher + compiler tests

## 2026-04-01 - Add structured debug reporting for category-scoped schema matching

Goal:
- expose enough structured schema-selection detail to debug fail-closed outcomes quickly from existing report artifacts
- keep the result envelope additive and backward-compatible while preserving fail-closed behavior
- ensure success paths also emit the new metadata so selected-template decisions remain diagnosable

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/models.py`
- `scraper/pipeline/schema_matcher.py`
- `scraper/pipeline/tests/test_prepare_result_assembly_module.py`
- `scraper/pipeline/tests/test_schema_matcher.py`

What changed:
- `SchemaMatchResult` now carries additive structured debug fields:
  - `resolved_category_path`
  - `candidate_pool_size`
  - `candidate_template_ids`
  - `selected_template_id`
  - `match_mode`
  - `hard_gate_failures`
  - `fail_reason`
  - `discriminator_hits`
  - `discriminator_misses`
  - `section_overlap_score`
  - `label_overlap_score`
- the matcher now populates those fields for:
  - empty category pools
  - manual-only categories
  - categories with no active templates
  - hard-gate failures
  - successful direct selection
  - successful bounded sibling selection
- standard fail reasons are now surfaced through the result envelope:
  - `pool_empty_for_category`
  - `manual_only_category`
  - `no_active_templates`
  - `discriminator_miss`
  - `insufficient_section_overlap`
  - `insufficient_label_overlap`
  - `no_safe_template_match`
- `schema_resolution` in the prepare report now includes the expanded structured debug payload automatically via `SchemaMatchResult.to_dict()`
- fail-closed behavior is unchanged:
  - no unrelated fallback template is selected
  - `selected_template_id` stays `null` when no safe match exists
  - `no_safe_template_match` remains an explicit surfaced warning/result state rather than a silent continuation

Test coverage added/updated:
- matcher tests now assert specific surfaced fail reasons for:
  - discriminator misses
  - manual-only categories
  - insufficient section overlap
  - insufficient label overlap
- success-path tests now assert that selected-template debug metadata is present in both `SchemaMatchResult` and the prepare report payload

Commands run:
- `Get-Content scraper\pipeline\models.py | Select-Object -Skip 248 -First 60`
- `Get-Content scraper\pipeline\prepare_result_assembly.py | Select-Object -Skip 90 -First 90`
- `Get-Content scraper\pipeline\tests\test_schema_matcher.py`
- `Get-Content scraper\pipeline\tests\test_prepare_result_assembly_module.py | Select-Object -Skip 360 -First 90`
- `Get-Content scraper\pipeline\services\render_execution.py | Select-Object -First 120`
- `python -m pytest scraper/pipeline/tests/test_schema_matcher.py`
- `python -m pytest scraper/pipeline/tests/test_prepare_result_assembly_module.py`
- `python -m pytest scraper/pipeline/tests/test_workflow.py scraper/pipeline/tests/test_services.py`
- `python -m pytest scraper/pipeline/tests`

Validation:
- `python -m pytest scraper/pipeline/tests/test_schema_matcher.py` passed
- `python -m pytest scraper/pipeline/tests/test_prepare_result_assembly_module.py` passed
- `python -m pytest scraper/pipeline/tests/test_workflow.py scraper/pipeline/tests/test_services.py` passed
- `python -m pytest scraper/pipeline/tests` passed with `218 passed`

Risks / follow-up:
- fail reasons are intentionally summarized to one primary reason in `SchemaMatchResult.fail_reason`; full per-template gate detail remains available in `hard_gate_failures`
- direct-single categories expose real overlap metrics from the selected compiled template; those values are diagnostic, not a synthetic guarantee of `1.0`

## 2026-04-01 - Implement category-scoped runtime schema selection with fail-closed sibling matching

Goal:
- replace the old global schema scoring path with category-scoped runtime selection that consumes the richer compiled metadata
- keep category resolution unchanged while ensuring unrelated categories can never win once taxonomy resolution is correct
- make direct-single categories deterministic and make sibling categories compete only inside their resolved category pool

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/prepare_result_assembly.py`
- `scraper/pipeline/schema_matcher.py`
- `scraper/pipeline/tests/test_characteristics_pipeline.py`
- `scraper/pipeline/tests/test_prepare_result_assembly_module.py`
- `scraper/pipeline/tests/test_schema_matcher.py`

What changed:
- `SchemaMatcher` no longer scores across the full schema library
- runtime candidate pools are now built from the resolved category binding using compiled `category_path`, `parent_category`, `leaf_category`, and `sub_category` metadata
- if a resolved category path has no exact compiled schema entry but the family resolves to a leaf-only compiled template, the matcher falls back only to leaf-only templates in that same parent/leaf family
- non-active templates are excluded from auto-selection by treating `template_status != active` as unsafe for runtime matching
- categories with exactly one active safe template now select that schema directly with deterministic score `1.0`
- sibling categories now apply hard gates before scoring:
  - `required_labels_any`
  - `required_labels_all`
  - `forbidden_labels`
  - `min_section_overlap`
  - `min_label_overlap`
- only candidates that survive those gates are scored, and scoring is bounded to the resolved sibling pool using:
  - normalized section overlap
  - normalized label overlap
  - normalized section-label pair overlap
  - discriminator-label overlap
- when no safe category-scoped candidate survives, the matcher now returns `no_safe_template_match` instead of borrowing another category
- `assemble_prepare_result()` now passes `taxonomy_path`, `parent_category`, and `leaf_category` into the matcher so runtime selection can scope itself without changing taxonomy resolution

Test coverage added/updated:
- direct deterministic selection when one active safe template remains in the resolved category
- sibling-only competition inside one category pool
- wrong-category schemas cannot be selected even if extracted specs resemble another template family
- weak generic overlap fails closed instead of drifting globally
- washing-machine-like extracted specs cannot select unrelated small-appliance templates
- existing TV/runtime tests now assert the new category-scoped direct-selection behavior rather than weak global matching

Commands run:
- `rg -n "schema|template|characteristics|matcher|category.*schema|no_safe_template_match|required_labels_any|required_labels_all|forbidden_labels|min_section_overlap|min_label_overlap" scraper -S`
- `Get-Content scraper\pipeline\schema_matcher.py`
- `Get-Content scraper\pipeline\prepare_result_assembly.py | Select-Object -First 110`
- `Get-Content scraper\pipeline\tests\test_schema_matcher.py`
- `Get-Content scraper\pipeline\tests\test_characteristics_pipeline.py | Select-Object -Skip 320 -First 170`
- `Get-Content scraper\pipeline\tests\test_prepare_result_assembly_module.py | Select-Object -Skip 240 -First 130`
- `python -m pytest scraper/pipeline/tests/test_schema_matcher.py`
- `python -m pytest scraper/pipeline/tests/test_prepare_result_assembly_module.py`
- `python -m pytest scraper/pipeline/tests/test_characteristics_pipeline.py`
- `python -m pytest scraper/pipeline/tests/test_product_parser.py`
- `python -m pytest scraper/pipeline/tests/test_prepare_provider_resolution.py`
- `python -m pytest scraper/pipeline/tests/test_prepare_stage_result_assembly.py`
- `python -m pytest scraper/pipeline/tests`

Validation:
- `python -m pytest scraper/pipeline/tests/test_schema_matcher.py` passed
- `python -m pytest scraper/pipeline/tests/test_prepare_result_assembly_module.py` passed
- `python -m pytest scraper/pipeline/tests/test_characteristics_pipeline.py` passed
- `python -m pytest scraper/pipeline/tests/test_product_parser.py` passed
- `python -m pytest scraper/pipeline/tests/test_prepare_provider_resolution.py` passed
- `python -m pytest scraper/pipeline/tests/test_prepare_stage_result_assembly.py` passed
- `python -m pytest scraper/pipeline/tests` passed with `215 passed`

Risks / follow-up:
- compiled metadata currently uses `match_mode` values such as `direct_single` and `category_pool`; runtime now consumes the safety metadata correctly, but a future cleanup can align naming with the docs contract if needed
- leaf-only fallback is intentionally bounded to the resolved parent/leaf family so categories like TV size buckets still resolve safely without reopening cross-category rescue
- no category resolver logic changed in this milestone

## 2026-04-01 - Freeze category-scoped schema matching contract before code changes

Goal:
- update the control docs first before any runtime matcher work
- define the exact branch contract for category-scoped schema matching so later runtime schema selection becomes fail closed once canonical category resolution is correct
- keep this commit docs-only with no matcher behavior changes yet

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `docs/specs/2026-04-01-category-scoped-schema-matching-contract.md`

Recorded problem statement:
- the current failure mode is not category resolution drift alone; category match can be correct while schema selection still drifts to an unrelated template because matching is too global or too weakly constrained
- the example failure class captured in the contract is a washing-machine product inheriting meat-grinder-like characteristics from an unrelated schema family

Recorded design contract:
- runtime schema selection must be category-scoped rather than global
- compiled runtime metadata must include category binding plus hard-gating fields
- deterministic direct selection must be used when a category has exactly one active safe template
- if multiple templates exist in the same category family, only sibling templates in that family may compete
- if hard gates fail, the matcher must return `no_safe_template_match` instead of borrowing another category's schema

Recorded compiled metadata contract:
- `PLAN.md` and the new spec now define these required compiled runtime fields:
  - `source_system`
  - `template_id`
  - `category_path`
  - `parent_category`
  - `leaf_category`
  - `sub_category`
  - `cta_map_key`
  - `template_status`
  - `match_mode`
  - `section_names_exact`
  - `section_names_normalized`
  - `label_set_exact`
  - `label_set_normalized`
  - `section_label_pairs_normalized`
  - `discriminator_labels`
  - `required_labels_any`
  - `required_labels_all`
  - `forbidden_labels`
  - `min_section_overlap`
  - `min_label_overlap`
  - `sibling_template_ids`
  - `fingerprint`
  - `source_template_file`
- `template_status` is now documented to distinguish at least:
  - `active`
  - `manual_only`
  - `deprecated`
  - `incomplete`
- `match_mode` is now documented to distinguish at least:
  - `direct_only`
  - `sibling_scored`

Recorded matcher behavior contract:
- resolve canonical category first
- build a category-scoped candidate pool from compiled metadata
- drop `manual_only`, `deprecated`, and `incomplete` templates
- direct-select when exactly one active safe template remains
- otherwise apply intra-category hard gates and bounded sibling scoring only within the same category family
- if no candidate satisfies the hard gates, return `no_safe_template_match`

Recorded non-goals:
- no global fuzzy fallback
- no cross-category schema rescue
- no category taxonomy rewrite in this branch
- no category resolution behavior change in this branch
- no public workflow entrypoint change in this branch
- no unrelated prepare/render orchestration refactor in this branch

Commands run:
- `Get-ChildItem -Force`
- `Get-Content PLAN.md`
- `Get-Content DOCUMENTATION.md`
- `Get-ChildItem docs -Recurse -File | Select-Object -ExpandProperty FullName`
- `rg -n "schema|template|characteristics|matcher|match" PLAN.md DOCUMENTATION.md docs -S`
- `Get-Content PLAN.md | Select-Object -Skip 360 -First 120`
- `Get-Content DOCUMENTATION.md | Select-Object -First 220`
- `Get-Content DOCUMENTATION.md | Select-Object -Skip 560 -First 120`

Validation:
- `PLAN.md` now explicitly defines category-scoped candidate pools
- `PLAN.md` and the new spec explicitly define fail-closed matcher behavior
- the compiled metadata fields and required `match_mode` values are now documented
- this commit changes docs only; no Python/runtime files changed and no matcher behavior changed yet

## 2026-04-01 - Land split-LLM intro validation timing and intro-only retry refactor

Goal:
- record the dedicated follow-up branch scope for the split-LLM orchestration refactor before changing Python code
- move intro word-count enforcement earlier so candidate/render/publish work is gated on intro success instead of discovering failures first at late candidate validation time
- keep `seo_meta` single-pass and allow it to complete before intro validation, without letting intro retries mutate it

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `scraper/pipeline/services/llm_stage_execution.py`
- `scraper/pipeline/services/metadata.py`
- `scraper/pipeline/services/models.py`
- `scraper/pipeline/services/render_execution.py`
- `scraper/pipeline/tests/test_llm_stage_execution.py`
- `scraper/pipeline/tests/test_services.py`
- `scraper/pipeline/tests/test_workflow.py`

Recorded scope:
- execution order becomes:
  - `seo_meta` generation or resolution first
  - `intro_text` generation or resolution second
  - immediate intro validation
  - intro-only retry on `llm_intro_text_word_count_invalid`
  - only then existing render/validation/publish flow
- `seo_meta` may complete before intro validation succeeds
- intro validation is now an early hard gate for downstream candidate build, final render assembly, CSV publish, and OpenCart publish work
- intro retries do not regenerate or mutate `seo_meta`
- later candidate validation remains as a safety backstop, not the first intro word-count enforcement point
- landed internal seam:
  - `scraper/pipeline/services/llm_stage_execution.py`
  - `run_intro_text_with_retry(...)`
  - `execute_split_llm_stage(...)`
- landed render-stage behavior:
  - `render_execution.py` now resolves and validates `seo_meta` before intro execution
  - intro retries are limited to 3 total attempts and only occur for `llm_intro_text_word_count_invalid`
  - intro validation failures now stop the run before candidate CSV build, final render assembly, CSV publish copy, or OpenCart publish can begin
  - successful intro retries unlock the downstream render path exactly once
- landed intro failure typing and trace behavior:
  - intro retry exhaustion now raises a typed `IntroTextRetryExhaustedError`
  - the typed failure carries structured intro-specific data through `failure.stage`, `failure.code`, and `failure.attempts`
  - `intro_text.retry_trace.json` is written under `work/{model}/llm/` with per-attempt `attempt`, `word_count`, `error_codes`, `status`, and `reason`
  - render failure metadata now persists the intro stage trace details under `render.run.json`
- landed atomic-write behavior:
  - intro retry writes now use temp-file plus `os.replace(...)` semantics so a partial intro rewrite cannot be mistaken for a persisted invalid intro on the next validation pass
- landed test coverage:
  - direct helper coverage in `scraper/pipeline/tests/test_llm_stage_execution.py`
  - workflow regressions proving early intro retry/success and early intro failure before candidate build
  - regression proving `seo_meta.output.json` stays preserved and byte-for-byte unchanged across intro retries and final intro exhaustion
  - rerun/idempotency regression proving render with already-valid `seo_meta` performs downstream work exactly once per render invocation when intro becomes valid on the first pass
  - service regression proving early intro validation failures propagate as render-stage service failures

Commands run:
- `Get-Location; git branch --show-current; git status --short`
- `rg --files PLAN.md DOCUMENTATION.md scraper/pipeline | sort`
- `rg -n "render_execution|validate_intro_text_output|intro_text.output|seo_meta.output|llm_intro_text_word_count_invalid|split llm|intro_text" scraper/pipeline -S`
- `Get-Content PLAN.md`
- `Get-Content DOCUMENTATION.md`
- `Get-Content scraper/pipeline/services/render_execution.py`
- `Get-Content scraper/pipeline/services/llm_stage_execution.py`
- `Get-Content scraper/pipeline/services/metadata.py`
- `Get-Content scraper/pipeline/services/models.py`
- `Get-Content scraper/pipeline/llm_contract.py`
- `Get-Content scraper/pipeline/services/errors.py`
- `Get-Content scraper/pipeline/tests/test_workflow.py | Select-Object -Skip 400 -First 120`
- `Get-Content scraper/pipeline/tests/test_services.py | Select-Object -Skip 430 -First 170`
- `Get-Content scraper/pipeline/services/__init__.py`
- `Get-Content scraper/pipeline/tests/test_workflow.py | Select-Object -First 220`
- `Get-Content scraper/pipeline/tests/test_services.py | Select-Object -First 220`
- `Get-Content scraper/pipeline/tests/test_workflow.py | Select-Object -Skip 560 -First 220`
- `Get-Content scraper/pipeline/tests/test_workflow.py | Select-Object -Skip 940 -First 120`
- `Get-Content scraper/pipeline/tests/test_workflow.py | Select-Object -Skip 1320 -First 90`
- `rg -n "_load_render_llm_inputs|_normalize_render_llm_inputs|llm_stage_execution|execute_split_llm_stage|run_intro_text_with_retry" scraper/pipeline/tests scraper/pipeline -S`
- `python -m pytest -q pipeline/tests/test_llm_stage_execution.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_workflow.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_services.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_llm_contract.py` from `scraper/`

Validation:
- `PLAN.md` now records the branch scope as completed
- `seo_meta` is resolved first, remains single-pass, and is not regenerated during intro retries
- intro word-count failures are now handled at the split-LLM stage instead of first surfacing during late candidate validation
- downstream candidate/render/publish work is blocked until intro validation succeeds
- intro retry exhaustion is now a typed error object with structured `stage`, intro-specific `code`, and `attempts` fields
- per-attempt retry trace data is now persisted under `work/{model}/llm/intro_text.retry_trace.json` and copied into failure metadata details for inspection in CI and local runs
- intro retry rewrites now use atomic replace semantics
- targeted pytest results:
  - `pipeline/tests/test_llm_stage_execution.py`: `9 passed`
  - `pipeline/tests/test_workflow.py`: `40 passed`
  - `pipeline/tests/test_services.py`: `21 passed`
  - `pipeline/tests/test_llm_contract.py`: `10 passed`

## 2026-04-02 - Rewrite stale Skroutz helper test to target the extracted public seam

Goal:
- fix the failing scraper test suite after the section-assets extraction by removing a stale import from `prepare_stage.py`
- keep the coverage intent, but assert through the extracted public seam instead of the removed private helper location

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/tests/test_skroutz_sections.py`

Changes:
- replaced the stale import of `_select_skroutz_image_backed_sections` from `scraper/pipeline/prepare_stage.py`
- rewrote the affected test to call `resolve_skroutz_section_assets(...)` from `scraper/pipeline/prepare_section_assets.py`
- kept the original behavior under test:
  - text-only rendered interludes are skipped
  - image-backed sections are selected in stable order
  - resolved image URLs flow into the selected Besco inputs on the public seam

Commands run:
- `python -m pytest -q scraper/pipeline/tests/test_skroutz_sections.py`
- `python -m pytest -q scraper/pipeline/tests/test_prepare_section_assets.py scraper/pipeline/tests/test_prepare_section_assets_module.py scraper/pipeline/tests/test_prepare_skroutz_section_assets_module.py`
- `python -m pytest -q` from `scraper/`

Validation:
- the stale collection failure on `test_skroutz_sections.py` is removed
- the public-seam Skroutz test coverage remains in place
- the full scraper suite passes after the test rewrite

## 2026-04-01 - Finalize docs for prepare-stage section-assets extraction

Goal:
- mark the section-assets extraction branch scope complete in the control docs
- make the landed module name, typed result name, narrowed stage responsibilities, and landed test split explicit
- keep this commit docs-only with no Python changes

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`

Landed state recorded:
- landed internal seam module:
  - `scraper/pipeline/prepare_section_assets.py`
- landed typed result:
  - `PrepareSectionAssetsResult`
- landed narrowed `prepare_stage.py` responsibilities:
  - top-level routing for whether sections run at all
  - direct-source / non-Skroutz section orchestration, still inline by design
  - final `source_payload` creation
  - downstream result-assembly handoff
  - scrape-artifact persistence handoff
  - outward dict-shaped `execute_prepare_stage(...)` return payload compatibility
- landed test coverage split:
  - direct helper and standalone seam tests in `scraper/pipeline/tests/test_prepare_section_assets_module.py` and `scraper/pipeline/tests/test_prepare_skroutz_section_assets_module.py`
  - stage-isolation tests in `scraper/pipeline/tests/test_prepare_section_assets.py`
  - downstream deterministic stage-isolation tests in `scraper/pipeline/tests/test_prepare_stage_result_assembly.py`
  - adjacent taxonomy-enrichment stage-isolation tests in `scraper/pipeline/tests/test_prepare_taxonomy_enrichment.py`
  - prepare-focused workflow regression coverage remains the higher-level unchanged-behavior backstop
- landed injection boundary:
  - `execute_prepare_stage(...)` now keeps one section-assets seam injection:
    - `resolve_skroutz_section_assets_fn`

Direct-source status recorded explicitly:
- the direct-source / non-Skroutz section path still remains inline in `prepare_stage.py` by design after this branch

Next recommended branch:
- the next real section branch should be direct-source / non-Skroutz section extraction
- naming polish is not yet the recommended next branch because one meaningful section seam still remains

Commands run:
- `Get-Content PLAN.md | Select-Object -Skip 550 -First 110`
- `Get-Content DOCUMENTATION.md -TotalCount 220`
- `Get-Content README.md -TotalCount 220`

Validation:
- `PLAN.md` now records the section-assets extraction as landed rather than planned
- `DOCUMENTATION.md` now records the landed module name, typed result name, narrowed stage responsibilities, and landed test split
- `README.md` was reviewed and left unchanged because it does not incorrectly describe internal prepare-stage ownership
- this commit is docs-only and does not modify Python files

## 2026-04-01 - Collapse prepare-stage section-assets dependency surface to one seam

Goal:
- narrow `execute_prepare_stage(...)` to one explicit injected section-assets seam
- stop relying on module-level monkeypatching or any lower-level section helper exposure when isolating the stage
- preserve workflow, prepare execution, and public runtime behavior unchanged

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/prepare_stage.py`
- `scraper/pipeline/tests/test_prepare_section_assets.py`

Changes:
- `execute_prepare_stage(...)` now exposes one section-assets seam:
  - `resolve_skroutz_section_assets_fn=resolve_skroutz_section_assets`
- stage internals now call that injected seam instead of referencing only the imported module function directly
- no lower-level section helpers were added to the stage signature
- updated prepare-stage section-assets tests so stage isolation now passes `resolve_skroutz_section_assets_fn=...` directly when isolating Skroutz section behavior
- direct unit tests continue to target the extracted section-assets module itself

Old vs new signature summary:
- old:
  - `execute_prepare_stage(..., resolve_prepare_taxonomy_enrichment_fn=..., assemble_prepare_result_fn=..., persist_prepare_scrape_artifacts_fn=...)`
- new:
  - `execute_prepare_stage(..., resolve_prepare_taxonomy_enrichment_fn=..., resolve_skroutz_section_assets_fn=resolve_skroutz_section_assets, assemble_prepare_result_fn=..., persist_prepare_scrape_artifacts_fn=...)`

Commands run:
- `python -m pytest -q pipeline/tests/test_prepare_skroutz_section_assets_module.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_prepare_section_assets_module.py pipeline/tests/test_prepare_section_assets.py pipeline/tests/test_prepare_taxonomy_enrichment.py pipeline/tests/test_prepare_stage_result_assembly.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_workflow.py -k "test_prepare_workflow_writes_prompt_artifacts"` from `scraper/`

Validation:
- direct section-assets module tests still passed
- updated stage section-assets isolation tests still passed
- adjacent taxonomy-enrichment and result-assembly isolation tests still passed
- one prepare-workflow regression path still passed after the signature narrowing
- no public workflow entrypoint changed
- no `prepare_execution.py` behavior changed

## 2026-04-01 - Wire prepare stage to the extracted Skroutz section-assets workflow

Goal:
- route `scraper/pipeline/prepare_stage.py` through `resolve_skroutz_section_assets(...)`
- remove the now-redundant inline Skroutz section-asset workflow block from `prepare_stage.py`
- preserve outward stage return keys, result-assembly inputs, persistence wiring, and public workflow behavior

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/prepare_stage.py`
- `scraper/pipeline/tests/test_prepare_section_assets.py`

Changes:
- `prepare_stage.py` now calls `resolve_skroutz_section_assets(...)` when:
  - `source == "skroutz"`
  - `cli.sections > 0`
- removed the inline Skroutz block from `prepare_stage.py` that previously owned:
  - manufacturer-first block selection
  - fallback to `extract_skroutz_section_window(...)`
  - rendered section-image record extraction
  - `_select_skroutz_image_backed_sections(...)`
  - resolved-image mutation on selected blocks
  - optional `presentation_source_html` override
  - strict Skroutz Besco download handling
  - Skroutz diagnostics / `sections_artifact_payload` assembly
- `prepare_stage.py` now keeps only the surrounding orchestration and consumes the extracted result fields from `resolve_skroutz_section_assets(...)`
- updated stage characterization tests so Skroutz-focused stage coverage now stubs `resolve_skroutz_section_assets(...)` directly instead of patching the removed inline internals

Commands run:
- `python -m pytest -q pipeline/tests/test_prepare_skroutz_section_assets_module.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_prepare_section_assets_module.py pipeline/tests/test_prepare_section_assets.py pipeline/tests/test_prepare_taxonomy_enrichment.py pipeline/tests/test_prepare_stage_result_assembly.py` from `scraper/`

Validation:
- direct standalone Skroutz section-assets module tests still passed
- updated stage characterization tests still passed after the wiring change
- adjacent taxonomy-enrichment and result-assembly isolation tests still passed
- outward `execute_prepare_stage(...)` return keys remained unchanged
- no workflow/service/public entrypoint changed

Section logic intentionally still left in `prepare_stage.py`:
- top-level decision to run sections or not
- direct-source / non-Skroutz section orchestration
- final `source_payload` creation
- final handoff into `assemble_prepare_result_fn(...)`
- final handoff into `persist_prepare_scrape_artifacts_fn(...)`

## 2026-04-01 - Add standalone Skroutz section-assets workflow module without wiring stage yet

Goal:
- add the extracted Skroutz section-asset workflow as a standalone internal module seam
- keep this commit limited to the new typed result and direct module tests
- avoid rerouting `prepare_stage.py` yet so the stage injection surface remains unchanged in this commit

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/prepare_section_assets.py`
- `scraper/pipeline/tests/test_prepare_skroutz_section_assets_module.py`

Changes:
- extended `scraper/pipeline/prepare_section_assets.py` with:
  - typed result `PrepareSectionAssetsResult`
  - new entrypoint `resolve_skroutz_section_assets(...)`
- the extracted standalone Skroutz workflow now owns, inside the new module:
  - manufacturer-first block selection
  - fallback to `extract_skroutz_section_window(...)`
  - `fetcher.extract_skroutz_section_image_records(...)`
  - an internal `_select_skroutz_image_backed_sections(...)`
  - mutation of selected blocks with resolved image URLs
  - optional `presentation_source_html_override` via `build_skroutz_presentation_source_html(...)`
  - reuse of the shared `download_section_assets(...)` helper
  - production of downstream section-asset outputs:
    - `selected_presentation_blocks`
    - `selected_besco_images`
    - `downloaded_besco`
    - `besco_warnings`
    - `besco_files`
    - `besco_filenames_by_section`
    - `section_warnings`
    - `section_image_candidates`
    - `section_image_urls_resolved`
    - `section_extraction_window`
    - `sections_artifact_payload`
    - `presentation_source_html_override`
- added direct module tests in:
  - `scraper/pipeline/tests/test_prepare_skroutz_section_assets_module.py`

Commands run:
- `python -m pytest -q pipeline/tests/test_prepare_skroutz_section_assets_module.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_prepare_section_assets_module.py pipeline/tests/test_prepare_section_assets.py pipeline/tests/test_prepare_taxonomy_enrichment.py pipeline/tests/test_prepare_stage_result_assembly.py` from `scraper/`

Validation:
- direct standalone Skroutz section-assets tests passed
- existing section-assets helper and stage characterization tests still passed
- no production wiring changed in `prepare_stage.py`
- no public workflow or service behavior changed in this commit

Intentional temporary duplication left for the next commit:
- `prepare_stage.py` still contains the active inline Skroutz section-asset workflow
- `resolve_skroutz_section_assets(...)` currently mirrors that live stage logic but is not called by `prepare_stage.py` yet
- `_select_skroutz_image_backed_sections(...)` now exists in both `prepare_stage.py` and `prepare_section_assets.py` until the stage is wired over in the next commit

## 2026-04-01 - Extract pure section diagnostics and `bescos_raw` payload builders

Goal:
- remove the deterministic section diagnostics / `bescos_raw` payload builders from `scraper/pipeline/prepare_stage.py`
- keep the commit limited to pure helper extraction and wiring the existing Skroutz branches through those helpers
- preserve current payload shapes, filenames, result-assembly inputs, and persistence wiring

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/prepare_section_assets.py`
- `scraper/pipeline/prepare_stage.py`
- `scraper/pipeline/tests/test_prepare_section_assets_module.py`

Changes:
- extended `scraper/pipeline/prepare_section_assets.py` with pure helpers:
  - `build_section_image_candidates(...)`
  - `build_section_image_urls_resolved(...)`
  - `build_sections_artifact_payload(...)`
- kept `download_section_assets(...)` in the same focused helper module
- moved the duplicated deterministic payload shaping for both Skroutz branches out of `prepare_stage.py`:
  - manufacturer-backed Skroutz section diagnostics now use the pure helpers
  - fallback Skroutz section diagnostics and `sections_artifact_payload` now use the pure helpers after the existing resolved-image mutation step
- preserved:
  - exact `section_image_candidates` shape
  - exact `section_image_urls_resolved` shape
  - exact `sections_artifact_payload` / `bescos_raw` shape
  - target filenames `besco{N}.jpg`
  - existing `section_extraction_window` shaping and merge behavior
  - existing result-assembly input keys and persistence wiring

Commands run:
- `python -m pytest -q pipeline/tests/test_prepare_section_assets_module.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_prepare_section_assets.py pipeline/tests/test_prepare_taxonomy_enrichment.py pipeline/tests/test_prepare_stage_result_assembly.py` from `scraper/`

Validation:
- helper-module tests passed after adding direct coverage for the pure builders
- existing section-assets characterization tests still passed
- adjacent taxonomy-enrichment and result-assembly isolation tests still passed
- no public workflow entrypoint changed
- no output artifact paths changed

Remaining orchestration intentionally still in `prepare_stage.py`:
- direct-source / non-Skroutz section extraction
- Skroutz manufacturer-first branch selection
- Skroutz fallback extraction via `extract_skroutz_section_window(...)`
- rendered-title reconciliation and the resolved-image mutation loop
- `section_extraction_window` inline construction / merge behavior
- outward `execute_prepare_stage(...)` return keys and persistence handoff

## 2026-04-01 - Extract shared Besco section-download helper

Goal:
- remove the duplicated Besco / section-image download logic from `scraper/pipeline/prepare_stage.py`
- keep the commit limited to one shared helper and wiring the two existing call sites through it
- preserve current direct-path warning behavior, Skroutz strict-failure behavior, and outward stage payloads

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/prepare_section_assets.py`
- `scraper/pipeline/prepare_stage.py`
- `scraper/pipeline/tests/test_prepare_section_assets_module.py`

Changes:
- added focused helper module:
  - `scraper/pipeline/prepare_section_assets.py`
- added shared helper:
  - `download_section_assets(...)`
- added typed helper result:
  - `SectionAssetDownloadResult`
- moved the duplicated Besco download policy into the helper:
  - `fetcher.download_besco_images(...)`
  - direct-path warning-only `FetchError` handling
  - Skroutz strict `FetchError` -> `RuntimeError` handling
  - strict expected-count enforcement for Skroutz
  - `besco_filenames_by_section` mapping
  - returned bundle of:
    - `downloaded_besco`
    - `besco_warnings`
    - `besco_files`
    - `besco_filenames_by_section`
- wired both existing `prepare_stage.py` call sites through the helper:
  - direct / non-Skroutz section path
  - Skroutz section path

Behavior preserved explicitly:
- direct / non-Skroutz path still converts `FetchError` into warning-only `besco_download_failed:...`
- Skroutz path still raises `RuntimeError` on `FetchError`
- Skroutz path still raises `RuntimeError` on incomplete Besco download
- successful downloads still populate `besco_filenames_by_section` from downloaded image positions exactly as before
- section diagnostics and `sections_artifact_payload` construction remain in `prepare_stage.py` in this commit

Commands run:
- `python -m pytest -q pipeline/tests/test_prepare_section_assets_module.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_prepare_section_assets.py pipeline/tests/test_prepare_taxonomy_enrichment.py pipeline/tests/test_prepare_stage_result_assembly.py` from `scraper/`

Validation:
- new helper-module tests passed
- existing section-assets characterization tests still passed after the extraction
- adjacent taxonomy-enrichment and result-assembly isolation tests still passed
- no public workflow entrypoint changed
- no output artifact paths changed

Remaining duplicated / in-place section logic intentionally left for later commits:
- direct-source / non-Skroutz section extraction still lives inline in `prepare_stage.py`
- Skroutz manufacturer-first selection still lives inline in `prepare_stage.py`
- Skroutz fallback extraction, rendered-title reconciliation, resolved-image mutation, and `sections_artifact_payload` construction still live inline in `prepare_stage.py`
- outward `execute_prepare_stage(...)` return keys remain unchanged

## 2026-04-01 - Add prepare-stage section-assets characterization tests

Goal:
- pin the current direct-source and Skroutz section-asset behavior inside `scraper/pipeline/prepare_stage.py`
- add narrow characterization coverage before extracting the section-assets seam
- keep this commit test-only with no production behavior changes

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/tests/test_prepare_section_assets.py`

Changes:
- added focused prepare-stage characterization coverage for the direct-source / non-Skroutz section path:
  - `selected_presentation_blocks` come from `extract_presentation_blocks(...)`
  - only image-bearing blocks become `GalleryImage` Besco records
  - direct-path Besco download `FetchError` stays warning-only and does not become a hard failure
- added focused Skroutz manufacturer-first coverage:
  - manufacturer presentation blocks are preferred when enough blocks exist
  - manufacturer-backed section diagnostics and `sections_artifact_payload` / `bescos_raw` payload shape are pinned
  - successful manufacturer-backed Besco downloads produce the current `downloaded_besco` and `besco_filenames_by_section` handoff values
- added focused Skroutz fallback coverage:
  - `extract_skroutz_section_window(...)` output is consumed
  - rendered section image records are reconciled against parsed section titles in order
  - selected blocks are mutated with resolved image URLs
  - the merged `section_extraction_window` and `sections_artifact_payload` / `bescos_raw` payload shape are pinned
  - fallback rebuilds `presentation_source_html` when manufacturer presentation was not applied
- added strict-failure characterization for current Skroutz behavior:
  - insufficient rendered image-record count
  - title-order mismatch between parsed and rendered section lists
  - incomplete Skroutz Besco download on the manufacturer-first path
- pinned the exact values that currently feed downstream seams:
  - `selected_presentation_blocks`
  - `section_warnings`
  - `section_image_candidates`
  - `section_image_urls_resolved`
  - `section_extraction_window`
  - `selected_besco_images`
  - `downloaded_besco`
  - `besco_filenames_by_section`
  - `sections_artifact_payload`

Commands run:
- `python -m pytest -q pipeline/tests/test_prepare_section_assets.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_prepare_taxonomy_enrichment.py pipeline/tests/test_prepare_stage_result_assembly.py` from `scraper/`

Validation:
- new section-assets characterization tests passed: `6 passed`
- adjacent taxonomy-enrichment and result-assembly isolation tests still passed: `8 passed`
- no production Python modules changed
- no workflow behavior changed

Ambiguities recorded:
- on the direct path, Besco download still uses `requested_sections=len(selected_presentation_blocks)` even when only a subset of selected blocks have images, so Besco positions can be sparse while the path remains warning-only on `FetchError`
- on the Skroutz fallback path, `section_extraction_window` merges parsed and rendered window dictionaries asymmetrically: `candidate_count` and `duplicate_signatures_skipped` take the `max(...)`, while other overlapping keys are overwritten by the rendered-window payload
- the section-asset diagnostics that later feed result assembly are not returned directly from `execute_prepare_stage(...)`; they are observable today only through the downstream seam inputs and persisted `bescos_raw` payload

## 2026-04-01 - Freeze prepare-stage section-assets refactor scope

Goal:
- document the exact branch scope for `refactor/prepare-stage-section-assets`
- update control docs first, before any Python extraction work
- keep this commit docs-only and avoid changing runtime behavior, tests, imports, workflow entrypoints, or artifact contracts

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`

Recorded scope:
- branch goal:
  - extract the Skroutz/manufacturer-first section asset workflow out of `scraper/pipeline/prepare_stage.py` while preserving current runtime behavior
- exact non-goals:
  - no public workflow or CLI behavior change
  - no prepare/render ownership-boundary change
  - no output artifact path or filename change
  - no `prepare_execution.py` behavior change
  - no result-assembly ownership change in this branch
  - no provider-resolution ownership change in this branch
  - no render ownership change
  - no extraction of the whole direct-source / non-Skroutz section path in this branch
  - no extraction of `html_builders.extract_presentation_blocks(...)` in this branch
  - no relocation of `skroutz_sections` helpers in this branch
  - no naming-polish cleanup in this branch
  - no split-task LLM handoff contract change
- proposed module name:
  - `scraper/pipeline/prepare_skroutz_section_assets.py`
- proposed typed result name:
  - `PrepareSkroutzSectionAssetsResult`
- what leaves `prepare_stage.py` in this branch:
  - the Skroutz/manufacturer-first section asset workflow
  - the rendered-Skroutz image-backed section matching path
  - the shared section-image download helper reused by both direct and Skroutz paths
  - deterministic section diagnostics builders, including `section_image_candidates`, `section_image_urls_resolved`, `section_extraction_window`, and `bescos_raw` / sections-artifact payload shaping
  - the typed handoff carrying section asset state back into `prepare_stage.py`
- what stays in `prepare_stage.py` in this branch:
  - top-level routing for whether sections run at all
  - direct-source / non-Skroutz section orchestration except for reuse of the shared extracted downloader
  - final handoff into `assemble_prepare_result_fn(...)`
  - final handoff into `persist_prepare_scrape_artifacts_fn(...)`
  - provider-resolution ownership
  - outward dict-shaped `execute_prepare_stage(...)` payload compatibility
- explicit branch boundary:
  - `html_builders.extract_presentation_blocks(...)` stays where it is
  - `skroutz_sections` helpers stay where they are
  - direct-source section extraction itself is not fully extracted in this branch
  - `prepare` stays scrape-only plus LLM-handoff-only
  - render ownership does not change

Planned test split for later commits:
- add direct module-level coverage in `scraper/pipeline/tests/test_prepare_skroutz_section_assets_module.py`
- add stage-isolation coverage in `scraper/pipeline/tests/test_prepare_stage_section_assets.py`
- keep adjacent stage-isolation coverage in `test_prepare_taxonomy_enrichment.py` and `test_prepare_stage_result_assembly.py`
- keep prepare/workflow/provider regressions as the unchanged-behavior backstop

Commands run:
- `Get-Content PLAN.md`
- `Get-Content DOCUMENTATION.md`
- `Get-Content README.md`
- `rg -n "section|besco|download|skroutz|presentation|html_builders|extract_presentation_blocks|assemble_prepare_result_fn|persist_prepare_scrape_artifacts_fn" scraper/pipeline/prepare_stage.py`
- `rg -n "extract_presentation_blocks|skroutz_sections|bescos_raw|section image|download" scraper/pipeline -g "*.py"`

Validation:
- `PLAN.md` now records the new branch goal, non-goals, proposed seam/module/result naming, ownership split, and later test split
- `DOCUMENTATION.md` now captures the same scope freeze as the engineering log entry for this docs-only commit
- `README.md` was reviewed and left unchanged because it does not describe the internal prepare-stage seam inaccurately
- this commit does not modify Python files
- this commit does not modify test files

## 2026-04-01 - Finalize docs for prepare-stage taxonomy/enrichment extraction

Goal:
- mark the taxonomy/enrichment extraction branch scope complete in the control docs
- make the landed ownership boundary and landed test split explicit
- keep this commit docs-only with no Python changes

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`

Landed state recorded:
- landed internal seam module:
  - `scraper/pipeline/prepare_taxonomy_enrichment.py`
- landed typed result:
  - `PrepareTaxonomyEnrichmentResult`
- landed narrowed `prepare_stage.py` responsibilities:
  - provider-resolution ownership
  - gallery download orchestration
  - section-image/Besco download orchestration
  - Skroutz section extraction and manufacturer-presentation fallback handling
  - downstream result-assembly handoff
  - scrape-artifact persistence handoff
  - outward dict-shaped `execute_prepare_stage(...)` return payload compatibility
- landed test coverage split:
  - direct seam tests in `scraper/pipeline/tests/test_prepare_taxonomy_enrichment_module.py`
  - stage-isolation tests in `scraper/pipeline/tests/test_prepare_taxonomy_enrichment.py`
  - downstream deterministic stage-isolation tests in `scraper/pipeline/tests/test_prepare_stage_result_assembly.py`
  - prepare/workflow/provider regression coverage remains the higher-level unchanged-behavior backstop
- landed injection boundary:
  - `execute_prepare_stage(...)` now keeps one taxonomy/enrichment seam injection:
    - `resolve_prepare_taxonomy_enrichment_fn`

Next recommended branch:
- the next real structural seam is still the remaining gallery/Besco plus Skroutz section-extraction orchestration in `prepare_stage.py`
- naming polish is not yet the recommended next branch because that larger stage seam still remains

Commands run:
- `Get-Content PLAN.md | Select-Object -Skip 480 -First 80`
- `Get-Content DOCUMENTATION.md -TotalCount 160`
- `Get-Content README.md`

Validation:
- `PLAN.md` now records the taxonomy/enrichment extraction as landed rather than proposed
- `DOCUMENTATION.md` now records the landed module name, typed result name, narrowed stage responsibilities, and test split
- `README.md` was reviewed and left unchanged because it does not incorrectly describe internal prepare-stage ownership
- this commit is docs-only and does not modify Python files

## 2026-04-01 - Collapse prepare-stage taxonomy/enrichment to one injected seam

Goal:
- reduce the taxonomy/enrichment dependency surface in `execute_prepare_stage(...)` to one injected callable
- remove the now-redundant lower-level stage injection surface because those helpers are internal to `scraper/pipeline/prepare_taxonomy_enrichment.py`
- keep workflow, prepare execution, and outward stage behavior unchanged

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/prepare_stage.py`
- `scraper/pipeline/prepare_taxonomy_enrichment.py`
- `scraper/pipeline/tests/test_prepare_taxonomy_enrichment.py`
- `scraper/pipeline/tests/test_prepare_taxonomy_enrichment_module.py`
- `scraper/pipeline/tests/test_prepare_stage_result_assembly.py`
- `scraper/pipeline/tests/test_provider_selection.py`

Changes:
- `execute_prepare_stage(...)` now exposes one taxonomy/enrichment seam:
  - `resolve_prepare_taxonomy_enrichment_fn=resolve_prepare_taxonomy_enrichment`
- removed the old lower-level stage injection surface:
  - `taxonomy_resolver_factory`
  - `enrich_source_from_manufacturer_docs_fn`
- `prepare_stage.py` now depends only on the single typed taxonomy/enrichment seam and no longer exposes the internal resolver/enrichment helpers in its signature
- direct seam tests continue to target `scraper/pipeline/prepare_taxonomy_enrichment.py`
- stage-isolation tests now stub only `resolve_prepare_taxonomy_enrichment_fn` when isolating `execute_prepare_stage(...)`
- docs now use the landed seam name:
  - `resolve_prepare_taxonomy_enrichment(...)`

Old vs new stage signature summary:
- old:
  - `execute_prepare_stage(..., taxonomy_resolver_factory=TaxonomyResolver, enrich_source_from_manufacturer_docs_fn=enrich_source_from_manufacturer_docs, ...)`
- new:
  - `execute_prepare_stage(..., resolve_prepare_taxonomy_enrichment_fn=resolve_prepare_taxonomy_enrichment, ...)`

Commands run:
- `python -m pytest -q pipeline/tests/test_prepare_taxonomy_enrichment_module.py pipeline/tests/test_prepare_taxonomy_enrichment.py pipeline/tests/test_prepare_stage_result_assembly.py pipeline/tests/test_provider_selection.py pipeline/tests/test_workflow.py -k "prepare"` from `scraper/`

Validation:
- direct taxonomy/enrichment seam tests still pass
- stage-isolation tests now stub only the single taxonomy/enrichment seam
- prepare-focused provider-selection regressions still pass
- prepare-focused workflow regression coverage still passes
- no public workflow or service entrypoint changed

## 2026-04-01 - Wire prepare stage to the taxonomy/enrichment seam

Goal:
- route `scraper/pipeline/prepare_stage.py` through the new taxonomy-resolution plus manufacturer-enrichment seam
- remove the now-redundant inline taxonomy/enrichment block from `prepare_stage.py`
- preserve the outward `execute_prepare_stage(...)` payload, prepare/workflow behavior, and ownership boundaries

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/prepare_stage.py`

Changes:
- wired `prepare_stage.py` to `resolve_prepare_taxonomy_enrichment(...)` in `scraper/pipeline/prepare_taxonomy_enrichment.py`
- removed the inline prepare-stage block that previously owned:
  - local taxonomy resolver construction
  - `taxonomy_resolver.resolve(...)` orchestration
  - conditional `source == "skroutz"` manufacturer-doc enrichment orchestration
  - the local unpacking/assembly of taxonomy plus manufacturer-enrichment handoff values
- `prepare_stage.py` now:
  - keeps gallery and Besco orchestration
  - keeps any upstream shaping required before the taxonomy/enrichment seam
  - receives typed taxonomy/enrichment outputs from the seam
  - keeps the downstream handoff into result assembly
  - keeps the outward dict-shaped return payload compatible with downstream callers

Commands run:
- `Get-Content scraper/pipeline/prepare_stage.py`
- `Get-Content scraper/pipeline/prepare_taxonomy_enrichment.py`
- `python -m pytest -q pipeline/tests/test_prepare_taxonomy_enrichment_module.py pipeline/tests/test_prepare_taxonomy_enrichment.py pipeline/tests/test_prepare_stage_result_assembly.py pipeline/tests/test_provider_selection.py pipeline/tests/test_workflow.py -k "prepare"` from `scraper/`

Validation:
- direct taxonomy/enrichment seam tests still pass
- existing prepare-stage taxonomy/enrichment characterization tests still pass
- adjacent prepare-stage result-assembly tests still pass
- prepare-focused provider-selection and workflow regressions still pass
- outward `execute_prepare_stage(...)` return keys remain unchanged

Logic intentionally still left in `prepare_stage.py`:
- gallery download orchestration
- section-image/Besco download orchestration
- Skroutz section extraction and manufacturer-presentation fallback handling
- downstream result-assembly handoff
- scrape-artifact persistence handoff

## 2026-04-01 - Add standalone prepare taxonomy/enrichment seam without wiring it

Goal:
- add the extracted taxonomy-resolution plus manufacturer-enrichment module for the current branch
- keep `scraper/pipeline/prepare_stage.py` behavior unchanged in this commit by not wiring the new seam yet
- pin the new seam directly with focused tests while preserving the existing prepare-stage regressions

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/prepare_taxonomy_enrichment.py`
- `scraper/pipeline/tests/test_prepare_taxonomy_enrichment_module.py`

Changes:
- added `scraper/pipeline/prepare_taxonomy_enrichment.py`
- added the new internal typed result:
  - `PrepareTaxonomyEnrichmentResult`
- added the new internal seam:
  - `resolve_prepare_taxonomy_enrichment(...)`
- the new module now owns standalone logic for:
  - taxonomy resolver construction through `taxonomy_resolver_factory`
  - `taxonomy_resolver.resolve(...)` orchestration using the current prepare-stage input contract
  - Skroutz-only manufacturer-doc enrichment orchestration
  - the current non-Skroutz default manufacturer-enrichment payload shape
  - the typed handoff bundle for taxonomy, taxonomy candidates, and manufacturer-enrichment diagnostics
- added focused direct tests for the seam in `scraper/pipeline/tests/test_prepare_taxonomy_enrichment_module.py`

Intentional temporary duplication left for the next commit:
- `scraper/pipeline/prepare_stage.py` still contains the active inline taxonomy-resolution plus manufacturer-enrichment block
- `scraper/pipeline/prepare_taxonomy_enrichment.py` currently mirrors that logic but is not called by `prepare_stage.py` yet
- the non-Skroutz default manufacturer-enrichment payload currently exists in both places so the next commit can wire the seam first and de-duplicate second if needed

Commands run:
- `Get-Content scraper/pipeline/manufacturer_enrichment.py`
- `Get-Content scraper/pipeline/taxonomy.py`
- `python -m pytest -q pipeline/tests/test_prepare_taxonomy_enrichment_module.py pipeline/tests/test_prepare_taxonomy_enrichment.py pipeline/tests/test_prepare_stage_result_assembly.py` from `scraper/`

Validation:
- the new taxonomy/enrichment seam module is covered directly without changing production behavior
- existing prepare-stage taxonomy/enrichment characterization tests still pass unchanged
- adjacent prepare-stage result-assembly tests still pass
- this commit does not move result assembly, scrape persistence, or provider resolution

## 2026-04-01 - Add prepare-stage taxonomy/enrichment characterization tests

Goal:
- pin the current taxonomy-resolution plus manufacturer-enrichment behavior inside `scraper/pipeline/prepare_stage.py`
- add narrow characterization coverage before extracting the taxonomy/enrichment orchestration seam
- keep this commit test-only with no production behavior changes

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/tests/test_prepare_taxonomy_enrichment.py`

Changes:
- added focused prepare-stage seam characterization coverage for:
  - the exact `taxonomy_resolver.resolve(...)` inputs currently passed by `prepare_stage.py`
  - top-level and result-assembly propagation of `taxonomy_candidates`
  - Skroutz-only manufacturer enrichment orchestration, including the current `output_dir=model_dir/"manufacturer"` contract
  - the current non-Skroutz skip behavior and default fallback payload shape for:
    - `electronet`
    - `manufacturer_tefal`
  - propagation of manufacturer-enrichment mutations on `parsed.source` into the later prepare-stage flow
  - current warning/reason behavior with the real result-assembly path:
    - taxonomy `reason` is appended to top-level report warnings
    - manufacturer-enrichment warnings remain nested under `report["manufacturer_enrichment"]` and are not flattened into `report["warnings"]`
  - the current top-level `execute_prepare_stage(...)` output shape relied on by downstream code

Commands run:
- `Get-Content scraper/pipeline/prepare_stage.py`
- `Get-Content scraper/pipeline/prepare_result_assembly.py`
- `Get-Content scraper/pipeline/services/prepare_execution.py`
- `python -m pytest -q pipeline/tests/test_prepare_taxonomy_enrichment.py pipeline/tests/test_prepare_stage_result_assembly.py` from `scraper/`

Validation:
- the new taxonomy/enrichment characterization tests pass
- adjacent prepare-stage result-assembly tests still pass
- no production Python modules changed
- no workflow behavior changed

Ambiguities recorded:
- current behavior does not flatten manufacturer-enrichment warnings into `report["warnings"]`; they remain only under `report["manufacturer_enrichment"]["warnings"]`
- non-Skroutz sources currently receive a synthetic default manufacturer-enrichment payload rather than `None` or an omitted field, and the fallback reason differs by source (`not_applicable_non_skroutz` vs `direct_source_already_manufacturer`)

## 2026-04-01 - Freeze prepare-stage taxonomy enrichment refactor scope

Goal:
- document the exact branch scope for `refactor/prepare-stage-taxonomy-enrichment`
- update control docs first, before any Python extraction work
- keep this commit docs-only and avoid changing runtime behavior, tests, imports, workflow entrypoints, or artifact contracts

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`

Recorded scope:
- branch goal:
  - extract taxonomy resolution plus manufacturer-doc enrichment orchestration out of `scraper/pipeline/prepare_stage.py` while preserving current runtime behavior
- exact non-goals:
  - no public workflow or CLI behavior change
  - no prepare/render ownership-boundary change
  - no output artifact path or filename change
  - no `prepare_execution.py` behavior change
  - no provider-resolution reshuffle in this branch
  - no scrape-persistence extraction or path redesign in this branch
  - no result-assembly extraction or result-assembly ownership change in this branch
  - no schema/result-assembly ownership change in this branch
  - no render ownership change
  - no naming-polish cleanup in this branch
  - no split-task LLM handoff contract change
- proposed module name:
  - `scraper/pipeline/prepare_taxonomy_enrichment.py`
- proposed typed result name:
  - `PrepareTaxonomyEnrichmentResult`
- what leaves `prepare_stage.py` in this branch:
  - `taxonomy_resolver.resolve(...)`
  - conditional manufacturer-doc enrichment orchestration
  - the typed handoff carrying resolved taxonomy plus manufacturer-enriched section state back into `prepare_stage.py`
- what stays in `prepare_stage.py` in this branch:
  - provider-resolution ownership
  - gallery and Besco orchestration
  - scrape persistence seam invocation
  - result-assembly seam invocation
  - the outward dict-shaped `execute_prepare_stage(...)` payload
- explicit branch boundary:
  - result assembly remains outside this branch
  - `prepare_execution.py` remains unchanged
  - taxonomy and manufacturer enrichment move together as one orchestration seam

Proposed test split for later commits:
- add direct module-level coverage in `test_prepare_taxonomy_enrichment_module.py`
- add stage-isolation coverage in `test_prepare_stage_taxonomy_enrichment.py`
- keep existing prepare/workflow/provider regressions as the behavioral backstop for Electronet, Skroutz, and supported manufacturer flows
- run targeted seam tests during each extraction step, then run the broader scraper suite before closing the branch

Commands run:
- `rg -n "Branch scope|prepare-stage result assembly refactor|recommended next branch|taxonomy/manufacturer-enrichment orchestration" PLAN.md DOCUMENTATION.md`
- `Get-Content PLAN.md | Select-Object -Skip 350 -First 140`
- `Get-Content DOCUMENTATION.md -TotalCount 140`
- `Get-Content README.md`

Validation:
- the new branch scope is now recorded in `PLAN.md`
- the engineering log now captures the branch goal, non-goals, proposed module/result names, ownership split, and planned test split
- `README.md` was reviewed and did not require changes for this scope-freeze commit
- this commit remains docs-only and does not modify Python files
- this commit remains docs-only and does not modify test files

## 2026-04-01 - Finalize docs for prepare-stage result-assembly extraction

Goal:
- freeze the landed ownership for the prepare-stage result-assembly refactor in the control docs
- remove active-state wording drift that still described the branch as proposed or implied direct `SchemaMatcher` construction in `prepare_stage.py`
- keep this commit docs-only

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`

Changes:
- updated `PLAN.md` to record the landed state instead of the earlier planned state for this branch
- documented that `scraper/pipeline/prepare_stage.py` now owns only upstream orchestration and input preparation:
  - gallery/Besco handling
  - taxonomy resolution
  - manufacturer enrichment
  - shaping needed before deterministic result assembly
- documented that `scraper/pipeline/prepare_result_assembly.py` now owns:
  - schema source preference logic
  - schema matcher construction
  - `schema_matcher.match(...)` orchestration
  - deterministic row building
  - normalized payload assembly
  - report payload assembly
- documented the landed single injection seam:
  - `assemble_prepare_result_fn=assemble_prepare_result`
- documented test intent clearly without renaming files in this commit:
  - `test_prepare_result_assembly_module.py` covers direct module-level schema/result behavior
  - `test_prepare_stage_result_assembly.py` isolates stage orchestration by stubbing only the single result-assembly seam
- recorded that public workflow behavior and `scraper/pipeline/services/prepare_execution.py` behavior remain unchanged
- recorded the next recommended follow-up branch:
  - taxonomy/manufacturer-enrichment orchestration extraction
- reviewed `README.md` and left it unchanged because it does not describe the old internal ownership incorrectly

Commands run:
- `rg -n "prepare_stage.py|prepare_result_assembly|SchemaMatcher|schema_matcher_factory|assemble_prepare_result_fn|scope defined|Proposed extracted module|test_prepare_stage_result_assembly|test_prepare_result_assembly_module|taxonomy/enrichment" PLAN.md DOCUMENTATION.md README.md`
- `Get-Content PLAN.md | Select-Object -Skip 390 -First 90`
- `Get-Content DOCUMENTATION.md -TotalCount 120`
- `Get-Content README.md -TotalCount 220`

Validation:
- control docs now describe the landed prepare-stage/result-assembly ownership precisely
- no stale active-state wording remains in the branch-scope section implying that `prepare_stage.py` still constructs `SchemaMatcher`
- `README.md` did not require changes
- no Python files changed
- no test files changed
- no public entrypoint changed

## 2026-04-01 - Collapse prepare-stage result assembly to one injected seam

Goal:
- reduce the deterministic result-assembly dependency surface in `execute_prepare_stage(...)` to one injected callable
- remove the stage-level low-level schema-matcher injection now that result assembly is extracted
- keep workflow, prepare execution, and outward stage behavior unchanged

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `scraper/pipeline/prepare_result_assembly.py`
- `scraper/pipeline/prepare_stage.py`
- `scraper/pipeline/tests/test_prepare_stage_result_assembly.py`
- `scraper/pipeline/tests/test_prepare_result_assembly_module.py`
- `scraper/pipeline/tests/test_provider_selection.py`

Changes:
- `execute_prepare_stage(...)` now exposes one deterministic assembly seam:
  - `assemble_prepare_result_fn=assemble_prepare_result`
- removed the old lower-level stage injection:
  - `schema_matcher_factory`
- `prepare_stage.py` no longer imports or constructs `SchemaMatcher`
- `prepare_result_assembly.py` now owns schema-matcher construction internally through its own defaulted `schema_matcher_factory`
- direct tests continue to target `prepare_result_assembly.py` for schema/result behavior
- stage tests in `test_prepare_stage_result_assembly.py` now stub only `assemble_prepare_result_fn` when isolating stage orchestration
- provider-selection tests were updated to stub the single result-assembly seam instead of a low-level schema matcher
- control docs now reflect the landed names:
  - landed result type: `PrepareResultAssemblyResult`
  - landed stage injection boundary: `assemble_prepare_result_fn`
  - no landed `PrepareResultAssemblyInput` type exists in the current branch

Old vs new stage signature summary:
- old:
  - `execute_prepare_stage(..., schema_matcher_factory=SchemaMatcher, ...)`
- new:
  - `execute_prepare_stage(..., assemble_prepare_result_fn=assemble_prepare_result, ...)`

Commands run:
- `Get-Content scraper/pipeline/prepare_stage.py`
- `Get-Content scraper/pipeline/prepare_result_assembly.py`
- `Get-Content scraper/pipeline/tests/test_provider_selection.py`
- `Get-Content scraper/pipeline/tests/test_prepare_stage_result_assembly.py`
- `python -m pytest -q pipeline/tests/test_provider_selection.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_workflow.py -k "prepare"` from `scraper/`
- `python -m pytest -q pipeline/tests/test_services.py -k "prepare_product"` from `scraper/`

Validation:
- direct result-assembly tests still pass
- stage orchestration tests now isolate only the single result-assembly seam
- provider-selection regressions still pass
- prepare-focused workflow and service regressions still pass
- no public workflow or service entrypoint changed

## 2026-04-01 - Wire prepare stage to the result-assembly seam

Goal:
- route `scraper/pipeline/prepare_stage.py` through the new deterministic result-assembly module
- remove the now-redundant inline schema/result assembly block from `prepare_stage.py`
- preserve the outward `execute_prepare_stage(...)` payload, prepare/workflow behavior, and prepare/render ownership boundaries

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/prepare_stage.py`

Changes:
- wired `prepare_stage.py` to `assemble_prepare_result(...)` in `scraper/pipeline/prepare_result_assembly.py`
- removed the inline deterministic assembly block from `prepare_stage.py` that previously owned:
  - effective spec-section shaping for schema selection
  - preferred schema-source-file computation
  - `schema_matcher.match(...)` orchestration
  - deterministic row-building through `build_row(...)`
  - normalized payload assembly
  - deterministic report payload assembly
- `prepare_stage.py` now:
  - keeps gallery and Besco orchestration
  - keeps taxonomy resolution
  - keeps manufacturer enrichment orchestration
  - prepares the assembly inputs and delegates deterministic result assembly through the new seam
  - keeps the outward dict-shaped return payload compatible with `prepare_execution.py`
- removed the now-redundant local `build_identity_checks(...)` helper from `prepare_stage.py` because the assembly seam owns that report field composition now

Commands run:
- `Get-Content scraper/pipeline/prepare_stage.py`
- `python -m pytest -q pipeline/tests/test_prepare_result_assembly_module.py pipeline/tests/test_prepare_stage_result_assembly.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_provider_selection.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_workflow.py -k "prepare"` from `scraper/`
- `python -m pytest -q pipeline/tests/test_services.py -k "prepare_product"` from `scraper/`

Validation:
- direct seam tests still pass
- existing prepare-stage characterization tests still pass
- provider-selection regressions still pass with the stage routed through the seam
- prepare-focused workflow and service regressions still pass
- outward `execute_prepare_stage(...)` return keys remain unchanged

Remaining deterministic assembly logic intentionally left in `prepare_stage.py`:
- none from the extracted schema/result assembly block
- only upstream orchestration remains there for gallery/Besco handling, taxonomy resolution, manufacturer enrichment, and preparation of inputs for result assembly

## 2026-04-01 - Add standalone prepare result-assembly seam without wiring it

Goal:
- add the extracted deterministic prepare result-assembly module for the current branch
- keep `scraper/pipeline/prepare_stage.py` behavior unchanged in this commit by not wiring the new seam yet
- pin the new module directly with focused tests while preserving the existing prepare-stage regressions

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/prepare_result_assembly.py`
- `scraper/pipeline/tests/test_prepare_result_assembly_module.py`

Changes:
- added `scraper/pipeline/prepare_result_assembly.py`
- added the new internal typed result:
  - `PrepareResultAssemblyResult`
- added the new internal seam:
  - `assemble_prepare_result(...)`
- the new module now owns standalone logic for:
  - effective spec-section shaping used for schema selection
  - preferred schema-source-file computation
  - `schema_matcher.match(...)` orchestration
  - deterministic row-building through `build_row(...)`
  - normalized payload assembly
  - deterministic report payload assembly for prepare-stage outputs
- added focused direct tests for the seam in `scraper/pipeline/tests/test_prepare_result_assembly_module.py`

Intentional temporary duplication left for the next commit:
- `scraper/pipeline/prepare_stage.py` still contains the active inline deterministic schema/result assembly block
- `scraper/pipeline/prepare_result_assembly.py` currently mirrors that logic but is not called by `prepare_stage.py` yet
- `build_prepare_result_identity_checks(...)` currently duplicates the local `build_identity_checks(...)` helper shape from `prepare_stage.py`

Commands run:
- `Get-Content scraper/pipeline/tests/test_prepare_stage_result_assembly.py`
- `Get-Content scraper/pipeline/prepare_stage.py`
- `python -m pytest -q pipeline/tests/test_prepare_result_assembly_module.py pipeline/tests/test_prepare_stage_result_assembly.py` from `scraper/`

Validation:
- the new seam module is covered directly without changing production behavior
- existing prepare-stage characterization tests still pass unchanged
- this commit does not move taxonomy resolution, manufacturer enrichment, provider resolution, or artifact persistence

## 2026-04-01 - Freeze prepare-stage result assembly refactor scope

Goal:
- document the exact branch scope for `refactor/prepare-stage-result-assembly`
- update control docs first, before any Python extraction work
- keep this commit docs-only and avoid changing runtime behavior, tests, imports, workflow entrypoints, or artifact contracts

Scope framing:
- this section records planned branch work for extracting the deterministic schema-matching and normalized/report assembly seam out of `scraper/pipeline/prepare_stage.py`
- it is not a statement that the seam has already been extracted in the current runtime
- active runtime behavior remains unchanged in this commit

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`

Recorded scope:
- branch goal:
  - extract the deterministic schema-matching and normalized/report assembly seam out of `scraper/pipeline/prepare_stage.py` while preserving current runtime behavior
- exact non-goals:
  - no public workflow or CLI behavior change
  - no prepare/render ownership-boundary change
  - no output artifact path or filename change
  - no taxonomy-resolution extraction in this branch
  - no manufacturer-enrichment extraction in this branch
  - no provider-resolution reshuffle in this branch
  - no scrape-persistence extraction or path redesign in this branch
  - no render ownership change
  - no naming-polish cleanup in this branch
  - no split-task LLM handoff contract change
- proposed extracted module name:
  - `scraper/pipeline/prepare_result_assembly.py`
- proposed result types:
  - `PrepareResultAssemblyInput`
  - `PrepareResultAssemblyResult`
- what stays in `prepare_stage.py` after this branch:
  - provider-resolution orchestration
  - gallery download orchestration
  - section-image/Besco download orchestration
  - taxonomy resolution for now
  - manufacturer enrichment orchestration for now
  - scrape-persistence seam invocation through `scraper/pipeline/prepare_scrape_persistence.py`
  - the outward dict-shaped `execute_prepare_stage(...)` payload
- what leaves `prepare_stage.py` in this branch:
  - effective spec-section selection for deterministic schema matching
  - preferred schema-source-file selection
  - the `schema_matcher.match(...)` call and schema-candidate assembly
  - deterministic row and normalized payload assembly via `build_row(...)`
  - deterministic report payload assembly, including warning aggregation, diagnostics packaging, and `files_written` composition
- explicit branch boundary:
  - taxonomy resolution and manufacturer enrichment stay in `prepare_stage.py` for now
  - `prepare` remains scrape-only plus LLM-handoff-only
  - `render` ownership stays unchanged
  - `scraper/pipeline/services/prepare_execution.py` remains the owner of `work/{model}/llm/*`

Test strategy for the next commits:
- add focused unit coverage for the extracted result-assembly seam
- assert unchanged schema-match outputs, normalized payload shape, warning ordering, and report assembly behavior
- keep existing prepare/workflow/provider regressions as the behavioral backstop for Electronet, Skroutz, and supported manufacturer flows
- run targeted seam tests during each extraction step, then run the broader scraper suite before closing the branch

Commands run:
- `rg -n "prepare_stage|artifact persistence|schema-matching|normalized|report assembly|taxonomy|manufacturer enrichment" PLAN.md DOCUMENTATION.md README.md scraper/pipeline/prepare_stage.py`
- `Get-Content PLAN.md`
- `Get-Content DOCUMENTATION.md`
- `Get-Content README.md`
- `Get-Content scraper/pipeline/prepare_stage.py`

Validation:
- the new branch scope is now recorded in `PLAN.md`
- the engineering log now captures the branch goal, non-goals, proposed module and result types, retained ownership, and planned test strategy
- this commit remains docs-only and does not modify Python files or tests
- `README.md` did not require changes for this scope-freeze commit

## 2026-04-01 - Finalize scrape persistence extraction docs

Goal:
- mark the scrape persistence extraction branch scope complete in the control docs
- make the landed current-state ownership boundary unambiguous
- keep this commit docs-only with no runtime-code changes

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`

Current-state guidance:
- scrape artifact persistence now lives in `scraper/pipeline/prepare_scrape_persistence.py`
- `scraper/pipeline/prepare_stage.py` now owns prepare-stage orchestration only:
  - it resolves provider-backed input through the existing provider seam
  - it computes gallery/besco selection, taxonomy, schema match, normalized payloads, and report payloads
  - it delegates scrape-stage persistence through one typed persistence seam call
- `scraper/pipeline/services/prepare_execution.py` still owns all `work/{model}/llm/*` writes:
  - `task_manifest.json`
  - `intro_text.context.json`
  - `intro_text.prompt.txt`
  - `seo_meta.context.json`
  - `seo_meta.prompt.txt`
  - output placeholders under `work/{model}/llm/`
- current scrape artifact ownership under `work/{model}/scrape/` remains:
  - `{model}.raw.html`
  - `{model}.source.json`
  - `{model}.normalized.json`
  - `{model}.report.json`
  - `bescos_raw.json` when section extraction produces it
  - scrape-stage supporting assets that already belong under `work/{model}/scrape/`

Validation:
- `PLAN.md` now marks the scrape persistence extraction scope complete
- active docs now state the landed ownership boundary directly
- this commit is docs-only and does not modify runtime code

## 2026-04-01 - Narrow the prepare-stage scrape persistence seam

Goal:
- reduce the scrape persistence seam to one clear typed persistence call from `prepare_stage.py`
- remove remaining write-oriented local variables and persistence choreography from the stage implementation
- keep the outward `execute_prepare_stage(...)` payload and all public workflow behavior unchanged

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/characteristics_pipeline.py`
- `scraper/pipeline/mapping.py`
- `scraper/pipeline/prepare_scrape_persistence.py`
- `scraper/pipeline/prepare_stage.py`
- `scraper/pipeline/tests/test_prepare_scrape_persistence.py`
- `scraper/pipeline/tests/test_provider_selection.py`

Changes:
- `prepare_stage.py` now builds one `PrepareScrapePersistenceInput` object, fills it as state is computed, and calls `persist_prepare_scrape_artifacts(...)` once
- path derivation for the canonical scrape artifacts now lives on `PrepareScrapePersistenceInput` via typed properties instead of ad hoc stage-local path variables
- `PrepareScrapePersistenceResult` was reduced to the canonical persisted scrape paths only
- removed write-tracking fields from the persistence result because the stage and direct persistence tests only need the canonical paths and on-disk outputs
- `mapping.build_row(...)` and `characteristics_pipeline.build_characteristics_for_product(...)` now accept optional in-memory raw HTML so prepare-stage characteristics generation no longer requires an early raw-html disk write before the final scrape persistence call
- prepare-stage orchestration tests now target the injected persistence seam instead of asserting file-writing internals

Old vs new seam:
- old seam:
  - `prepare_stage.py` derived scrape paths locally
  - staged persistence happened in two phases
  - prepare-stage tests still indirectly asserted persisted files
- new seam:
  - one typed `PrepareScrapePersistenceInput`
  - one `persist_prepare_scrape_artifacts(...)` call
  - one small `PrepareScrapePersistenceResult`
  - prepare-stage tests assert persistence orchestration through the seam

Commands run:
- `python -m pytest -q pipeline/tests/test_prepare_scrape_persistence.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_provider_selection.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_workflow.py -k "prepare"` from `scraper/`
- `python -m pytest -q pipeline/tests/test_services.py -k "prepare_product"` from `scraper/`

Validation:
- direct persistence tests still pass against the new module shape
- prepare-stage tests now assert the typed persistence seam is invoked once with the prepared scrape payload
- prepare-focused workflow and service regressions still pass
- public workflow behavior did not change

## 2026-04-01 - Wire prepare stage to the scrape persistence module

Goal:
- route `scraper/pipeline/prepare_stage.py` through the new scrape persistence module
- remove the now-redundant inline scrape write logic from `prepare_stage.py`
- preserve the prepare-stage outward payload, artifact paths, and downstream service/workflow behavior

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/prepare_scrape_persistence.py`
- `scraper/pipeline/prepare_stage.py`

Changes:
- wired `prepare_stage.py` to `persist_prepare_scrape_artifacts(...)`
- moved the active scrape artifact writes behind the new module for:
  - `{model}.raw.html`
  - `{model}.source.json`
  - `{model}.normalized.json`
  - `{model}.report.json`
  - `bescos_raw.json` cleanup and optional write
- removed the direct inline `write_text(...)` / `write_json(...)` scrape writes from `prepare_stage.py`
- kept the outward `execute_prepare_stage(...)` return payload stable:
  - `raw_html_path`
  - `source_json_path`
  - `normalized_json_path`
  - `report_json_path`
  - all existing stage result keys still return with the same meaning
- expanded `PrepareScrapePersistenceInput` so the same module can support:
  - the early raw-HTML write needed before characteristics generation reads `source.raw_html_path`
  - the final scrape bundle write for source, normalized, report, and optional `bescos_raw.json`

Compatibility behavior preserved intentionally:
- `prepare_stage.py` still computes prepare state, taxonomy, schema match, manufacturer enrichment, gallery selection, and besco selection exactly where it did before
- raw HTML is still persisted before downstream characteristics logic that reads `source.raw_html_path` from disk
- `prepare_execution.py` remains untouched
- `work/{model}/llm/*` ownership remains untouched
- provider-resolution, taxonomy, manufacturer, and schema logic remain untouched
- file names and locations under `work/{model}/scrape/` remain unchanged

Commands run:
- `python -m pytest -q pipeline/tests/test_prepare_scrape_persistence.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_provider_selection.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_workflow.py -k "prepare"` from `scraper/`
- `python -m pytest -q pipeline/tests/test_services.py -k "prepare_product"` from `scraper/`

Validation:
- new scrape persistence unit tests passed
- prepare-stage/provider-selection tests passed after the wiring change
- prepare-focused workflow and service regression tests passed
- `prepare_stage.py` no longer owns direct scrape artifact writes inline
- outward stage behavior remained stable in the targeted regression set

## 2026-04-01 - Add standalone prepare scrape persistence module and unit tests

Goal:
- add the new scrape artifact persistence module for the branch without wiring it into `prepare_stage.py` yet
- introduce the preferred typed input/result objects for the persistence seam
- add focused unit tests that freeze the current scrape-write contract before the follow-up integration commit

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `scraper/pipeline/prepare_scrape_persistence.py`
- `scraper/pipeline/tests/test_prepare_scrape_persistence.py`

Changes:
- added `scraper/pipeline/prepare_scrape_persistence.py`
- added typed persistence models:
  - `PrepareScrapePersistenceInput`
  - `PrepareScrapePersistenceResult`
- added `persist_prepare_scrape_artifacts(...)` as a standalone persistence helper that currently owns:
  - path derivation for `{model}.raw.html`
  - path derivation for `{model}.source.json`
  - path derivation for `{model}.normalized.json`
  - path derivation for `{model}.report.json`
  - cleanup of stale `bescos_raw.json`
  - optional write of `bescos_raw.json`
- updated the branch-scope note in `PLAN.md` so the proposed module/type names match the landed preferred names for this branch

Intentional temporary duplication left for the next commit:
- `scraper/pipeline/prepare_stage.py` still performs the active scrape persistence inline
- the new persistence module mirrors that write surface but is not wired in yet
- `prepare_execution.py` remains untouched in this commit by branch rule

Commands run:
- `Get-Content scraper/pipeline/prepare_stage.py`
- `Get-Content scraper/pipeline/services/execution_models.py`
- `Get-Content scraper/pipeline/services/models.py`
- `Get-Content scraper/pipeline/utils.py`
- `python -m pytest -q pipeline/tests/test_prepare_scrape_persistence.py` from `scraper/`

Validation:
- focused unit tests cover canonical scrape file writes, exact filenames, JSON/text content behavior, stale `bescos_raw.json` cleanup, and no writes under `llm/`
- `prepare_stage.py` behavior is unchanged in this commit because the new module is not wired yet

## 2026-04-01 - Freeze prepare-stage artifact persistence refactor scope

Goal:
- document the exact branch scope for `refactor/prepare-stage-artifact-persistence`
- update control docs first, before any Python extraction work
- keep this commit docs-only and avoid changing runtime behavior, tests, imports, workflow entrypoints, or artifact contracts

Scope framing:
- this section records planned branch work for extracting all scrape-stage artifact persistence out of `scraper/pipeline/prepare_stage.py`
- it is not a statement that the persistence seam has already been extracted in the current runtime
- active runtime behavior remains unchanged in this commit

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`

Recorded scope:
- exact branch goal:
  - extract all scrape artifact persistence out of `scraper/pipeline/prepare_stage.py` into a dedicated module while preserving current runtime behavior
- exact non-goals:
  - no public workflow or CLI behavior change
  - no `work/{model}/llm/*` ownership change
  - no provider-resolution ownership change
  - no taxonomy/manufacturer/schema logic change
  - no stage result payload-key redesign
  - no artifact path or filename change
  - no candidate-stage or publish-stage persistence extraction
- explicit scrape-stage writes that move together in this branch:
  - `work/{model}/scrape/{model}.raw.html`
  - `work/{model}/scrape/{model}.source.json`
  - `work/{model}/scrape/{model}.normalized.json`
  - `work/{model}/scrape/{model}.report.json`
  - scrape-stage supporting assets and auxiliary artifacts currently written under `work/{model}/scrape/`
- proposed extracted module name:
  - `scraper/pipeline/prepare_artifact_persistence.py`
- proposed typed persistence names:
  - `PrepareArtifactPersistenceInput`
  - `PrepareArtifactPersistenceResult`
- explicit ownership boundary captured in `PLAN.md`:
  - `scraper/pipeline/services/prepare_execution.py` remains responsible for all `work/{model}/llm/*` task-manifest, context, prompt, and LLM-handoff writes
- invariants recorded in `PLAN.md`:
  - prepare remains scrape-only plus LLM-handoff-only; render remains the sole owner of candidate and publish outputs
  - provider-resolution ownership does not move in this branch
  - taxonomy/manufacturer/schema logic does not move in this branch
  - stage result payload keys stay unchanged
  - scrape artifact paths and filenames stay unchanged
  - warning/error behavior must stay unchanged unless tests prove accidental drift
- follow-up branch candidates recorded:
  - schema-matching or taxonomy-adjacent prepare-stage seam extraction
  - typed prepare-stage result models
  - regression hardening around warning/error text and scrape-artifact path invariants

Commands run:
- `Get-ChildItem -Name`
- `Get-Content PLAN.md`
- `Get-Content DOCUMENTATION.md`
- `Get-Content README.md`

Validation:
- scope is now documented in `PLAN.md` and logged in `DOCUMENTATION.md`
- this commit remains docs-only and does not modify Python files, tests, imports, or runtime behavior
- `README.md` did not require changes for this scope-freeze commit

## 2026-04-01 - Freeze prepare-stage provider-resolution refactor scope

Goal:
- document the exact branch scope for `refactor/prepare-stage-provider-resolution`
- update control docs first, before any Python extraction work
- keep this commit docs-only and avoid changing runtime behavior, tests, imports, or workflow entrypoints

Scope framing:
- this section records planned branch work for extracting the provider-resolution seam out of `scraper/pipeline/prepare_stage.py`
- it is not a statement that the seam has already been extracted in the current runtime
- active runtime behavior remains unchanged in this commit

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`

Recorded scope:
- branch goal:
  - extract the provider-resolution seam out of `scraper/pipeline/prepare_stage.py` first, without changing observable behavior
- concrete seam responsibilities:
  - source detection
  - runtime provider registry bootstrap
  - source-to-`provider_id` mapping
  - `registry.require(...)`
  - `provider.fetch_snapshot(...)`
  - `provider.normalize(...)`
  - conversion from `ProviderResult` into the existing local fetch/parsed shape
  - final URL scope validation
  - source-specific product-page checks and operator hints that currently run before gallery/taxonomy/schema work
- landed extracted module name:
  - `scraper/pipeline/prepare_provider_resolution.py`
- landed seam result type:
  - `PrepareProviderResolutionResult`
  - landed fields: `source`, `provider_id`, `fetch`, `parsed`
- invariants recorded in `PLAN.md`:
  - public workflow entrypoint and CLI behavior stay unchanged
  - prepare/render ownership boundaries stay unchanged
  - output artifact paths stay unchanged
  - artifact persistence is not extracted in this branch
  - schema matching is not extracted in this branch
  - the split-task LLM handoff contract stays unchanged
  - supported-source behavior and current warning/error behavior stay unchanged
- next-commit test strategy:
  - add focused regression coverage around source detection, provider selection, final URL validation, and pre-gallery source-specific page checks
  - keep prepare-stage and workflow regression meaning unchanged across Electronet, Skroutz, and supported manufacturer flows
  - use existing fixtures and workflow-oriented tests, then run the full scraper suite before branch completion
- planned follow-up branch after this one:
  - artifact persistence extraction

Commands run:
- `git status --short`
- `Get-Content PLAN.md`
- `Get-Content DOCUMENTATION.md`
- `Get-Content README.md`
- `rg -n "Branch scope|artifact persistence|provider-resolution|prepare_stage.py|typed execution results|metadata and error semantics hardening|Phase 4" PLAN.md DOCUMENTATION.md README.md`
- `Get-Content PLAN.md | Select-Object -Skip 240 -First 60`
- `Get-Content DOCUMENTATION.md | Select-Object -First 120`
- `git diff --stat`

Validation:
- scope is now documented in `PLAN.md` and logged in `DOCUMENTATION.md`
- this commit remains docs-only and does not modify Python files, tests, imports, or runtime behavior
- `README.md` did not require changes for this scope-freeze commit

## 2026-04-01 - Collapse prepare-stage provider injection surface

Goal:
- reduce `execute_prepare_stage(...)` to one provider-resolution seam injection
- align prepare-stage tests with the extracted seam instead of the old wide provider bootstrap injection surface
- reconcile the control docs with the landed module/type names from the earlier extraction commits

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `scraper/pipeline/prepare_stage.py`
- `scraper/pipeline/tests/test_provider_selection.py`

Changes:
- collapsed `execute_prepare_stage(...)` provider-resolution dependency injection to one callable:
  - old provider-resolution DI surface included:
    - `detect_source_fn`
    - `electronet_parser_factory`
    - `skroutz_parser_factory`
    - `manufacturer_parser_factory`
    - `bootstrap_provider_registry_fn`
    - `source_to_provider_id_fn`
  - new prepare-stage seam:
    - `resolve_prepare_provider_input_fn`
- kept `validate_url_scope_fn` in `execute_prepare_stage(...)` because the existing scrape report still records final URL scope validation details after the seam returns
- updated prepare-stage tests so stage-level stubbing now happens through `resolve_prepare_provider_input_fn` instead of stubbing provider bootstrap details directly
- reconciled branch-scope docs to the landed extraction names:
  - module: `scraper/pipeline/prepare_provider_resolution.py`
  - result type: `PrepareProviderResolutionResult`
- removed stale prepare-stage imports tied only to the old inline provider-resolution surface

Commands run:
- `rg -n "execute_prepare_stage\\(|resolve_prepare_provider_resolution|bootstrap_provider_registry_fn|source_to_provider_id_fn|detect_source_fn|validate_url_scope_fn|electronet_parser_factory|skroutz_parser_factory|manufacturer_parser_factory" scraper/pipeline/tests scraper/pipeline PLAN.md DOCUMENTATION.md README.md`
- `python -m pytest -q pipeline/tests/test_prepare_provider_resolution.py pipeline/tests/test_provider_selection.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_workflow.py -k "prepare_workflow or workflow_main_prepare or render_workflow_delegates_to_service_execution or workflow_main_render_routes_through_render_service"` from `scraper/`

Validation:
- extracted provider-resolution unit tests still exercise the dedicated module directly
- prepare-stage tests now stub only the single provider-resolution seam where stage isolation is needed
- workflow-facing behavior remains unchanged in the targeted regression coverage
- no public workflow entrypoint or artifact path changed in this commit

## 2026-04-01 - Finalize metadata and error semantics hardening docs

Goal:
- update active project docs after the landed metadata/error hardening work
- mark the `hardening/metadata-and-error-semantics` branch scope complete
- record the current runtime behavior for degraded prepare/render outcomes without changing runtime code in the same commit

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`

Current-state guidance added:
- no silent metadata write failures remain in active prepare/render paths
- prepare/render now distinguish:
  - full success: core stage result is known and required primary artifacts exist
  - degraded success / partial failure: core stage result is known, but metadata persistence or another secondary artifact/reporting side effect is missing
  - hard failure: the core stage outcome is not trustworthy or a required primary artifact is missing
- prepare degraded behavior:
  - metadata write failure after a known successful prepare returns a degraded `ServiceResult`
  - missing persisted metadata after an otherwise successful prepare is surfaced through `run.warnings`, `run.error_code`, `run.error_detail`, and `artifacts.metadata_path = None`
- render degraded behavior:
  - metadata write failure after a known successful render returns a degraded `ServiceResult`
  - validation failure remains the primary render failure when known, and any metadata-write problem is added as a warning rather than replacing the validation semantics
  - missing persisted metadata after an otherwise known render result is surfaced through `run.warnings`, `run.error_code`, `run.error_detail`, and `artifacts.metadata_path = None`
- operator-visible workflow behavior under degraded conditions remains stable:
  - workflow prepare/render keep the same public command surface
  - operator summaries still print candidate/validation/artifact paths when those artifacts exist
  - when metadata is unavailable on a degraded result, workflow output shows `Metadata path: None` instead of silently implying the file exists
- artifact absence rules now distinguish:
  - missing primary prepare/render artifacts -> hard failure
  - missing metadata artifact after a known core outcome -> degraded result

Commands run:
- `rg -n "silent metadata|partial failure|degraded success|metadata path" PLAN.md DOCUMENTATION.md`
- `python -m pytest -q` from `scraper/`

Validation:
- active docs now reflect the landed metadata/error semantics rather than the old planned branch state
- this commit is docs-only and does not modify runtime code

## 2026-03-31 - Freeze metadata and error semantics hardening scope

Goal:
- document the exact scope for `hardening/metadata-and-error-semantics`
- keep this commit docs-only and avoid any runtime, import, parser, CLI, provider, or test changes
- preserve current workflow-facing behavior while scoping the future metadata/error hardening work

Scope framing:
- this section records planned branch work for metadata and error semantics hardening
- it is not a statement that the hardening is already implemented in the current runtime
- active runtime behavior remains unchanged in this commit

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`

Changes:
- added a `PLAN.md` branch-scope section for `metadata and error semantics hardening`
- recorded the target end state:
  - no silent metadata write failure
  - prepare/render expose consistent partial-failure semantics
  - artifact absence is surfaced consistently
  - workflow-facing behavior remains stable unless the run truly fails
- recorded the explicit non-goals:
  - no `prepare_stage.py` decomposition
  - no typed-result redesign beyond the existing `RunMetadata`, `RunArtifacts`, and `ServiceResult` models
  - no workflow parser or CLI changes
  - no provider routing changes

Commands run:
- `git status --short`
- `Get-Content -Raw PLAN.md`
- `Get-Content -Raw DOCUMENTATION.md`
- `rg -n "metadata and error semantics|silent metadata|partial-failure|non-goals" PLAN.md DOCUMENTATION.md`
- `git diff --stat`

Validation:
- scope is now documented in `PLAN.md` and logged in `DOCUMENTATION.md`
- this commit remains docs-only and does not modify Python files, tests, imports, or runtime behavior

## 2026-03-31 - Complete typed execution results migration

Goal:
- finish the `refactor/typed-execution-results` branch by removing the old prepare/render execution-result dict contract from the execution-to-service seam
- keep public workflow and service behavior unchanged while finalizing the internal typed execution models
- close the planning/docs loop for the completed branch scope

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `scraper/pipeline/services/execution_models.py`
- `scraper/pipeline/services/prepare_execution.py`
- `scraper/pipeline/services/prepare_service.py`
- `scraper/pipeline/services/render_execution.py`
- `scraper/pipeline/services/render_service.py`
- `scraper/pipeline/workflow.py`
- `scraper/pipeline/tests/test_services.py`
- `scraper/pipeline/tests/test_skroutz_integration.py`
- `scraper/pipeline/tests/test_skroutz_sections.py`
- `scraper/pipeline/tests/test_workflow.py`

Changes:
- completed the typed execution seam:
  - `execute_prepare_workflow(...)` now returns `PrepareExecutionResult`
  - `execute_render_workflow(...)` now returns `RenderExecutionResult`
- updated `prepare_service.py` and `render_service.py` to consume typed result attributes instead of the old execution-result dict contract
- removed the obsolete prepare/render execution-result dict assembly from the execution functions
- updated workflow and integration tests so the prepare/render execution seam is asserted through typed results only
- marked the `PLAN.md` typed-execution-results branch scope as completed

Intentionally retained untyped internals:
- `execute_prepare_stage(...)` still returns a mapping-like stage payload; the prepare executor preserves that as internal stage data because typing the stage itself is outside this branch scope
- render-side LLM input payloads, validation payloads, and normalized/extracted section payloads remain mapping/list structures inside `render_execution.py`; those are internal content payloads rather than the outward execution-result seam
- provider and publish execution payloads remain on their current contracts in this branch

Commands run:
- `Select-String -Path scraper\\pipeline\\**\\*.py -Pattern 'dict\\[str, Any\\]|result\\[\"'`
- `python -m compileall scraper/pipeline`
- `python -m pytest -q pipeline/tests/test_services.py` from `scraper/`
- `python -m pytest -q` from `scraper/`

Validation:
- prepare/render execution functions now return typed execution models directly
- prepare/render services no longer depend on the old execution-result dict contract
- full scraper test suite passed with no public workflow/service behavior changes

## 2026-03-31 - Freeze typed execution results branch scope

Goal:
- document the exact branch scope for converting prepare/render execution outputs from dict payloads into typed execution result objects
- keep this commit docs-only and avoid any runtime, import, or test changes
- preserve the current outward `ServiceResult` contract while scoping the internal execution typing work

Scope framing:
- this section records planned branch work for `refactor/typed-execution-results`
- it is not a statement that `execute_prepare_workflow(...)` or `execute_render_workflow(...)` already return typed result objects today
- active runtime behavior and runtime instructions remain unchanged in this commit

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`

Changes:
- added a `PLAN.md` branch-scope section for `typed execution results`
- recorded the target end state:
  - `execute_prepare_workflow(...)` returns `PrepareExecutionResult`
  - `execute_render_workflow(...)` returns `RenderExecutionResult`
  - `prepare_service.py` and `render_service.py` stop indexing execution results through `result["..."]` keys
  - the outward `ServiceResult` contract remains stable
- recorded the explicit non-goals:
  - no `prepare_stage.py` decomposition
  - no metadata semantics redesign
  - no workflow CLI behavior changes
  - no provider behavior changes
  - no service error-policy redesign

Commands run:
- `git status --short`
- `Get-Content PLAN.md`
- `Get-Content DOCUMENTATION.md`
- `rg -n "typed execution results|PrepareExecutionResult|RenderExecutionResult|prepare_service.py|render_service.py|ServiceResult|branch scope|non-goals" PLAN.md DOCUMENTATION.md`
- `rg -n "execute_prepare_workflow|execute_render_workflow|PrepareExecutionResult|RenderExecutionResult" scraper PLAN.md DOCUMENTATION.md`
- `Get-Content scraper/pipeline/services/prepare_service.py`
- `Get-Content scraper/pipeline/services/render_service.py`

Validation:
- scope is now documented in `PLAN.md` without changing active runtime instructions
- this commit remains docs-only and does not modify Python files, tests, imports, or runtime behavior

## 2026-03-31 - Align active docs with workflow-only runtime

Goal:
- make active documentation describe only the surviving workflow-only runtime after the legacy entrypoints were removed
- keep historical pre-cleanup references available only as clearly historical engineering-log evidence
- avoid changing runtime code in the same commit

Files edited:
- `README.md`
- `PLAN.md`
- `DOCUMENTATION.md`

Changes:
- updated `README.md` so install, prepare, render, and test guidance all describe the workflow-only runtime
- added an explicit active-runtime note in `README.md` that `python -m pipeline.workflow` is the only public entrypoint
- named the removed legacy runtime surfaces in `README.md` as removed, not runnable
- updated `PLAN.md` so M37 is now completed
- updated `PLAN.md` top-level and milestone wording so removed `pipeline.cli`, `full_run.py`, `run_service.py`, and `run_execution.py` are treated as historical pre-M37 state rather than active runtime truth
- replaced the old planned M37 scope wording in `DOCUMENTATION.md` with completion wording for the workflow-only runtime and docs alignment
- clarified that any mentions below of removed legacy entrypoints remain only as historical engineering-log evidence

Active runtime truth after M37:
- public runtime entrypoint:
  - `python -m pipeline.workflow`
- public workflow commands:
  - `python -m pipeline.workflow prepare ...`
  - `python -m pipeline.workflow render --model {model}`
- active test command:
  - `cd scraper && python -m pytest -q`
- removed legacy runtime surfaces:
  - `python -m pipeline.cli`
  - `scraper/pipeline/full_run.py`
  - `scraper/pipeline/services/run_service.py`
  - `scraper/pipeline/services/run_execution.py`

Historical note:
- references below to `pipeline.cli`, `execute_full_run(...)`, `run_service.py`, or `run_execution.py` are retained only as historical pre-M37 execution evidence unless a section explicitly states current guidance

Commands run:
- `rg -n "python -m pipeline\\.cli|execute_full_run|run_service|run_execution|pipeline\\.workflow|prepare|render|pytest -q" README.md PLAN.md DOCUMENTATION.md docs archive -S`
- `Get-Content README.md`
- `Get-Content PLAN.md`
- `Get-Content DOCUMENTATION.md | Select-Object -First 260`

Validation:
- active docs now describe only the surviving workflow prepare/render interface
- historical references to removed entrypoints remain only in clearly historical milestone/context wording

## 2026-03-31 - Freeze workflow-only cleanup branch scope (historical pre-completion note)

Goal:
- record the exact branch cleanup scope for making `pipeline.workflow` the only public entrypoint
- keep this commit documentation-only and avoid changing active runtime truth before the cleanup lands
- leave `README.md` untouched until the runtime deletion commit makes the new entrypoint story true

Scope framing:
- this section records planned cleanup work for branch `cleanup/workflow-single-entrypoint`
- it is not a statement that the current runtime already removed `pipeline.cli`, `full_run.py`, `run_service.py`, or `run_execution.py`
- active runtime guidance remains unchanged in this commit so docs do not get ahead of code

Files planned for deletion when the cleanup lands:
- `scraper/pipeline/cli.py`
- `scraper/pipeline/full_run.py`
- `scraper/pipeline/services/run_service.py`
- `scraper/pipeline/services/run_execution.py`

Files planned for rewrite when the cleanup lands:
- `scraper/pipeline/workflow.py`
- `scraper/pipeline/services/__init__.py`
- `scraper/pipeline/tests/test_workflow.py`
- `scraper/pipeline/tests/test_provider_selection.py`
- `scraper/pipeline/tests/test_services.py`
- `scraper/pipeline/tests/test_skroutz_integration.py`
- `README.md`
- `PLAN.md`
- `DOCUMENTATION.md`

Tests planned for migration when the cleanup lands:
- `scraper/pipeline/tests/test_workflow.py`
  - migrate `execute_full_run(...)` coverage to the surviving `pipeline.workflow` prepare/render entrypoints and their direct orchestration seams
- `scraper/pipeline/tests/test_provider_selection.py`
  - move supported-source and injected-provider assertions off `execute_full_run(...)` and onto provider-registry bootstrap plus prepare-stage/workflow execution
- `scraper/pipeline/tests/test_services.py`
  - drop `run_service` / `run_execution` ownership checks and keep coverage focused on the surviving prepare, render, and publish service layers
- `scraper/pipeline/tests/test_skroutz_integration.py`
  - replace the direct `pipeline.cli` validation dependency with whichever validation seam survives under the workflow-only entrypoint

README timing rule:
- runtime instructions in `README.md` must be updated only after the deletion lands, in the same implementation window or immediately after, so active docs never present a non-existent or not-yet-true workflow-only state

Branch acceptance checks:
- this scope-freeze commit must remain docs-only:
  - `git diff --stat` shows only `PLAN.md` and `DOCUMENTATION.md`
- cleanup implementation acceptance after the deletion lands:
  - `python -m pipeline.workflow prepare --help` and `python -m pipeline.workflow render --help` remain the public runtime help surfaces
  - no active runtime docs present `python -m pipeline.cli ...` as runnable
  - provider-selection and supported-source coverage no longer calls `execute_full_run(...)`
  - the legacy files listed above are removed rather than left as alternate public entrypoints

Commands run:
- `git status --short`
- `Get-Content PLAN.md`
- `Get-Content DOCUMENTATION.md`
- `rg -n "pipeline\\.cli|execute_full_run|run_service|run_execution|workflow-only|branch scope|cleanup scope|M36|Phase 4" PLAN.md DOCUMENTATION.md -S`
- `Get-Content PLAN.md | Select-Object -Last 220`
- `Get-Content DOCUMENTATION.md | Select-Object -First 220`
- `rg -n "pipeline\\.cli|execute_full_run|run_service|run_execution|full_run\\.py" scraper/pipeline/tests scraper/pipeline README.md -S`
- `rg --files scraper/pipeline/tests`

Validation:
- documented the future workflow-only cleanup scope without changing runtime code, imports, tests, or active README instructions
- kept the scope explicitly framed as planned branch work instead of current runtime truth at the time

## 2026-03-30 - Add minimal GitHub Actions scraper test workflow

Goal:
- add the smallest GitHub Actions workflow that matches the documented scraper test path
- keep CI setup aligned with the root README install and test commands
- avoid any runtime-code changes in the same commit

Files edited:
- `.github/workflows/tests.yml`
- `DOCUMENTATION.md`

Changes:
- added `.github/workflows/tests.yml`
- configured the workflow to trigger on:
  - `push`
  - `pull_request`
- configured a single `ubuntu-latest` job
- configured Python setup through `actions/setup-python@v5` with Python `3.11`
- installed dependencies from repo-root `requirements.txt`
- installed Playwright Chromium with `python -m playwright install chromium`
- ran the test suite from `scraper/` with `python -m pytest -q`
- kept the workflow minimal and aligned with the README command sequence as closely as possible

Assumptions:
- GitHub-hosted Ubuntu runners provide the system libraries Playwright Chromium needs for this repo's current test suite
- the repo-root `requirements.txt` remains the canonical dependency file for CI, matching the current README guidance

Commands run:
- `Get-Content README.md`
- `Get-Content DOCUMENTATION.md | Select-Object -First 120`
- `rg -n "CI|GitHub Actions|workflow|tests.yml|Phase 4|pending" PLAN.md IMPLEMENT.md DOCUMENTATION.md README.md -S`
- `Get-Content .github/workflows/tests.yml`
- `py -3.12 -m pip install PyYAML --target %TEMP%\\product-agent-yamlcheck`
- temporary Python validation of `.github/workflows/tests.yml` via `yaml.safe_load(...)`
- temporary removal of `%TEMP%\\product-agent-yamlcheck`
- `git diff --check`

Validation:
- workflow YAML syntax parsed successfully via a temporary isolated `PyYAML` install and `yaml.safe_load(...)`
- quoted the top-level `"on"` key so the workflow remains GitHub-valid and also parses cleanly under generic YAML tooling
- validation in this commit was limited to workflow syntax and control-doc accuracy because no runtime code changed

Deferred:
- no runtime code changes were made
- no test files were changed
- no expansion into broader CI features such as caching, matrix builds, or artifact uploads

## 2026-03-30 - Add stable service error taxonomy and workflow exit mapping

Goal:
- replace exception-type-name service errors with stable semantic service codes
- map low-level exceptions to those codes at the service boundary
- make workflow exit behavior explicit and stable
- persist stable semantic error codes in run metadata

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `scraper/pipeline/services/__init__.py`
- `scraper/pipeline/services/errors.py`
- `scraper/pipeline/services/prepare_execution.py`
- `scraper/pipeline/services/prepare_service.py`
- `scraper/pipeline/services/render_execution.py`
- `scraper/pipeline/services/render_service.py`
- `scraper/pipeline/services/run_execution.py`
- `scraper/pipeline/services/run_service.py`
- `scraper/pipeline/tests/test_services.py`
- `scraper/pipeline/tests/test_workflow.py`
- `scraper/pipeline/workflow.py`

Changes:
- added stable semantic service error codes in `scraper/pipeline/services/errors.py`:
  - `missing_artifact`
  - `provider_failure`
  - `parse_failure`
  - `validation_failure`
  - `publish_failure`
  - `unexpected_failure`
- extended `ServiceError` to carry:
  - `code`
  - `message`
  - `cause`
  - `retryable`
  - `details`
- added a single service-boundary mapper that converts low-level exceptions into stable service errors:
  - `FileNotFoundError` -> `missing_artifact`
  - provider errors during fetch/load stages -> `provider_failure`
  - provider normalization failures and known parse/section failures -> `parse_failure`
  - render-stage `OSError` publish failures -> `publish_failure`
  - everything else -> `unexpected_failure`
- updated `prepare_service.py`, `render_service.py`, and `run_service.py` to wrap failures through the stable mapper instead of using `type(exc).__name__`
- updated `prepare_execution.py` and `render_execution.py` so prepare/render run metadata now store semantic `error_code` values
- updated render success/failure metadata handling so failed validation stores:
  - `error_code: validation_failure`
  - `error_detail: Candidate validation failed`
- updated full-run composition metadata in `run_execution.py` so stable child error codes and details propagate into the composed run result
- replaced the old workflow `ServiceError` exit handling with an explicit matrix in `scraper/pipeline/workflow.py`:
  - `missing_artifact` -> `3`
  - `provider_failure` -> `4`
  - `validation_failure` -> `5`
  - `parse_failure` -> `6`
  - `publish_failure` -> `7`
  - `unexpected_failure` -> `8`
- kept user-facing workflow stderr output readable by continuing to print the mapped service message rather than raw exception metadata
- updated service/workflow tests to assert stable public error behavior instead of exception-type-name internals

Intentional behavior changes:
- service-layer `error_code` values are now stable semantic codes rather than Python exception class names
- workflow exit codes now distinguish missing artifacts, provider failures, validation failures, parse failures, publish failures, and unexpected failures explicitly
- failed render validation now records `validation_failure` in run metadata instead of leaving `error_code` empty

Commands run:
- `Get-Content -Path scraper/pipeline/services/errors.py`
- `Get-Content -Path scraper/pipeline/services/prepare_service.py`
- `Get-Content -Path scraper/pipeline/services/render_service.py`
- `Get-Content -Path scraper/pipeline/services/run_service.py`
- `Get-Content -Path scraper/pipeline/services/run_execution.py`
- `Get-Content -Path scraper/pipeline/services/prepare_execution.py`
- `Get-Content -Path scraper/pipeline/services/render_execution.py`
- `Get-Content -Path scraper/pipeline/workflow.py`
- `Get-Content -Path scraper/pipeline/tests/test_services.py`
- `Get-Content -Path scraper/pipeline/tests/test_workflow.py`
- `rg -n "ServiceError|error_code|validation_failure|type\\(exc\\)__name__|exit_code" PLAN.md IMPLEMENT.md DOCUMENTATION.md scraper/pipeline scraper/pipeline/tests -S`
- `py -3.12 -m pytest -q pipeline/tests/test_services.py pipeline/tests/test_workflow.py` from `scraper/`
- `py -3.12 -m pytest -q pipeline/tests/test_services.py pipeline/tests/test_workflow.py pipeline/tests/test_provider_selection.py pipeline/tests/test_skroutz_integration.py pipeline/tests/test_skroutz_sections.py` from `scraper/`
- `git diff --check`

Validation:
- targeted service/workflow subset first:
  - `py -3.12 -m pytest -q pipeline/tests/test_services.py pipeline/tests/test_workflow.py` from `scraper/`
  - passed, `34 passed`
- broader affected suite:
  - `py -3.12 -m pytest -q pipeline/tests/test_services.py pipeline/tests/test_workflow.py pipeline/tests/test_provider_selection.py pipeline/tests/test_skroutz_integration.py pipeline/tests/test_skroutz_sections.py` from `scraper/`
  - passed, `54 passed`
- `git diff --check` passed

Deferred:
- no CI changes were made
- no provider bootstrap changes were made in this milestone
- no provider fetch/normalize internals were changed

Historical note:
- Sections below, including this M23 rename record, preserve `scrapper/` and `electronet_single_import` references only as execution evidence unless a section explicitly states current guidance.

## 2026-03-30 - Resolve providers through registry bootstrap

Goal:
- replace ad hoc provider-selection branches in orchestration with registry-driven resolution
- keep provider fetch and normalize behavior unchanged
- add public coverage for registry bootstrap and source-to-provider-id mapping

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/full_run.py`
- `scraper/pipeline/prepare_stage.py`
- `scraper/pipeline/providers/__init__.py`
- `scraper/pipeline/providers/registry.py`
- `scraper/pipeline/tests/test_provider_selection.py`
- `scraper/pipeline/tests/test_workflow.py`

Changes:
- extended `scraper/pipeline/providers/registry.py` with:
  - `bootstrap_runtime_provider_registry(...)`
  - `source_to_provider_id(...)`
- made `bootstrap_runtime_provider_registry(...)` the single runtime bootstrap point for the active providers:
  - `electronet`
  - `skroutz`
  - `manufacturer_tefal`
- updated `scraper/pipeline/prepare_stage.py` orchestration to:
  - build the provider registry once per run
  - map detected source to provider id through `source_to_provider_id(...)`
  - resolve the provider through `registry.require(...)`
- removed the active-path dependence on the old ad hoc provider-selection helper branches from orchestration
- kept the existing readable failure behavior for missing runtime providers by surfacing the registry-not-registered failure as a direct runtime error
- updated `scraper/pipeline/full_run.py` to pass the registry bootstrap and source-mapping functions through to the compatibility wrapper path
- re-exported the new bootstrap and mapping helpers from `scraper/pipeline/providers/__init__.py`
- updated tests so public registry behavior is what is asserted now:
  - bootstrap coverage
  - source mapping coverage
  - orchestration tests inject a registry instead of anchoring on private branch-selection internals

Intentional behavior changes:
- no provider fetch or normalize behavior changed
- no provider ids changed
- orchestration now depends on the public registry bootstrap plus mapping seam instead of private branch selection code

Commands run:
- `Get-Content -Raw scraper/pipeline/providers/registry.py`
- `Get-Content -Raw scraper/pipeline/prepare_stage.py`
- `Get-Content -Raw scraper/pipeline/tests/test_provider_selection.py`
- `rg -n "_resolve_provider_for_source|ProviderRegistry|provider_id|detect_source\\(|require\\(" scraper/pipeline scraper/pipeline/tests -S`
- `Get-Content -Raw scraper/pipeline/providers/__init__.py`
- `Get-Content -Raw scraper/pipeline/providers/electronet_provider.py`
- `Get-Content -Raw scraper/pipeline/providers/skroutz_provider.py`
- `Get-Content -Raw scraper/pipeline/providers/manufacturer_tefal_provider.py`
- `py -3.12 -m pytest -q pipeline/tests/test_provider_selection.py pipeline/tests/test_workflow.py` from `scraper/`
- `py -3.12 -m pytest -q pipeline/tests/test_provider_selection.py pipeline/tests/test_workflow.py pipeline/tests/test_services.py pipeline/tests/test_skroutz_integration.py pipeline/tests/test_skroutz_sections.py` from `scraper/`
- `rg -n "_resolve_provider_for_source|bootstrap_runtime_provider_registry|source_to_provider_id|registry.require\\(" scraper/pipeline scraper/pipeline/tests -S`

Validation:
- targeted provider/orchestration subset first:
  - `py -3.12 -m pytest -q pipeline/tests/test_provider_selection.py pipeline/tests/test_workflow.py` from `scraper/`
  - passed, `26 passed`
- broader affected suite:
  - `py -3.12 -m pytest -q pipeline/tests/test_provider_selection.py pipeline/tests/test_workflow.py pipeline/tests/test_services.py pipeline/tests/test_skroutz_integration.py pipeline/tests/test_skroutz_sections.py` from `scraper/`
  - passed, `47 passed`

Deferred:
- no error taxonomy changes were made
- no CI changes were made
- no provider fetch/normalize internals were changed

## 2026-03-30 - Make prepare scrape-only under the split-task workflow

Goal:
- finish the prepare/render execution seam after the split-LLM refactor
- make `prepare` scrape-only plus split-task handoff-only
- keep `render` as the sole owner of final candidate outputs and publish copy

Files added:
- `scraper/pipeline/prepare_stage.py`

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `README.md`
- `scraper/pipeline/full_run.py`
- `scraper/pipeline/services/prepare_execution.py`
- `scraper/pipeline/services/prepare_service.py`
- `scraper/pipeline/services/render_service.py`
- `scraper/pipeline/workflow.py`
- `scraper/pipeline/tests/test_services.py`
- `scraper/pipeline/tests/test_skroutz_integration.py`
- `scraper/pipeline/tests/test_workflow.py`

Changes:
- extracted the scrape-only execution core into `scraper/pipeline/prepare_stage.py`
- moved the active prepare-stage behavior there:
  - provider-backed fetch and normalization
  - scrape artifact writes under `work/{model}/scrape/`
  - deterministic normalization used by the split-task handoff
  - report generation
- kept candidate CSV generation out of the new prepare-stage core
- updated `scraper/pipeline/services/prepare_execution.py` so the active prepare path now calls `execute_prepare_stage(...)` directly instead of `execute_full_run(...)`
- removed the old nested scrape-dir workaround from prepare because the new core now writes directly to `work/{model}/scrape/`
- kept `scraper/pipeline/services/render_execution.py` as the only owner of:
  - `work/{model}/candidate/{model}.csv`
  - `work/{model}/candidate/{model}.normalized.json`
  - `work/{model}/candidate/{model}.validation.json`
  - `work/{model}/candidate/description.html`
  - `work/{model}/candidate/characteristics.html`
  - `products/{model}.csv`
- reduced `scraper/pipeline/full_run.py` to a thin compatibility wrapper:
  - it now delegates to `execute_prepare_stage(...)`
  - it performs the legacy direct CSV write only for explicit callers of `execute_full_run(...)`
  - it is no longer part of the active workflow prepare path
- updated `scraper/pipeline/workflow.py` so `prepare_workflow(...)` no longer imports or passes through `execute_full_run(...)`
- fixed `scraper/pipeline/services/prepare_service.py` so prepare result details come from the actual scrape result payload
- fixed `scraper/pipeline/services/render_service.py` so an unpublished render result can map `published_csv_path` as `None` safely
- updated `README.md` to describe the steady-state boundary:
  - prepare writes scrape plus split-task handoff artifacts only
  - render owns candidate outputs and publish copy

Intentional behavior changes:
- `python -m pipeline.workflow prepare ...` no longer creates `work/{model}/scrape/{model}.csv`
- `python -m pipeline.workflow prepare ...` does not create `work/{model}/candidate/{model}.csv`
- explicit compatibility calls to `execute_full_run(...)` still write a direct CSV for callers and tests that intentionally exercise the legacy full-run helper

Commands run:
- `Get-Content -Raw scraper/pipeline/services/prepare_execution.py`
- `Get-Content -Raw scraper/pipeline/services/render_execution.py`
- `Get-Content -Raw scraper/pipeline/services/prepare_service.py`
- `Get-Content -Raw scraper/pipeline/services/render_service.py`
- `Get-Content -Raw scraper/pipeline/services/run_execution.py`
- `Get-Content -Raw scraper/pipeline/workflow.py`
- `Get-Content -Raw scraper/pipeline/full_run.py`
- `Get-Content -Raw README.md`
- `Get-Content -Raw scraper/pipeline/tests/test_workflow.py`
- `Get-Content -Raw scraper/pipeline/tests/test_services.py`
- `Get-Content -Raw scraper/pipeline/tests/test_skroutz_integration.py`
- `Get-Content -Raw scraper/pipeline/cli.py`
- `rg -n "execute_full_run\\(|prepare_workflow\\(|execute_prepare_workflow\\(|candidate_csv_path|published_csv_path|work/\\{model\\}/scrape/\\{model\\}\\.csv|llm_output\\.json|intro_text\\.output|seo_meta\\.output" scraper/pipeline scraper/pipeline/tests README.md -S`
- `rg -n "_select_skroutz_image_backed_sections" scraper/pipeline/tests scraper/pipeline -S`
- `py -3.12 -m pytest -q pipeline/tests/test_workflow.py pipeline/tests/test_services.py` from `scraper/`
- `py -3.12 -m pytest -q pipeline/tests/test_workflow.py pipeline/tests/test_services.py pipeline/tests/test_skroutz_integration.py pipeline/tests/test_skroutz_sections.py pipeline/tests/test_provider_selection.py` from `scraper/`

Validation:
- smallest relevant subset first:
  - `py -3.12 -m pytest -q pipeline/tests/test_workflow.py pipeline/tests/test_services.py` from `scraper/`
  - passed, `27 passed`
- broader affected suite:
  - `py -3.12 -m pytest -q pipeline/tests/test_workflow.py pipeline/tests/test_services.py pipeline/tests/test_skroutz_integration.py pipeline/tests/test_skroutz_sections.py pipeline/tests/test_provider_selection.py` from `scraper/`
  - passed, `47 passed`

Deferred:
- no provider registry refactor was attempted
- no service error taxonomy work was attempted
- no CI changes were attempted
- `execute_full_run(...)` remains available as a thin compatibility wrapper for explicit direct callers rather than being removed entirely in this milestone

## 2026-03-30 - Define post-split prepare/render execution seam cleanup scope

Goal:
- document the complete post-split branch scope before any runtime code changes
- keep this commit docs-only and record the actual current prepare/render seam versus the intended steady-state ownership boundary
- avoid implying that the seam cleanup is already implemented

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `IMPLEMENT.md`

Current state:
- `README.md` still documents the two-stage `prepare` / `render` workflow under `scraper/`, including prepare handoff artifacts under `work/{model}/llm/` and render candidate artifacts under `work/{model}/candidate/`
- `scraper/pipeline/services/prepare_execution.py` still routes prepare through `execute_full_run(...)`
- `scraper/pipeline/full_run.py` still writes `{model}.csv` into the output root it is given, so the active prepare path still produces a scrape-stage CSV side effect under `work/{model}/scrape/`
- `scraper/pipeline/services/render_execution.py` already consumes split-task outputs:
  - `work/{model}/llm/intro_text.output.txt`
  - `work/{model}/llm/seo_meta.output.json`
- `scraper/pipeline/services/render_execution.py` already writes candidate-stage artifacts and publish copy:
  - `work/{model}/candidate/{model}.csv`
  - `work/{model}/candidate/{model}.validation.json`
  - `work/{model}/candidate/description.html`
  - `work/{model}/candidate/characteristics.html`
  - `products/{model}.csv` when validation passes

Target state:
- prepare owns scrape-only execution plus task handoff artifact creation
- render owns all final candidate and publish outputs
- the active prepare path no longer depends on `execute_full_run(...)`
- `full_run.py` is reduced to explicit full-run composition only, or retired from the active prepare path entirely

Ownership boundary after split-LLM:
- prepare-owned artifacts:
  - `work/{model}/scrape/{model}.raw.html`
  - `work/{model}/scrape/{model}.source.json`
  - `work/{model}/scrape/{model}.normalized.json`
  - `work/{model}/scrape/{model}.report.json`
  - scrape-stage downloaded assets and supporting scrape artifacts under `work/{model}/scrape/`
  - `work/{model}/llm/task_manifest.json`
  - `work/{model}/llm/intro_text.context.json`
  - `work/{model}/llm/intro_text.prompt.txt`
  - `work/{model}/llm/seo_meta.context.json`
  - `work/{model}/llm/seo_meta.prompt.txt`
- render-owned artifacts:
  - `work/{model}/candidate/{model}.csv`
  - `work/{model}/candidate/{model}.normalized.json`
  - `work/{model}/candidate/{model}.validation.json`
  - `work/{model}/candidate/description.html`
  - `work/{model}/candidate/characteristics.html`
  - `products/{model}.csv`
- LLM-stage handoff note:
  - the LLM still writes `work/{model}/llm/intro_text.output.txt` and `work/{model}/llm/seo_meta.output.json`, but prepare owns the contract and handoff scaffolding for those files rather than render owning their creation

Intended fate of `full_run.py`:
- `scraper/pipeline/full_run.py` should stop being the active implementation seam behind workflow prepare
- acceptable end states for this branch are:
  - a narrowed explicit full-run composition wrapper above scrape-only prepare plus render
  - retirement from the active prepare path if service-owned composition fully replaces it
- unacceptable end state:
  - any remaining prepare-stage dependency that keeps candidate CSV generation or other render/publish side effects inside the active prepare path

Out of scope for this branch:
- provider bootstrap changes
- service error taxonomy redesign
- CI changes

Commands run:
- `Get-Content -Raw PLAN.md`
- `Get-Content -Raw DOCUMENTATION.md`
- `Get-Content -Raw IMPLEMENT.md`
- `Get-Content -Raw scraper/pipeline/services/prepare_execution.py`
- `Get-Content -Raw scraper/pipeline/services/render_execution.py`
- `Get-Content -Raw scraper/pipeline/full_run.py`
- `Get-Content -Raw scraper/pipeline/workflow.py`
- `Get-Content -Raw README.md`
- `rg -n "execute_full_run\\(|llm_output\\.json|intro_text\\.output|seo_meta\\.output|candidate|validation|publish|csv_path" scraper/pipeline/services scraper/pipeline/full_run.py scraper/pipeline/workflow.py README.md -S`
- `rg --files scraper/pipeline/tests`
- `git status --short`
- `git diff --check -- PLAN.md DOCUMENTATION.md IMPLEMENT.md`

Validation:
- docs-only commit
- `git diff --check -- PLAN.md DOCUMENTATION.md IMPLEMENT.md` passed
- no runtime tests were run because this commit only updates control docs and must not include runtime or test changes

Deferred:
- no runtime code, tests, or README changes were made in this commit
- the prepare/render seam cleanup remains planned work only at this stage
- earlier M34 records remain preserved below as historical execution evidence for the split-task contract, even though the post-split execution seam cleanup is now tracked separately as pending work

## 2026-03-30 - Remove legacy combined LLM handoff and finalize split-task workflow

Goal:
- remove the temporary combined LLM compatibility path from prepare, render, validators, tests, and runtime docs
- leave the branch in its final steady state with split `intro_text` and `seo_meta` artifacts only
- align operator-facing docs with deterministic section rendering and the final failure policy

Files edited:
- `AGENTS.md`
- `README.md`
- `PLAN.md`
- `IMPLEMENT.md`
- `DOCUMENTATION.md`
- `scraper/pipeline/llm_contract.py`
- `scraper/pipeline/repo_paths.py`
- `scraper/pipeline/workflow.py`
- `scraper/pipeline/services/models.py`
- `scraper/pipeline/services/prepare_execution.py`
- `scraper/pipeline/services/prepare_service.py`
- `scraper/pipeline/services/render_execution.py`
- `scraper/pipeline/services/render_service.py`
- `scraper/pipeline/services/run_execution.py`
- `scraper/pipeline/tests/test_llm_contract.py`
- `scraper/pipeline/tests/test_services.py`
- `scraper/pipeline/tests/test_skroutz_integration.py`
- `scraper/pipeline/tests/test_skroutz_sections.py`
- `scraper/pipeline/tests/test_utils_support_paths.py`
- `scraper/pipeline/tests/test_workflow.py`

Files removed:
- `resources/prompts/master_prompt+.txt`
- `resources/schemas/compact_response.schema.json`

Changes:
- removed legacy combined prepare artifact generation:
  - `work/{model}/llm_context.json`
  - `work/{model}/prompt.txt`
- removed the legacy combined render input path:
  - `work/{model}/llm_output.json`
- simplified the active LLM contract in `scraper/pipeline/llm_contract.py` to split-task-only helpers and validators:
  - kept `build_intro_text_context(...)`
  - kept `build_seo_meta_context(...)`
  - kept `build_task_manifest(...)`
  - kept `validate_intro_text_output(...)`
  - kept `validate_seo_meta_output(...)`
  - removed the old combined-context builder and combined/legacy validators
- updated `scraper/pipeline/services/prepare_execution.py` so prepare now writes only:
  - `work/{model}/llm/task_manifest.json`
  - `work/{model}/llm/intro_text.context.json`
  - `work/{model}/llm/intro_text.prompt.txt`
  - `work/{model}/llm/seo_meta.context.json`
  - `work/{model}/llm/seo_meta.prompt.txt`
- updated the manifest to steady-state mode:
  - `prepare_mode: split_tasks`
  - removed compatibility metadata for legacy combined artifacts
- updated `scraper/pipeline/services/render_execution.py` so render now requires:
  - `work/{model}/llm/intro_text.output.txt`
  - `work/{model}/llm/seo_meta.output.json`
- removed the render fallback to legacy combined payloads and changed the missing-artifact error to the split-task-only path
- removed legacy artifact fields from service-layer artifact models and service result mapping
- retired the obsolete combined prompt/schema resources and removed their centralized path constants
- updated workflow CLI output to print only the split-task artifact paths
- updated `AGENTS.md` and `README.md` to describe the final runtime:
  - split prepare outputs
  - split LLM outputs
  - deterministic section rendering
  - section warning/failure policy
  - no LLM section-copy generation
- updated tests so final steady-state behavior is the only active runtime expectation

Legacy behavior removed:
- prepare no longer writes combined `llm_context.json` or `prompt.txt`
- render no longer accepts combined `llm_output.json`
- the LLM no longer owns:
  - `presentation.intro_html`
  - `presentation.sections[].title`
  - `presentation.sections[].body_html`
- the reduced combined prompt/schema resources are no longer part of the runtime

Commands run:
- `rg -n "llm_context\\.json|prompt\\.txt|llm_output\\.json|presentation\\.intro_html|presentation\\.sections|validate_llm_output|legacy|split_tasks_with_legacy_compatibility|intro_text\\.output|seo_meta\\.output|task_manifest" README.md PLAN.md DOCUMENTATION.md IMPLEMENT.md AGENTS.md scraper resources -S`
- `Get-Content scraper/pipeline/llm_contract.py`
- `Get-Content scraper/pipeline/services/prepare_execution.py`
- `Get-Content scraper/pipeline/services/render_execution.py`
- `Get-Content scraper/pipeline/services/models.py`
- `Get-Content scraper/pipeline/services/prepare_service.py`
- `Get-Content scraper/pipeline/services/render_service.py`
- `Get-Content scraper/pipeline/services/run_execution.py`
- `Get-Content scraper/pipeline/workflow.py`
- `Get-Content README.md`
- `Get-Content AGENTS.md`
- `Get-Content IMPLEMENT.md`
- `Get-Content scraper/pipeline/tests/test_llm_contract.py`
- `Get-Content scraper/pipeline/tests/test_services.py`
- `Get-Content scraper/pipeline/tests/test_workflow.py`
- `Get-Content scraper/pipeline/tests/test_skroutz_integration.py`
- `Get-Content scraper/pipeline/tests/test_skroutz_sections.py`
- `py -3.12 -m pytest -q pipeline/tests/test_llm_contract.py pipeline/tests/test_workflow.py pipeline/tests/test_services.py pipeline/tests/test_skroutz_integration.py pipeline/tests/test_skroutz_sections.py pipeline/tests/test_utils_support_paths.py` from `scraper/`
- `py -3.12 -m pytest -q` from `scraper/`

Validation:
- targeted cleanup-facing subset first:
  - `py -3.12 -m pytest -q pipeline/tests/test_llm_contract.py pipeline/tests/test_workflow.py pipeline/tests/test_services.py pipeline/tests/test_skroutz_integration.py pipeline/tests/test_skroutz_sections.py pipeline/tests/test_utils_support_paths.py` from `scraper/`
  - passed, `46 passed`
- full suite:
  - `py -3.12 -m pytest -q` from `scraper/`
  - passed, `120 passed`

Deferred:
- no provider-registry, CI, or unrelated service-layer refactors were attempted in this cleanup commit
- historical documentation below still mentions old combined artifacts as prior-state evidence and was not rewritten wholesale

## 2026-03-30 - Assemble description HTML from `intro_text` and deterministic sections

Goal:
- migrate render to the split-task outputs introduced in M30
- make final description HTML code-owned and assembled from plain-text `intro_text`, deterministic CTA data, and deterministic cleaned presentation sections
- keep the compatibility phase active by accepting legacy combined `llm_output.json` until final cleanup

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `scraper/pipeline/html_builders.py`
- `scraper/pipeline/llm_contract.py`
- `scraper/pipeline/mapping.py`
- `scraper/pipeline/services/render_execution.py`
- `scraper/pipeline/tests/test_llm_contract.py`
- `scraper/pipeline/tests/test_skroutz_integration.py`
- `scraper/pipeline/tests/test_skroutz_sections.py`
- `scraper/pipeline/tests/test_workflow.py`

Changes:
- updated `scraper/pipeline/services/render_execution.py` so render now prefers split-task outputs from `work/{model}/llm/`:
  - `intro_text.output.txt`
  - `seo_meta.output.json`
- kept compatibility with legacy `work/{model}/llm_output.json`:
  - legacy `product.meta_description` and `product.meta_keywords` are still accepted
  - legacy `presentation.intro_html` is reduced to plain text for the active render path
  - legacy section title/body content is no longer required or used for final description assembly
- replaced the active render-time LLM validation path in `scraper/pipeline/llm_contract.py`:
  - added split validators for `intro_text` and `seo_meta`
  - removed render-time dependence on LLM-owned section title/body validation
  - kept the old combined validator available only as legacy compatibility support for older tests and artifacts
- added `build_description_html_from_intro_and_sections(...)` in `scraper/pipeline/html_builders.py`
- updated `scraper/pipeline/mapping.py` so final description HTML is now assembled in code from:
  - plain-text `intro_text`
  - deterministic CTA text
  - deterministic cleaned presentation sections
- kept wrappers, classes, styles, and CTA/link rendering code-owned
- enforced deterministic section failure policy during render:
  - hard fail when source sections are missing entirely and sections were requested
  - hard fail when usable section count is `0` and sections were requested
  - hard fail when more than one requested section is classified `missing`
  - warn and continue when sections are `weak`
  - warn and continue when exactly one requested section is `missing`
- passed only `usable` deterministic sections into the final HTML renderer
- preserved source titles and sanitized source wording for section bodies; no section rewriting or LLM section generation remains in the active path
- normalized SEO keywords in `scraper/pipeline/mapping.py` so render now:
  - guarantees brand and model/MPN are present
  - collapses duplicate keywords
  - collapses singular/plural variants in code before CSV serialization
- preserved section-image wiring by original `source_index` so skipped weak sections do not shift later Besco image assignments
- wrote split/legacy mode details into render normalized artifacts and run metadata:
  - `llm_mode`
  - `llm_artifact_paths`
  - `presentation_sections`

Behavior changes:
- final `description` HTML is no longer sourced from LLM HTML sections in the active render path
- the intro paragraph now comes from plain-text LLM `intro_text` and is escaped into the existing wrapper structure in code
- deterministic section warnings now surface in render validation reports, including reduced-section cases during the compatibility phase
- legacy combined LLM outputs remain accepted intentionally, but only for intro/meta compatibility; section rendering is deterministic even when legacy artifacts are present
- compatibility fixture coverage now expects legacy render inputs to succeed when the active split-compatible validation rules are satisfied

Commands run:
- `rg -n "validate_llm_output|meta_keywords|build_description_html_from_llm|build_description_html|extract_presentation_blocks" scraper/pipeline -S`
- `Get-Content scraper/pipeline/services/render_execution.py`
- `Get-Content scraper/pipeline/html_builders.py`
- `Get-Content scraper/pipeline/mapping.py`
- `Get-Content scraper/pipeline/llm_contract.py`
- `Get-Content scraper/pipeline/presentation_sections.py`
- `Get-Content scraper/pipeline/tests/test_workflow.py`
- `Get-Content scraper/pipeline/tests/test_skroutz_sections.py`
- `Get-Content scraper/pipeline/tests/test_skroutz_integration.py`
- `py -3.12 -m pytest -q pipeline/tests/test_workflow.py pipeline/tests/test_llm_contract.py` from `scraper/`
- `py -3.12 -m pytest -q pipeline/tests/test_skroutz_sections.py::test_143481_rendered_description_preserves_locked_wrappers pipeline/tests/test_skroutz_integration.py::test_prepare_and_render_workflow_with_skroutz_fixtures` from `scraper/`
- `py -3.12 -m pytest -q pipeline/tests/test_workflow.py pipeline/tests/test_llm_contract.py pipeline/tests/test_services.py pipeline/tests/test_skroutz_sections.py pipeline/tests/test_skroutz_integration.py pipeline/tests/test_presentation_sections.py` from `scraper/`

Validation:
- render-focused subset first:
  - `py -3.12 -m pytest -q pipeline/tests/test_workflow.py pipeline/tests/test_llm_contract.py` from `scraper/`
  - passed, `27 passed`
- targeted compatibility regressions after the image-mapping fix:
  - `py -3.12 -m pytest -q pipeline/tests/test_skroutz_sections.py::test_143481_rendered_description_preserves_locked_wrappers pipeline/tests/test_skroutz_integration.py::test_prepare_and_render_workflow_with_skroutz_fixtures` from `scraper/`
  - passed, `2 passed`
- broader affected suite:
  - `py -3.12 -m pytest -q pipeline/tests/test_workflow.py pipeline/tests/test_llm_contract.py pipeline/tests/test_services.py pipeline/tests/test_skroutz_sections.py pipeline/tests/test_skroutz_integration.py pipeline/tests/test_presentation_sections.py` from `scraper/`
  - passed, `57 passed`

Deferred:
- final cleanup is still pending:
  - legacy `work/{model}/llm_output.json` is still accepted
  - legacy `work/{model}/llm_context.json` and `work/{model}/prompt.txt` still exist as compatibility artifacts from prepare
  - `README.md` has not been updated to the final steady-state split-output flow yet
- no LLM prompt split changes were made in this commit beyond consuming the split outputs already introduced in prepare

## 2026-03-30 - Split prepare into `intro_text` and `seo_meta` task artifacts

Goal:
- make split task-specific LLM handoff artifacts the primary prepare outputs
- keep the branch mergeable by preserving the legacy combined prepare files and legacy render input path during the transition
- remove section title/body generation from the new task ownership model without changing render to consume the new task outputs yet

Files added:
- `resources/prompts/intro_text_prompt.txt`
- `resources/prompts/seo_meta_prompt.txt`

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `scraper/pipeline/repo_paths.py`
- `scraper/pipeline/llm_contract.py`
- `scraper/pipeline/services/models.py`
- `scraper/pipeline/services/prepare_execution.py`
- `scraper/pipeline/services/prepare_service.py`
- `scraper/pipeline/services/run_execution.py`
- `scraper/pipeline/workflow.py`
- `scraper/pipeline/tests/test_llm_contract.py`
- `scraper/pipeline/tests/test_services.py`
- `scraper/pipeline/tests/test_utils_support_paths.py`
- `scraper/pipeline/tests/test_workflow.py`

Changes:
- added two task-specific prompt resources under `resources/prompts/`:
  - `intro_text_prompt.txt`
  - `seo_meta_prompt.txt`
- added new prompt path constants in `scraper/pipeline/repo_paths.py`
- extended `scraper/pipeline/llm_contract.py` with split-task builders:
  - `build_intro_text_context(...)`
  - `build_seo_meta_context(...)`
  - `build_task_manifest(...)`
- kept the existing combined `build_llm_context(...)` and legacy prompt rendering path in place strictly for compatibility
- updated `scraper/pipeline/services/prepare_execution.py` so prepare now writes these primary artifacts:
  - `work/{model}/llm/intro_text.context.json`
  - `work/{model}/llm/intro_text.prompt.txt`
  - `work/{model}/llm/seo_meta.context.json`
  - `work/{model}/llm/seo_meta.prompt.txt`
  - `work/{model}/llm/task_manifest.json`
- reserved expected task output targets in the manifest for the later render migration:
  - `work/{model}/llm/intro_text.output.txt`
  - `work/{model}/llm/seo_meta.output.json`
- preserved these compatibility artifacts intentionally:
  - `work/{model}/llm_context.json`
  - `work/{model}/prompt.txt`
  - `work/{model}/llm_output.json`
- updated prepare metadata and service-layer artifact models so run metadata now records:
  - `llm_dir`
  - `llm_task_manifest_path`
  - `intro_text_*` paths
  - `seo_meta_*` paths
- updated workflow prepare CLI output to print the new primary task artifact paths plus the legacy compatibility paths

Task ownership changes:
- `intro_text` now owns only the intro paragraph prompt/output contract:
  - plain text only
  - one paragraph
  - Greek
  - 120-180 words
  - no HTML
  - no bullets
  - no CTA language
- `seo_meta` now owns only:
  - `product.meta_description`
  - `product.meta_keywords`
- the new task contexts do not include section title/body generation instructions
- deterministic `presentation_source_sections` remain outside the split task contexts and stay in deterministic artifacts instead of being passed as a required `intro_text` writing input

Compatibility behavior intentionally preserved:
- prepare still writes the legacy combined context and prompt files because render has not been migrated yet
- render still reads legacy `work/{model}/llm_output.json` in this commit
- the task manifest explicitly marks the prepare mode as `split_tasks_with_legacy_compatibility`

Commands run:
- `Get-Content scraper/pipeline/repo_paths.py`
- `Get-Content scraper/pipeline/services/models.py`
- `rg -n "llm_context_path|prompt_path|llm_output_path|MASTER_PROMPT_PATH|prompt.txt|llm_context.json|task_manifest|intro_text|seo_meta" scraper/pipeline scraper/pipeline/tests resources -S`
- `Get-Content scraper/pipeline/services/prepare_service.py`
- `Get-Content scraper/pipeline/services/metadata.py`
- `Get-Content scraper/pipeline/workflow.py`
- `rg -n "meta_description_draft|differentiator|key_specs|deterministic_product" scraper/pipeline/deterministic_fields.py scraper/pipeline/tests/test_workflow.py scraper/pipeline/tests/test_skroutz_integration.py -S`
- `Get-Content scraper/pipeline/deterministic_fields.py`
- `Get-Content scraper/pipeline/tests/test_utils_support_paths.py`
- `Get-Content scraper/pipeline/services/run_execution.py`
- `Get-Content scraper/pipeline/tests/test_workflow.py | Select-Object -First 170`
- `Get-Content scraper/pipeline/tests/test_workflow.py | Select-Object -Skip 900 -First 60`
- `Get-Content scraper/pipeline/tests/test_services.py | Select-Object -First 240`
- `Get-Content scraper/pipeline/tests/test_llm_contract.py`
- `py -3.12 -m pytest -q pipeline/tests/test_llm_contract.py pipeline/tests/test_workflow.py pipeline/tests/test_services.py pipeline/tests/test_utils_support_paths.py` from `scraper/`
- `py -3.12 -m pytest -q pipeline/tests/test_presentation_sections.py pipeline/tests/test_llm_contract.py pipeline/tests/test_workflow.py pipeline/tests/test_services.py pipeline/tests/test_utils_support_paths.py pipeline/tests/test_skroutz_sections.py pipeline/tests/test_skroutz_integration.py` from `scraper/`

Validation:
- targeted prepare-facing subset first:
  - `py -3.12 -m pytest -q pipeline/tests/test_llm_contract.py pipeline/tests/test_workflow.py pipeline/tests/test_services.py pipeline/tests/test_utils_support_paths.py` from `scraper/`
  - passed, `30 passed`
- broader affected tests:
  - `py -3.12 -m pytest -q pipeline/tests/test_presentation_sections.py pipeline/tests/test_llm_contract.py pipeline/tests/test_workflow.py pipeline/tests/test_services.py pipeline/tests/test_utils_support_paths.py pipeline/tests/test_skroutz_sections.py pipeline/tests/test_skroutz_integration.py` from `scraper/`
  - passed, `52 passed`

Deferred:
- render was not changed to consume `intro_text` or `seo_meta` outputs in this commit
- legacy combined `llm_context.json`, `prompt.txt`, and `llm_output.json` remain intentionally present for the transition
- section title/body generation is still part of the legacy combined compatibility prompt only; the new split task artifacts do not assign that work to the LLM

## 2026-03-30 - Deterministic presentation section cleaning and quality classification foundation

Goal:
- add a deterministic normalization and quality-classification seam for extracted `presentation_source_sections`
- keep the current single-prompt LLM handoff intact for now while making section cleaning and section-state evaluation code-owned
- avoid changing final HTML assembly in this step

Files added:
- `scraper/pipeline/presentation_sections.py`
- `scraper/pipeline/tests/test_presentation_sections.py`

Files edited:
- `DOCUMENTATION.md`
- `scraper/pipeline/models.py`
- `scraper/pipeline/llm_contract.py`
- `scraper/pipeline/tests/test_workflow.py`

Changes:
- added `scraper/pipeline/presentation_sections.py` as the deterministic section normalization module
- introduced normalized presentation section dataclasses in `scraper/pipeline/models.py`:
  - `NormalizedPresentationSection`
  - `NormalizedPresentationSectionMetrics`
- implemented deterministic section normalization with these behaviors:
  - preserves source order
  - preserves source wording while stripping markup, URLs, and non-content tags
  - preserves source titles when present
  - classifies each section as `usable`, `weak`, or `missing`
  - emits reason codes including:
    - `missing_extraction`
    - `missing_empty_after_clean`
    - `missing_image_only`
    - `weak_short_body`
    - `weak_missing_title`
    - `weak_noisy_body`
    - `weak_duplicate`
    - `usable_clean`
  - applies the agreed word-count and alphabetic-character thresholds
  - detects duplicates against previously accepted non-missing section bodies
- updated `scraper/pipeline/llm_contract.py` so `build_llm_context(...)` now writes normalized deterministic `presentation_source_sections` into `work/{model}/llm_context.json`
- kept the current LLM output contract unchanged in this commit:
  - `presentation.intro_html`
  - `presentation.sections[].title`
  - `presentation.sections[].body_html`
  - `product.meta_description`
  - `product.meta_keywords`
- did not change render HTML assembly in this step

Behavior changes:
- `prepare` now exposes normalized section records in LLM context instead of raw extracted title/paragraph pairs
- each section record now includes:
  - `source_index`
  - `title`
  - `body_text`
  - `image_url`
  - `quality`
  - `reason`
  - `metrics`
- when fewer extracted sections exist than requested, `build_llm_context(...)` pads the deterministic section list with `missing_extraction` placeholders up to `sections_required`

Commands run:
- `rg -n "presentation_source_sections|sections|rendered_sections|section" scraper/pipeline -S`
- `Get-Content scraper/pipeline/llm_contract.py`
- `Get-Content scraper/pipeline/services/render_execution.py`
- `Get-Content scraper/pipeline/html_builders.py`
- `Get-Content scraper/pipeline/models.py`
- `Get-Content scraper/pipeline/mapping.py`
- `Get-Content scraper/pipeline/tests/test_llm_contract.py`
- `Get-Content scraper/pipeline/tests/test_workflow.py | Select-Object -First 180`
- `Get-Content scraper/pipeline/services/prepare_execution.py`
- `Get-Content scraper/pipeline/tests/test_services.py`
- `Get-Content resources/prompts/master_prompt+.txt`
- `rg -n "presentation_source_sections|paragraph|image_url|title" resources/prompts/master_prompt+.txt scraper/pipeline/tests/test_workflow.py scraper/pipeline/tests/test_skroutz_integration.py scraper/pipeline/tests/test_skroutz_sections.py -S`
- `Get-Content scraper/pipeline/normalize.py`
- `py -3.12 -m pytest -q pipeline/tests/test_presentation_sections.py` from `scraper/`
- `py -3.12 -m pytest -q pipeline/tests/test_presentation_sections.py pipeline/tests/test_workflow.py pipeline/tests/test_llm_contract.py` from `scraper/`
- `py -3.12 -m pytest -q pipeline/tests/test_services.py` from `scraper/`
- `py -3.12 -m pytest -q pipeline/tests/test_presentation_sections.py pipeline/tests/test_workflow.py pipeline/tests/test_llm_contract.py pipeline/tests/test_services.py` from `scraper/`

Validation:
- smallest relevant subset first:
  - `py -3.12 -m pytest -q pipeline/tests/test_presentation_sections.py` from `scraper/`
  - passed, `10 passed`
- broader affected tests:
  - `py -3.12 -m pytest -q pipeline/tests/test_presentation_sections.py pipeline/tests/test_workflow.py pipeline/tests/test_llm_contract.py` from `scraper/`
  - passed, `29 passed`
  - `py -3.12 -m pytest -q pipeline/tests/test_services.py` from `scraper/`
  - passed, `8 passed`
  - final rerun:
  - `py -3.12 -m pytest -q pipeline/tests/test_presentation_sections.py pipeline/tests/test_workflow.py pipeline/tests/test_llm_contract.py pipeline/tests/test_services.py` from `scraper/`
  - passed, `37 passed`

Deferred:
- no LLM task split was attempted in this commit
- no prompt-template change was attempted in this commit
- no render-side deterministic section consumption was attempted in this commit
- no README change was made in this commit

## 2026-03-30 - Branch scope design note for split-LLM `intro_text` and deterministic presentation

Purpose:
- document the full planned scope of the split-LLM deterministic-presentation branch before runtime code changes
- keep this commit docs-only and avoid implying that any runtime or test work is already complete

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `IMPLEMENT.md`

Current state:
- `README.md` still documents single prepare outputs:
  - `work/{model}/llm_context.json`
  - `work/{model}/prompt.txt`
- `scraper/pipeline/llm_contract.py` currently marks these fields as LLM-owned:
  - `presentation.intro_html`
  - `presentation.sections[].title`
  - `presentation.sections[].body_html`
  - `product.meta_description`
  - `product.meta_keywords`
- `scraper/pipeline/services/prepare_execution.py` still builds one LLM context and one prompt
- `scraper/pipeline/services/render_execution.py` still reads `work/{model}/llm_output.json`

Target state:
- prepare emits two task-specific LLM handoffs:
  - `intro_text`
  - `seo_meta`
- `intro_text` returns plain text only, one paragraph, 120-180 words
- `seo_meta` returns:
  - `meta_description`
  - `meta_keywords`
- presentation section title/body generation is removed from the LLM
- presentation sections are built deterministically from `presentation_source_sections`
- existing source section titles are kept when present
- deterministic section handling is limited to cleaning/sanitizing unsafe or noisy markup while preserving wording
- final description HTML is rendered in code from:
  - the LLM `intro_text` paragraph
  - deterministic CTA data
  - cleaned deterministic source sections
- HTML wrappers, CTA block, image wiring, section layout, classes, and styles become code-owned

Compatibility phase:
- render will first look for task-specific outputs:
  - `work/{model}/intro_text.llm_output.json`
  - `work/{model}/seo_meta.llm_output.json`
- render will continue to accept legacy combined `work/{model}/llm_output.json` during the compatibility phase
- final cleanup removes the combined-output fallback and the single-prompt artifact contract

Deterministic ownership boundaries:
- LLM-owned in the target branch:
  - `intro_text`
  - `product.meta_description`
  - `product.meta_keywords`
- code-owned in the target branch:
  - presentation section selection, classification, and cleaning
  - section titles when sourced
  - CTA text and CTA block wiring
  - description wrappers, classes, and styles
  - image wiring
  - section layout
  - keyword deduplication
  - singular/plural keyword collapsing
  - final HTML assembly

Section quality classifier:
- `usable`: the source section has enough preserved text or media-backed structure to render as a deterministic feature block
- `weak`: the source section exists but is too thin, noisy, or redundant to count confidently; warn and continue if remaining sections are sufficient
- `missing`: the requested section slot cannot be filled from source data after extraction and cleaning

Failure policy:
- if `presentation_source_sections` are missing entirely, fail the run
- if sections are `weak`, warn and continue with fewer sections
- if exactly one requested section is `missing`, warn and continue with fewer sections
- do not add a fallback that asks the LLM to regenerate missing deterministic section copy

SEO rules planned for code ownership:
- `intro_text` stays plain text only and is converted to HTML in code
- `seo_meta` must return `meta_description` and `meta_keywords`
- brand and model must always appear in `meta_keywords`
- duplicate keywords and singular/plural variants are collapsed in code before CSV mapping

Commands run:
- `Get-Location | Select-Object -ExpandProperty Path`
- `git status --short`
- `Get-Content -Raw PLAN.md`
- `Get-Content -Raw IMPLEMENT.md`
- `Get-Content -Raw DOCUMENTATION.md`
- `rg -n "intro_html|meta_description|meta_keywords|sections\\[\\]\\.title|sections\\[\\]\\.body_html|llm_output\\.json|prompt\\.txt|llm_context\\.json|prepare_execution|render_execution|presentation_source_sections" scraper resources README.md -S`
- `rg --files scraper/pipeline/tests`
- `rg -n "llm_contract|compact_response.schema.json|master_prompt\\+\\.txt|prompt.txt|llm_context.json" scraper/pipeline resources -S`
- `Get-Content DOCUMENTATION.md | Select-Object -First 140`
- `rg -n "Phase 3|M29|Validation rules|Stop conditions|Current milestone" PLAN.md DOCUMENTATION.md IMPLEMENT.md -S`
- `git diff --check`
- `git diff -- PLAN.md IMPLEMENT.md DOCUMENTATION.md`

Validation:
- docs-only commit
- `git diff --check` passed
- no runtime tests were run because this commit only updates control docs and must not include runtime or test changes

Deferred:
- no runtime code, tests, or README changes were made in this commit
- the compatibility phase, deterministic section pipeline, and final cleanup remain planned work only at this stage

## M29 — make run_service the true owner of full-run orchestration

Goal:
- move the real full-run orchestration body out of `scraper/pipeline/services/run_service.py` into a service-owned execution module
- keep CLI commands, workflow adapter behavior, artifact paths, validation semantics, publish gating, output semantics, and provider behavior unchanged
- finish the full-run ownership inversion without widening scope into workflow or provider redesign

Files added:
- `scraper/pipeline/services/run_execution.py`

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `scraper/pipeline/services/run_service.py`
- `scraper/pipeline/tests/test_services.py`

Changes:
- extracted the full-run composition body from `scraper/pipeline/services/run_service.py::run_product(...)` into `scraper/pipeline/services/run_execution.py::execute_run_workflow(...)`
- kept the full-run composition service-owned by having the new executor compose `prepare_product(...)` and `render_product(...)` and return the same aggregated `ServiceResult` shape as before
- reduced `scraper/pipeline/services/run_service.py` to a thin service wrapper that directly calls the new service-owned full-run executor and preserves the existing exception-wrapping behavior
- updated `scraper/pipeline/tests/test_services.py` to prove:
  - service-owned modules involved in prepare/render/full-run execution do not import `workflow.py`
  - the new full-run executor still composes prepare/render results in order with unchanged aggregation semantics
  - `run_product(...)` now delegates to the service-owned full-run executor and still wraps executor errors

Commands run:
- `Get-ChildItem -Force`
- `rg -n "run_product|FullRunRequest|prepare_product|render_product|run_execution|workflow" scraper/pipeline -S`
- `Get-Content PLAN.md`
- `Get-Content DOCUMENTATION.md`
- `Get-Content scraper/pipeline/services/run_service.py`
- `Get-Content scraper/pipeline/tests/test_services.py`
- `Get-Content scraper/pipeline/workflow.py`
- `Get-Content scraper/pipeline/services/models.py`
- `Get-Content scraper/pipeline/cli.py`
- `Get-Content scraper/pipeline/services/__init__.py`
- `rg -n "run_product\\(|prepare_product\\(|render_product\\(" scraper/pipeline/tests/test_workflow.py scraper/pipeline/tests/test_services.py scraper/pipeline/cli.py -S`
- `git status --short`
- `Get-Content scraper/pipeline/services/prepare_service.py`
- `Get-Content scraper/pipeline/services/render_service.py`
- `Get-Content scraper/pipeline/services/prepare_execution.py`
- `Get-Content scraper/pipeline/services/render_execution.py`
- `rg -n "Current milestone|M28|M29|Phase 2 milestones" PLAN.md DOCUMENTATION.md -S`
- `Get-Content scraper/pipeline/tests/test_workflow.py | Select-Object -Skip 940 -First 40`
- `python -m compileall pipeline` from `scraper/`
- `py -3.12 -m pytest -q pipeline/tests/test_services.py` from `scraper/`
- `py -3.12 -m pytest -q pipeline/tests/test_workflow.py` from `scraper/`
- `py -3.12 -m pytest -q` from `scraper/`

Validation:
- compile validation:
  - `python -m compileall pipeline` from `scraper/`
  - passed
- exact requested pytest commands:
  - `py -3.12 -m pytest -q pipeline/tests/test_services.py` from `scraper/`
  - passed
  - `py -3.12 -m pytest -q pipeline/tests/test_workflow.py` from `scraper/`
  - passed
  - `py -3.12 -m pytest -q` from `scraper/`
  - passed

Risks:
- `run_product(...)` remains the stable service entrypoint while the real full-run composition now lives one layer lower in `run_execution.py`; this is intentional and keeps the service contract unchanged
- `cli.py` still owns standalone full-run metadata emission, while M29 only moves service-layer orchestration ownership

Deferred:
- no provider migration, CLI redesign, workflow redesign, artifact-path change, validation-contract change, or publish-gating change was attempted
- `scraper/pipeline/tests/test_workflow.py` did not require edits because the workflow layer remains an unchanged adapter for prepare/render-only commands
- `IMPLEMENT.md`, `AGENTS.md`, `README.md`, and `RULES.md` were left unchanged because M29 did not add a new durable operator rule or change the accepted runtime interface

## M28 — make services the true owner of prepare/render orchestration

Goal:
- move the real prepare/render orchestration bodies out of `scraper/pipeline/workflow.py` and into service-owned execution modules
- keep CLI/workflow commands, artifact paths, validation semantics, publish gating, and provider behavior unchanged
- finish the prepare/render ownership inversion without widening scope into provider changes or full-run redesign

Files added:
- `scraper/pipeline/services/prepare_execution.py`
- `scraper/pipeline/services/render_execution.py`

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `scraper/pipeline/workflow.py`
- `scraper/pipeline/services/prepare_service.py`
- `scraper/pipeline/services/render_service.py`
- `scraper/pipeline/tests/test_services.py`
- `scraper/pipeline/tests/test_workflow.py`

Changes:
- extracted the prepare orchestration body from `workflow.prepare_workflow(...)` into `scraper/pipeline/services/prepare_execution.py::execute_prepare_workflow(...)`, including scrape artifact normalization, prompt/context generation, and prepare metadata writes
- extracted the render orchestration body from `workflow.render_workflow(...)` into `scraper/pipeline/services/render_execution.py::execute_render_workflow(...)`, including LLM output loading, candidate generation, validation, publish gating, and render metadata writes
- updated `scraper/pipeline/services/prepare_service.py` so `prepare_product(...)` now calls the service-owned prepare executor directly and no longer imports `workflow.py`
- updated `scraper/pipeline/services/render_service.py` so `render_product(...)` now calls the service-owned render executor directly and no longer imports `workflow.py`
- reduced `scraper/pipeline/workflow.py` to thin prepare/render adapters that inject the existing `WORK_ROOT`, `PRODUCTS_ROOT`, and `execute_full_run(...)` dependencies while keeping the CLI entrypoint behavior unchanged
- updated `scraper/pipeline/tests/test_services.py` to assert the services no longer import `workflow.py` and to mock the new service-owned executors instead of workflow-owned orchestration
- updated `scraper/pipeline/tests/test_workflow.py` with focused adapter-delegation coverage while preserving the existing prepare/render behavior tests at the current baseline

Commands run:
- `Get-Content scraper/pipeline/workflow.py`
- `Get-Content scraper/pipeline/services/prepare_service.py`
- `Get-Content scraper/pipeline/services/render_service.py`
- `Get-Content scraper/pipeline/tests/test_services.py`
- `Get-Content scraper/pipeline/tests/test_workflow.py`
- `Get-Content PLAN.md`
- `Get-Content DOCUMENTATION.md`
- `rg -n "prepare_workflow|render_workflow|prepare_product\\(|render_product\\(" scraper/pipeline -S`
- `Get-Content scraper/pipeline/services/models.py`
- `Get-Content scraper/pipeline/services/__init__.py`
- `git status --short`
- `Get-Content scraper/pipeline/tests/test_skroutz_integration.py -TotalCount 40`
- `Get-Content scraper/pipeline/tests/test_skroutz_sections.py -TotalCount 40`
- `Get-Content scraper/pipeline/workflow.py | Select-Object -First 220`
- `Get-Content scraper/pipeline/workflow.py | Select-Object -Skip 220`
- `Get-Content scraper/pipeline/workflow.py`
- `Get-Content scraper/pipeline/services/prepare_execution.py`
- `Get-Content scraper/pipeline/services/render_execution.py`
- `Get-Content scraper/pipeline/tests/test_services.py`
- `Get-Content scraper/pipeline/tests/test_workflow.py | Select-Object -First 140`
- `python -m compileall pipeline` from `scraper/`
- `python -m pytest -q pipeline/tests/test_services.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_workflow.py` from `scraper/`
- `python -m pytest -q` from `scraper/`
- `py -0p`
- `where.exe python`
- `py -3.12 -m pytest -q pipeline/tests/test_services.py` from `scraper/`
- `py -3.12 -m pytest -q pipeline/tests/test_workflow.py` from `scraper/`
- `py -3.12 -m pytest -q` from `scraper/`

Validation:
- compile validation:
  - `python -m compileall pipeline` from `scraper/`
  - passed
- exact requested pytest commands:
  - `python -m pytest -q pipeline/tests/test_services.py` from `scraper/`
  - `python -m pytest -q pipeline/tests/test_workflow.py` from `scraper/`
  - `python -m pytest -q` from `scraper/`
  - all three failed before test discovery because the active `python` resolved to `C:\Users\Rashingar\AppData\Local\Programs\Python\Python310\python.exe`, which does not have `pytest` installed
- executed pytest validation on the installed interpreter:
  - `py -3.12 -m pytest -q pipeline/tests/test_services.py` from `scraper/`
  - passed, `7 passed`
  - `py -3.12 -m pytest -q pipeline/tests/test_workflow.py` from `scraper/`
  - passed, `15 passed`
  - `py -3.12 -m pytest -q` from `scraper/`
  - passed, `103 passed`

Risks:
- `workflow.prepare_workflow(...)` and `workflow.render_workflow(...)` remain as compatibility adapters for existing tests and callers; M28 intentionally changes ownership, not the public callable surface
- service-layer path constants still exist in both workflow adapters and service-owned executors by design so the workflow layer can continue injecting the current roots without changing runtime semantics

Deferred:
- no provider changes, full-run service redesign, CLI UX changes, artifact-path changes, or validation-contract changes were attempted
- `IMPLEMENT.md`, `AGENTS.md`, `README.md`, and `RULES.md` were left unchanged because M28 did not introduce a new durable operator rule or change the accepted runtime interface

## M27 — retire legacy runtime source branches and close the migration phase

Goal:
- remove the now-obsolete legacy source-routing fallback branches left behind after provider parity was proven
- keep provider-backed execution as the single active internal seam for all currently supported runtime sources
- preserve CLI/workflow commands, accepted inputs, outputs, artifact paths, and validation semantics while closing Phase 2 cleanly

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `scraper/pipeline/full_run.py`
- `scraper/pipeline/tests/test_provider_selection.py`
- `scraper/pipeline/tests/test_workflow.py`

Files moved:
- none

Before/after summary:
- before:
  - all supported sources already had provider adapters, but `scraper/pipeline/full_run.py` still carried direct fetch/parser fallback branches that could bypass the provider seam if provider selection returned `None`
  - `full_run.py` also still contained one dead pre-migration section-routing branch under `if cli.sections > 0 and source != "skroutz":` that could never execute
- after:
  - `execute_full_run(...)` now fails fast with `No provider configured for supported source: ...` instead of falling back to legacy per-source fetch/parser logic
  - the dead non-provider section-routing branch was removed, leaving the live non-Skroutz section extraction path and the existing Skroutz-specific post-enrichment path intact
  - tests now lock both the supported provider map and the fail-fast no-provider behavior so the migration boundary does not regress silently

Changes:
- updated `scraper/pipeline/full_run.py` to remove the legacy direct fetch/parse branches for supported sources and require provider selection before normalization proceeds
- removed the unreachable dead source-branch duplication in the non-Skroutz section extraction block of `scraper/pipeline/full_run.py`
- added `test_resolve_provider_for_source_returns_none_for_unsupported_source` in `scraper/pipeline/tests/test_provider_selection.py` so the supported-provider map stays explicit
- added `test_execute_full_run_fails_fast_when_supported_source_has_no_provider` in `scraper/pipeline/tests/test_workflow.py` so a missing provider can no longer silently reactivate legacy runtime routing
- updated `PLAN.md` to mark M27 completed, mark Phase 2 completed, and add the Phase 3 handoff header without starting new implementation work

Commands run:
- `Get-ChildItem`
- `Get-Content PLAN.md`
- `Get-Content IMPLEMENT.md`
- `Get-Content DOCUMENTATION.md`
- `Get-Content scraper\\pipeline\\full_run.py`
- `Get-Content scraper\\pipeline\\tests\\test_workflow.py`
- `Get-Content scraper\\pipeline\\tests\\test_provider_selection.py`
- `rg -n '_resolve_provider_for_source|provider is not None|provider seam|provider-backed|legacy branch|legacy routing|source == "skroutz"|source == "manufacturer_tefal"|return None' scraper\\pipeline PLAN.md README.md IMPLEMENT.md -S`
- `rg -n 'fetch_httpx\\(|fetch_playwright\\(|ManufacturerProductParser\\(|SkroutzProductParser\\(|ElectronetProductParser\\(' scraper\\pipeline\\full_run.py scraper\\pipeline\\providers scraper\\pipeline\\tests -S`
- `Get-Content scraper\\pipeline\\source_detection.py`
- `Get-Content scraper\\pipeline\\tests\\conftest.py`
- `Get-Content scraper\\pipeline\\providers\\registry.py`
- `Get-Content scraper\\pipeline\\providers\\electronet_provider.py`
- `Get-Content scraper\\pipeline\\providers\\skroutz_provider.py`
- `Get-Content scraper\\pipeline\\providers\\manufacturer_tefal_provider.py`
- `git diff -- scraper/pipeline/full_run.py scraper/pipeline/tests/test_provider_selection.py scraper/pipeline/tests/test_workflow.py`
- `py -3.12 -m pytest -q pipeline/tests/test_provider_selection.py pipeline/tests/test_workflow.py` from `scraper/`
- `py -3.12 -m pytest -q` from `scraper/`

Validation:
- targeted migration-closure validation:
  - `py -3.12 -m pytest -q pipeline/tests/test_provider_selection.py pipeline/tests/test_workflow.py` from `scraper/`
  - passed, `21 passed`
- full suite validation:
  - `py -3.12 -m pytest -q` from `scraper/`
  - passed, `100 passed`

Risks:
- provider resolution still uses the existing private helper `_resolve_provider_for_source(...)`; M27 intentionally closes the migration by removing fallback routing rather than redesigning provider registration or widening the contract

Deferred:
- no provider-registry runtime rewrite, hybrid RAG work, service-layer redesign, CLI UX change, README change, or source-scope expansion was attempted
- `IMPLEMENT.md`, `README.md`, `AGENTS.md`, and `RULES.md` were left unchanged because no durable process rule or user-facing runtime behavior changed

## M26 — migrate supported manufacturer flows behind provider adapters

Goal:
- route the currently supported manufacturer runtime flow behind the existing provider seam without changing CLI/workflow inputs, artifact locations, metadata filenames, service contracts, or validation semantics
- address the current manufacturer enrichment weak spot reflected in the failing test baseline

Files added:
- `scraper/pipeline/providers/manufacturer_tefal_provider.py`
- `scraper/pipeline/tests/fixtures/providers/manufacturer_tefal/344709/product.html`

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `scraper/pipeline/full_run.py`
- `scraper/pipeline/manufacturer_enrichment.py`
- `scraper/pipeline/providers/__init__.py`
- `scraper/pipeline/tests/test_manufacturer_enrichment.py`
- `scraper/pipeline/tests/test_provider_selection.py`
- `scraper/pipeline/tests/test_workflow.py`

Changes:
- added `ManufacturerTefalProvider` under `scraper/pipeline/providers/` as the production adapter for the currently supported manufacturer source:
  - preserves the existing live fetch order of HTTPX first, then Playwright fallback
  - reuses the existing `ManufacturerProductParser`
  - supports optional fixture HTML overrides for deterministic provider tests
- updated `scraper/pipeline/full_run.py` so `_resolve_provider_for_source(...)` now selects `ManufacturerTefalProvider` for `manufacturer_tefal` while leaving the rest of the prepare/render pipeline unchanged
- exported `ManufacturerTefalProvider` from `scraper/pipeline/providers/__init__.py`
- added a committed manufacturer provider fixture at `scraper/pipeline/tests/fixtures/providers/manufacturer_tefal/344709/product.html` so provider normalization can be tested against a stable Tefal product page sample
- updated `scraper/pipeline/tests/test_provider_selection.py` to prove:
  - Electronet, Skroutz, and the supported manufacturer source all resolve through the production provider seam
  - `ManufacturerTefalProvider.fetch_snapshot()` reads the committed fixture
  - `ManufacturerTefalProvider.normalize()` returns the expected provider/runtime result shape
- updated `scraper/pipeline/tests/test_workflow.py` so the manufacturer default-flow regression now proves provider-backed execution in production instead of the legacy direct parser branch
- made one narrow compatibility fix in `scraper/pipeline/manufacturer_enrichment.py`:
  - enrichment now tolerates official-doc adapters whose `discover(...)` implementation does not accept the optional `fetcher` keyword
  - this preserves the current enrichment contract while resolving the previously failing manufacturer framework tests
- updated `scraper/pipeline/tests/test_manufacturer_enrichment.py` to keep the manufacturer regression explicit, including the no-`fetcher` discover-signature compatibility path
- left `scraper/pipeline/parser_product_manufacturer.py`, workflow metadata, CLI/service entrypoints, output locations, and validation semantics unchanged

Commands run:
- `Get-Content PLAN.md | Select-Object -First 90`
- `Get-Content IMPLEMENT.md`
- `Get-Content DOCUMENTATION.md | Select-Object -First 180`
- `rg -n "manufacturer_tefal|ManufacturerProductParser|enrich_source_from_manufacturer_docs|provider|supported manufacturer|adapter" scraper/pipeline PLAN.md DOCUMENTATION.md -S`
- `git status --short`
- `Get-Content scraper/pipeline/full_run.py`
- `Get-Content scraper/pipeline/manufacturer_enrichment.py`
- `Get-Content scraper/pipeline/parser_product_manufacturer.py`
- `Get-Content scraper/pipeline/source_detection.py`
- `Get-Content scraper/pipeline/tests/test_manufacturer_enrichment.py`
- `Get-Content scraper/pipeline/tests/test_workflow.py | Select-Object -Skip 380 -First 140`
- `Get-Content scraper/pipeline/tests/conftest.py`
- `Get-ChildItem -Recurse scraper/pipeline/tests/fixtures/providers/manufacturer_tefal`
- `Get-Content scraper/pipeline/providers/__init__.py`
- `Get-Content scraper/pipeline/tests/test_manufacturer_enrichment_tefal.py`
- `Get-Content scraper/pipeline/tests/test_provider_selection.py`
- `Get-Content scraper/pipeline/models.py | Select-String -Pattern "class FetchResult|class ParsedProduct|class SourceProductData" -Context 0,60`
- `rg -n "_resolve_provider_for_source\\(" scraper/pipeline/tests scraper/pipeline -S`
- `python -m compileall scraper/pipeline`
- `py -3.12 -m pytest -q pipeline/tests/test_manufacturer_enrichment.py pipeline/tests/test_manufacturer_enrichment_tefal.py pipeline/tests/test_parser_product_manufacturer.py pipeline/tests/test_provider_selection.py pipeline/tests/test_workflow.py::test_execute_full_run_routes_manufacturer_tefal_through_provider_by_default` from `scraper/`
- `py -3.12 -m pytest -q` from `scraper/`
- `git status --short`
- `git diff --stat`

Validation:
- compile validation:
  - `python -m compileall scraper/pipeline`
  - passed
- targeted manufacturer validation:
  - `py -3.12 -m pytest -q pipeline/tests/test_manufacturer_enrichment.py pipeline/tests/test_manufacturer_enrichment_tefal.py pipeline/tests/test_parser_product_manufacturer.py pipeline/tests/test_provider_selection.py pipeline/tests/test_workflow.py::test_execute_full_run_routes_manufacturer_tefal_through_provider_by_default` from `scraper/`
  - passed, `17 passed`
- full suite validation:
  - `py -3.12 -m pytest -q` from `scraper/`
  - passed, `98 passed`

Risks:
- only the currently supported manufacturer runtime source is provider-backed in M26; broader manufacturer-provider expansion remains future work
- the manufacturer fixture coverage is intentionally narrow and focused on the committed Tefal regression sample, so future manufacturer providers should add their own fixture roots rather than overloading this one

Deferred:
- no service-layer redesign, workflow metadata redesign, CLI change, README change, or source-scope expansion was attempted
- no legacy manufacturer code was removed beyond the smallest runtime-routing change needed for this milestone
- `IMPLEMENT.md`, `AGENTS.md`, `RULES.md`, and `README.md` were left unchanged because no new durable process rule or accepted runtime I/O change was introduced

## M25 — route Skroutz through the provider seam in production

Goal:
- promote Skroutz from the M22 test-injected provider proof to normal runtime provider selection without changing CLI/workflow inputs, artifact locations, metadata filenames, or validation semantics

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `scraper/pipeline/full_run.py`
- `scraper/pipeline/providers/skroutz_provider.py`
- `scraper/pipeline/tests/test_provider_selection.py`
- `scraper/pipeline/tests/test_skroutz_integration.py`
- `scraper/pipeline/tests/test_workflow.py`

Changes:
- updated `scraper/pipeline/full_run.py` so `_resolve_provider_for_source(...)` now selects `SkroutzProvider` for supported Skroutz product URLs in normal production flow while leaving Electronet and manufacturer routing unchanged
- extended `scraper/pipeline/providers/skroutz_provider.py` from a fixture-only proof into a production-capable provider adapter:
  - live fetch path uses the existing Skroutz runtime order of Playwright first, then HTTPX fallback
  - fixture HTML overrides remain supported for deterministic tests
  - provider metadata now reports live fetch capability while preserving the same downstream `FetchResult` and `ParsedProduct` conversion contract
- updated provider-selection tests to assert that:
  - Electronet and Skroutz both resolve through the provider seam
  - manufacturer sources still do not
  - `SkroutzProvider` can still normalize fixture-backed snapshots
  - `SkroutzProvider` uses the live fetcher path when no fixture override is configured
- updated the default workflow regression in `scraper/pipeline/tests/test_workflow.py` so Skroutz now proves provider-seam execution by default instead of the legacy branch
- updated `scraper/pipeline/tests/test_skroutz_integration.py` to assert prepare/render parity still holds for fixture-backed Skroutz workflow runs with `playwright` fetch mode preserved in the emitted report
- left `scraper/pipeline/tests/test_skroutz_sections.py` and `scraper/pipeline/tests/test_skroutz_taxonomy.py` unchanged because they already cover downstream section extraction and taxonomy behavior; they were rerun as targeted regression validation for this milestone

Commands run:
- `Get-Content PLAN.md`
- `Get-Content IMPLEMENT.md`
- `Get-Content DOCUMENTATION.md`
- `rg -n "M25|Skroutz|provider seam|_resolve_provider_for_source|SkroutzProvider|provider selection" PLAN.md IMPLEMENT.md DOCUMENTATION.md scraper -S`
- `Get-Content scraper/pipeline/full_run.py`
- `Get-Content scraper/pipeline/providers/skroutz_provider.py`
- `Get-Content scraper/pipeline/providers/__init__.py`
- `Get-Content scraper/pipeline/tests/test_provider_selection.py`
- `Get-Content scraper/pipeline/tests/test_skroutz_integration.py`
- `Get-Content scraper/pipeline/tests/test_skroutz_sections.py`
- `Get-Content scraper/pipeline/tests/test_skroutz_taxonomy.py`
- `Get-Content scraper/pipeline/tests/test_workflow.py`
- `Get-Content scraper/pipeline/providers/base.py`
- `Get-Content scraper/pipeline/providers/models.py`
- `Get-Content scraper/pipeline/providers/electronet_provider.py`
- `rg -n "provider_id|ProviderKind|FIXTURE|VENDOR_SITE|supports_identity|fetch_snapshot\\(|normalize\\(" scraper/pipeline/providers -S`
- `rg -n "_resolve_provider_for_source|legacy Skroutz|by default|skroutz provider|fetch_mode" scraper/pipeline/tests -S`
- `git status --short`
- `rg -n "_resolve_provider_for_source\\(" scraper/pipeline -S`
- `python -m compileall scraper/pipeline`
- `py -3.12 -m pytest -q pipeline/tests/test_provider_selection.py pipeline/tests/test_workflow.py pipeline/tests/test_skroutz_integration.py pipeline/tests/test_skroutz_sections.py pipeline/tests/test_skroutz_taxonomy.py` from `scraper/`
- `py -3.12 -m pytest -q` from `scraper/`
- `git status --short`

Validation:
- compile validation:
  - `python -m compileall scraper/pipeline`
  - passed
- targeted provider and Skroutz validation:
  - `py -3.12 -m pytest -q pipeline/tests/test_provider_selection.py pipeline/tests/test_workflow.py pipeline/tests/test_skroutz_integration.py pipeline/tests/test_skroutz_sections.py pipeline/tests/test_skroutz_taxonomy.py` from `scraper/`
  - passed, `34 passed`
- full suite validation:
  - `py -3.12 -m pytest -q` from `scraper/`
  - returned the accepted baseline for this milestone: `93 passed, 2 failed`
  - unchanged accepted failures:
    - `pipeline/tests/test_manufacturer_enrichment.py::test_enrichment_framework_supports_pdf_candidates`
    - `pipeline/tests/test_manufacturer_enrichment.py::test_enrichment_framework_supports_html_candidates`

Risks:
- `SkroutzProvider` now owns both live and fixture-backed fetch paths; future provider migrations should keep fixture overrides narrow so production routing changes stay observable in runtime tests
- the repo still carries the two pre-existing manufacturer-enrichment failures outside M25 scope

Deferred:
- no manufacturer provider migration was attempted
- no provider-contract redesign, registry-driven runtime rewrite, CLI change, publish-semantics change, or opportunistic cleanup was performed
- `AGENTS.md`, `IMPLEMENT.md`, `RULES.md`, and `README.md` were left unchanged because operator-facing behavior and accepted runtime I/O did not change

## M24 — stabilize the post-workdir test baseline

Goal:
- stabilize the post-M23 pytest baseline without changing runtime behavior by moving touched test baselines under `scraper/pipeline/tests/fixtures/...` and aligning workflow assertions with the live render contract

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`
- `scraper/pipeline/tests/conftest.py`
- `scraper/pipeline/tests/test_skroutz_integration.py`
- `scraper/pipeline/tests/test_skroutz_sections.py`
- `scraper/pipeline/tests/test_workflow.py`

Files added:
- `scraper/pipeline/tests/fixtures/golden_outputs/skroutz/143481.csv`
- `scraper/pipeline/tests/fixtures/golden_outputs/skroutz/307497.csv`
- `scraper/pipeline/tests/fixtures/golden_outputs/skroutz/341490.csv`
- `scraper/pipeline/tests/fixtures/golden_outputs/skroutz/344317.csv`

Changes:
- added `skroutz_golden_outputs_root` as the shared pytest fixture root for committed Skroutz golden CSV baselines
- removed the touched test-layer dependency on repo-level `products/*.csv` by copying the four committed Skroutz baseline CSVs into `scraper/pipeline/tests/fixtures/golden_outputs/skroutz/`
- updated `test_skroutz_integration.py` to seed temporary publish baselines from fixture-owned golden outputs only and to assert the live render contract:
  - candidate CSV still exists when validation fails
  - `published_csv_path` is `None` when validation is not ok
  - publish-skip warnings are surfaced in the validation report
- updated `test_skroutz_sections.py` to build its LLM payload and temporary baseline only from fixture-owned golden outputs
- updated `test_workflow.py` to assert that render still writes the full candidate bundle even when validation fails and publish is skipped
- left runtime modules unchanged because the failing behavior was test-expectation drift, not a proven workflow bug

Commands run:
- `Get-Content PLAN.md`
- `Get-Content DOCUMENTATION.md`
- `Get-Content IMPLEMENT.md`
- `rg --files scraper/pipeline/tests`
- `Get-Content scraper/pipeline/tests/conftest.py`
- `Get-Content scraper/pipeline/tests/test_workflow.py`
- `Get-Content scraper/pipeline/tests/test_skroutz_integration.py`
- `Get-Content scraper/pipeline/workflow.py`
- `Get-Content scraper/pipeline/services/run_service.py`
- `git ls-files products work scraper/work`
- `rg -n "products_root|products/.*csv|golden_outputs/skroutz" scraper/pipeline/tests`
- `py -3.12 -m pytest -q pipeline/tests/test_workflow.py::test_render_workflow_writes_candidate_bundle pipeline/tests/test_skroutz_integration.py::test_prepare_and_render_workflow_with_skroutz_fixtures pipeline/tests/test_skroutz_sections.py::test_143481_rendered_description_preserves_locked_wrappers` from `scraper/`
- `Get-Content` for the generated `233541.validation.json`, `143481.validation.json`, and matching `render.run.json` files under the temporary pytest workdirs
- `py -3.12 -m pytest -q pipeline/tests/test_workflow.py pipeline/tests/test_skroutz_integration.py pipeline/tests/test_skroutz_sections.py` from `scraper/`
- `py -3.12 -m pytest -q` from `scraper/`
- `git status --short`

Validation:
- focused failing-contract reproduction before the test updates:
  - `py -3.12 -m pytest -q pipeline/tests/test_workflow.py::test_render_workflow_writes_candidate_bundle pipeline/tests/test_skroutz_integration.py::test_prepare_and_render_workflow_with_skroutz_fixtures pipeline/tests/test_skroutz_sections.py::test_143481_rendered_description_preserves_locked_wrappers` from `scraper/`
  - result: `2 failed, 1 passed`
  - failures:
    - `pipeline/tests/test_workflow.py::test_render_workflow_writes_candidate_bundle`
    - `pipeline/tests/test_skroutz_integration.py::test_prepare_and_render_workflow_with_skroutz_fixtures`
  - both failures were stale publish expectations against a real `published_csv_path is None` contract when validation was not ok
- targeted touched-test validation after the fix:
  - `py -3.12 -m pytest -q pipeline/tests/test_workflow.py pipeline/tests/test_skroutz_integration.py pipeline/tests/test_skroutz_sections.py` from `scraper/`
  - passed, `24 passed`
- full suite validation after the fix:
  - `py -3.12 -m pytest -q` from `scraper/`
  - returned the accepted baseline: `92 passed, 2 failed`
  - unchanged accepted failures:
    - `pipeline/tests/test_manufacturer_enrichment.py::test_enrichment_framework_supports_pdf_candidates`
    - `pipeline/tests/test_manufacturer_enrichment.py::test_enrichment_framework_supports_html_candidates`

Risks:
- the committed deliverable CSVs under `products/` still exist in the repo by design; M24 only removed the touched tests' baseline dependency on them
- the full-suite baseline still includes the two long-standing manufacturer-enrichment failures outside M24 scope

Deferred:
- no runtime-code, workflow-contract, provider-routing, or CLI changes were made
- no additional fixture migration beyond the touched baseline CSVs was attempted in this milestone

## M23 — rename `scrapper/electronet_single_import` to `scraper/pipeline`

Goal:
- rename the active runtime directory and package from `scrapper/electronet_single_import` to `scraper/pipeline` without changing runtime behavior, provider behavior, CLI flags, artifact roots, metadata filenames, or workflow semantics

Directories moved:
- `scrapper/` -> `scraper/`
- `scraper/electronet_single_import/` -> `scraper/pipeline/`

Files edited:
- `README.md`
- `AGENTS.md`
- `RULES.md`
- `IMPLEMENT.md`
- `PLAN.md`
- `DOCUMENTATION.md`
- `docs/runbooks/repo-layout.md`
- `docs/checkpoints/IMPLEMENTATION_CHECKPOINT.md`
- `docs/specs/2026-03-22-pipeline-optimization-design.md`
- `scraper/README.md`
- `scraper/pipeline/cli.py`
- `scraper/pipeline/workflow.py`
- `scraper/pipeline/tests/*.py`
- `tools/capture_skroutz_fixture.py`

Changes:
- updated active runtime commands and current-state guidance from `scrapper/` plus `electronet_single_import` to `scraper/` plus `pipeline`
- updated runtime `prog=` strings so the CLI/help surface now shows `python -m pipeline.cli` and `python -m pipeline.workflow`
- updated tracked test imports and the active Skroutz fixture helper script to import from `pipeline`
- updated `IMPLEMENT.md` current path rules to `scraper/pipeline/...` and removed the stale reference to the no-longer-present `scrapper/requirements.txt` from the active dependency guardrail
- updated `PLAN.md` current repo facts, active phase summary paths, and root policy to the renamed layout and marked M23 completed
- kept prior audit and milestone evidence intact; only added a short historical clarification where needed so remaining old-name references stay explicitly historical
- added no compatibility shim because the renamed package executed cleanly with the narrow path/import updates

Commands run:
- `rg -n "scrapper/electronet_single_import|electronet_single_import|cd scrapper|python -m electronet_single_import|scrapper/" .`
- `rg -n "from electronet_single_import|import electronet_single_import|prog=\"python -m electronet_single_import|prog='python -m electronet_single_import" .`
- `rg -n "scrapper/|electronet_single_import|cd scrapper|python -m electronet_single_import" README.md AGENTS.md RULES.md PLAN.md IMPLEMENT.md DOCUMENTATION.md docs/ scraper/ scrapper/`
- `git status --short`
- directory rename command moving `scrapper/` to `scraper/` and `scraper/electronet_single_import/` to `scraper/pipeline/`
- `cd scraper && python -m pipeline.workflow --help`
- `cd scraper && python -m pipeline.cli --help`
- `python -m compileall scraper/pipeline`
- `cd scraper && python -m pytest -q`
- post-rename `rg` sweeps for active and historical references
- `git status --short`

Validation:
- `cd scraper && python -m pipeline.workflow --help`
  - passed
- `cd scraper && python -m pipeline.cli --help`
  - passed
- `python -m compileall scraper/pipeline`
  - passed
- `cd scraper && python -m pytest -q`
  - passed at the accepted baseline: `92 passed, 2 failed`
- the only accepted failing tests remained:
  - `test_enrichment_framework_supports_pdf_candidates`
  - `test_enrichment_framework_supports_html_candidates`
- post-rename sweeps confirmed active commands/docs now use `scraper/` and `pipeline`; remaining old-name hits are preserved historical references only
- the active-surface sweep over `README.md`, `AGENTS.md`, `RULES.md`, `IMPLEMENT.md`, `docs/runbooks/repo-layout.md`, `docs/checkpoints/IMPLEMENTATION_CHECKPOINT.md`, `scraper/`, and `tools/capture_skroutz_fixture.py` returned no old-name matches
- the remaining broad-sweep hits were limited to this M23 rename record, the top-level historical notes, older milestone logs, and already-labeled historical spec/audit material

Risks:
- historical docs and milestone logs still contain pre-M23 names by design; future sweeps should continue treating those sections as preserved evidence, not active guidance

Deferred:
- no compatibility shim was added
- no provider, workflow, dependency, or output-semantics changes were made

## M22 — add provider selection and one second provider proof

Goal:
- add the smallest private provider-selection seam needed to prove a second provider behind the M20 contract without changing CLI/workflow behavior, source detection, default production Skroutz routing, artifact locations, or validation semantics
- keep Electronet as the only production-selected provider and prove `SkroutzProvider` only through deterministic test injection

Files created:
- `scrapper/electronet_single_import/providers/skroutz_provider.py`
- `scrapper/electronet_single_import/tests/test_provider_selection.py`

Files edited:
- `scrapper/electronet_single_import/full_run.py`
- `scrapper/electronet_single_import/providers/__init__.py`
- `scrapper/electronet_single_import/tests/test_workflow.py`
- `PLAN.md`
- `DOCUMENTATION.md`

Changes:
- added `SkroutzProvider` as a fixture-only provider adapter with constructor-injected fixture HTML paths only:
  - no built-in production fixture URL map
  - no live HTTP fetching
  - no Playwright fetching
- added a private `_resolve_provider_for_source(...)` helper in `scrapper/electronet_single_import/full_run.py`
- kept default production routing unchanged:
  - `electronet` resolves to `ElectronetProvider`
  - `skroutz` resolves to no provider by default and continues through the legacy Skroutz branch
  - manufacturer handling remains on the existing non-provider branch
- generalized the existing provider execution block in `full_run.py` so any resolved provider still converts back into the current `FetchResult` and `ParsedProduct` runtime shapes before downstream processing
- exported `SkroutzProvider` from `scrapper/electronet_single_import/providers/__init__.py`
- added focused provider tests that cover:
  - default resolver behavior selecting Electronet only
  - `SkroutzProvider.fetch_snapshot()` reading deterministic fixture HTML
  - `SkroutzProvider.normalize()` returning the expected provider/runtime shapes
  - test-only injection of `SkroutzProvider` through the private resolver seam
- added a workflow regression test proving Skroutz still uses the legacy runtime path by default when no override is applied
- did not change `cli.py`, `workflow.py`, `source_detection.py`, `providers/registry.py`, `providers/base.py`, `providers/models.py`, dependency files, README files, `AGENTS.md`, `RULES.md`, or `IMPLEMENT.md`

Validation:
- `python -m compileall scrapper/electronet_single_import`
  - passed
- `python -m pytest -q electronet_single_import/tests/test_provider_selection.py`
  - passed, `4 passed`
- `python -m pytest -q electronet_single_import/tests/test_workflow.py`
  - passed, `12 passed`
- `python -m pytest -q electronet_single_import/tests/test_skroutz_integration.py`
  - passed, `7 passed`
- `python -m pytest -q electronet_single_import/tests/test_skroutz_sections.py`
  - passed, `5 passed`
- `python -m pytest -q`
  - expected baseline only, `92 passed` and `2 failed`
- the only accepted failing tests remained:
  - `test_enrichment_framework_supports_pdf_candidates`
  - `test_enrichment_framework_supports_html_candidates`

Risks:
- the second-provider proof is intentionally test-only for Skroutz routing; production Skroutz execution still depends on the legacy branch until a later milestone adds a live provider path
- the repo still carries the two pre-existing manufacturer enrichment failures

Deferred:
- production Skroutz provider routing remains deferred
- broader provider routing for manufacturer sources remains deferred
- registry-driven runtime routing remains deferred

## M21 — extract the current primary source into a provider adapter

Goal:
- extract exactly one current primary source flow behind the M20 provider contract by routing the Electronet primary path through a concrete provider adapter without changing runtime inputs, workflow/CLI behavior, artifact locations, validation semantics, or non-Electronet execution paths

Files created:
- `scrapper/electronet_single_import/providers/electronet_provider.py`

Files edited:
- `scrapper/electronet_single_import/full_run.py`
- `scrapper/electronet_single_import/tests/test_workflow.py`
- `PLAN.md`
- `DOCUMENTATION.md`

Primary source extracted:
- `electronet`

Integration points changed:
- `scrapper/electronet_single_import/full_run.py` now routes only the Electronet source branch through `ElectronetProvider`
- `scrapper/electronet_single_import/full_run.py` converts the provider result back into the existing `FetchResult` and `ParsedProduct` runtime shapes before the rest of the pipeline continues
- non-Electronet branches in `full_run.py` continue using the existing Skroutz and manufacturer fetch/parse logic
- `scrapper/electronet_single_import/tests/test_workflow.py` now verifies the Electronet path uses the provider adapter while preserving the existing mismatch-warning and downstream report behavior

Changes:
- added `ElectronetProvider` as the single concrete M21 adapter, with provider metadata aligned to the M20 contract:
  - provider id `electronet`
  - source name `electronet`
  - provider kind `vendor_site`
  - capabilities `url_input`, `live_fetch`, `html_snapshot`, and `normalized_product`
- moved the existing Electronet-only fetch/normalize seam into the provider without widening the M20 contract
- preserved the current Electronet fetch order inside the provider:
  - try HTTPX first
  - fall back to Playwright on fetch failure
- preserved the current Electronet critical-missing recovery inside the provider:
  - if the initial parse still has `critical_missing`, rerun a Playwright fetch and reparse
  - only replace the first parse when the fallback reduces the critical-missing count
- stored fetch-only details not modeled directly by `ProviderSnapshot` in `snapshot.metadata`, specifically `fetch_method` and `fallback_used`
- kept the downstream runtime behavior unchanged by translating the provider result back into the existing local execution models before taxonomy resolution, schema matching, artifact writing, and validation
- left source detection, URL-scope validation, workflow entrypoints, CLI/service entrypoints, Skroutz extraction, and manufacturer enrichment behavior unchanged
- did not add provider selection, registry-driven runtime routing, or a second provider

Commands run:
- `Get-ChildItem -Force`
- `rg --files AGENTS.md RULES.md IMPLEMENT.md PLAN.md DOCUMENTATION.md scrapper/electronet_single_import`
- `Get-Content AGENTS.md`
- `Get-Content RULES.md`
- `Get-Content IMPLEMENT.md`
- `rg -n "M20|M21|provider" PLAN.md DOCUMENTATION.md scrapper/electronet_single_import/providers scrapper/electronet_single_import/full_run.py scrapper/electronet_single_import/services/run_service.py scrapper/electronet_single_import/workflow.py`
- `Get-Content scrapper/electronet_single_import/providers/models.py`
- `Get-Content scrapper/electronet_single_import/providers/base.py`
- `Get-Content scrapper/electronet_single_import/providers/registry.py`
- `Get-Content scrapper/electronet_single_import/providers/__init__.py`
- `Get-Content scrapper/electronet_single_import/full_run.py`
- `Get-Content scrapper/electronet_single_import/source_detection.py`
- `Get-Content scrapper/electronet_single_import/services/run_service.py`
- `Get-Content scrapper/electronet_single_import/workflow.py`
- `Get-Content scrapper/electronet_single_import/parser_product_electronet.py`
- `Get-Content scrapper/electronet_single_import/fetcher.py`
- `Get-Content scrapper/electronet_single_import/parser_product_skroutz.py`
- `Get-Content scrapper/electronet_single_import/parser_product_manufacturer.py`
- `rg -n "execute_full_run|detect_source\(|manufacturer_tefal" scrapper/electronet_single_import`
- `rg -n "electronet" scrapper/electronet_single_import/tests`
- `Get-Content scrapper/electronet_single_import/tests/test_workflow.py`
- `Get-Content scrapper/electronet_single_import/tests/test_services.py`
- `Get-Content PLAN.md | Select-Object -First 120`
- `Get-Content DOCUMENTATION.md | Select-Object -First 120`
- `git status --short`
- `python -m compileall scrapper/electronet_single_import`
- `python -m pytest -q scrapper/electronet_single_import/tests/test_workflow.py`
- `python -m pytest -q` from `scrapper/`
- `python -m pytest -q scrapper/electronet_single_import/tests/test_workflow.py scrapper/electronet_single_import/tests/test_skroutz_integration.py scrapper/electronet_single_import/tests/test_skroutz_sections.py`
- `python -m compileall scrapper/electronet_single_import`
- `python -m pytest -q` from `scrapper/`
- `git status --short`

Validation:
- `python -m compileall scrapper/electronet_single_import` succeeded before and after the final fix
- targeted validation succeeded:
  - `python -m pytest -q scrapper/electronet_single_import/tests/test_workflow.py` returned `11 passed`
  - `python -m pytest -q scrapper/electronet_single_import/tests/test_workflow.py scrapper/electronet_single_import/tests/test_skroutz_integration.py scrapper/electronet_single_import/tests/test_skroutz_sections.py` returned `23 passed`
- `python -m pytest -q` from `scrapper/` returned `87 passed, 2 failed`
- the only accepted failing tests remained:
  - `test_enrichment_framework_supports_pdf_candidates`
  - `test_enrichment_framework_supports_html_candidates`
- one intermediate M21 regression in the Skroutz branch was introduced during extraction and then fixed in `full_run.py`; no new failures remained after the fix

Risks:
- the provider seam is still only proven for the Electronet primary source; runtime provider selection and secondary-provider support remain unimplemented until M22
- the repo still carries the two pre-existing manufacturer enrichment failures

Deferred:
- provider selection and registry-driven runtime routing remain M22 work
- adding a second concrete provider remains M22 work
- expanding provider-based routing beyond the Electronet branch remains deferred
- no changes were made to `cli.py`, `input_validation.py`, `source_detection.py`, dependency files, README files, `AGENTS.md`, `RULES.md`, or `IMPLEMENT.md`

## M20 — define provider contract and registry

Goal:
- define a narrow internal provider abstraction and registration seam for future manufacturer, vendor-site, and fixture-backed adapters without changing current runtime behavior, source detection, workflow wiring, or CLI entrypoints

Files created:
- `scrapper/electronet_single_import/providers/__init__.py`
- `scrapper/electronet_single_import/providers/base.py`
- `scrapper/electronet_single_import/providers/models.py`
- `scrapper/electronet_single_import/providers/registry.py`

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`

Contract elements added:
- `ProviderDefinition` with provider identifier, emitted `source_name`, provider kind, and capability declaration
- `ProviderInputIdentity` with typed optional identity fields for `model`, `url`, `sku`, `brand`, `vendor_code`, `mpn`, and extensible extras
- `ProviderSnapshot` with fetch/snapshot fields for requested and final URL, snapshot kind, content type, status, headers, and text/byte payloads
- `ProviderResult` with normalized product output anchored to current `SourceProductData` plus provenance, field diagnostics, missing-field tracking, warnings, and overall confidence
- `ProviderErrorInfo` and `ProviderError` with structured provider error code, stage, retryability, and details
- `ProductProvider` abstract base contract with `fetch_snapshot(...)` and `normalize(...)`
- `ProviderRegistry` with explicit provider registration, lookup, required lookup, and definition listing

Changes:
- added a new standalone `scrapper/electronet_single_import/providers/` package so the provider seam exists without touching current execution modules
- kept the normalized provider output aligned to the current parser/runtime shape by reusing `SourceProductData` and `FieldDiagnostic` instead of inventing a second normalization model
- separated provider type from runtime source naming via `ProviderKind` and `ProviderDefinition.source_name`
- made the contract broad enough for future vendor-site, manufacturer-site, and fixture-backed adapters through explicit kind, capability, identity, and snapshot enums
- added structured provider error metadata for identity, fetch, normalize, and registry stages
- added a simple in-memory registry for provider registration and lookup only
- did not add any concrete provider adapters
- did not route source detection, `full_run.py`, CLI entrypoints, workflow entrypoints, or the service layer through the new provider package

Commands run:
- `Get-Content AGENTS.md`
- `Get-Content RULES.md`
- `Get-Content IMPLEMENT.md`
- `Get-Content PLAN.md`
- `Get-Content DOCUMENTATION.md`
- `Get-Content scrapper/electronet_single_import/source_detection.py`
- `Get-Content scrapper/electronet_single_import/full_run.py`
- `Get-Content scrapper/electronet_single_import/input_validation.py`
- `Get-Content scrapper/electronet_single_import/services/models.py`
- `Get-Content scrapper/electronet_single_import/services/errors.py`
- `Get-Content scrapper/electronet_single_import/services/run_service.py`
- `Get-ChildItem scrapper/electronet_single_import -File | Select-Object -ExpandProperty Name`
- `rg -n "class Parsed|class .*Source|@dataclass|provenance|confidence|page_type|source_name|critical_missing|field_diagnostics|spec_sections|gallery_images|presentation_source_html|manufacturer_enrichment" scrapper/electronet_single_import -g "*.py"`
- `Get-Content scrapper/electronet_single_import/models.py`
- `Get-Content scrapper/electronet_single_import/manufacturer_enrichment.py`
- `Get-Content scrapper/electronet_single_import/parser_product_electronet.py`
- `Get-Content scrapper/electronet_single_import/parser_product_skroutz.py`
- `Get-Content scrapper/electronet_single_import/parser_product_manufacturer.py`
- `Get-Content scrapper/electronet_single_import/providers/models.py`
- `Get-Content scrapper/electronet_single_import/providers/base.py`
- `Get-Content scrapper/electronet_single_import/providers/registry.py`
- `Get-Content scrapper/electronet_single_import/providers/__init__.py`
- `rg -n "Current milestone|M20|Phase 2 milestones" PLAN.md DOCUMENTATION.md`
- `Get-Content PLAN.md | Select-Object -First 90`
- `Get-Content DOCUMENTATION.md | Select-Object -First 80`
- `python -m compileall scrapper/electronet_single_import`
- `python -m pytest -q` from `scrapper/`
- `git status --short`

Validation:
- `python -m compileall scrapper/electronet_single_import` succeeded
- `python -m pytest -q` from `scrapper/` returned `87 passed, 2 failed`
- the only accepted failing tests remained:
  - `test_enrichment_framework_supports_pdf_candidates`
  - `test_enrichment_framework_supports_html_candidates`
- no new failures were introduced by M20

Risks:
- the new provider contract is intentionally unwired, so it still depends on later milestones to prove adapter extraction and runtime selection
- the repo still carries the two pre-existing manufacturer enrichment failures

Deferred:
- extracting the current Electronet/Skroutz/manufacturer logic into concrete provider adapters remains M21+
- wiring provider selection into runtime behavior remains M22
- provider-contract tests were intentionally deferred in M20 to keep the milestone inside the approved file scope and because the package is currently import-safe and unused by runtime code

## M19a — remove remaining cross-layer imports after service routing

Goal:
- remove the remaining cross-layer imports between `cli.py`, `workflow.py`, and `full_run.py` without changing commands, flags, validation behavior, artifact paths, metadata filenames, or exit semantics

Files created:
- `scrapper/electronet_single_import/input_validation.py`

Files edited:
- `scrapper/electronet_single_import/cli.py`
- `scrapper/electronet_single_import/full_run.py`
- `scrapper/electronet_single_import/tests/test_skroutz_sections.py`
- `scrapper/electronet_single_import/workflow.py`
- `PLAN.md`
- `DOCUMENTATION.md`

Changes:
- moved shared `FAIL_MESSAGE` and `validate_input(...)` into the neutral module `scrapper/electronet_single_import/input_validation.py`
- updated `cli.py` to import validation from the neutral module and removed its unused import of `_select_skroutz_image_backed_sections` from `full_run.py`
- updated `workflow.py` to import `FAIL_MESSAGE` and `validate_input(...)` from the neutral module instead of from `cli.py`
- updated `full_run.py` to import `FAIL_MESSAGE` from the neutral module so it remains an execution module rather than a shared constants bucket
- updated `test_skroutz_sections.py` to import `_select_skroutz_image_backed_sections` from its actual lower-layer owner, `full_run.py`
- kept `execute_full_run(...)` in `full_run.py` and left service-layer contracts unchanged

Cross-layer imports removed:
- `scrapper/electronet_single_import/cli.py` no longer imports `FAIL_MESSAGE` or `_select_skroutz_image_backed_sections` from `scrapper/electronet_single_import/full_run.py`
- `scrapper/electronet_single_import/workflow.py` no longer imports `FAIL_MESSAGE` or `validate_input(...)` from `scrapper/electronet_single_import/cli.py`

Commands run:
- `Get-Content AGENTS.md`
- `Get-Content RULES.md`
- `Get-Content IMPLEMENT.md`
- `Get-Content scrapper/electronet_single_import/cli.py`
- `Get-Content scrapper/electronet_single_import/workflow.py`
- `Get-Content scrapper/electronet_single_import/full_run.py`
- `Get-Content scrapper/electronet_single_import/services/run_service.py`
- `Get-Content scrapper/electronet_single_import/models.py`
- `Get-Content PLAN.md`
- `Get-Content DOCUMENTATION.md`
- `rg -n "FAIL_MESSAGE|validate_input|_select_skroutz_image_backed_sections|execute_full_run|from \\.cli|from \\.full_run" scrapper/electronet_single_import -g "*.py"`
- `Get-Content scrapper/electronet_single_import/tests/test_workflow.py`
- `Get-Content scrapper/electronet_single_import/tests/test_services.py`
- `Get-Content scrapper/electronet_single_import/tests/test_skroutz_sections.py`
- `Get-Content scrapper/electronet_single_import/tests/test_skroutz_integration.py`
- `rg -n "from electronet_single_import\\.cli import _select_skroutz_image_backed_sections|from \\.full_run import FAIL_MESSAGE|from \\.cli import FAIL_MESSAGE, validate_input" scrapper/electronet_single_import/tests scrapper/electronet_single_import -g "*.py"`
- `rg -n "Current milestone|M19 —|M20|M19a" PLAN.md DOCUMENTATION.md`
- `Get-Content PLAN.md -TotalCount 80`
- `Get-Content DOCUMENTATION.md -TotalCount 120`
- `python -m compileall scrapper/electronet_single_import`
- `python -m pytest -q electronet_single_import/tests/test_workflow.py electronet_single_import/tests/test_services.py electronet_single_import/tests/test_skroutz_integration.py electronet_single_import/tests/test_skroutz_sections.py` from `scrapper/`
- `python -m pytest -q` from `scrapper/`
- `git status --short`

Validation:
- `python -m compileall scrapper/electronet_single_import` succeeded
- `python -m pytest -q electronet_single_import/tests/test_workflow.py electronet_single_import/tests/test_services.py electronet_single_import/tests/test_skroutz_integration.py electronet_single_import/tests/test_skroutz_sections.py` from `scrapper/` passed with `29 passed`
- `python -m pytest -q` from `scrapper/` returned `87 passed, 2 failed`
- the only accepted failing tests remained:
  - `test_enrichment_framework_supports_pdf_candidates`
  - `test_enrichment_framework_supports_html_candidates`
- `git status --short` showed only the expected M19a edits plus the new neutral helper module

Risks:
- the repo still carries the two pre-existing manufacturer enrichment failures
- `cli.py` still re-exports `validate_input(...)` by import for backward-compatible test and caller access, but the implementation now lives in the neutral module rather than in the CLI layer

Deferred:
- no service-layer files were changed because the boundary cleanup did not require contract adjustments
- no provider abstraction work was started; that remains M20

## M19 — route CLI through the service layer

Goal:
- refactor the CLI-facing entrypoints to call the M18 service layer instead of duplicating orchestration logic, while preserving command names, flags, exit semantics, artifact locations, metadata filenames, and provider behavior

Files edited:
- `scrapper/electronet_single_import/cli.py`
- `scrapper/electronet_single_import/full_run.py`
- `scrapper/electronet_single_import/services/run_service.py`
- `scrapper/electronet_single_import/tests/test_services.py`
- `scrapper/electronet_single_import/tests/test_workflow.py`
- `scrapper/electronet_single_import/workflow.py`
- `PLAN.md`
- `DOCUMENTATION.md`

Changes:
- extracted the pre-existing standalone full-run implementation into the lower-layer module `scrapper/electronet_single_import/full_run.py`
- changed `run_cli_input()` into a thin CLI adapter that builds `FullRunRequest` and calls `run_product()`
- restored `run_product()` to orchestrate below the CLI layer through `prepare_product()` and `render_product()` rather than calling anything in `cli.py`
- kept `FullRunRequest.out` so the CLI adapter can pass output-root intent into the service layer without inverting module dependencies
- routed `python -m electronet_single_import.workflow prepare` through `prepare_product()` and `python -m electronet_single_import.workflow render` through `render_product()`
- updated `prepare_workflow()` to use the extracted lower-layer executor instead of importing standalone CLI orchestration
- added focused tests that verify CLI-to-service routing and that the service layer composes stage services without importing `cli.py`

Commands run:
- `Get-Content AGENTS.md`
- `Get-Content RULES.md`
- `Get-Content scrapper/electronet_single_import/cli.py`
- `Get-Content scrapper/electronet_single_import/workflow.py`
- `Get-ChildItem scrapper/electronet_single_import/services -Recurse -File | Select-Object -ExpandProperty FullName`
- `Get-Content PLAN.md`
- `Get-Content DOCUMENTATION.md`
- `Get-Content scrapper/electronet_single_import/services/prepare_service.py`
- `Get-Content scrapper/electronet_single_import/services/render_service.py`
- `Get-Content scrapper/electronet_single_import/services/run_service.py`
- `Get-Content scrapper/electronet_single_import/services/models.py`
- `rg -n "run_cli_input\\(|prepare_workflow\\(|render_workflow\\(|prepare_product\\(|render_product\\(|run_product\\(" scrapper/electronet_single_import -g "*.py"`
- `Get-Content scrapper/electronet_single_import/services/__init__.py`
- `Get-Content scrapper/electronet_single_import/services/errors.py`
- `Get-Content scrapper/electronet_single_import/tests/test_services.py`
- `Get-Content scrapper/electronet_single_import/tests/test_workflow.py`
- `rg -n "def test_.*main|cli\\.main\\(|workflow\\.main\\(" scrapper/electronet_single_import/tests -g "*.py"`
- `git status --short`
- `python -m compileall scrapper/electronet_single_import`
- `python -m pytest -q electronet_single_import/tests/test_services.py electronet_single_import/tests/test_workflow.py` from `scrapper/`
- `python -m pytest -q` from `scrapper/`
- `git status --short`

Validation:
- `python -m compileall scrapper/electronet_single_import` succeeded
- `python -m pytest -q electronet_single_import/tests/test_services.py electronet_single_import/tests/test_workflow.py` from `scrapper/` passed with `17 passed`
- `python -m pytest -q` from `scrapper/` returned `87 passed, 2 failed`
- the only accepted failing tests remained:
  - `test_enrichment_framework_supports_pdf_candidates`
  - `test_enrichment_framework_supports_html_candidates`
- no new unexpected failures were introduced by M19

Risks:
- the repo still carries the two pre-existing manufacturer enrichment failures
- standalone CLI metadata emission still remains a CLI concern because the service layer intentionally does not emit `full.run.json`

Deferred:
- no provider-contract work was started; that remains M20
- no dependency files, provider logic, README files, `AGENTS.md`, `RULES.md`, or `IMPLEMENT.md` were changed

## M18 — add service layer models/errors/wrappers

Goal:
- add a thin internal service layer around the existing prepare/render workflow stages using the M15 contract and M16/M17 stage metadata, without rerouting CLI entrypoints, changing workflow semantics, or introducing new runtime artifact or metadata filenames

Files created:
- `scrapper/electronet_single_import/services/errors.py`
- `scrapper/electronet_single_import/services/prepare_service.py`
- `scrapper/electronet_single_import/services/render_service.py`
- `scrapper/electronet_single_import/services/run_service.py`
- `scrapper/electronet_single_import/tests/test_services.py`

Files edited:
- `scrapper/electronet_single_import/services/__init__.py`
- `PLAN.md`
- `DOCUMENTATION.md`

Service entrypoints added:
- `prepare_product(request: PrepareRequest) -> ServiceResult`
- `render_product(request: RenderRequest) -> ServiceResult`
- `run_product(request: FullRunRequest) -> ServiceResult`

Changes:
- added a small internal `ServiceError` wrapper with stable `code`, `message`, and optional `cause`
- added `prepare_product()` as a thin wrapper over `workflow.prepare_workflow()` that converts the M15 request into `CLIInput`, reuses the existing prepare-stage metadata file, and returns a `ServiceResult` with scrape/prompt artifact paths
- added `render_product()` as a thin wrapper over `workflow.render_workflow()` that reuses the existing render-stage metadata file and returns a `ServiceResult` with candidate and validation artifact paths
- added `run_product()` as an internal composition layer over `prepare_product()` then `render_product()` and kept full-run aggregation inside `ServiceResult.details`
- did not emit `full.run.json` from the new service layer
- did not modify `cli.py`
- did not modify `workflow.py`
- kept runtime behavior unchanged by leaving CLI entrypoints, workflow semantics, output locations, provider logic, and metadata filenames untouched

Commands run:
- `Get-Content AGENTS.md`
- `Get-Content RULES.md`
- `Get-Content scrapper/electronet_single_import/workflow.py`
- `Get-Content scrapper/electronet_single_import/services/__init__.py`
- `Get-Content scrapper/electronet_single_import/services/models.py`
- `Get-Content scrapper/electronet_single_import/services/metadata.py`
- `Get-Content scrapper/electronet_single_import/models.py`
- `Get-Content scrapper/electronet_single_import/tests/test_workflow.py`
- `rg -n "class CLIInput|@dataclass\\(.*CLIInput|CLIInput\\(" scrapper/electronet_single_import/models.py scrapper/electronet_single_import -g "*.py"`
- `rg --files scrapper/electronet_single_import/tests`
- `rg -n "class .*Error|ServiceError|error_code|run_status" scrapper/electronet_single_import -g "*.py"`
- `Get-Content PLAN.md -TotalCount 90`
- `Get-Content DOCUMENTATION.md -TotalCount 120`
- `python -m compileall scrapper/electronet_single_import`
- `python -m pytest -q electronet_single_import/tests/test_services.py` from `scrapper/`
- `python -m pytest -q` from `scrapper/`
- `git status --short`

Validation:
- `python -m compileall scrapper/electronet_single_import` succeeded
- `python -m pytest -q electronet_single_import/tests/test_services.py` from `scrapper/` passed with `6 passed`
- `python -m pytest -q` from `scrapper/` returned `84 passed, 2 failed`
- the only known failing tests remained:
  - `test_enrichment_framework_supports_pdf_candidates`
  - `test_enrichment_framework_supports_html_candidates`
- no new unexpected test failures were introduced by M18

Risks:
- the full suite still has the two pre-existing manufacturer enrichment failures
- the service layer currently returns aggregated full-run metadata paths through `ServiceResult.details`, not a dedicated full-run metadata artifact, by design for M18

Deferred:
- routing CLI entrypoints through the service layer remains deferred to M19
- no new runtime metadata file is emitted for `run_product()` in M18
- no workflow or CLI refactor beyond the additive service wrapper layer was performed in M18

## M17 — make CLI/workflow emit metadata

Goal:
- make the current CLI and workflow surfaces emit a structured run status and metadata file path without changing command names, flags, exit codes, workflow semantics, or existing artifact locations

Files edited:
- `scrapper/electronet_single_import/cli.py`
- `scrapper/electronet_single_import/services/metadata.py`
- `scrapper/electronet_single_import/workflow.py`
- `PLAN.md`
- `DOCUMENTATION.md`

Changes:
- promoted the metadata write helper into `scrapper/electronet_single_import/services/metadata.py` so both CLI and workflow can reuse the same run-status and metadata serialization path
- kept `prepare_workflow()` and `render_workflow()` additive-only by returning `run_status` alongside the existing result fields
- updated `python -m electronet_single_import.workflow prepare` to print the completed run status and the emitted `prepare.run.json` path after the existing scrape/prompt artifact lines
- updated `python -m electronet_single_import.workflow render` to print the completed run status and the emitted `render.run.json` path after the existing candidate/validation lines
- added best-effort standalone CLI metadata emission as `full.run.json` in the current CLI output model directory and surfaced its run status plus metadata path in the CLI output
- kept existing CLI flags, command names, exit-code behavior, workflow artifact locations, provider behavior, and validation semantics unchanged

Commands run:
- `Get-Content AGENTS.md`
- `Get-Content RULES.md`
- `Get-Content scrapper/electronet_single_import/cli.py`
- `Get-Content scrapper/electronet_single_import/workflow.py`
- `Get-Content scrapper/electronet_single_import/services/models.py`
- `Get-Content scrapper/electronet_single_import/services/metadata.py`
- `Get-Content PLAN.md`
- `Get-Content DOCUMENTATION.md`
- `rg -n "metadata_path|RunStatus|prepare_workflow\\(|render_workflow\\(|Validation ok|LLM context:|Candidate CSV:" scrapper/electronet_single_import/tests scrapper/electronet_single_import`
- `Get-Content scrapper/electronet_single_import/tests/test_workflow.py`
- `rg -n "M17|emit metadata|run status|metadata path" PLAN.md DOCUMENTATION.md scrapper/electronet_single_import -g "*.md" -g "*.py"`
- `rg -n "electronet_single_import\\.cli|python -m electronet_single_import\\.cli|--out" README.md scrapper/README.md scrapper/electronet_single_import/tests -g "*.md" -g "*.py"`
- `python -m compileall scrapper/electronet_single_import`
- `python -m pytest -q` from `scrapper/`
- `python -m pytest -q electronet_single_import/tests/test_workflow.py` from `scrapper/`
- `git status --short`

Validation:
- `python -m compileall scrapper/electronet_single_import` succeeded
- `python -m pytest -q electronet_single_import/tests/test_workflow.py` from `scrapper/` passed with `8 passed`
- `python -m pytest -q` from `scrapper/` returned `78 passed, 2 failed`
- unchanged accepted failing tests:
  - `test_enrichment_framework_supports_pdf_candidates`
  - `test_enrichment_framework_supports_html_candidates`
- `git status --short` showed only the expected M17 edits

Risks:
- no new test failures were introduced by M17
- standalone CLI metadata now adds one new sidecar file, `full.run.json`, under the existing CLI output model directory; existing artifacts and paths remain unchanged

Deferred:
- no CLI UX redesign beyond the additive status and metadata-path lines
- service-layer wrappers and CLI routing through that layer remain deferred to M18-M19
- no test-file changes were made in M17; coverage for the new surface lines still relies on compile, existing workflow tests, and the unchanged full-suite baseline

## M16 — write structured run metadata alongside current files

Goal:
- emit structured metadata sidecar files for the current prepare and render workflow stages without changing existing artifact contents or runtime semantics

Files created:
- `scrapper/electronet_single_import/services/metadata.py`

Files edited:
- `scrapper/electronet_single_import/workflow.py`
- `scrapper/electronet_single_import/tests/test_workflow.py`
- `PLAN.md`
- `DOCUMENTATION.md`

Metadata files emitted by stage:
- `work/{model}/prepare.run.json`
- `work/{model}/render.run.json`

Changes:
- added metadata serialization and writing helpers in `scrapper/electronet_single_import/services/metadata.py`
- used the M15 run contract models as the metadata source shape
- wrote prepare metadata after prompt artifacts are emitted and render metadata after candidate artifacts are emitted
- added best-effort failed-run metadata emission when prepare or render raise after the model work directory is known
- kept existing workflow artifact filenames, locations, and CLI output formatting unchanged
- updated `PLAN.md` to mark M16 complete and note metadata emission

Commands run:
- `Get-Content scrapper/electronet_single_import/workflow.py`
- `Get-Content scrapper/electronet_single_import/cli.py`
- `Get-Content scrapper/electronet_single_import/services/models.py`
- `Get-Content scrapper/electronet_single_import/tests/test_workflow.py`
- `python -m pytest -q electronet_single_import/tests/test_workflow.py` from `scrapper/`
- `python -m pytest -q` from `scrapper/`
- `python -m compileall scrapper/electronet_single_import`
- `git status --short`

Validation:
- `python -m compileall scrapper/electronet_single_import` succeeded
- `python -m pytest -q electronet_single_import/tests/test_workflow.py` from `scrapper/` passed
- `python -m pytest -q` from `scrapper/` returned `78 passed, 2 failed`
- unchanged failing tests:
  - `test_enrichment_framework_supports_pdf_candidates`
  - `test_enrichment_framework_supports_html_candidates`
- `git status --short` confirmed the expected M16 file changes

Risks:
- no new M16 failures were introduced; the only remaining failures are the pre-existing manufacturer enrichment tests
- the full-suite pass count increased from `76` to `78` because M16 added two focused workflow metadata tests while keeping the same two known failing tests

Deferred:
- CLI-facing metadata output changes remain deferred to M17
- service-layer wrappers and routing remain deferred to later milestones
- no metadata is emitted for failures that occur before a model work directory can be determined
  - this preserves current runtime behavior while keeping metadata writing best-effort

## M15 — define run contract

Goal:
- add import-safe run contract models for future service, metadata, CLI, and API seams without changing current runtime behavior

Files created:
- `scrapper/electronet_single_import/services/__init__.py`
- `scrapper/electronet_single_import/services/models.py`

Files edited:
- `PLAN.md`
- `DOCUMENTATION.md`

Models added:
- `RunType`
- `RunStatus`
- `PrepareRequest`
- `RenderRequest`
- `FullRunRequest`
- `RunArtifacts`
- `RunMetadata`
- `ServiceResult`

Changes:
- created the new `scrapper/electronet_single_import/services/` package as import-safe package setup only
- added contract-only dataclass and enum definitions in `scrapper/electronet_single_import/services/models.py`
- included the planned `metadata_path` artifact field so M16 can emit metadata without reshaping the contract
- kept metadata-facing warnings and error fields on `RunMetadata`
- kept `ServiceResult` lean with only `run`, `artifacts`, and `details`
- updated `PLAN.md` to mark M15 complete and note that the run contract exists but is not wired into runtime behavior

Validation:
- `python -m compileall scrapper/electronet_single_import` succeeded
- `python -m pytest -q` from `scrapper/` did not match the requested baseline and finished at `69 passed, 9 failed`
- failing tests:
  - `test_enrichment_framework_supports_pdf_candidates`
  - `test_enrichment_framework_supports_html_candidates`
  - `test_skroutz_parser_and_deterministic_fields_cover_supported_families`
  - `test_prepare_and_render_workflow_with_skroutz_fixtures`
  - `test_143481_html_fixture_resolves_9_sections_in_stable_order`
  - `test_placeholder_urls_are_rejected_for_resolved_section_images`
  - `test_143481_rendered_description_preserves_locked_wrappers`
  - `test_taxonomy_regression_fixture_resolves_expected_categories`
  - `test_representative_taxonomy_html_fixtures_cover_supported_skroutz_combos`
- `git status --short` confirmed only the expected milestone files changed, alongside the pre-existing untracked `.claude/worktrees/`

Risks:
- the current repo test baseline does not match the milestone's expected `75 passed, 2 failed` result
- seven additional Skroutz fixture-path failures are present in `test_skroutz_integration.py`, `test_skroutz_sections.py`, and `test_skroutz_taxonomy.py`, all failing with `FileNotFoundError` against hardcoded absolute fixture paths outside the current workspace
- the two existing manufacturer enrichment failures remain in `test_manufacturer_enrichment.py`

Deferred:
- metadata emission and file writing remain deferred to M16
- runtime wiring for CLI and workflow remains deferred to later milestones
- serializers, validators, helper methods, and service wrappers remain intentionally out of scope for M15

## Pre-M15 control-doc refresh

Goal:
- align repository control documents with the post-cleanup architecture phase
- remove cleanup-only ambiguity before M15-M22
- separate milestone governance from runtime execution guidance

Files edited:
- `PLAN.md`
- `IMPLEMENT.md`
- `DOCUMENTATION.md`
- `AGENTS.md`
- `RULES.md`

Changes:
- promoted `PLAN.md` from cleanup-only framing to full active roadmap framing
- added the Phase 2 architecture milestones M15-M22
- added explicit hybrid-RAG gating
- updated `IMPLEMENT.md` to govern milestone execution for the new phase
- updated `AGENTS.md` and `RULES.md` so runtime input scope matches the actual code-supported source scope
- marked M15 as the next active milestone

Validation:
- docs-only review
- no runtime files changed
- no dependency files changed

Risks:
- none for runtime behavior; this commit changes guidance only

Deferred:
- `README.md` refresh
- any user-facing architecture overview
- milestone-specific implementation entries starting at M15

## Historical reference note
- Completed milestone entries, audit summaries, and command logs below preserve prior-state file paths intentionally.
- When older sections mention paths such as `docs/superpowers/specs/...`, `work/IMPLEMENTATION_CHECKPOINT.md`, root support-asset filenames, `RULES_legacy.md`, `master_prompt_legacy.txt`, or `scrapper/requirements.txt`, read them as historical pre-M4, pre-M5, pre-M6, or pre-M10 references unless the section explicitly states current guidance.

## Repo invariants
- Active runnable code lives under `scrapper/electronet_single_import/`.
- `products/` remains the final CSV/output area.
- `work/{model}/...` remains the runtime artifact area.
- Legacy files must be archived, not deleted casually.
- Shared support assets now live under `resources/` and remain centrally resolved through `scrapper/electronet_single_import/repo_paths.py`.

## Milestone log

### M1 — Control files and cleanup directories
Status: completed
Goal:
- add approved scaffolding directories and log the milestone without changing runtime behavior

Changes:
- created `docs/audits/`, `docs/runbooks/`, `docs/checkpoints/`, `docs/specs/`, `archive/legacy/`, `resources/mappings/`, `resources/prompts/`, `resources/schemas/`, and `resources/templates/`
- added `.gitkeep` in each created target directory because it would otherwise remain empty and would not appear in Git status
- updated `PLAN.md` to mark M1 complete and record that the control docs already existed before execution
- updated `DOCUMENTATION.md` with milestone results, commands, validation, risks, and follow-up

Validation:
- pre-creation filesystem check confirmed all nine approved target directories were absent
- post-creation filesystem check confirmed all nine approved target directories exist, each contains `.gitkeep`, and no extra contents were added
- `python -m pytest -q` from `scrapper/` remained at the expected baseline: `75 passed, 2 failed`
- unchanged failing tests: `test_enrichment_framework_supports_pdf_candidates`, `test_enrichment_framework_supports_html_candidates`

Notes:
- `PLAN.md`, `IMPLEMENT.md`, and `DOCUMENTATION.md` already existed before M1; this milestone did not recreate them
- `IMPLEMENT.md` was intentionally not edited because no new recurring execution rule was discovered
- scraper smoke validation was intentionally skipped because pathing and runtime behavior were unchanged
- current repo-root support assets remain in place as source-of-truth files
- empty directories alone would not appear in Git status without `.gitkeep`

### M2 — Repo cleanup audit
Status: completed
Goal:
- classify root files and cleanup candidates

Changes:
- created `docs/audits/repo_cleanup_audit.md`
- classified every current root-level file into `keep in root`, `move later after path centralization`, `archive as legacy`, or `uncertain`
- explicitly classified `schemas/compact_response.schema.json` as `move later after path centralization`
- explicitly classified `docs/specs/2026-03-22-pipeline-optimization-design.md` and `docs/checkpoints/IMPLEMENTATION_CHECKPOINT.md` as safe `move now` candidates
- documented evidence for non-obvious classifications from runtime path callsites and current repo docs
- updated `PLAN.md` to mark M2 complete

Validation:
- root inventory and candidate existence checks completed
- `rg` evidence sweep completed for every explicitly named file or candidate
- `python -m pytest -q` from `scrapper/` remained at the expected baseline: `75 passed, 2 failed`
- unchanged failing tests: `test_enrichment_framework_supports_pdf_candidates`, `test_enrichment_framework_supports_html_candidates`

Notes:
- no requested classification was downgraded to `uncertain` due to contradictory live evidence in this pass
- `requirements.txt` remains `uncertain` and is intentionally postponed to the dependency audit milestone
- scraper smoke validation was intentionally skipped because pathing and runtime behavior were unchanged
- no files were moved or deleted in this milestone

### M3 — Path centralization
Status: completed
Goal:
- add `repo_paths.py` and remove scattered support-file path assumptions

Changes:
- created `scrapper/electronet_single_import/repo_paths.py`
- replaced these approved direct support-asset path constructions in `scrapper/electronet_single_import/utils.py`: `PRODUCT_TEMPLATE_PATH`, `PRESENTATION_TEMPLATE_PATH`, `CATALOG_TAXONOMY_PATH`, `SCHEMA_LIBRARY_PATH`, `CHARACTERISTICS_TEMPLATES_PATH`, `FILTER_MAP_PATH`, `NAME_RULES_PATH`, `DIFFERENTIATOR_PRIORITY_MAP_PATH`, `MASTER_PROMPT_PATH`, `COMPACT_RESPONSE_SCHEMA_PATH`, and `MANUFACTURER_SOURCE_MAP_PATH`
- kept the existing path constant names available from `utils.py` so downstream modules did not need churn
- updated `scrapper/electronet_single_import/tests/test_utils_support_paths.py` to validate centralized path resolution from `repo_paths.py`
- updated `PLAN.md` to mark M3 complete without changing the asset locations

Validation:
- pre-edit `rg` confirmed the approved direct support-asset callsites were in `scrapper/electronet_single_import/utils.py`
- post-edit `rg` confirmed the approved support-asset filename literals are now owned by `scrapper/electronet_single_import/repo_paths.py`
- `python -m pytest -q electronet_single_import/tests/test_utils_support_paths.py` from `scrapper/` passed
- `python -m pytest -q` from `scrapper/` remained at the expected baseline: `75 passed, 2 failed`
- unchanged failing tests: `test_enrichment_framework_supports_pdf_candidates`, `test_enrichment_framework_supports_html_candidates`

Notes:
- unresolved out-of-scope direct path assumptions remain in `scrapper/electronet_single_import/workflow.py` for `work/` and `products/`
- hardcoded absolute repo paths remain in some tests and were intentionally left out of scope for this milestone
- scraper smoke validation was intentionally skipped because pytest plus code inspection was sufficient for this path-only change
- no support assets were moved or renamed

### M4 — Safe docs/checkpoint moves
Status: completed
Goal:
- move the two approved non-runtime documentation and planning files out of their old locations without changing runtime behavior

Changes:
- moved the pipeline optimization design doc into `docs/specs/2026-03-22-pipeline-optimization-design.md`
- moved the implementation checkpoint into `docs/checkpoints/IMPLEMENTATION_CHECKPOINT.md`
- updated path references in `PLAN.md`, `DOCUMENTATION.md`, and `docs/audits/repo_cleanup_audit.md`

Validation:
- pre-move checks confirmed both source files existed and both destination files were absent
- post-move checks confirmed the old source files no longer exist and the new destination files do exist
- `rg` for the old paths returned no remaining references after the updates
- `python -m pytest -q` from `scrapper/` remained at the expected baseline: `75 passed, 2 failed`
- unchanged failing tests: `test_enrichment_framework_supports_pdf_candidates`, `test_enrichment_framework_supports_html_candidates`

Notes:
- no runtime code was edited
- no support assets were moved
- scraper smoke validation was intentionally skipped because no runtime pathing or behavior changed
- empty directories were intentionally left in place because they may still be part of the intended docs/work scaffolding
- the remaining old-path mentions are intentionally preserved in the command log as historical execution records

### M5 — Legacy archive move
Status: completed
Goal:
- archive the two approved historical reference files without changing runtime behavior

Changes:
- moved `RULES_legacy.md` to `archive/legacy/RULES_legacy.md`
- moved `master_prompt_legacy.txt` to `archive/legacy/master_prompt_legacy.txt`
- removed `archive/legacy/.gitkeep` because the archive directory now contains real files
- updated path references in `PLAN.md`, `DOCUMENTATION.md`, `RULES.md`, `docs/audits/repo_cleanup_audit.md`, and `archive/legacy/master_prompt_legacy.txt`

Validation:
- pre-move checks confirmed both source files existed and both archive destinations were absent
- post-move checks confirmed the old source files no longer exist and the new archive paths do exist
- `rg` for the old paths returned no remaining references outside intentional historical command-log mentions
- `python -m pytest -q` from `scrapper/` remained at the expected baseline: `75 passed, 2 failed`
- unchanged failing tests: `test_enrichment_framework_supports_pdf_candidates`, `test_enrichment_framework_supports_html_candidates`

Notes:
- no runtime code was edited
- no active support assets were moved
- scraper smoke validation was intentionally skipped because no runtime pathing or behavior changed
- no additional files were archived in this milestone

### M6 — Support asset relocation into `resources/`
Status: completed

### M7 — Documentation normalization
Status: completed

### M8 — Dependency audit
Status: completed

### M9 — Final health pass
Status: completed

## M6 detail
Goal:
- move the approved shared support assets into `resources/` without changing runtime behavior

Changes:
- moved `MANUFACTURER_SOURCE_MAP.json`, `catalog_taxonomy.json`, `filter_map.json`, `name_rules.json`, `differentiator_priority_map.csv`, and `taxonomy_mapping_template.csv` into `resources/mappings/`
- moved `electronet_schema_library.json`, `schema_index.csv`, and `compact_response.schema.json` into `resources/schemas/`
- moved `TEMPLATE_presentation.html`, `characteristics_templates.json`, and `product_import_template.csv` into `resources/templates/`
- moved `master_prompt+.txt` into `resources/prompts/`
- updated `scrapper/electronet_single_import/repo_paths.py` so the centralized support-asset constants resolve from `resources/`
- updated `scrapper/electronet_single_import/tests/test_utils_support_paths.py` to validate the `resources/` layout
- updated active path references in `README.md`, `RULES.md`, `AGENTS.md`, `scrapper/README.md`, `docs/audits/repo_cleanup_audit.md`, and `PLAN.md`
- removed `.gitkeep` from `resources/mappings/`, `resources/schemas/`, `resources/templates/`, and `resources/prompts/` after those directories became non-empty
- removed the old `schemas/` directory after `compact_response.schema.json` moved and the directory became empty

Validation:
- pre-move checks confirmed every approved source existed and every approved destination was absent
- post-move checks confirmed the old source paths no longer contain the moved files and the new `resources/` paths do contain them
- `rg` for the old asset paths confirmed active references were updated, with old basenames preserved only in historical records where intentionally retained
- `rg` for the new `resources/` paths confirmed runtime and active guidance ownership moved to `resources/`
- `python -m pytest -q electronet_single_import/tests/test_utils_support_paths.py` from `scrapper/` passed
- `python -m pytest -q` from `scrapper/` remained at the expected baseline: `75 passed, 2 failed`
- unchanged failing tests: `test_enrichment_framework_supports_pdf_candidates`, `test_enrichment_framework_supports_html_candidates`

Notes:
- no runtime code outside `scrapper/electronet_single_import/repo_paths.py` was changed
- downstream runtime imports remained stable because existing constant names were preserved
- scraper smoke validation was intentionally skipped because the targeted path test, full pytest run, and code inspection were sufficient for this relocation-only milestone
- archived legacy files and historical command-log entries still contain old basenames intentionally and were not rewritten as part of M6

## M7 detail
Goal:
- normalize repo layout documentation after the M6 `resources/` move without changing runtime behavior

Changes:
- updated `README.md` to describe the post-M6 repo layout and current directory responsibilities
- created `docs/runbooks/repo-layout.md` as the practical repo-specific layout guide
- updated `PLAN.md` to mark M7 completed after the documentation normalization pass
- corrected documentation drift in active layout guidance without changing `AGENTS.md`, `RULES.md`, `IMPLEMENT.md`, or runtime code

Validation:
- `rg` over repo docs confirmed active layout guidance now points to `resources/` for shared support assets
- `rg` over repo docs confirmed `docs/checkpoints/IMPLEMENTATION_CHECKPOINT.md` and `docs/specs/2026-03-22-pipeline-optimization-design.md` are the current post-M4 locations in active guidance, with old-path mentions retained only in historical command logs
- `python -m pytest -q` from `scrapper/` remained at the expected baseline: `75 passed, 2 failed`
- unchanged failing tests: `test_enrichment_framework_supports_pdf_candidates`, `test_enrichment_framework_supports_html_candidates`

Notes:
- `AGENTS.md`, `RULES.md`, and runtime Python files were intentionally left unchanged because no broken active layout reference was found in them during M7
- scraper smoke validation was intentionally skipped because this was a docs-only milestone

## M8 detail
Goal:
- audit dependency ownership for `requirements.txt` and `scrapper/requirements.txt` without changing dependency files or runtime behavior

Changes:
- created `docs/audits/dependency_audit.md`
- recorded a side-by-side comparison of the two dependency files
- documented current live usage evidence from install instructions, control docs, and import scans
- updated `PLAN.md` to mark M8 completed with an audit-only result

Validation:
- file inspection completed for `requirements.txt` and `scrapper/requirements.txt`
- `rg` captured current references to dependency files and install commands across repo docs
- live import scans confirmed scraper/runtime imports for `httpx`, `playwright`, `beautifulsoup4`, `pypdf`, `PIL`, and `pillow_avif`, while no live `requests` import was found
- `python -m pytest -q` from `scrapper/` remained at the expected baseline: `75 passed, 2 failed`
- unchanged failing tests: `test_enrichment_framework_supports_pdf_candidates`, `test_enrichment_framework_supports_html_candidates`

Notes:
- the audit concludes that `scrapper/requirements.txt` is the only currently documented install target, but not yet the only file that appears required by live evidence
- dependency ownership remains audit-only and no dependency file was modified
- scraper smoke validation was intentionally skipped because this milestone did not change runtime behavior

## M9 detail
Goal:
- record a final post-cleanup repo health pass without changing runtime behavior

Changes:
- created `docs/audits/post_cleanup_health_pass.md`
- recorded the final repo-health summary, confirmed remaining issues, safe follow-up items, risky postponed items, and the recommended next action
- updated `PLAN.md` to mark M9 completed with an audit-only result

Validation:
- targeted `rg` searches confirmed no active guidance drift for the approved M4, M5, and M6 path changes
- targeted searches confirmed the main remaining issues are deferred items: dependency ownership, redundant `.gitkeep` files in non-empty `docs/` directories, `workflow.py` output-root assumptions, and hardcoded absolute repo paths in some tests
- `python -m pytest -q` from `scrapper/` remained at the expected baseline: `75 passed, 2 failed`
- unchanged failing tests: `test_enrichment_framework_supports_pdf_candidates`, `test_enrichment_framework_supports_html_candidates`

Notes:
- no files were moved or deleted in M9
- no dependency files were changed
- no runtime code was edited
- scraper smoke validation was intentionally skipped because this was an audit-only milestone

## M10 detail
Goal:
- consolidate dependency ownership to one canonical repo-root `requirements.txt` without changing runtime behavior

Changes:
- updated repo-root `requirements.txt` to the verified canonical dependency union:
  - kept the scraper pins for `httpx`, `beautifulsoup4`, `lxml`, `playwright`, `pytest`, and `pypdf`
  - retained `pillow` and `pillow-avif-plugin` because live scraper imports still require them
  - removed `requests` because no live import evidence remained and clean-environment verification succeeded without it
- removed `scrapper/requirements.txt` after clean-environment verification succeeded
- updated `scrapper/README.md` so dependency installation now points to the canonical repo-root `requirements.txt`
- updated `PLAN.md` to mark M10 completed

Validation:
- captured the pre-edit dependency overlap between root and scraper files
- created a clean temporary virtual environment outside the repo
- installed dependencies from repo-root `requirements.txt` only
- import checks passed for `httpx`, `playwright`, `bs4`, `pypdf`, `PIL`, and `pillow_avif`
- full `python -m pytest -q` from `scrapper/` under the clean environment remained at the expected baseline: `75 passed, 2 failed`
- unchanged failing tests: `test_enrichment_framework_supports_pdf_candidates`, `test_enrichment_framework_supports_html_candidates`
- active install guidance no longer depends on `scrapper/requirements.txt`

Notes:
- runtime behavior remained unchanged because no runtime code was modified
- remaining `scrapper/requirements.txt` mentions are preserved in audit/history docs as prior-state evidence
- the temporary verification environment was created outside the repo and removed after validation

## M11 detail
Goal:
- consolidate README ownership to one canonical repo-root `README.md` without changing runtime behavior

Changes:
- updated repo-root `README.md` so it now includes the current project summary, repo layout, canonical install from root `requirements.txt`, current scraper workflow commands, runtime artifact locations, output locations, and test instructions
- reduced `scrapper/README.md` to a minimal pointer to the repo-root `README.md`
- updated `PLAN.md` to mark M11 completed

Validation:
- inspected both README files and merged the still-useful scraper setup and workflow content into root `README.md`
- `rg` confirmed there is no active conflicting setup guidance between the root README and the reduced `scrapper/README.md`
- `python -m pytest -q` from `scrapper/` remained at the expected baseline: `75 passed, 2 failed`
- unchanged failing tests: `test_enrichment_framework_supports_pdf_candidates`, `test_enrichment_framework_supports_html_candidates`

Notes:
- `scrapper/README.md` was reduced to a pointer instead of being removed so existing historical or cross-doc references do not break
- no runtime code, dependency files, or project structure changed
- scraper smoke validation was intentionally skipped because this was a docs-only milestone

## M12 detail
Goal:
- remove stale old-file and old-path references from active guidance only without changing runtime behavior

Changes:
- inspected the active guidance set for stale references to pre-M4, M5, M6, and M10 file paths
- confirmed that the remaining old-file references are confined to historical milestone logs, audits, specs, and archive material
- reduced `scrapper/README.md` further so it acts only as a concise pointer to the canonical repo-root `README.md`
- updated `PLAN.md` to mark M12 completed with an active-guidance-only normalization result

Validation:
- `rg` across active guidance confirmed no stale old-file references remain in current guidance, aside from clearly historical mentions in control-doc history sections
- `python -m pytest -q` from `scrapper/` remained at the expected baseline: `75 passed, 2 failed`
- unchanged failing tests: `test_enrichment_framework_supports_pdf_candidates`, `test_enrichment_framework_supports_html_candidates`

Notes:
- no runtime code, dependency files, or project structure changed
- current guidance redundancy was reduced only where it was safe to do so, without rewriting historical material
- scraper smoke validation was intentionally skipped because this was a docs-only milestone

## M13 detail
Goal:
- normalize historical old-file and old-path references in audits, specs, logs, and archive material while preserving provenance

Changes:
- added short historical-context notes to the affected audit, spec, and archived legacy files so pre-move paths are now explicitly labeled as prior-state references
- clarified in this engineering log that old file paths in completed milestone sections and command logs are intentional historical references rather than current guidance
- updated `PLAN.md` to mark M13 completed with provenance-preserving historical normalization

Validation:
- `rg` across `docs/audits/`, `docs/specs/`, `archive/legacy/`, and `DOCUMENTATION.md` confirmed the known old paths now remain either explicitly labeled as historical or already sit inside clearly historical records
- `python -m pytest -q` from `scrapper/` remained at the expected baseline: `75 passed, 2 failed`
- unchanged failing tests: `test_enrichment_framework_supports_pdf_candidates`, `test_enrichment_framework_supports_html_candidates`

Notes:
- no runtime code, dependency files, or project structure changed
- provenance was preserved by adding clarification notes instead of rewriting the underlying historical outcomes
- scraper smoke validation was intentionally skipped because this was a docs-only milestone

## M14 detail
Goal:
- reduce proven runtime-code redundancy and improve concision without changing behavior

Changes:
- switched the confirmed support-asset path consumers from `utils.py` compatibility re-exports to direct imports from `scrapper/electronet_single_import/repo_paths.py`
- removed the dead `RULES_PATH` constant from `scrapper/electronet_single_import/utils.py`
- removed the one-callsite `build_model_output_dir()` wrapper and inlined its exact current behavior in `scrapper/electronet_single_import/cli.py`
- simplified `scrapper/electronet_single_import/utils.py` so it now keeps only actual utility helpers rather than mixed utility and path-ownership responsibilities
- made a small concision cleanup in `scrapper/electronet_single_import/deterministic_fields.py` by collapsing duplicate typing imports while touching the file for the path-import change

Validation:
- confirmed before editing that `RULES_PATH` had no callsites, `build_model_output_dir()` had exactly one caller in `scrapper/electronet_single_import/cli.py`, and the path-constant compatibility seam was limited to the edited runtime modules
- `python -m compileall scrapper/electronet_single_import` succeeded
- `python -m pytest -q electronet_single_import/tests/test_utils_support_paths.py` from `scrapper/` passed
- `python -m pytest -q electronet_single_import/tests/test_workflow.py electronet_single_import/tests/test_csv_writer.py electronet_single_import/tests/test_validator.py electronet_single_import/tests/test_taxonomy.py electronet_single_import/tests/test_schema_matcher.py` from `scrapper/` passed
- `python -m pytest -q electronet_single_import/tests/test_characteristics_pipeline.py electronet_single_import/tests/test_deterministic_fields.py electronet_single_import/tests/test_deterministic_fields_ice_cream_maker.py electronet_single_import/tests/test_manufacturer_enrichment_tefal.py` from `scrapper/` passed
- full `python -m pytest -q` from `scrapper/` remained at the expected baseline: `75 passed, 2 failed`
- unchanged failing tests: `test_enrichment_framework_supports_pdf_candidates`, `test_enrichment_framework_supports_html_candidates`

Notes:
- runtime behavior remained unchanged because this pass only reduced a dead constant, a one-callsite wrapper, and the `utils.py` path-compatibility seam
- no tests needed edits because the path values and behavior under test stayed the same
- higher-risk cleanup remains deferred, including `workflow.py` output-root refactors, hardcoded absolute repo paths in some tests, and broader utility API reshaping

## Commands run
- `rg -n "M15|Current milestone|Phase 2 milestones|M14 detail|Next active milestone" PLAN.md DOCUMENTATION.md`
- `Get-Content AGENTS.md`
- `Get-Content RULES.md`
- `Get-Content IMPLEMENT.md`
- `git status --short`
- `Get-Content PLAN.md | Select-Object -First 90`
- `Get-Content PLAN.md | Select-Object -Skip 180`
- `Get-Content DOCUMENTATION.md | Select-Object -First 60`
- `Get-Content DOCUMENTATION.md | Select-Object -Skip 350`
- `python -m compileall scrapper/electronet_single_import`
- `python -m pytest -q` from `scrapper/`
- pre-creation filesystem check for `docs/audits/`, `docs/runbooks/`, `docs/checkpoints/`, `docs/specs/`, `archive/legacy/`, `resources/mappings/`, `resources/prompts/`, `resources/schemas/`, and `resources/templates/`
- directory creation for the same approved target paths only when absent
- post-creation filesystem check for approved target paths, `.gitkeep` presence, and empty-directory state
- `python -m pytest -q` from `scrapper/`
- `git status --short`
- `Get-ChildItem -Force -File` at repo root
- `Get-ChildItem docs/audits`
- `Get-ChildItem docs/superpowers/specs,work`
- `rg` sweep for each explicitly named file or candidate to capture runtime code references, docs or planning references, or absence of references
- `Get-Content scrapper/electronet_single_import/utils.py`
- `Get-Content RULES.md`
- `Get-Content AGENTS.md`
- `Get-Content README.md`
- `Get-Content scrapper/README.md`
- pre-edit `rg` over `scrapper/electronet_single_import/` for approved support-asset filenames
- `Get-Content scrapper/electronet_single_import/tests/test_utils_support_paths.py`
- `Get-Content scrapper/electronet_single_import/repo_paths.py`
- post-edit `rg` over `scrapper/electronet_single_import/*.py` for approved support-asset filenames
- `python -m pytest -q electronet_single_import/tests/test_utils_support_paths.py` from `scrapper/`
- source/destination existence checks for the two approved M4 moves
- `Move-Item` for `docs/superpowers/specs/2026-03-22-pipeline-optimization-design.md` to `docs/specs/2026-03-22-pipeline-optimization-design.md`
- `Move-Item` for `work/IMPLEMENTATION_CHECKPOINT.md` to `docs/checkpoints/IMPLEMENTATION_CHECKPOINT.md`
- `rg` for old and new M4 paths before and after the move
- source/destination existence checks for `RULES_legacy.md` and `master_prompt_legacy.txt`
- `Move-Item` for `RULES_legacy.md` to `archive/legacy/RULES_legacy.md`
- `Move-Item` for `master_prompt_legacy.txt` to `archive/legacy/master_prompt_legacy.txt`
- `Remove-Item` for `archive/legacy/.gitkeep` after the archive directory became non-empty
- `rg` for old and new M5 legacy paths before and after the move
- pre-move source and destination existence checks for every approved M6 support asset
- `rg` for old and new M6 support-asset paths before and after the move
- `Move-Item` for the approved M6 support assets into `resources/mappings/`, `resources/schemas/`, `resources/templates/`, and `resources/prompts/`
- `Remove-Item` for `.gitkeep` in `resources/mappings/`, `resources/schemas/`, `resources/templates/`, and `resources/prompts/` after those directories became non-empty
- `Remove-Item` for the old `schemas/` directory after it became empty
- `Get-Content README.md`
- existence check for `docs/runbooks/repo-layout.md`
- `rg` over repo docs for pre-M6 support-asset paths and post-M4 moved doc paths
- `Get-Content requirements.txt`
- `Get-Content scrapper/requirements.txt`
- `rg` over repo docs for dependency-file references and install/setup commands
- live import scans for packages declared in either dependency file
- root directory inventory
- recursive search for remaining `.gitkeep` files
- targeted `rg` for pre-M4, M5, and M6 paths and known deferred runtime/path issues
- dependency overlap comparison between root and scraper requirement files
- clean temporary virtual environment creation outside the repo
- dependency install from canonical repo-root `requirements.txt`
- clean-environment import validation for `httpx`, `playwright`, `bs4`, `pypdf`, `PIL`, and `pillow_avif`
- full `python -m pytest -q` from `scrapper/` under the clean environment
- `rg` for `scrapper/requirements.txt` after consolidation
- temporary verification-environment removal
- README inspection for root and scraper README ownership
- `rg` for `scrapper/README.md` references after README consolidation
- targeted `rg` for stale old-file references across current guidance docs
- targeted `rg` for stale old-file references across `docs/audits/`, `docs/specs/`, `archive/legacy/`, and `DOCUMENTATION.md`
- `Get-ChildItem -Recurse -File scrapper/electronet_single_import`
- `rg` over `scrapper/electronet_single_import/` for `REPO_ROOT`, path constants, `build_model_output_dir`, `RULES_PATH`, and utility callsites
- `Get-Content` inspection for `scrapper/electronet_single_import/utils.py`, `repo_paths.py`, `cli.py`, `workflow.py`, `csv_writer.py`, `validator.py`, `taxonomy.py`, `schema_matcher.py`, `manufacturer_enrichment.py`, `characteristics_pipeline.py`, and `deterministic_fields.py`
- `python -m compileall scrapper/electronet_single_import`
- `python -m pytest -q electronet_single_import/tests/test_utils_support_paths.py` from `scrapper/`
- `python -m pytest -q electronet_single_import/tests/test_workflow.py electronet_single_import/tests/test_csv_writer.py electronet_single_import/tests/test_validator.py electronet_single_import/tests/test_taxonomy.py electronet_single_import/tests/test_schema_matcher.py` from `scrapper/`
- `python -m pytest -q electronet_single_import/tests/test_characteristics_pipeline.py electronet_single_import/tests/test_deterministic_fields.py electronet_single_import/tests/test_deterministic_fields_ice_cream_maker.py electronet_single_import/tests/test_manufacturer_enrichment_tefal.py` from `scrapper/`

## Open risks
- direct path assumptions may exist in multiple scraper modules
- docs may drift during file moves if not updated in the same commit
- baseline pytest failures remain in `electronet_single_import/tests/test_manufacturer_enrichment.py`
- `schema_index.csv` and `taxonomy_mapping_template.csv` have weaker direct runtime evidence than the hardcoded support assets
- `workflow.py` still contains out-of-scope `REPO_ROOT` output-root assumptions for `work/` and `products/`
- some tests still use hardcoded absolute repo paths and were intentionally deferred
- historical docs and archived legacy files intentionally retain some old support-asset basenames as prior-state evidence
- redundant `.gitkeep` files remain in non-empty `docs/audits/`, `docs/checkpoints/`, `docs/runbooks/`, and `docs/specs/` directories
- broader runtime utility/API reshaping beyond the current path-ownership seam remains intentionally deferred to avoid behavior risk

## Next approved action
No cleanup follow-up is scheduled by default. If approved, open a narrowly scoped follow-up for deferred path assumptions, test path cleanup, or redundant `.gitkeep` removal.

## 2026-03-28 - Skroutz mixed-section pipeline fix and live run for model 123456

## What changed
- fixed Skroutz section selection in `scrapper/electronet_single_import/cli.py` so prepare selects the first requested image-backed rich-description sections instead of blindly slicing the first parsed sections when text-only `one-column` blocks appear mid-stream
- added a regression test in `scrapper/electronet_single_import/tests/test_skroutz_sections.py` covering the mixed image/text section ordering case
- ran the live Product-Agent pipeline for model `123456` against the provided Skroutz product URL and authored `work/123456/llm_output.json` using the reduced LLM contract

## Files and directories affected
- `scrapper/electronet_single_import/cli.py`
- `scrapper/electronet_single_import/tests/test_skroutz_sections.py`
- `work/123456/`
- `products/123456.csv`

## Commands run
- `Get-ChildItem -Force`
- `git status --short`
- `rg --files AGENTS.md PLAN.md IMPLEMENT.md DOCUMENTATION.md`
- `python -m electronet_single_import.workflow prepare --model 123456 --url "https://www.skroutz.gr/s/60276903/tcl-smart-tileorasi-115-4k-uhd-mini-led-c7k-hdr-2025-115c7k.html" --photos 7 --sections 7 --skroutz-status 1 --boxnow 0 --price 9999` from `scrapper/`
- `rg -n "Skroutz section image could not be resolved|section image could not be resolved|section_image|section image" scrapper`
- `Get-Content` inspection for `scrapper/electronet_single_import/cli.py`, `fetcher.py`, `skroutz_sections.py`, `workflow.py`, `html_builders.py`, `work/123456/llm_context.json`, `work/123456/prompt.txt`, `work/123456/scrape/123456.source.json`, `work/123456/scrape/123456.report.json`, `resources/prompts/master_prompt+.txt`, `resources/schemas/compact_response.schema.json`, `resources/mappings/filter_map.json`, and `products/123456.csv`
- `python -m pytest scrapper/electronet_single_import/tests/test_skroutz_sections.py -q`
- `python -m pytest scrapper/electronet_single_import/tests/test_skroutz_integration.py -q`
- `python -m electronet_single_import.workflow render --model 123456` from `scrapper/`

## Validation results
- initial live `prepare` failed with `Skroutz section image could not be resolved for section 6`
- focused tests passed after the fix:
  - `scrapper/electronet_single_import/tests/test_skroutz_sections.py`: 5 passed
  - `scrapper/electronet_single_import/tests/test_skroutz_integration.py`: 7 passed
- first live `render` failed validation with `llm_intro_word_count_invalid`
- adjusted `work/123456/llm_output.json` intro length to satisfy the reduced contract
- final live `render` passed with `Validation ok: True`
- final validation warnings remained:
  - `characteristics_template_used:schema:sha1:954c8413f2da941e78f3ddce65df522654336c8c`
  - `characteristics_template_unresolved_fields:12`

## Risks, blockers, or skipped items
- the live product still relies on the characteristics template for some unresolved spec fields; this is reported but not a blocking validation failure
- no durable process-rule update was required in `IMPLEMENT.md`
- no milestone-plan change was required in `PLAN.md`

## 2026-03-28 - Portable test fixture path centralization

## What changed
- created `scrapper/electronet_single_import/tests/conftest.py` as the canonical test-layer path source of truth
- added shared pytest fixtures for `tests_root`, `fixtures_root`, `skroutz_fixtures_root`, and `products_root`
- removed machine-specific absolute path assumptions from the affected Skroutz tests and switched them to the shared fixtures
- kept the change test-only; no runtime module outside `scrapper/electronet_single_import/tests/` was edited

## Files edited
- `scrapper/electronet_single_import/tests/conftest.py`
- `scrapper/electronet_single_import/tests/test_skroutz_integration.py`
- `scrapper/electronet_single_import/tests/test_skroutz_sections.py`
- `scrapper/electronet_single_import/tests/test_skroutz_taxonomy.py`
- `DOCUMENTATION.md`

## Normalized path assumptions
- `test_skroutz_integration.py`
  - replaced hard-coded absolute `REPO_ROOT`
  - replaced per-file `FIXTURES_ROOT` and `PRODUCTS_ROOT`
  - switched fetcher and baseline-copy helpers to accept shared fixture paths
- `test_skroutz_sections.py`
  - replaced hard-coded absolute `REPO_ROOT`
  - replaced per-file `FIXTURES_ROOT` and `PRODUCTS_ROOT`
  - switched fixture fetcher helper and baseline CSV reads to shared fixture paths
- `test_skroutz_taxonomy.py`
  - replaced hard-coded absolute `REPO_ROOT`
  - replaced derived `REGRESSION_FIXTURE` and `TAXONOMY_CASES_ROOT`
  - switched taxonomy fixture reads to shared fixture paths

## Commands run
- `rg --files scrapper/electronet_single_import/tests`
- `Get-Content scrapper/conftest.py`
- `Get-Content scrapper/electronet_single_import/tests/test_skroutz_integration.py`
- `Get-Content scrapper/electronet_single_import/tests/test_skroutz_sections.py`
- `Get-Content scrapper/electronet_single_import/tests/test_skroutz_taxonomy.py`
- `rg -n "Users\\\\|VS_Projects|Product-Agent|__file__|parents\\[|parent.parent|fixtures|FIXTURES_ROOT|PRODUCTS_ROOT|REPO_ROOT" scrapper/electronet_single_import/tests`
- `python -m pytest -q electronet_single_import/tests/test_skroutz_integration.py` from `scrapper/`
- `python -m pytest -q electronet_single_import/tests/test_skroutz_sections.py` from `scrapper/`
- `python -m pytest -q electronet_single_import/tests/test_skroutz_taxonomy.py` from `scrapper/`
- `python -m pytest -q` from `scrapper/`
- `python -m compileall scrapper/electronet_single_import`
- `git status --short`

## Validation results
- targeted tests after the path fix:
  - `electronet_single_import/tests/test_skroutz_integration.py`: `7 passed`
  - `electronet_single_import/tests/test_skroutz_sections.py`: `5 passed`
  - `electronet_single_import/tests/test_skroutz_taxonomy.py`: `5 passed`
- full suite after the path fix:
  - `76 passed, 2 failed`
  - remaining failures:
    - `test_enrichment_framework_supports_pdf_candidates`
    - `test_enrichment_framework_supports_html_candidates`
- `python -m compileall scrapper/electronet_single_import` succeeded
- `git status --short` showed only the expected test-layer edits and `DOCUMENTATION.md`

## Risks, blockers, or skipped items
- no runtime behavior risk is expected because the change is confined to test path resolution
- no `PLAN.md` update was needed because this is a test-baseline stabilization task rather than a milestone-order change

## 2026-03-30 - Phase 2 test fixture hierarchy migration

## What changed
- migrated the committed Skroutz test fixtures from the legacy flat `scraper/pipeline/tests/fixtures/skroutz/` layout into the explicit provider hierarchy under `scraper/pipeline/tests/fixtures/providers/skroutz/`
- added the new shared pytest fixture roots in `scraper/pipeline/tests/conftest.py` and kept `skroutz_fixtures_root` as a backward-compatible alias to the new Skroutz provider fixture root
- updated the touched Skroutz tests to read fixture HTML, rendered-sections JSON, and taxonomy-case assets from the new hierarchy
- created empty committed placeholder directories for the requested explicit fixture tree with `.gitkeep` files where no tracked fixture content exists yet
- made one minimal stale-guidance fix in `AGENTS.md` and one additive fixture-location rule in `IMPLEMENT.md`
- left `work/` and `scraper/work/` untouched because `git ls-files work scraper/work` returned no tracked files in this checkout

## Files and directories affected
- edited:
  - `scraper/pipeline/tests/conftest.py`
  - `scraper/pipeline/tests/test_provider_selection.py`
  - `scraper/pipeline/tests/test_skroutz_integration.py`
  - `scraper/pipeline/tests/test_skroutz_sections.py`
  - `scraper/pipeline/tests/test_skroutz_taxonomy.py`
  - `AGENTS.md`
  - `IMPLEMENT.md`
  - `DOCUMENTATION.md`
- moved:
  - `scraper/pipeline/tests/fixtures/skroutz/*.html` -> `scraper/pipeline/tests/fixtures/providers/skroutz/html/`
  - `scraper/pipeline/tests/fixtures/skroutz/143481.rendered_sections.json` -> `scraper/pipeline/tests/fixtures/providers/skroutz/rendered_sections/`
  - `scraper/pipeline/tests/fixtures/skroutz/skroutz_taxonomy_regression.csv` -> `scraper/pipeline/tests/fixtures/providers/skroutz/taxonomy_cases/`
  - `scraper/pipeline/tests/fixtures/skroutz/taxonomy_cases/*` -> `scraper/pipeline/tests/fixtures/providers/skroutz/taxonomy_cases/`
- added placeholder directories:
  - `scraper/pipeline/tests/fixtures/providers/skroutz/json/`
  - `scraper/pipeline/tests/fixtures/providers/electronet/html/`
  - `scraper/pipeline/tests/fixtures/providers/electronet/json/`
  - `scraper/pipeline/tests/fixtures/providers/manufacturer_tefal/344709/`
  - `scraper/pipeline/tests/fixtures/pipeline_runs/`
  - `scraper/pipeline/tests/fixtures/golden_outputs/`

## Commands run
- `git ls-files work scraper/work`
- `New-Item -ItemType Directory -Force ...` for the new fixture hierarchy roots
- `git mv` for the explicit Skroutz fixture moves into `providers/skroutz/...`
- `Remove-Item scraper/pipeline/tests/fixtures/skroutz` after the legacy directory became empty
- `Get-Content` inspection for `AGENTS.md`, `IMPLEMENT.md`, `DOCUMENTATION.md`, and the touched test files
- `git status --short`
- `rg -n "def .*fixtures_root|skroutz_fixtures_root|fixtures/skroutz|work/|scraper/work/|active regression samples" scraper/pipeline/tests AGENTS.md IMPLEMENT.md .gitignore`
- `python -m pytest -q pipeline/tests/test_provider_selection.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_skroutz_integration.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_skroutz_sections.py` from `scraper/`
- `python -m pytest -q pipeline/tests/test_skroutz_taxonomy.py` from `scraper/`
- `where.exe python`
- `py -0p`
- `py -3.12 -m pytest --version`
- `py -3.12 -m pytest -q pipeline/tests/test_provider_selection.py` from `scraper/`
- `py -3.12 -m pytest -q pipeline/tests/test_skroutz_integration.py` from `scraper/`
- `py -3.12 -m pytest -q pipeline/tests/test_skroutz_sections.py` from `scraper/`
- `py -3.12 -m pytest -q pipeline/tests/test_skroutz_taxonomy.py` from `scraper/`
- `py -3.12 -m pytest -q` from `scraper/`

## Validation results
- initial validation command path using `python -m pytest` could not run because the active `python` interpreter did not have `pytest` installed
- focused touched-test results using `py -3.12 -m pytest`:
  - `pipeline/tests/test_provider_selection.py`: `4 passed`
  - `pipeline/tests/test_skroutz_sections.py`: `5 passed`
  - `pipeline/tests/test_skroutz_taxonomy.py`: `5 passed`
  - `pipeline/tests/test_skroutz_integration.py`: `6 passed, 1 failed`
- the touched integration failure was `test_prepare_and_render_workflow_with_skroutz_fixtures`, failing on `render_result["published_csv_path"] is None` after fixture loading had already succeeded from the new hierarchy
- full suite result: `90 passed, 4 failed`
- unchanged baseline failures from the earlier documented suite baseline:
  - `pipeline/tests/test_manufacturer_enrichment.py::test_enrichment_framework_supports_pdf_candidates`
  - `pipeline/tests/test_manufacturer_enrichment.py::test_enrichment_framework_supports_html_candidates`
- additional currently failing workflow publication tests:
  - `pipeline/tests/test_skroutz_integration.py::test_prepare_and_render_workflow_with_skroutz_fixtures`
  - `pipeline/tests/test_workflow.py::test_render_workflow_writes_candidate_bundle`
- no new fixture-path lookup failures were observed in the focused path-migration assertions

## Risks, blockers, or skipped items
- `scraper/work/344709/debug_manufacturer/` was absent in this checkout, so no manufacturer repro assets were promoted in this phase
- `work/229957_skroutz_debug.html` exists only as an ignored local file and was intentionally left untracked
- no `.gitignore` change was needed or made
- the remaining test failures are outside this migration's edit scope; the fixture path migration stopped at test-layer changes and the minimal allowed control-file updates

## 2026-03-31 - Warning-only OpenCart image upload after render publish

Goal:
- update the active control-docs in the requested order before code changes
- wire the single repo-native OpenCart image upload shell entrypoint after successful `products/{model}.csv` publish
- keep upload warning-only so successful render/publish outputs remain valid

Files changed:
- `PLAN.md`
- `IMPLEMENT.md`
- `AGENTS.md`
- `RULES.md`
- `README.md`
- `scraper/pipeline/services/render_execution.py`
- `scraper/pipeline/services/render_service.py`
- `scraper/pipeline/workflow.py`
- `scraper/pipeline/tests/test_workflow.py`
- `scraper/pipeline/tests/test_services.py`
- `DOCUMENTATION.md`

Commands run:
- `Get-Content` inspection for `PLAN.md`, `IMPLEMENT.md`, `AGENTS.md`, `RULES.md`, `README.md`, `scraper/pipeline/services/render_execution.py`, `scraper/pipeline/services/render_service.py`, `scraper/pipeline/workflow.py`, `scraper/pipeline/tests/test_workflow.py`, and `scraper/pipeline/tests/test_services.py`
- `python -m pytest -q scraper/pipeline/tests/test_workflow.py scraper/pipeline/tests/test_services.py` from repo root
- `python -m pytest -q` from `scraper/`

Implementation notes:
- updated the control-docs first to state that successful render publish now attempts OpenCart image upload through `tools/run_opencart_image_upload.sh`
- kept `tools/run_opencart_image_upload.sh` as the only shell entrypoint and reused `tools/opencart_upload_images.py` unchanged
- wired the upload stage in `scraper/pipeline/services/render_execution.py` immediately after `shutil.copyfile(candidate_csv_path, published_csv_path)`
- passed the exact current-job published CSV path through `CURRENT_JOB_PRODUCT_FILE`
- preserved the uploader default admin path by not overriding `OPENCART_ADMIN_PATH` in the runtime integration
- captured upload status, report path, and warning details in render metadata/service details while keeping upload failures warning-only
- extended workflow CLI output to print publish and upload status lines

Validation:
- targeted touched tests passed: `37 passed`
- full suite passed from `scraper/`: `138 passed`

Risks, blockers, or skipped items:
- the shell upload stage now depends on `bash` being available in the runtime environment; when unavailable or when upload exits non-zero, the render run stays successful and records a warning
- no changes were made to the uploader resolver order, path conventions, or default admin path

## 2026-03-31 - Pipeline run for model 123456 (Skroutz TCL 115C7K)

Goal:
- run the full Product-Agent pipeline for the provided filled template
- generate only the LLM-owned intro and SEO outputs
- render and validate the final candidate bundle and deliverable CSV

Files changed:
- `work/123456/llm/intro_text.output.txt`
- `work/123456/llm/seo_meta.output.json`
- `work/123456/candidate/123456.csv`
- `work/123456/candidate/123456.validation.json`
- `work/123456/candidate/description.html`
- `work/123456/candidate/characteristics.html`
- `products/123456.csv`
- `DOCUMENTATION.md`

Commands run:
- `python -m pipeline.workflow prepare --model 123456 --url "https://www.skroutz.gr/s/60276903/tcl-smart-tileorasi-115-4k-uhd-mini-led-c7k-hdr-2025-115c7k.html" --photos 7 --sections 7 --skroutz-status 1 --boxnow 0 --price 9999` from `scraper/`
- inspected:
  - `work/123456/llm/task_manifest.json`
  - `work/123456/llm/intro_text.context.json`
  - `work/123456/llm/intro_text.prompt.txt`
  - `work/123456/llm/seo_meta.context.json`
  - `work/123456/llm/seo_meta.prompt.txt`
  - `work/123456/scrape/123456.source.json`
  - `work/123456/scrape/123456.report.json`
- wrote:
  - `work/123456/llm/intro_text.output.txt`
  - `work/123456/llm/seo_meta.output.json`
- `python -m pipeline.workflow render --model 123456` from `scraper/`
- inspected:
  - `work/123456/candidate/123456.csv`
  - `work/123456/candidate/123456.validation.json`
  - `work/123456/candidate/description.html`
  - `work/123456/candidate/characteristics.html`
  - `resources/mappings/filter_map.json`

Validation:
- render completed successfully with `Validation ok: True`
- final machine-readable report: `work/123456/candidate/123456.validation.json`
- final deliverable path exists: `products/123456.csv`
- validation warnings only:
  - `characteristics_template_used:schema:sha1:954c8413f2da941e78f3ddce65df522654336c8c`
  - `characteristics_template_unresolved_fields:12`

Notes:
- taxonomy resolved to `ΕΙΚΟΝΑ & ΗΧΟΣ > Τηλεοράσεις > 50'' & άνω`
- category filters for that taxonomy were resolved from `resources/mappings/filter_map.json` as:
  - `Τεχνολογία Οθόνης`
  - `Smart Tv`
  - `Ανάλυση`
  - `Μέγεθος Οθόνης`
- resolved filter values from source/spec evidence:
  - `Τεχνολογία Οθόνης`: `Mini LED`
  - `Smart Tv`: `Google TV`
  - `Ανάλυση`: `ULTRA HD (4K)`
  - `Μέγεθος Οθόνης`: `115"`
## 2026-03-31 - OpenCart post-publish retry and diagnostics for model 123455

Goal:
- retry the post-publish OpenCart image upload for `products/123455.csv`
- diagnose the failure mode from login, cookies, body preview, and filemanager responses
- fix the uploader generically where the failure was caused by runtime/script issues

Files changed:
- `tools/run_opencart_image_upload.sh`
- `tools/opencart_upload_images.py`
- `work/123455/upload.opencart.json`
- `DOCUMENTATION.md`

Commands run:
- `bash tools/run_opencart_image_upload.sh` with `CURRENT_JOB_PRODUCT_FILE=products/123455.csv`
- `rg -n "permission_probe|user_token|body preview|cookie|login failed|filemanager|opencart" -S tools scraper`
- `python tools/opencart_upload_images.py --model 123455 --repo-root ... --store-base https://www.etranoulis.gr --admin-path /ipadmin/index.php --username ... --password ... --report-file work/123455/upload.opencart.json`
- inline Python diagnostics calling `login()` and `permission_probe()` from `tools/opencart_upload_images.py`
- final verification: `bash tools/run_opencart_image_upload.sh` with `CURRENT_JOB_PRODUCT_FILE=products/123455.csv`

Implementation notes:
- fixed Git Bash / MSYS argument conversion in `tools/run_opencart_image_upload.sh` by converting repo/script paths with `cygpath` while excluding the OpenCart admin web path from MSYS rewriting
- extended `tools/opencart_upload_images.py` to recognize localized Greek OpenCart responses for:
  - missing-folder responses used by the modify-permission probe
  - duplicate-folder responses during nested directory creation
- kept the upload flow and filemanager endpoints unchanged; only robustness around runtime path handling and localized admin responses was updated

Validation:
- first retry showed the shell wrapper was building a bad login target after path mangling:
  - POST target became `https://www.etranoulis.gr/C:/Program Files/Git/ipadmin/index.php?route=common/login`
  - HTTP `404`
  - body preview was the storefront not-found page, not the admin login/token flow
- direct PowerShell run confirmed admin login/session were valid once the wrapper issue was bypassed:
  - `user_token` present
  - cookies present: `OCSESSID`
  - permission probe returned Greek JSON error `Ειδοποίηση: Δεν υπάρχει ο φάκελος!`
- final shell retry succeeded end-to-end
- upload report now exists at `work/123455/upload.opencart.json`
- final upload report shows:
  - `login.ok = true`
  - `permission_probe.can_modify = true`
  - gallery upload success
  - besco upload success

Risks, blockers, or skipped items:
- the uploader still depends on recognizable localized admin error strings; if the store theme/module changes those strings, the permission probe or duplicate-folder handling may need another localization update
- no backfill was done for older render metadata that referenced a missing upload report before this fix

## 2026-03-31 - Fix OpenCart CSV import session token handling and complete model 123455 publish

Goal:
- diagnose the remaining OpenCart `csv_import` failure after successful render and image upload
- fix the importer generically if the failure is caused by the repo-native automation
- complete the full runtime pipeline for model `123455`

Files changed:
- `tools/opencart_import_csv_playwright.py`
- `work/123455/llm/intro_text.output.txt`
- `work/123455/llm/seo_meta.output.json`
- `work/123455/candidate/123455.csv`
- `work/123455/candidate/123455.validation.json`
- `work/123455/candidate/description.html`
- `work/123455/candidate/characteristics.html`
- `work/123455/import.opencart.json`
- `work/123455/publish.run.json`
- `products/123455.csv`
- `DOCUMENTATION.md`

Commands run:
- `python -m pipeline.workflow prepare --model 123455 --url "https://www.skroutz.gr/s/60276903/tcl-smart-tileorasi-115-4k-uhd-mini-led-c7k-hdr-2025-115c7k.html" --photos 7 --sections 7 --skroutz-status 1 --boxnow 0 --price 9999` from `scraper/`
- inspected:
  - `work/123455/llm/task_manifest.json`
  - `work/123455/llm/intro_text.context.json`
  - `work/123455/llm/intro_text.prompt.txt`
  - `work/123455/llm/seo_meta.context.json`
  - `work/123455/llm/seo_meta.prompt.txt`
  - `work/123455/scrape/123455.source.json`
  - `work/123455/scrape/123455.report.json`
  - `work/123455/candidate/123455.validation.json`
  - `work/123455/render.run.json`
  - `work/123455/publish.run.json`
  - `work/123455/import.opencart.json`
  - `resources/mappings/filter_map.json`
- `python -m pipeline.workflow render --model 123455` from `scraper/`
- debug probe against the admin import page using Playwright after sourcing `.secrets/opencart.env`
- `bash -lc 'DRY_RUN=1 bash tools/run_opencart_import_csv.sh 123455'`
- `bash -lc 'bash tools/run_opencart_import_csv.sh 123455'`
- inline Python call to `execute_publish_workflow('123455', current_job_product_file=Path(...products/123455.csv))`

Implementation notes:
- the first render attempt failed only because `intro_text.output.txt` was under the required 120-word minimum; expanding the paragraph to 129 words resolved validation
- the remaining publish failure was caused by `tools/opencart_import_csv_playwright.py` opening the CSV import route without carrying the authenticated OpenCart `user_token`
- confirmed the failure mode by probing the post-login import page:
  - requested route stayed on the import URL
  - `select[name="profile_id"]` was absent
  - the page body showed the invalid-session-token login prompt
- fixed the importer generically by preserving the current admin `user_token` and appending it to the CSV import route before navigation
- kept the existing Step 1/2/3 import flow unchanged; only the authenticated route construction was corrected

Validation:
- final candidate validation succeeded: `work/123455/candidate/123455.validation.json` reports `ok: true`
- final deliverable exists: `products/123455.csv`
- importer dry run succeeded and reached Step 2 with:
  - `profile_name = product_new`
  - `selected_model_mapping = model`
  - `mapping_ok = true`
- final OpenCart import succeeded: `work/123455/import.opencart.json` reports `ok: true`
- final publish metadata succeeded: `work/123455/publish.run.json` reports:
  - `status = completed`
  - `publish_status = success`
  - `publish_stage = csv_import`
- remaining validation warnings are source/template warnings only:
  - `characteristics_template_used:schema:sha1:954c8413f2da941e78f3ddce65df522654336c8c`
  - `characteristics_template_unresolved_fields:12`

Risks, blockers, or skipped items:
- the importer currently assumes the admin session token remains exposed as `user_token` in the post-login URL; if the OpenCart admin auth flow changes again, the route-token helper may need to be expanded
- no dedicated automated test coverage was added for the Playwright importer in this pass because the immediate validation path was the live OpenCart dry-run plus live import

## 2026-03-31 - Separate render and publish phases for OpenCart automation

Goal:
- split OpenCart automation into a true post-render publish phase
- keep render success tied only to render artifacts and validation
- run image upload before CSV import through one repo-native wrapper

Files changed:
- `AGENTS.md`
- `DOCUMENTATION.md`
- `IMPLEMENT.md`
- `README.md`
- `RULES.md`
- `scraper/pipeline/services/__init__.py`
- `scraper/pipeline/services/metadata.py`
- `scraper/pipeline/services/models.py`
- `scraper/pipeline/services/publish_execution.py`
- `scraper/pipeline/services/publish_service.py`
- `scraper/pipeline/services/render_execution.py`
- `scraper/pipeline/services/render_service.py`
- `scraper/pipeline/services/run_execution.py`
- `scraper/pipeline/tests/test_services.py`
- `scraper/pipeline/tests/test_workflow.py`
- `scraper/pipeline/workflow.py`
- `tools/run_opencart_image_upload.sh`
- `tools/run_opencart_pipeline.sh`

Commands run:
- `python -m pytest -q pipeline/tests/test_services.py pipeline/tests/test_workflow.py` from `scraper/`
- `bash -n tools/run_opencart_pipeline.sh`
- `bash -n tools/run_opencart_image_upload.sh`
- `bash -n tools/run_opencart_import_csv.sh`
- `rg -n "scripts/run_opencart|scripts/.*opencart|run_opencart_image_upload\.sh|run_opencart_import_csv\.sh|run_opencart_pipeline\.sh" README.md AGENTS.md RULES.md IMPLEMENT.md tools scraper -S`
- `Test-Path tools/run_opencart_pipeline.sh`
- `Test-Path tools/run_opencart_image_upload.sh`
- `Test-Path tools/run_opencart_import_csv.sh`
- `Test-Path tools/opencart_upload_images.py`
- `Test-Path tools/opencart_import_csv_playwright.py`
- `Test-Path .secrets/opencart.env`

Implementation notes:
- removed the inline OpenCart upload call from render execution so `render_execution.py` and `render_service.py` are render-only
- added `RunType.PUBLISH`, `PublishRequest`, `publish_execution.py`, and `publish_service.py` for a separate publish phase with `publish.run.json`
- moved render -> publish sequencing up to `workflow.py` for the render CLI path and `run_execution.py` for the full-run path
- added `tools/run_opencart_pipeline.sh` to perform preflight checks, image upload, then CSV import with stage-specific exit codes:
  - `11` preflight
  - `12` image_upload
  - `13` csv_import
- updated operator-facing docs to point to `tools/run_opencart_pipeline.sh` and the new publish-phase reports

Validation:
- targeted tests passed: `37 passed`
- shell syntax checks passed for `tools/run_opencart_pipeline.sh`, `tools/run_opencart_image_upload.sh`, and `tools/run_opencart_import_csv.sh`
- all referenced OpenCart tool files and `.secrets/opencart.env` exist
- no incorrect `scripts/` references remain for these OpenCart entrypoints

Risks, blockers, or skipped items:
- `publish_status=warning` is currently used when the publish wrapper exits `0` but one or both expected report files are missing
- `scraper/pipeline/tests/test_workflow.py` still contains a small amount of unreachable legacy test code below early returns from targeted patching; the behavior is validated, but that cleanup was not expanded beyond the minimal integration scope

## 2026-03-31 - Restore OpenCart image upload login hardening

Goal:
- diagnose the `image_upload` regression for model `123456`
- restore the earlier working OpenCart admin login flow inside the repo-native uploader path

Files changed:
- `DOCUMENTATION.md`
- `tools/opencart_upload_images.py`
- `tools/run_opencart_image_upload.sh`
- `tools/run_opencart_import_csv.sh`

Commands run:
- `git status --short`
- `rg -n "opencart|image_upload|user_token|admin_path|STORE_BASE|OPENCART" tools scraper -S`
- `git log --oneline -- tools/run_opencart_image_upload.sh tools/opencart_upload_images.py tools/run_opencart_pipeline.sh`
- `git show 295201e:tools/opencart_upload_images.py`
- `bash -lc 'source .secrets/opencart.env && python tools/opencart_upload_images.py --model 123456 --repo-root "$(pwd)" --store-base "$OPENCART_STORE_BASE" --admin-path "$OPENCART_ADMIN_PATH" --username "$OPENCART_ADMIN_USER" --password "$OPENCART_ADMIN_PASS" --dry-run'`
- direct PowerShell/Python HTTP probe against `https://www.etranoulis.gr/ipadmin/index.php?route=common/login`
- `bash -lc 'source .secrets/opencart.env && DRY_RUN=1 bash tools/run_opencart_image_upload.sh 123456'`
- `bash -lc 'source .secrets/opencart.env && bash tools/run_opencart_image_upload.sh 123456'`
- `bash -lc 'source .secrets/opencart.env && CURRENT_JOB_PRODUCT_FILE="$(pwd)/products/123456.csv" bash tools/run_opencart_pipeline.sh 123456'`

Implementation notes:
- confirmed the current uploader had regressed from the earlier hardened login logic in commit `295201e`
- restored the warm-session + browser-like header + redirect-follow fallback login flow in `tools/opencart_upload_images.py`
- restored localized helper checks for permission-denied, missing-directory, and already-exists responses
- added `MSYS2_ARG_CONV_EXCL` protection to `tools/run_opencart_image_upload.sh` so Git Bash does not rewrite `/ipadmin/index.php` into a Windows path
- applied the same shell-side admin path protection to `tools/run_opencart_import_csv.sh` after the full pipeline exposed the same wrapper issue in `csv_import`

Validation:
- direct HTTP probe showed the admin endpoint is healthy when called correctly:
  - warm login page `200`
  - login POST `302`
  - redirect contains `user_token`
- standalone wrapper dry run now succeeds and writes `work/123456/upload.opencart.json`
- standalone live image upload now succeeds for model `123456`
- full `tools/run_opencart_pipeline.sh 123456` run now passes `image_upload` and reaches `csv_import`
- upload report confirms:
  - `login.ok = true`
  - `permission_probe.can_modify = true`
  - gallery upload success
  - besco upload success

Risks, blockers, or skipped items:
- `csv_import` is still failing after login for a separate reason: the Playwright importer times out waiting for `select[name="profile_id"]`
- no deeper importer UI fix was included in this image-upload diagnostic pass

## 2026-03-31 - Add Skroutz air-conditioner taxonomy support and run model 000001

Goal:
- run the full template-triggered pipeline for model `000001` from a Skroutz air-conditioner URL
- resolve `Unsupported Skroutz page type` caused by missing air-conditioner taxonomy handling

Files changed:
- `DOCUMENTATION.md`
- `scraper/pipeline/parser_product_skroutz.py`
- `scraper/pipeline/skroutz_taxonomy.py`
- `work/000001/llm/intro_text.output.txt`
- `work/000001/llm/seo_meta.output.json`

Commands run:
- `..\.venv\Scripts\python.exe -m pipeline.workflow prepare --help` from `scraper/`
- `..\.venv\Scripts\python.exe -m pipeline.workflow prepare --model 000001 --url "https://www.skroutz.gr/s/54974577/Inventor-Emperor-Klimatistiko-Inverter-24000-BTU-A-A-me-Ionisti-kai-WiFi.html" --photos 7 --sections 5 --skroutz-status 1 --boxnow 0 --price 1050` from `scraper/`
- `..\.venv\Scripts\python.exe -m pipeline.workflow render --model 000001` from `scraper/`
- `$env:CURRENT_JOB_PRODUCT_FILE = "products/000001.csv"; bash tools/run_opencart_pipeline.sh` from repo root

Implementation notes:
- added `air_conditioner` family detection in Skroutz parser family rules
- added air-conditioner helper taxonomy classification in `skroutz_taxonomy.py`:
  - parent: `ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ`
  - leaf: `Κλιματιστικά`
  - sub-category heuristic: `Τοίχου` / `Φορητά` / `Ντουλάπες`
- kept deterministic field ownership unchanged and authored only LLM-owned outputs:
  - `intro_text`
  - `product.meta_description`
  - `product.meta_keywords`

Validation:
- initial prepare failure reproduced: `Unsupported Skroutz page type: unsupported_skroutz_page_type`
- after taxonomy patch, prepare succeeded and produced scrape + llm task artifacts under `work/000001/`
- render succeeded:
  - `products/000001.csv` created
  - `work/000001/candidate/000001.validation.json` reports `"ok": true`
- publish phase failed before upload/import stage due local Bash/WSL startup error:
  - `Bash/Service/CreateInstance/0xd0000022`
  - status captured in `work/000001/publish.run.json`

Risks, blockers, or skipped items:
- OpenCart publish could not proceed in this environment because Bash/WSL failed to start, so `upload.opencart.json` and `import.opencart.json` were not produced for this run
- characteristics mapping still reports unresolved template fields (`characteristics_template_unresolved_fields:13`) inherited from current schema matching

## 2026-03-31 - Pipeline run for model 000002 (Skroutz television)

Goal:
- execute the full template-triggered pipeline for model `000002`

Files changed:
- `DOCUMENTATION.md`
- `work/000002/llm/intro_text.output.txt`
- `work/000002/llm/seo_meta.output.json`
- generated runtime artifacts under `work/000002/` and `products/000002.csv`

Commands run:
- `..\.venv\Scripts\python.exe -m pipeline.workflow prepare --model 000002 --url "https://www.skroutz.gr/s/60276903/tcl-smart-tileorasi-115-4k-uhd-mini-led-c7k-hdr-2025-115c7k.html" --photos 7 --sections 7 --skroutz-status 1 --boxnow 0 --price 9999` from `scraper/`
- `..\.venv\Scripts\python.exe -m pipeline.workflow render --model 000002` from `scraper/`
- `$env:CURRENT_JOB_PRODUCT_FILE = "products/000002.csv"; bash tools/run_opencart_pipeline.sh` from repo root

Implementation notes:
- `boxnow` was provided blank in the template; runtime CLI requires integer, so execution used `--boxnow 0`
- authored only LLM-owned fields:
  - `intro_text`
  - `product.meta_description`
  - `product.meta_keywords`

Validation:
- `prepare` succeeded and produced scrape/llm artifacts for `000002`
- `render` succeeded and published `products/000002.csv`
- `work/000002/candidate/000002.validation.json` reports `"ok": true`

Risks, blockers, or skipped items:
- post-render OpenCart publish failed at shell startup with `Bash/Service/CreateInstance/0xd0000022`
- `work/000002/upload.opencart.json` and `work/000002/import.opencart.json` were not generated because publish failed before those stages
- characteristics diagnostics report unresolved fields: `characteristics_template_unresolved_fields:12`

## 2026-03-31 - Improve OpenCart publish diagnostics for Bash/WSL and preflight failures

Goal:
- make publish-phase failures explainable when the shell wrapper never starts
- replace opaque `publish_stage: unknown` cases with preflight diagnostics for common environment and artifact failures

Files changed:
- `DOCUMENTATION.md`
- `scraper/pipeline/services/publish_execution.py`
- `scraper/pipeline/tests/test_workflow.py`

Commands run:
- `.\\.venv\\Scripts\\python.exe -m pytest -q scraper/pipeline/tests/test_workflow.py -k "publish_workflow or workflow_main_render_routes_through_render_service"`

Implementation notes:
- added Python-side preflight checks in `publish_execution.py` before invoking `bash`:
  - shell entrypoint exists
  - published CSV exists
  - main gallery image exists
  - `bash` is present on `PATH`
  - `bash --version` can start successfully
- added launcher failure classification for common shell startup issues:
  - `bash_or_wsl_startup_failure`
  - `bash_access_denied`
  - `bash_not_available`
- when Bash/WSL fails before the wrapper script starts, publish now reports `publish_stage = preflight` instead of `unknown`

Validation:
- targeted workflow tests passed: `5 passed`
- covered cases include:
  - successful publish wrapper invocation with Bash probe
  - missing `bash` on `PATH`
  - broken WSL/Bash launcher with `CreateInstance/0xd0000022`
  - missing main gallery image preflight failure

Risks, blockers, or skipped items:
- diagnostics are improved only in the Python publish layer; shell wrapper exit codes remain the source of truth once the wrapper actually starts
- no broader full-run regression suite was executed beyond the targeted workflow tests

## 2026-03-31 - Repair OpenCart publish execution on Windows Bash/WSL and verify end-to-end success

Goal:
- fix the actual publish execution path for Windows so the pipeline can invoke the native OpenCart Bash wrappers reliably
- remove the original `Bash/Service/CreateInstance/0xd0000022` blocker and the follow-on Windows-path invocation failure

Files changed:
- `DOCUMENTATION.md`
- `scraper/pipeline/services/publish_execution.py`
- `scraper/pipeline/tests/test_workflow.py`
- `tools/run_opencart_pipeline.sh`
- `tools/run_opencart_image_upload.sh`
- `tools/run_opencart_import_csv.sh`

Commands run:
- `wsl -l -v`
- `wsl.exe --set-default Ubuntu`
- `bash --version`
- `bash -lc "echo pipeline-bash-ok"`
- `wsl.exe -d Ubuntu bash -lc "echo from-ubuntu"`
- `bash -n tools/run_opencart_pipeline.sh`
- `bash -n tools/run_opencart_image_upload.sh`
- `bash -n tools/run_opencart_import_csv.sh`
- `bash -lc "python3 -m pip install --break-system-packages playwright"`
- `bash -lc "python3 -m playwright install chromium"`
- `bash -lc "python3 -m playwright install chromium-headless-shell"`
- `bash -lc "python3 -m playwright install-deps chromium-headless-shell"`
- `.\\.venv\\Scripts\\python.exe -m pytest -q scraper/pipeline/tests/test_workflow.py -k "publish_workflow or workflow_main_render_routes_through_render_service or test_execute_publish_workflow_passes_model_and_current_job_product_file or test_execute_publish_workflow_fails_preflight_when_bash_is_missing or test_execute_publish_workflow_classifies_wsl_launcher_probe_failures or test_execute_publish_workflow_fails_preflight_when_main_image_is_missing"`
- `.\\.venv\\Scripts\\python.exe -m pytest -q scraper/pipeline/tests/test_services.py -k "publish_product_maps_execution_result or execute_run_workflow_composes_prepare_and_render_results"`
- `..\.venv\Scripts\python.exe -m pipeline.workflow render --model 000002` from `scraper/`

Implementation notes:
- system diagnosis showed two separate failures:
  - Windows `bash.exe` initially targeted the default WSL distro `Ubuntu-22.04`, which could not create an instance and returned `CreateInstance/0xd0000022`
  - after switching the default distro to working `Ubuntu`, the Python publish layer still passed Windows-only absolute paths into Bash, causing `/bin/bash: D:...run_opencart_pipeline.sh: No such file or directory`
- fixed the host environment by switching the default WSL distro to `Ubuntu`, which restored `bash --version` and direct wrapper execution
- updated `publish_execution.py` so the Bash invocation uses repo-relative shell paths for:
  - `tools/run_opencart_pipeline.sh`
  - `CURRENT_JOB_PRODUCT_FILE`
- stopped forcing `REPO_ROOT` into the shell environment from Windows Python; the wrapper now resolves repo root from its own script path as intended
- normalized the OpenCart shell wrappers to LF line endings and made env loading tolerant of CRLF `.secrets/opencart.env` files by sourcing through `tr -d '\r'`
- installed missing Playwright runtime pieces inside the working WSL distro so the CSV import stage could launch Chromium successfully

Validation:
- direct native publish wrapper run completed successfully for model `000002`:
  - image upload wrote `work/000002/upload.opencart.json`
  - CSV import wrote `work/000002/import.opencart.json`
- targeted workflow tests passed: `5 passed`
- targeted service tests passed: `2 passed`
- rerun through the actual pipeline entrypoint succeeded:
  - `render` exit code `0`
  - `work/000002/candidate/000002.validation.json` still reports `"ok": true`
  - `work/000002/publish.run.json` now reports:
    - `"publish_status": "success"`
    - `"publish_stage": "csv_import"`
    - `"publish_message": "OpenCart publish completed successfully."`

Risks, blockers, or skipped items:
- `Ubuntu-22.04` still appears broken independently of the pipeline and may need separate repair or removal if you intend to use that distro again
- the pipeline now works through the active default distro, but WSL-level distro hygiene is still an operator concern outside repo code

## 2026-03-31 - Run full Product-Agent pipeline for model 000003 (TCL 115C7K)

Goal:
- execute the template-triggered end-to-end pipeline for model `000003`
- prepare scrape artifacts, write the LLM-owned intro and SEO fields, render the candidate and published CSV, and complete the native OpenCart publish phase

Files changed:
- `DOCUMENTATION.md`
- `work/000003/llm/intro_text.output.txt`
- `work/000003/llm/seo_meta.output.json`
- `work/000003/candidate/000003.csv`
- `work/000003/candidate/000003.normalized.json`
- `work/000003/candidate/000003.validation.json`
- `work/000003/candidate/description.html`
- `work/000003/candidate/characteristics.html`
- `products/000003.csv`
- `work/000003/publish.run.json`
- `work/000003/upload.opencart.json`
- `work/000003/import.opencart.json`

Commands run:
- `python -m pipeline.workflow prepare --model 000003 --url "https://www.skroutz.gr/s/60276903/tcl-smart-tileorasi-115-4k-uhd-mini-led-c7k-hdr-2025-115c7k.html" --photos 7 --sections 7 --skroutz-status 1 --boxnow 0 --price 9999` from `scraper/`
- `python -m pipeline.workflow render --model 000003` from `scraper/`

Implementation notes:
- generated the required LLM outputs only for `intro_text`, `product.meta_description`, and `product.meta_keywords`
- kept the intro text to one Greek paragraph within the configured word-count range
- render completed with taxonomy `ΕΙΚΟΝΑ & ΗΧΟΣ > Τηλεοράσεις > 50'' & άνω`
- native OpenCart publish completed successfully after render, including image upload and CSV import

Validation:
- `work/000003/candidate/000003.validation.json` reports `"ok": true`
- `products/000003.csv` was published successfully
- `work/000003/publish.run.json` reports:
  - `publish_status = success`
  - `publish_stage = csv_import`
  - `publish_message = OpenCart publish completed successfully.`
- `work/000003/import.opencart.json` reports `Products Created: 1`

Risks, blockers, or skipped items:
- validation still carries the existing template warning `characteristics_template_unresolved_fields:12`
- unresolved characteristic fields are source-null/template-null gaps, not render blockers for this product

## 2026-03-31 - Fix Skroutz washing machine characteristics template routing

Goal:
- fix the pipeline so Skroutz washing machines do not inherit unrelated schema-based characteristics layouts
- verify the fix against the live regression sample `000007` through the actual workflow

Files changed:
- `DOCUMENTATION.md`
- `resources/templates/characteristics_templates.json`
- `scraper/pipeline/tests/test_characteristics_pipeline.py`
- `work/000007/scrape/000007.report.json`
- `work/000007/candidate/000007.normalized.json`
- `work/000007/candidate/000007.validation.json`
- `work/000007/candidate/characteristics.html`
- `work/000007/candidate/000007.csv`
- `products/000007.csv`
- `work/000007/publish.run.json`
- `work/000007/upload.opencart.json`
- `work/000007/import.opencart.json`

Commands run:
- `python -m pytest scraper/pipeline/tests/test_characteristics_pipeline.py -k "washing_machine or ice_cream_maker or soundbar or built_in_hob or fridge_freezer"`
- `python -m pipeline.workflow prepare --model 000007 --url "https://www.skroutz.gr/s/55224637/Samsung-Plyntirio-Rouchon-9kg-me-Technologia-Atmou-1400-Strofon-Ecobubble-Mayro-WW90DB7U94GBU3.html" --photos 5 --sections 14 --skroutz-status 1 --boxnow 0 --price 900` from `scraper/`
- `python -m pipeline.workflow render --model 000007` from `scraper/`

Implementation notes:
- added taxonomy-specific Skroutz templates for freestanding and built-in washing machines
- configured those templates to prefer the correct schema source files while rendering raw verified spec sections instead of forcing an Electronet-shaped layout onto mismatched Skroutz specs
- added regression coverage to ensure washing machines keep the raw-spec characteristics path and select `plyntiria_rouxwn.json` as the preferred schema family
- reran the actual product workflow for model `000007` after the code change

Validation:
- targeted characteristics tests passed: `9 passed`
- `work/000007/candidate/characteristics.html` now contains washing-machine spec sections instead of meat-mincer fields
- `work/000007/candidate/000007.validation.json` reports `"ok": true`
- validation warnings no longer include `characteristics_template_used` or `characteristics_template_unresolved_fields`
- `work/000007/publish.run.json` reports:
  - `publish_status = success`
  - `publish_stage = csv_import`
  - `publish_message = OpenCart publish completed successfully.`

Risks, blockers, or skipped items:
- the selected washing-machine template currently preserves raw Skroutz section naming and ordering; that is intentional to avoid inventing or partially mapping fields until a complete cross-source washing-machine template is defined
- remaining validation warnings for `000007` are presentation-related (`presentation_sections_weak:3`, `requested_sections_reduced:11`) and are unrelated to the characteristics fix

## 2026-03-31 - Runtime pipeline run for model `000006`

What changed:
- ran the full prepare -> LLM -> render -> OpenCart publish workflow for model `000006` using the live Skroutz washing-machine URL
- authored the LLM-owned outputs `intro_text.output.txt` and `seo_meta.output.json` under `work/000006/llm/`
- corrected an initial intro-text validation failure by expanding the Greek intro from `106` to `121` words and reran render successfully

Files changed:
- `DOCUMENTATION.md`
- `work/000006/llm/intro_text.output.txt`
- `work/000006/llm/seo_meta.output.json`
- `work/000006/candidate/000006.csv`
- `work/000006/candidate/000006.validation.json`
- `work/000006/candidate/description.html`
- `work/000006/candidate/characteristics.html`
- `work/000006/render.run.json`
- `products/000006.csv`
- `work/000006/publish.run.json`
- `work/000006/upload.opencart.json`
- `work/000006/import.opencart.json`

Commands run:
- `python -m pipeline.workflow prepare --model 000006 --url "https://www.skroutz.gr/s/55224637/Samsung-Plyntirio-Rouchon-9kg-me-Technologia-Atmou-1400-Strofon-Ecobubble-Mayro-WW90DB7U94GBU3.html" --photos 5 --sections 14 --skroutz-status 1 --boxnow 0 --price 900` from `scraper/`
- `python -m pipeline.workflow render --model 000006` from `scraper/` (first run failed validation on intro word count)
- `python -m pipeline.workflow render --model 000006` from `scraper/` (rerun succeeded and triggered publish)

Implementation notes:
- kept LLM generation constrained to the runtime-owned fields: `intro_text`, `product.meta_description`, and `product.meta_keywords`
- used only verified source evidence from the generated LLM context for the Greek intro and SEO metadata
- preserved deterministic section/body rendering and characteristics generation from the local pipeline

Validation:
- first render failed with `llm_intro_text_word_count_invalid`
- final `work/000006/candidate/000006.validation.json` reports `"ok": true`
- `products/000006.csv` was published successfully
- `work/000006/publish.run.json` reports:
  - `publish_status = success`
  - `publish_stage = csv_import`
  - `publish_message = OpenCart publish completed successfully.`
- `work/000006/import.opencart.json` reports `Products Updated = 1`

Risks, blockers, or skipped items:
- validation still reports presentation warnings `presentation_sections_weak:3` and `requested_sections_reduced:11`, but these are warnings only and did not block render or publish

## 2026-04-02 - Explicit subcategory match policy for Electronet schema matching

What changed:
- added explicit compiled `subcategory_match_policy` metadata to the Electronet schema library with a conservative exception map for `tileoraseis`, `koyzines`, `plyntiria_piaton`, and `foyrnoi_mikrokymaton`
- updated `SchemaMatcher.build_candidate_pool()` to stay exact-path first and only allow leaf-only fallback when the resolved parent/leaf family has compiled `leaf_family` eligibility
- surfaced `subcategory_match_policy` in matcher debug output and candidate diagnostics so normalized/report artifacts can carry the policy cleanly
- added compiler, synthetic matcher, compiled-library TV fallback, and serialization regression coverage
- regenerated `resources/schemas/electronet_schema_library.json` so runtime uses the explicit policy metadata

Files changed:
- `DOCUMENTATION.md`
- `docs/specs/2026-04-01-category-scoped-schema-matching-contract.md`
- `resources/schemas/electronet_schema_library.json`
- `scraper/pipeline/models.py`
- `scraper/pipeline/schema_matcher.py`
- `scraper/pipeline/tests/test_schema_matcher.py`
- `scraper/pipeline/tests/test_schema_matcher_compiled_library_regressions.py`
- `tools/schema_registry/build_electronet_schema_library.py`
- `tools/schema_registry/tests/test_build_electronet_schema_library.py`

Commands run:
- `python tools/schema_registry/build_electronet_schema_library.py`
- `python -m pytest tools/schema_registry/tests/test_build_electronet_schema_library.py scraper/pipeline/tests/test_schema_matcher.py scraper/pipeline/tests/test_schema_matcher_compiled_library_regressions.py scraper/pipeline/tests/test_prepare_result_assembly_module.py -q`
- `python -m pytest scraper/pipeline/tests/test_execution_models.py scraper/pipeline/tests/test_workflow.py -q`

Validation:
- compiler and matcher focused regressions passed: `32 passed`
- execution model and workflow serialization regressions passed: `42 passed`
- checked-in compiled library now emits `subcategory_match_policy` for every schema entry

Risks, blockers, or skipped items:
- this commit intentionally keeps the `leaf_family` exception set narrow and metadata-driven; broader mixed-family policy handling is still deferred

## 2026-04-02 - Schema-registry validation, index, and coverage tools

What changed:
- finalized the schema-registry support tooling around the live repo layout and outputs
- updated the schema index contract to emit `subcategory_match_policy` from the compiled Electronet library into `resources/schemas/schema_index.csv`
- extended schema-index tests to cover the new column and malformed-library failure handling
- extended coverage tests to lock in `REVIEW` status when multiple templates claim the same expected category
- updated the schema-registry README so the documented emitted metadata matches the current compiled library and matcher debug surface

Files changed:
- `DOCUMENTATION.md`
- `resources/schemas/schema_index.csv`
- `tools/schema_registry/README.md`
- `tools/schema_registry/build_schema_index.py`
- `tools/schema_registry/tests/test_build_schema_index.py`
- `tools/schema_registry/tests/test_refresh_template_coverage.py`

Commands run:
- `python -m tools.schema_registry.validate_templates`
- `python -m tools.schema_registry.build_electronet_schema_library`
- `python -m tools.schema_registry.build_schema_index`
- `python -m tools.schema_registry.refresh_template_coverage`
- `python -m pytest tools/schema_registry/tests/test_validate_templates.py tools/schema_registry/tests/test_build_schema_index.py tools/schema_registry/tests/test_refresh_template_coverage.py tools/schema_registry/tests/test_build_electronet_schema_library.py -q`

Validation:
- repo-root validation CLI passed against the live Electronet templates
- repo-root build CLIs completed successfully for the compiled library, schema index, and coverage report
- focused schema-registry test suite passed: `18 passed`

Risks, blockers, or skipped items:
- `refresh_template_coverage.py` still derives expected coverage from repository taxonomy inputs and bound templates only; it does not infer any broader multi-source coverage model beyond the current repo truth

## 2026-04-02 - Mixed leaf and subcategory family policy normalization

What changed:
- extended the compiled `subcategory_match_policy` contract with a third value, `mixed_family`
- mapped the mixed air-conditioner family templates (`klimatistika`, `toixoy`, `forita`, `ntoylapes`) and mixed fan family templates (`anemistires`, `mini`, `ydronefosis`, `orthostatis`, `epitrapezioi`, `orofis`, `air_coolers_epidapedioi`, `anemisthres_an_toixou`) to `mixed_family`
- kept the existing `leaf_family` exceptions unchanged and preserved strict `exact_subcategory` behavior for non-exception families
- updated `SchemaMatcher.build_candidate_pool()` so exact category-path pools always win first, while leaf-level fallback remains parent/leaf-bounded and is allowed only for `leaf_family` and `mixed_family`
- added synthetic matcher regressions and compiled-library regressions covering exact-win, bounded fallback, and strict fail-closed behavior
- regenerated `resources/schemas/electronet_schema_library.json` to reflect the new explicit policy values

Files changed:
- `DOCUMENTATION.md`
- `docs/specs/2026-04-01-category-scoped-schema-matching-contract.md`
- `resources/schemas/electronet_schema_library.json`
- `scraper/pipeline/schema_matcher.py`
- `scraper/pipeline/tests/test_schema_matcher.py`
- `scraper/pipeline/tests/test_schema_matcher_compiled_library_regressions.py`
- `tools/schema_registry/build_electronet_schema_library.py`
- `tools/schema_registry/tests/test_build_electronet_schema_library.py`

Commands run:
- `python -m tools.schema_registry.build_electronet_schema_library`
- `python -m tools.schema_registry.build_schema_index`
- `python -m tools.schema_registry.refresh_template_coverage`
- `python -m pytest tools/schema_registry/tests/test_build_electronet_schema_library.py scraper/pipeline/tests/test_schema_matcher.py scraper/pipeline/tests/test_schema_matcher_compiled_library_regressions.py tools/schema_registry/tests/test_build_schema_index.py tools/schema_registry/tests/test_refresh_template_coverage.py -q`

Validation:
- focused compiler, matcher, and related registry regressions passed: `41 passed`
- regenerated compiled Electronet schema library now emits `mixed_family` for the intended air-conditioner and fan families

Risks, blockers, or skipped items:
- this commit keeps the `mixed_family` allowlist deliberately narrow and explicit; broader generic mixed-family inference remains out of scope

## 2026-04-02 - Config-driven deterministic rules, schema policy metadata, and OpenCart config cleanup

What changed:
- promoted `resources/mappings/name_rules.json` to the active deterministic-rule source by adding validated loader/resolver code and switching `scraper/pipeline/deterministic_fields.py` to resolve generic rules and source-scoped strategy selection from JSON
- migrated the generic JSON rule payloads to match the live `differentiator_priority_map.csv` differentiator ordering/coverage so the JSON ruleset now carries the same runtime rule content
- kept the existing deterministic family formatters for the supported source-scoped families, but removed the hardcoded source/family gating from the active path in favor of config-backed rule lookup
- added `resources/mappings/schema_policy_rules.json` and updated the Electronet schema compiler to derive `subcategory_match_policy` from authored metadata instead of hardcoded exception sets
- regenerated `resources/schemas/electronet_schema_library.json` and `resources/schemas/schema_index.csv` from the new schema-policy config input with no intended behavior drift
- added `tools/opencart_config.py` as the shared OpenCart runtime config resolver and rewired the importer/uploader Python tools plus the two Bash wrappers to use the same precedence model
- updated the image uploader plan/report to build Besco HTML URLs from the resolved store base instead of a baked host literal
- replaced the product-specific `resources/templates/TEMPLATE_presentation.html` sample with a neutral placeholder/example asset and documented that it is not a runtime content source
- updated operator-facing docs/config comments for the canonical OpenCart config precedence path

Files changed:
- `DOCUMENTATION.md`
- `README.md`
- `opencart.env.example`
- `resources/mappings/name_rules.json`
- `resources/mappings/schema_policy_rules.json`
- `resources/schemas/electronet_schema_library.json`
- `resources/schemas/schema_index.csv`
- `resources/templates/TEMPLATE_presentation.html`
- `scraper/pipeline/deterministic_fields.py`
- `scraper/pipeline/deterministic_rule_config.py`
- `scraper/pipeline/repo_paths.py`
- `scraper/pipeline/tests/test_utils_support_paths.py`
- `tools/opencart_config.py`
- `tools/opencart_import_csv_playwright.py`
- `tools/opencart_upload_images.py`
- `tools/run_opencart_image_upload.sh`
- `tools/run_opencart_import_csv.sh`
- `tools/schema_registry/build_electronet_schema_library.py`
- `tools/schema_registry/tests/test_build_electronet_schema_library.py`

Commands run:
- `python -m pytest -q pipeline/tests/test_deterministic_fields.py`
- `python -m pytest -q tools/schema_registry/tests/test_build_electronet_schema_library.py`
- `python -m pytest -q pipeline/tests/test_utils_support_paths.py`
- `python -m tools.schema_registry.build_electronet_schema_library`
- `python -m tools.schema_registry.build_schema_index`
- `python -m pytest -q pipeline/tests/test_schema_matcher_compiled_library_regressions.py`
- `python -m pytest -q tools/schema_registry/tests/test_build_electronet_schema_library.py`
- inline Python compile checks for:
  - `scraper/pipeline/deterministic_fields.py`
  - `scraper/pipeline/deterministic_rule_config.py`
  - `tools/opencart_config.py`
  - `tools/opencart_import_csv_playwright.py`
  - `tools/opencart_upload_images.py`
- `bash -n tools/run_opencart_import_csv.sh`
- `bash -n tools/run_opencart_image_upload.sh`
- `python tools/opencart_config.py export-shell --repo-root .`

Validation:
- deterministic naming regressions passed: `8 passed`
- schema-registry builder tests passed: `9 passed`
- compiled-library matcher regressions passed: `14 passed`
- support-path regression passed: `1 passed`
- shared OpenCart config resolver executed successfully and both updated Bash wrappers passed syntax validation

Risks, blockers, or skipped items:
- `differentiator_priority_map.csv` remains in the repo for reference/backward auditability, but runtime ownership now belongs to `resources/mappings/name_rules.json`
- the OpenCart config work was validated through compile/syntax checks and resolver execution only; no live admin upload/import run was performed in this pass

Date: 2026-04-02

Milestone: Generic deterministic unit assembly fix and live Electronet verification

What changed:
- fixed the generic deterministic differentiator resolver so partial spec-label matches can recover split label/value measurements like `Τάση Volt -> 18V` instead of degrading to bare alias tokens such as `Volt`
- added matched-label-aware unit normalization for deterministic metadata outputs so names/meta titles/SEO now compact units consistently (`18V`, `9kg`, `60cm`, `305Lt`, `2200W`)
- tightened fuzzy alias matching to avoid broad generic aliases like `Τύπος` incorrectly binding to unrelated spec labels such as `Τύπος Μπαταρίας`
- preserved literal/title fallback behavior for non-spec differentiators while upgrading measurement fallback extraction to capture full numeric phrases when no spec label match exists
- corrected stale corrupted Greek label literals in the source-scoped Skroutz deterministic helpers so soundbar, coffee-filter, kettle, ice-cream-maker, tabletop-hob, and fridge-freezer strategies resolve current spec labels deterministically again
- reran the live Electronet workflow for model `331566`; the published CSV now uses `Black&Decker PV1820L-QW – Σκουπάκι 18V Ανθρακί` with aligned `meta_title`, `seo_keyword`, and `product_url`

Files changed:
- `DOCUMENTATION.md`
- `scraper/pipeline/deterministic_fields.py`
- `scraper/pipeline/tests/test_deterministic_fields.py`

Commands run:
- `python -m pytest -q scraper/pipeline/tests/test_deterministic_fields.py`
- `python -m pytest -q scraper/pipeline/tests/test_workflow.py`
- `python -m pytest -q scraper/pipeline/tests/test_skroutz_integration.py`
- `python -m pytest -q scraper/pipeline/tests/test_deterministic_fields.py scraper/pipeline/tests/test_skroutz_integration.py scraper/pipeline/tests/test_workflow.py`
- `python -m pipeline.workflow prepare --model 331566 --url "https://www.electronet.gr/exoplismos-spitioy/skoypisma/skoypakia/skoypaki-black-decker-dustbuster-pivot-pv1820l-qw-18-volt" --photos 1 --sections 4 --skroutz-status 0 --boxnow 1 --price 99`
- `python -m pipeline.workflow render --model 331566`

Validation:
- deterministic/workflow/integration regression suite passed: `60 passed`
- live `331566` prepare completed successfully and regenerated LLM context with deterministic differentiators `18V`, `Ανθρακί`
- live `331566` render validation reported `ok: true`
- live OpenCart publish completed successfully with `publish_status: success` and `publish_stage: csv_import`

Risks, blockers, or skipped items:
- the compact-unit policy now changes deterministic names/slugs where old outputs used spaced units; additional baseline updates may be needed as more archived products are rerendered
- the fix intentionally leaves LLM-owned `meta_description` and `meta_keyword` content untouched; only deterministic inputs and outputs were changed
