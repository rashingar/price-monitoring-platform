
# Schema Registry

This directory contains the tooling for the editable schema-template layer.

The purpose of the schema registry is to keep **human-maintained schema templates**
separate from the **compiled runtime schema artifacts** used by the pipeline.

## Why this exists

The runtime schema library is compact and useful for fast matching, but it is not
the best authoring surface for:

- reviewing category-specific schema structure
- tracking label drift over time
- validating template consistency
- reporting coverage and missing categories
- compiling deterministic runtime artifacts

This toolchain solves that by introducing an editable template layer that can be:

- validated
- audited
- compiled
- indexed

## Source of truth vs runtime artifacts

### Editable source-of-truth
Located under:

`resources/templates/electronet/`

These template files are the human-maintained category templates.

They should preserve:

* exact section order
* exact label order
* category ownership
* example URLs
* stable template ids
* template fingerprints

### Compiled runtime artifacts

Located under:

`resources/schemas/`


Main outputs:

* `electronet_schema_library.json`
* `schema_index.csv`

These are derived artifacts for runtime matching and inspection.

## Tool responsibilities

### `validate_templates.py`

Validate all schema template files before build.

Responsibilities:

* load template files
* validate against the shared JSON schema contract
* enforce repo-level invariants
* detect duplicate authored ids and file/id drift
* fail loudly when templates are invalid
* support both authored Electronet template shapes currently present in the repo

Use this first.

### `build_electronet_schema_library.py`

Compile validated Electronet templates into the compact runtime schema library.

Responsibilities:

* read template files
* normalize current authored templates into the runtime schema shape
* derive `sections` and `schema_id` only from current authored templates plus taxonomy binding
* derive summary fields such as section counts and sentinel values
* write `resources/schemas/electronet_schema_library.json`

This is the main compile step.

### `build_schema_index.py`

Flatten the compiled runtime schema library into an index CSV.

Responsibilities:

* read the compiled schema library
* emit one row per schema
* produce a stable inspection/debugging index
* write `resources/schemas/schema_index.csv`

This is a support artifact, not the primary runtime output.

### `refresh_template_coverage.py`

Generate a markdown coverage report for the Electronet template registry.

Responsibilities:

* compare expected category coverage against existing templates
* show which categories are covered, missing, or manual-only
* include example-backed visibility for review
* write the coverage report under `docs/audits/`

This is an audit/planning tool, not a runtime step.

## Expected workflow

Typical workflow:

1. Add or edit template files under `resources/templates/electronet/`
2. Run template validation
3. Build the compiled Electronet schema library
4. Build the schema index
5. Refresh the coverage report
6. Commit source templates and derived artifacts together when appropriate

## Suggested command order

```bash
python -m tools.schema_registry.validate_templates
python -m tools.schema_registry.build_electronet_schema_library
python -m tools.schema_registry.build_schema_index
python -m tools.schema_registry.refresh_template_coverage
```

## Design rules

* Templates are the editable source of truth.
* Compiled artifacts are derived outputs.
* Do not edit compiled runtime artifacts manually if they are generated from templates.
* Preserve exact authored Greek strings unless a compiler rule explicitly says otherwise.
* Preserve section and label order.
* Prefer deterministic output over convenience.
* Fail clearly instead of guessing when template inputs are invalid.
* Do not recover schema structure or ids from prior compiled artifacts.

## Landed runtime metadata

`build_electronet_schema_library.py` emits compiled runtime matcher metadata into `resources/schemas/electronet_schema_library.json`.

Matcher-relevant fields that currently land in the compiled library include:

* `schema_id`
* `source_system`
* `template_id`
* `authored_template_id`
* `category_path`
* `parent_category`
* `leaf_category`
* `sub_category`
* `subcategory_match_policy`
* `cta_map_key`
* `cta_url`
* `template_status`
* `match_mode`
* `section_names_exact`
* `section_names_normalized`
* `label_set_exact`
* `label_set_normalized`
* `section_label_pairs_normalized`
* `discriminator_labels`
* `required_labels_any`
* `required_labels_all`
* `forbidden_labels`
* `min_section_overlap`
* `min_label_overlap`
* `sibling_template_ids`
* `fingerprint`
* `source_template_file`
* `n_sections`
* `n_rows_total`
* `sections`
* `sentinel`
* `source_files`

Landed `match_mode` meanings:

* `direct_single`: the category-scoped active runtime pool contains exactly one safe template, so matcher selects it directly
* `category_pool`: multiple active sibling templates exist in one category family, so matcher may compare only inside that bounded pool
* `manual_only`: compiled entry is visible for diagnostics but excluded from automatic runtime matching

Hard-gating metadata consumed by runtime before any sibling scoring:

* `required_labels_any`
* `required_labels_all`
* `forbidden_labels`
* `min_section_overlap`
* `min_label_overlap`

Fail-closed matcher rule:

* if the bounded category pool is empty or no candidate survives the hard gates, runtime returns `no_safe_template_match`
* no global schema similarity fallback is allowed
* no cross-category schema rescue is allowed

## Runtime debug inspection

For a product job, inspect matcher outcomes in:

* `work/{model}/scrape/{model}.normalized.json`
  * `schema_match`
* `work/{model}/scrape/{model}.report.json`
  * `schema_resolution`
  * `schema_candidates`
  * `schema_preference`

Those report objects now expose the structured matcher debug envelope, including:

* resolved category path
* candidate pool size and template ids
* selected template id
* subcategory match policy
* match mode
* hard-gate failures
* fail reason
* discriminator hits and misses
* section and label overlap scores

## Non-goals

This directory does **not** own:

* live product scraping
* runtime pipeline orchestration
* LLM prompting
* direct publish behavior
* ad hoc manual data fixes inside runtime artifacts

Those belong elsewhere in the repo.

## Directory relationship


`tools/schema_registry/`
`resources/templates/electronet/`
`resources/schemas/`
`docs/audits/`


Interpretation:

* `tools/schema_registry/` = tooling
* `resources/templates/electronet/` = editable templates
* `resources/schemas/` = compiled runtime outputs
* `docs/audits/` = human-readable coverage/audit reports

## Future extensions

Likely future improvements:

* fingerprint verification
* CI validation
* machine-readable coverage output
* multi-source template registries beyond Electronet
* compiler support for richer runtime matching metadata

