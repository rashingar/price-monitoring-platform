import json

from product_factory.repo_paths import (
    CATALOG_TAXONOMY_PATH,
    CHARACTERISTICS_TEMPLATES_PATH,
    DIFFERENTIATOR_PRIORITY_MAP_PATH,
    FILTER_MAP_BASE_PATH,
    FILTER_MAP_MANUAL_OVERRIDES_PATH,
    FILTER_MAP_PATH,
    FILTER_MAP_SYNC_REPORT_PATH,
    FULL_CATALOG_WITH_FILTERS_PATH,
    INTRO_TEXT_PROMPT_PATH,
    MANUFACTURER_SOURCE_MAP_PATH,
    NAME_RULES_PATH,
    PRESENTATION_TEMPLATE_PATH,
    PRODUCT_TEMPLATE_PATH,
    REPO_ROOT,
    SCHEMA_LIBRARY_PATH,
    SCHEMA_INDEX_PATH,
    SCHEMA_POLICY_RULES_PATH,
    SEO_META_PROMPT_PATH,
    TAXONOMY_MAPPING_TEMPLATE_PATH,
)


def test_support_files_resolve_from_resources_layout() -> None:
    assert REPO_ROOT.name == "product-factory-api"
    expected_paths = [
        (PRODUCT_TEMPLATE_PATH, REPO_ROOT / "resources" / "templates" / "product_import_template.csv"),
        (PRESENTATION_TEMPLATE_PATH, REPO_ROOT / "resources" / "templates" / "TEMPLATE_presentation.html"),
        (CATALOG_TAXONOMY_PATH, REPO_ROOT / "resources" / "mappings" / "catalog_taxonomy.json"),
        (SCHEMA_LIBRARY_PATH, REPO_ROOT / "resources" / "schemas" / "electronet_schema_library.json"),
        (
            CHARACTERISTICS_TEMPLATES_PATH,
            REPO_ROOT / "resources" / "templates" / "characteristics_templates.json",
        ),
        (FILTER_MAP_PATH, REPO_ROOT / "resources" / "mappings" / "filter_map.json"),
        (FILTER_MAP_BASE_PATH, REPO_ROOT / "resources" / "mappings" / "filter_map.base.json"),
        (
            FILTER_MAP_MANUAL_OVERRIDES_PATH,
            REPO_ROOT / "resources" / "mappings" / "filter_map.manual_overrides.json",
        ),
        (
            FILTER_MAP_SYNC_REPORT_PATH,
            REPO_ROOT / "resources" / "mappings" / "filter_map.sync_report.json",
        ),
        (
            FULL_CATALOG_WITH_FILTERS_PATH,
            REPO_ROOT / "resources" / "mappings" / "full_catalog_with_filters.csv",
        ),
        (NAME_RULES_PATH, REPO_ROOT / "resources" / "mappings" / "name_rules.json"),
        (
            SCHEMA_POLICY_RULES_PATH,
            REPO_ROOT / "resources" / "mappings" / "schema_policy_rules.json",
        ),
        (
            DIFFERENTIATOR_PRIORITY_MAP_PATH,
            REPO_ROOT / "resources" / "mappings" / "differentiator_priority_map.csv",
        ),
        (INTRO_TEXT_PROMPT_PATH, REPO_ROOT / "resources" / "prompts" / "intro_text_prompt.txt"),
        (SEO_META_PROMPT_PATH, REPO_ROOT / "resources" / "prompts" / "seo_meta_prompt.txt"),
        (
            MANUFACTURER_SOURCE_MAP_PATH,
            REPO_ROOT / "resources" / "mappings" / "MANUFACTURER_SOURCE_MAP.json",
        ),
        (SCHEMA_INDEX_PATH, REPO_ROOT / "resources" / "schemas" / "schema_index.csv"),
        (
            TAXONOMY_MAPPING_TEMPLATE_PATH,
            REPO_ROOT / "resources" / "mappings" / "taxonomy_mapping_template.csv",
        ),
    ]
    for actual_path, expected_path in expected_paths:
        assert actual_path == expected_path
        if actual_path != FULL_CATALOG_WITH_FILTERS_PATH:
            assert actual_path.exists()


def test_filter_map_uses_object_style_category_filters() -> None:
    filter_map = json.loads(FILTER_MAP_PATH.read_text(encoding="utf-8"))
    rows_with_filters = [row for row in filter_map["subcategories"] if row["filter_groups"]]

    assert rows_with_filters
    for row in rows_with_filters[:10]:
        assert all(isinstance(group, dict) for group in row["filter_groups"])
        assert all({"group_id", "name", "required", "status", "values"} <= set(group) for group in row["filter_groups"])
