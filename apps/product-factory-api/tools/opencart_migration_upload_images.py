#!/usr/bin/env python3
from __future__ import annotations

"""Upload only explicitly approved migration image copies.

This adapter is intentionally separate from normal Product Factory gallery
publishing.  It accepts a run-scoped, hash-pinned manifest, uploads no besco
assets, deletes nothing, and confirms the public bytes after upload.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

try:
    import requests
except ImportError:  # pragma: no cover - runtime dependency guard
    requests = None

from tools.opencart_config import (
    compute_opencart_target_identity,
    resolve_opencart_config,
)
from tools.opencart_upload_images import (
    UploadError,
    build_admin_index,
    ensure_remote_nested_dir,
    login,
    permission_probe,
    upload_files,
)


MODEL_RE = re.compile(r"^[0-9]{6}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
MIGRATION_AUTHORIZATION_TTL_SECONDS = 30 * 60


def _canonical_content_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _parse_rfc3339(value: str, *, label: str) -> datetime:
    if not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})",
        value,
    ):
        raise UploadError(f"Migration image {label} must be RFC3339.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UploadError(f"Migration image {label} must be RFC3339.") from exc
    if parsed.tzinfo is None:
        raise UploadError(f"Migration image {label} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def _validate_authorization_window(
    issued_value: Any, expires_value: Any
) -> tuple[datetime, datetime]:
    issued = _parse_rfc3339(str(issued_value or ""), label="authorization issued_at")
    expires = _parse_rfc3339(
        str(expires_value or ""), label="authorization expires_at"
    )
    now = datetime.now(timezone.utc)
    lifetime = (expires - issued).total_seconds()
    if (
        issued > now
        or expires <= now
        or lifetime <= 0
        or lifetime > MIGRATION_AUTHORIZATION_TTL_SECONDS
    ):
        raise UploadError(
            "Migration image authorization is expired, future-dated, or exceeds its maximum lifetime."
        )
    return issued, expires


def consume_image_authorization(
    manifest_path: Path, authorization: Mapping[str, Any]
) -> dict[str, Any]:
    _validate_authorization_window(
        authorization.get("issued_at"), authorization.get("expires_at")
    )
    resolved_manifest = manifest_path.expanduser().resolve()
    run_id = str(authorization.get("migration_run_id") or "")
    run_roots = [parent for parent in resolved_manifest.parents if parent.name == run_id]
    if not run_roots:
        raise UploadError("Migration image manifest is outside its declared run.")
    marker = (
        run_roots[0]
        / "consumption"
        / (
            f"image_upload.{authorization.get('model')}."
            f"{authorization.get('claim_hash')}.json"
        )
    )
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "adapter": "image_upload",
        "operation": authorization.get("operation"),
        "migration_run_id": run_id,
        "snapshot_id": authorization.get("snapshot_id"),
        "model": authorization.get("model"),
        "claim_hash": authorization.get("claim_hash"),
        "image_operations_hash": authorization.get("image_operations_hash"),
        "consumed_at": datetime.now().astimezone().isoformat(),
    }
    try:
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise UploadError(
            "Migration image authorization was already consumed; replay is forbidden."
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception as exc:
        raise UploadError(
            "Could not durably consume migration image authorization."
        ) from exc
    return {**payload, "marker": str(marker)}


def _safe_error_message(
    exc: BaseException, *, admin_path: str = ""
) -> str:
    message = str(exc) or exc.__class__.__name__
    redacted = re.sub(
        r"([?&](?:user_token|token|password)=)[^&\s'\"]+",
        r"\1<redacted>",
        message,
        flags=re.IGNORECASE,
    )
    for variant in {
        str(admin_path or "").strip(),
        str(admin_path or "").strip().replace("\\", "/"),
        str(admin_path or "").strip("/\\"),
    }:
        if variant:
            redacted = redacted.replace(variant, "<redacted-admin-path>")
    return redacted


def write_atomic_report(report_path: Path, payload: Mapping[str, Any]) -> None:
    """Durably replace the report without exposing a partial JSON document."""

    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=report_path.parent,
            prefix=f".{report_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, report_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_manifest(
    path: Path, model: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise UploadError(f"Migration image manifest is invalid: {path}") from exc
    if not isinstance(payload, Mapping) or payload.get("schema_version") != "1.0":
        raise UploadError("Migration image manifest schema_version must be 1.0.")
    if payload.get("model") != model:
        raise UploadError("Migration image manifest model does not match.")
    operations = payload.get("operations")
    authorization = _validate_run_authorization(
        payload.get("authorization"),
        manifest_path=path,
        manifest_model=model,
        manifest_operations=operations,
    )
    if not isinstance(operations, list) or not operations:
        raise UploadError("Migration image manifest contains no operations.")
    result: list[dict[str, Any]] = []
    seen_targets: set[str] = set()
    for raw in operations:
        if not isinstance(raw, Mapping):
            raise UploadError("Migration image operation must be an object.")
        if raw.get("model") != model:
            raise UploadError("Migration image operation model does not match.")
        old_path = str(raw.get("old_path") or "")
        new_path = str(raw.get("new_path") or "")
        expected_prefix = f"catalog/01_main/{model}/"
        if not new_path.startswith(expected_prefix) or Path(new_path).suffix.lower() != ".jpg":
            raise UploadError(f"Unsafe migration image target: {new_path}")
        if "01_bescos" in old_path.casefold() or "01_bescos" in new_path.casefold():
            raise UploadError("Migration image manifest may not contain besco assets.")
        target_file = Path(str(raw.get("target_file") or "")).expanduser().resolve()
        if not target_file.exists() or not target_file.is_file():
            raise UploadError(f"Migration image target file does not exist: {target_file}")
        if target_file.name != Path(new_path).name:
            raise UploadError("Migration image filename does not match its public path.")
        target_hash = str(raw.get("target_hash") or "")
        if not HASH_RE.fullmatch(target_hash):
            raise UploadError("Migration image target hash is invalid.")
        actual_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()
        if actual_hash != target_hash:
            raise UploadError(f"Migration image target hash changed: {target_file}")
        source_file = Path(str(raw.get("source_file") or "")).expanduser().resolve()
        source_hash = str(raw.get("source_hash") or "")
        if (
            not raw.get("original_retained")
            or not source_file.is_file()
            or not HASH_RE.fullmatch(source_hash)
        ):
            raise UploadError("Migration image original-retention check failed.")
        if hashlib.sha256(source_file.read_bytes()).hexdigest() != source_hash:
            raise UploadError(
                f"Migration image source hash changed after authorization: {source_file}"
            )
        if new_path in seen_targets:
            raise UploadError(f"Duplicate migration image target: {new_path}")
        seen_targets.add(new_path)
        result.append(
            {
                **dict(raw),
                "source_file": str(source_file),
                "target_file": str(target_file),
            }
        )
    return (
        sorted(result, key=lambda item: int(item.get("position") or 0)),
        authorization,
    )


def _validate_run_authorization(
    raw: Any,
    *,
    manifest_path: Path,
    manifest_model: str,
    manifest_operations: Any,
) -> dict[str, Any]:
    required = {
        "schema_version",
        "operation",
        "migration_run_id",
        "snapshot_id",
        "approval_hash",
        "plan_hash",
        "target_identity",
        "model",
        "csv_sha256",
        "headers",
        "image_operations_hash",
        "claim_path",
        "claim_hash",
        "issued_at",
        "expires_at",
    }
    if not isinstance(raw, Mapping) or set(raw) != required:
        raise UploadError("Migration image authorization has an invalid exact shape.")
    authorization = dict(raw)
    if authorization.get("schema_version") != "1.0":
        raise UploadError("Migration image authorization schema_version must be 1.0.")
    if authorization.get("operation") not in {"apply", "rollback"}:
        raise UploadError("Migration image authorization operation is invalid.")
    if authorization.get("model") != manifest_model:
        raise UploadError("Migration image authorization model does not match.")
    if not all(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", str(authorization[key]))
        for key in ("migration_run_id", "snapshot_id")
    ):
        raise UploadError("Migration image authorization IDs are invalid.")
    if not all(
        HASH_RE.fullmatch(str(authorization[key]) or "")
        for key in (
            "approval_hash",
            "plan_hash",
            "csv_sha256",
            "image_operations_hash",
            "claim_hash",
        )
    ):
        raise UploadError("Migration image authorization hash is invalid.")
    issued_at, _expires_at = _validate_authorization_window(
        authorization.get("issued_at"), authorization.get("expires_at")
    )
    headers = authorization.get("headers")
    if (
        not isinstance(headers, list)
        or not headers
        or not all(isinstance(header, str) and header.strip() for header in headers)
        or len(headers) != len(set(headers))
    ):
        raise UploadError("Migration image authorization headers are invalid.")
    if not isinstance(manifest_operations, list) or not manifest_operations:
        raise UploadError("Migration image manifest contains no operations.")
    if _canonical_content_hash(manifest_operations) != authorization[
        "image_operations_hash"
    ]:
        raise UploadError("Migration image operations no longer match authorization.")

    resolved_manifest = manifest_path.expanduser().resolve()
    if len(resolved_manifest.parents) < 3:
        raise UploadError("Migration image manifest is outside a migration run.")
    run_root = resolved_manifest.parents[2]
    if run_root.name != authorization["migration_run_id"]:
        raise UploadError("Migration image manifest run does not match authorization.")
    claim_path = Path(str(authorization["claim_path"])).expanduser().resolve()
    try:
        claim_path.relative_to(run_root)
    except ValueError as exc:
        raise UploadError("Migration image claim is outside its run.") from exc
    if not claim_path.is_file():
        raise UploadError("Migration image claim is missing.")
    if hashlib.sha256(claim_path.read_bytes()).hexdigest() != authorization[
        "claim_hash"
    ]:
        raise UploadError("Migration image claim hash no longer matches.")
    try:
        claim = json.loads(claim_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise UploadError("Migration image apply claim is invalid.") from exc
    claim_keys = {
        "schema_version",
        "operation",
        "migration_run_id",
        "snapshot_id",
        "approval_hash",
        "plan_hash",
        "target_identity",
        "claimed_at",
        "one_shot",
        "scopes",
    }
    if not isinstance(claim, Mapping) or set(claim) != claim_keys:
        raise UploadError("Migration image claim has an invalid exact shape.")
    for key in (
        "migration_run_id",
        "snapshot_id",
        "approval_hash",
        "plan_hash",
        "target_identity",
    ):
        if claim.get(key) != authorization.get(key):
            raise UploadError(f"Migration image claim mismatches {key}.")
    if (
        claim.get("schema_version") != "1.0"
        or claim.get("operation") != authorization["operation"]
        or claim.get("one_shot") is not True
    ):
        raise UploadError("Migration image claim is not an active run claim.")
    claimed_at = _parse_rfc3339(
        str(claim.get("claimed_at") or ""), label="claim claimed_at"
    )
    if issued_at < claimed_at:
        raise UploadError("Migration image authorization predates its run claim.")

    scopes = claim.get("scopes")
    scope_keys = {
        "model",
        "csv_sha256",
        "headers",
        "image_operations_hash",
    }
    if not isinstance(scopes, list) or not scopes:
        raise UploadError("Migration image claim scopes are invalid.")
    normalized_scopes: list[dict[str, Any]] = []
    seen_models: set[str] = set()
    for raw_scope in scopes:
        if not isinstance(raw_scope, Mapping) or set(raw_scope) != scope_keys:
            raise UploadError("Migration image claim scope has an invalid exact shape.")
        scope = dict(raw_scope)
        scope_model = scope.get("model")
        scope_headers = scope.get("headers")
        if (
            not isinstance(scope_model, str)
            or not MODEL_RE.fullmatch(scope_model)
            or scope_model in seen_models
            or not HASH_RE.fullmatch(str(scope.get("csv_sha256") or ""))
            or not HASH_RE.fullmatch(
                str(scope.get("image_operations_hash") or "")
            )
            or not isinstance(scope_headers, list)
            or not scope_headers
            or not all(
                isinstance(header, str) and header.strip()
                for header in scope_headers
            )
            or len(scope_headers) != len(set(scope_headers))
        ):
            raise UploadError("Migration image claim scope is invalid.")
        seen_models.add(scope_model)
        normalized_scopes.append(scope)

    authorized_scope = {
        "model": authorization["model"],
        "csv_sha256": authorization["csv_sha256"],
        "headers": authorization["headers"],
        "image_operations_hash": authorization["image_operations_hash"],
    }
    if normalized_scopes.count(authorized_scope) != 1:
        raise UploadError("Migration image authorization has no exact claim scope.")
    return authorization


def _public_image_url(store_base: str, operation: Mapping[str, Any]) -> str:
    return (
        f"{store_base.rstrip('/')}/image/"
        f"{str(operation['new_path']).lstrip('/')}"
    )


def _get_public_image(public_url: str):
    if requests is None:
        raise UploadError("Missing dependency: requests")
    try:
        return requests.get(
            public_url,
            timeout=60,
            allow_redirects=False,
            headers={"User-Agent": "ProductFactory-SEO-Migration/1.0"},
        )
    except requests.RequestException as exc:
        raise UploadError(
            f"Public migration image request was ambiguous: {public_url}: "
            f"{_safe_error_message(exc)}"
        ) from exc


def _same_public_image_url(requested: str, final: str) -> bool:
    left = urlsplit(str(requested or ""))
    right = urlsplit(str(final or ""))
    return (
        left.scheme.casefold(),
        (left.hostname or "").casefold(),
        left.port,
        left.path,
        left.query,
        left.fragment,
    ) == (
        right.scheme.casefold(),
        (right.hostname or "").casefold(),
        right.port,
        right.path,
        right.query,
        right.fragment,
    )


def preflight_public_images(
    *,
    store_base: str,
    operations: list[Mapping[str, Any]],
    results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Classify every public target before any OpenCart write is attempted."""

    checked = results if results is not None else []
    for operation in operations:
        public_url = _public_image_url(store_base, operation)
        expected_hash = str(operation.get("target_hash") or "")
        try:
            response = _get_public_image(public_url)
        except UploadError as exc:
            checked.append(
                {
                    "new_path": operation.get("new_path"),
                    "public_url": public_url,
                    "state": "ambiguous_error",
                    "verified": False,
                    "upload_required": False,
                    "expected_hash": expected_hash,
                    "error": _safe_error_message(exc),
                }
            )
            raise

        base_result: dict[str, Any] = {
            "new_path": operation.get("new_path"),
            "public_url": public_url,
            "http_status": response.status_code,
            "final_url": str(response.url),
            "expected_hash": expected_hash,
        }
        if not _same_public_image_url(public_url, str(response.url)):
            checked.append(
                {
                    **base_result,
                    "observed_hash": None,
                    "state": "redirect_rejected",
                    "verified": False,
                    "upload_required": False,
                }
            )
            raise UploadError(
                f"Public migration image target redirected away from its exact path: {public_url}"
            )
        if 200 <= response.status_code < 300:
            observed_hash = hashlib.sha256(response.content).hexdigest()
            if observed_hash == expected_hash:
                checked.append(
                    {
                        **base_result,
                        "observed_hash": observed_hash,
                        "state": "verified_existing",
                        "verified": True,
                        "upload_required": False,
                    }
                )
                continue
            checked.append(
                {
                    **base_result,
                    "observed_hash": observed_hash,
                    "state": "conflict",
                    "verified": False,
                    "upload_required": False,
                }
            )
            raise UploadError(
                f"Public migration image target already exists with different bytes: {public_url}"
            )

        if response.status_code in {404, 410}:
            checked.append(
                {
                    **base_result,
                    "observed_hash": None,
                    "state": "upload_required",
                    "verified": False,
                    "upload_required": True,
                }
            )
            continue

        checked.append(
            {
                **base_result,
                "observed_hash": None,
                "state": "ambiguous_error",
                "verified": False,
                "upload_required": False,
            }
        )
        raise UploadError(
            "Public migration image target preflight was ambiguous with "
            f"HTTP {response.status_code}: {public_url}"
        )
    return checked


