from product_factory.characteristics_pipeline import CharacteristicsTemplateRegistry
from product_factory.models import (
    SchemaMatchResult,
    SourceProductData,
    TaxonomyResolution,
)
from product_factory.repo_paths import SCHEMA_LIBRARY_PATH
from product_factory.utils import read_json


def _schema_id_for_source_file(source_file: str) -> str:
    payload = read_json(SCHEMA_LIBRARY_PATH)
    for schema in payload.get("schemas", []):
        if source_file in schema.get("source_files", []):
            schema_id = str(schema.get("schema_id", "")).strip()
            if schema_id:
                return schema_id
    raise AssertionError(f"Schema id not found for source file {source_file!r}.")


ROBOT_VACUUM_SCHEMA_ID = _schema_id_for_source_file("skoypes_rompot.json")
STEAM_CLEANER_SCHEMA_ID = _schema_id_for_source_file("atmokatharistes.json")
STICK_VACUUM_SCHEMA_ID = _schema_id_for_source_file("skoypes_stick.json")
FRYER_SCHEMA_ID = _schema_id_for_source_file("fritezes.json")


def test_characteristics_registry_prefers_robot_vacuum_schema_for_skroutz() -> None:
    registry = CharacteristicsTemplateRegistry()
    source = SourceProductData(source_name="skroutz", name="Rowenta Robot Vacuum")
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Σκούπισμα",
        sub_category="Σκούπες Ρομπότ",
    )

    preferred_source_files = registry.preferred_schema_source_files(source, taxonomy)
    template = registry.select_template(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=ROBOT_VACUUM_SCHEMA_ID, score=0.9
        ),
    )

    assert preferred_source_files == ["skoypes_rompot.json"]
    assert template is not None
    assert template["matched_schema_id"] == ROBOT_VACUUM_SCHEMA_ID
    assert template["preferred_schema_source_files"] == ["skoypes_rompot.json"]
    assert template["template_source"] == "schema_library_with_custom_overrides"
    assert template["custom_template_id"] == "skroutz_robot_vacuum_v1"


def test_characteristics_registry_prefers_steam_cleaner_schema_for_skroutz() -> None:
    registry = CharacteristicsTemplateRegistry()
    source = SourceProductData(source_name="skroutz", name="Ariete Steam Cleaner")
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Σκούπισμα",
        sub_category="Ατμοκαθαριστές",
    )

    preferred_source_files = registry.preferred_schema_source_files(source, taxonomy)
    template = registry.select_template(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=STEAM_CLEANER_SCHEMA_ID, score=0.9
        ),
    )

    assert preferred_source_files == ["atmokatharistes.json"]
    assert template is not None
    assert template["matched_schema_id"] == STEAM_CLEANER_SCHEMA_ID
    assert template["preferred_schema_source_files"] == ["atmokatharistes.json"]
    assert template["template_source"] == "custom"
    assert template["template_id"] == "skroutz_steam_cleaner_v1"


def test_characteristics_registry_prefers_stick_vacuum_schema_for_skroutz() -> None:
    registry = CharacteristicsTemplateRegistry()
    source = SourceProductData(source_name="skroutz", name="Rohnson Stick Vacuum")
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Σκούπισμα",
        sub_category="Σκούπες Stick",
    )

    preferred_source_files = registry.preferred_schema_source_files(source, taxonomy)
    template = registry.select_template(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=STICK_VACUUM_SCHEMA_ID, score=0.9
        ),
    )

    assert preferred_source_files == ["skoypes_stick.json"]
    assert template is not None
    assert template["matched_schema_id"] == STICK_VACUUM_SCHEMA_ID
    assert template["preferred_schema_source_files"] == ["skoypes_stick.json"]
    assert template["template_source"] == "schema_library_with_custom_overrides"
    assert template["custom_template_id"] == "skroutz_stick_vacuum_v1"


def test_characteristics_registry_prefers_fryer_schema_for_skroutz() -> None:
    registry = CharacteristicsTemplateRegistry()
    source = SourceProductData(source_name="skroutz", name="Taurus Fry 3")
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Μικροί Μάγειρες",
        sub_category="Φριτέζες",
    )

    preferred_source_files = registry.preferred_schema_source_files(source, taxonomy)
    template = registry.select_template(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(matched_schema_id=FRYER_SCHEMA_ID, score=0.9),
    )

    assert preferred_source_files == ["fritezes.json"]
    assert template is not None
    assert template["matched_schema_id"] == FRYER_SCHEMA_ID
    assert template["preferred_schema_source_files"] == ["fritezes.json"]
    assert template["template_source"] == "schema_library_with_custom_overrides"
    assert template["custom_template_id"] == "skroutz_fryer_v1"
