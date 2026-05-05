# Product-Agent Plan

## Purpose

This file is the source of truth for staged repository changes.

Phase 1 cleanup milestones (M1-M14) are complete and remain preserved below as historical record.

Phase 2: architecture foundation is complete through M29. Phase 3 completed the split-LLM deterministic-presentation refactor through M34. Post-split execution seam cleanup, service/workflow error hardening, and the workflow-only public-entrypoint cleanup are now complete through M37. Phase 4 remains pending.

## Current repo facts
- The active runnable code lives under `scraper/pipeline/`.
- The repo also contains shared support assets, output CSVs, runtime work artifacts, helper tools, and docs.
- Current runtime documentation treats several support files as source-of-truth inputs and now reads them from `resources/` through the centralized path layer.
- `products/` and `work/` must remain stable during early cleanup.
- `work/{model}/...` is reserved for runtime artifacts.
- Successful render publish now continues with a warning-only OpenCart image upload attempt through `tools/run_opencart_image_upload.sh`, using `CURRENT_JOB_PRODUCT_FILE` for the exact current-job published CSV path.
- Legacy historical references exist and must be archived, not deleted casually.
- Historical milestone evidence below may still mention `scrapper/` and `electronet_single_import` as pre-M23 names.
- Historical milestone evidence below may also mention removed pre-M37 runtime surfaces such as `pipeline.cli`, `full_run.py`, `run_service.py`, and `run_execution.py`.

## Cleanup goals
1. Reduce root clutter safely.
2. Preserve current scraper behavior.
3. Introduce a central path layer before moving runtime support files.
4. Move non-runtime docs/checkpoints out of runtime directories.
5. Archive legacy files cleanly.
6. Categorize support assets under `resources/`.
7. Keep outputs and artifacts stable.
8. Avoid broad refactors during cleanup.

## Non-goals
- No RAG system in this cleanup plan.
- No FastAPI service introduction.
- No Postgres/pgvector migration.
- No broad business-logic rewrite.
- No pyproject migration unless explicitly scheduled later.

## Active phase

### Phase 2 — Architecture foundation

Status: completed

Goals:
1. Define a stable run contract for CLI, workflow, future API, and future job execution.
2. Emit structured metadata alongside current artifacts without changing current outputs.
3. Introduce a thin internal service layer around the current workflow.
4. Define and prove a provider abstraction with one second provider.
5. Preserve current runtime behavior while creating clean internal seams for later expansion.

Hard rule:
- Do not start hybrid RAG before:
  - M15-M19 are complete
  - M20-M22 are complete
  - at least one non-primary provider works behind the provider contract

Phase 2 milestones:
- M15 — define run contract (completed; import-safe run contract models added under `scraper/pipeline/services/` and not wired into runtime behavior)
- M16 — write structured run metadata alongside current files (completed; `prepare.run.json` and `render.run.json` are now emitted under `work/{model}/`)
- M17 — make CLI/workflow emit metadata (completed; historical pre-M37 state added `full.run.json` for the legacy standalone CLI while workflow prepare/render surfaced run status plus metadata path)
- M18 — add service layer models/errors/wrappers (completed; thin internal prepare/render wrappers and a historical pre-M37 full-run composition lived under `scraper/pipeline/services/` without rerouting prepare/render behavior or adding new stage metadata files)
- M19 — route CLI through the service layer (completed; historical pre-M37 state routed the removed `cli.py` adapter through the full-run service while workflow `prepare`/`render` entrypoints continued to call the stage service wrappers)
- M19a — remove remaining cross-layer imports after service routing (completed; shared input validation moved to a neutral module, and the now-removed `cli.py` / `full_run.py` cross-layer imports were reduced without changing runtime behavior at the time)
- M20 — define provider contract and registry (completed; standalone typed provider models, base contract, and registry now exist under `scraper/pipeline/providers/` without wiring runtime behavior or extracting current adapters)
- M21 — extract the current primary source into a provider adapter (completed; the Electronet primary source path now runs through a concrete provider adapter while preserving the existing runtime outputs and leaving other sources on their current execution branches)
- M22 — add provider selection and one second provider proof (completed; `full_run.py` now has a minimal private provider-selection seam, Electronet remains the only production-selected provider, and a fixture-backed `SkroutzProvider` is proven through test-injected routing without changing default Skroutz runtime behavior)
- M23 — rename the active runtime package and directory layout (completed; the runtime moved under `scraper/pipeline`; historical pre-M37 invocation included both `python -m pipeline.workflow ...` and the now-removed `python -m pipeline.cli ...`)
- M24 — stabilize the post-workdir test baseline (completed; touched workflow and Skroutz tests now read committed golden CSV baselines from `scraper/pipeline/tests/fixtures/golden_outputs/skroutz/` and assert the live render contract where candidate bundles can exist while publish is skipped on failed validation)
- M25 — route Skroutz through the provider seam in production (completed; supported Skroutz product URLs now select `SkroutzProvider` through `_resolve_provider_for_source(...)`, the provider supports live fetch plus fixture overrides, and prepare/render artifact shapes plus validation semantics remain unchanged)
- M26 — migrate supported manufacturer flows behind provider adapters (completed; the current supported manufacturer runtime flow now selects `ManufacturerTefalProvider` through `_resolve_provider_for_source(...)`, the provider preserves the existing HTTPX-then-Playwright fetch order plus optional fixtures, and prepare/render contracts remain unchanged while manufacturer enrichment regressions are resolved)
- M27 — retire legacy runtime source branches and close the migration phase (completed; historical pre-M37 `execute_full_run(...)` failed fast when a supported source lacked a provider instead of falling back to legacy fetch/parser branches, and provider-based execution became the active internal seam for supported sources)
- M28 — make services the true owner of prepare/render orchestration (completed; the real prepare/render orchestration now lives under `scraper/pipeline/services/prepare_execution.py` and `scraper/pipeline/services/render_execution.py`, `prepare_service.py` and `render_service.py` call those service-owned executors directly without importing `workflow.py`, and `workflow.py` remains a thin CLI/adapter layer with unchanged runtime behavior)
- M29 — make `run_service` the true owner of full-run orchestration (completed; historical pre-M37 full-run composition lived under `scraper/pipeline/services/run_execution.py` and `run_service.py` before those legacy surfaces were removed)

### Phase 3 — Split-LLM `intro_text` and deterministic presentation refactor

Status: completed

Goals:
1. Replace the current single-prompt LLM handoff with two task-specific LLM tasks: `intro_text` and `seo_meta`.
2. Remove presentation section title/body generation from the LLM contract.
3. Build deterministic presentation sections from `presentation_source_sections` while preserving source titles when present and only cleaning/sanitizing wording.
4. Render the final description HTML in code from LLM `intro_text`, deterministic CTA data, and cleaned deterministic source sections while keeping wrappers, classes, and styles code-owned.
5. Add a render-side compatibility phase during the transition and then remove it in final cleanup.
6. Enforce the planned section failure policy and SEO keyword normalization rules in code.

Hard rules:
- Do not move HTML wrappers, CTA blocks, image wiring, or section layout ownership back to the LLM.
- Do not silently continue when `presentation_source_sections` are absent entirely; that case must hard fail.
- Do not remove the compatibility path until regression coverage proves the split-output path is stable.