def verify_public_images(
    *,
    store_base: str,
    operations: list[Mapping[str, Any]],
    results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    verified = results if results is not None else []
    for operation in operations:
        public_url = _public_image_url(store_base, operation)
        expected_hash = str(operation.get("target_hash") or "")
        try:
            response = _get_public_image(public_url)
        except UploadError as exc:
            verified.append(
                {
                    "new_path": operation.get("new_path"),
                    "public_url": public_url,
                    "state": "ambiguous_error",
                    "verified": False,
                    "expected_hash": expected_hash,
                    "error": _safe_error_message(exc),
                }
            )
            raise
        if not _same_public_image_url(public_url, str(response.url)):
            verified.append(
                {
                    "new_path": operation.get("new_path"),
                    "public_url": public_url,
                    "http_status": response.status_code,
                    "final_url": str(response.url),
                    "state": "redirect_rejected",
                    "verified": False,
                    "expected_hash": expected_hash,
                }
            )
            raise UploadError(
                f"Public migration image verification redirected away from its exact path: {public_url}"
            )
        if response.status_code < 200 or response.status_code >= 300:
            verified.append(
                {
                    "new_path": operation.get("new_path"),
                    "public_url": public_url,
                    "http_status": response.status_code,
                    "final_url": str(response.url),
                    "state": "verification_failed",
                    "verified": False,
                    "expected_hash": expected_hash,
                }
            )
            raise UploadError(
                f"Public migration image verification failed with HTTP {response.status_code}: {public_url}"
            )
        observed_hash = hashlib.sha256(response.content).hexdigest()
        if observed_hash != expected_hash:
            verified.append(
                {
                    "new_path": operation.get("new_path"),
                    "public_url": public_url,
                    "http_status": response.status_code,
                    "final_url": str(response.url),
                    "state": "verification_failed",
                    "expected_hash": expected_hash,
                    "observed_hash": observed_hash,
                    "verified": False,
                }
            )
            raise UploadError(f"Public migration image hash mismatch: {public_url}")
        verified.append(
            {
                "new_path": operation.get("new_path"),
                "public_url": public_url,
                "http_status": response.status_code,
                "final_url": str(response.url),
                "expected_hash": expected_hash,
                "observed_hash": observed_hash,
                "state": "verified_after_upload",
                "verified": True,
            }
        )
    return verified


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload hash-pinned image copies for an approved SEO migration."
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--report-file", required=True)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--expected-target-identity", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = Path(args.report_file).expanduser().resolve()
    report: dict[str, Any] = {
        "ok": False,
        "status": "pending",
        "schema_version": "1.0",
        "model": args.model,
        "delete_operations": 0,
        "originals_retained": False,
        "operations": [],
        "target_preflight": [],
        "public_hash_verification": [],
        "write_state": {
            "target_preflight_attempted": False,
            "target_preflight_complete": False,
            "admin_auth_attempted": False,
            "directory_prepare_attempted": False,
            "external_write_attempted": False,
            "upload_attempted": False,
            "upload_confirmed": False,
            "upload_outcome": "not_attempted",
            "post_upload_verification_attempted": False,
            "post_upload_verification_complete": False,
            "upload_required_paths": [],
            "upload_attempted_paths": [],
            "uploaded_paths": [],
            "verified_paths": [],
            "skipped_existing_paths": [],
        },
    }
    write_state = report["write_state"]
    resolved_admin_path = ""

    try:
        if requests is None:
            raise UploadError("Missing dependency: requests")
        if not MODEL_RE.fullmatch(args.model):
            raise UploadError("Model must be exactly six digits.")

        repo_root = Path(args.repo_root).expanduser().resolve()
        manifest_path = Path(args.manifest).expanduser().resolve()
        operations, authorization = load_manifest(manifest_path, args.model)
        report["operations"] = operations
        report["authorization"] = {
            key: authorization[key]
            for key in (
                "operation",
                "migration_run_id",
                "snapshot_id",
                "approval_hash",
                "plan_hash",
                "target_identity",
                "model",
                "csv_sha256",
                "headers",
                "image_operations_hash",
                "claim_hash",
            )
        }
        report["originals_retained"] = all(
            item.get("original_retained") for item in operations
        )
        requested_profile = getattr(args, "profile", None)
        expected_target_identity = getattr(args, "expected_target_identity", None)
        config = resolve_opencart_config(
            repo_root=repo_root, profile=requested_profile
        )
        resolved_admin_path = str(config.get("admin_path") or "")
        resolved_profile = str(
            config.get("profile")
            or requested_profile
            or ("unbound" if expected_target_identity is None else "")
        )
        target_identity = compute_opencart_target_identity(
            store_base=config["store_base"],
            admin_path=config["admin_path"],
            profile=resolved_profile,
        )
        report["target_identity"] = target_identity
        if authorization["target_identity"] != target_identity:
            raise UploadError(
                "Run authorization target does not match resolved OpenCart target."
            )
        if (
            expected_target_identity is not None
            and expected_target_identity != target_identity
        ):
            raise UploadError(
                "Resolved OpenCart target does not match the expected migration target identity."
            )

        preflight_results: list[dict[str, Any]] = report["target_preflight"]
        write_state["target_preflight_attempted"] = True
        preflight_public_images(
            store_base=config["store_base"],
            operations=operations,
            results=preflight_results,
        )
        write_state["target_preflight_complete"] = True
        write_state["skipped_existing_paths"] = [
            item["new_path"]
            for item in preflight_results
            if item.get("state") == "verified_existing"
        ]
        write_state["verified_paths"] = list(
            write_state["skipped_existing_paths"]
        )
        required_paths = [
            item["new_path"]
            for item in preflight_results
            if item.get("upload_required") is True
        ]
        write_state["upload_required_paths"] = required_paths
        required_path_set = set(required_paths)
        upload_operations = [
            item for item in operations if item["new_path"] in required_path_set
        ]

        report["authorization_consumption"] = consume_image_authorization(
            manifest_path, authorization
        )
        write_atomic_report(report_path, report)

        if not upload_operations:
            report.update(
                {
                    "ok": True,
                    "status": "verified_existing",
                    "upload": {
                        "skipped": True,
                        "uploaded_count": 0,
                        "reason": "All public targets already contain the approved bytes.",
                    },
                    "message": "Approved image bytes already exist; no OpenCart write was attempted.",
                }
            )
            write_atomic_report(report_path, report)
            return 0

        if not config["username"] or not config["password"]:
            raise UploadError("OpenCart admin credentials are not configured.")
        admin_index = build_admin_index(config["store_base"], config["admin_path"])
        session = requests.Session()
        write_state["admin_auth_attempted"] = True
        user_token = login(
            session, admin_index, config["username"], config["password"]
        )
        probe = permission_probe(session, admin_index, user_token)
        if not probe.get("can_modify"):
            raise UploadError(
                "OpenCart file manager modify permission was not confirmed."
            )

        remote_dir = f"01_main/{args.model}"
        report["remote_dir"] = remote_dir
        write_state["directory_prepare_attempted"] = True
        write_state["external_write_attempted"] = True
        ensure_remote_nested_dir(session, admin_index, user_token, remote_dir)

        attempted_paths = [item["new_path"] for item in upload_operations]
        write_state["upload_attempted"] = True
        write_state["upload_attempted_paths"] = attempted_paths
        write_state["upload_outcome"] = "unknown"
        upload_result = upload_files(
            session,
            admin_index,
            user_token,
            remote_dir,
            [str(item["target_file"]) for item in upload_operations],
        )
        write_state["upload_confirmed"] = True
        write_state["upload_outcome"] = "confirmed"
        write_state["uploaded_paths"] = attempted_paths
        report["upload"] = upload_result

        public_verification: list[dict[str, Any]] = report[
            "public_hash_verification"
        ]
        write_state["post_upload_verification_attempted"] = True
        verify_public_images(
            store_base=config["store_base"],
            operations=upload_operations,
            results=public_verification,
        )
        write_state["post_upload_verification_complete"] = True
        verified_after_upload = [
            item["new_path"]
            for item in public_verification
            if item.get("verified") is True
        ]
        write_state["verified_paths"] = [
            *write_state["skipped_existing_paths"],
            *verified_after_upload,
        ]
        report.update(
            {
                "ok": True,
                "status": "uploaded_and_verified",
                "message": "Approved image copies uploaded and public hashes verified; originals retained.",
            }
        )
        write_atomic_report(report_path, report)
        return 0
    except Exception as exc:
        if write_state["upload_attempted"] and not write_state["upload_confirmed"]:
            write_state["upload_outcome"] = "unknown_after_failure"
        verified_paths = {
            item.get("new_path")
            for item in [
                *report.get("target_preflight", []),
                *report.get("public_hash_verification", []),
            ]
            if item.get("verified") is True and item.get("new_path")
        }
        write_state["verified_paths"] = sorted(verified_paths)
        report.update(
            {
                "ok": False,
                "status": "failed",
                "error": {
                    "type": exc.__class__.__name__,
                    "message": _safe_error_message(
                        exc, admin_path=resolved_admin_path
                    ),
                },
            }
        )
        try:
            write_atomic_report(report_path, report)
        except Exception as report_exc:
            raise UploadError(
                "Migration image upload failed and its machine-readable report "
                f"could not be written atomically: {report_path}"
            ) from report_exc
        if isinstance(exc, UploadError):
            raise
        raise UploadError(
            _safe_error_message(exc, admin_path=resolved_admin_path)
        ) from exc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except UploadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
