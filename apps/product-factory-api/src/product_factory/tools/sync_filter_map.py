from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import sys
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any

from product_factory.repo_paths import (
    FILTER_MAP_BASE_PATH,
    FILTER_MAP_MANUAL_OVERRIDES_PATH,
    FILTER_MAP_PATH,
    FILTER_MAP_SYNC_REPORT_PATH,
    FULL_CATALOG_WITH_FILTERS_PATH,
)

FILTER_PREFIX = "filter_group:"
VALID_STATUSES = {"active", "inactive", "deprecated"}
INVALID_MANUAL_OVERRIDES_MESSAGE = "Manual filter override JSON is invalid. Restore from backup or fix the file."


class InvalidFilterOverrideJsonError(ValueError):
    def __init__(self, path: Path, detail: str) -> None:
        super().__init__(f"{INVALID_MANUAL_OVERRIDES_MESSAGE} Path: {path}. Detail: {detail}")
        self.path = path
        self.detail = detail


def stable_category_id(canonical_category_path: str) -> str:
    return "cat_" + _sha1(canonical_category_path)[:12]


def stable_group_id(category_id: str, group_name: str) -> str:
    return "fg_" + _sha1(f"{category_id}::{group_name}")[:12]


def stable_value_id(group_id: str, value: str) -> str:
    return "fv_" + _sha1(f"{group_id}::{value}")[:12]


