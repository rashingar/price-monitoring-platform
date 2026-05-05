from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.schema_registry.validate_templates import (
    DEFAULT_SCHEMA_PATH,
    render_report,
    validate_all_templates,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _valid_template(template_id: str, category: str = "Κατηγορία") -> dict[str, object]:
    return {
        "id": f"{template_id}_electronet_labels_v1",
        "category_gr": category,
        "cta_map_key": category,
        "cta_url": "https://www.electronet.gr/demo/category",
        "electronet_examples": ["https://www.electronet.gr/demo/product-1"],
        "sections": [
            {
                "section": "Γενικά",
                "labels": ["Ετικέτα 1", "Ετικέτα 2"],
            }
        ],
    }


def test_validate_templates_passes_on_valid_minimal_template_set(tmp_path: Path) -> None:
    template_root = tmp_path / "templates"
    template_root.mkdir()
    _write_json(template_root / "demo.json", _valid_template("demo"))

    results, duplicate_messages = validate_all_templates(template_root=template_root, schema_path=DEFAULT_SCHEMA_PATH)

    assert duplicate_messages == []
    assert len(results) == 1
    assert results[0][1] == []
    assert "Summary: checked=1 valid=1 invalid=0 issues=0" in render_report(results, duplicate_messages)


def test_validate_templates_fails_on_duplicate_template_ids(tmp_path: Path) -> None:
    template_root = tmp_path / "templates"
    template_root.mkdir()
    _write_json(template_root / "demo_a.json", _valid_template("demo_a"))
    _write_json(template_root / "demo_b.json", {**_valid_template("demo_b"), "id": "shared_electronet_labels_v1"})
    _write_json(template_root / "shared.json", {**_valid_template("shared"), "id": "shared_electronet_labels_v1"})

    results, duplicate_messages = validate_all_templates(template_root=template_root, schema_path=DEFAULT_SCHEMA_PATH)

    assert any("duplicate logical template id" in message for message in duplicate_messages)
    assert any(results)


def test_validate_templates_fails_on_duplicate_labels_in_one_section(tmp_path: Path) -> None:
    template_root = tmp_path / "templates"
    template_root.mkdir()
    payload = _valid_template("demo")
    payload["sections"] = [{"section": "Γενικά", "labels": ["Ετικέτα", " Ετικέτα "]}]
    _write_json(template_root / "demo.json", payload)

    results, _ = validate_all_templates(template_root=template_root, schema_path=DEFAULT_SCHEMA_PATH)

    messages = [issue.message for _, issues in results for issue in issues]
    assert any("duplicate label" in message for message in messages)


def test_validate_templates_fails_on_duplicate_section_names(tmp_path: Path) -> None:
    template_root = tmp_path / "templates"
    template_root.mkdir()
    payload = _valid_template("demo")
    payload["sections"] = [
        {"section": "Γενικά", "labels": ["Α"]},
        {"section": " Γενικά ", "labels": ["Β"]},
    ]
    _write_json(template_root / "demo.json", payload)

    results, _ = validate_all_templates(template_root=template_root, schema_path=DEFAULT_SCHEMA_PATH)

    messages = [issue.message for _, issues in results for issue in issues]
    assert any("duplicate section name" in message for message in messages)


def test_validate_templates_fails_on_blank_required_metadata(tmp_path: Path) -> None:
    template_root = tmp_path / "templates"
    template_root.mkdir()
    payload = _valid_template("demo")
    payload["id"] = "   "
    payload["category_gr"] = ""
    payload["cta_map_key"] = " "
    _write_json(template_root / "demo.json", payload)

    results, _ = validate_all_templates(template_root=template_root, schema_path=DEFAULT_SCHEMA_PATH)

    messages = [issue.message for _, issues in results for issue in issues]
    assert any("logical template id is blank" in message for message in messages)
    assert any("logical category is blank" in message for message in messages)
    assert any("logical cta_map_key is blank" in message for message in messages)