Phase 3 milestones:
- M30 — split the LLM contract and prepare artifacts (completed; `prepare` now writes task-specific artifacts under `work/{model}/llm/` for `intro_text` and `seo_meta`, emits `task_manifest.json` as the primary handoff index, constrains `intro_text` to plain-text one-paragraph output, and defines `seo_meta` as `meta_description` plus structured `meta_keywords`)
- M31 — add render compatibility for split outputs and legacy combined output (completed; the branch transition proved `render` against both split outputs and the temporary combined fallback before final cleanup removed the legacy path)
- M32 — build deterministic presentation sections and section-quality policy (completed; `presentation_source_sections` are now classified as `usable`, `weak`, or `missing`; missing source sections hard fail; weak sections or exactly one missing requested section warn and continue with fewer sections; source wording is preserved apart from cleaning/sanitization; and source titles are retained when present)
- M33 — render final description HTML and SEO normalization in code (completed; description HTML is now assembled in code from plain-text `intro_text`, deterministic CTA data, and cleaned deterministic source sections; wrappers/classes/styles remain code-owned; keyword normalization in code enforces brand/model presence while collapsing duplicates and singular/plural variants; and section-image mapping stays tied to original source order when weak sections are skipped)
- M34 — final cleanup of legacy combined artifacts and docs (completed; the legacy single-prompt artifact contract was removed from steady-state prepare/render expectations, `render` no longer depends on combined `llm_output.json`, obsolete combined prompt/schema assets were retired, and user-facing/runtime docs now describe the final split-task contract)

### Post-split execution seam cleanup

Status: completed

Goals:
1. Finish the prepare/render execution seam after the split-LLM refactor.
2. Make `prepare` truly scrape-only plus LLM-handoff-only.
3. Keep `render` as the sole owner of candidate CSV generation, validation artifacts, description HTML, characteristics HTML, and publish copy.
4. Remove the remaining active-path dependence on `execute_full_run(...)` for prepare-stage behavior.
5. Reduce or retire `full_run.py` from the active prepare path without broadening scope into provider bootstrap, service error taxonomy, or CI.

Hard rules:
- Do not reintroduce combined LLM artifacts or change the split-task `intro_text` / `seo_meta` contract.
- Do not let `prepare` write candidate or publish artifacts in steady state.
- Do not broaden this cleanup into provider bootstrap, service error taxonomy, or CI work.

Post-split milestone:
- M35 — clean up the prepare/render execution seam (completed; `scraper/pipeline/prepare_stage.py` is now the scrape-only execution core, `scraper/pipeline/services/prepare_execution.py` writes scrape plus split-task handoff artifacts without routing through `execute_full_run(...)`, `prepare` no longer writes a scrape-stage CSV, `render` remains the sole owner of candidate and publish outputs, and `scraper/pipeline/full_run.py` is reduced to a thin compatibility wrapper for explicit direct callers)

Implementation substeps:
1. Extract or introduce a scrape-only execution seam that returns the parsed, taxonomy, normalized, and report data needed by `prepare` without writing candidate-stage outputs.
2. Re-route `scraper/pipeline/services/prepare_execution.py` to that scrape-only seam and remove its active-path dependency on `execute_full_run(...)`.
3. Remove scrape-stage CSV generation and any other candidate/publish side effects from the active prepare path while preserving scrape artifacts under `work/{model}/scrape/` and task handoff artifacts under `work/{model}/llm/`.
4. Keep `scraper/pipeline/services/render_execution.py` as the sole owner of candidate CSV generation, validation reports, `description.html`, `characteristics.html`, and publish-copy to `products/`.
5. Narrow `scraper/pipeline/full_run.py` to explicit full-run composition only, or retire it from the active prepare path entirely, without changing supported-provider behavior.

Acceptance criteria:
1. `python -m pipeline.workflow prepare ...` writes only scrape artifacts and LLM handoff artifacts under `work/{model}/`; it does not write `work/{model}/scrape/{model}.csv`, candidate artifacts, or publish outputs.
2. `scraper/pipeline/services/prepare_execution.py` no longer imports or depends on `execute_full_run(...)` for active prepare behavior.
3. `python -m pipeline.workflow render --model {model}` remains the sole owner of `work/{model}/candidate/{model}.csv`, `work/{model}/candidate/{model}.validation.json`, `work/{model}/candidate/description.html`, `work/{model}/candidate/characteristics.html`, and `products/{model}.csv`.
4. Split-task `intro_text` / `seo_meta` inputs and outputs, supported-provider behavior, and render validation semantics remain unchanged.
5. `scraper/pipeline/full_run.py` is either reduced to an explicit full-run wrapper over prepare plus render or otherwise removed from the active prepare path, with no new scope added in provider bootstrap, service error taxonomy, or CI.

### Service/workflow error taxonomy hardening

Status: completed

Goals:
1. Replace exception-type-name service errors with stable semantic service codes.
2. Keep low-level exception mapping at the service boundary without introducing a large exception hierarchy.
3. Make workflow exit behavior explicit and stable across prepare/render failure modes.
4. Store stable semantic error codes in run metadata instead of raw exception type names.

Hard rules:
- Keep user-facing CLI/workflow error messages readable.
- Do not broaden this work into provider bootstrap, CI, or a larger exception hierarchy redesign.
- Keep fetch/normalize behavior inside providers unchanged.

Milestone:
- M36 — add stable service error taxonomy and workflow exit mapping (completed; `scraper/pipeline/services/errors.py` now defines stable semantic error codes plus a boundary mapper, prepare/render/full-run services wrap low-level failures into those codes, workflow exit behavior is driven by an explicit code-to-exit matrix, and prepare/render metadata now persist stable semantic `error_code` values including validation failures)

### Workflow-only public entrypoint cleanup

Status: completed

Goals:
1. Make `python -m pipeline.workflow ...` the only public CLI entrypoint.
2. Remove the remaining legacy public-entrypoint and full-run compatibility surfaces:
   - `scraper/pipeline/cli.py`
   - `scraper/pipeline/full_run.py`
   - `scraper/pipeline/services/run_service.py`
   - `scraper/pipeline/services/run_execution.py`
3. Move provider-selection and supported-source regression coverage off `execute_full_run(...)` and onto the surviving workflow, prepare-stage, provider-registry, and provider-adapter seams.
4. Update active runtime docs so they present only the surviving workflow entrypoint.

Hard rules:
- Keep active usage docs aligned with the surviving runtime surface only.
- Do not broaden this cleanup into provider fetch/normalize changes, LLM contract changes, or unrelated service-boundary refactors.

Milestone:
- M37 — make `pipeline.workflow` the only public CLI entrypoint (completed; `pipeline.workflow` is now the sole public command surface, `pipeline.cli` plus the legacy full-run compatibility stack have been removed, provider-selection coverage no longer anchors on `execute_full_run(...)`, and active docs no longer advertise removed entrypoints as runnable)

