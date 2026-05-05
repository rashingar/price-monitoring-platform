# Category-Scoped Schema Matching Contract

Date: 2026-04-01
Status: implemented

## Purpose

This document records the landed contract for category-scoped schema matching.

The branch scope covered:
- schema/template compilation
- compiled runtime metadata
- runtime schema selection safety
- structured matcher debug reporting

This branch did not change:
- category resolution behavior
- public workflow entrypoints
- unrelated prepare/render orchestration

## Problem statement

The safety gap was not category resolution alone. A product could resolve to the correct canonical category while schema matching still drifted to an unrelated template because selection was previously too global or too weakly constrained.

The failure class this implementation prevents is a correctly resolved washing-machine product inheriting characteristics from an unrelated kitchen, grooming, or other appliance family.

## Landed design

1. Runtime schema selection is category-scoped, not global.
2. Compiled runtime metadata includes category binding plus hard-gating fields.
3. If a resolved category has exactly one active safe template, runtime selects it directly.
4. If multiple active safe templates exist in one category family, only those siblings may compete.
5. If hard gates fail, matcher returns a fail-closed result instead of borrowing another category's schema.

## Compiled runtime metadata

Every compiled runtime entry now includes these matcher-relevant fields:

| Field | Meaning |
| --- | --- |
| `schema_id` | Stable deterministic identifier derived from current authored template structure and current taxonomy binding. |
| `source_system` | Source family the compiled template belongs to. |
| `template_id` | Stable compiled template identifier. |
| `authored_template_id` | Authored template id from the source template file. |
| `category_path` | Canonical full category path bound to the template. |
| `parent_category` | Canonical parent category segment. |
| `leaf_category` | Canonical leaf category segment. |
| `sub_category` | Canonical optional sub-category segment. |
| `subcategory_match_policy` | Explicit policy controlling whether a resolved subcategory may fall back to a leaf-only template inside the same parent/leaf family. |
| `cta_map_key` | Deterministic CTA mapping key already used elsewhere in the pipeline. |
| `cta_url` | Resolved CTA URL bound to the taxonomy entry. |
| `template_status` | Runtime eligibility status. |
| `match_mode` | Runtime matching mode for the compiled entry. |
| `section_names_exact` | Exact authored section names. |
| `section_names_normalized` | Normalized section names used by runtime matching. |
| `label_set_exact` | Exact authored label set. |
| `label_set_normalized` | Normalized label set used by runtime matching. |
| `section_label_pairs_normalized` | Normalized section-label pairs used for bounded sibling comparison. |
| `discriminator_labels` | Labels that distinguish one sibling template from another. |
| `required_labels_any` | At least one of these labels must be present when populated. |
| `required_labels_all` | All of these labels must be present when populated. |
| `forbidden_labels` | Presence of any of these labels disqualifies the candidate. |
| `min_section_overlap` | Minimum section-overlap count required before scoring can proceed. |
| `min_label_overlap` | Minimum label-overlap count required before scoring can proceed. |
| `sibling_template_ids` | Closed list of sibling templates allowed to compete inside the same category family. |
| `fingerprint` | Stable compiled fingerprint for deterministic change tracking. |
| `source_template_file` | Source template path used to produce the compiled entry. |
| `n_sections` | Count of compiled sections. |
| `n_rows_total` | Count of compiled characteristic rows. |
| `sections` | Compatibility section payload emitted from current authored template sections in authored order. |
| `sentinel` | Sentinel section/label metadata used for diagnostics. |
| `source_files` | Source filenames associated with the compiled entry. |

Landed `template_status` behavior:
- `active`: eligible for automatic runtime selection
- `manual_only`: compiled for visibility/diagnostics, excluded from automatic runtime selection
- `deprecated`: compiled for visibility/diagnostics, excluded from automatic runtime selection
- `incomplete`: compiled for visibility/diagnostics, excluded from automatic runtime selection

Landed `match_mode` values:
- `direct_single`: the category-scoped active pool contains exactly one safe template; runtime selects it directly
- `category_pool`: multiple active siblings exist in the same category family; runtime may compare only within that bounded pool
- `manual_only`: entry is visible in compiled metadata but excluded from automatic runtime matching

