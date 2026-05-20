from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from product_factory import mapping
from product_factory.category_filters import (
    find_filter_category,
    get_filter_group_value_map,
    load_filter_map,
    resolve_category_filter_values,
)
from product_factory.csv_writer import write_csv_row
from product_factory.models import (
    CLIInput,
    ParsedProduct,
    SchemaMatchResult,
    SourceProductData,
    SpecItem,
    SpecSection,
    TaxonomyResolution,
)
from product_factory.validator import validate_candidate_csv


def _category() -> dict:
    return {
        "category_id": "cat_laptops",
        "key": "Laptops",
        "path": "ΠΛΗΡΟΦΟΡΙΚΗ > Υπολογιστές > Laptops",
        "filter_groups": [
            {
                "group_id": "fg_screen",
                "name": "Διαγώνιος Οθόνης  (Ίντσες)",
                "required": True,
                "status": "active",
                "values": [
                    {"value_id": "fv_156", "value": "15.6", "status": "active"},
                    {"value_id": "fv_173", "value": "17.3", "status": "deprecated"},
                ],
            },
            {
                "group_id": "fg_os",
                "name": "Λειτουργικό",
                "required": False,
                "status": "active",
                "values": [
                    {"value_id": "fv_win11", "value": "Windows 11", "status": "active"}
                ],
            },
            {
                "group_id": "fg_ram",
                "name": "Μνήμη Ram",
                "required": True,
                "status": "active",
                "values": [
                    {"value_id": "fv_8", "value": "8 GB", "status": "active"},
                    {"value_id": "fv_16", "value": "16 GB", "status": "active"},
                ],
            },
            {
                "group_id": "fg_gpu",
                "name": "Μοντέλο Κάρτας Γραφικών",
                "required": False,
                "status": "active",
                "values": [],
            },
            {
                "group_id": "fg_disk",
                "name": "Σκληρός Δίσκος",
                "required": False,
                "status": "active",
                "values": [],
            },
            {
                "group_id": "fg_cpu",
                "name": "Τύπος επεξεργαστή",
                "required": False,
                "status": "active",
                "values": [],
            },
            {
                "group_id": "fg_inactive",
                "name": "Ανενεργό",
                "required": True,
                "status": "inactive",
                "values": [{"value_id": "fv_old", "value": "Old", "status": "active"}],
            },
            {
                "group_id": "fg_deprecated",
                "name": "Παλιό Group",
                "required": True,
                "status": "deprecated",
                "values": [
                    {"value_id": "fv_legacy", "value": "Legacy", "status": "active"}
                ],
            },
        ],
    }


def _filter_map() -> dict:
    category = _category()
    return {
        "subcategories": [category],
        "by_category_id": {category["category_id"]: category},
        "by_path": {category["path"]: category},
    }


def _taxonomy(category_id: str = "cat_laptops") -> TaxonomyResolution:
    return TaxonomyResolution(
        category_id=category_id,
        parent_category="ΠΛΗΡΟΦΟΡΙΚΗ",
        leaf_category="Υπολογιστές",
        sub_category="Laptops",
        taxonomy_path="ΠΛΗΡΟΦΟΡΙΚΗ > Υπολογιστές > Laptops",
        cta_url="https://example.com/laptops",
    )


def _source(
    *items: tuple[str, str], manufacturer_items: list[tuple[str, str]] | None = None
) -> SourceProductData:
    return SourceProductData(
        brand="Lenovo",
        mpn="ABC",
        name="Lenovo Laptop ABC",
        key_specs=[SpecItem(label=label, value=value) for label, value in items],
        manufacturer_spec_sections=[
            SpecSection(
                section="Manufacturer",
                items=[
                    SpecItem(label=label, value=value)
                    for label, value in manufacturer_items or []
                ],
            )
        ],
    )