Acceptance criteria:
1. `python -m pipeline.workflow prepare ...` and `python -m pipeline.workflow render ...` remain the only documented public runtime commands.
2. `scraper/pipeline/cli.py`, `scraper/pipeline/full_run.py`, `scraper/pipeline/services/run_service.py`, and `scraper/pipeline/services/run_execution.py` are removed.
3. Provider-selection and supported-source coverage no longer calls `execute_full_run(...)` and instead asserts the surviving workflow/prepare/provider seams directly.
4. Active docs present only the workflow prepare/render interface as runnable.

### Branch scope — typed execution results

Status: completed

Purpose:
1. Freeze the exact branch scope for converting prepare/render execution outputs from ad hoc dict payloads into typed execution result objects.
2. Keep this work limited to the execution-result seam between `execute_prepare_workflow(...)` / `execute_render_workflow(...)` and the service wrappers that consume them.
3. Preserve current runtime behavior, current workflow commands, and the outward service-layer contract while this internal typing cleanup lands.

Target end state:
1. `execute_prepare_workflow(...)` returns a typed `PrepareExecutionResult`.
2. `execute_render_workflow(...)` returns a typed `RenderExecutionResult`.
3. `scraper/pipeline/services/prepare_service.py` stops indexing prepare execution payloads through `result["..."]` keys and consumes typed fields instead.
4. `scraper/pipeline/services/render_service.py` stops indexing render execution payloads through `result["..."]` keys and consumes typed fields instead.
5. The outward `ServiceResult` contract exposed by `prepare_product(...)` and `render_product(...)` remains stable for callers.

In scope:
1. Introduce typed execution result objects for the prepare and render execution seams.
2. Update the prepare/render service wrappers to map from typed execution result objects into the existing outward `ServiceResult`.
3. Keep artifact paths, run-status values, warnings, validation handling, and current workflow-facing behavior unchanged.

Explicit non-goals:
1. No `prepare_stage.py` decomposition.
2. No metadata semantics redesign.
3. No workflow CLI behavior changes.
4. No provider behavior changes.
5. No service error-policy redesign.

Acceptance criteria:
1. `prepare_service.py` and `render_service.py` no longer depend on `dict.get(...)` / `result["..."]` access against execution results.
2. `execute_prepare_workflow(...)` and `execute_render_workflow(...)` own the typed execution result shapes directly.
3. The outward `ServiceResult` shape, meaning, and artifact contract remain stable.
4. This branch does not expand into stage decomposition, metadata redesign, CLI changes, or provider changes.

Completion note:
- completed; `scraper/pipeline/services/execution_models.py` now owns typed `PrepareExecutionResult` and `RenderExecutionResult` models, `prepare_execution.py` and `render_execution.py` return those typed results directly, and `prepare_service.py` / `render_service.py` consume typed attributes while preserving the outward `ServiceResult` contract

### Branch scope — metadata and error semantics hardening

Status: completed

Purpose:
1. Freeze the exact branch scope for hardening metadata persistence and prepare/render error semantics without changing runtime behavior in the scope-freeze commit.
2. Keep this work limited to the existing metadata-write path plus the prepare/render service-to-workflow reporting seam.
3. Build on the existing `RunMetadata`, `RunArtifacts`, and `ServiceResult` models instead of broadening the branch into new runtime architecture work.

Historical starting point for this branch:
1. `metadata.py` previously swallowed metadata write exceptions.
2. `workflow.py` already printed metadata path and validation/candidate artifact paths for operators.
3. The service layer already exposed `RunMetadata`, `RunArtifacts`, and `ServiceResult`.

Target end state:
1. No silent metadata write failure remains in the active prepare/render paths.
2. `prepare` and `render` expose consistent partial-failure semantics when the main stage result is known but metadata or artifact-side effects fail.
3. Artifact absence is surfaced consistently across prepare/render service results and workflow-facing reporting.
4. Workflow-facing behavior remains stable unless the run truly fails.

In scope:
1. Harden metadata write semantics around the existing prepare/render metadata persistence path.
2. Align prepare/render handling so metadata-write and artifact-surfacing problems follow the same partial-failure policy.
3. Normalize how missing expected artifacts are represented through the existing `RunArtifacts` and `ServiceResult` contracts.
4. Preserve current operator-facing metadata-path and candidate/validation-path reporting on successful runs.

Explicit non-goals:
1. No `prepare_stage.py` decomposition.
2. No typed-result redesign beyond the existing `RunMetadata`, `RunArtifacts`, and `ServiceResult` models.
3. No workflow parser or CLI changes.
4. No provider routing changes.
5. No broader runtime-behavior changes outside metadata and error semantics hardening.

Acceptance criteria:
1. No silent metadata write failures remain on the active prepare/render paths.
2. Prepare and render expose the same partial-failure semantics for metadata-write and artifact-availability problems.
3. Missing expected artifacts are surfaced consistently to callers and operators instead of being silently omitted.
4. Existing workflow-facing operator output remains stable unless the underlying run truly fails.
5. This branch does not expand into stage decomposition, typed-result redesign, workflow parser/CLI work, or provider routing changes.

Completion note:
- completed; `scraper/pipeline/services/metadata.py` now raises structured metadata-write failures instead of silently ignoring them, `prepare_service.py` and `render_service.py` now distinguish degraded known-outcome results from hard failures when metadata or required artifacts are missing, and workflow-facing prepare/render summaries keep the same public command shape while showing `Metadata path: None` when degraded results do not have a persisted metadata file

### Branch scope — prepare-stage provider-resolution refactor

Status: scope defined

Purpose:
1. Freeze the exact branch scope for extracting the provider-resolution seam out of `scraper/pipeline/prepare_stage.py` first, without changing observable runtime behavior.
2. Keep this branch limited to provider resolution and provider-backed source preparation concerns that currently sit inline inside `prepare_stage.py`.
3. Preserve the current public workflow entrypoint, prepare/render ownership split, artifact paths, warnings, and failures while the seam is isolated.

Branch goal:
1. Move the provider-resolution decision path behind a dedicated internal seam while keeping `python -m pipeline.workflow prepare ...` behavior unchanged.

Landed extracted module:
1. `scraper/pipeline/prepare_provider_resolution.py`

Proposed seam responsibilities:
1. Source detection.
2. Runtime provider registry bootstrap.
3. Source-to-`provider_id` mapping.
4. `registry.require(...)`.
5. `provider.fetch_snapshot(...)`.
6. `provider.normalize(...)`.
7. Conversion from `ProviderResult` into the existing local fetch/parsed shape consumed by `prepare_stage.py`.
8. Final URL scope validation.
9. Source-specific product-page checks and operator hints that currently run before gallery, taxonomy, and schema work.

Landed seam result type:
1. `PrepareProviderResolutionResult`

Landed result fields:
1. `source`
2. `provider_id`
3. `fetch`
4. `parsed`

Result contract notes:
1. `fetch` and `parsed` are intentionally existing local shapes reused by `prepare_stage.py`; this branch does not redesign persistence payloads or schema-matching inputs.
2. Warning text, ordering, and emission points must remain behaviorally unchanged even though warning ownership now sits inside the extracted seam.

