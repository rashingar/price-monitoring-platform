from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping


SNAPSHOT_SCHEMA_VERSION = "1.0"
SNAPSHOT_FILENAME = "snapshot.json"

SNAPSHOT_PRODUCT_FIELDS = (
    "model",
    "product_id",
    "status",
    "active",
    "name",
    "description",
    "meta_title",
    "meta_description",
    "meta_keywords",
    "seo_keyword",
    "canonical_url",
    "mpn",
    "ean",
    "gtin",
    "upc",
    "jan",
    "isbn",
    "main_image",
    "additional_images",
    "category",
    "filters",
    "manufacturer",
    "related_products",
    "price",
    "quantity",
    "stock_status",
    "date_added",
    "last_modified",
)

_LIST_FIELDS = {"additional_images", "related_products"}
_SNAPSHOT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_SECRET_METADATA_RE = re.compile(
    r"(?i)(?:password|passwd|secret|token|api[_ -]?key)\s*[:=]"
)
_URI_PASSWORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^/@\s:]+:[^/@\s]+@")

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "model": (
        "model",
        "internal_model",
        "internal_product_code",
        "product_code",
        "sku",
    ),
    "product_id": (
        "product_id",
        "opencart_product_id",
        "catalog_product_id",
        "id",
    ),
    "status": ("status", "product_status"),
    # Active is intentionally independent of status and is never inferred.
    "active": ("active", "is_active", "enabled"),
    "name": ("name", "product_name"),
    "description": ("description", "product_description"),
    "meta_title": ("meta_title", "meta_title_1", "metadata_title"),
    "meta_description": (
        "meta_description",
        "meta_description_1",
        "metadata_description",
    ),
    "meta_keywords": (
        "meta_keywords",
        "meta_keyword",
        "meta_keywords_1",
        "metadata_keywords",
    ),
    "seo_keyword": ("seo_keyword", "seo_url_keyword", "keyword", "slug"),
    "canonical_url": (
        "canonical_url",
        "canonical_product_url",
        "product_url",
        "store_product_url",
        "url",
    ),
    "mpn": ("mpn", "manufacturer_part_number"),
    "ean": ("ean", "ean_code", "ean13"),
    "gtin": (
        "gtin",
        "gtin_code",
        "gtin8",
        "gtin_8",
        "gtin12",
        "gtin_12",
        "gtin13",
        "gtin_13",
        "gtin14",
        "gtin_14",
    ),
    "upc": ("upc", "upc_code"),
    "jan": ("jan", "jan_code"),
    "isbn": ("isbn", "isbn_code"),
    "main_image": ("main_image", "image", "image_path", "main_image_path"),
    "additional_images": (
        "additional_images",
        "additional_image",
        "additional_image_paths",
        "gallery_images",
    ),
    "category": ("category", "categories", "category_path"),
    "filters": ("filters", "filter", "filter_values", "product_filters"),
    "manufacturer": ("manufacturer", "manufacturer_name", "brand"),
    "related_products": (
        "related_products",
        "related_product",
        "related_models",
    ),
    "price": ("price", "product_price"),
    "quantity": ("quantity", "product_quantity", "stock_quantity"),
    "stock_status": ("stock_status", "stock_status_name"),
    "date_added": ("date_added", "created_at", "product_created_at"),
    "last_modified": (
        "last_modified",
        "last_modified_timestamp",
        "date_modified",
        "modified_at",
        "updated_at",
    ),
}

_TOP_LEVEL_KEYS = {"schema_version", "snapshot_id", "metadata", "products"}
_METADATA_KEYS = {
    "timestamp",
    "source_environment",
    "source_export_identity",
    "target_identity",
    "source_basename",
    "row_count",
    "source_hash",
    "catalog_hash",
    "content_hash",
    "available_fields",
    "unavailable_fields",
}


class SnapshotError(RuntimeError):
    """Base error for immutable catalog snapshot operations."""


class SnapshotValidationError(SnapshotError):
    """Raised when an export or snapshot violates the snapshot contract."""


