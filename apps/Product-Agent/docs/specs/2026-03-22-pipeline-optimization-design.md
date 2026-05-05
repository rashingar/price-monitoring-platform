# Pipeline Optimization Design Spec

Historical note:
- This spec was written before the later support-asset relocation milestones.
- Asset names such as `catalog_taxonomy.json`, `master_prompt+.txt`, `compact_response.schema.json`, and `name_rules.json` refer to their pre-M6 naming/location context unless an updated implementation note says otherwise.
- Paths such as `scrapper/` and package names such as `electronet_single_import` refer to the pre-M23 runtime layout.

## Context

The Product-Agent pipeline scrapes product pages from Electronet and Skroutz, enriches them via LLM, and outputs OpenCart-ready CSV files. While scraping works, the output quality doesn't match the live catalog standard (222-product sample). Key gaps: inconsistent product naming beyond 4 hardcoded Skroutz families, LLM-dependent CTA text with Greek gender errors, freeform meta_descriptions that miss the catalog's structured pattern, and no tool to measure quality gaps systematically.

## Goals

1. **Deterministic CTA** with correct Greek grammatical gender
2. **Template-based meta_description** with LLM grammar polish only
3. **Data-driven product naming** covering all categories, with LLM readability polish
4. **Catalog diffing tool** for quality measurement
5. **Reduce LLM token usage** by ~30-40%

---

## Change 1: Deterministic CTA with Gender Metadata

### Data: `catalog_taxonomy.json`

Add `gender_map` section at root level:

```json
{
  "gender_map": {
    "Τηλεοράσεις": {"gender": "fem", "plural_label": "Τηλεοράσεις"},
    "Πλυντήρια Ρούχων": {"gender": "neut", "plural_label": "Πλυντήρια Ρούχων"},
    "Εστίες": {"gender": "fem", "plural_label": "Εστίες"},
    "Sound Bars": {"gender": "fem", "plural_label": "Sound Bars"},
    "Ψυγεία": {"gender": "neut", "plural_label": "Ψυγεία"},
    "Κλιματιστικά": {"gender": "neut", "plural_label": "Κλιματιστικά"}
  }
}
```

Lookup order: `sub_category` -> `leaf_category` -> fallback neuter "Δείτε περισσότερα εδώ".

### Model: `models.py`

Add to `TaxonomyResolution`:
```python
gender: str = ""
plural_label: str = ""
```

### Taxonomy: `taxonomy.py`

After resolving taxonomy, populate `gender` and `plural_label` from `gender_map`.

### CTA Builder: `html_builders.py`

New function:
```python
GENDER_SUFFIX = {"fem": "ες", "neut": "α", "masc": "ους"}

def build_deterministic_cta(gender: str, plural_label: str) -> str:
    suffix = GENDER_SUFFIX.get(gender, "α")
    if not plural_label:
        return "Δείτε περισσότερα εδώ"
    return f"Δείτε περισσότερ{suffix} {plural_label} εδώ"
```

### Remove from LLM: `llm_contract.py`, `master_prompt+.txt`, `compact_response.schema.json`

- Remove `cta_text` from `llm_owned_fields`
- Remove `cta_rule` and `cta_target_label` from `writer_rules`
- Remove `cta_text` from LLM output shape and schema
- Update `validate_llm_output()`: expected presentation keys become `{"intro_html", "sections"}`

### Wiring: `mapping.py`

Replace `cta_text=str(llm_presentation.get("cta_text", ""))` with deterministic CTA from taxonomy.

---

## Change 2: Meta Description -- Template + LLM Grammar Polish

### Builder: `deterministic_fields.py`

New function:
```python
ARTICLE_MAP = {"fem": "Η", "neut": "Το", "masc": "Ο"}

def build_meta_description_draft(
    brand: str, mpn: str, category_phrase: str,
    gender: str, key_differentiators: list[str],
) -> str:
    article = ARTICLE_MAP.get(gender, "Το")
    specs = ", ".join(key_differentiators[:4])
    draft = f"{article} {brand} {mpn} είναι {category_phrase}"
    if specs:
        draft += f" με {specs}"
    return draft + "."
```

### LLM Context: `llm_contract.py`

Pass `meta_description_draft` in `deterministic_product` dict (flows automatically).

### Prompt: `master_prompt+.txt`

Change `meta_description` rule to:
```
- `meta_description`: Smooth the Greek grammar of `deterministic_product.meta_description_draft`.
  Keep all facts. Fix article agreement and natural phrasing. Exactly one sentence.
```