Invariants that must not change:
1. Public workflow entrypoint and CLI flags remain unchanged.
2. Prepare remains scrape-only plus LLM-handoff-only; render remains the sole owner of candidate and publish outputs.
3. Output artifact paths remain exactly under the current `work/{model}/...` and `products/{model}.csv` locations.
4. Artifact persistence stays where it is in this branch; no persistence extraction lands here.
5. Schema matching stays where it is in this branch; no schema-matching extraction lands here.
6. The split-task LLM handoff contract stays unchanged.
7. Supported-source routing behavior, source-specific validation behavior, and error/warning behavior stay unchanged.
8. The existing local conversion from provider output into prepare-stage fetch/parsed data remains behaviorally identical.

Explicit non-goals:
1. No public entrypoint or CLI behavior changes.
2. No prepare/render ownership-boundary changes.
3. No output artifact path changes.
4. No artifact-persistence extraction in this branch.
5. No schema-matching extraction in this branch.
6. No split-task LLM handoff contract changes.
7. No provider fetch/normalize behavior changes beyond relocating the orchestration seam.

Test strategy for the next commits:
1. Add focused regression coverage around the extracted seam using the current supported-source matrix so source detection, provider selection, final URL validation, and product-page guardrails are asserted directly.
2. Keep prepare-stage and workflow regression coverage unchanged in meaning so the refactor proves no observable behavior change for Electronet, Skroutz, and currently supported manufacturer flows.
3. Reuse committed fixtures and current workflow-oriented tests rather than introducing a new runtime path.
4. Run targeted provider-selection and prepare/workflow tests during each extraction step, then run the full scraper test suite before closing the branch.

Landed injection boundary:
1. `execute_prepare_stage(...)` should keep only one provider-resolution seam injection, `resolve_prepare_provider_input_fn`, instead of exposing the provider-specific bootstrap/mapping/parser injection surface directly.

Planned sequencing after this branch:
1. The next follow-up branch after this provider-resolution extraction should isolate artifact persistence out of `prepare_stage.py`.

### Branch scope — prepare-stage artifact persistence refactor

Status: completed

Purpose:
1. Freeze the exact branch scope for extracting all scrape-stage artifact persistence out of `scraper/pipeline/prepare_stage.py` into a dedicated module, without changing observable runtime behavior.
2. Keep this branch limited to scrape-stage writes under `work/{model}/scrape/` and the persistence seam that currently lives inline inside `prepare_stage.py`.
3. Preserve the current public workflow entrypoint, prepare/render ownership split, provider-resolution ownership, artifact paths, warnings, errors, and stage result payload keys while the write seam is isolated.

Branch goal:
1. Move all scrape-stage artifact persistence currently owned inline by `scraper/pipeline/prepare_stage.py` behind one dedicated internal persistence module, while keeping `python -m pipeline.workflow prepare ...` behavior unchanged.

Explicit write scope for this branch:
1. `work/{model}/scrape/{model}.raw.html`
2. `work/{model}/scrape/{model}.source.json`
3. `work/{model}/scrape/{model}.normalized.json`
4. `work/{model}/scrape/{model}.report.json`
5. scrape-stage supporting assets and auxiliary artifacts currently written under `work/{model}/scrape/`

Landed extracted module:
1. `scraper/pipeline/prepare_scrape_persistence.py`

Landed typed persistence names:
1. input: `PrepareScrapePersistenceInput`
2. result: `PrepareScrapePersistenceResult`

Landed seam responsibilities:
1. Persist the raw fetched HTML artifact under the current `work/{model}/scrape/` path and filename.
2. Persist the source payload JSON under the current `work/{model}/scrape/` path and filename.
3. Persist the normalized payload JSON under the current `work/{model}/scrape/` path and filename.
4. Persist the scrape report JSON under the current `work/{model}/scrape/` path and filename.
5. Persist any scrape-stage supporting assets and auxiliary artifacts that currently belong under `work/{model}/scrape/`.
6. Return the same persisted artifact-path information that the current prepare-stage flow already exposes to downstream callers.

Ownership boundary that must stay explicit:
1. `scraper/pipeline/services/prepare_execution.py` remains the owner of all `work/{model}/llm/*` task-manifest, context, prompt, and LLM-handoff writes in this branch.
2. This branch extracts scrape-stage writes together only; it does not move `work/{model}/llm/*` persistence out of `prepare_execution.py`.

Invariants that must not change:
1. Public workflow entrypoint and CLI flags remain unchanged.
2. Prepare remains scrape-only plus LLM-handoff-only; render remains the sole owner of candidate and publish outputs.
3. `prepare_execution.py` remains responsible for `work/{model}/llm/*`.
4. Provider-resolution ownership stays where it landed in the provider-resolution branch; no provider-resolution reshuffle happens here.
5. Taxonomy, manufacturer enrichment, schema matching, and normalization logic stay where they are in this branch.
6. Stage result payload keys remain unchanged in this branch.
7. Output artifact paths, filenames, and directory layout remain exactly under the current `work/{model}/scrape/`, `work/{model}/llm/`, `work/{model}/candidate/`, and `products/` locations.
8. Warning text, warning ordering, error text, and failure behavior remain unchanged unless regression tests prove an accidental drift.
9. The split-task LLM handoff contract stays unchanged.

Explicit non-goals:
1. No public workflow or CLI behavior changes.
2. No `work/{model}/llm/*` ownership changes.
3. No provider-resolution extraction or provider-routing changes.
4. No taxonomy/manufacturer/schema logic changes.
5. No stage result payload-key redesign.
6. No artifact path or filename changes.
7. No candidate-stage or publish-stage persistence extraction in this branch.

Follow-up branch candidates after this one:
1. Extract schema-matching or taxonomy-adjacent prepare-stage computation behind its own seam without changing current ownership boundaries.
2. Introduce typed prepare-stage result models for the internal stage seam, if still needed after persistence extraction settles.
3. Harden focused regression coverage around unchanged warning/error text and scrape-artifact path contracts for supported sources.

Completion note:
1. completed; scrape artifact persistence now lives under `scraper/pipeline/prepare_scrape_persistence.py`, `scraper/pipeline/prepare_stage.py` now builds prepare state and delegates scrape-stage persistence through one typed seam call, and `scraper/pipeline/services/prepare_execution.py` remains the sole owner of `work/{model}/llm/*` writes while outward prepare-stage payload keys and scrape artifact paths remain unchanged

### Branch scope — prepare-stage result assembly refactor

Status: completed

Purpose:
1. Extract the deterministic schema-matching and normalized/report assembly seam out of `scraper/pipeline/prepare_stage.py`, after the scrape-persistence branch landed, without changing observable runtime behavior.
2. Keep the branch limited to the schema-match, normalized payload, and report payload assembly that previously sat inline inside `prepare_stage.py`.
3. Preserve the public workflow entrypoint, prepare/render ownership split, output artifact paths, warnings, errors, and split-task LLM handoff contract while this internal computation seam is isolated.

Branch goal:
1. Move the deterministic schema-matching and normalized/report assembly path behind one dedicated internal seam while keeping `python -m pipeline.workflow prepare ...` behavior unchanged.

Landed extracted module:
1. `scraper/pipeline/prepare_result_assembly.py`

Landed result type:
1. `PrepareResultAssemblyResult`