class SnapshotIntegrityError(SnapshotError):
    """Raised when persisted snapshot content no longer matches its hash."""


class SnapshotExistsError(SnapshotError):
    """Raised when a caller attempts to overwrite an existing snapshot."""


def create_catalog_snapshot(
    source_export_path: str | Path,
    *,
    output_root: str | Path,
    source_environment: str,
    source_export_identity: str,
    target_identity: str | None = None,
    snapshot_id: str | None = None,
    timestamp: str | datetime | None = None,
) -> dict[str, Any]:
    """Create one immutable, canonical snapshot from a UTF-8 CSV export.

    The source file is read once. Its exact bytes are hashed, while row values
    are normalized into the stable Phase 4 field contract.
    """

    source_path = Path(source_export_path)
    if not source_path.exists() or not source_path.is_file():
        raise SnapshotValidationError(f"source export does not exist: {source_path}")
    try:
        source_bytes = source_path.read_bytes()
    except OSError as exc:
        raise SnapshotValidationError(f"could not read source export: {source_path}") from exc
    if not source_bytes:
        raise SnapshotValidationError("source export is empty")

    normalized_timestamp = _normalize_timestamp(timestamp)
    environment = _safe_metadata_value(source_environment, field="source_environment")
    export_identity = _safe_metadata_value(
        source_export_identity, field="source_export_identity"
    )
    bound_target_identity = _safe_metadata_value(
        target_identity if target_identity is not None else "unbound",
        field="target_identity",
    )
    source_hash = _sha256(source_bytes)
    resolved_snapshot_id = snapshot_id or _default_snapshot_id(
        normalized_timestamp, source_hash
    )
    _validate_snapshot_id(resolved_snapshot_id)

    products, available_fields = _read_products(source_bytes)
    unavailable_fields = [
        field for field in SNAPSHOT_PRODUCT_FIELDS if field not in available_fields
    ]
    payload: dict[str, Any] = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": resolved_snapshot_id,
        "metadata": {
            "timestamp": normalized_timestamp,
            "source_environment": environment,
            "source_export_identity": export_identity,
            "target_identity": bound_target_identity,
            "source_basename": _safe_source_basename(source_path.name),
            "row_count": len(products),
            "source_hash": source_hash,
            "catalog_hash": _catalog_hash(products, available_fields),
            "content_hash": "",
            "available_fields": [
                field for field in SNAPSHOT_PRODUCT_FIELDS if field in available_fields
            ],
            "unavailable_fields": unavailable_fields,
        },
        "products": products,
    }
    payload["metadata"]["content_hash"] = compute_snapshot_content_hash(payload)
    verify_catalog_snapshot(payload, expected_snapshot_id=resolved_snapshot_id)

    target_dir = snapshot_directory(output_root, resolved_snapshot_id)
    snapshot_root = target_dir.parent
    snapshot_root.mkdir(parents=True, exist_ok=True)
    try:
        target_dir.mkdir()
    except FileExistsError as exc:
        raise SnapshotExistsError(
            f"snapshot already exists and cannot be overwritten: {resolved_snapshot_id}"
        ) from exc

    target_path = target_dir / SNAPSHOT_FILENAME
    try:
        _atomic_write_text(target_path, _pretty_json(payload))
    except Exception:
        # The directory was created by this call and contains at most our file.
        target_path.unlink(missing_ok=True)
        try:
            target_dir.rmdir()
        except OSError:
            pass
        raise
    return deepcopy(payload)