Landed `subcategory_match_policy` values:
- `exact_subcategory`: if a resolved subcategory path has no exact compiled pool, runtime fails closed instead of falling back to a leaf-only template
- `leaf_family`: if a resolved subcategory path has no exact compiled pool, runtime may fall back only to leaf-only templates explicitly marked with this policy inside the same resolved parent/leaf family
- `mixed_family`: exact subcategory templates and a leaf-level template may coexist in one parent/leaf family; runtime must use the exact category-path pool when present and may fall back to the leaf-level template only when no exact compiled pool exists

## Runtime matcher decision flow

The landed matcher flow is:

1. Resolve canonical category first.
2. Build a category-scoped candidate pool from compiled metadata using `taxonomy_path` when available.
3. If `taxonomy_path` is absent but parent/leaf/subcategory are resolved, normalize that binding and use it to scope the pool.
4. If no exact category-path pool exists and the resolved family has an explicitly eligible fallback policy (`leaf_family` or `mixed_family`), fall back only to leaf-only templates inside that same resolved parent/leaf family.
5. In `mixed_family` categories, exact subcategory templates and leaf-level templates may coexist in the broader family, but the exact category-path pool always wins when it exists.
6. Apply preferred source-file narrowing only inside that already bounded pool.
7. Drop any candidate whose `template_status` is not `active`.
8. If exactly one active safe template remains, select it directly and do not run sibling scoring.
9. If multiple active safe templates remain, apply hard gates before scoring:
   - reject candidates missing `required_labels_all`
   - reject candidates missing all of `required_labels_any` when that field is populated
   - reject candidates containing any `forbidden_labels`
   - reject candidates below `min_section_overlap`
   - reject candidates below `min_label_overlap`
10. Score only the remaining sibling candidates in that same bounded category family using:
   - normalized section overlap
   - normalized label overlap
   - normalized section-label pair overlap
   - discriminator-label overlap
11. If no candidate survives the hard gates, return a fail-closed matcher result.

## Hard-gating rules

The hard gates are mandatory safety checks, not soft ranking hints:

- `required_labels_all`
  - every listed normalized label must be present
- `required_labels_any`
  - at least one listed normalized label must be present when the field is populated
- `forbidden_labels`
  - any overlap disqualifies the candidate immediately
- `min_section_overlap`
  - extracted normalized section overlap must meet the compiled minimum
- `min_label_overlap`
  - extracted normalized label overlap must meet the compiled minimum

If these gates fail, runtime does not downgrade the result into a cross-category fallback.

## Fail-closed semantics

`no_safe_template_match` is the correct fail-closed outcome when the category-scoped runtime pool cannot produce a safe match.

Fail-closed rules:
- no global fuzzy fallback is allowed
- no cross-category schema rescue is allowed
- a candidate from another category family must never be selected to “heal” a mismatch
- `matched_schema_id` stays `null`
- `selected_template_id` stays `null`
- runtime reports still include bounded candidate and gate-failure diagnostics for debugging

Standard fail reasons currently surfaced:
- `pool_empty_for_category`
- `manual_only_category`
- `no_active_templates`
- `discriminator_miss`
- `insufficient_section_overlap`
- `insufficient_label_overlap`
- `no_safe_template_match`

## Runtime debug reporting

Matcher results are exposed through the existing runtime artifacts.

Inspect:
- `work/{model}/scrape/{model}.normalized.json`
  - `schema_match`
- `work/{model}/scrape/{model}.report.json`
  - `schema_resolution`
  - `schema_candidates`
  - `schema_preference`

Structured matcher debug fields currently surfaced on `schema_match` / `schema_resolution`:
- `resolved_category_path`
- `subcategory_match_policy`
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

The entries in `schema_candidates` are bounded to the resolved category pool. They are no longer a global similarity leaderboard.

## Non-goals

- no global fuzzy fallback
- no cross-category schema rescue
- no category taxonomy rewrite in this branch
- no category resolution behavior change in this branch
- no public workflow entrypoint change in this branch
- no unrelated prepare/render orchestration refactor in this branch

## Current branch state

The compiler metadata, category-scoped matcher, structured debug reporting, and regression coverage for this contract are implemented in the repository.
