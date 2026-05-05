from __future__ import annotations

import pytest

from pipeline.models import SpecItem, SpecSection
from pipeline.normalize import normalize_for_match
from pipeline.repo_paths import SCHEMA_LIBRARY_PATH
from pipeline.schema_matcher import SchemaMatcher
from pipeline.utils import read_json


_PAYLOAD = read_json(SCHEMA_LIBRARY_PATH)
_SCHEMAS_BY_TEMPLATE_ID = {
    str(schema["template_id"]): schema
    for schema in _PAYLOAD["schemas"]
}


def _schema(template_id: str) -> dict[str, object]:
    return _SCHEMAS_BY_TEMPLATE_ID[template_id]


def _spec_sections_from_schema(
    schema: dict[str, object],
    *,
    section_count: int | None = None,
    labels_per_section: int | None = None,
) -> list[SpecSection]:
    raw_sections = schema.get("sections", [])
    max_sections = section_count or max(int(schema.get("min_section_overlap") or 0), 2)
    sections: list[SpecSection] = []
    total_labels = 0
    target_labels = max(int(schema.get("min_label_overlap") or 0), 4)

    for raw_section in raw_sections[:max_sections]:
        title = str(raw_section.get("title", "")).strip()
        labels = [str(label).strip() for label in raw_section.get("labels", []) if str(label).strip()]
        if not title or not labels:
            continue
        limit = labels_per_section or max(2, min(len(labels), target_labels))
        chosen_labels = labels[:limit]
        sections.append(
            SpecSection(
                section=title,
                items=[SpecItem(label=label, value="fixture") for label in chosen_labels],
            )
        )
        total_labels += len(chosen_labels)
        if total_labels >= target_labels:
            break

    return sections


def _spec_sections_for_exact_labels(schema: dict[str, object], labels: list[str]) -> list[SpecSection]:
    normalized_targets = {normalize_for_match(label) for label in labels if normalize_for_match(label)}
    sections: list[SpecSection] = []
    for raw_section in schema.get("sections", []):
        title = str(raw_section.get("title", "")).strip()
        matched_labels = [
            str(label).strip()
            for label in raw_section.get("labels", [])
            if normalize_for_match(label) in normalized_targets
        ]
        if title and matched_labels:
            sections.append(
                SpecSection(
                    section=title,
                    items=[SpecItem(label=label, value="fixture") for label in matched_labels],
                )
            )
    return sections


def _labels_matching(schema: dict[str, object], *tokens: str) -> list[str]:
    desired = [normalize_for_match(token) for token in tokens if normalize_for_match(token)]
    labels: list[str] = []
    for label in schema.get("label_set_exact", []):
        normalized = normalize_for_match(label)
        if any(token in normalized for token in desired):
            labels.append(str(label))
    return labels


@pytest.mark.parametrize(
    "template_id",
    [
        "tileoraseis",
        "koyzines",
        "plyntiria_piaton",
        "entoixizomena_plyntiria_piaton",
        "plyntiria_rouxwn",
        "entoixizomena_plyntiria_royxon",
        "entoixizomena_psygeia",
    ],
)
def test_compiled_library_direct_single_regressions_select_resolved_family(template_id: str) -> None:
    schema = _schema(template_id)
    matcher = SchemaMatcher()

    result, candidates = matcher.match(
        _spec_sections_from_schema(schema),
        taxonomy_sub_category=schema.get("sub_category"),
        taxonomy_path=str(schema.get("category_path", "")),
        taxonomy_parent_category=schema.get("parent_category"),
        taxonomy_leaf_category=schema.get("leaf_category"),
    )

    assert result.selected_template_id == template_id
    assert result.matched_schema_id == schema["schema_id"]
    assert result.match_mode == "direct_single"
    assert result.fail_reason == ""
    assert result.candidate_pool_size == 1
    assert result.candidate_template_ids == [template_id]
    assert candidates[0]["matched_schema_id"] == schema["schema_id"]
    assert candidates[0]["gate_status"] == "bypassed_direct_single"


def test_compiled_library_generic_washing_machine_labels_cannot_escape_resolved_family() -> None:
    washing_machine = _schema("plyntiria_rouxwn")
    matcher = SchemaMatcher()
    generic_labels = _labels_matching(
        washing_machine,
        "εγγυηση",
        "διαστασ",
        "βαρος",
        "ενεργειακη κλαση",
    )
    spec_sections = _spec_sections_for_exact_labels(washing_machine, generic_labels[:4])

    result, candidates = matcher.match(
        spec_sections,
        taxonomy_sub_category=washing_machine.get("sub_category"),
        taxonomy_path=str(washing_machine.get("category_path", "")),
        taxonomy_parent_category=washing_machine.get("parent_category"),
        taxonomy_leaf_category=washing_machine.get("leaf_category"),
    )

    assert result.selected_template_id == "plyntiria_rouxwn"
    assert result.fail_reason == ""
    assert result.candidate_template_ids == ["plyntiria_rouxwn"]
    assert result.selected_template_id not in {"koyzines", "isiotika_mallion", "voyrtses_psalidia_isiotika"}
    assert {candidate["template_id"] for candidate in candidates} == {"plyntiria_rouxwn"}


