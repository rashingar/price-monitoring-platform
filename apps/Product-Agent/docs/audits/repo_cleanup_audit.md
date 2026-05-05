# Repo Cleanup Audit

Historical note:
- This audit records the M2 classification snapshot from before the later M4, M5, M6, and M10 moves.
- Old paths and filenames below are preserved as pre-move evidence, not as current guidance.
- Read root-asset references such as `catalog_taxonomy.json`, `master_prompt+.txt`, and `schemas/compact_response.schema.json` as pre-M6 locations unless a later note says otherwise.

## Evidence Used
- Root inventory from `Get-ChildItem -Force -File` at repo root
- Candidate existence from `Get-ChildItem docs/audits` and `Get-ChildItem docs/superpowers/specs,work`
- `rg` sweep for each explicitly named file or candidate to capture runtime code references, docs or planning references, or absence of references
- Runtime path evidence from `scrapper/electronet_single_import/utils.py`
- Source-of-truth and workflow evidence from `RULES.md`, `AGENTS.md`, `README.md`, and `scrapper/README.md`

No material contradiction was found between the requested classifications and the live repo evidence in this pass. If a later audit finds a meaningful mismatch, that item should be reclassified as `uncertain` until the contradiction is resolved.

M6 update:
- the approved shared support assets were moved into `resources/`
- the classification table below remains the historical M2 pre-move snapshot, not a statement of current asset locations

## Root-Level File Classification
| Root-level file | Classification | Evidence |
| --- | --- | --- |
| `.gitignore` | keep in root | Repo-scoped control file; not a movable runtime asset. |
| `AGENTS.md` | keep in root | Repo-scoped operating instructions for this workflow. |
| `catalog_taxonomy.json` | move later after path centralization | Named as source of truth in `RULES.md`, `README.md`, and `scrapper/README.md`; loaded from repo root in `scrapper/electronet_single_import/utils.py`. |
| `characteristics_templates.json` | move later after path centralization | Loaded from repo root in `scrapper/electronet_single_import/utils.py`; shared support template asset. |
| `differentiator_priority_map.csv` | move later after path centralization | Loaded from repo root in `scrapper/electronet_single_import/utils.py`; shared mapping asset. |
| `DOCUMENTATION.md` | keep in root | Repo control doc used as the running engineering log. |
| `electronet_schema_library.json` | move later after path centralization | Named as source of truth in `RULES.md`, `README.md`, and `scrapper/README.md`; loaded from repo root in `scrapper/electronet_single_import/utils.py`. |
| `filter_map.json` | move later after path centralization | Named in `AGENTS.md`, `RULES.md`, and `README.md`; loaded from repo root in `scrapper/electronet_single_import/utils.py`. |
| `IMPLEMENT.md` | keep in root | Repo control doc for standing execution rules. |
| `MANUFACTURER_SOURCE_MAP.json` | move later after path centralization | Loaded from repo root in `scrapper/electronet_single_import/utils.py`; shared enrichment mapping. |
| `master_prompt+.txt` | move later after path centralization | Named in `AGENTS.md`, `RULES.md`, and `README.md`; loaded from repo root in `scrapper/electronet_single_import/utils.py`. |
| `archive/legacy/master_prompt_legacy.txt` | archive as legacy | `RULES.md` marks the old script-driven workflow as historical only. |
| `name_rules.json` | move later after path centralization | Loaded from repo root in `scrapper/electronet_single_import/utils.py`; shared naming-rules asset. |
| `PLAN.md` | keep in root | Repo control doc and milestone source of truth. |
| `product_import_template.csv` | move later after path centralization | Named in `RULES.md`, `README.md`, and `scrapper/README.md`; loaded from repo root in `scrapper/electronet_single_import/utils.py`. |
| `README.md` | keep in root | Repo-level entry documentation for the current layout. |
| `requirements.txt` | uncertain | Current evidence does not prove root ownership; `scrapper/README.md` installs from `scrapper/requirements.txt`, and dependency ownership is deferred to a later audit. |
| `RULES.md` | keep in root | Repo-scoped runtime rules document. |
| `archive/legacy/RULES_legacy.md` | archive as legacy | `RULES.md` marks the old script-driven workflow as historical only. |
| `schema_index.csv` | move later after path centralization | Only docs or legacy references were found, but it is a shared schema support asset, so this stays conservative pending path centralization. |
| `taxonomy_mapping_template.csv` | move later after path centralization | No live runtime references were found; classified conservatively as a shared mapping template rather than a safe move-now control doc. |
| `TEMPLATE_presentation.html` | move later after path centralization | Named in `RULES.md`, `README.md`, and `scrapper/README.md`; loaded from repo root in `scrapper/electronet_single_import/utils.py`. |

## Explicit Non-Root Entries
| Path | Classification | Evidence |
| --- | --- | --- |
| `schemas/compact_response.schema.json` | move later after path centralization | Named in `AGENTS.md` and `RULES.md`; loaded from `REPO_ROOT / "schemas" / "compact_response.schema.json"` in `scrapper/electronet_single_import/utils.py`. |
| `docs/specs/2026-03-22-pipeline-optimization-design.md` | move now | Search found planning and design references only; no runtime callsites were found. |
| `docs/checkpoints/IMPLEMENTATION_CHECKPOINT.md` | move now | Search found planning references only; no runtime callsites were found, and the prior location inside `work/` conflicted with the runtime-artifact purpose of that tree. |

## Risks And Postponed Items
- `requirements.txt` remains postponed to the dependency audit milestone because the current evidence does not establish whether the repo-root file or `scrapper/requirements.txt` is authoritative.
- `schema_index.csv` and `taxonomy_mapping_template.csv` have weaker direct evidence than the hardcoded support assets; they should be rechecked during path centralization and dependency cleanup.
- M6 executed the approved relocation for the shared support assets that were previously classified as `move later after path centralization`.
- This audit is classification only. No files were moved, deleted, or rewritten outside the approved docs for M2.
