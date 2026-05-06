from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RESOURCES_DIR = REPO_ROOT / "resources"
MAPPINGS_DIR = RESOURCES_DIR / "mappings"
SCHEMAS_DIR = RESOURCES_DIR / "schemas"
TEMPLATES_DIR = RESOURCES_DIR / "templates"
PROMPTS_DIR = RESOURCES_DIR / "prompts"
SETTINGS_DIR = RESOURCES_DIR / "settings"

PRODUCT_TEMPLATE_PATH = TEMPLATES_DIR / "product_import_template.csv"
PRESENTATION_TEMPLATE_PATH = TEMPLATES_DIR / "TEMPLATE_presentation.html"
CATALOG_TAXONOMY_PATH = MAPPINGS_DIR / "catalog_taxonomy.json"
SCHEMA_LIBRARY_PATH = SCHEMAS_DIR / "electronet_schema_library.json"
CHARACTERISTICS_TEMPLATES_PATH = TEMPLATES_DIR / "characteristics_templates.json"
FILTER_MAP_PATH = MAPPINGS_DIR / "filter_map.json"
FILTER_MAP_BASE_PATH = MAPPINGS_DIR / "filter_map.base.json"
FILTER_MAP_MANUAL_OVERRIDES_PATH = MAPPINGS_DIR / "filter_map.manual_overrides.json"
FILTER_MAP_MANUAL_OVERRIDES_BACKUP_DIR = MAPPINGS_DIR / "backups" / "filter_overrides"
FILTER_MAP_SYNC_REPORT_PATH = MAPPINGS_DIR / "filter_map.sync_report.json"
LABEL_ALIASES_PATH = MAPPINGS_DIR / "label_aliases.json"
FULL_CATALOG_WITH_FILTERS_PATH = MAPPINGS_DIR / "full_catalog_with_filters.csv"
NAME_RULES_PATH = MAPPINGS_DIR / "name_rules.json"
SCHEMA_POLICY_RULES_PATH = MAPPINGS_DIR / "schema_policy_rules.json"
DIFFERENTIATOR_PRIORITY_MAP_PATH = MAPPINGS_DIR / "differentiator_priority_map.csv"
INTRO_TEXT_PROMPT_PATH = PROMPTS_DIR / "intro_text_prompt.txt"
SEO_META_PROMPT_PATH = PROMPTS_DIR / "seo_meta_prompt.txt"
PRODUCT_FACTORY_SETTINGS_PATH = SETTINGS_DIR / "product_factory_settings.json"
MANUFACTURER_SOURCE_MAP_PATH = MAPPINGS_DIR / "MANUFACTURER_SOURCE_MAP.json"
SCHEMA_INDEX_PATH = SCHEMAS_DIR / "schema_index.csv"
TAXONOMY_MAPPING_TEMPLATE_PATH = MAPPINGS_DIR / "taxonomy_mapping_template.csv"


def model_root_path(model: str, *, repo_root: Path | None = None) -> Path:
    return (repo_root or REPO_ROOT) / "work" / model


def category_filter_review_dir(model: str, *, repo_root: Path | None = None) -> Path:
    return model_root_path(model, repo_root=repo_root) / "review"


def category_filter_review_path(model: str, *, repo_root: Path | None = None) -> Path:
    return category_filter_review_dir(model, repo_root=repo_root) / "category_filters.override.json"


def category_filter_review_path_for_model_root(model_root: Path) -> Path:
    return model_root / "review" / "category_filters.override.json"