def _template(path: Path, headers: list[str] | None = None) -> Path:
    headers = headers or ["model", "name", "meta_description"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
    return path


def _csv(path: Path, headers: list[str], row: dict[str, str]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerow(row)
    return path


def _patch_mapping_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(
        mapping,
        "build_deterministic_product_fields",
        lambda **_: {
            "name": "Lenovo Laptop ABC",
            "meta_title": "Lenovo Laptop ABC",
            "mpn": "ABC",
            "manufacturer": "Lenovo",
            "seo_keyword": "lenovo-laptop-abc",
            "brand": "Lenovo",
        },
    )
    monkeypatch.setattr(mapping, "build_deterministic_cta", lambda *_: "CTA")
    monkeypatch.setattr(
        mapping, "build_description_html", lambda **_: ("<p>description</p>", [])
    )
    monkeypatch.setattr(
        mapping,
        "build_description_html_from_intro_and_sections",
        lambda **_: ("<p>description</p>", []),
    )
    monkeypatch.setattr(
        mapping,
        "build_description_html_from_llm",
        lambda **_: ("<p>description</p>", []),
    )
    monkeypatch.setattr(
        mapping,
        "build_characteristics_for_product",
        lambda **_: ("<table></table>", {}, []),
    )


def test_category_filter_category_lookup_by_category_id() -> None:
    assert find_filter_category(_filter_map(), category_id="cat_laptops")[
        "path"
    ].endswith("Laptops")


def test_tv_subcategories_share_filter_groups() -> None:
    payload = load_filter_map()
    tv_categories = [
        category
        for category in payload["subcategories"]
        if category.get("parent_category") == "ΕΙΚΟΝΑ & ΗΧΟΣ"
        and category.get("leaf_category") == "Τηλεοράσεις"
    ]

    assert [category["sub_category"] for category in tv_categories] == [
        "8K UHD",
        "OLED TV",
        "TCL",
        "4K UHD",
        "Έως 32''",
        "33''-50''",
        "50'' & άνω",
    ]
    signatures = [
        {
            "groups": [group["name"] for group in category["filter_groups"]],
            "required": {
                group["name"]: group["required"] for group in category["filter_groups"]
            },
            "values": get_filter_group_value_map(category),
        }
        for category in tv_categories
    ]
    assert all(signature == signatures[0] for signature in signatures)
    assert signatures[0]["required"] == {
        "Smart Tv": False,
        "Ανάλυση": True,
        "Μέγεθος οθόνης": True,
        "Τεχνολογία Οθόνης": True,
    }


def test_tv_resolution_filter_maps_4k_ultra_hd_to_4k_uhd() -> None:
    payload = load_filter_map()
    category = find_filter_category(
        payload, taxonomy_path="ΕΙΚΟΝΑ & ΗΧΟΣ > Τηλεοράσεις > 33''-50''"
    )
    source = SourceProductData(
        name='TCL Smart Τηλεόραση 43" 4K UHD LED 43P6K',
        key_specs=[
            SpecItem(label="Ευκρίνεια", value="4K Ultra HD"),
            SpecItem(label="Διαγώνιος", value='43 "'),
            SpecItem(label="Τύπος Panel", value="Direct LED"),
        ],
    )
    taxonomy = TaxonomyResolution(
        category_id=category["category_id"],
        parent_category="ΕΙΚΟΝΑ & ΗΧΟΣ",
        leaf_category="Τηλεοράσεις",
        sub_category="33''-50''",
        taxonomy_path="ΕΙΚΟΝΑ & ΗΧΟΣ > Τηλεοράσεις > 33''-50''",
    )

    result = resolve_category_filter_values(source, taxonomy, category)
    by_group = {group.group_name: group for group in result.groups}

    assert by_group["Ανάλυση"].resolved_value == "4K UHD"
    assert by_group["Ανάλυση"].resolved_from == "source_spec_alias"


def test_category_filter_category_lookup_falls_back_to_taxonomy_path() -> None:
    found = find_filter_category(
        _filter_map(), taxonomy_path="ΠΛΗΡΟΦΟΡΙΚΗ > Υπολογιστές > Laptops"
    )
    assert found["category_id"] == "cat_laptops"


def test_exact_spec_label_resolves_filter_value() -> None:
    result = resolve_category_filter_values(
        _source(("Μνήμη Ram", "16 GB")), _taxonomy(), _category()
    )
    ram = next(group for group in result.groups if group.group_name == "Μνήμη Ram")
    assert ram.resolved_value == "16 GB"
    assert ram.resolved_from == "source_spec_exact"


def test_normalized_spec_label_resolves_filter_value() -> None:
    result = resolve_category_filter_values(
        _source(("Μνήμη   Ram", "16 GB")), _taxonomy(), _category()
    )
    ram = next(group for group in result.groups if group.group_name == "Μνήμη Ram")
    assert ram.resolved_value == "16 GB"
    assert ram.resolved_from == "normalized_source"


def test_air_conditioner_filters_derive_btu_and_wifi_from_product_text() -> None:
    category = {
        "category_id": "cat_wall_ac",
        "key": "Τοίχου",
        "path": "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ > Κλιματιστικά > Τοίχου",
        "filter_groups": [
            {
                "group_id": "fg_capacity",
                "name": "Ονομαστική Απόδοση",
                "required": True,
                "status": "active",
                "values": [
                    {"value_id": "fv_24000", "value": "24000 BTU", "status": "active"}
                ],
            },
            {
                "group_id": "fg_wifi",
                "name": "Wifi",
                "required": True,
                "status": "active",
                "values": [
                    {
                        "value_id": "fv_wifi",
                        "value": "Υποστηρίζεται",
                        "status": "active",
                    }
                ],
            },
        ],
    }
    source = SourceProductData(
        name="A/C Inventor Neo Plus NPVI-24WFI/NPVO24 24000Btu",
        hero_summary="Κλιματιστικό Neo+, WiFi Standard με Φωνητικές Εντολές.",
    )
    taxonomy = TaxonomyResolution(
        category_id="cat_wall_ac",
        parent_category="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
        leaf_category="Κλιματιστικά",
        sub_category="Τοίχου",
        taxonomy_path="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ > Κλιματιστικά > Τοίχου",
    )

    result = resolve_category_filter_values(source, taxonomy, category)

    assert result.warnings == []
    resolved = {group.group_name: group.resolved_value for group in result.groups}
    assert resolved["Ονομαστική Απόδοση"] == "24000 BTU"
    assert resolved["Wifi"] == "Υποστηρίζεται"


def _energy_class_category() -> dict:
    return {
        "category_id": "cat_wall_ac",
        "key": "Τοίχου",
        "path": "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ > Κλιματιστικά > Τοίχου",
        "filter_groups": [
            {
                "group_id": "fg_energy",
                "name": "Ενεργειακή Κλάση",
                "required": True,
                "status": "active",
                "values": [
                    {
                        "value_id": "fv_a_triple_plus",
                        "value": "A+++",
                        "status": "active",
                    },
                    {
                        "value_id": "fv_a_double_plus",
                        "value": "A++",
                        "status": "active",
                    },
                    {"value_id": "fv_a_plus", "value": "A+", "status": "active"},
                    {"value_id": "fv_a", "value": "A", "status": "active"},
                ],
            }
        ],
    }


def _energy_class_taxonomy() -> TaxonomyResolution:
    return TaxonomyResolution(
        category_id="cat_wall_ac",
        parent_category="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
        leaf_category="Κλιματιστικά",
        sub_category="Τοίχου",
        taxonomy_path="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ > Κλιματιστικά > Τοίχου",
    )


def test_air_conditioner_energy_class_pair_keeps_double_plus_from_name() -> None:
    result = resolve_category_filter_values(
        SourceProductData(name="A/C Inventor 12000BTU A++/A+ WiFi"),
        _energy_class_taxonomy(),
        _energy_class_category(),
    )

    energy = result.groups[0]
    assert energy.resolved_value == "A++"
    assert energy.resolved_value != "A+++"


def test_air_conditioner_energy_class_pair_keeps_single_plus_from_name() -> None:
    result = resolve_category_filter_values(
        SourceProductData(name="A/C Inventor 12000BTU A+/A WiFi"),
        _energy_class_taxonomy(),
        _energy_class_category(),
    )

    energy = result.groups[0]
    assert energy.resolved_value == "A+"
    assert energy.resolved_value != "A+++"


def test_air_conditioner_energy_class_triple_plus_from_name() -> None:
    result = resolve_category_filter_values(
        SourceProductData(name="A/C Inventor 12000BTU A+++ WiFi"),
        _energy_class_taxonomy(),
        _energy_class_category(),
    )

    assert result.groups[0].resolved_value == "A+++"


def test_energy_class_direct_spec_value_keeps_double_plus() -> None:
    result = resolve_category_filter_values(
        SourceProductData(
            name="A/C Inventor 12000BTU WiFi",
            key_specs=[SpecItem(label="Ενεργειακή Κλάση", value="A++")],
        ),
        _energy_class_taxonomy(),
        _energy_class_category(),
    )

    energy = result.groups[0]
    assert energy.resolved_value == "A++"
    assert energy.resolved_value != "A+++"


def test_energy_class_direct_spec_value_keeps_plain_a() -> None:
    result = resolve_category_filter_values(
        SourceProductData(
            name="A/C Inventor 12000BTU WiFi",
            key_specs=[SpecItem(label="Ενεργειακή Κλάση", value="A")],
        ),
        _energy_class_taxonomy(),
        _energy_class_category(),
    )

    assert result.groups[0].resolved_value == "A"


def test_watt_filter_group_resolves_from_power_source_label() -> None:
    category = {
        "category_id": "cat_soundbar",
        "path": "ΕΙΚΟΝΑ & ΗΧΟΣ > Audio Systems > Sound Bars",
        "filter_groups": [
            {
                "group_id": "fg_power",
                "name": "Ισχύς (Watt)",
                "required": True,
                "status": "active",
                "values": [
                    {"value_id": "fv_580", "value": "580 W", "status": "active"}
                ],
            }
        ],
    }
    result = resolve_category_filter_values(
        _source(("Ισχύς", "580 W")), _taxonomy("cat_soundbar"), category
    )
    power = result.groups[0]
    assert power.resolved_value == "580 W"
    assert power.resolved_from == "source_spec_alias"


def test_watt_filter_group_resolves_from_power_in_watts_source_label() -> None:
    category = {
        "category_id": "cat_coffee",
        "path": "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ > Καφές-Ροφήματα-Χυμοί > Καφετιέρες Φίλτρου",
        "filter_groups": [
            {
                "group_id": "fg_power",
                "name": "Ισχύς (Watt)",
                "required": True,
                "status": "active",
                "values": [
                    {"value_id": "fv_1000", "value": "1000", "status": "active"}
                ],
            }
        ],
    }
    result = resolve_category_filter_values(
        _source(("Ισχύς σε Watts", "1000")), _taxonomy("cat_coffee"), category
    )
    power = result.groups[0]
    assert power.resolved_value == "1000"
    assert power.resolved_from == "source_spec_alias"


def test_watt_filter_group_resolves_from_max_power_watt_source_label() -> None:
    category = {
        "category_id": "cat_vacuums",
        "path": "ΞΞ™ΞΞ™Ξ‘ΞΞΞ£ Ξ•ΞΞΞ Ξ›Ξ™Ξ£ΞΞΞ£ > Ξ£ΞΊΞΏΟΟ€ΞΉΟƒΞΌΞ± > Ξ£ΞΊΞΏΟΟ€ΞµΟ‚",
        "filter_groups": [
            {
                "group_id": "fg_power",
                "name": "Ξ™ΟƒΟ‡ΟΟ‚ (Watt)",
                "required": True,
                "status": "active",
                "values": [{"value_id": "fv_550", "value": "550", "status": "active"}],
            }
        ],
    }
    result = resolve_category_filter_values(
        _source(("ΞΞ­Ξ³ΞΉΟƒΟ„Ξ· Ξ™ΟƒΟ‡ΟΟ‚ (Watt)", "550")),
        _taxonomy("cat_vacuums"),
        category,
    )
    power = result.groups[0]
    assert power.resolved_value == "550"
    assert power.resolved_from == "source_spec_alias"


@pytest.mark.parametrize(
    ("group_name", "source_label"),
    [
        ("Ισχύς (Watt)", "Ισχύς"),
        ("Ισχυς (Watt)", "Ισχυς"),
        ("Ισχύς (Watt)", "Ισχύς σε Watts"),
        ("Ισχυς (Watt)", "Ισχυς σε Watts"),
        ("Ισχύς (Watt)", "Μέγιστη Ισχύς (Watt)"),
        ("Ισχυς (Watt)", "Μεγιστη Ισχυς (Watt)"),
        ("Ισχύς (Watt)", "Ξ™ΟƒΟ‡ΟΟ‚"),
        ("Ισχύς (Watt)", "Ξ™ΟƒΟ‡ΟΟ‚ ΟƒΞµ Watts"),
        ("Ισχύς (Watt)", "ΞΞ­Ξ³ΞΉΟƒΟ„Ξ· Ξ™ΟƒΟ‡ΟΟ‚ (Watt)"),
    ],
)
def test_watt_filter_group_resolves_power_aliases_through_shared_registry(
    group_name: str, source_label: str
) -> None:
    category = {
        "category_id": "cat_power",
        "path": "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ > Σκούπισμα > Σκούπες",
        "filter_groups": [
            {
                "group_id": "fg_power",
                "name": group_name,
                "required": True,
                "status": "active",
                "values": [{"value_id": "fv_550", "value": "550", "status": "active"}],
            }
        ],
    }
    result = resolve_category_filter_values(
        _source((source_label, "550")), _taxonomy("cat_power"), category
    )
    power = result.groups[0]
    assert power.resolved_value == "550"
    assert power.resolved_from in {"source_spec_alias", "normalized_source"}
    assert power.outside_allowed is False


def test_watt_filter_group_does_not_resolve_unrelated_dimension_or_weight_labels() -> (
    None
):
    category = {
        "category_id": "cat_power",
        "path": "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ > Σκούπισμα > Σκούπες",
        "filter_groups": [
            {
                "group_id": "fg_power",
                "name": "Ισχύς (Watt)",
                "required": True,
                "status": "active",
                "values": [{"value_id": "fv_550", "value": "550", "status": "active"}],
            }
        ],
    }
    dimension = resolve_category_filter_values(
        _source(("Διαστάσεις", "550")), _taxonomy("cat_power"), category
    )
    weight = resolve_category_filter_values(
        _source(("Βάρος", "550")), _taxonomy("cat_power"), category
    )
    assert dimension.groups[0].resolved_value == ""
    assert weight.groups[0].resolved_value == ""


def test_sound_system_filter_group_resolves_from_channels_source_label() -> None:
    category = {
        "category_id": "cat_soundbar",
        "path": "ΕΙΚΟΝΑ & ΗΧΟΣ > Audio Systems > Sound Bars",
        "filter_groups": [
            {
                "group_id": "fg_channels",
                "name": "Σύστημα Ήχου",
                "required": True,
                "status": "active",
                "values": [{"value_id": "fv_51", "value": "5.1", "status": "active"}],
            }
        ],
    }
    result = resolve_category_filter_values(
        _source(("Κανάλια", "5.1")), _taxonomy("cat_soundbar"), category
    )
    channels = result.groups[0]
    assert channels.resolved_value == "5.1"
    assert channels.resolved_from == "source_spec_alias"


def test_burner_count_filter_group_resolves_from_burners_source_label() -> None:
    category = {
        "category_id": "cat_hobs",
        "path": "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ > Μικροί Μάγειρες > Εστίες",
        "filter_groups": [
            {
                "group_id": "fg_burners",
                "name": "Αριθμός εστιών",
                "required": True,
                "status": "active",
                "values": [{"value_id": "fv_2", "value": "2", "status": "active"}],
            }
        ],
    }
    result = resolve_category_filter_values(
        _source(("Εστίες", "2")), _taxonomy("cat_hobs"), category
    )
    burners = result.groups[0]
    assert burners.resolved_value == "2"
    assert burners.resolved_from == "source_spec_alias"


def test_approved_review_value_overrides_source_derived_value() -> None:
    result = resolve_category_filter_values(
        _source(("Μνήμη Ram", "8 GB")),
        _taxonomy(),
        _category(),
        review_values={"Μνήμη Ram": "16 GB"},
    )
    ram = next(group for group in result.groups if group.group_name == "Μνήμη Ram")
    assert ram.resolved_value == "16 GB"
    assert ram.resolved_from == "approved_review"


def test_saved_review_value_overrides_source_derived_value_before_approval(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_mapping_dependencies(monkeypatch)
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    (review_dir / "category_filters.override.json").write_text(
        json.dumps(
            {"approved": False, "values": {"Μνήμη Ram": "16 GB"}}, ensure_ascii=False
        ),
        encoding="utf-8",
    )

    row, _normalized, warnings = mapping.build_row(
        CLIInput(model="ABC", url="", price="1"),
        ParsedProduct(
            source=_source(
                ("Διαγώνιος Οθόνης  (Ίντσες)", "15.6"), ("Μνήμη Ram", "8 GB")
            )
        ),
        _taxonomy(),
        SchemaMatchResult(),
        model_root=tmp_path,
        filter_map=_filter_map(),
    )

    assert row["filter_group:Μνήμη Ram"] == "16 GB"
    assert "category_filter_review_not_approved" in warnings


def test_active_required_missing_filter_produces_warning_and_no_emitted_column() -> (
    None
):
    result = resolve_category_filter_values(
        _source(("Μνήμη Ram", "16 GB")), _taxonomy(), _category()
    )
    assert (
        "required_category_filter_missing:Διαγώνιος Οθόνης  (Ίντσες)" in result.warnings
    )
    assert not result.errors
    assert "filter_group:Διαγώνιος Οθόνης  (Ίντσες)" not in result.emitted_columns


def test_active_optional_missing_filter_does_not_produce_validation_error() -> None:
    result = resolve_category_filter_values(
        _source(("Διαγώνιος Οθόνης  (Ίντσες)", "15.6"), ("Μνήμη Ram", "16 GB")),
        _taxonomy(),
        _category(),
    )
    assert "Λειτουργικό" in result.unresolved_optional_groups
    assert not any(error.endswith(":Λειτουργικό") for error in result.errors)


def test_inactive_group_does_not_block_render() -> None:
    result = resolve_category_filter_values(
        _source(("Ανενεργό", "Old")), _taxonomy(), _category()
    )
    inactive = next(group for group in result.groups if group.group_name == "Ανενεργό")
    assert inactive.resolved_value == ""
    assert inactive.emitted is False
    assert not any(error.endswith(":Ανενεργό") for error in result.errors)
    assert "inactive_category_filter_used:Ανενεργό" not in result.warnings


def test_deprecated_value_is_emitted_and_warned() -> None:
    result = resolve_category_filter_values(
        _source(("Διαγώνιος Οθόνης  (Ίντσες)", "17.3"), ("Μνήμη Ram", "16 GB")),
        _taxonomy(),
        _category(),
    )
    screen = next(
        group
        for group in result.groups
        if group.group_name == "Διαγώνιος Οθόνης  (Ίντσες)"
    )
    assert screen.emitted is True
    assert (
        "deprecated_category_filter_value_used:Διαγώνιος Οθόνης  (Ίντσες)"
        in result.warnings
    )


def test_outside_allowed_value_is_emitted_and_warned() -> None:
    result = resolve_category_filter_values(
        _source(("Διαγώνιος Οθόνης  (Ίντσες)", "16.0"), ("Μνήμη Ram", "16 GB")),
        _taxonomy(),
        _category(),
    )
    screen = next(
        group
        for group in result.groups
        if group.group_name == "Διαγώνιος Οθόνης  (Ίντσες)"
    )
    assert screen.emitted is True
    assert screen.outside_allowed is True
    assert (
        "category_filter_value_outside_allowed:Διαγώνιος Οθόνης  (Ίντσες)"
        in result.warnings
    )


def test_value_alias_resolves_to_canonical_allowed_filter_value() -> None:
    category = {
        "category_id": "cat_vacuums",
        "path": "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ > Σκούπισμα > Σκούπες",
        "filter_groups": [
            {
                "group_id": "fg_vacuum_type",
                "name": "Τύπος Ηλεκτρικής Σκούπας",
                "required": True,
                "status": "active",
                "values": [
                    {
                        "value_id": "fv_bagless",
                        "value": "Με κάδο",
                        "status": "active",
                        "aliases": ["Τροχήλατη με δοχείο συλλογής σκόνης"],
                    }
                ],
            }
        ],
    }
    result = resolve_category_filter_values(
        _source(("Τύπος Ηλεκτρικής Σκούπας", "Τροχήλατη με δοχείο συλλογής σκόνης")),
        _taxonomy("cat_vacuums"),
        category,
    )
    vacuum_type = result.groups[0]
    assert vacuum_type.resolved_value == "Με κάδο"
    assert vacuum_type.outside_allowed is False


def test_skroutz_description_pair_resolves_filter_value_and_unit_alias() -> None:
    category = {
        "category_id": "cat_microwave",
        "path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Φούρνοι Μικροκυμάτων > Με Grill",
        "filter_groups": [
            {
                "group_id": "fg_power",
                "name": "Ισχύς (Watt)",
                "required": True,
                "status": "active",
                "values": [
                    {"value_id": "fv_800", "value": "800 W", "status": "active"}
                ],
            }
        ],
    }
    source = SourceProductData(
        source_name="skroutz",
        name="Brand MW-1",
        presentation_source_html="<ul><li>Ισχύς: 800W.</li></ul>",
    )

    result = resolve_category_filter_values(
        source, _taxonomy("cat_microwave"), category
    )

    power = result.groups[0]
    assert power.resolved_value == "800 W"
    assert power.resolved_from == "description_alias"
    assert power.outside_allowed is False


def test_dash_source_values_are_treated_as_missing_filter_values() -> None:
    category = {
        "category_id": "cat_dryers",
        "path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Πλυντήρια-Στεγνωτήρια > Στεγνωτήρια Ρούχων",
        "filter_groups": [
            {
                "group_id": "fg_color",
                "name": "Χρώμα",
                "required": True,
                "status": "active",
                "values": [
                    {"value_id": "fv_white", "value": "Λευκό", "status": "active"}
                ],
            }
        ],
    }

    result = resolve_category_filter_values(
        _source(("Χρώμα", "-")), _taxonomy("cat_dryers"), category
    )

    color = result.groups[0]
    assert color.resolved_value == ""
    assert color.emitted is False
    assert color.outside_allowed is False


def test_loading_type_value_alias_resolves_front_loading_to_allowed_value() -> None:
    category = {
        "category_id": "cat_washers",
        "path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Πλυντήρια-Στεγνωτήρια > Πλυντήρια Ρούχων",
        "filter_groups": [
            {
                "group_id": "fg_loading",
                "name": "Τρόπος Φόρτωσης",
                "required": True,
                "status": "active",
                "values": [
                    {"value_id": "fv_front", "value": "Εμπρός", "status": "active"}
                ],
            }
        ],
    }

    result = resolve_category_filter_values(
        _source(("Τύπος", "Εμπρόσθιας Φόρτωσης")), _taxonomy("cat_washers"), category
    )

    loading = result.groups[0]
    assert loading.resolved_value == "Εμπρός"
    assert loading.outside_allowed is False


def test_generic_capacity_label_only_feeds_dryer_kilos_for_dryer_taxonomy() -> None:
    category = {
        "category_id": "cat_dryer_or_washer",
        "path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Πλυντήρια-Στεγνωτήρια > Στεγνωτήρια Ρούχων",
        "filter_groups": [
            {
                "group_id": "fg_drying_capacity",
                "name": "Κιλά Στεγνώματος",
                "required": True,
                "status": "active",
                "values": [{"value_id": "fv_8", "value": "8kg", "status": "active"}],
            }
        ],
    }
    dryer_taxonomy = TaxonomyResolution(
        category_id="cat_dryer_or_washer",
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Πλυντήρια-Στεγνωτήρια",
        sub_category="Στεγνωτήρια Ρούχων",
        taxonomy_path="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Πλυντήρια-Στεγνωτήρια > Στεγνωτήρια Ρούχων",
    )
    washer_taxonomy = TaxonomyResolution(
        category_id="cat_dryer_or_washer",
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Πλυντήρια-Στεγνωτήρια",
        sub_category="Πλυντήρια Ρούχων",
        taxonomy_path="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Πλυντήρια-Στεγνωτήρια > Πλυντήρια Ρούχων",
    )

    dryer_result = resolve_category_filter_values(
        _source(("Χωρητικότητα", "8 kg")), dryer_taxonomy, category
    )
    washer_result = resolve_category_filter_values(
        _source(("Χωρητικότητα", "8 kg")), washer_taxonomy, category
    )

    assert dryer_result.groups[0].resolved_value == "8kg"
    assert dryer_result.groups[0].outside_allowed is False
    assert washer_result.groups[0].resolved_value == ""


def test_hob_zone_count_combines_count_and_technology_for_allowed_value() -> None:
    category = {
        "category_id": "cat_hobs",
        "path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Εντοιχιζόμενες Συσκευές > Εστίες",
        "filter_groups": [
            {
                "group_id": "fg_zones",
                "name": "Αριθμός Ζωνών",
                "required": True,
                "status": "active",
                "values": [
                    {
                        "value_id": "fv_4_induction",
                        "value": "4 επαγωγικές",
                        "status": "active",
                    }
                ],
            }
        ],
    }

    result = resolve_category_filter_values(
        _source(("Αριθμός εστιών", "4"), ("Τύπος", "Επαγωγική")),
        _taxonomy("cat_hobs"),
        category,
    )

    zones = result.groups[0]
    assert zones.resolved_value == "4 επαγωγικές"
    assert zones.resolved_from == "source_hob_zone_technology"
    assert zones.outside_allowed is False


def test_hob_technology_value_alias_resolves_to_allowed_filter_value() -> None:
    category = {
        "category_id": "cat_hobs",
        "path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Εντοιχιζόμενες Συσκευές > Εστίες",
        "filter_groups": [
            {
                "group_id": "fg_technology",
                "name": "Τεχνολογία Εστιών",
                "required": True,
                "status": "active",
                "values": [
                    {
                        "value_id": "fv_induction",
                        "value": "Αυτόνομο Κεραμικό Επαγωγικό",
                        "status": "active",
                    }
                ],
            }
        ],
    }

    result = resolve_category_filter_values(
        _source(("Τύπος", "Επαγωγική")), _taxonomy("cat_hobs"), category
    )

    technology = result.groups[0]
    assert technology.resolved_value == "Αυτόνομο Κεραμικό Επαγωγικό"
    assert technology.outside_allowed is False


def test_hob_technology_plato_label_alias_resolves_to_allowed_filter_value() -> None:
    category = {
        "category_id": "cat_hobs",
        "path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Εντοιχιζόμενες Συσκευές > Εστίες",
        "filter_groups": [
            {
                "group_id": "fg_technology",
                "name": "Τεχνολογία Εστιών",
                "required": True,
                "status": "active",
                "values": [
                    {
                        "value_id": "fv_combined_ceramic_electric",
                        "value": "Συνδυαζόμενο Κεραμικό Ηλεκτρικό",
                        "status": "active",
                    },
                    {
                        "value_id": "fv_ceramic_electric",
                        "value": "Αυτόνομο Κεραμικό Ηλεκτρικό",
                        "status": "active",
                    },
                ],
            }
        ],
    }

    result = resolve_category_filter_values(
        _source(("Τεχνολογία Πλατώ Εστιών", "Αυτόνομο κεραμικό ηλεκτρικό")),
        _taxonomy("cat_hobs"),
        category,
    )

    technology = result.groups[0]
    assert technology.resolved_value == "Αυτόνομο Κεραμικό Ηλεκτρικό"
    assert technology.resolved_from == "source_spec_alias"
    assert technology.outside_allowed is False


def test_builtin_hobs_energy_class_filter_is_optional_in_effective_map() -> None:
    category = find_filter_category(
        load_filter_map(),
        taxonomy_path="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Εντοιχιζόμενες Συσκευές > Εστίες",
    )

    energy = next(
        group
        for group in category["filter_groups"]
        if group["name"] == "Ενεργειακή Κλάση"
    )
    assert energy["required"] is False


def test_hob_width_prefers_builtin_cutout_width_label() -> None:
    category = {
        "category_id": "cat_hobs",
        "path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Εντοιχιζόμενες Συσκευές > Εστίες",
        "filter_groups": [
            {
                "group_id": "fg_width",
                "name": "Πλάτος cm",
                "required": True,
                "status": "active",
                "values": [
                    {"value_id": "fv_56", "value": "56 cm", "status": "active"},
                    {"value_id": "fv_574", "value": "57,4 cm", "status": "active"},
                ],
            }
        ],
    }
    taxonomy = TaxonomyResolution(
        category_id="cat_hobs",
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Εντοιχιζόμενες Συσκευές",
        sub_category="Εστίες",
        taxonomy_path="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Εντοιχιζόμενες Συσκευές > Εστίες",
    )

    result = resolve_category_filter_values(
        _source(
            ("Πλάτος Διάστασης Εντοιχισμού σε Εκατοστά", "56,00"),
            ("Πλάτος Συσκευής σε Εκατοστά", "57,40"),
        ),
        taxonomy,
        category,
    )

    width = result.groups[0]
    assert width.resolved_value == "56 cm"
    assert width.resolved_from == "source_width_label"
    assert width.outside_allowed is False


def test_fryer_capacity_uses_bucket_capacity_label_for_liter_filter() -> None:
    category = {
        "category_id": "cat_fryers",
        "path": "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ > Μικροί Μάγειρες > Φριτέζες",
        "filter_groups": [
            {
                "group_id": "fg_capacity",
                "name": "Χωρητικότητα σε Λίτρα",
                "required": True,
                "status": "active",
                "values": [
                    {"value_id": "fv_15", "value": "- 1.5 -", "status": "active"}
                ],
            }
        ],
    }
    taxonomy = TaxonomyResolution(
        category_id="cat_fryers",
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Μικροί Μάγειρες",
        sub_category="Φριτέζες",
        taxonomy_path="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ > Μικροί Μάγειρες > Φριτέζες",
    )

    result = resolve_category_filter_values(
        _source(("Χωρητικότητα Κάδου Μαγειρέματος σε Κιλά", "1,5")),
        taxonomy,
        category,
    )

    capacity = result.groups[0]
    assert capacity.resolved_value == "- 1.5 -"
    assert capacity.resolved_from == "source_spec_alias"
    assert capacity.outside_allowed is False


def test_egg_boiler_filter_is_derived_from_title() -> None:
    category = {
        "category_id": "cat_kettles",
        "path": "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ > Συσκευές Κουζίνας > Βραστήρες",
        "filter_groups": [
            {
                "group_id": "fg_egg_boiler",
                "name": "Βραστήρας Αυγών",
                "required": False,
                "status": "active",
                "values": [{"value_id": "fv_yes", "value": "Ναι", "status": "active"}],
            }
        ],
    }
    taxonomy = TaxonomyResolution(
        category_id="cat_kettles",
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Συσκευές Κουζίνας",
        sub_category="Βραστήρες",
        taxonomy_path="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ > Συσκευές Κουζίνας > Βραστήρες",
    )
    source = SourceProductData(
        brand="Philips",
        mpn="HD9137/90",
        name="Philips Βραστήρας Αυγών 6 Θέσεων 400W Μαύρος",
    )

    result = resolve_category_filter_values(source, taxonomy, category)

    egg_boiler = result.groups[0]
    assert egg_boiler.resolved_value == "Ναι"
    assert egg_boiler.resolved_from == "source_spec_exact"
    assert egg_boiler.emitted is True


def test_no_frost_spacing_alias_resolves_to_allowed_filter_value() -> None:
    category = {
        "category_id": "cat_fridge_freezers",
        "path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Ψυγεία & Καταψύκτες > Ψυγειοκαταψύκτες",
        "filter_groups": [
            {
                "group_id": "fg_cooling",
                "name": "Ψύξη",
                "required": True,
                "status": "active",
                "values": [
                    {
                        "value_id": "fv_total_no_frost",
                        "value": "Total No Frost",
                        "status": "active",
                    }
                ],
            }
        ],
    }

    result = resolve_category_filter_values(
        _source(("Σύστημα Ψύξης", "Total NoFrost")),
        _taxonomy("cat_fridge_freezers"),
        category,
    )

    cooling = result.groups[0]
    assert cooling.resolved_value == "Total No Frost"
    assert cooling.outside_allowed is False


def test_oven_filter_aliases_and_inactive_group_allow_canonical_resolution() -> None:
    category = {
        "category_id": "cat_ovens",
        "path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Εντοιχιζόμενες Συσκευές > Φούρνοι",
        "filter_groups": [
            {
                "group_id": "fg_energy",
                "name": "Ενεργειακή Κλάση",
                "required": True,
                "status": "active",
                "values": [
                    {
                        "value_id": "fv_energy_a_plus",
                        "value": "Α+",
                        "status": "active",
                        "aliases": ["A+"],
                    }
                ],
            },
            {
                "group_id": "fg_clock",
                "name": "Ηλεκτρονικό Ρολόι",
                "required": True,
                "status": "active",
                "values": [
                    {
                        "value_id": "fv_clock_yes",
                        "value": "- Ναι -",
                        "status": "active",
                        "aliases": ["Ναι"],
                    }
                ],
            },
            {
                "group_id": "fg_type",
                "name": "Τύπος φούρνου",
                "required": True,
                "status": "active",
                "values": [
                    {
                        "value_id": "fv_oven_electric",
                        "value": "Ηλεκτρικό",
                        "status": "active",
                        "aliases": ["Ηλεκτρικός"],
                    }
                ],
            },
            {
                "group_id": "fg_capacity",
                "name": "Χωρητικότητα Φούρνου",
                "required": True,
                "status": "active",
                "values": [
                    {
                        "value_id": "fv_capacity_71",
                        "value": "71lt",
                        "status": "active",
                        "aliases": ["71 lt", "71 λίτρα", "71"],
                    }
                ],
            },
            {
                "group_id": "fg_width",
                "name": "Πλάτος cm",
                "required": True,
                "status": "active",
                "values": [
                    {"value_id": "fv_width_594", "value": "59,4 cm", "status": "active"}
                ],
            },
            {
                "group_id": "fg_cooling_energy",
                "name": "Ενεργειακή Κλάση Ψύξης",
                "required": True,
                "status": "inactive",
                "values": [
                    {"value_id": "fv_unused", "value": "A+", "status": "active"}
                ],
            },
        ],
    }
    result = resolve_category_filter_values(
        _source(
            ("Ενεργειακή Κλάση", "A+"),
            ("Ψηφιακή Οθόνη", "Ναι- με προγραμματισμό διάρκειας/λήξη ψησίματος"),
            ("Τύπος Φούρνου", "Φούρνος ηλεκτρικός"),
            ("Χωρητικότητα Φούρνου σε Λίτρα", "71"),
            ("Διαστάσεις Συσκευής σε Εκατοστά (Υ χ Π χ Β)", "59.50 x 59.40 x 54.80"),
        ),
        _taxonomy("cat_ovens"),
        category,
    )
    by_group = {group.group_name: group for group in result.groups}
    assert by_group["Ενεργειακή Κλάση"].resolved_value == "Α+"
    assert by_group["Ηλεκτρονικό Ρολόι"].resolved_value == "- Ναι -"
    assert by_group["Ηλεκτρονικό Ρολόι"].resolved_from == "source_spec_alias"
    assert by_group["Τύπος φούρνου"].resolved_value == "Ηλεκτρικό"
    assert by_group["Χωρητικότητα Φούρνου"].resolved_value == "71lt"
    assert by_group["Πλάτος cm"].resolved_value == "59,4 cm"
    assert (
        "required_category_filter_missing:Ενεργειακή Κλάση Ψύξης" not in result.errors
    )
    assert all(
        group.outside_allowed is False
        for group in by_group.values()
        if group.group_status == "active"
    )


def test_empty_resolved_values_are_not_emitted() -> None:
    result = resolve_category_filter_values(
        _source(("Διαγώνιος Οθόνης  (Ίντσες)", ""), ("Μνήμη Ram", "16 GB")),
        _taxonomy(),
        _category(),
    )
    assert "filter_group:Διαγώνιος Οθόνης  (Ίντσες)" not in result.emitted_columns


def test_csv_writer_writes_base_headers_first_and_dynamic_headers_after(
    tmp_path: Path,
) -> None:
    template = _template(tmp_path / "template.csv", ["model", "name"])
    headers, ordered = write_csv_row(
        {"model": "1", "filter_group:Μνήμη Ram": "16 GB", "name": "Laptop"},
        tmp_path / "out.csv",
        template,
    )
    assert headers == ["model", "name", "filter_group:Μνήμη Ram"]
    assert ordered["filter_group:Μνήμη Ram"] == "16 GB"


def test_csv_writer_omits_empty_filter_group_fields(tmp_path: Path) -> None:
    template = _template(tmp_path / "template.csv", ["model"])
    headers, _ordered = write_csv_row(
        {"model": "1", "filter_group:Μνήμη Ram": ""},
        tmp_path / "out.csv",
        template,
    )
    assert headers == ["model"]


def test_validator_accepts_base_headers_plus_trailing_filter_group_headers(
    tmp_path: Path,
) -> None:
    template = _template(tmp_path / "template.csv", ["model", "name"])
    candidate = _csv(
        tmp_path / "candidate.csv",
        ["model", "name", "filter_group:Μνήμη Ram"],
        {"model": "1", "name": "Laptop", "filter_group:Μνήμη Ram": "16 GB"},
    )
    report = validate_candidate_csv(candidate, template_path=template)
    assert report["ok"] is True


def test_validator_rejects_filter_group_headers_inside_base_header_block(
    tmp_path: Path,
) -> None:
    template = _template(tmp_path / "template.csv", ["model", "name"])
    candidate = _csv(
        tmp_path / "candidate.csv",
        ["model", "filter_group:Μνήμη Ram", "name"],
        {"model": "1", "name": "Laptop", "filter_group:Μνήμη Ram": "16 GB"},
    )
    report = validate_candidate_csv(candidate, template_path=template)
    assert "dynamic_filter_header_inside_base_block" in report["errors"]


def test_validator_rejects_non_filter_trailing_headers(tmp_path: Path) -> None:
    template = _template(tmp_path / "template.csv", ["model", "name"])
    candidate = _csv(
        tmp_path / "candidate.csv",
        ["model", "name", "unexpected"],
        {"model": "1", "name": "Laptop", "unexpected": "x"},
    )
    report = validate_candidate_csv(candidate, template_path=template)
    assert "non_filter_trailing_headers" in report["errors"]


def test_validator_reports_dynamic_filter_headers_and_count(tmp_path: Path) -> None:
    template = _template(tmp_path / "template.csv", ["model", "name"])
    candidate = _csv(
        tmp_path / "candidate.csv",
        ["model", "name", "filter_group:Μνήμη Ram", "filter_group:Λειτουργικό"],
        {
            "model": "1",
            "name": "Laptop",
            "filter_group:Μνήμη Ram": "16 GB",
            "filter_group:Λειτουργικό": "Windows 11",
        },
    )
    report = validate_candidate_csv(candidate, template_path=template)
    assert report["dynamic_filter_headers"] == [
        "filter_group:Μνήμη Ram",
        "filter_group:Λειτουργικό",
    ]
    assert report["dynamic_filter_count"] == 2


def test_build_row_adds_category_filter_diagnostics_to_normalized_output(
    monkeypatch,
) -> None:
    _patch_mapping_dependencies(monkeypatch)
    row, normalized, _warnings = mapping.build_row(
        CLIInput(model="ABC", url="", price="1"),
        ParsedProduct(
            source=_source(
                ("Διαγώνιος Οθόνης  (Ίντσες)", "15.6"), ("Μνήμη Ram", "16 GB")
            )
        ),
        _taxonomy(),
        SchemaMatchResult(),
        filter_map=_filter_map(),
    )
    assert normalized["category_filters"]["filter_category_found"] is True
    assert "filter_group:Μνήμη Ram" in row


def test_build_row_serializes_multiple_tv_categories(monkeypatch) -> None:
    _patch_mapping_dependencies(monkeypatch)
    row, _normalized, _warnings = mapping.build_row(
        CLIInput(model="TV60", url="", price="1"),
        ParsedProduct(
            source=SourceProductData(
                brand="TCL",
                name='TCL 60" OLED 4K UHD TV',
                key_specs=[
                    SpecItem(label="Διαγώνιος Οθόνης ( Ίντσες )", value="60"),
                    SpecItem(label="Τεχνολογία Οθόνης", value="OLED"),
                    SpecItem(label="Ανάλυση Οθόνης", value="Ultra HD ( 4K )"),
                ],
            )
        ),
        TaxonomyResolution(
            parent_category="ΕΙΚΟΝΑ & ΗΧΟΣ",
            leaf_category="Τηλεοράσεις",
            sub_category="50'' & άνω",
            taxonomy_path="ΕΙΚΟΝΑ & ΗΧΟΣ > Τηλεοράσεις > 50'' & άνω",
            cta_url="https://www.etranoulis.gr/eikona-hxos/thleoraseis",
        ),
        SchemaMatchResult(),
        filter_map={"subcategories": [], "by_category_id": {}, "by_path": {}},
    )

    assert row["category"].split(":::") == [
        "ΕΙΚΟΝΑ & ΗΧΟΣ",
        "ΕΙΚΟΝΑ & ΗΧΟΣ///Τηλεοράσεις",
        "ΕΙΚΟΝΑ & ΗΧΟΣ///Τηλεοράσεις///50'' & άνω",
        "ΕΙΚΟΝΑ & ΗΧΟΣ///Τηλεοράσεις///OLED TV",
        "ΕΙΚΟΝΑ & ΗΧΟΣ///Τηλεοράσεις///4K UHD",
        "ΕΙΚΟΝΑ & ΗΧΟΣ///Τηλεοράσεις///TCL",
    ]


def test_build_row_emits_laptop_style_filters_for_laptops_taxonomy_fixture(
    monkeypatch,
) -> None:
    _patch_mapping_dependencies(monkeypatch)
    row, _normalized, _warnings = mapping.build_row(
        CLIInput(model="ABC", url="", price="1"),
        ParsedProduct(
            source=_source(
                ("Διαγώνιος Οθόνης  (Ίντσες)", "15.6"),
                ("Λειτουργικό", "Windows 11"),
                ("Μνήμη Ram", "16 GB"),
                ("Μοντέλο Κάρτας Γραφικών", "RTX 3050"),
                ("Σκληρός Δίσκος", "512 GB SSD"),
                ("Τύπος επεξεργαστή", "Intel Core i7"),
            )
        ),
        _taxonomy(),
        SchemaMatchResult(),
        filter_map=_filter_map(),
    )
    assert [key for key in row if key.startswith("filter_group:")] == [
        "filter_group:Διαγώνιος Οθόνης  (Ίντσες)",
        "filter_group:Λειτουργικό",
        "filter_group:Μνήμη Ram",
        "filter_group:Μοντέλο Κάρτας Γραφικών",
        "filter_group:Σκληρός Δίσκος",
        "filter_group:Τύπος επεξεργαστή",
    ]


def test_microwave_filter_map_marks_grill_optional_and_removes_liter_capacity() -> None:
    filter_map = load_filter_map()
    expected = {
        "cat_7f1f151c974c": ("fg_c51e0faf5096", "fg_e0687464347d"),
        "cat_71bbce141acc": ("fg_0d5893235e18", "fg_58a5c1bfc67d"),
        "cat_2860df0d9d56": ("", "fg_5d339ef0cddc"),
    }

    for category_id, (grill_group_id, liters_group_id) in expected.items():
        category = find_filter_category(
            filter_map, category_id=category_id, taxonomy_path=""
        )
        groups = {group["group_id"]: group for group in category["filter_groups"]}
        if grill_group_id:
            assert groups[grill_group_id]["name"] == "Με Grill"
            assert groups[grill_group_id]["required"] is False
            assert groups[grill_group_id]["status"] == "active"
        assert groups[liters_group_id]["name"] == "Χωρητικότητα σε Λίτρα"
        assert groups[liters_group_id]["required"] is False
        assert groups[liters_group_id]["status"] == "inactive"

    without_grill = find_filter_category(
        filter_map, category_id="cat_2860df0d9d56", taxonomy_path=""
    )
    taxonomy = TaxonomyResolution(
        category_id="cat_2860df0d9d56",
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Φούρνοι Μικροκυμάτων",
        sub_category="Χωρίς Grill",
        taxonomy_path="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Φούρνοι Μικροκυμάτων > Χωρίς Grill",
    )
    result = resolve_category_filter_values(
        _source(
            ("Ισχύς Μικροκυμάτων (Watt)", "700"),
            ("Χωρητικότητα Φούρνου σε Λίτρα", "20"),
            ("Χρώμα", "Ασημί"),
        ),
        taxonomy,
        without_grill,
    )
    by_group = {group.group_name: group for group in result.groups}
    assert by_group["Ισχύς (Watt)"].resolved_value == "700"
    assert by_group["Χωρητικότητα Φούρνου"].resolved_value == "20lt"
    assert by_group["Χωρητικότητα σε Λίτρα"].emitted is False
    assert "required_category_filter_missing:Ισχύς (Watt)" not in result.warnings
    assert "filter_group:Χωρητικότητα σε Λίτρα" not in result.emitted_columns


def test_render_style_missing_required_filters_warn_without_failing_validation(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_mapping_dependencies(monkeypatch)
    row, normalized, _warnings = mapping.build_row(
        CLIInput(model="ABC", url="", price="1"),
        ParsedProduct(source=_source(("Μνήμη Ram", "16 GB"))),
        _taxonomy(),
        SchemaMatchResult(),
        filter_map=_filter_map(),
        llm_product={"meta_description": "Valid description", "meta_keywords": []},
    )
    template = _template(
        tmp_path / "template.csv", ["model", "name", "meta_description"]
    )
    csv_path = tmp_path / "candidate.csv"
    write_csv_row(row, csv_path, template)
    report = validate_candidate_csv(
        csv_path,
        template_path=template,
        category_filter_errors=normalized["category_filters"]["errors"],
        category_filter_warnings=normalized["category_filters"]["warnings"],
    )
    assert report["ok"] is True
    assert (
        "required_category_filter_missing:Διαγώνιος Οθόνης  (Ίντσες)"
        in report["warnings"]
    )
