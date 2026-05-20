from __future__ import annotations

import csv
import json
from pathlib import Path

from product_factory.tools.sync_filter_map import (
    build_base_from_csv,
    default_manual_overrides,
    run_apply_overrides,
    run_bootstrap,
    stable_category_id,
    stable_group_id,
    stable_value_id,
)


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "model",
        "category",
        "filter_group:Διαγώνιος Οθόνης  (Ίντσες)",
        "filter_group:Χρώμα",
        "filter_group:Μνήμη Ram",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _sample_rows() -> list[dict[str, str]]:
    category = (
        "ΠΛΗΡΟΦΟΡΙΚΗ:::ΠΛΗΡΟΦΟΡΙΚΗ///Υπολογιστές:::ΠΛΗΡΟΦΟΡΙΚΗ///Υπολογιστές///Laptops"
    )
    return [
        {
            "model": "A",
            "category": category,
            "filter_group:Διαγώνιος Οθόνης  (Ίντσες)": "15.6",
            "filter_group:Χρώμα": "Μαύρο",
            "filter_group:Μνήμη Ram": "16 GB",
        },
        {
            "model": "B",
            "category": category,
            "filter_group:Διαγώνιος Οθόνης  (Ίντσες)": " 17.3 ",
            "filter_group:Χρώμα": "λευκό",
            "filter_group:Μνήμη Ram": "",
        },
    ]


def _only_category(payload: dict) -> dict:
    return payload["subcategories"][0]


def _only_group(category: dict, name: str) -> dict:
    return next(group for group in category["filter_groups"] if group["name"] == name)


def _make_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "csv_path": tmp_path / "full_catalog_with_filters.csv",
        "base_path": tmp_path / "filter_map.base.json",
        "manual_path": tmp_path / "filter_map.manual_overrides.json",
        "filter_map_path": tmp_path / "filter_map.json",
        "report_path": tmp_path / "filter_map.sync_report.json",
    }


def test_csv_bootstrap_writes_object_only_filter_groups(tmp_path: Path) -> None:
    csv_path = tmp_path / "filters.csv"
    _write_csv(csv_path, _sample_rows())

    base, _report = build_base_from_csv(csv_path, tmp_path / "missing_filter_map.json")
    category = _only_category(base)

    assert category["filter_groups"]
    assert all(isinstance(group, dict) for group in category["filter_groups"])
    assert all(
        "group_id" in group and "values" in group for group in category["filter_groups"]
    )


