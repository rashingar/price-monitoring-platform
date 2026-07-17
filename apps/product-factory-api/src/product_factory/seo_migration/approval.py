from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


APPROVAL_SCHEMA_VERSION = "1.0"

_TOP_LEVEL_KEYS = {
    "schema_version",
    "snapshot_id",
    "migration_run_id",
    "approved_by",
    "approved_at",
    "products",
}
_PRODUCT_KEYS = {
    "model",
    "approved_fields",
    "approved_slug_change",
    "approved_image_path_change",
    "notes",
}
_MODEL_RE = re.compile(r"^\d{6}$")
_RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


class ApprovalValidationError(ValueError):
    """Raised when a machine-readable migration approval is invalid."""


def load_approval_manifest(
    path: str | Path,
    *,
    snapshot_id: str,
    migration_run_id: str,
    allowed_fields: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Load JSON without accepting duplicate keys, then validate it strictly."""

    approval_path = Path(path)
    if not approval_path.exists() or not approval_path.is_file():
        raise ApprovalValidationError(f"approval file does not exist: {approval_path}")
    try:
        payload = json.loads(
            approval_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ApprovalValidationError("approval file is not valid UTF-8 JSON") from exc
    return validate_approval_manifest(
        payload,
        snapshot_id=snapshot_id,
        migration_run_id=migration_run_id,
        allowed_fields=allowed_fields,
    )


def validate_approval_manifest(
    payload: Mapping[str, Any],
    *,
    snapshot_id: str,
    migration_run_id: str,
    allowed_fields: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Validate the exact Phase 4 approval schema and expected run identity."""

    if not isinstance(payload, Mapping):
        raise ApprovalValidationError("approval manifest must be a JSON object")
    _require_exact_keys(payload, _TOP_LEVEL_KEYS, context="approval manifest")
    if payload.get("schema_version") != APPROVAL_SCHEMA_VERSION:
        raise ApprovalValidationError("approval schema_version must be 1.0")

    actual_snapshot_id = _nonempty_text(payload.get("snapshot_id"), "snapshot_id")
    actual_run_id = _nonempty_text(
        payload.get("migration_run_id"), "migration_run_id"
    )
    expected_snapshot_id = _nonempty_text(snapshot_id, "expected snapshot_id")
    expected_run_id = _nonempty_text(
        migration_run_id, "expected migration_run_id"
    )
    if actual_snapshot_id != expected_snapshot_id:
        raise ApprovalValidationError(
            "approval snapshot_id does not match the selected snapshot"
        )
    if actual_run_id != expected_run_id:
        raise ApprovalValidationError(
            "approval migration_run_id does not match the selected migration run"
        )

    _nonempty_text(payload.get("approved_by"), "approved_by")
    _parse_rfc3339(payload.get("approved_at"))
    products = payload.get("products")
    if not isinstance(products, list):
        raise ApprovalValidationError("approval products must be an array")

    normalized_allowed: set[str] | None = None
    if allowed_fields is not None:
        normalized_allowed = set()
        for field in allowed_fields:
            normalized_allowed.add(_canonical_field_name(field, "allowed field"))

    seen_models: set[str] = set()
    for index, product in enumerate(products, start=1):
        if not isinstance(product, Mapping):
            raise ApprovalValidationError(
                f"approval product {index} must be a JSON object"
            )
        _require_exact_keys(
            product, _PRODUCT_KEYS, context=f"approval product {index}"
        )
        model = product.get("model")
        if not isinstance(model, str) or not _MODEL_RE.fullmatch(model):
            raise ApprovalValidationError(
                f"approval product {index} model must be exactly six digits"
            )
        if model in seen_models:
            raise ApprovalValidationError(f"approval contains duplicate model: {model}")
        seen_models.add(model)

        approved_fields = product.get("approved_fields")
        if not isinstance(approved_fields, list):
            raise ApprovalValidationError(
                f"approved_fields for {model} must be an array"
            )
        normalized_fields = [
            _canonical_field_name(field, f"approved field for {model}")
            for field in approved_fields
        ]
        if len(normalized_fields) != len(set(normalized_fields)):
            raise ApprovalValidationError(
                f"approved_fields for {model} contains duplicates"
            )
        if normalized_allowed is not None:
            unknown = sorted(set(normalized_fields) - normalized_allowed)
            if unknown:
                raise ApprovalValidationError(
                    f"approved_fields for {model} contains unsupported fields: {unknown}"
                )

        for flag in ("approved_slug_change", "approved_image_path_change"):
            if type(product.get(flag)) is not bool:
                raise ApprovalValidationError(f"{flag} for {model} must be boolean")
        if not isinstance(product.get("notes"), str):
            raise ApprovalValidationError(f"notes for {model} must be a string")

    return deepcopy(dict(payload))


def approved_product_map(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Index a previously validated approval without changing its semantics."""

    products = payload.get("products")
    if not isinstance(products, list):
        raise ApprovalValidationError("approval products must be an array")
    indexed: dict[str, dict[str, Any]] = {}
    for product in products:
        if not isinstance(product, Mapping):
            raise ApprovalValidationError("approval product must be a JSON object")
        model = product.get("model")
        if not isinstance(model, str) or not _MODEL_RE.fullmatch(model):
            raise ApprovalValidationError("approval product model must be six digits")
        if model in indexed:
            raise ApprovalValidationError(f"approval contains duplicate model: {model}")
        indexed[model] = deepcopy(dict(product))
    return indexed


def _require_exact_keys(
    payload: Mapping[str, Any], expected: set[str], *, context: str
) -> None:
    actual = set(payload)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        raise ApprovalValidationError(
            f"{context} keys are invalid; missing={missing}, unknown={unknown}"
        )


def _nonempty_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApprovalValidationError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise ApprovalValidationError(f"{field} must not have surrounding whitespace")
    return value


def _canonical_field_name(value: Any, context: str) -> str:
    field = _nonempty_text(value, context)
    if not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*", field):
        raise ApprovalValidationError(
            f"{context} must be a canonical lowercase field name"
        )
    return field


def _parse_rfc3339(value: Any) -> datetime:
    if not isinstance(value, str) or not _RFC3339_RE.fullmatch(value):
        raise ApprovalValidationError("approved_at must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApprovalValidationError(
            "approved_at must be an RFC3339 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ApprovalValidationError("approved_at must include a timezone")
    return parsed


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ApprovalValidationError(
                f"approval JSON contains duplicate key: {key}"
            )
        payload[key] = value
    return payload
