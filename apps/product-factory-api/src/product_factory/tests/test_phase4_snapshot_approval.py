from __future__ import annotations

import csv
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from product_factory.seo_migration import (
    SNAPSHOT_PRODUCT_FIELDS,
    ApprovalValidationError,
    SnapshotExistsError,
    SnapshotIntegrityError,
    SnapshotValidationError,
    approved_product_map,
    create_catalog_snapshot,
    load_approval_manifest,
    load_catalog_snapshot,
    snapshot_file_path,
    validate_approval_manifest,
)


FULL_EXPORT_HEADERS = [
    "SKU",
    "OpenCart Product ID",
    "Product Status",
    "Active",
    "Product Name",
    "Product Description",
    "Meta Title",
    "Meta Description",
    "Meta Keywords",
    "SEO Keyword",
    "Canonical Product URL",
    "Manufacturer Part Number",
    "EAN Code",
    "GTIN",
    "UPC",
    "JAN",
    "ISBN",
    "Image Path",
    "Additional Image Paths",
    "Category Path",
    "Filter Values",
    "Manufacturer Name",
    "Related Models",
    "Product Price",
    "Stock Quantity",
    "Stock Status Name",
    "Date Added",
    "Last Modified Timestamp",
]


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _full_row(model: str, *, name: str) -> dict[str, str]:
    return {
        "SKU": model,
        "OpenCart Product ID": str(int(model) + 10),
        "Product Status": "1",
        "Active": "true",
        "Product Name": name,
        "Product Description": f"Description for {name}",
        "Meta Title": f"{name} | eTranoulis",
        "Meta Description": f"Meta for {name}",
        "Meta Keywords": "alpha, beta",
        "SEO Keyword": f"product-{model}",
        "Canonical Product URL": f"https://www.etranoulis.gr/product-{model}",
        "Manufacturer Part Number": f"MPN-{model}",
        "EAN Code": f"520{model}0000",
        "GTIN": f"0520{model}0000",
        "UPC": f"1{model}",
        "JAN": f"2{model}",
        "ISBN": f"3{model}",
        "Image Path": f"catalog/01_main/{model}/main.jpg",
        "Additional Image Paths": (
            f"catalog/01_main/{model}/second.jpg:::"
            f"catalog/01_main/{model}/third.jpg"
        ),
        "Category Path": "Climate///Air Conditioners",
        "Filter Values": "BTU=12000:::Wi-Fi=Yes",
        "Manufacturer Name": "Midea",
        "Related Models": "100001,100002",
        "Product Price": "799.00",
        "Stock Quantity": "4",
        "Stock Status Name": "In stock",
        "Date Added": "2025-01-02T03:04:05+00:00",
        "Last Modified Timestamp": "2026-07-12T09:10:11+03:00",
    }


def _approval() -> dict:
    return {
        "schema_version": "1.0",
        "snapshot_id": "snapshot-1",
        "migration_run_id": "migration-1",
        "approved_by": "operator@example.test",
        "approved_at": "2026-07-12T12:34:56+03:00",
        "products": [
            {
                "model": "123456",
                "approved_fields": ["meta_title", "meta_description"],
                "approved_slug_change": False,
                "approved_image_path_change": False,
                "notes": "Content-only canary.",
            }
        ],
    }