What stays in `prepare_stage.py` after this branch:
1. Provider-resolution orchestration stays in `prepare_stage.py`.
2. Gallery download orchestration and section-image/Besco download orchestration stay in `prepare_stage.py`.
3. Taxonomy resolution stays in `prepare_stage.py` for now.
4. Manufacturer enrichment orchestration stays in `prepare_stage.py` for now.
5. Scrape artifact persistence stays delegated through `scraper/pipeline/prepare_scrape_persistence.py`.
6. Any shaping needed before deterministic result assembly stays in `prepare_stage.py`.
7. The outward `execute_prepare_stage(...)` return payload stays dict-shaped in this branch.

What leaves `prepare_stage.py` in this branch:
1. Effective spec-section selection for deterministic schema matching.
2. Preferred schema-source-file selection for the active taxonomy/source state.
3. The `schema_matcher.match(...)` call and schema-candidate assembly.
4. Deterministic row plus normalized payload assembly currently produced through `build_row(...)`.
5. Deterministic report payload assembly, including warning aggregation, diagnostics packaging, and `files_written` report composition.
6. The internal typed handoff back to `prepare_stage.py` for schema-match, schema-candidates, row, normalized, and report outputs.

Landed seam responsibilities:
1. Accept the already-resolved prepare-stage state needed for deterministic schema matching and result assembly.
2. Build effective spec sections from the current parsed source plus manufacturer-enriched sections.
3. Resolve schema preferences, construct the schema matcher, run schema matching, and return schema candidates with unchanged behavior.
4. Build the deterministic normalized payload and mapped row with unchanged behavior.
5. Assemble the scrape report payload with unchanged warning ordering, diagnostics content, and file-path reporting.
6. Return the deterministic result bundle needed by `prepare_stage.py` without moving taxonomy resolution, manufacturer enrichment, scrape persistence, or LLM handoff ownership.

Invariants that must not change:
1. Public workflow entrypoint and CLI flags remain unchanged.
2. Prepare remains scrape-only plus LLM-handoff-only; render remains the sole owner of candidate and publish outputs.
3. `scraper/pipeline/services/prepare_execution.py` remains responsible for all `work/{model}/llm/*` writes.
4. Output artifact paths, filenames, and directory layout remain exactly under the current `work/{model}/scrape/`, `work/{model}/llm/`, `work/{model}/candidate/`, and `products/` locations.
5. Taxonomy resolution and manufacturer enrichment stay in `prepare_stage.py` for now.
6. Provider-resolution ownership stays where it landed in the previous branch.
7. Render ownership does not change in this branch.
8. The split-task `intro_text` / `seo_meta` handoff contract stays unchanged.
9. Warning text, warning ordering, error text, and failure behavior remain unchanged unless regression tests prove accidental drift.

Explicit non-goals:
1. No public workflow or CLI behavior changes.
2. No prepare/render ownership-boundary changes.
3. No output artifact path or filename changes.
4. No taxonomy-resolution extraction in this branch.
5. No manufacturer-enrichment extraction in this branch.
6. No provider-resolution reshuffle in this branch.
7. No scrape-persistence extraction or path redesign in this branch.
8. No render ownership changes in this branch.
9. No naming-polish cleanup in this branch.
10. No split-task LLM handoff contract changes.

Landed test coverage:
1. Direct schema/result behavior is covered in module-level tests for `scraper/pipeline/prepare_result_assembly.py`.
2. Stage-isolation tests stub only the single result-assembly seam and keep `execute_prepare_stage(...)` focused on upstream orchestration behavior.
3. Existing prepare/workflow/provider regression coverage continues to prove no public behavior change for supported Electronet, Skroutz, and manufacturer flows.
4. Public workflow and `scraper/pipeline/services/prepare_execution.py` behavior remain unchanged.

Landed injection boundary:
1. `execute_prepare_stage(...)` keeps one deterministic result-assembly seam injection, `assemble_prepare_result_fn`, and no longer exposes lower-level schema-matcher injection for this branch.

Recommended next branch:
1. Extract taxonomy/manufacturer-enrichment orchestration out of `scraper/pipeline/prepare_stage.py` as the next internal seam, without widening into workflow or handoff behavior changes.

### Branch scope — category-scoped schema matching contract

Status: pending

Purpose:
1. Freeze the exact branch contract for making runtime schema selection fail closed once canonical category resolution is already correct.
2. Keep this work limited to schema/template compilation and runtime schema selection safety.
3. Preserve category resolution behavior, public workflow entrypoints, and unrelated prepare/render orchestration in the scope-freeze commit.

Problem statement:
1. The current failure mode is not category resolution drift; category resolution can be correct while schema selection still drifts to an unrelated template because matching is too global or too weakly constrained.
2. The concrete failure class to prevent is a correctly resolved washing-machine product borrowing meat-grinder-like characteristics because a global matcher can still score an unrelated template highly enough.

Design contract:
1. Runtime schema selection must be category-scoped, not global.
2. Compiled runtime metadata must bind every selectable template to its resolved category family and expose hard-gating fields for runtime enforcement.
3. When a category resolves to exactly one active safe template, runtime selection must use deterministic direct selection instead of fuzzy competition.
4. When multiple templates exist in the same category family, only sibling templates inside that same category family may compete.
5. If hard gates fail, the matcher must fail closed with `no_safe_template_match` instead of borrowing a schema from another category.

Compiled runtime metadata contract:
1. The compiled runtime manifest for each template entry introduced by this branch must include:
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
2. `template_status` is the compiled safety gate for template eligibility and must distinguish at least:
   - `active`
   - `manual_only`
   - `deprecated`
   - `incomplete`
3. `match_mode` is the compiled runtime-selection mode and must distinguish at least:
   - `direct_only`
   - `sibling_scored`
4. Only `active` templates may enter the automatic runtime candidate pool.
5. `sibling_template_ids` must enumerate only templates within the same category family that are allowed to compete when `match_mode` is `sibling_scored`.

Matcher behavior contract:
1. Resolve canonical category first.
2. Build a category-scoped candidate pool from compiled metadata using the resolved category binding.
3. Drop any candidate marked `manual_only`, `deprecated`, or `incomplete`.
4. If exactly one active safe template remains, select it directly.
5. Otherwise, apply only intra-category hard gates and bounded scoring across sibling candidates from that same category family.
6. If no candidate satisfies the hard gates, return `no_safe_template_match`.

Invariants that must not change in this branch:
1. Category resolution behavior does not change in this branch.
2. Public workflow entrypoints do not change in this branch.
3. Prepare/render orchestration ownership does not change in this branch.
4. This scope-freeze commit does not change runtime behavior yet.

Explicit non-goals:
1. No global fuzzy fallback.
2. No cross-category schema rescue.
3. No category taxonomy rewrite in this branch.
4. No category resolution behavior change in this branch.
5. No public workflow entrypoint change in this branch.
6. No unrelated prepare/render orchestration refactor in this branch.

Documentation home:
1. The detailed field-by-field contract for this branch is recorded in `docs/specs/2026-04-01-category-scoped-schema-matching-contract.md`.

### Phase 4 — Hybrid RAG foundation

Status: pending

Entry handoff:
1. Complete M36 before starting any hybrid RAG work.
2. Keep provider-based execution under `scraper/pipeline/` as the single internal seam for supported sources.
3. Preserve current CLI/workflow commands, accepted inputs, artifact paths, and validation semantics while future retrieval work layers above that seam.
4. Preserve the completed split-task steady-state contract while starting retrieval-layer work; do not reintroduce combined LLM artifacts.
5. Do not reintroduce source-specific routing below the provider boundary.

