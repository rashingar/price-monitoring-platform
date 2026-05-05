from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from tools.schema_registry.build_electronet_schema_library import (
    DEFAULT_OUTPUT_PATH as DEFAULT_LIBRARY_PATH,
    REPO_ROOT,
    load_json,
    normalize_whitespace,
)


DEFAULT_INDEX_PATH = REPO_ROOT / "resources" / "schemas" / "schema_index.csv"
FIELDNAMES = [
    "schema_id",
    "template_id",
    "authored_template_id",
    "category_path",
    "parent_category",
    "leaf_category",
    "sub_category",
    "category_gr",
    "cta_map_key",
    "cta_url",
    "template_status",
    "subcategory_match_policy",
    "match_mode",
    "template_file",
    "fingerprint",
    "n_sections",
    "n_rows_total",
    "last_section",
    "last_label",
    "example_count",
    "first_example",
]
REQUIRED_SCHEMA_FIELDS = {
    "schema_id",
    "template_id",
    "authored_template_id",
    "category_path",
    "parent_category",
    "leaf_category",
    "category_gr",
    "cta_map_key",
    "cta_url",
    "template_status",
    "subcategory_match_policy",
    "match_mode",
    "fingerprint",
    "source_template_file",
    "n_sections",
    "n_rows_total",
    "sentinel",
}


def load_compiled_library(library_path: Path) -> dict[str, Any]:
    payload = load_json(library_path)
    if not isinstance(payload, dict):
        raise ValueError(f"Compiled library must be a JSON object: {library_path}")
    schemas = payload.get("schemas")
    if not isinstance(schemas, list):
        raise ValueError(f"Compiled library is missing a schemas array: {library_path}")
    return payload


def _expect_scalar(schema: dict[str, Any], key: str) -> str:
    value = schema.get(key)
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value)
    raise ValueError(f"schema {schema.get('schema_id', '<unknown>')}: field {key!r} must be scalar")


def _expect_int(schema: dict[str, Any], key: str) -> int:
    value = schema.get(key)
    if not isinstance(value, int):
        raise ValueError(f"schema {schema.get('schema_id', '<unknown>')}: field {key!r} must be an integer")
    return value


def _flatten_examples(schema: dict[str, Any]) -> tuple[int, str]:
    examples = schema.get("electronet_examples", [])
    if examples is None:
        return 0, ""
    if not isinstance(examples, list):
        raise ValueError(f"schema {schema.get('schema_id', '<unknown>')}: electronet_examples must be a list")
    normalized = [normalize_whitespace(item) for item in examples if normalize_whitespace(item)]
    return len(normalized), (normalized[0] if normalized else "")


def _flatten_sentinel(schema: dict[str, Any]) -> tuple[str, str]:
    sentinel = schema.get("sentinel")
    if not isinstance(sentinel, dict):
        raise ValueError(f"schema {schema.get('schema_id', '<unknown>')}: sentinel must be an object")
    last_section = normalize_whitespace(sentinel.get("last_section"))
    last_label = normalize_whitespace(sentinel.get("last_label"))
    return last_section, last_label


def flatten_schema_entry(schema: dict[str, Any]) -> dict[str, str | int]:
    missing = sorted(REQUIRED_SCHEMA_FIELDS - set(schema))
    if missing:
        raise ValueError(
            f"schema {schema.get('schema_id', '<unknown>')} is missing required field(s): {', '.join(missing)}"
        )

    last_section, last_label = _flatten_sentinel(schema)
    example_count, first_example = _flatten_examples(schema)

    row: dict[str, str | int] = {
        "schema_id": _expect_scalar(schema, "schema_id"),
        "template_id": _expect_scalar(schema, "template_id"),
        "authored_template_id": _expect_scalar(schema, "authored_template_id"),
        "category_path": _expect_scalar(schema, "category_path"),
        "parent_category": _expect_scalar(schema, "parent_category"),
        "leaf_category": _expect_scalar(schema, "leaf_category"),
        "sub_category": _expect_scalar(schema, "sub_category"),
        "category_gr": _expect_scalar(schema, "category_gr"),
        "cta_map_key": _expect_scalar(schema, "cta_map_key"),
        "cta_url": _expect_scalar(schema, "cta_url"),
        "template_status": _expect_scalar(schema, "template_status"),
        "subcategory_match_policy": _expect_scalar(schema, "subcategory_match_policy"),
        "match_mode": _expect_scalar(schema, "match_mode"),
        "template_file": _expect_scalar(schema, "source_template_file"),
        "fingerprint": _expect_scalar(schema, "fingerprint"),
        "n_sections": _expect_int(schema, "n_sections"),
        "n_rows_total": _expect_int(schema, "n_rows_total"),
        "last_section": last_section,
        "last_label": last_label,
        "example_count": example_count,
        "first_example": first_example,
    }

    return row


def build_rows(payload: dict[str, Any]) -> list[dict[str, str | int]]:
    rows = [flatten_schema_entry(schema) for schema in payload["schemas"]]

    seen_schema_ids: set[str] = set()
    for row in rows:
        schema_id = str(row["schema_id"])
        if schema_id in seen_schema_ids:
            raise ValueError(f"Duplicate schema_id in compiled library: {schema_id}")
        seen_schema_ids.add(schema_id)

    rows.sort(
        key=lambda row: (
            str(row["category_path"]),
            str(row["template_status"]),
            str(row["template_id"]),
            str(row["schema_id"]),
        )
    )
    return rows


def write_csv(rows: list[dict[str, str | int]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    payload = load_compiled_library(DEFAULT_LIBRARY_PATH)
    rows = build_rows(payload)
    write_csv(rows, DEFAULT_INDEX_PATH)


if __name__ == "__main__":
    main()