def test_snapshot_normalizes_aliases_sorts_rows_and_hashes_deterministically(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input" / "catalog.csv"
    _write_csv(
        source,
        FULL_EXPORT_HEADERS,
        [
            _full_row("123456", name="Second"),
            _full_row("000001", name="First"),
        ],
    )
    timestamp = "2026-07-12T09:00:00Z"
    first = create_catalog_snapshot(
        source,
        output_root=tmp_path / "one",
        source_environment="production",
        source_export_identity="opencart:seo-full:v1",
        target_identity="opencart-target:sha256:" + "a" * 64,
        snapshot_id="snapshot-1",
        timestamp=timestamp,
    )
    second = create_catalog_snapshot(
        source,
        output_root=tmp_path / "two",
        source_environment="production",
        source_export_identity="opencart:seo-full:v1",
        target_identity="opencart-target:sha256:" + "a" * 64,
        snapshot_id="snapshot-1",
        timestamp=timestamp,
    )

    assert first == second
    assert snapshot_file_path(tmp_path / "one", "snapshot-1").read_bytes() == (
        snapshot_file_path(tmp_path / "two", "snapshot-1").read_bytes()
    )
    assert [product["model"] for product in first["products"]] == [
        "000001",
        "123456",
    ]
    product = first["products"][1]
    assert set(product) == set(SNAPSHOT_PRODUCT_FIELDS)
    assert product["product_id"] == "123466"
    assert product["active"] == "true"
    assert product["description"] == "Description for Second"
    assert product["additional_images"] == [
        "catalog/01_main/123456/second.jpg",
        "catalog/01_main/123456/third.jpg",
    ]
    assert product["related_products"] == ["100001", "100002"]
    assert first["metadata"]["available_fields"] == list(SNAPSHOT_PRODUCT_FIELDS)
    assert first["metadata"]["unavailable_fields"] == []
    assert first["metadata"]["source_basename"] == "catalog.csv"
    assert first["metadata"]["target_identity"] == (
        "opencart-target:sha256:" + "a" * 64
    )
    assert first["metadata"]["source_hash"] == (
        f"sha256:{hashlib.sha256(source.read_bytes()).hexdigest()}"
    )
    assert str(tmp_path) not in json.dumps(first)


def test_snapshot_records_absent_fields_separately_from_exported_empty_lists(
    tmp_path: Path,
) -> None:
    source = tmp_path / "minimal.csv"
    _write_csv(
        source,
        ["model", "name", "additional_image", "related_product"],
        [
            {
                "model": "123456",
                "name": "Product",
                "additional_image": "",
                "related_product": "",
            }
        ],
    )

    snapshot = create_catalog_snapshot(
        source,
        output_root=tmp_path / "output",
        source_environment="fixture",
        source_export_identity="fixture:minimal",
        snapshot_id="minimal-1",
        timestamp="2026-07-12T09:00:00Z",
    )

    row = snapshot["products"][0]
    assert row["additional_images"] == []
    assert row["related_products"] == []
    assert row["active"] is None
    assert row["meta_title"] is None
    assert "additional_images" in snapshot["metadata"]["available_fields"]
    assert "active" in snapshot["metadata"]["unavailable_fields"]


def test_snapshot_collects_dynamic_filter_columns(tmp_path: Path) -> None:
    source = tmp_path / "filters.csv"
    _write_csv(
        source,
        ["model", "filter_group:BTU", "filter-group Wi-Fi"],
        [{"model": "123456", "filter_group:BTU": "12000", "filter-group Wi-Fi": "Yes"}],
    )

    snapshot = create_catalog_snapshot(
        source,
        output_root=tmp_path / "output",
        source_environment="fixture",
        source_export_identity="fixture:filters",
        snapshot_id="filters-1",
        timestamp="2026-07-12T09:00:00Z",
    )

    assert snapshot["products"][0]["filters"] == {
        "filter-group Wi-Fi": "Yes",
        "filter_group:BTU": "12000",
    }
    assert "filters" in snapshot["metadata"]["available_fields"]


@pytest.mark.parametrize(
    "rows,match",
    [
        ([{"model": "", "name": "Missing"}], "has no model"),
        (
            [
                {"model": "123456", "name": "One"},
                {"model": "123456", "name": "Two"},
            ],
            "duplicate model",
        ),
    ],
)
def test_snapshot_rejects_missing_and_duplicate_models(
    tmp_path: Path, rows: list[dict[str, str]], match: str
) -> None:
    source = tmp_path / "invalid.csv"
    _write_csv(source, ["model", "name"], rows)

    with pytest.raises(SnapshotValidationError, match=match):
        create_catalog_snapshot(
            source,
            output_root=tmp_path / "output",
            source_environment="fixture",
            source_export_identity="fixture:invalid",
            timestamp="2026-07-12T09:00:00Z",
        )


def test_snapshot_is_immutable_and_detects_internal_tampering(tmp_path: Path) -> None:
    source = tmp_path / "catalog.csv"
    _write_csv(source, ["model", "name"], [{"model": "123456", "name": "Before"}])
    kwargs = {
        "output_root": tmp_path / "output",
        "source_environment": "fixture",
        "source_export_identity": "fixture:catalog",
        "snapshot_id": "immutable-1",
        "timestamp": "2026-07-12T09:00:00Z",
    }
    create_catalog_snapshot(source, **kwargs)
    with pytest.raises(SnapshotExistsError, match="cannot be overwritten"):
        create_catalog_snapshot(source, **kwargs)

    path = snapshot_file_path(tmp_path / "output", "immutable-1")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["products"][0]["name"] = "Tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SnapshotIntegrityError, match="content hash"):
        load_catalog_snapshot(tmp_path / "output", "immutable-1")


def test_snapshot_can_verify_original_export_hash(tmp_path: Path) -> None:
    source = tmp_path / "catalog.csv"
    _write_csv(source, ["model", "name"], [{"model": "123456", "name": "Before"}])
    create_catalog_snapshot(
        source,
        output_root=tmp_path / "output",
        source_environment="fixture",
        source_export_identity="fixture:catalog",
        snapshot_id="source-hash-1",
        timestamp="2026-07-12T09:00:00Z",
    )
    _write_csv(source, ["model", "name"], [{"model": "123456", "name": "After"}])

    with pytest.raises(SnapshotIntegrityError, match="source hash"):
        load_catalog_snapshot(
            tmp_path / "output", "source-hash-1", source_export_path=source
        )


def test_snapshot_rejects_secret_bearing_identity(tmp_path: Path) -> None:
    source = tmp_path / "catalog.csv"
    _write_csv(source, ["model"], [{"model": "123456"}])

    with pytest.raises(SnapshotValidationError, match="appears to contain a secret"):
        create_catalog_snapshot(
            source,
            output_root=tmp_path / "output",
            source_environment="production",
            source_export_identity="password=hunter2",
            timestamp="2026-07-12T09:00:00Z",
        )


def test_valid_approval_manifest_and_model_index() -> None:
    manifest = _approval()

    validated = validate_approval_manifest(
        manifest,
        snapshot_id="snapshot-1",
        migration_run_id="migration-1",
        allowed_fields={"meta_title", "meta_description"},
    )

    assert validated == manifest
    assert validated is not manifest
    assert approved_product_map(validated)["123456"]["notes"] == "Content-only canary."


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda value: value.update({"unexpected": True}), "unknown"),
        (lambda value: value.update({"schema_version": "2.0"}), "schema_version"),
        (lambda value: value.update({"approved_by": "  "}), "approved_by"),
        (
            lambda value: value.update({"approved_at": "2026-07-12T12:34:56"}),
            "RFC3339",
        ),
        (
            lambda value: value["products"][0].update({"model": "12345"}),
            "six digits",
        ),
        (
            lambda value: value["products"][0].update(
                {"approved_fields": ["meta_title", "meta_title"]}
            ),
            "duplicates",
        ),
        (
            lambda value: value["products"][0].update(
                {"approved_slug_change": "false"}
            ),
            "must be boolean",
        ),
        (
            lambda value: value["products"][0].update({"extra": "no"}),
            "unknown",
        ),
    ],
)
def test_approval_rejects_invalid_shapes(mutation, match: str) -> None:
    manifest = deepcopy(_approval())
    mutation(manifest)

    with pytest.raises(ApprovalValidationError, match=match):
        validate_approval_manifest(
            manifest,
            snapshot_id="snapshot-1",
            migration_run_id="migration-1",
        )