### Branch scope — split-LLM intro validation timing and intro-only retry

Status: completed on dedicated follow-up branch `feat/split-llm-intro-retry`

Purpose:
1. Move split-LLM orchestration to `seo_meta` generation first, then `intro_text` generation, then immediate intro validation, then intro-only retry on `llm_intro_text_word_count_invalid`, and only after that continue into the existing render/validation/publish flow.
2. Keep this branch limited to the internal split-LLM execution seam plus the render-stage gating point where intro validation must now happen before candidate build starts.
3. Preserve the public workflow surface so `prepare` remains scrape-only plus prompt/context artifact generation and `render` remains the owner of candidate/render/publish work.

Target internal seam:
1. Add a narrow helper module under `scraper/pipeline/services/` for split-LLM stage execution.
2. Introduce:
   - `run_intro_text_with_retry(...)`
   - `execute_split_llm_stage(...)`
3. Keep any new generation/resolution callables optional and internal-facing so tests can inject them without a broader runtime redesign.

Required execution order:
1. Resolve or generate `seo_meta` first.
2. Keep `seo_meta` single-pass in this branch.
3. Resolve or generate `intro_text` second.
4. Validate `intro_text` immediately after each generation/resolution attempt.
5. Retry only `intro_text` when validation returns `llm_intro_text_word_count_invalid`, with at most 3 total intro attempts.
6. Do not enter candidate build, final render assembly, CSV publish copy, or OpenCart publish until intro validation succeeds.
7. Keep later candidate validation as a safety backstop, not the first intro word-count enforcement point.

Behavior rules:
1. `seo_meta` may complete before intro validation succeeds and may remain on disk for inspection if intro later fails.
2. Intro retries must rewrite only `intro_text.output.txt`.
3. Intro retries must not regenerate or mutate `seo_meta.output.json`.
4. Non-word-count intro failures still fail once with no retry and no downstream render/candidate/publish work.
5. A successful intro retry must unlock the downstream render/candidate/publish path exactly once.

Explicit non-goals:
1. No new public CLI command.
2. No prompt/context artifact shape change unless a test strictly requires it.
3. No broad service/model redesign.
4. No change to the existing render/candidate/publish ownership boundary after the intro gate passes.

Completion note:
1. completed; `scraper/pipeline/services/llm_stage_execution.py` now owns `execute_split_llm_stage(...)` plus `run_intro_text_with_retry(...)`, intro retry exhaustion is raised as a typed intro-specific validation error with structured `stage` / `code` / `attempts` data plus persisted per-attempt trace output, intro rewrites now use atomic replace semantics, `scraper/pipeline/services/render_execution.py` resolves `seo_meta` before intro, retries only intro on `llm_intro_text_word_count_invalid`, blocks candidate/render/publish work until intro succeeds, and the new workflow/service regressions prove `seo_meta` remains single-pass while downstream work runs exactly once only after intro validation passes

### Branch scope — prepare-stage taxonomy enrichment refactor

Status: completed

Purpose:
1. Freeze the exact branch scope for extracting taxonomy resolution plus manufacturer-doc enrichment orchestration out of `scraper/pipeline/prepare_stage.py`, after the result-assembly branch landed, without changing observable runtime behavior.
2. Keep this branch limited to one orchestration seam that owns `taxonomy_resolver.resolve(...)`, conditional manufacturer-doc enrichment orchestration, and the typed handoff back into `prepare_stage.py`.
3. Preserve the public workflow entrypoint, prepare/render ownership split, output artifact paths, warnings, errors, and split-task LLM handoff contract while this internal orchestration seam is isolated.

Branch goal:
1. Move taxonomy resolution and manufacturer enrichment together behind one dedicated internal seam while keeping `python -m pipeline.workflow prepare ...` behavior unchanged.

Landed extracted module:
1. `scraper/pipeline/prepare_taxonomy_enrichment.py`

Landed typed result:
1. `PrepareTaxonomyEnrichmentResult`

What leaves `prepare_stage.py` in this branch:
1. The `taxonomy_resolver.resolve(...)` call and the surrounding taxonomy-resolution orchestration.
2. The conditional manufacturer-doc enrichment orchestration that currently runs after taxonomy resolution.
3. The internal typed handoff from that seam back into `prepare_stage.py` for resolved taxonomy and manufacturer-enriched section state.

What stays in `prepare_stage.py` in this branch:
1. Provider-resolution ownership stays in `prepare_stage.py`.
2. Gallery download orchestration and section-image/Besco download orchestration stay in `prepare_stage.py`.
3. Skroutz section extraction and manufacturer-presentation fallback handling stay in `prepare_stage.py`.
4. Scrape artifact persistence stays delegated through `scraper/pipeline/prepare_scrape_persistence.py`.
5. Result assembly remains outside this branch and stays delegated through `scraper/pipeline/prepare_result_assembly.py`.
6. The outward `execute_prepare_stage(...)` return payload stays dict-shaped in this branch.
7. Any orchestration before the new taxonomy/enrichment seam and after its typed handoff stays in `prepare_stage.py`.

Seam boundary that must stay explicit:
1. Taxonomy resolution and manufacturer enrichment move together as one orchestration seam in this branch; they do not split into separate extractions.
2. Result assembly remains outside this branch; no schema-match, normalized/report assembly, or result-assembly ownership moves in this branch.
3. `scraper/pipeline/services/prepare_execution.py` remains unchanged in this branch.
4. `execute_prepare_stage(...)` now keeps one taxonomy/enrichment seam injection, `resolve_prepare_taxonomy_enrichment_fn`, instead of exposing lower-level resolver or enrichment-helper injections directly.

Invariants that must not change:
1. Public workflow entrypoint and CLI flags remain unchanged.
2. Prepare remains scrape-only plus LLM-handoff-only; render remains the sole owner of candidate and publish outputs.
3. `scraper/pipeline/services/prepare_execution.py` remains responsible for all `work/{model}/llm/*` writes and remains behaviorally unchanged.
4. Output artifact paths, filenames, and directory layout remain exactly under the current `work/{model}/scrape/`, `work/{model}/llm/`, `work/{model}/candidate/`, and `products/` locations.
5. Result assembly remains delegated through `scraper/pipeline/prepare_result_assembly.py`.
6. Provider-resolution ownership stays where it landed in the previous branch.
7. Render ownership does not change in this branch.
8. The split-task `intro_text` / `seo_meta` handoff contract stays unchanged.
9. Warning text, warning ordering, error text, and failure behavior remain unchanged unless regression tests prove accidental drift.

Explicit non-goals:
1. No public workflow or CLI behavior changes.
2. No prepare/render ownership-boundary changes.
3. No output artifact path or filename changes.
4. No `prepare_execution.py` behavior changes.
5. No provider-resolution reshuffle in this branch.
6. No scrape-persistence extraction or path redesign in this branch.
7. No result-assembly extraction or result-assembly ownership changes in this branch.
8. No schema/result-assembly ownership changes in this branch.
9. No render ownership changes in this branch.
10. No naming-polish cleanup in this branch.
11. No split-task LLM handoff contract changes.