def test_compiled_library_tv_leaf_family_policy_supports_subcategory_fallback() -> None:
    tv_schema = _schema("tileoraseis")
    matcher = SchemaMatcher()

    result, candidates = matcher.match(
        _spec_sections_from_schema(tv_schema),
        taxonomy_sub_category="50'' & άνω",
        taxonomy_path="ΕΙΚΟΝΑ & ΗΧΟΣ > Τηλεοράσεις > 50'' & άνω",
        taxonomy_parent_category=tv_schema.get("parent_category"),
        taxonomy_leaf_category=tv_schema.get("leaf_category"),
    )

    assert tv_schema["subcategory_match_policy"] == "leaf_family"
    assert result.selected_template_id == "tileoraseis"
    assert result.matched_schema_id == tv_schema["schema_id"]
    assert result.subcategory_match_policy == "leaf_family"
    assert result.fail_reason == ""
    assert result.candidate_pool_size == 1
    assert result.candidate_template_ids == ["tileoraseis"]
    assert {candidate["template_id"] for candidate in candidates} == {"tileoraseis"}
    assert candidates[0]["subcategory_match_policy"] == "leaf_family"


def test_compiled_library_emits_mixed_family_for_air_conditioners_and_fans() -> None:
    assert _schema("klimatistika")["subcategory_match_policy"] == "mixed_family"
    assert _schema("toixoy")["subcategory_match_policy"] == "mixed_family"
    assert _schema("forita")["subcategory_match_policy"] == "mixed_family"
    assert _schema("ntoylapes")["subcategory_match_policy"] == "mixed_family"
    assert _schema("anemistires")["subcategory_match_policy"] == "mixed_family"
    assert _schema("mini")["subcategory_match_policy"] == "mixed_family"
    assert _schema("ydronefosis")["subcategory_match_policy"] == "mixed_family"
    assert _schema("orthostatis")["subcategory_match_policy"] == "mixed_family"
    assert _schema("epitrapezioi")["subcategory_match_policy"] == "mixed_family"
    assert _schema("orofis")["subcategory_match_policy"] == "mixed_family"
    assert _schema("air_coolers_epidapedioi")["subcategory_match_policy"] == "mixed_family"
    assert _schema("anemisthres_an_toixou")["subcategory_match_policy"] == "mixed_family"


def test_compiled_library_mixed_family_exact_pool_wins_for_air_conditioners() -> None:
    wall_mounted = _schema("toixoy")
    matcher = SchemaMatcher()

    result, candidates = matcher.match(
        _spec_sections_from_schema(wall_mounted),
        taxonomy_sub_category=wall_mounted.get("sub_category"),
        taxonomy_path=str(wall_mounted.get("category_path", "")),
        taxonomy_parent_category=wall_mounted.get("parent_category"),
        taxonomy_leaf_category=wall_mounted.get("leaf_category"),
    )

    assert result.selected_template_id == "toixoy"
    assert result.matched_schema_id == wall_mounted["schema_id"]
    assert result.subcategory_match_policy == "mixed_family"
    assert result.candidate_pool_size == 1
    assert result.candidate_template_ids == ["toixoy"]
    assert {candidate["template_id"] for candidate in candidates} == {"toixoy"}


def test_compiled_library_mixed_family_allows_leaf_fallback_for_air_conditioners_when_exact_missing() -> None:
    air_conditioners = _schema("klimatistika")
    matcher = SchemaMatcher()

    result, candidates = matcher.match(
        _spec_sections_from_schema(air_conditioners),
        taxonomy_sub_category="Κασέτα",
        taxonomy_path="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ > Κλιματιστικά > Κασέτα",
        taxonomy_parent_category=air_conditioners.get("parent_category"),
        taxonomy_leaf_category=air_conditioners.get("leaf_category"),
    )

    assert result.selected_template_id == "klimatistika"
    assert result.matched_schema_id == air_conditioners["schema_id"]
    assert result.subcategory_match_policy == "mixed_family"
    assert result.fail_reason == ""
    assert result.candidate_pool_size == 1
    assert result.candidate_template_ids == ["klimatistika"]
    assert {candidate["template_id"] for candidate in candidates} == {"klimatistika"}
    assert candidates[0]["subcategory_match_policy"] == "mixed_family"


def test_compiled_library_kitchen_specs_cannot_override_washing_machine_category_binding() -> None:
    washing_machine = _schema("plyntiria_rouxwn")
    kitchen = _schema("koyzines")
    matcher = SchemaMatcher()

    result, candidates = matcher.match(
        _spec_sections_from_schema(kitchen, section_count=2, labels_per_section=3),
        taxonomy_sub_category=washing_machine.get("sub_category"),
        taxonomy_path=str(washing_machine.get("category_path", "")),
        taxonomy_parent_category=washing_machine.get("parent_category"),
        taxonomy_leaf_category=washing_machine.get("leaf_category"),
    )

    assert result.selected_template_id == "plyntiria_rouxwn"
    assert result.fail_reason == ""
    assert result.candidate_template_ids == ["plyntiria_rouxwn"]
    assert {candidate["template_id"] for candidate in candidates} == {"plyntiria_rouxwn"}


def test_compiled_library_non_exception_subcategory_family_remains_exact() -> None:
    washing_machine = _schema("plyntiria_rouxwn")

    assert washing_machine["subcategory_match_policy"] == "exact_subcategory"