def _sha1(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _trim_outer(value: Any) -> str:
    return str(value or "").strip()


def canonicalize_category_path(path: str) -> str:
    return " > ".join(segment.strip() for segment in path.split(">") if segment.strip())


def _canonical_path_from_assignment(assignment: str) -> str:
    segments = [_trim_outer(segment) for segment in assignment.split("///")]
    segments = [segment for segment in segments if segment]
    if len(segments) < 2:
        return ""
    return " > ".join(segments[:3])


def parse_category_assignments(category_value: str) -> list[dict[str, Any]]:
    assignments: list[dict[str, Any]] = []
    for raw_assignment in str(category_value or "").split(":::"):
        raw_assignment = raw_assignment.strip()
        if not raw_assignment:
            continue
        depth = len([segment for segment in raw_assignment.split("///") if segment.strip()])
        path = _canonical_path_from_assignment(raw_assignment)
        if path:
            assignments.append({"raw": raw_assignment, "depth": depth, "path": path})
    return assignments


def select_category_path(
    category_value: str,
    *,
    row_number: int,
    existing_paths: set[str],
    report: dict[str, Any],
) -> str:
    assignments = parse_category_assignments(category_value)
    if not assignments:
        report["warnings"].append({"row": row_number, "message": "No usable category path found."})
        return ""

    max_depth = max(item["depth"] for item in assignments)
    deepest_paths = list(OrderedDict.fromkeys(item["path"] for item in assignments if item["depth"] == max_depth))
    if len(deepest_paths) == 1:
        return deepest_paths[0]

    existing_matches = [path for path in deepest_paths if path in existing_paths]
    if len(existing_matches) == 1:
        chosen = existing_matches[0]
        report["existing_map_fallback_rows"].append(
            {"row": row_number, "candidates": deepest_paths, "selected_path": chosen}
        )
        return chosen

    chosen = deepest_paths[0]
    report["first_deepest_fallback_rows"].append(
        {"row": row_number, "candidates": deepest_paths, "selected_path": chosen}
    )
    return chosen


def _category_parts(path: str) -> dict[str, str]:
    parts = [part.strip() for part in path.split(">")]
    parent = parts[0] if len(parts) >= 1 else ""
    leaf = parts[1] if len(parts) >= 2 else ""
    sub = " > ".join(parts[2:]) if len(parts) >= 3 else ""
    return {
        "key": sub or leaf,
        "parent_category": parent,
        "leaf_category": leaf,
        "sub_category": sub,
    }


def _new_category(path: str) -> dict[str, Any]:
    path = canonicalize_category_path(path)
    category_id = stable_category_id(path)
    parts = _category_parts(path)
    return {
        "category_id": category_id,
        "key": parts["key"],
        "parent_category": parts["parent_category"],
        "leaf_category": parts["leaf_category"],
        "sub_category": parts["sub_category"],
        "path": path,
        "url": "",
        "filter_groups": [],
    }


def _new_group(category_id: str, group_name: str) -> dict[str, Any]:
    group_name = _trim_outer(group_name)
    return {
        "group_id": stable_group_id(category_id, group_name),
        "name": group_name,
        "required": True,
        "status": "active",
        "values": [],
    }


def _new_value(group_id: str, value: str) -> dict[str, str]:
    value = _trim_outer(value)
    return {
        "value_id": stable_value_id(group_id, value),
        "value": value,
        "status": "active",
    }


def _normalized_aliases(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        alias = _trim_outer(item)
        if alias and alias not in out:
            out.append(alias)
    return out


def _filter_columns(headers: list[str]) -> list[tuple[str, str]]:
    return [(header, header[len(FILTER_PREFIX) :]) for header in headers if header.startswith(FILTER_PREFIX)]


def _existing_paths_from_map(path: Path) -> set[str]:
    payload = _read_json(path, default={}) or {}
    paths = set()
    for item in payload.get("subcategories", []):
        item_path = item.get("path")
        if item_path:
            paths.add(canonicalize_category_path(item_path))
    return paths


def build_base_from_csv(csv_path: Path, existing_map_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    existing_paths = _existing_paths_from_map(existing_map_path)
    report = new_report("bootstrap-from-csv", csv_path=csv_path)

    if not csv_path.exists():
        raise FileNotFoundError(f"Bootstrap CSV not found: {csv_path}")

    categories: OrderedDict[str, dict[str, Any]] = OrderedDict()
    seen_groups: set[str] = set()
    seen_values: set[str] = set()

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        filter_columns = _filter_columns(headers)
        report["filter_columns_seen"] = len(filter_columns)
        if "category" not in headers:
            report["warnings"].append({"message": "CSV has no category column."})

        for row_index, row in enumerate(reader, start=2):
            report["rows_read"] += 1
            selected_path = select_category_path(
                row.get("category", ""),
                row_number=row_index,
                existing_paths=existing_paths,
                report=report,
            )
            if not selected_path:
                continue

            category = categories.get(selected_path)
            if category is None:
                category = _new_category(selected_path)
                category["_group_index"] = OrderedDict()
                categories[selected_path] = category

            group_index: OrderedDict[str, dict[str, Any]] = category["_group_index"]
            for column_name, group_name in filter_columns:
                value = _trim_outer(row.get(column_name, ""))
                if not value:
                    continue
                display_group_name = _trim_outer(group_name)
                group = group_index.get(display_group_name)
                if group is None:
                    group = _new_group(category["category_id"], display_group_name)
                    group["_value_index"] = OrderedDict()
                    group_index[display_group_name] = group
                    category["filter_groups"].append(group)
                    seen_groups.add(group["group_id"])

                value_index: OrderedDict[str, dict[str, str]] = group["_value_index"]
                if value not in value_index:
                    value_obj = _new_value(group["group_id"], value)
                    value_index[value] = value_obj
                    group["values"].append(value_obj)
                    seen_values.add(value_obj["value_id"])

    for category in categories.values():
        category.pop("_group_index", None)
        for group in category["filter_groups"]:
            group.pop("_value_index", None)

    report["categories_seen"] = len(categories)
    report["categories_updated"] = len([path for path in categories if path in existing_paths])
    report["categories_added"] = len([path for path in categories if path not in existing_paths])
    report["groups_seen"] = len(seen_groups)
    report["values_seen"] = len(seen_values)

    base = build_filter_map_payload(categories.values(), source="csv-bootstrap")
    return base, report


def default_manual_overrides() -> dict[str, Any]:
    return {
        "meta": {
            "description": "Manual overrides layered on top of filter_map.base.json to generate filter_map.json.",
            "schema_version": 1,
        },
        "metadata": {
            "schema_version": 1,
            "updated_at": "",
            "revision": "",
            "last_operation": "",
        },
        "categories": {},
    }


def read_filter_map_json(path: Path) -> dict[str, Any]:
    payload = _read_json(path, default=None)
    if payload is None:
        raise FileNotFoundError(f"Filter map JSON not found: {path}")
    return payload


def read_json_file(path: Path, default: Any | None = None) -> Any:
    return _read_json(path, default=default)


def write_json_file(path: Path, payload: Any) -> None:
    _write_json(path, payload)


def write_filter_map_json(path: Path, payload: dict[str, Any]) -> None:
    _write_json(path, payload)


def write_manual_overrides(path: Path, payload: dict[str, Any]) -> None:
    _write_json(path, payload)


def load_manual_overrides(path: Path) -> dict[str, Any]:
    try:
        payload = _read_json(path, default=None)
    except json.JSONDecodeError as exc:
        raise InvalidFilterOverrideJsonError(path, str(exc)) from exc
    if payload is None:
        return default_manual_overrides()
    if not isinstance(payload, dict):
        raise InvalidFilterOverrideJsonError(path, "Top-level payload must be a JSON object.")
    payload.setdefault("meta", default_manual_overrides()["meta"])
    payload.setdefault("metadata", default_manual_overrides()["metadata"])
    payload.setdefault("categories", {})
    if not isinstance(payload["meta"], dict):
        raise InvalidFilterOverrideJsonError(path, "Field 'meta' must be a JSON object.")
    if not isinstance(payload["metadata"], dict):
        raise InvalidFilterOverrideJsonError(path, "Field 'metadata' must be a JSON object.")
    if not isinstance(payload["categories"], dict):
        raise InvalidFilterOverrideJsonError(path, "Field 'categories' must be a JSON object.")
    return payload


def apply_manual_overrides(
    base_payload: dict[str, Any],
    manual_payload: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    categories = OrderedDict((category["category_id"], copy.deepcopy(category)) for category in base_payload.get("subcategories", []))
    report["manual_override_categories"] = len(manual_payload.get("categories", {}))

    for category_id, category_override in manual_payload.get("categories", {}).items():
        if category_override.get("category_id") and category_override["category_id"] != category_id:
            report["warnings"].append(
                {"category_id": category_id, "message": "Override key does not match category_id field."}
            )
        path = canonicalize_category_path(category_override.get("path", ""))
        category = categories.get(category_id)
        if category is None:
            if not path:
                report["warnings"].append(
                    {"category_id": category_id, "message": "Cannot add override category without a path."}
                )
                continue
            category = _new_category(path)
            category["category_id"] = category_id
            categories[category_id] = category
        elif path and path != category.get("path"):
            category.update(_category_parts(path))
            category["path"] = path

        groups_by_id = OrderedDict((group["group_id"], group) for group in category.get("filter_groups", []))
        for group_id, group_override in category_override.get("groups", {}).items():
            report["manual_override_groups"] += 1
            _validate_status(group_override, "group", group_id, report)
            group = groups_by_id.get(group_id)
            if group is None:
                group_name = _trim_outer(group_override.get("name", ""))
                if not group_name:
                    report["warnings"].append(
                        {"category_id": category_id, "group_id": group_id, "message": "Cannot add group without name."}
                    )
                    continue
                group = {
                    "group_id": group_id,
                    "name": group_name,
                    "required": bool(group_override.get("required", True)),
                    "status": group_override.get("status", "active"),
                    "values": [],
                }
                category.setdefault("filter_groups", []).append(group)
                groups_by_id[group_id] = group
                report["overridden_groups"].append(
                    {"category_id": category_id, "group_id": group_id, "field": "added"}
                )
            else:
                for field in ("name", "required", "status"):
                    if field in group_override and group.get(field) != group_override[field]:
                        group[field] = group_override[field]
                        report["overridden_groups"].append(
                            {"category_id": category_id, "group_id": group_id, "field": field}
                        )

            values_by_id = OrderedDict((value["value_id"], value) for value in group.get("values", []))
            value_overrides = group_override.get("values", {})
            for value_id, value_override in value_overrides.items():
                report["manual_override_values"] += 1
                _validate_status(value_override, "value", value_id, report)
                value = values_by_id.get(value_id)
                if value is None:
                    display_value = _trim_outer(value_override.get("value", ""))
                    if not display_value:
                        report["warnings"].append(
                            {
                                "category_id": category_id,
                                "group_id": group_id,
                                "value_id": value_id,
                                "message": "Cannot add value without display value.",
                            }
                        )
                        continue
                    value = {
                        "value_id": value_id,
                        "value": display_value,
                        "status": value_override.get("status", "active"),
                    }
                    aliases = _normalized_aliases(value_override.get("aliases"))
                    if aliases:
                        value["aliases"] = aliases
                    group.setdefault("values", []).append(value)
                    values_by_id[value_id] = value
                    report["overridden_values"].append(
                        {"category_id": category_id, "group_id": group_id, "value_id": value_id, "field": "added"}
                    )
                else:
                    for field in ("value", "status", "aliases"):
                        if field not in value_override:
                            continue
                        override_value = _normalized_aliases(value_override[field]) if field == "aliases" else value_override[field]
                        if field == "aliases" and not override_value:
                            value.pop("aliases", None)
                        elif value.get(field) != override_value:
                            value[field] = override_value
                            report["overridden_values"].append(
                                {
                                    "category_id": category_id,
                                    "group_id": group_id,
                                    "value_id": value_id,
                                    "field": field,
                                }
                            )

            override_value_ids = [value_id for value_id in value_overrides if value_id in values_by_id]
            if override_value_ids:
                reordered_values = [values_by_id[value_id] for value_id in override_value_ids]
                override_value_id_set = set(override_value_ids)
                reordered_values.extend(value for value in group.get("values", []) if value.get("value_id") not in override_value_id_set)
                if [value.get("value_id") for value in group.get("values", [])] != [value.get("value_id") for value in reordered_values]:
                    group["values"] = reordered_values
                    report["overridden_groups"].append(
                        {"category_id": category_id, "group_id": group_id, "field": "value_order"}
                    )

    return build_filter_map_payload(categories.values(), source="base-plus-manual-overrides")


def _validate_status(payload: dict[str, Any], kind: str, item_id: str, report: dict[str, Any]) -> None:
    status = payload.get("status")
    if status is not None and status not in VALID_STATUSES:
        report["warnings"].append({"id": item_id, "kind": kind, "message": f"Unknown status: {status}"})


def build_filter_map_payload(categories: Any, *, source: str) -> dict[str, Any]:
    subcategories = [_clean_category_for_output(category) for category in categories]
    by_key: OrderedDict[str, dict[str, Any]] = OrderedDict()
    by_id: OrderedDict[str, dict[str, Any]] = OrderedDict()
    by_path: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for category in subcategories:
        by_key[category["key"]] = category
        by_id[category["category_id"]] = category
        by_path[category["path"]] = category
    return {
        "meta": {
            "description": "Generated filter map. Do not edit directly; run product_factory.tools.sync_filter_map.",
            "schema_version": 1,
            "source": source,
        },
        "subcategories": subcategories,
        "by_sub_category_key": by_key,
        "by_category_id": by_id,
        "by_path": by_path,
    }


def _clean_category_for_output(category: dict[str, Any]) -> dict[str, Any]:
    cleaned = {
        "category_id": category["category_id"],
        "key": category.get("key", ""),
        "parent_category": category.get("parent_category", ""),
        "leaf_category": category.get("leaf_category", ""),
        "sub_category": category.get("sub_category", ""),
        "path": category.get("path", ""),
        "url": category.get("url", ""),
        "filter_groups": [],
    }
    for group in category.get("filter_groups", []):
        values: list[dict[str, Any]] = []
        for value in group.get("values", []):
            cleaned_value = {
                "value_id": value["value_id"],
                "value": value.get("value", ""),
                "status": value.get("status", "active"),
            }
            aliases = _normalized_aliases(value.get("aliases"))
            if aliases:
                cleaned_value["aliases"] = aliases
            values.append(cleaned_value)
        cleaned["filter_groups"].append(
            {
                "group_id": group["group_id"],
                "name": group.get("name", ""),
                "required": bool(group.get("required", True)),
                "status": group.get("status", "active"),
                "values": values,
            }
        )
    return cleaned


def new_report(mode: str, *, csv_path: Path | None = None) -> dict[str, Any]:
    return {
        "mode": mode,
        "csv_path": str(csv_path) if csv_path else "",
        "base_path": str(FILTER_MAP_BASE_PATH),
        "manual_overrides_path": str(FILTER_MAP_MANUAL_OVERRIDES_PATH),
        "filter_map_path": str(FILTER_MAP_PATH),
        "rows_read": 0,
        "filter_columns_seen": 0,
        "categories_seen": 0,
        "categories_updated": 0,
        "categories_added": 0,
        "groups_seen": 0,
        "values_seen": 0,
        "manual_override_categories": 0,
        "manual_override_groups": 0,
        "manual_override_values": 0,
        "existing_map_fallback_rows": [],
        "first_deepest_fallback_rows": [],
        "overridden_groups": [],
        "overridden_values": [],
        "warnings": [],
    }


def _with_report_paths(report: dict[str, Any], *, base_path: Path, manual_path: Path, filter_map_path: Path) -> dict[str, Any]:
    report["base_path"] = str(base_path)
    report["manual_overrides_path"] = str(manual_path)
    report["filter_map_path"] = str(filter_map_path)
    return report


def run_bootstrap(
    *,
    csv_path: Path,
    base_path: Path,
    manual_path: Path,
    filter_map_path: Path,
    report_path: Path,
    write: bool,
) -> int:
    base_payload, report = build_base_from_csv(csv_path, filter_map_path)
    report = _with_report_paths(report, base_path=base_path, manual_path=manual_path, filter_map_path=filter_map_path)
    manual_payload = load_manual_overrides(manual_path)
    final_payload = apply_manual_overrides(base_payload, manual_payload, report)

    if write:
        expected = {
            base_path: base_payload,
            manual_path: manual_payload,
            filter_map_path: final_payload,
            report_path: report,
        }
        for path, payload in expected.items():
            _write_json(path, payload)
        print(f"Wrote filter map bootstrap outputs to {filter_map_path}")
        return 0
    expected = {
        base_path: base_payload,
        manual_path: manual_payload,
        filter_map_path: final_payload,
    }
    return _check_files(expected)


def run_apply_overrides(
    *,
    base_path: Path,
    manual_path: Path,
    filter_map_path: Path,
    report_path: Path,
    write: bool,
) -> int:
    base_payload = _read_json(base_path, default=None)
    if base_payload is None:
        raise FileNotFoundError(f"Base filter map not found: {base_path}")
    manual_payload = load_manual_overrides(manual_path)
    report = _with_report_paths(
        new_report("apply-overrides"),
        base_path=base_path,
        manual_path=manual_path,
        filter_map_path=filter_map_path,
    )
    report["categories_seen"] = len(base_payload.get("subcategories", []))
    report["groups_seen"] = sum(len(category.get("filter_groups", [])) for category in base_payload.get("subcategories", []))
    report["values_seen"] = sum(
        len(group.get("values", []))
        for category in base_payload.get("subcategories", [])
        for group in category.get("filter_groups", [])
    )
    final_payload = apply_manual_overrides(base_payload, manual_payload, report)

    if write:
        expected = {
            manual_path: manual_payload,
            filter_map_path: final_payload,
            report_path: report,
        }
        for path, payload in expected.items():
            _write_json(path, payload)
        print(f"Wrote generated filter map to {filter_map_path}")
        return 0
    expected = {
        manual_path: manual_payload,
        filter_map_path: final_payload,
    }
    return _check_files(expected)


def regenerate_filter_map_from_overrides(
    *,
    base_path: Path,
    manual_path: Path,
    filter_map_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    base_payload = read_filter_map_json(base_path)
    manual_payload = load_manual_overrides(manual_path)
    report = _with_report_paths(
        new_report("apply-overrides"),
        base_path=base_path,
        manual_path=manual_path,
        filter_map_path=filter_map_path,
    )
    report["categories_seen"] = len(base_payload.get("subcategories", []))
    report["groups_seen"] = sum(len(category.get("filter_groups", [])) for category in base_payload.get("subcategories", []))
    report["values_seen"] = sum(
        len(group.get("values", []))
        for category in base_payload.get("subcategories", [])
        for group in category.get("filter_groups", [])
    )
    final_payload = apply_manual_overrides(base_payload, manual_payload, report)
    write_filter_map_json(filter_map_path, final_payload)
    write_filter_map_json(report_path, report)
    return final_payload


def _check_files(expected: dict[Path, Any]) -> int:
    stale: list[str] = []
    for path, payload in expected.items():
        expected_bytes = _json_bytes(payload)
        actual_bytes = path.read_bytes() if path.exists() else None
        if actual_bytes != expected_bytes:
            stale.append(str(path))
    if stale:
        print("Filter map files are stale:", file=sys.stderr)
        for path in stale:
            print(f"- {path}", file=sys.stderr)
        return 1
    print("Filter map files are up to date.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Product-Agent filter map files.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--bootstrap-from-csv", action="store_true", help="Rebuild base map from full catalog CSV.")
    mode.add_argument("--apply-overrides", action="store_true", help="Regenerate final map from base plus overrides.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true", help="Write generated files.")
    action.add_argument("--check", action="store_true", help="Exit non-zero when generated files are stale.")
    parser.add_argument("--csv-path", type=Path, default=FULL_CATALOG_WITH_FILTERS_PATH)
    parser.add_argument("--base-path", type=Path, default=FILTER_MAP_BASE_PATH)
    parser.add_argument("--manual-overrides-path", type=Path, default=FILTER_MAP_MANUAL_OVERRIDES_PATH)
    parser.add_argument("--filter-map-path", type=Path, default=FILTER_MAP_PATH)
    parser.add_argument("--sync-report-path", type=Path, default=FILTER_MAP_SYNC_REPORT_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.bootstrap_from_csv:
        return run_bootstrap(
            csv_path=args.csv_path,
            base_path=args.base_path,
            manual_path=args.manual_overrides_path,
            filter_map_path=args.filter_map_path,
            report_path=args.sync_report_path,
            write=args.write,
        )
    return run_apply_overrides(
        base_path=args.base_path,
        manual_path=args.manual_overrides_path,
        filter_map_path=args.filter_map_path,
        report_path=args.sync_report_path,
        write=args.write,
    )


if __name__ == "__main__":
    raise SystemExit(main())