Landed test coverage split:
1. Direct seam coverage now lives in `scraper/pipeline/tests/test_prepare_taxonomy_enrichment_module.py` for taxonomy resolution, manufacturer-doc enrichment gating, and the typed result returned to `prepare_stage.py`.
2. Stage-isolation coverage now lives in `scraper/pipeline/tests/test_prepare_taxonomy_enrichment.py` and stubs only the single taxonomy/enrichment seam so `execute_prepare_stage(...)` stays focused on surrounding orchestration behavior.
3. Adjacent stage isolation for the downstream deterministic seam remains in `scraper/pipeline/tests/test_prepare_stage_result_assembly.py`.
4. Existing prepare/workflow/provider regression coverage continues to prove no public behavior change for Electronet, Skroutz, and supported manufacturer flows.

Completion note:
1. completed; taxonomy resolution plus Skroutz-only manufacturer-doc enrichment now live in `scraper/pipeline/prepare_taxonomy_enrichment.py`, `PrepareTaxonomyEnrichmentResult` is the typed handoff back into `prepare_stage.py`, and `execute_prepare_stage(...)` now exposes one injected taxonomy/enrichment seam via `resolve_prepare_taxonomy_enrichment_fn` while preserving outward return keys and prepare/workflow behavior

Recommended next branch:
1. Extract the remaining gallery/Besco plus Skroutz section-extraction orchestration out of `scraper/pipeline/prepare_stage.py` as the next real structural seam; naming polish should stay secondary to that extraction.

### Branch scope — prepare-stage section assets refactor

Status: completed

Purpose:
1. Freeze the exact branch scope for extracting the Skroutz/manufacturer-first section asset workflow out of `scraper/pipeline/prepare_stage.py` without changing observable runtime behavior.
2. Keep this branch limited to the Skroutz section-asset seam, the shared section-image download helper reused by both direct and Skroutz paths, and the deterministic section diagnostics / `bescos_raw` payload builders.
3. Preserve the public workflow entrypoint, prepare/render ownership split, output artifact paths, warnings, errors, and split-task LLM handoff contract while this internal seam is isolated.

Branch goal:
1. Move the Skroutz/manufacturer-first section asset workflow behind one dedicated internal seam while keeping `python -m pipeline.workflow prepare ...` behavior unchanged.

Landed extracted module:
1. `scraper/pipeline/prepare_section_assets.py`

Landed typed result:
1. `PrepareSectionAssetsResult`

What left `prepare_stage.py` in this branch:
1. The whole Skroutz/manufacturer-first section asset workflow that chooses between manufacturer presentation blocks and rendered Skroutz section assets.
2. The rendered-Skroutz image-backed section matching path, including title-order validation and resolved-image selection behavior.
3. The shared section-image download helper used by both the direct-source and Skroutz section paths.
4. Deterministic section diagnostics builders, including section-image candidate payloads, resolved-image payloads, extraction-window payload shaping, and `bescos_raw` / sections-artifact payload assembly.
5. The typed handoff back into `prepare_stage.py` for selected presentation blocks, Besco images, download outputs, warnings, deterministic diagnostics/artifact payloads, and optional presentation HTML override.

What stays in `prepare_stage.py` after this branch:
1. Top-level routing for whether sections run at all stays in `prepare_stage.py`.
2. Direct-source / non-Skroutz section orchestration stays inline in `prepare_stage.py` by design in this branch, while reusing the shared extracted section-image downloader.
3. Final `source_payload` creation stays in `prepare_stage.py`.
4. Final handoff into `assemble_prepare_result_fn(...)` stays in `prepare_stage.py`.
5. Final handoff into `persist_prepare_scrape_artifacts_fn(...)` stays in `prepare_stage.py`.
6. Provider-resolution ownership stays in `prepare_stage.py`.
7. Taxonomy resolution and manufacturer enrichment remain outside this branch and stay delegated through `scraper/pipeline/prepare_taxonomy_enrichment.py`.
8. Result assembly remains outside this branch and stays delegated through `scraper/pipeline/prepare_result_assembly.py`.
9. The outward `execute_prepare_stage(...)` return payload stays dict-shaped in this branch.

Explicit boundary statements:
1. `html_builders.extract_presentation_blocks(...)` stays where it is in `scraper/pipeline/html_builders.py`.
2. `skroutz_sections` helpers stay where they are in `scraper/pipeline/skroutz_sections.py`.
3. Direct-source section extraction itself is not fully extracted in this branch.
4. `scraper/pipeline/services/prepare_execution.py` remains behaviorally unchanged in this branch.
5. Prepare stays scrape-only plus LLM-handoff-only, and render ownership does not change in this branch.

Invariants that must not change:
1. Public workflow entrypoint and CLI flags remain unchanged.
2. Prepare remains scrape-only plus LLM-handoff-only; render remains the sole owner of candidate and publish outputs.
3. `scraper/pipeline/services/prepare_execution.py` remains responsible for all `work/{model}/llm/*` writes and remains behaviorally unchanged.
4. Output artifact paths, filenames, and directory layout remain exactly under the current `work/{model}/scrape/`, `work/{model}/llm/`, `work/{model}/candidate/`, and `products/` locations.
5. Result assembly ownership does not change in this branch.
6. Provider-resolution ownership does not change in this branch.
7. Render ownership does not change in this branch.
8. The split-task `intro_text` / `seo_meta` handoff contract stays unchanged.
9. Warning text, warning ordering, error text, and failure behavior remain unchanged unless regression tests prove accidental drift.

Explicit non-goals:
1. No public workflow or CLI behavior changes.
2. No prepare/render ownership-boundary changes.
3. No output artifact path or filename changes.
4. No `prepare_execution.py` behavior changes.
5. No result-assembly ownership changes in this branch.
6. No provider-resolution ownership changes in this branch.
7. No render ownership changes in this branch.
8. No extraction of the whole direct-source / non-Skroutz section path in this branch.
9. No extraction of `html_builders.extract_presentation_blocks(...)` in this branch.
10. No relocation of `skroutz_sections` helpers in this branch.
11. No naming-polish cleanup in this branch.
12. No split-task LLM handoff contract changes.

Landed test coverage split:
1. Direct helper and standalone seam coverage now lives in `scraper/pipeline/tests/test_prepare_section_assets_module.py` and `scraper/pipeline/tests/test_prepare_skroutz_section_assets_module.py`.
2. Stage-isolation coverage now lives in `scraper/pipeline/tests/test_prepare_section_assets.py` and stubs only the single extracted Skroutz section-assets seam, `resolve_skroutz_section_assets_fn`, when isolating `execute_prepare_stage(...)`.
3. Adjacent stage-isolation coverage remains in `scraper/pipeline/tests/test_prepare_taxonomy_enrichment.py` and `scraper/pipeline/tests/test_prepare_stage_result_assembly.py`.
4. Prepare-focused workflow regression coverage remains the higher-level unchanged-behavior backstop, and the branch kept a targeted `test_prepare_workflow_writes_prompt_artifacts` smoke/regression path green.