def test_approval_rejects_identity_mismatch_duplicate_models_and_unknown_fields() -> None:
    with pytest.raises(ApprovalValidationError, match="snapshot_id does not match"):
        validate_approval_manifest(
            _approval(), snapshot_id="other", migration_run_id="migration-1"
        )

    duplicate = _approval()
    duplicate["products"].append(deepcopy(duplicate["products"][0]))
    with pytest.raises(ApprovalValidationError, match="duplicate model"):
        validate_approval_manifest(
            duplicate, snapshot_id="snapshot-1", migration_run_id="migration-1"
        )

    with pytest.raises(ApprovalValidationError, match="unsupported fields"):
        validate_approval_manifest(
            _approval(),
            snapshot_id="snapshot-1",
            migration_run_id="migration-1",
            allowed_fields={"meta_title"},
        )


def test_approval_loader_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "approval.json"
    path.write_text(
        """{
          "schema_version": "1.0",
          "snapshot_id": "snapshot-1",
          "snapshot_id": "snapshot-2",
          "migration_run_id": "migration-1",
          "approved_by": "operator",
          "approved_at": "2026-07-12T12:34:56Z",
          "products": []
        }""",
        encoding="utf-8",
    )

    with pytest.raises(ApprovalValidationError, match="duplicate key"):
        load_approval_manifest(
            path, snapshot_id="snapshot-1", migration_run_id="migration-1"
        )