def test_csv_bootstrap_preserves_exact_group_spelling_internal_spacing(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "filters.csv"
    _write_csv(csv_path, _sample_rows())

    base, _report = build_base_from_csv(csv_path, tmp_path / "missing_filter_map.json")
    names = [group["name"] for group in _only_category(base)["filter_groups"]]

    assert "Διαγώνιος Οθόνης  (Ίντσες)" in names
    assert "Διαγώνιος Οθόνης (Ίντσες)" not in names


def test_csv_bootstrap_preserves_exact_values_decimals_casing_and_accents(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "filters.csv"
    _write_csv(csv_path, _sample_rows())

    base, _report = build_base_from_csv(csv_path, tmp_path / "missing_filter_map.json")
    category = _only_category(base)

    screen_group = _only_group(category, "Διαγώνιος Οθόνης  (Ίντσες)")
    color_group = _only_group(category, "Χρώμα")
    assert [value["value"] for value in screen_group["values"]] == ["15.6", "17.3"]
    assert [value["value"] for value in color_group["values"]] == ["Μαύρο", "λευκό"]


def test_category_parsing_uses_first_deepest_path_when_needed(tmp_path: Path) -> None:
    csv_path = tmp_path / "filters.csv"
    _write_csv(
        csv_path,
        [
            {
                "model": "A",
                "category": "A:::A///B:::A///B///C:::X:::X///Y:::X///Y///Z",
                "filter_group:Διαγώνιος Οθόνης  (Ίντσες)": "10",
                "filter_group:Χρώμα": "",
                "filter_group:Μνήμη Ram": "",
            }
        ],
    )

    base, report = build_base_from_csv(csv_path, tmp_path / "missing_filter_map.json")

    assert _only_category(base)["path"] == "A > B > C"
    assert report["first_deepest_fallback_rows"][0]["selected_path"] == "A > B > C"


def test_category_parsing_uses_existing_map_fallback_for_one_existing_deepest_path(
    tmp_path: Path,
) -> None:
    existing_map = {
        "subcategories": [
            {
                "path": "X > Y > Z",
                "filter_groups": [],
            }
        ]
    }
    existing_path = tmp_path / "filter_map.json"
    existing_path.write_text(
        json.dumps(existing_map, ensure_ascii=False), encoding="utf-8"
    )
    csv_path = tmp_path / "filters.csv"
    _write_csv(
        csv_path,
        [
            {
                "model": "A",
                "category": "A///B///C:::X///Y///Z",
                "filter_group:Διαγώνιος Οθόνης  (Ίντσες)": "10",
                "filter_group:Χρώμα": "",
                "filter_group:Μνήμη Ram": "",
            }
        ],
    )

    base, report = build_base_from_csv(csv_path, existing_path)

    assert _only_category(base)["path"] == "X > Y > Z"
    assert report["existing_map_fallback_rows"][0]["selected_path"] == "X > Y > Z"


def test_stable_category_id_generation_is_deterministic() -> None:
    path = "ΠΛΗΡΟΦΟΡΙΚΗ > Υπολογιστές > Laptops"
    assert stable_category_id(path) == stable_category_id(path)
    assert stable_category_id(path).startswith("cat_")


def test_stable_group_id_generation_is_deterministic() -> None:
    category_id = stable_category_id("ΠΛΗΡΟΦΟΡΙΚΗ > Υπολογιστές > Laptops")
    assert stable_group_id(category_id, "Μνήμη Ram") == stable_group_id(
        category_id, "Μνήμη Ram"
    )
    assert stable_group_id(category_id, "Μνήμη Ram").startswith("fg_")


def test_stable_value_id_generation_is_deterministic() -> None:
    category_id = stable_category_id("ΠΛΗΡΟΦΟΡΙΚΗ > Υπολογιστές > Laptops")
    group_id = stable_group_id(category_id, "Μνήμη Ram")
    assert stable_value_id(group_id, "16 GB") == stable_value_id(group_id, "16 GB")
    assert stable_value_id(group_id, "16 GB").startswith("fv_")


def test_final_base_contains_no_legacy_string_list_filter_groups(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "filters.csv"
    _write_csv(csv_path, _sample_rows())

    base, _report = build_base_from_csv(csv_path, tmp_path / "missing_filter_map.json")

    for category in base["subcategories"]:
        assert all(not isinstance(group, str) for group in category["filter_groups"])


def test_manual_overrides_are_applied_after_base_and_can_add_values(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path)
    _write_csv(paths["csv_path"], _sample_rows())
    run_bootstrap(**paths, write=True)
    base = json.loads(paths["base_path"].read_text(encoding="utf-8"))
    category = _only_category(base)
    group = _only_group(category, "Μνήμη Ram")
    new_value_id = stable_value_id(group["group_id"], "32 GB")
    manual = default_manual_overrides()
    manual["categories"] = {
        category["category_id"]: {
            "category_id": category["category_id"],
            "path": category["path"],
            "groups": {
                group["group_id"]: {
                    "group_id": group["group_id"],
                    "name": group["name"],
                    "required": group["required"],
                    "status": group["status"],
                    "values": {
                        new_value_id: {
                            "value_id": new_value_id,
                            "value": "32 GB",
                            "status": "active",
                        }
                    },
                }
            },
        }
    }
    paths["manual_path"].write_text(
        json.dumps(manual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    run_apply_overrides(
        base_path=paths["base_path"],
        manual_path=paths["manual_path"],
        filter_map_path=paths["filter_map_path"],
        report_path=paths["report_path"],
        write=True,
    )
    final = json.loads(paths["filter_map_path"].read_text(encoding="utf-8"))
    values = _only_group(_only_category(final), "Μνήμη Ram")["values"]

    assert any(value["value"] == "32 GB" for value in values)


def test_manual_overrides_win_conflicts(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _write_csv(paths["csv_path"], _sample_rows())
    run_bootstrap(**paths, write=True)
    base = json.loads(paths["base_path"].read_text(encoding="utf-8"))
    category = _only_category(base)
    group = _only_group(category, "Μνήμη Ram")
    value = group["values"][0]
    manual = default_manual_overrides()
    manual["categories"] = {
        category["category_id"]: {
            "category_id": category["category_id"],
            "path": category["path"],
            "groups": {
                group["group_id"]: {
                    "group_id": group["group_id"],
                    "name": "Μνήμη RAM",
                    "required": False,
                    "status": "inactive",
                    "values": {
                        value["value_id"]: {
                            "value_id": value["value_id"],
                            "value": value["value"],
                            "status": "deprecated",
                        }
                    },
                }
            },
        }
    }
    paths["manual_path"].write_text(
        json.dumps(manual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    run_apply_overrides(
        base_path=paths["base_path"],
        manual_path=paths["manual_path"],
        filter_map_path=paths["filter_map_path"],
        report_path=paths["report_path"],
        write=True,
    )
    final_group = _only_group(
        _only_category(
            json.loads(paths["filter_map_path"].read_text(encoding="utf-8"))
        ),
        "Μνήμη RAM",
    )

    assert final_group["required"] is False
    assert final_group["status"] == "inactive"
    assert final_group["values"][0]["status"] == "deprecated"


def test_manual_override_file_supports_active_inactive_deprecated_statuses(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path)
    _write_csv(paths["csv_path"], _sample_rows())
    run_bootstrap(**paths, write=True)
    base = json.loads(paths["base_path"].read_text(encoding="utf-8"))
    category = _only_category(base)
    group = _only_group(category, "Μνήμη Ram")
    active_value = group["values"][0]
    inactive_value_id = stable_value_id(group["group_id"], "64 GB")
    manual = default_manual_overrides()
    manual["categories"] = {
        category["category_id"]: {
            "category_id": category["category_id"],
            "path": category["path"],
            "groups": {
                group["group_id"]: {
                    "group_id": group["group_id"],
                    "name": group["name"],
                    "status": "deprecated",
                    "values": {
                        active_value["value_id"]: {
                            "value_id": active_value["value_id"],
                            "value": active_value["value"],
                            "status": "active",
                        },
                        inactive_value_id: {
                            "value_id": inactive_value_id,
                            "value": "64 GB",
                            "status": "inactive",
                        },
                    },
                }
            },
        }
    }
    paths["manual_path"].write_text(
        json.dumps(manual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    run_apply_overrides(
        base_path=paths["base_path"],
        manual_path=paths["manual_path"],
        filter_map_path=paths["filter_map_path"],
        report_path=paths["report_path"],
        write=True,
    )
    group = _only_group(
        _only_category(
            json.loads(paths["filter_map_path"].read_text(encoding="utf-8"))
        ),
        "Μνήμη Ram",
    )

    assert group["status"] == "deprecated"
    assert {value["status"] for value in group["values"]} >= {"active", "inactive"}


def test_manual_override_file_preserves_value_aliases(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _write_csv(paths["csv_path"], _sample_rows())
    run_bootstrap(**paths, write=True)
    base = json.loads(paths["base_path"].read_text(encoding="utf-8"))
    category = _only_category(base)
    group = _only_group(category, "Μνήμη Ram")
    value = group["values"][0]
    manual = default_manual_overrides()
    manual["categories"] = {
        category["category_id"]: {
            "category_id": category["category_id"],
            "path": category["path"],
            "groups": {
                group["group_id"]: {
                    "group_id": group["group_id"],
                    "name": group["name"],
                    "values": {
                        value["value_id"]: {
                            "value_id": value["value_id"],
                            "value": value["value"],
                            "status": "active",
                            "aliases": ["16 gigabyte", " 16GB "],
                        },
                    },
                }
            },
        }
    }
    paths["manual_path"].write_text(
        json.dumps(manual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    run_apply_overrides(
        base_path=paths["base_path"],
        manual_path=paths["manual_path"],
        filter_map_path=paths["filter_map_path"],
        report_path=paths["report_path"],
        write=True,
    )
    group = _only_group(
        _only_category(
            json.loads(paths["filter_map_path"].read_text(encoding="utf-8"))
        ),
        "Μνήμη Ram",
    )

    assert group["values"][0]["aliases"] == ["16 gigabyte", "16GB"]


def test_csv_derived_groups_and_values_have_default_statuses(tmp_path: Path) -> None:
    csv_path = tmp_path / "filters.csv"
    _write_csv(csv_path, _sample_rows())

    base, _report = build_base_from_csv(csv_path, tmp_path / "missing_filter_map.json")

    for group in _only_category(base)["filter_groups"]:
        assert group["required"] is True
        assert group["status"] == "active"
        assert all(value["status"] == "active" for value in group["values"])


def test_csv_derived_values_default_to_active_status(tmp_path: Path) -> None:
    csv_path = tmp_path / "filters.csv"
    _write_csv(csv_path, _sample_rows())

    base, _report = build_base_from_csv(csv_path, tmp_path / "missing_filter_map.json")
    values = [
        value
        for group in _only_category(base)["filter_groups"]
        for value in group["values"]
    ]

    assert values
    assert {value["status"] for value in values} == {"active"}


def test_apply_overrides_mode_works_without_full_catalog_csv(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _write_csv(paths["csv_path"], _sample_rows())
    run_bootstrap(**paths, write=True)
    paths["csv_path"].unlink()

    result = run_apply_overrides(
        base_path=paths["base_path"],
        manual_path=paths["manual_path"],
        filter_map_path=paths["filter_map_path"],
        report_path=paths["report_path"],
        write=True,
    )

    assert result == 0
    assert paths["filter_map_path"].exists()


def test_final_filter_map_generation_is_deterministic(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _write_csv(paths["csv_path"], _sample_rows())
    run_bootstrap(**paths, write=True)

    first = paths["filter_map_path"].read_bytes()
    run_apply_overrides(
        base_path=paths["base_path"],
        manual_path=paths["manual_path"],
        filter_map_path=paths["filter_map_path"],
        report_path=paths["report_path"],
        write=True,
    )
    second = paths["filter_map_path"].read_bytes()

    assert first == second


def test_sync_report_contains_counts_and_fallback_decisions(tmp_path: Path) -> None:
    csv_path = tmp_path / "filters.csv"
    _write_csv(
        csv_path,
        [
            {
                "model": "A",
                "category": "A///B///C:::X///Y///Z",
                "filter_group:Διαγώνιος Οθόνης  (Ίντσες)": "10",
                "filter_group:Χρώμα": "",
                "filter_group:Μνήμη Ram": "",
            }
        ],
    )

    _base, report = build_base_from_csv(csv_path, tmp_path / "missing_filter_map.json")

    assert report["rows_read"] == 1
    assert report["filter_columns_seen"] == 3
    assert report["categories_seen"] == 1
    assert report["groups_seen"] == 1
    assert report["values_seen"] == 1
    assert report["first_deepest_fallback_rows"]