Landed injection boundary:
1. `execute_prepare_stage(...)` now keeps one explicit section-assets seam injection, `resolve_skroutz_section_assets_fn`, and does not expose lower-level section helpers in its signature.

Completion note:
1. completed; Skroutz section assets now live behind `scraper/pipeline/prepare_section_assets.py`, `PrepareSectionAssetsResult` is the typed handoff back into `prepare_stage.py`, direct-source / non-Skroutz section extraction intentionally remains inline by design, and `execute_prepare_stage(...)` now exposes one injected section-assets seam via `resolve_skroutz_section_assets_fn` while preserving outward return keys and prepare/workflow behavior.

Recommended next branch:
1. Extract the remaining direct-source / non-Skroutz section orchestration out of `scraper/pipeline/prepare_stage.py` as the next real section seam; naming polish should stay secondary to that extraction.

## Root policy
### Keep in root
- `.claude/`
- `.gitignore`
- `AGENTS.md`
- `RULES.md`
- `README.md`
- `PLAN.md`
- `IMPLEMENT.md`
- `DOCUMENTATION.md`
- `requirements.txt`
- `products/`
- `work/`
- `scraper/`
- `tools/`
- `resources/`

### Move later after path centralization
- none; M6 moved the approved shared support assets into `resources/`

### Shared support assets under `resources/`
- `resources/mappings/`: `MANUFACTURER_SOURCE_MAP.json`, `catalog_taxonomy.json`, `filter_map.json`, `name_rules.json`, `differentiator_priority_map.csv`, `taxonomy_mapping_template.csv`
- `resources/schemas/`: `electronet_schema_library.json`, `schema_index.csv`
- `resources/templates/`: `TEMPLATE_presentation.html`, `characteristics_templates.json`, `product_import_template.csv`
- `resources/prompts/`: `intro_text_prompt.txt`, `seo_meta_prompt.txt`

### Move now
- none; M4 completed the two previously approved safe documentation/planning moves

### Archive
- none; M5 archived the two approved legacy files under `archive/legacy/`

## Planned milestones
## Phase 1 — Cleanup history
### M1 — Create control files and cleanup directories
Status: completed
Evidence:
- `PLAN.md`, `IMPLEMENT.md`, and `DOCUMENTATION.md` already existed before M1 execution, so this milestone was limited to approved scaffolding directories and control-doc logging.

Created:
- `docs/audits/`
- `docs/runbooks/`
- `docs/checkpoints/`
- `docs/specs/`
- `archive/legacy/`
- `resources/mappings/`
- `resources/prompts/`
- `resources/schemas/`
- `resources/templates/`

### M2 — Audit current layout
Status: completed
Evidence:
- Created `docs/audits/repo_cleanup_audit.md` with one-row-per-root-file classifications and explicit non-root cleanup candidates.
- Left `requirements.txt` as `uncertain` pending the later dependency audit because live evidence does not yet prove repo-root ownership.

### M3 — Centralize support-file lookup
Status: completed
Evidence:
- Added `scrapper/electronet_single_import/repo_paths.py` to centralize approved support-asset locations without moving any assets.
- Routed the existing support-asset path hub in `scrapper/electronet_single_import/utils.py` through the new module while preserving downstream imports.

### M4 — Move safe docs/checkpoint files
Status: completed
Evidence:
- Moved the pipeline optimization design doc into `docs/specs/2026-03-22-pipeline-optimization-design.md`.
- Moved the implementation checkpoint into `docs/checkpoints/IMPLEMENTATION_CHECKPOINT.md`.

### M5 — Archive legacy files
Status: completed
Evidence:
- Moved `RULES_legacy.md` to `archive/legacy/RULES_legacy.md`.
- Moved `master_prompt_legacy.txt` to `archive/legacy/master_prompt_legacy.txt`.

### M6 — Move shared support assets into `resources/`
Status: completed
Evidence:
- Moved the approved shared support assets into `resources/mappings/`, `resources/schemas/`, `resources/templates/`, and `resources/prompts/`.
- Updated `scrapper/electronet_single_import/repo_paths.py` so centralized runtime path resolution now targets the new `resources/` locations without changing loader semantics.

### M7 — Normalize documentation
Status: completed
Evidence:
- Updated `README.md` to describe the post-M6 `resources/`, `docs/`, `archive/`, `work/`, and `products/` layout accurately.
- Created `docs/runbooks/repo-layout.md` as the repo-specific layout guide for future operators and Codex runs.

### M8 — Audit dependency strategy
Status: completed
Evidence:
- Recorded `docs/audits/dependency_audit.md` with a side-by-side comparison of `requirements.txt` and `scrapper/requirements.txt`.
- Kept dependency ownership audit-only in M8 and deferred any merge, move, or modernization work pending explicit follow-up approval.

### M9 — Final health pass
Status: completed
Evidence:
- Recorded `docs/audits/post_cleanup_health_pass.md` with the final repo-health summary, remaining issues, safe follow-up items, risky postponed items, and the recommended next action.
- Kept M9 audit-only with no file moves, dependency changes, or runtime-code changes.

### M10 — Consolidate canonical root requirements
Status: completed
Evidence:
- Promoted repo-root `requirements.txt` to the canonical dependency file using the verified live-needed union of root and scraper dependencies.
- Removed `scrapper/requirements.txt` only after clean-environment install, import checks, and full pytest validation succeeded against the canonical root file.

### M11 - Consolidate canonical root README
Status: completed
Evidence:
- Merged the still-useful scraper setup and workflow guidance into the repo-root `README.md`.
- Reduced `scrapper/README.md` to a minimal pointer so the root README is the single canonical README entrypoint.

### M12 - Purge stale references from active guidance
Status: completed
Evidence:
- Verified that stale old-file references now remain only in historical milestone logs, audits, specs, and archive material rather than active current guidance.
- Reduced `scrapper/README.md` further so it acts only as a concise pointer to the canonical repo-root `README.md`.

### M13 - Normalize historical references with provenance preserved
Status: completed
Evidence:
- Added short historical-context notes to the affected audits, spec, archived legacy files, and `DOCUMENTATION.md` so pre-move paths are explicitly labeled as prior-state references.
- Preserved the underlying milestone outcomes and archived text rather than rewriting history into current guidance.

### M14 - Runtime-code redundancy reduction and concision pass
Status: completed
Evidence:
- Moved the confirmed support-asset path consumers to direct imports from `scrapper/electronet_single_import/repo_paths.py`, removing the remaining `utils.py` compatibility-reexport seam.
- Removed the dead `RULES_PATH` constant and the one-callsite `build_model_output_dir()` wrapper without changing the known pytest baseline.

## Phase transition note

Cleanup is complete through M14.

New implementation work starts at M30 and now continues through the completed post-split M37 workflow-only public-entrypoint cleanup before Phase 4. Cleanup history remains preserved for auditability and should not be rewritten unless a historical correction is needed.

## Validation rules
After each milestone:
1. run repo-appropriate tests
2. run scraper smoke checks if path behavior changed
3. confirm no source-of-truth asset path is broken
4. update `DOCUMENTATION.md`

## Stop conditions
Stop and document before proceeding if:
- runtime paths break
- tests fail unexpectedly
- a source-of-truth file has unclear ownership
- dependency-file purpose is uncertain
