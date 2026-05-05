import json
from pathlib import Path

from pipeline.models import SpecItem, SpecSection
from pipeline.normalize import normalize_for_match
from pipeline.schema_matcher import SchemaMatcher


def _write_schema_library(tmp_path: Path, schemas: list[dict[str, object]]) -> Path:
    path = tmp_path / "schema_library.json"
    path.write_text(json.dumps({"schemas": schemas}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _schema(
    *,
    schema_id: str,
    template_id: str,
    category_path: str,
    parent_category: str,
    leaf_category: str,
    sub_category: str | None,
    sections: list[tuple[str, list[str]]],
    template_status: str = "active",
    match_mode: str = "direct_single",
    subcategory_match_policy: str = "exact_subcategory",
    sibling_template_ids: list[str] | None = None,
    required_labels_any: list[str] | None = None,
    required_labels_all: list[str] | None = None,
    forbidden_labels: list[str] | None = None,
    min_section_overlap: int = 1,
    min_label_overlap: int = 1,
) -> dict[str, object]:
    label_set_exact = _preserve_order([label for _section, labels in sections for label in labels])
    section_names_normalized = [normalize_for_match(section) for section, _labels in sections]
    label_set_normalized = [normalize_for_match(label) for label in label_set_exact]
    section_label_pairs_normalized = _preserve_order(
        [
            normalize_for_match(f"{section} || {label}")
            for section, labels in sections
            for label in labels
        ]
    )
    return {
        "schema_id": schema_id,
        "template_id": template_id,
        "category_path": category_path,
        "parent_category": parent_category,
        "leaf_category": leaf_category,
        "sub_category": sub_category,
        "template_status": template_status,
        "match_mode": match_mode,
        "subcategory_match_policy": subcategory_match_policy,
        "section_names_exact": [section for section, _labels in sections],
        "section_names_normalized": section_names_normalized,
        "label_set_exact": label_set_exact,
        "label_set_normalized": label_set_normalized,
        "section_label_pairs_normalized": section_label_pairs_normalized,
        "discriminator_labels": [],
        "required_labels_any": [normalize_for_match(label) for label in (required_labels_any or [])],
        "required_labels_all": [normalize_for_match(label) for label in (required_labels_all or [])],
        "forbidden_labels": [normalize_for_match(label) for label in (forbidden_labels or [])],
        "min_section_overlap": min_section_overlap,
        "min_label_overlap": min_label_overlap,
        "sibling_template_ids": list(sibling_template_ids or []),
        "n_sections": len(sections),
        "n_rows_total": sum(len(labels) for _section, labels in sections),
        "sections": [{"title": section, "labels": labels} for section, labels in sections],
        "sentinel": {},
        "source_files": [f"{template_id}.json"],
    }


def _spec_sections(*sections: tuple[str, list[str]]) -> list[SpecSection]:
    return [
        SpecSection(section=section, items=[SpecItem(label=label, value="x") for label in labels])
        for section, labels in sections
    ]


def test_direct_single_category_selects_only_active_safe_template(tmp_path: Path) -> None:
    schema_path = _write_schema_library(
        tmp_path,
        [
            _schema(
                schema_id="wm-1",
                template_id="washing_machine_active",
                category_path="Home > Laundry > Washing Machines",
                parent_category="Home",
                leaf_category="Laundry",
                sub_category="Washing Machines",
                sections=[
                    ("Overview", ["Capacity", "Spin Speed"]),
                    ("Programs", ["Steam Program", "Delay End"]),
                ],
                min_section_overlap=1,
                min_label_overlap=2,
            ),
            _schema(
                schema_id="wm-manual",
                template_id="washing_machine_manual",
                category_path="Home > Laundry > Washing Machines",
                parent_category="Home",
                leaf_category="Laundry",
                sub_category="Washing Machines",
                sections=[("TODO", ["Needs Manual Labels"])],
                template_status="manual_only",
                match_mode="manual_only",
            ),
            _schema(
                schema_id="wm-deprecated",
                template_id="washing_machine_deprecated",
                category_path="Home > Laundry > Washing Machines",
                parent_category="Home",
                leaf_category="Laundry",
                sub_category="Washing Machines",
                sections=[("Overview", ["Old Capacity"])],
                template_status="deprecated",
                match_mode="manual_only",
            ),
            _schema(
                schema_id="toaster-1",
                template_id="toaster",
                category_path="Home > Small Appliances > Toasters",
                parent_category="Home",
                leaf_category="Small Appliances",
                sub_category="Toasters",
                sections=[("Overview", ["Slots", "Power"])],
            ),
        ],
    )
    matcher = SchemaMatcher(str(schema_path))

    result, candidates = matcher.match(
        _spec_sections(
            ("Overview", ["Capacity", "Spin Speed"]),
            ("Programs", ["Steam Program", "Delay End"]),
        ),
        taxonomy_sub_category="Washing Machines",
        taxonomy_path="Home > Laundry > Washing Machines",
        taxonomy_parent_category="Home",
        taxonomy_leaf_category="Laundry",
    )

    assert result.matched_schema_id == "wm-1"
    assert result.score == 1.0
    assert "weak_schema_match" not in result.warnings
    assert result.resolved_category_path == "Home > Laundry > Washing Machines"
    assert result.subcategory_match_policy == "exact_subcategory"
    assert result.candidate_pool_size == 3
    assert result.candidate_template_ids == [
        "washing_machine_active",
        "washing_machine_manual",
        "washing_machine_deprecated",
    ]
    assert result.selected_template_id == "washing_machine_active"
    assert result.match_mode == "direct_single"
    assert result.fail_reason == ""
    assert result.section_overlap_score == 1.0
    assert result.label_overlap_score == 1.0
    assert candidates == [
        {
            "matched_schema_id": "wm-1",
            "template_id": "washing_machine_active",
            "matched_sub_category": "Washing Machines",
            "category_path": "Home > Laundry > Washing Machines",
            "template_status": "active",
            "match_mode": "direct_single",
            "subcategory_match_policy": "exact_subcategory",
            "score": 1.0,
            "section_overlap": 2,
            "label_overlap": 4,
            "section_overlap_score": 1.0,
            "label_overlap_score": 1.0,
            "pair_overlap": 4,
            "discriminator_overlap": 0,
            "discriminator_hits": [],
            "discriminator_misses": [],
            "gate_status": "bypassed_direct_single",
            "gate_reasons": [],
            "n_sections": 2,
            "n_rows_total": 4,
            "source_files": ["washing_machine_active.json"],
        }
    ]


def test_category_pool_compares_only_sibling_templates(tmp_path: Path) -> None:
    schema_path = _write_schema_library(
        tmp_path,
        [
            _schema(
                schema_id="kettle-basic",
                template_id="kettle_basic",
                category_path="Home > Small Appliances > Kettles",
                parent_category="Home",
                leaf_category="Small Appliances",
                sub_category="Kettles",
                sections=[
                    ("Overview", ["Capacity", "Power", "Color"]),
                    ("Features", ["Cordless"]),
                ],
                match_mode="category_pool",
                sibling_template_ids=["kettle_glass"],
                required_labels_any=["Capacity"],
                min_section_overlap=1,
                min_label_overlap=2,
            ),
            _schema(
                schema_id="kettle-glass",
                template_id="kettle_glass",
                category_path="Home > Small Appliances > Kettles",
                parent_category="Home",
                leaf_category="Small Appliances",
                sub_category="Kettles",
                sections=[
                    ("Overview", ["Capacity", "Power", "Color"]),
                    ("Features", ["Glass Body", "Temperature Control"]),
                ],
                match_mode="category_pool",
                sibling_template_ids=["kettle_basic"],
                required_labels_any=["Capacity"],
                min_section_overlap=1,
                min_label_overlap=2,
            ),
            _schema(
                schema_id="toaster-1",
                template_id="toaster",
                category_path="Home > Small Appliances > Toasters",
                parent_category="Home",
                leaf_category="Small Appliances",
                sub_category="Toasters",
                sections=[
                    ("Overview", ["Power", "Color", "Crumb Tray"]),
                    ("Features", ["Defrost"]),
                ],
                min_section_overlap=1,
                min_label_overlap=2,
            ),
        ],
    )
    matcher = SchemaMatcher(str(schema_path))

    result, candidates = matcher.match(
        _spec_sections(
            ("Overview", ["Capacity", "Power", "Color"]),
            ("Features", ["Glass Body", "Temperature Control"]),
        ),
        taxonomy_sub_category="Kettles",
        taxonomy_path="Home > Small Appliances > Kettles",
        taxonomy_parent_category="Home",
        taxonomy_leaf_category="Small Appliances",
    )

    assert result.matched_schema_id == "kettle-glass"
    assert result.selected_template_id == "kettle_glass"
    assert result.match_mode == "category_pool"
    assert result.resolved_category_path == "Home > Small Appliances > Kettles"
    assert result.candidate_pool_size == 2
    assert result.candidate_template_ids == ["kettle_basic", "kettle_glass"]
    assert {candidate["matched_schema_id"] for candidate in candidates} == {"kettle-basic", "kettle-glass"}
    assert all(candidate["category_path"] == "Home > Small Appliances > Kettles" for candidate in candidates)


def test_wrong_category_schema_cannot_be_selected(tmp_path: Path) -> None:
    schema_path = _write_schema_library(
        tmp_path,
        [
            _schema(
                schema_id="wm-1",
                template_id="washing_machine_active",
                category_path="Home > Laundry > Washing Machines",
                parent_category="Home",
                leaf_category="Laundry",
                sub_category="Washing Machines",
                sections=[
                    ("Overview", ["Capacity", "Spin Speed"]),
                    ("Programs", ["Steam Program", "Delay End"]),
                ],
                required_labels_any=["Capacity"],
                min_section_overlap=1,
                min_label_overlap=2,
            ),
            _schema(
                schema_id="kettle-basic",
                template_id="kettle_basic",
                category_path="Home > Small Appliances > Kettles",
                parent_category="Home",
                leaf_category="Small Appliances",
                sub_category="Kettles",
                sections=[
                    ("Overview", ["Capacity", "Power", "Color"]),
                    ("Features", ["Cordless"]),
                ],
                match_mode="category_pool",
                sibling_template_ids=["kettle_glass"],
                required_labels_any=["Capacity"],
                min_section_overlap=1,
                min_label_overlap=2,
            ),
            _schema(
                schema_id="kettle-glass",
                template_id="kettle_glass",
                category_path="Home > Small Appliances > Kettles",
                parent_category="Home",
                leaf_category="Small Appliances",
                sub_category="Kettles",
                sections=[
                    ("Overview", ["Capacity", "Power", "Color"]),
                    ("Features", ["Glass Body", "Temperature Control"]),
                ],
                match_mode="category_pool",
                sibling_template_ids=["kettle_basic"],
                required_labels_any=["Capacity"],
                min_section_overlap=1,
                min_label_overlap=2,
            ),
        ],
    )
    matcher = SchemaMatcher(str(schema_path))

    result, candidates = matcher.match(
        _spec_sections(
            ("Overview", ["Spin Speed", "Drum Size"]),
            ("Programs", ["Steam Program", "Delay End"]),
        ),
        taxonomy_sub_category="Kettles",
        taxonomy_path="Home > Small Appliances > Kettles",
        taxonomy_parent_category="Home",
        taxonomy_leaf_category="Small Appliances",
    )

    assert result.matched_schema_id is None
    assert result.warnings == ["no_safe_template_match"]
    assert result.fail_reason == "discriminator_miss"
    assert result.selected_template_id is None
    assert result.candidate_template_ids == ["kettle_basic", "kettle_glass"]
    assert result.hard_gate_failures == [
        {"template_id": "kettle_basic", "gate_reasons": ["missing_required_labels_any", "min_label_overlap"]},
        {"template_id": "kettle_glass", "gate_reasons": ["missing_required_labels_any", "min_label_overlap"]},
    ]
    assert {candidate["matched_schema_id"] for candidate in candidates} == {"kettle-basic", "kettle-glass"}
    assert "wm-1" not in {candidate["matched_schema_id"] for candidate in candidates}


def test_leaf_family_policy_allows_leaf_only_fallback_when_exact_subcategory_pool_is_absent(tmp_path: Path) -> None:
    schema_path = _write_schema_library(
        tmp_path,
        [
            _schema(
                schema_id="tv-leaf",
                template_id="tileoraseis",
                category_path="Electronics > TVs > -",
                parent_category="Electronics",
                leaf_category="TVs",
                sub_category=None,
                subcategory_match_policy="leaf_family",
                sections=[
                    ("Overview", ["Screen Size", "Panel Type", "HDR"]),
                    ("Connectivity", ["HDMI", "Wi-Fi"]),
                ],
                min_section_overlap=1,
                min_label_overlap=2,
            ),
            _schema(
                schema_id="audio-leaf",
                template_id="soundbars",
                category_path="Electronics > Audio > -",
                parent_category="Electronics",
                leaf_category="Audio",
                sub_category=None,
                subcategory_match_policy="leaf_family",
                sections=[("Overview", ["Power Output", "Bluetooth"])],
            ),
        ],
    )
    matcher = SchemaMatcher(str(schema_path))

    result, candidates = matcher.match(
        _spec_sections(
            ("Overview", ["Screen Size", "Panel Type", "HDR"]),
            ("Connectivity", ["HDMI", "Wi-Fi"]),
        ),
        taxonomy_sub_category="50 Inches Plus",
        taxonomy_path="Electronics > TVs > 50 Inches Plus",
        taxonomy_parent_category="Electronics",
        taxonomy_leaf_category="TVs",
    )

    assert result.matched_schema_id == "tv-leaf"
    assert result.selected_template_id == "tileoraseis"
    assert result.subcategory_match_policy == "leaf_family"
    assert result.candidate_pool_size == 1
    assert result.candidate_template_ids == ["tileoraseis"]
    assert candidates[0]["subcategory_match_policy"] == "leaf_family"
    assert all(candidate["category_path"] == "Electronics > TVs > -" for candidate in candidates)


def test_mixed_family_exact_pool_wins_over_leaf_template(tmp_path: Path) -> None:
    schema_path = _write_schema_library(
        tmp_path,
        [
            _schema(
                schema_id="ac-leaf",
                template_id="klimatistika",
                category_path="Home > Air Conditioners > -",
                parent_category="Home",
                leaf_category="Air Conditioners",
                sub_category=None,
                subcategory_match_policy="mixed_family",
                sections=[("Overview", ["BTU", "Inverter", "Wi-Fi"])],
                min_section_overlap=1,
                min_label_overlap=2,
            ),
            _schema(
                schema_id="ac-wall",
                template_id="toixoy",
                category_path="Home > Air Conditioners > Wall Mounted",
                parent_category="Home",
                leaf_category="Air Conditioners",
                sub_category="Wall Mounted",
                subcategory_match_policy="mixed_family",
                sections=[
                    ("Overview", ["BTU", "Inverter", "Wi-Fi"]),
                    ("Dimensions", ["Indoor Height", "Outdoor Height"]),
                ],
                min_section_overlap=1,
                min_label_overlap=2,
            ),
        ],
    )
    matcher = SchemaMatcher(str(schema_path))

    result, candidates = matcher.match(
        _spec_sections(
            ("Overview", ["BTU", "Inverter", "Wi-Fi"]),
            ("Dimensions", ["Indoor Height", "Outdoor Height"]),
        ),
        taxonomy_sub_category="Wall Mounted",
        taxonomy_path="Home > Air Conditioners > Wall Mounted",
        taxonomy_parent_category="Home",
        taxonomy_leaf_category="Air Conditioners",
    )

    assert result.matched_schema_id == "ac-wall"
    assert result.selected_template_id == "toixoy"
    assert result.subcategory_match_policy == "mixed_family"
    assert result.candidate_pool_size == 1
    assert result.candidate_template_ids == ["toixoy"]
    assert {candidate["template_id"] for candidate in candidates} == {"toixoy"}


def test_mixed_family_allows_leaf_fallback_when_exact_missing(tmp_path: Path) -> None:
    schema_path = _write_schema_library(
        tmp_path,
        [
            _schema(
                schema_id="fan-leaf",
                template_id="anemistires",
                category_path="Home > Fans > -",
                parent_category="Home",
                leaf_category="Fans",
                sub_category=None,
                subcategory_match_policy="mixed_family",
                sections=[
                    ("Overview", ["Power", "Diameter", "Speeds"]),
                    ("General", ["Color", "Warranty"]),
                ],
                min_section_overlap=1,
                min_label_overlap=2,
            ),
            _schema(
                schema_id="fan-desk",
                template_id="epitrapezioi",
                category_path="Home > Fans > Desk",
                parent_category="Home",
                leaf_category="Fans",
                sub_category="Desk",
                subcategory_match_policy="mixed_family",
                sections=[("Overview", ["Power", "Diameter", "Oscillation"])],
            ),
        ],
    )
    matcher = SchemaMatcher(str(schema_path))

    result, candidates = matcher.match(
        _spec_sections(
            ("Overview", ["Power", "Diameter", "Speeds"]),
            ("General", ["Color", "Warranty"]),
        ),
        taxonomy_sub_category="Ceiling",
        taxonomy_path="Home > Fans > Ceiling",
        taxonomy_parent_category="Home",
        taxonomy_leaf_category="Fans",
    )

    assert result.matched_schema_id == "fan-leaf"
    assert result.selected_template_id == "anemistires"
    assert result.subcategory_match_policy == "mixed_family"
    assert result.candidate_pool_size == 1
    assert result.candidate_template_ids == ["anemistires"]
    assert candidates[0]["subcategory_match_policy"] == "mixed_family"
    assert all(candidate["category_path"] == "Home > Fans > -" for candidate in candidates)


def test_exact_subcategory_policy_does_not_fall_back_to_leaf_only_template(tmp_path: Path) -> None:
    schema_path = _write_schema_library(
        tmp_path,
        [
            _schema(
                schema_id="dishwasher-leaf",
                template_id="dishwashers",
                category_path="Home > Dishwashers > -",
                parent_category="Home",
                leaf_category="Dishwashers",
                sub_category=None,
                subcategory_match_policy="exact_subcategory",
                sections=[
                    ("Overview", ["Place Settings", "Programs", "Noise Level"]),
                ],
            ),
        ],
    )
    matcher = SchemaMatcher(str(schema_path))

    result, candidates = matcher.match(
        _spec_sections(("Overview", ["Place Settings", "Programs", "Noise Level"])),
        taxonomy_sub_category="45cm",
        taxonomy_path="Home > Dishwashers > 45cm",
        taxonomy_parent_category="Home",
        taxonomy_leaf_category="Dishwashers",
    )

    assert result.matched_schema_id is None
    assert result.fail_reason == "pool_empty_for_category"
    assert result.candidate_pool_size == 0
    assert result.candidate_template_ids == []
    assert result.subcategory_match_policy == ""
    assert candidates == []


def test_leaf_family_fallback_remains_parent_leaf_bounded(tmp_path: Path) -> None:
    schema_path = _write_schema_library(
        tmp_path,
        [
            _schema(
                schema_id="tv-leaf",
                template_id="tileoraseis",
                category_path="Electronics > TVs > -",
                parent_category="Electronics",
                leaf_category="TVs",
                sub_category=None,
                subcategory_match_policy="leaf_family",
                sections=[("Overview", ["Screen Size", "HDR"])],
            ),
            _schema(
                schema_id="range-leaf",
                template_id="koyzines",
                category_path="Home > Ranges > -",
                parent_category="Home",
                leaf_category="Ranges",
                sub_category=None,
                subcategory_match_policy="leaf_family",
                sections=[("Overview", ["Burners", "Capacity"])],
            ),
        ],
    )
    matcher = SchemaMatcher(str(schema_path))

    result, candidates = matcher.match(
        _spec_sections(("Overview", ["Power Output", "Bluetooth"])),
        taxonomy_sub_category="Portable",
        taxonomy_path="Electronics > Audio > Portable",
        taxonomy_parent_category="Electronics",
        taxonomy_leaf_category="Audio",
    )

    assert result.matched_schema_id is None
    assert result.fail_reason == "pool_empty_for_category"
    assert result.candidate_pool_size == 0
    assert result.candidate_template_ids == []
    assert candidates == []


def test_generic_overlap_fails_closed_instead_of_global_drift(tmp_path: Path) -> None:
    schema_path = _write_schema_library(
        tmp_path,
        [
            _schema(
                schema_id="kettle-basic",
                template_id="kettle_basic",
                category_path="Home > Small Appliances > Kettles",
                parent_category="Home",
                leaf_category="Small Appliances",
                sub_category="Kettles",
                sections=[
                    ("Overview", ["Capacity", "Power", "Color"]),
                    ("Features", ["Cordless"]),
                ],
                match_mode="category_pool",
                sibling_template_ids=["kettle_glass"],
                required_labels_any=["Capacity"],
                min_section_overlap=1,
                min_label_overlap=3,
            ),
            _schema(
                schema_id="kettle-glass",
                template_id="kettle_glass",
                category_path="Home > Small Appliances > Kettles",
                parent_category="Home",
                leaf_category="Small Appliances",
                sub_category="Kettles",
                sections=[
                    ("Overview", ["Capacity", "Power", "Color"]),
                    ("Features", ["Glass Body", "Temperature Control"]),
                ],
                match_mode="category_pool",
                sibling_template_ids=["kettle_basic"],
                required_labels_any=["Capacity"],
                min_section_overlap=1,
                min_label_overlap=3,
            ),
            _schema(
                schema_id="wm-1",
                template_id="washing_machine_active",
                category_path="Home > Laundry > Washing Machines",
                parent_category="Home",
                leaf_category="Laundry",
                sub_category="Washing Machines",
                sections=[
                    ("Overview", ["Capacity", "Spin Speed"]),
                    ("Programs", ["Steam Program", "Delay End"]),
                ],
            ),
        ],
    )
    matcher = SchemaMatcher(str(schema_path))

    result, candidates = matcher.match(
        _spec_sections(("Overview", ["Power", "Color"])),
        taxonomy_sub_category="Kettles",
        taxonomy_path="Home > Small Appliances > Kettles",
        taxonomy_parent_category="Home",
        taxonomy_leaf_category="Small Appliances",
    )

    assert result.matched_schema_id is None
    assert result.warnings == ["no_safe_template_match"]
    assert result.fail_reason == "discriminator_miss"
    assert {candidate["matched_schema_id"] for candidate in candidates} == {"kettle-basic", "kettle-glass"}
    assert all(candidate["gate_status"] == "failed" for candidate in candidates)


def test_washing_machine_like_specs_cannot_select_small_appliance_template(tmp_path: Path) -> None:
    schema_path = _write_schema_library(
        tmp_path,
        [
            _schema(
                schema_id="kettle-basic",
                template_id="kettle_basic",
                category_path="Home > Small Appliances > Kettles",
                parent_category="Home",
                leaf_category="Small Appliances",
                sub_category="Kettles",
                sections=[
                    ("Overview", ["Capacity", "Power", "Color"]),
                    ("Features", ["Cordless"]),
                ],
                match_mode="category_pool",
                sibling_template_ids=["toaster-1"],
                required_labels_any=["Capacity"],
                min_section_overlap=1,
                min_label_overlap=2,
            ),
            _schema(
                schema_id="toaster-1",
                template_id="toaster",
                category_path="Home > Small Appliances > Kettles",
                parent_category="Home",
                leaf_category="Small Appliances",
                sub_category="Kettles",
                sections=[
                    ("Overview", ["Power", "Color", "Slots"]),
                    ("Features", ["Defrost"]),
                ],
                match_mode="category_pool",
                sibling_template_ids=["kettle_basic"],
                required_labels_any=["Power"],
                min_section_overlap=1,
                min_label_overlap=2,
            ),
        ],
    )
    matcher = SchemaMatcher(str(schema_path))

    result, candidates = matcher.match(
        _spec_sections(
            ("Overview", ["Spin Speed", "Drum Size"]),
            ("Programs", ["Steam Program", "Delay End", "Child Lock"]),
        ),
        taxonomy_sub_category="Kettles",
        taxonomy_path="Home > Small Appliances > Kettles",
        taxonomy_parent_category="Home",
        taxonomy_leaf_category="Small Appliances",
    )

    assert result.matched_schema_id is None
    assert result.warnings == ["no_safe_template_match"]
    assert result.fail_reason == "discriminator_miss"
    assert {candidate["matched_schema_id"] for candidate in candidates} == {"kettle-basic", "toaster-1"}


def test_manual_only_category_reports_manual_only_fail_reason(tmp_path: Path) -> None:
    schema_path = _write_schema_library(
        tmp_path,
        [
            _schema(
                schema_id="manual-1",
                template_id="manual_template",
                category_path="Home > Laundry > Irons",
                parent_category="Home",
                leaf_category="Laundry",
                sub_category="Irons",
                sections=[("TODO", ["Needs Manual Labels"])],
                template_status="manual_only",
                match_mode="manual_only",
            ),
        ],
    )
    matcher = SchemaMatcher(str(schema_path))

    result, candidates = matcher.match(
        _spec_sections(("Overview", ["Power"])),
        taxonomy_sub_category="Irons",
        taxonomy_path="Home > Laundry > Irons",
        taxonomy_parent_category="Home",
        taxonomy_leaf_category="Laundry",
    )

    assert result.matched_schema_id is None
    assert result.fail_reason == "manual_only_category"
    assert result.candidate_pool_size == 1
    assert result.candidate_template_ids == ["manual_template"]
    assert result.selected_template_id is None
    assert candidates[0]["gate_reasons"] == ["template_status:manual_only"]


def test_insufficient_section_overlap_reports_specific_fail_reason(tmp_path: Path) -> None:
    schema_path = _write_schema_library(
        tmp_path,
        [
            _schema(
                schema_id="schema-1",
                template_id="section_heavy",
                category_path="Home > Appliances > Fans",
                parent_category="Home",
                leaf_category="Appliances",
                sub_category="Fans",
                sections=[
                    ("Overview", ["Power", "Color"]),
                    ("Features", ["Remote Control"]),
                    ("Dimensions", ["Height"]),
                ],
                match_mode="category_pool",
                sibling_template_ids=["schema-2"],
                min_section_overlap=2,
                min_label_overlap=1,
            ),
            _schema(
                schema_id="schema-2",
                template_id="section_heavy_2",
                category_path="Home > Appliances > Fans",
                parent_category="Home",
                leaf_category="Appliances",
                sub_category="Fans",
                sections=[
                    ("Overview", ["Power", "Color"]),
                    ("Features", ["Timer"]),
                    ("Dimensions", ["Width"]),
                ],
                match_mode="category_pool",
                sibling_template_ids=["schema-1"],
                min_section_overlap=2,
                min_label_overlap=1,
            ),
        ],
    )
    matcher = SchemaMatcher(str(schema_path))

    result, _candidates = matcher.match(
        _spec_sections(("Overview", ["Power", "Color"])),
        taxonomy_sub_category="Fans",
        taxonomy_path="Home > Appliances > Fans",
        taxonomy_parent_category="Home",
        taxonomy_leaf_category="Appliances",
    )

    assert result.matched_schema_id is None
    assert result.fail_reason == "insufficient_section_overlap"


def test_insufficient_label_overlap_reports_specific_fail_reason(tmp_path: Path) -> None:
    schema_path = _write_schema_library(
        tmp_path,
        [
            _schema(
                schema_id="schema-1",
                template_id="label_heavy",
                category_path="Home > Appliances > Mixers",
                parent_category="Home",
                leaf_category="Appliances",
                sub_category="Mixers",
                sections=[("Overview", ["Power", "Speed", "Color"])],
                match_mode="category_pool",
                sibling_template_ids=["schema-2"],
                min_section_overlap=1,
                min_label_overlap=3,
            ),
            _schema(
                schema_id="schema-2",
                template_id="label_heavy_2",
                category_path="Home > Appliances > Mixers",
                parent_category="Home",
                leaf_category="Appliances",
                sub_category="Mixers",
                sections=[("Overview", ["Power", "Pulse", "Bowl"])],
                match_mode="category_pool",
                sibling_template_ids=["schema-1"],
                min_section_overlap=1,
                min_label_overlap=3,
            ),
        ],
    )
    matcher = SchemaMatcher(str(schema_path))

    result, _candidates = matcher.match(
        _spec_sections(("Overview", ["Power"])),
        taxonomy_sub_category="Mixers",
        taxonomy_path="Home > Appliances > Mixers",
        taxonomy_parent_category="Home",
        taxonomy_leaf_category="Appliances",
    )

    assert result.matched_schema_id is None
    assert result.fail_reason == "insufficient_label_overlap"