def load_catalog_snapshot(
    output_root: str | Path,
    snapshot_id: str,
    *,
    source_export_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load and integrity-check a persisted snapshot."""

    _validate_snapshot_id(snapshot_id)
    path = snapshot_file_path(output_root, snapshot_id)
    if not path.exists() or not path.is_file():
        raise SnapshotValidationError(f"snapshot does not exist: {snapshot_id}")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SnapshotValidationError(f"snapshot JSON is invalid: {snapshot_id}") from exc
    verify_catalog_snapshot(
        payload,
        expected_snapshot_id=snapshot_id,
        source_export_path=source_export_path,
    )
    return deepcopy(payload)


def verify_catalog_snapshot(
    payload: Mapping[str, Any],
    *,
    expected_snapshot_id: str | None = None,
    source_export_path: str | Path | None = None,
) -> None:
    """Validate schema invariants and detect snapshot/source tampering."""

    if not isinstance(payload, Mapping):
        raise SnapshotValidationError("snapshot must be a JSON object")
    _require_exact_keys(payload, _TOP_LEVEL_KEYS, context="snapshot")
    if payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise SnapshotValidationError("snapshot schema_version must be 1.0")

    snapshot_id = payload.get("snapshot_id")
    if not isinstance(snapshot_id, str):
        raise SnapshotValidationError("snapshot_id must be a string")
    _validate_snapshot_id(snapshot_id)
    if expected_snapshot_id is not None and snapshot_id != expected_snapshot_id:
        raise SnapshotValidationError("snapshot_id does not match the requested snapshot")

    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        raise SnapshotValidationError("snapshot metadata must be an object")
    _require_exact_keys(metadata, _METADATA_KEYS, context="snapshot metadata")
    _parse_rfc3339(str(metadata.get("timestamp") or ""), field="timestamp")
    stored_environment = metadata.get("source_environment")
    if _safe_metadata_value(stored_environment, field="source_environment") != stored_environment:
        raise SnapshotValidationError("source_environment is not normalized")
    stored_identity = metadata.get("source_export_identity")
    if _safe_metadata_value(
        stored_identity, field="source_export_identity"
    ) != stored_identity:
        raise SnapshotValidationError("source_export_identity is not normalized")
    stored_target_identity = metadata.get("target_identity")
    if _safe_metadata_value(
        stored_target_identity, field="target_identity"
    ) != stored_target_identity:
        raise SnapshotValidationError("target_identity is not normalized")
    source_basename = metadata.get("source_basename")
    if (
        not isinstance(source_basename, str)
        or not source_basename
        or Path(source_basename).name != source_basename
    ):
        raise SnapshotValidationError("source_basename must be a plain filename")
    _safe_source_basename(source_basename)

    products = payload.get("products")
    if not isinstance(products, list) or not products:
        raise SnapshotValidationError("snapshot products must be a non-empty array")
    row_count = metadata.get("row_count")
    if type(row_count) is not int or row_count != len(products):
        raise SnapshotValidationError("snapshot row_count does not match products")

    available = _validate_field_inventory(
        metadata.get("available_fields"), field="available_fields"
    )
    unavailable = _validate_field_inventory(
        metadata.get("unavailable_fields"), field="unavailable_fields"
    )
    if set(available) & set(unavailable):
        raise SnapshotValidationError("available_fields and unavailable_fields overlap")
    if set(available) | set(unavailable) != set(SNAPSHOT_PRODUCT_FIELDS):
        raise SnapshotValidationError(
            "available_fields and unavailable_fields must cover the canonical fields"
        )
    if "model" not in available:
        raise SnapshotValidationError("model must be available in the source export")

    models: list[str] = []
    for index, product in enumerate(products, start=1):
        if not isinstance(product, Mapping):
            raise SnapshotValidationError(f"snapshot product {index} must be an object")
        _require_exact_keys(
            product, set(SNAPSHOT_PRODUCT_FIELDS), context=f"snapshot product {index}"
        )
        model = product.get("model")
        if not isinstance(model, str) or not model.strip():
            raise SnapshotValidationError(f"snapshot product {index} has no model")
        if model != model.strip():
            raise SnapshotValidationError(f"snapshot product {index} model is not normalized")
        models.append(model)
        for field in SNAPSHOT_PRODUCT_FIELDS:
            value = product.get(field)
            if field == "filters" and field in available:
                if not isinstance(value, Mapping) or not all(
                    isinstance(key, str) and isinstance(item, str)
                    for key, item in value.items()
                ):
                    raise SnapshotValidationError(
                        "filters must be an object of exported column names and values"
                    )
            elif field == "filters" and value is not None:
                raise SnapshotValidationError(
                    "filters must be null when absent from the export"
                )
            elif field in _LIST_FIELDS and field in available:
                if not isinstance(value, list) or not all(
                    isinstance(item, str) for item in value
                ):
                    raise SnapshotValidationError(
                        f"{field} must be an array of strings when exported"
                    )
            elif field in _LIST_FIELDS and value is not None:
                raise SnapshotValidationError(
                    f"{field} must be null when absent from the export"
                )
            elif field in available and not isinstance(value, str):
                raise SnapshotValidationError(
                    f"{field} must be a string when exported"
                )
            elif field not in available and value is not None:
                raise SnapshotValidationError(
                    f"{field} must be null when absent from the export"
                )
    if len(models) != len(set(models)):
        raise SnapshotValidationError("snapshot contains duplicate models")
    if models != sorted(models):
        raise SnapshotValidationError("snapshot products are not sorted by model")

    source_hash = metadata.get("source_hash")
    catalog_hash = metadata.get("catalog_hash")
    content_hash = metadata.get("content_hash")
    _validate_sha256(source_hash, field="source_hash")
    _validate_sha256(catalog_hash, field="catalog_hash")
    _validate_sha256(content_hash, field="content_hash")
    calculated = compute_snapshot_content_hash(payload)
    if not hmac.compare_digest(str(content_hash), calculated):
        raise SnapshotIntegrityError("snapshot content hash does not match its content")
    calculated_catalog_hash = _catalog_hash(products, set(available))
    if not hmac.compare_digest(str(catalog_hash), calculated_catalog_hash):
        raise SnapshotIntegrityError("snapshot catalog hash does not match its products")

    if source_export_path is not None:
        source_path = Path(source_export_path)
        try:
            current_source_hash = _sha256(source_path.read_bytes())
        except OSError as exc:
            raise SnapshotIntegrityError(
                f"could not verify snapshot source export: {source_path}"
            ) from exc
        if not hmac.compare_digest(str(source_hash), current_source_hash):
            raise SnapshotIntegrityError(
                "snapshot source hash no longer matches the source export"
            )


def compute_snapshot_content_hash(payload: Mapping[str, Any]) -> str:
    """Return the self-hash, excluding only the content_hash field itself."""

    material = deepcopy(dict(payload))
    metadata = material.get("metadata")
    if isinstance(metadata, dict):
        metadata.pop("content_hash", None)
    return _sha256(_canonical_json_bytes(material))


def compute_catalog_export_hash(source_export_path: str | Path) -> str:
    """Hash canonical catalog rows from a fresh export for stale-state checks."""

    source_path = Path(source_export_path)
    try:
        source_bytes = source_path.read_bytes()
    except OSError as exc:
        raise SnapshotValidationError(
            f"could not read catalog export for freshness verification: {source_path}"
        ) from exc
    products, available_fields = _read_products(source_bytes)
    return _catalog_hash(products, available_fields)


def normalize_catalog_export(source_export_path: str | Path) -> dict[str, Any]:
    """Read a full export without persisting it, for apply/rollback verification."""

    source_path = Path(source_export_path)
    try:
        source_bytes = source_path.read_bytes()
    except OSError as exc:
        raise SnapshotValidationError(f"could not read catalog export: {source_path}") from exc
    products, available_fields = _read_products(source_bytes)
    return {
        "source_hash": _sha256(source_bytes),
        "catalog_hash": _catalog_hash(products, available_fields),
        "available_fields": [
            field for field in SNAPSHOT_PRODUCT_FIELDS if field in available_fields
        ],
        "unavailable_fields": [
            field for field in SNAPSHOT_PRODUCT_FIELDS if field not in available_fields
        ],
        "row_count": len(products),
        "products": products,
    }


def _catalog_hash(products: list[Mapping[str, Any]], available_fields: set[str]) -> str:
    return _sha256(
        _canonical_json_bytes(
            {
                "available_fields": [
                    field for field in SNAPSHOT_PRODUCT_FIELDS if field in available_fields
                ],
                "products": products,
            }
        )
    )


def snapshot_directory(output_root: str | Path, snapshot_id: str) -> Path:
    _validate_snapshot_id(snapshot_id)
    return Path(output_root) / "snapshots" / snapshot_id


def snapshot_file_path(output_root: str | Path, snapshot_id: str) -> Path:
    return snapshot_directory(output_root, snapshot_id) / SNAPSHOT_FILENAME


def _read_products(source_bytes: bytes) -> tuple[list[dict[str, Any]], set[str]]:
    try:
        source_text = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SnapshotValidationError("source export must be UTF-8 CSV") from exc

    try:
        reader = csv.DictReader(io.StringIO(source_text, newline=""))
        headers = reader.fieldnames or []
        if not headers:
            raise SnapshotValidationError("source export has no header row")
        normalized_headers: dict[str, str] = {}
        for header in headers:
            normalized = _normalize_header(header)
            if not normalized:
                raise SnapshotValidationError("source export contains a blank header")
            if normalized in normalized_headers:
                raise SnapshotValidationError(
                    f"source export contains duplicate header: {header}"
                )
            normalized_headers[normalized] = header

        columns_by_field: dict[str, list[str]] = {}
        available_fields: set[str] = set()
        for field in SNAPSHOT_PRODUCT_FIELDS:
            columns = [
                normalized_headers[alias]
                for alias in _FIELD_ALIASES[field]
                if alias in normalized_headers
            ]
            columns_by_field[field] = columns
            if columns:
                available_fields.add(field)

        dynamic_filter_columns = sorted(
            (
                actual
                for normalized, actual in normalized_headers.items()
                if normalized.startswith("filter_group_")
            ),
            key=_normalize_header,
        )
        if dynamic_filter_columns:
            available_fields.add("filters")
        if "model" not in available_fields:
            raise SnapshotValidationError("source export is missing a model column")

        products: list[dict[str, Any]] = []
        seen_models: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            if None in row and any(_normalize_scalar(value) for value in row[None] or []):
                raise SnapshotValidationError(
                    f"source export row {row_number} contains values without headers"
                )
            product: dict[str, Any] = {}
            model = _resolve_scalar(
                row,
                columns_by_field["model"],
                field="model",
                row_number=row_number,
            )
            if not model:
                raise SnapshotValidationError(
                    f"source export row {row_number} has no model"
                )
            if model in seen_models:
                raise SnapshotValidationError(
                    f"source export contains duplicate model: {model}"
                )
            seen_models.add(model)

            for field in SNAPSHOT_PRODUCT_FIELDS:
                if field not in available_fields:
                    product[field] = None
                    continue
                if field == "filters":
                    product[field] = _resolve_filters(
                        row,
                        columns_by_field[field],
                        dynamic_filter_columns,
                        row_number=row_number,
                    )
                    continue
                raw_value = _resolve_scalar(
                    row,
                    columns_by_field[field],
                    field=field,
                    row_number=row_number,
                )
                product[field] = (
                    _split_list(raw_value, field=field)
                    if field in _LIST_FIELDS
                    else raw_value
                )
            product["model"] = model
            products.append(product)
    except csv.Error as exc:
        raise SnapshotValidationError(f"source export CSV is invalid: {exc}") from exc

    if not products:
        raise SnapshotValidationError("source export has no product rows")
    products.sort(key=lambda product: str(product["model"]))
    return products, available_fields


def _resolve_scalar(
    row: Mapping[str, Any],
    columns: list[str],
    *,
    field: str,
    row_number: int,
) -> str:
    normalized_values = [_normalize_scalar(row.get(column)) for column in columns]
    nonempty = list(dict.fromkeys(value for value in normalized_values if value))
    if len(nonempty) > 1:
        raise SnapshotValidationError(
            f"source export row {row_number} has conflicting aliases for {field}"
        )
    return nonempty[0] if nonempty else ""


def _resolve_filters(
    row: Mapping[str, Any],
    columns: list[str],
    dynamic_columns: list[str],
    *,
    row_number: int,
) -> dict[str, str]:
    serialized = _resolve_scalar(
        row, columns, field="filters", row_number=row_number
    )
    if not dynamic_columns:
        return {"serialized": serialized} if serialized else {}
    values: dict[str, str] = {}
    if serialized:
        values["serialized"] = serialized
    for column in dynamic_columns:
        values[str(column).strip()] = _normalize_scalar(row.get(column))
    return dict(sorted(values.items()))


def _split_list(value: str, *, field: str) -> list[str]:
    if not value:
        return []
    if value.startswith("["):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
            return [_normalize_scalar(item) for item in parsed if _normalize_scalar(item)]
    delimiter = ":::" if ":::" in value else "," if field == "related_products" else None
    if delimiter is None:
        return [value]
    return [
        normalized
        for item in value.split(delimiter)
        if (normalized := _normalize_scalar(item))
    ]


def _normalize_header(value: Any) -> str:
    text = str(value or "").lstrip("\ufeff").strip().casefold()
    return re.sub(r"[^\w]+", "_", text, flags=re.UNICODE).strip("_")


def _normalize_scalar(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def _validate_field_inventory(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SnapshotValidationError(f"{field} must be an array of strings")
    if len(value) != len(set(value)):
        raise SnapshotValidationError(f"{field} contains duplicates")
    unknown = [item for item in value if item not in SNAPSHOT_PRODUCT_FIELDS]
    if unknown:
        raise SnapshotValidationError(f"{field} contains unknown fields: {unknown}")
    expected_order = [item for item in SNAPSHOT_PRODUCT_FIELDS if item in value]
    if value != expected_order:
        raise SnapshotValidationError(f"{field} is not in canonical order")
    return list(value)


def _require_exact_keys(
    payload: Mapping[str, Any], expected: set[str], *, context: str
) -> None:
    actual = set(payload)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        raise SnapshotValidationError(
            f"{context} keys are invalid; missing={missing}, unknown={unknown}"
        )


def _validate_snapshot_id(snapshot_id: str) -> None:
    if not isinstance(snapshot_id, str) or not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise SnapshotValidationError("snapshot_id is not a safe identifier")


def _safe_metadata_value(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise SnapshotValidationError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > 512:
        raise SnapshotValidationError(f"{field} must be a non-empty safe value")
    if _SECRET_METADATA_RE.search(normalized) or _URI_PASSWORD_RE.search(normalized):
        raise SnapshotValidationError(f"{field} appears to contain a secret")
    if any(ord(character) < 32 for character in normalized):
        raise SnapshotValidationError(f"{field} contains control characters")
    return normalized


def _safe_source_basename(value: Any) -> str:
    basename = _safe_metadata_value(value, field="source_basename")
    if Path(basename).name != basename:
        raise SnapshotValidationError("source_basename must be a plain filename")
    return basename


def _normalize_timestamp(value: str | datetime | None) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        parsed = value
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise SnapshotValidationError("timestamp must include a timezone")
    elif isinstance(value, str):
        parsed = _parse_rfc3339(value, field="timestamp")
    else:
        raise SnapshotValidationError("timestamp must be RFC3339 text or datetime")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_rfc3339(value: str, *, field: str) -> datetime:
    if not _RFC3339_RE.fullmatch(value):
        raise SnapshotValidationError(f"{field} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotValidationError(f"{field} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SnapshotValidationError(f"{field} must include a timezone")
    return parsed


def _default_snapshot_id(timestamp: str, source_hash: str) -> str:
    compact = timestamp.replace("-", "").replace(":", "")
    return f"{compact}-{source_hash.removeprefix('sha256:')[:12]}"


def _validate_sha256(value: Any, *, field: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise SnapshotValidationError(f"{field} must be a lowercase SHA-256 value")


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pretty_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _atomic_write_text(path: Path, payload: str) -> None:
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise SnapshotValidationError(f"snapshot JSON contains duplicate key: {key}")
        payload[key] = value
    return payload
