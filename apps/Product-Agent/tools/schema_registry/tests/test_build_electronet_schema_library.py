from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.schema_registry.build_electronet_schema_library import build_library_payload


REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_ROOT = REPO_ROOT / "resources" / "templates" / "electronet"
TAXONOMY_PATH = REPO_ROOT / "resources" / "mappings" / "catalog_taxonomy.json"
CURRENT_LIBRARY_PATH = REPO_ROOT / "resources" / "schemas" / "electronet_schema_library.json"
SCHEMA_POLICY_RULES_PATH = REPO_ROOT / "resources" / "mappings" / "schema_policy_rules.json"


def _repo_payload() -> dict[str, object]:
    return build_library_payload(
        template_root=TEMPLATE_ROOT,
        taxonomy_path=TAXONOMY_PATH,
        schema_policy_rules_path=SCHEMA_POLICY_RULES_PATH,
        existing_library_path=CURRENT_LIBRARY_PATH,
    )


def _schemas_by_template_id(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    return {str(schema["template_id"]): schema for schema in payload["schemas"]}  # type: ignore[index]


def test_build_library_is_deterministic_for_repo_inputs() -> None:
    first = _repo_payload()
    second = _repo_payload()
    assert first == second


def test_build_library_emits_category_bound_metadata_for_regression_families() -> None:
    payload = _repo_payload()
    schemas = _schemas_by_template_id(payload)

    expected = {
        "tileoraseis": {
            "category_path": "ΕΙΚΟΝΑ & ΗΧΟΣ > Τηλεοράσεις > -",
            "parent_category": "ΕΙΚΟΝΑ & ΗΧΟΣ",
            "leaf_category": "Τηλεοράσεις",
            "sub_category": None,
            "subcategory_match_policy": "leaf_family",
        },
        "klimatistika": {
            "category_path": "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ > Κλιματιστικά > -",
            "parent_category": "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
            "leaf_category": "Κλιματιστικά",
            "sub_category": None,
            "subcategory_match_policy": "mixed_family",
        },
        "anemistires": {
            "category_path": "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ > Ανεμιστήρες > -",
            "parent_category": "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
            "leaf_category": "Ανεμιστήρες",
            "sub_category": None,
            "subcategory_match_policy": "mixed_family",
        },
        "koyzines": {
            "category_path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Κουζίνες > -",
            "parent_category": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
            "leaf_category": "Κουζίνες",
            "sub_category": None,
            "subcategory_match_policy": "leaf_family",
        },
        "plyntiria_piaton": {
            "category_path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Πλυντήρια Πιάτων > -",
            "parent_category": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
            "leaf_category": "Πλυντήρια Πιάτων",
            "sub_category": None,
            "subcategory_match_policy": "leaf_family",
        },
        "plyntiria_rouxwn": {
            "category_path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Πλυντήρια-Στεγνωτήρια > Πλυντήρια Ρούχων",
            "parent_category": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
            "leaf_category": "Πλυντήρια-Στεγνωτήρια",
            "sub_category": "Πλυντήρια Ρούχων",
            "subcategory_match_policy": "exact_subcategory",
        },
        "entoixizomena_plyntiria_piaton": {
            "category_path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Εντοιχιζόμενες Συσκευές > Πλυντήρια Πιάτων",
            "parent_category": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
            "leaf_category": "Εντοιχιζόμενες Συσκευές",
            "sub_category": "Πλυντήρια Πιάτων",
            "subcategory_match_policy": "exact_subcategory",
        },
        "entoixizomena_plyntiria_royxon": {
            "category_path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Εντοιχιζόμενες Συσκευές > Πλυντήρια Ρούχων",
            "parent_category": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
            "leaf_category": "Εντοιχιζόμενες Συσκευές",
            "sub_category": "Πλυντήρια Ρούχων",
            "subcategory_match_policy": "exact_subcategory",
        },
        "entoixizomena_psygeia": {
            "category_path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Εντοιχιζόμενες Συσκευές > Ψυγεία",
            "parent_category": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
            "leaf_category": "Εντοιχιζόμενες Συσκευές",
            "sub_category": "Ψυγεία",
            "subcategory_match_policy": "exact_subcategory",
        },
    }

    required_fields = {
        "source_system",
        "template_id",
        "category_path",
        "parent_category",
        "leaf_category",
        "sub_category",
        "subcategory_match_policy",
        "cta_map_key",
        "template_status",
        "match_mode",
        "section_names_exact",
        "section_names_normalized",
        "label_set_exact",
        "label_set_normalized",
        "section_label_pairs_normalized",
        "discriminator_labels",
        "required_labels_any",
        "required_labels_all",
        "forbidden_labels",
        "min_section_overlap",
        "min_label_overlap",
        "sibling_template_ids",
        "fingerprint",
        "source_template_file",
        "schema_id",
        "n_sections",
        "n_rows_total",
        "sections",
        "sentinel",
        "source_files",
    }

    for template_id, binding in expected.items():
        schema = schemas[template_id]
        assert required_fields.issubset(schema.keys())
        assert schema["source_system"] == "electronet"
        assert schema["template_status"] == "active"
        assert schema["match_mode"] == "direct_single"
        assert schema["sibling_template_ids"] == []
        assert schema["source_template_file"].endswith(f"{template_id}.json")
        assert schema["source_files"] == [f"{template_id}.json"]
        assert schema["category_path"] == binding["category_path"]
        assert schema["parent_category"] == binding["parent_category"]
        assert schema["leaf_category"] == binding["leaf_category"]
        assert schema["sub_category"] == binding["sub_category"]
        assert schema["subcategory_match_policy"] == binding["subcategory_match_policy"]
        assert schema["fingerprint"]
        assert schema["section_names_exact"]
        assert schema["label_set_exact"]
        assert schema["section_names_exact"][0] == schema["sections"][0]["title"]


def test_build_library_marks_placeholder_templates_manual_only() -> None:
    payload = _repo_payload()
    schemas = _schemas_by_template_id(payload)

    for template_id in ["tv_box", "set", "paraskeyastis_pop_korn", "axesoyar_klimatistikon"]:
        schema = schemas[template_id]
        assert schema["template_status"] == "manual_only"
        assert schema["match_mode"] == "manual_only"
        assert schema["required_labels_any"] == []
        assert schema["required_labels_all"] == []
        assert schema["discriminator_labels"] == []
        assert schema["forbidden_labels"] == []
        assert schema["min_section_overlap"] == 0
        assert schema["min_label_overlap"] == 0


def test_build_library_emits_explicit_subcategory_match_policy_for_known_exceptions() -> None:
    payload = _repo_payload()
    schemas = _schemas_by_template_id(payload)

    assert schemas["tileoraseis"]["subcategory_match_policy"] == "leaf_family"
    assert schemas["koyzines"]["subcategory_match_policy"] == "leaf_family"
    assert schemas["plyntiria_piaton"]["subcategory_match_policy"] == "leaf_family"
    assert schemas["foyrnoi_mikrokymaton"]["subcategory_match_policy"] == "leaf_family"
    assert schemas["plyntiria_rouxwn"]["subcategory_match_policy"] == "exact_subcategory"


def test_build_library_emits_mixed_family_policy_for_air_conditioners_and_fans() -> None:
    payload = _repo_payload()
    schemas = _schemas_by_template_id(payload)

    for template_id in [
        "klimatistika",
        "toixoy",
        "forita",
        "ntoylapes",
        "anemistires",
        "mini",
        "ydronefosis",
        "orthostatis",
        "epitrapezioi",
        "orofis",
        "air_coolers_epidapedioi",
        "anemisthres_an_toixou",
    ]:
        assert schemas[template_id]["subcategory_match_policy"] == "mixed_family"

    assert schemas["tileoraseis"]["subcategory_match_policy"] == "leaf_family"
    assert schemas["plyntiria_rouxwn"]["subcategory_match_policy"] == "exact_subcategory"


def test_build_library_preserves_authored_order_and_normalizes_safe_separators() -> None:
    payload = _repo_payload()
    schemas = _schemas_by_template_id(payload)
    washing_machine = schemas["plyntiria_rouxwn"]

    assert washing_machine["section_names_exact"][:3] == [
        "Επισκόπηση Προϊόντος",
        "Επιλογές Πλύσης",
        "Ασφάλεια",
    ]
    assert washing_machine["label_set_exact"][:4] == [
        "Τρόπος Φόρτωσης Πλυντηρίου",
        "Τρόπος Τοποθέτησης",
        "Χωρητικότητα Πλύσης",
        "Μέγιστες Στροφές Στυψίματος",
    ]
    assert "Διαστάσεις Συσκευής σε Εκατοστά (Υ x Π x Β)" in washing_machine["label_set_normalized"]
    assert washing_machine["section_label_pairs_normalized"][0] == (
        "Επισκόπηση Προϊόντος || Τρόπος Φόρτωσης Πλυντηρίου"
    )


def test_build_library_uses_category_pool_for_multiple_active_siblings(tmp_path: Path) -> None:
    template_root = tmp_path / "templates"
    template_root.mkdir()
    taxonomy_path = tmp_path / "taxonomy.json"

    taxonomy_payload = {
        "paths": [
            {
                "parent_category": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
                "leaf_category": "Δοκιμαστική Κατηγορία",
                "sub_category": None,
                "path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Δοκιμαστική Κατηγορία > -",
                "cta_url": "https://example.test/demo",
                "url": "https://example.test/demo",
            }
        ]
    }
    taxonomy_path.write_text(json.dumps(taxonomy_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    template_a = {
        "id": "demo_template_a_v1",
        "category_gr": "Δοκιμαστική Κατηγορία",
        "cta_map_key": "Δοκιμαστική Κατηγορία",
        "cta_url": "https://example.test/demo",
        "electronet_examples": ["https://example.test/product-a"],
        "sections": [
            {
                "section": "Γενικά",
                "labels": ["Κοινή Ετικέτα", "Μοναδική Ετικέτα Α"],
            }
        ],
    }
    template_b = {
        "id": "demo_template_b_v1",
        "category_gr": "Δοκιμαστική Κατηγορία",
        "cta_map_key": "Δοκιμαστική Κατηγορία",
        "cta_url": "https://example.test/demo",
        "electronet_examples": ["https://example.test/product-b"],
        "sections": [
            {
                "section": "Γενικά",
                "labels": ["Κοινή Ετικέτα", "Μοναδική Ετικέτα Β"],
            }
        ],
    }
    (template_root / "demo_a.json").write_text(json.dumps(template_a, ensure_ascii=False, indent=2), encoding="utf-8")
    (template_root / "demo_b.json").write_text(json.dumps(template_b, ensure_ascii=False, indent=2), encoding="utf-8")

    payload = build_library_payload(
        template_root=template_root,
        taxonomy_path=taxonomy_path,
        existing_library_path=None,
    )
    schemas = _schemas_by_template_id(payload)

    entry_a = schemas["demo_a"]
    entry_b = schemas["demo_b"]

    assert entry_a["template_status"] == "active"
    assert entry_b["template_status"] == "active"
    assert entry_a["match_mode"] == "category_pool"
    assert entry_b["match_mode"] == "category_pool"
    assert entry_a["sibling_template_ids"] == ["demo_b"]
    assert entry_b["sibling_template_ids"] == ["demo_a"]
    assert entry_a["discriminator_labels"] == ["Μοναδική Ετικέτα Α"]
    assert entry_b["discriminator_labels"] == ["Μοναδική Ετικέτα Β"]
    assert entry_a["required_labels_any"] == ["Μοναδική Ετικέτα Α"]
    assert entry_b["required_labels_any"] == ["Μοναδική Ετικέτα Β"]
    assert entry_a["forbidden_labels"] == ["Μοναδική Ετικέτα Β"]
    assert entry_b["forbidden_labels"] == ["Μοναδική Ετικέτα Α"]


def test_build_library_is_source_of_truth_pure_against_existing_compiled_library(tmp_path: Path) -> None:
    template_root = tmp_path / "templates"
    template_root.mkdir()
    taxonomy_path = tmp_path / "taxonomy.json"
    existing_library_path = tmp_path / "existing_library.json"

    taxonomy_payload = {
        "paths": [
            {
                "parent_category": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
                "leaf_category": "Δοκιμαστική Κατηγορία",
                "sub_category": None,
                "path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Δοκιμαστική Κατηγορία > -",
                "cta_url": "https://example.test/demo",
                "url": "https://example.test/demo",
            }
        ]
    }
    taxonomy_path.write_text(json.dumps(taxonomy_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    authored_template = {
        "id": "demo_template_v1",
        "category_gr": "Δοκιμαστική Κατηγορία",
        "cta_map_key": "Δοκιμαστική Κατηγορία",
        "cta_url": "https://example.test/demo",
        "electronet_examples": ["https://example.test/product-a"],
        "sections": [
            {
                "section": "Πρώτη Ενότητα",
                "labels": ["Πρώτη Ετικέτα", "Δεύτερη Ετικέτα"],
            },
            {
                "section": "Δεύτερη Ενότητα",
                "labels": ["Τρίτη Ετικέτα"],
            },
        ],
    }
    (template_root / "demo.json").write_text(json.dumps(authored_template, ensure_ascii=False, indent=2), encoding="utf-8")

    existing_library_payload = {
        "version": "stale",
        "source_system": "electronet",
        "schemas": [
            {
                "schema_id": "sha1:legacy-schema-id",
                "template_id": "demo",
                "source_files": ["demo.json"],
                "sections": [
                    {
                        "title": "Παρωχημένη Ενότητα",
                        "labels": ["Παρωχημένη Ετικέτα"],
                    }
                ],
            }
        ],
    }
    existing_library_path.write_text(
        json.dumps(existing_library_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    payload_without_existing = build_library_payload(
        template_root=template_root,
        taxonomy_path=taxonomy_path,
        existing_library_path=None,
    )
    payload_with_existing = build_library_payload(
        template_root=template_root,
        taxonomy_path=taxonomy_path,
        existing_library_path=existing_library_path,
    )

    assert payload_with_existing == payload_without_existing

    schema = _schemas_by_template_id(payload_with_existing)["demo"]
    assert schema["sections"] == [
        {
            "title": "Πρώτη Ενότητα",
            "labels": ["Πρώτη Ετικέτα", "Δεύτερη Ετικέτα"],
        },
        {
            "title": "Δεύτερη Ενότητα",
            "labels": ["Τρίτη Ετικέτα"],
        },
    ]
    assert schema["schema_id"] != "sha1:legacy-schema-id"

    edited_root = tmp_path / "templates-edited"
    edited_root.mkdir()
    edited_template = dict(authored_template)
    edited_template["sections"] = [
        {
            "section": "Πρώτη Ενότητα",
            "labels": ["Πρώτη Ετικέτα", "Δεύτερη Ετικέτα", "Νέα Ετικέτα"],
        },
        {
            "section": "Δεύτερη Ενότητα",
            "labels": ["Τρίτη Ετικέτα"],
        },
    ]
    (edited_root / "demo.json").write_text(json.dumps(edited_template, ensure_ascii=False, indent=2), encoding="utf-8")

    edited_payload = build_library_payload(
        template_root=edited_root,
        taxonomy_path=taxonomy_path,
        existing_library_path=existing_library_path,
    )
    edited_schema = _schemas_by_template_id(edited_payload)["demo"]

    assert edited_schema["schema_id"] != schema["schema_id"]


def test_build_library_rejects_invalid_schema_policy_rules(tmp_path: Path) -> None:
    bad_rules_path = tmp_path / "schema_policy_rules.json"
    bad_rules_path.write_text(
        json.dumps(
            {
                "default_policy": "exact_subcategory",
                "overrides": {"tileoraseis": "unsupported_policy"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported schema policy"):
        build_library_payload(
            template_root=TEMPLATE_ROOT,
            taxonomy_path=TAXONOMY_PATH,
            schema_policy_rules_path=bad_rules_path,
            existing_library_path=CURRENT_LIBRARY_PATH,
        )