---

## Change 3: Product Name -- Data-Driven Rules + LLM Polish

### New Data File: `name_rules.json`

```json
{
  "rules": [
    {
      "match": {"leaf_category": "Τηλεοράσεις"},
      "category_phrase": "Τηλεόραση",
      "differentiator_specs": ["Ίντσες", "Ανάλυση", "Τεχνολογία Οθόνης"],
      "format_rules": {"Ίντσες": "{value}\""}
    },
    {
      "match": {"sub_category": "Sound Bars"},
      "category_phrase": "Soundbar",
      "differentiator_specs": ["Κανάλια", "Subwoofer"]
    },
    {
      "match": {"sub_category": "Πλυντήρια Ρούχων"},
      "category_phrase": "Πλυντήριο Ρούχων",
      "differentiator_specs": ["Χωρητικότητα", "Στροφές", "Ενεργειακή Κλάση"]
    }
  ],
  "default": {
    "differentiator_specs": ["Χωρητικότητα", "Ισχύς", "Χρώμα"],
    "format_rules": {}
  }
}
```

Each rule matches by `sub_category` and/or `leaf_category`. Covers all ~50+ categories from the catalog.

### Refactor: `deterministic_fields.py`

- Replace `build_skroutz_deterministic_fields()` 4-family hardcoded branches with `name_rules.json` lookup
- Unify electronet and skroutz name building into one data-driven flow
- Add `name_draft_tail` to returned dict (the part after `{brand} {mpn} --`)
- Existing `compose_name()`, `build_spec_lookup()`, `extract_mpn_from_name()` stay unchanged

### LLM: Add `name_tail_polished` field

- Add to LLM output shape in `master_prompt+.txt`
- Add to `compact_response.schema.json`
- Add validation in `validate_llm_output()`
- Rule: "Polish the name tail. Keep all technical details. Only improve Greek readability. Max 8 words."

### Render: `mapping.py`

After getting LLM output, reconstruct name:
```python
polished_tail = llm_product.get("name_tail_polished", "")
if polished_tail:
    name = f"{brand} {mpn} – {polished_tail}"
else:
    name = deterministic["name"]  # fallback
```

---

## Change 4: Catalog Diffing Tool

### New File: `tools/catalog_diff.py`

CLI tool:
```
python tools/catalog_diff.py --catalog-csv catalog_2026_plus.csv --candidate-dir products/ --output diff_report.json
```

### Comparison Fields

| Field | Method |
|-------|--------|
| `name` | Exact match + Levenshtein distance + structural check (brand+mpn prefix) |
| `meta_description` | Length diff, keyword overlap ratio |
| `category` | Exact path match |
| `characteristics` | Section count, missing spec labels |
| CTA text | Extract from description HTML, exact match |

### Output

JSON report with:
- Total catalog vs matched vs missing counts
- Per-field match statistics (exact/close/different)
- Per-product field-by-field comparison
- Overall quality score

---

## Files Modified

| File | Change |
|------|--------|
| `catalog_taxonomy.json` | Add `gender_map` section |
| `models.py:206-216` | Add `gender`, `plural_label` to `TaxonomyResolution` |
| `taxonomy.py` | Populate gender/plural_label during resolve |
| `html_builders.py:17-27` | Replace `resolve_cta_text()` with `build_deterministic_cta()` |
| `deterministic_fields.py` | Add `build_meta_description_draft()`, refactor name building to use `name_rules.json`, add `name_draft_tail` |
| `llm_contract.py:55-71` | Remove cta_text, add name_tail_polished, update writer_rules |
| `llm_contract.py:83-160` | Update `validate_llm_output()` expected shapes |
| `master_prompt+.txt` | Update LLM output shape, field rules |
| `compact_response.schema.json` | Add name_tail_polished, remove cta_text |
| `mapping.py:44-161` | Wire deterministic CTA, polished name, meta_description_draft |
| **New:** `name_rules.json` | Per-category naming rules |
| **New:** `tools/catalog_diff.py` | Catalog comparison CLI tool |

## Verification

1. Run existing tests: `python -m pytest scrapper/electronet_single_import/tests/`
2. Process a sample product through prepare+render and compare with catalog
3. Run catalog diff tool against the 222-product sample
4. Verify CTA text gender agreement for 5+ different categories
5. Verify meta_description follows the template pattern
6. Verify product name second half quality vs catalog
