from __future__ import annotations

"""Fail-closed production apply and rollback for approved Phase 4 patches."""

import csv
import hashlib
import json
import os
import re
import socket
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.parse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from ..image_pipeline import convert_image_bytes_to_jpg
from ..repo_paths import REPO_ROOT
from ..seo_phase2 import is_jpeg_bytes
from ..seo_health import evaluate_seo_health
from .approval import ApprovalValidationError, validate_approval_manifest
from .live_validation import build_not_run_report
from .planner import MigrationPlanError, verify_migration_plan
from .snapshot import SnapshotError, verify_catalog_snapshot


class MigrationApplyError(RuntimeError):
    pass


class MigrationPublisher(Protocol):
    target_identity: str

    def preflight_patch(
        self, *, model: str, csv_path: Path, report_path: Path
    ) -> Mapping[str, Any]: ...

    def publish_images(
        self,
        *,
        model: str,
        operations: list[Mapping[str, Any]],
        report_path: Path,
        authorization: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...

    def publish_patch(
        self,
        *,
        model: str,
        csv_path: Path,
        report_path: Path,
        authorization: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ApplyOptions:
    apply: bool
    environment: str
    confirmation: str
    canary: bool = False
    target_identity: str = ""


CSV_FIELD_MAP = {
    "name": "name",
    "description": "description",
    "meta_title": "meta_title",
    "meta_description": "meta_description",
    "meta_keywords": "meta_keyword",
    "category": "category",
    "manufacturer": "manufacturer",
    "mpn": "mpn",
    "related_products": "related_product",
}
ARTIFACT_ONLY_FIELDS = {
    "image_alt_metadata",
    "structured_data_manifest",
    "product_feed_manifest",
}
FORBIDDEN_APPROVAL_FIELDS = {
    "status",
    "active",
    "price",
    "quantity",
    "stock_status",
    "seo_keyword",
    "canonical_url",
    "gallery_image_candidate",
    "identifiers",
    *ARTIFACT_ONLY_FIELDS,
}
REQUIRED_PRODUCTION_SNAPSHOT_FIELDS = {
    "status",
    "name",
    "meta_title",
    "meta_description",
    "meta_keywords",
    "seo_keyword",
    "canonical_url",
    "mpn",
    "main_image",
    "additional_images",
    "category",
    "filters",
    "manufacturer",
    "related_products",
    "price",
    "quantity",
    "stock_status",
    "last_modified",
}
ADAPTER_AUTHORIZATION_TTL_SECONDS = 30 * 60
REDIRECT_EVIDENCE_MAX_AGE_SECONDS = 24 * 60 * 60


def apply_migration(
    *,
    snapshot: Mapping[str, Any],
    plan: Mapping[str, Any],
    approval: Mapping[str, Any],
    options: ApplyOptions,
    target_content_hash: str,
    run_dir: Path | str,
    publisher: MigrationPublisher,
    image_root: Path | str | None = None,
    redirect_confirmation: Mapping[str, Any] | None = None,
    live_validator: Any | None = None,
) -> dict[str, Any]:
    run_path = Path(run_dir).expanduser().resolve()
    active_locks = _acquire_operation_locks(
        run_path=run_path,
        target_identity=_publisher_target_identity(publisher),
        operation="apply",
    )
    try:
        return _apply_migration_impl(
            snapshot=snapshot,
            plan=plan,
            approval=approval,
            options=options,
            target_content_hash=target_content_hash,
            run_dir=run_path,
            publisher=publisher,
            image_root=image_root,
            redirect_confirmation=redirect_confirmation,
            live_validator=live_validator,
        )
    finally:
        _release_operation_locks(active_locks)


def _apply_migration_impl(
    *,
    snapshot: Mapping[str, Any],
    plan: Mapping[str, Any],
    approval: Mapping[str, Any],
    options: ApplyOptions,
    target_content_hash: str,
    run_dir: Path | str,
    publisher: MigrationPublisher,
    image_root: Path | str | None = None,
    redirect_confirmation: Mapping[str, Any] | None = None,
    live_validator: Any | None = None,
) -> dict[str, Any]:
    """Apply approved fields only after every production precondition passes.

    ``target_content_hash`` must be calculated from a fresh full export using
    the same canonical snapshot normalizer.  This function never falls back to
    a generated Product Factory CSV.
    """

    run_path = Path(run_dir).expanduser().resolve()
    run_id = str(plan.get("migration_run_id") or "")
    snapshot_id = str(plan.get("snapshot_id") or "")
    _validate_apply_flags(options, run_id)
    try:
        verify_catalog_snapshot(snapshot, expected_snapshot_id=snapshot_id)
        plan = verify_migration_plan(plan)
    except (SnapshotError, MigrationPlanError) as exc:
        raise MigrationApplyError(f"Immutable migration input is invalid: {exc}") from exc
    try:
        approval = validate_approval_manifest(
            approval,
            snapshot_id=snapshot_id,
            migration_run_id=run_id,
            allowed_fields={*CSV_FIELD_MAP, "filter_values"},
        )
    except ApprovalValidationError as exc:
        raise MigrationApplyError(f"Approval manifest is invalid: {exc}") from exc
    redirect_confirmation_not_before = _latest_rfc3339_timestamp(
        str(plan.get("generated_at") or ""),
        str(approval.get("approved_at") or ""),
        label="redirect approval/plan gate",
    )
    publisher_target_identity = _publisher_target_identity(publisher)
    _validate_plan_snapshot_approval(
        snapshot=snapshot,
        plan=plan,
        approval=approval,
        target_content_hash=target_content_hash,
        target_identity=options.target_identity,
        publisher_target_identity=publisher_target_identity,
    )
    product_approvals = _approval_products(approval)
    if any(
        item.get("approved_slug_change") is True
        and item.get("approved_image_path_change") is True
        for item in product_approvals.values()
    ):
        raise MigrationApplyError(
            "Slug and image-path migrations must use separate reviewed runs."
        )
    if any(
        item.get("approved_image_path_change") is True
        for item in product_approvals.values()
    ) and live_validator is None:
        raise MigrationApplyError(
            "Approved image-path migration requires configured live validation."
        )
    _validate_canary_scope(plan, product_approvals, options.canary)

    field_index = _plan_field_index(plan)
    product_plan_index = {
        str(item.get("model") or ""): item
        for item in plan.get("products", [])
        if isinstance(item, Mapping)
    }
    redirects = _redirect_index(plan)
    image_index = _image_index(plan)
    snapshot_products = _snapshot_product_index(snapshot)
    _validate_approved_slug_set(
        approvals=product_approvals,
        fields_by_model=field_index,
        snapshot_products=snapshot_products,
    )
    selected_operations = _selected_rollback_operations(
        plan=plan, approvals=product_approvals
    )
    rollback = deepcopy(dict(plan.get("rollback_manifest", {})))
    _verify_rollback_manifest_integrity(rollback)
    if not rollback.get("complete") or not rollback.get("created_before_apply"):
        raise MigrationApplyError("A complete pre-apply rollback manifest is required.")
    _reject_existing_apply_claim(run_path / "apply.claim.json")
    rollback["status"] = "apply_prepared"
    rollback["selected_operations"] = selected_operations
    rollback["apply_started_at"] = _utcnow()
    _atomic_json(run_path / "rollback_manifest.json", rollback)
    if not (run_path / "rollback_manifest.json").is_file():
        raise MigrationApplyError("Rollback manifest could not be created before apply.")

    approval_hash = _content_hash(approval)
    _persist_or_verify_reviewed_input(run_path / "apply.approval.json", approval)
    _persist_or_verify_reviewed_input(run_path / "apply.plan.json", plan)
    audit_path = run_path / "audit.jsonl"
    _append_audit(
        audit_path,
        {
            "event": "production_apply_authorized",
            "migration_run_id": run_id,
            "snapshot_id": snapshot_id,
            "environment": options.environment,
            "approval_hash": approval_hash,
            "approved_by": approval.get("approved_by"),
            "canary": options.canary,
            "models": sorted(product_approvals),
            "target_identity": publisher_target_identity,
        },
    )
    _preconfirm_approved_redirects(
        approvals=product_approvals,
        fields_by_model=field_index,
        snapshot_products=snapshot_products,
        redirects_by_model=redirects,
        confirmation=redirect_confirmation,
        target_identity=publisher_target_identity,
        migration_run_id=run_id,
        snapshot_id=snapshot_id,
        plan_hash=str(plan.get("plan_hash") or ""),
        confirmation_not_before=redirect_confirmation_not_before,
        rollback=rollback,
        run_path=run_path,
        approval_hash=approval_hash,
        audit_path=audit_path,
    )
    _validate_health_inputs(plan, product_approvals)

    bundle_dir = run_path / "apply"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "migration_run_id": run_id,
        "snapshot_id": snapshot_id,
        "environment": "production",
        "status": "running",
        "canary": options.canary,
        "started_at": _utcnow(),
        "products": [],
        "production_updated": False,
        "production_write_attempted": False,
        "production_update_state": "not_attempted",
        "publisher_target_identity": publisher_target_identity,
        "rollback_available": True,
        "post_catalog_verification": {
            "status": "not_run",
            "required": True,
            "reason": "fresh full export and monitor command required after adapter action",
        },
    }
    _atomic_json(run_path / "apply_result.json", result)

    applied_operation_keys: set[tuple[str, str]] = set()
    try:
        prepared_products: dict[str, dict[str, Any]] = {}
        for model in sorted(product_approvals):
            approval_item = product_approvals[model]
            current = snapshot_products.get(model)
            if current is None:
                raise MigrationApplyError(f"Approved model is missing from snapshot: {model}")
            fields = field_index.get(model, {})
            patch, artifact_bundle = _build_approved_patch(
                model=model,
                approval=approval_item,
                fields=fields,
                current=current,
                redirects=redirects.get(model, []),
                image_candidates=image_index.get(model, []),
                all_snapshot_products=snapshot_products,
                redirect_confirmation=redirect_confirmation,
                target_identity=publisher_target_identity,
                migration_run_id=run_id,
                snapshot_id=snapshot_id,
                plan_hash=str(plan.get("plan_hash") or ""),
                confirmation_not_before=redirect_confirmation_not_before,
            )
            if approval_item.get("approved_slug_change"):
                artifact_bundle = _required_coupled_artifact_bundle(
                    rollback=rollback,
                    model=model,
                    field="seo_keyword_candidate",
                )
            image_operations: list[dict[str, Any]] = []
            if approval_item.get("approved_image_path_change"):
                if image_root is None:
                    raise MigrationApplyError(
                        f"Approved image migration for {model} requires --image-root."
                    )
                image_operations = _prepare_approved_images(
                    model=model,
                    image_candidates=image_index.get(model, []),
                    image_root=Path(image_root),
                )
                _apply_image_references(
                    patch=patch,
                    current=current,
                    operations=image_operations,
                )
                artifact_bundle.update(
                    _required_coupled_artifact_bundle(
                        rollback=rollback,
                        model=model,
                        field="gallery_image_candidate",
                    )
                )
            _materialize_rollback_expectations(
                rollback=rollback,
                selected_operations=selected_operations,
                model=model,
                patch=patch,
                current=current,
            )

            effective_preflight_health = evaluate_effective_seo_health(
                model=model,
                product_plan=product_plan_index.get(model, {}),
                current=current,
                patch=patch,
                live_validation=_not_run_live_result(
                    model,
                    expected=_live_expected_state(
                        current=current,
                        patch=patch,
                        product_plan=product_plan_index.get(model, {}),
                        catalog_products=snapshot_products,
                        approval=approval_item,
                    ),
                ),
            )
            effective_preflight_blockers = int(
                effective_preflight_health.get("summary", {}).get(
                    "blocking_failures", 0
                )
            )
            if effective_preflight_blockers:
                raise MigrationApplyError(
                    "Approval-effective preflight SEO health has "
                    f"{effective_preflight_blockers} blocking failures for {model}."
                )
            image_live_preflight: Mapping[str, Any] = {}
            if image_operations:
                image_live_preflight = live_validator(
                    model=model,
                    expected=_live_expected_state(
                        current=current,
                        patch={},
                        product_plan=product_plan_index.get(model, {}),
                        catalog_products=snapshot_products,
                        approval=approval_item,
                    ),
                )
                image_live_failures = _image_live_validation_failures(
                    image_live_preflight
                )
                if image_live_failures:
                    raise MigrationApplyError(
                        f"Pre-apply image live validation is incomplete for {model}: "
                        f"{image_live_failures}"
                    )

            if artifact_bundle:
                artifact_dir = bundle_dir / "artifacts" / model
                artifact_dir.mkdir(parents=True, exist_ok=True)
                for name, payload in artifact_bundle.items():
                    _atomic_json(artifact_dir / f"{name}.json", payload)

            csv_path = bundle_dir / "patches" / f"{model}.csv"
            _write_partial_csv(csv_path, model=model, patch=patch)
            _verify_patch_columns(csv_path, approved_patch=patch)
            preflight_report = (
                bundle_dir / "reports" / f"{model}.import-preflight.json"
            )
            _append_audit(
                audit_path,
                {
                    "event": "product_import_preflight_started",
                    "migration_run_id": run_id,
                    "snapshot_id": snapshot_id,
                    "model": model,
                    "patch_hash": _sha256_file(csv_path),
                },
            )
            preflight_result = publisher.preflight_patch(
                model=model, csv_path=csv_path, report_path=preflight_report
            )
            _require_preflight_success(preflight_result, model=model)
            _append_audit(
                audit_path,
                {
                    "event": "product_import_preflight_confirmed",
                    "migration_run_id": run_id,
                    "snapshot_id": snapshot_id,
                    "model": model,
                    "mapping_ok": True,
                    "production_writes": 0,
                },
            )
            prepared_products[model] = {
                "approval": approval_item,
                "current": current,
                "patch": patch,
                "artifact_bundle": artifact_bundle,
                "image_operations": image_operations,
                "csv_path": csv_path,
                "effective_preflight_health": effective_preflight_health,
                "image_live_preflight": dict(image_live_preflight),
                "import_preflight": dict(preflight_result),
            }

        rollback["status"] = "apply_preflight_complete"
        _atomic_json(run_path / "rollback_manifest.json", rollback)
        apply_scopes = [
            {
                "model": model,
                "csv_sha256": _sha256_file(prepared_products[model]["csv_path"]),
                "headers": _csv_headers(prepared_products[model]["csv_path"]),
                "image_operations_hash": _content_hash(
                    prepared_products[model]["image_operations"]
                ),
            }
            for model in sorted(prepared_products)
        ]
        apply_claim_path = run_path / "apply.claim.json"
        _claim_apply_run_once(
            apply_claim_path,
            migration_run_id=run_id,
            snapshot_id=snapshot_id,
            approval_hash=approval_hash,
            plan_hash=str(plan.get("plan_hash") or ""),
            target_identity=publisher_target_identity,
            scopes=apply_scopes,
        )
        scopes_by_model = {str(scope["model"]): scope for scope in apply_scopes}
        for model in sorted(prepared_products):
            prepared = prepared_products[model]
            approval_item = prepared["approval"]
            current = prepared["current"]
            patch = prepared["patch"]
            image_operations = prepared["image_operations"]
            csv_path = prepared["csv_path"]
            authorization = _adapter_authorization(
                operation="apply",
                migration_run_id=run_id,
                snapshot_id=snapshot_id,
                approval_hash=approval_hash,
                plan_hash=str(plan.get("plan_hash") or ""),
                target_identity=publisher_target_identity,
                claim_path=apply_claim_path,
                scope=scopes_by_model[model],
            )
            _persist_or_verify_reviewed_input(
                bundle_dir / "authorizations" / f"{model}.json",
                authorization,
            )
            _mark_model_write_attempted(
                rollback=rollback,
                selected_operations=selected_operations,
                model=model,
            )
            _atomic_json(run_path / "rollback_manifest.json", rollback)
            _append_audit(
                audit_path,
                {
                    "event": "product_write_started",
                    "migration_run_id": run_id,
                    "snapshot_id": snapshot_id,
                    "model": model,
                    "approved_fields": sorted(approval_item.get("approved_fields", [])),
                    "patch_fields": sorted(patch),
                    "before": {
                        field: _current_for_csv_field(current, field)
                        for field in patch
                    },
                    "after": dict(patch),
                    "rollback_available": True,
                },
            )

            image_result: Mapping[str, Any] = {"ok": True, "skipped": True}
            if image_operations:
                _copy_prepared_images(image_operations)
                _append_audit(
                    audit_path,
                    {
                        "event": "local_image_copy_verified",
                        "migration_run_id": run_id,
                        "snapshot_id": snapshot_id,
                        "model": model,
                        "operations": image_operations,
                        "delete_operations": 0,
                        "originals_retained": True,
                    },
                )
                image_report = bundle_dir / "reports" / f"{model}.images.json"
                _begin_production_write_attempt(
                    result,
                    result_path=run_path / "apply_result.json",
                    audit_path=audit_path,
                    run_id=run_id,
                    snapshot_id=snapshot_id,
                    model=model,
                    stage="image_upload",
                )
                image_result = publisher.publish_images(
                    model=model,
                    operations=image_operations,
                    report_path=image_report,
                    authorization=authorization,
                )
                _require_publisher_success(image_result, stage="image_upload", model=model)
                image_write_state = image_result.get("write_state")
                image_status = str(image_result.get("status") or "")
                if (
                    isinstance(image_write_state, Mapping)
                    and image_status == "uploaded_and_verified"
                    and image_write_state.get("external_write_attempted") is True
                    and image_write_state.get("upload_confirmed") is True
                ):
                    result["production_updated"] = True
                    result["production_update_state"] = (
                        "image_upload_confirmed_catalog_pending"
                    )
                elif (
                    isinstance(image_write_state, Mapping)
                    and image_status == "verified_existing"
                    and image_write_state.get("external_write_attempted") is False
                    and image_write_state.get("upload_attempted") is False
                ):
                    if not any(
                        item.get("status") in {"applied", "applied_validation_failed"}
                        for item in result.get("products", [])
                        if isinstance(item, Mapping)
                    ):
                        result["production_updated"] = False
                        result["production_write_attempted"] = False
                    result["production_update_state"] = (
                        "image_already_present_catalog_pending"
                    )
                else:
                    raise MigrationApplyError(
                        f"Image publisher write-state attestation is invalid for {model}."
                    )
                _atomic_json(run_path / "apply_result.json", result)

            import_report = bundle_dir / "reports" / f"{model}.import.json"
            _begin_production_write_attempt(
                result,
                result_path=run_path / "apply_result.json",
                audit_path=audit_path,
                run_id=run_id,
                snapshot_id=snapshot_id,
                model=model,
                stage="partial_import",
            )
            import_result = publisher.publish_patch(
                model=model,
                csv_path=csv_path,
                report_path=import_report,
                authorization=authorization,
            )
            _require_publisher_success(import_result, stage="partial_import", model=model)
            for operation in selected_operations:
                if operation.get("model") == model:
                    applied_operation_keys.add((model, str(operation.get("field"))))
            _mark_rollback_applied(rollback, applied_operation_keys)
            rollback["status"] = "apply_in_progress_rollback_available"
            _atomic_json(run_path / "rollback_manifest.json", rollback)
            _require_zero_destructive_import_counts(import_result, model=model)
            result["production_updated"] = True
            result["production_update_state"] = "catalog_import_confirmed"
            _atomic_json(run_path / "apply_result.json", result)

            validation = (
                live_validator(
                    model=model,
                    expected=_live_expected_state(
                        current=current,
                        patch=patch,
                        product_plan=product_plan_index.get(model, {}),
                        catalog_products=snapshot_products,
                        approval=approval_item,
                    ),
                )
                if live_validator is not None
                else _not_run_live_result(
                    model,
                    expected=_live_expected_state(
                        current=current,
                        patch=patch,
                        product_plan=product_plan_index.get(model, {}),
                        catalog_products=snapshot_products,
                        approval=approval_item,
                    ),
                )
            )
            blocking_live = _blocking_live_failures(validation)
            if image_operations:
                blocking_live = sorted(
                    {
                        *blocking_live,
                        *_image_live_validation_failures(validation),
                    }
                )
            post_apply_health = evaluate_effective_seo_health(
                model=model,
                product_plan=product_plan_index.get(model, {}),
                current=current,
                patch=patch,
                live_validation=validation,
            )
            post_health_blockers = int(
                post_apply_health.get("summary", {}).get("blocking_failures", 0)
            )
            product_result = {
                "model": model,
                "status": (
                    "applied"
                    if not blocking_live and not post_health_blockers
                    else "applied_validation_failed"
                ),
                "patch_file": str(csv_path),
                "patch_hash": _sha256_file(csv_path),
                "patch_fields": sorted(patch),
                "image_result": dict(image_result),
                "import_result": dict(import_result),
                "before": {
                    field: _current_for_csv_field(current, field)
                    for field in patch
                },
                "expected_after": dict(patch),
                "observed_after": None,
                "observed_after_status": "not_run_requires_post_apply_full_export",
                "post_apply_seo_health": post_apply_health,
                "live_validation": validation,
                "blocking_live_failures": blocking_live,
            }
            result["products"].append(product_result)
            _atomic_json(run_path / "apply_result.json", result)
            _append_audit(
                audit_path,
                {
                    "event": "product_write_confirmed",
                    "migration_run_id": run_id,
                    "snapshot_id": snapshot_id,
                    "model": model,
                    "adapter_confirmed": True,
                    "import_report": str(import_report),
                    "live_validation_status": validation.get("status"),
                    "blocking_live_failures": blocking_live,
                    "post_apply_blocking_seo_failures": post_health_blockers,
                },
            )
            if post_health_blockers:
                raise MigrationApplyError(
                    f"Post-apply SEO health has {post_health_blockers} blocking failures for {model}; stopping rollout."
                )
            if blocking_live:
                raise MigrationApplyError(
                    f"Blocking live validation failed for {model}; stopping rollout."
                )
    except Exception as exc:
        result["status"] = "failed"
        result["finished_at"] = _utcnow()
        result["error"] = str(exc)
        if not result.get("production_write_attempted"):
            result["production_updated"] = False
            result["production_update_state"] = "not_attempted"
        elif result.get("production_updated") is not True:
            result["production_updated"] = None
            result["production_update_state"] = "unknown_after_write_attempt"
        _mark_rollback_applied(rollback, applied_operation_keys)
        rollback["status"] = "apply_failed_rollback_available"
        _atomic_json(run_path / "rollback_manifest.json", rollback)
        _atomic_json(run_path / "apply_result.json", result)
        _append_audit(
            audit_path,
            {
                "event": "production_apply_failed",
                "migration_run_id": run_id,
                "snapshot_id": snapshot_id,
                "error": str(exc),
                "rollback_available": True,
            },
        )
        if isinstance(exc, MigrationApplyError):
            raise
        raise MigrationApplyError(str(exc)) from exc

    result["status"] = "applied"
    result["finished_at"] = _utcnow()
    result["production_updated"] = bool(applied_operation_keys)
    result["production_update_state"] = (
        "confirmed" if applied_operation_keys else "not_attempted"
    )
    _mark_rollback_applied(rollback, applied_operation_keys)
    rollback["status"] = "available"
    rollback["apply_finished_at"] = result["finished_at"]
    _atomic_json(run_path / "rollback_manifest.json", rollback)
    _atomic_json(run_path / "apply_result.json", result)
    _append_audit(
        audit_path,
        {
            "event": "production_apply_completed",
            "migration_run_id": run_id,
            "snapshot_id": snapshot_id,
            "production_updated": result["production_updated"],
            "rollback_available": True,
        },
    )
    return result


def rollback_migration(
    *,
    migration_run_id: str,
    environment: str,
    confirmation: str,
    run_dir: Path | str,
    current_products: Mapping[str, Mapping[str, Any]],
    publisher: MigrationPublisher,
    target_identity: str,
    redirect_confirmation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if environment != "production":
        raise MigrationApplyError("Rollback target environment must be exactly production.")
    if confirmation != f"ROLLBACK {migration_run_id}":
        raise MigrationApplyError(
            f"Rollback confirmation must be exactly: ROLLBACK {migration_run_id}"
        )
    run_path = Path(run_dir).expanduser().resolve()
    active_locks = _acquire_operation_locks(
        run_path=run_path,
        target_identity=_publisher_target_identity(publisher),
        operation="rollback",
    )
    try:
        return _rollback_migration_impl(
            migration_run_id=migration_run_id,
            environment=environment,
            confirmation=confirmation,
            run_dir=run_path,
            current_products=current_products,
            publisher=publisher,
            target_identity=target_identity,
            redirect_confirmation=redirect_confirmation,
        )
    finally:
        _release_operation_locks(active_locks)


def _rollback_migration_impl(
    *,
    migration_run_id: str,
    environment: str,
    confirmation: str,
    run_dir: Path | str,
    current_products: Mapping[str, Mapping[str, Any]],
    publisher: MigrationPublisher,
    target_identity: str,
    redirect_confirmation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if environment != "production":
        raise MigrationApplyError("Rollback target environment must be exactly production.")
    if confirmation != f"ROLLBACK {migration_run_id}":
        raise MigrationApplyError(
            f"Rollback confirmation must be exactly: ROLLBACK {migration_run_id}"
        )
    run_path = Path(run_dir).expanduser().resolve()
    rollback_path = run_path / "rollback_manifest.json"
    rollback = _read_json(rollback_path)
    if str(rollback.get("migration_run_id") or "") != migration_run_id:
        raise MigrationApplyError("Rollback manifest run id does not match.")
    _verify_rollback_manifest_integrity(rollback)
    manifest_target_identity = str(rollback.get("target_identity") or "")
    publisher_target_identity = _publisher_target_identity(publisher)
    if (
        not manifest_target_identity
        or manifest_target_identity == "unbound"
        or target_identity != manifest_target_identity
        or publisher_target_identity != manifest_target_identity
    ):
        raise MigrationApplyError(
            "Rollback target identity does not match the immutable migration target."
        )
    apply_claim_path = run_path / "apply.claim.json"
    apply_claim = (
        _load_run_claim(
            apply_claim_path,
            expected_operation="apply",
            migration_run_id=migration_run_id,
            snapshot_id=str(rollback.get("snapshot_id") or ""),
            target_identity=manifest_target_identity,
        )
        if apply_claim_path.is_file()
        else None
    )
    sealed_plan = verify_migration_plan(_read_json(run_path / "apply.plan.json"))
    operations, external_cleanup_models = _derive_rollback_operations(
        run_path=run_path,
        rollback=rollback,
        sealed_plan=sealed_plan,
        apply_claim=apply_claim,
        target_identity=manifest_target_identity,
    )
    if not operations:
        raise MigrationApplyError("No applied rollback operations are available.")

    by_model: dict[str, list[dict[str, Any]]] = {}
    for operation in operations:
        by_model.setdefault(str(operation.get("model") or ""), []).append(operation)
    if apply_claim is not None:
        _bind_rollback_operations_to_apply_evidence(
            run_path=run_path,
            apply_claim=apply_claim,
            operations=by_model,
            external_cleanup_models=external_cleanup_models,
        )
        redirect_not_before = str(apply_claim.get("claimed_at") or "")
    else:
        _bind_external_redirect_cleanup_only(
            run_path=run_path,
            sealed_plan=sealed_plan,
            operations=by_model,
            target_identity=manifest_target_identity,
        )
        redirect_not_before = str(sealed_plan.get("generated_at") or "")
    external_cleanup_only = apply_claim is None
    _verify_rollback_current_state(by_model, current_products)
    _validate_reverse_redirects(
        by_model,
        redirect_confirmation,
        target_identity=manifest_target_identity,
        migration_run_id=migration_run_id,
        snapshot_id=str(rollback.get("snapshot_id") or ""),
        plan_hash=str(sealed_plan.get("plan_hash") or ""),
        confirmation_not_before=redirect_not_before,
    )

    audit_path = run_path / "audit.jsonl"
    result = {
        "schema_version": "1.0",
        "migration_run_id": migration_run_id,
        "status": "running",
        "started_at": _utcnow(),
        "products": [],
        "price_stock_status_excluded": True,
        "target_identity": manifest_target_identity,
        "production_write_attempted": False,
        "production_update_state": "not_attempted",
    }
    _atomic_json(run_path / "rollback_result.json", result)
    _append_audit(
        audit_path,
        {
            "event": "production_rollback_authorized",
            "migration_run_id": migration_run_id,
            "models": sorted(by_model),
            "target_identity": manifest_target_identity,
        },
    )
    try:
        for model in sorted(by_model):
            patch: dict[str, Any] = {}
            for operation in by_model[model]:
                if operation.get("_rollback_action") == "noop":
                    continue
                logical = str(operation.get("field") or "")
                _add_restore_value(patch, logical, operation)
            if not external_cleanup_only:
                _prepare_artifact_rollback(run_path, model, by_model[model])
            patch_path: Path | None = None
            publish_result: Mapping[str, Any] = {
                "ok": True,
                "skipped": True,
                "reason": "attempted_write_did_not_change_catalog_state",
            }
            if patch:
                patch_path = run_path / "rollback" / "patches" / f"{model}.csv"
                _write_partial_csv(patch_path, model=model, patch=patch)
                preflight_path = (
                    run_path
                    / "rollback"
                    / "reports"
                    / f"{model}.import-preflight.json"
                )
                preflight = publisher.preflight_patch(
                    model=model, csv_path=patch_path, report_path=preflight_path
                )
                _require_preflight_success(preflight, model=model)
                rollback_scope = {
                    "model": model,
                    "csv_sha256": _sha256_file(patch_path),
                    "headers": _csv_headers(patch_path),
                    "image_operations_hash": _content_hash([]),
                }
                rollback_claim_path = _next_rollback_claim_path(run_path, model)
                _claim_rollback_model(
                    rollback_claim_path,
                    migration_run_id=migration_run_id,
                    snapshot_id=str(rollback.get("snapshot_id") or ""),
                    approval_hash=str(apply_claim.get("approval_hash") or ""),
                    plan_hash=str(apply_claim.get("plan_hash") or ""),
                    target_identity=manifest_target_identity,
                    scope=rollback_scope,
                )
                rollback_authorization = _adapter_authorization(
                    operation="rollback",
                    migration_run_id=migration_run_id,
                    snapshot_id=str(rollback.get("snapshot_id") or ""),
                    approval_hash=str(apply_claim.get("approval_hash") or ""),
                    plan_hash=str(apply_claim.get("plan_hash") or ""),
                    target_identity=manifest_target_identity,
                    claim_path=rollback_claim_path,
                    scope=rollback_scope,
                )
                report_path = run_path / "rollback" / "reports" / f"{model}.import.json"
                _append_audit(
                    audit_path,
                    {
                        "event": "product_rollback_started",
                        "migration_run_id": migration_run_id,
                        "model": model,
                        "patch_fields": sorted(patch),
                        "target_identity": manifest_target_identity,
                    },
                )
                result["production_write_attempted"] = True
                result["production_update_state"] = (
                    "rollback_write_attempted_state_unknown"
                )
                _atomic_json(run_path / "rollback_result.json", result)
                publish_result = publisher.publish_patch(
                    model=model,
                    csv_path=patch_path,
                    report_path=report_path,
                    authorization=rollback_authorization,
                )
                _require_publisher_success(
                    publish_result, stage="rollback_import", model=model
                )
                _require_zero_destructive_import_counts(publish_result, model=model)
            if not external_cleanup_only:
                _restore_artifact_bundle(run_path, model, by_model[model])
            rolled_at = _utcnow()
            model_keys = {
                (model, str(operation.get("field")))
                for operation in by_model[model]
            }
            for operation in rollback.get("operations", []):
                if (str(operation.get("model")), str(operation.get("field"))) in model_keys:
                    operation["rolled_back"] = True
                    operation["rolled_back_at"] = rolled_at
                    matching = next(
                        (
                            item
                            for item in by_model[model]
                            if item.get("field") == operation.get("field")
                        ),
                        {},
                    )
                    operation["rollback_resolution"] = str(
                        matching.get("_rollback_action") or "restore"
                    )
                    if external_cleanup_only:
                        operation["external_redirect_cleanup_verified"] = True
                        operation["external_redirect_cleanup_verified_at"] = rolled_at
            rollback["status"] = "rollback_in_progress"
            _atomic_json(rollback_path, rollback)
            result["production_update_state"] = "rollback_product_confirmed"
            result["products"].append(
                {
                    "model": model,
                    "status": "rolled_back" if patch else "resolved_noop",
                    "patch_file": str(patch_path) if patch_path else None,
                    "patch_fields": sorted(patch),
                    "publisher_result": dict(publish_result),
                }
            )
            _atomic_json(run_path / "rollback_result.json", result)
            _append_audit(
                audit_path,
                {
                    "event": "product_rollback_confirmed",
                    "migration_run_id": migration_run_id,
                    "model": model,
                    "adapter_confirmed": True,
                },
            )
    except Exception as exc:
        rollback["status"] = "rollback_failed_partial_state_preserved"
        rollback["rollback_error"] = str(exc)
        _atomic_json(rollback_path, rollback)
        result["status"] = "failed"
        result["finished_at"] = _utcnow()
        result["error"] = str(exc)
        if result.get("production_write_attempted") and not result["products"]:
            result["production_update_state"] = "unknown_after_rollback_write_attempt"
        _atomic_json(run_path / "rollback_result.json", result)
        _append_audit(
            audit_path,
            {
                "event": "production_rollback_failed",
                "migration_run_id": migration_run_id,
                "error": str(exc),
                "completed_models": [item["model"] for item in result["products"]],
            },
        )
        if isinstance(exc, MigrationApplyError):
            raise
        raise MigrationApplyError(str(exc)) from exc
    rollback["status"] = "rolled_back"
    rollback["rollback_finished_at"] = _utcnow()
    _atomic_json(rollback_path, rollback)
    if external_cleanup_models:
        cleanup_path = run_path / "redirect_cleanup_required.json"
        cleanup = _read_json(cleanup_path)
        cleanup["status"] = "external_forward_redirect_cleanup_verified"
        cleanup["cleanup_verified_at"] = rollback["rollback_finished_at"]
        # Status/timestamp are operational fields after the original evidence
        # hash; retain the immutable content_hash for the reviewed requirement.
        _atomic_json(cleanup_path, cleanup)
    result["status"] = "rolled_back"
    result["production_update_state"] = "rollback_confirmed"
    result["finished_at"] = rollback["rollback_finished_at"]
    _atomic_json(run_path / "rollback_result.json", result)
    return result


class OpenCartPartialCsvPublisher:
    """Explicit adapter around the existing Karapuz partial-import tool.

    Construction alone does nothing.  Calls are made only from the gated apply
    functions above.  Credentials remain in the existing environment/config
    resolver and are never placed in migration artifacts.
    """

    def __init__(self, *, import_profile: str) -> None:
        if not import_profile.strip():
            raise MigrationApplyError("An explicit OpenCart migration import profile is required.")
        self.import_profile = import_profile.strip()
        self.target_identity = resolve_opencart_target_identity(self.import_profile)

    def preflight_patch(
        self, *, model: str, csv_path: Path, report_path: Path
    ) -> Mapping[str, Any]:
        return self._run_import_adapter(
            model=model,
            csv_path=csv_path,
            report_path=report_path,
            dry_run=True,
        )

    def publish_images(
        self,
        *,
        model: str,
        operations: list[Mapping[str, Any]],
        report_path: Path,
        authorization: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        manifest_path = report_path.with_suffix(".manifest.json")
        _atomic_json(
            manifest_path,
            {
                "schema_version": "1.0",
                "model": model,
                "operations": operations,
                "authorization": dict(authorization),
            },
        )
        script = REPO_ROOT / "tools" / "opencart_migration_upload_images.py"
        command = [
            sys.executable,
            str(script),
            "--model",
            model,
            "--manifest",
            str(manifest_path),
            "--repo-root",
            str(REPO_ROOT),
            "--profile",
            self.import_profile,
            "--expected-target-identity",
            self.target_identity,
            "--report-file",
            str(report_path),
        ]
        result = _run_adapter(command, report_path)
        if result.get("target_identity") != self.target_identity:
            raise MigrationApplyError(
                "OpenCart image adapter did not attest the expected target identity."
            )
        return result

    def publish_patch(
        self,
        *,
        model: str,
        csv_path: Path,
        report_path: Path,
        authorization: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return self._run_import_adapter(
            model=model,
            csv_path=csv_path,
            report_path=report_path,
            dry_run=False,
            authorization=authorization,
        )

    def _run_import_adapter(
        self,
        *,
        model: str,
        csv_path: Path,
        report_path: Path,
        dry_run: bool,
        authorization: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        script = REPO_ROOT / "tools" / "opencart_import_csv_playwright.py"
        command = [
            sys.executable,
            str(script),
            "--model",
            model,
            "--repo-root",
            str(REPO_ROOT),
            "--csv-file",
            str(csv_path),
            "--profile",
            self.import_profile,
            "--expected-target-identity",
            self.target_identity,
            "--expected-csv-sha256",
            _sha256_file(csv_path),
            "--allow-partial-csv",
            "--report-file",
            str(report_path),
        ]
        if dry_run:
            command.append("--dry-run")
        else:
            if not isinstance(authorization, Mapping):
                raise MigrationApplyError(
                    "Production partial import requires run-bound authorization."
                )
            authorization_path = report_path.with_suffix(".authorization.json")
            _atomic_json(authorization_path, dict(authorization))
            command.extend(
                ["--migration-authorization-file", str(authorization_path)]
            )
        result = _run_adapter(command, report_path)
        if result.get("target_identity") != self.target_identity:
            raise MigrationApplyError(
                "OpenCart import adapter did not attest the expected target identity."
            )
        return result


def resolve_opencart_target_identity(import_profile: str) -> str:
    """Resolve a non-secret target fingerprint from the actual OpenCart config."""

    try:
        from tools.opencart_config import (
            compute_opencart_target_identity,
            resolve_opencart_config,
        )
    except ImportError as exc:  # pragma: no cover - packaging/configuration failure
        raise MigrationApplyError("OpenCart target configuration resolver is unavailable.") from exc
    profile = str(import_profile or "").strip()
    if not profile:
        raise MigrationApplyError("An explicit OpenCart import profile is required.")
    config = resolve_opencart_config(repo_root=REPO_ROOT, profile=profile)
    try:
        return compute_opencart_target_identity(
            store_base=str(config.get("store_base") or ""),
            admin_path=str(config.get("admin_path") or ""),
            profile=str(config.get("profile") or ""),
        )
    except ValueError as exc:
        raise MigrationApplyError(str(exc)) from exc


def _validate_apply_flags(options: ApplyOptions, run_id: str) -> None:
    if not options.apply:
        raise MigrationApplyError("Apply rejected: the explicit --apply flag is required.")
    if options.environment != "production":
        raise MigrationApplyError(
            "Apply rejected: target environment must be exactly production."
        )
    if not options.target_identity.strip():
        raise MigrationApplyError(
            "Apply rejected: an explicit non-secret target identity is required."
        )
    if options.confirmation != f"APPLY {run_id}":
        raise MigrationApplyError(
            f"Apply confirmation must be exactly: APPLY {run_id}"
        )


def _validate_plan_snapshot_approval(
    *,
    snapshot: Mapping[str, Any],
    plan: Mapping[str, Any],
    approval: Mapping[str, Any],
    target_content_hash: str,
    target_identity: str,
    publisher_target_identity: str,
) -> None:
    metadata = snapshot.get("metadata", {})
    metadata = metadata if isinstance(metadata, Mapping) else {}
    snapshot_id = str(metadata.get("snapshot_id") or snapshot.get("snapshot_id") or "")
    snapshot_hash = str(metadata.get("content_hash") or "")
    catalog_hash = str(metadata.get("catalog_hash") or "")
    if not snapshot_id or snapshot_id != str(plan.get("snapshot_id") or ""):
        raise MigrationApplyError("Plan snapshot id does not match the loaded snapshot.")
    if snapshot_id != str(approval.get("snapshot_id") or ""):
        raise MigrationApplyError("Approval snapshot id does not match.")
    if str(plan.get("migration_run_id") or "") != str(
        approval.get("migration_run_id") or ""
    ):
        raise MigrationApplyError("Approval migration run id does not match.")
    environment = str(metadata.get("source_environment") or metadata.get("environment") or "")
    if environment != "production":
        raise MigrationApplyError(
            "Production apply requires a snapshot explicitly captured as production."
        )
    snapshot_target_identity = str(metadata.get("target_identity") or "")
    if snapshot_target_identity in {"", "unbound"}:
        raise MigrationApplyError(
            "Production snapshot is not bound to a resolved OpenCart target identity."
        )
    if str(plan.get("target_identity") or "") != snapshot_target_identity:
        raise MigrationApplyError(
            "Migration plan target identity does not match the immutable snapshot."
        )
    if snapshot_target_identity != target_identity:
        raise MigrationApplyError(
            "Target identity does not match the target bound into the snapshot."
        )
    if publisher_target_identity != target_identity:
        raise MigrationApplyError(
            "Resolved OpenCart profile target does not match --target-identity."
        )
    available_fields = set(metadata.get("available_fields", []) or [])
    missing_required = sorted(REQUIRED_PRODUCTION_SNAPSHOT_FIELDS - available_fields)
    if missing_required:
        raise MigrationApplyError(
            "Production snapshot is incomplete; missing required published fields: "
            f"{missing_required}"
        )
    if any(
        isinstance(item, Mapping)
        and item.get("approved_image_path_change") is True
        for item in approval.get("products", [])
    ) and "description" not in available_fields:
        raise MigrationApplyError(
            "Approved image migration requires current description HTML in the snapshot."
        )
    if not snapshot_hash or snapshot_hash != str(plan.get("snapshot_content_hash") or ""):
        raise MigrationApplyError("Snapshot hash no longer matches the migration plan.")
    if not catalog_hash or catalog_hash != str(plan.get("snapshot_catalog_hash") or ""):
        raise MigrationApplyError("Snapshot catalog hash no longer matches the migration plan.")
    if target_content_hash != catalog_hash:
        raise MigrationApplyError(
            "Catalog changed after the snapshot; take a new full export and re-plan."
        )
    rollback = plan.get("rollback_manifest", {})
    if not isinstance(rollback, Mapping) or not rollback.get("complete"):
        raise MigrationApplyError("Rollback manifest is missing or incomplete.")


def _approval_products(approval: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    products = approval.get("products", [])
    if not isinstance(products, list) or not products:
        raise MigrationApplyError("Approval manifest contains no products.")
    result: dict[str, dict[str, Any]] = {}
    for raw in products:
        if not isinstance(raw, Mapping):
            raise MigrationApplyError("Approval product entry must be an object.")
        model = str(raw.get("model") or "")
        if not re.fullmatch(r"[0-9]{6}", model) or model in result:
            raise MigrationApplyError(f"Invalid or duplicate approved model: {model!r}")
        fields = raw.get("approved_fields", [])
        if not isinstance(fields, list) or any(not isinstance(item, str) for item in fields):
            raise MigrationApplyError(f"approved_fields is invalid for {model}.")
        forbidden = sorted(set(fields) & FORBIDDEN_APPROVAL_FIELDS)
        if forbidden:
            raise MigrationApplyError(
                f"Approval contains forbidden or non-writable fields for {model}: {forbidden}"
            )
        result[model] = dict(raw)
    return result


def _validate_canary_scope(
    plan: Mapping[str, Any], approvals: Mapping[str, Any], canary: bool
) -> None:
    if not canary:
        return
    proposal = plan.get("canary_proposal", {})
    proposed = set(proposal.get("proposed_models", [])) if isinstance(proposal, Mapping) else set()
    unproposed = sorted(set(approvals) - proposed)
    if unproposed:
        raise MigrationApplyError(
            f"Canary approval contains models outside the reviewed proposal: {unproposed}"
        )


def _validate_health_inputs(
    plan: Mapping[str, Any], approvals: Mapping[str, Any]
) -> None:
    products = {
        str(item.get("model") or ""): item
        for item in plan.get("products", [])
        if isinstance(item, Mapping)
    }
    missing = sorted(
        model
        for model in approvals
        if not isinstance(products.get(model, {}).get("seo_health_input"), Mapping)
    )
    if missing:
        raise MigrationApplyError(
            f"Apply rejected: approval-effective SEO-health inputs are missing: {missing}"
        )
    blocking = sorted(
        model
        for model in approvals
        if int(
            products.get(model, {})
            .get("seo_health_after", {})
            .get("summary", {})
            .get("blocking_failures", 0)
            or 0
        )
        > 0
    )
    if blocking:
        raise MigrationApplyError(
            "Apply rejected: reviewed candidate SEO health contains blocking "
            f"failures for {blocking}."
        )


def _plan_field_index(plan: Mapping[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for product in plan.get("products", []):
        if not isinstance(product, Mapping):
            continue
        model = str(product.get("model") or "")
        result[model] = {
            str(field.get("field") or ""): dict(field)
            for field in product.get("fields", [])
            if isinstance(field, Mapping)
        }
    return result


def _redirect_index(plan: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for item in plan.get("redirect_candidates", []):
        if isinstance(item, Mapping):
            result.setdefault(str(item.get("model") or ""), []).append(dict(item))
    return result


def _image_index(plan: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for item in plan.get("image_candidates", []):
        if isinstance(item, Mapping):
            result.setdefault(str(item.get("model") or ""), []).append(dict(item))
    return result


def _snapshot_product_index(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("model") or ""): dict(row)
        for row in snapshot.get("products", [])
        if isinstance(row, Mapping)
    }


def _build_approved_patch(
    *,
    model: str,
    approval: Mapping[str, Any],
    fields: Mapping[str, Mapping[str, Any]],
    current: Mapping[str, Any],
    redirects: list[Mapping[str, Any]],
    image_candidates: list[Mapping[str, Any]],
    all_snapshot_products: Mapping[str, Mapping[str, Any]],
    redirect_confirmation: Mapping[str, Any] | None,
    target_identity: str,
    migration_run_id: str,
    snapshot_id: str,
    plan_hash: str,
    confirmation_not_before: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    patch: dict[str, Any] = {}
    artifacts: dict[str, Any] = {}
    for logical in approval.get("approved_fields", []):
        field = fields.get(str(logical))
        if field is None:
            raise MigrationApplyError(f"Approved field is absent from plan for {model}: {logical}")
        if field.get("classification") not in {"safe_content_update", "review_required"}:
            raise MigrationApplyError(
                f"Approved field is not writable for {model}: {logical} ({field.get('classification')})"
            )
        if logical == "filter_values":
            values = field.get("candidate_value")
            if not isinstance(values, Mapping):
                raise MigrationApplyError(f"Approved filter values are invalid for {model}.")
            current_filters = current.get("filters")
            if not isinstance(current_filters, Mapping) or any(
                not str(header).startswith("filter_group:")
                for header in current_filters
            ):
                raise MigrationApplyError(
                    f"Filter migration for {model} requires exact exported "
                    "filter_group:* source headers for reversible rollback."
                )
            if set(map(str, current_filters)) != set(map(str, values)):
                raise MigrationApplyError(
                    f"Filter migration for {model} cannot add or remove filter "
                    "columns; current and candidate filter_group:* sets must match."
                )
            for header, value in sorted(values.items()):
                if not str(header).startswith("filter_group:"):
                    raise MigrationApplyError(f"Unsafe filter column for {model}: {header}")
                existing_values = {
                    str(product.get("filters", {}).get(str(header)) or "")
                    for product in all_snapshot_products.values()
                    if isinstance(product.get("filters"), Mapping)
                    and str(product.get("filters", {}).get(str(header)) or "")
                }
                if str(value or "") not in existing_values:
                    raise MigrationApplyError(
                        f"Filter value change for {model}/{header} is not an exact "
                        "existing catalog value; auto-creation is forbidden."
                    )
                patch[str(header)] = value
            continue
        if logical == "identifiers":
            values = field.get("candidate_value")
            if not isinstance(values, Mapping):
                raise MigrationApplyError(f"Approved identifiers are invalid for {model}.")
            for key, value in sorted(values.items()):
                if key not in {"ean", "gtin", "upc", "jan", "isbn"}:
                    raise MigrationApplyError(f"Unsupported identifier field for {model}: {key}")
                patch[str(key)] = value
            continue
        if logical in ARTIFACT_ONLY_FIELDS:
            artifacts[str(logical)] = field.get("candidate_value")
            continue
        csv_field = CSV_FIELD_MAP.get(str(logical))
        if csv_field is None:
            raise MigrationApplyError(f"No safe production writer exists for field: {logical}")
        value = field.get("candidate_value")
        if logical == "category":
            existing_categories = {
                str(product.get("category") or "").strip()
                for product in all_snapshot_products.values()
                if str(product.get("category") or "").strip()
            }
            if str(value or "").strip() not in existing_categories:
                raise MigrationApplyError(
                    f"Category change for {model} is not attested as an existing "
                    "catalog category; auto-creation is forbidden."
                )
        if logical == "manufacturer":
            existing_manufacturers = {
                str(product.get("manufacturer") or "").strip()
                for product in all_snapshot_products.values()
                if str(product.get("manufacturer") or "").strip()
            }
            if str(value or "").strip() not in existing_manufacturers:
                raise MigrationApplyError(
                    f"Manufacturer change for {model} is not attested as an "
                    "existing catalog manufacturer."
                )
        if logical == "description":
            _require_besco_references_preserved(
                before=str(current.get("description") or ""),
                after=str(value or ""),
            )
        if logical == "related_products" and isinstance(value, list):
            value = ",".join(str(item) for item in value)
        patch[csv_field] = value

    if approval.get("approved_slug_change"):
        slug_field = fields.get("seo_keyword_candidate", {})
        url_field = fields.get("canonical_url", {})
        if slug_field.get("classification") != "review_required" or url_field.get(
            "classification"
        ) != "review_required":
            raise MigrationApplyError(f"No reviewable slug change exists for {model}.")
        new_slug = str(slug_field.get("candidate_value") or "")
        _validate_slug_uniqueness(model, new_slug, all_snapshot_products)
        new_canonical_url = str(url_field.get("candidate_value") or "")
        _validate_canonical_slug_change(
            model=model,
            current_url=str(current.get("canonical_url") or ""),
            candidate_url=new_canonical_url,
            new_slug=new_slug,
        )
        patch["seo_keyword"] = new_slug
        patch["product_url"] = new_canonical_url
        missing_coupled_artifacts: list[str] = []
        for artifact_name in ("structured_data_manifest", "product_feed_manifest"):
            artifact_field = fields.get(artifact_name, {})
            value = artifact_field.get("candidate_value")
            if isinstance(value, Mapping):
                updated = dict(value)
                if artifact_name == "structured_data_manifest":
                    updated["url"] = patch["product_url"]
                else:
                    updated["link"] = patch["product_url"]
                artifacts[artifact_name] = updated
            else:
                missing_coupled_artifacts.append(artifact_name)
        if missing_coupled_artifacts:
            raise MigrationApplyError(
                f"Slug change for {model} cannot update required coupled artifacts: "
                f"{missing_coupled_artifacts}"
            )
        _require_redirect_confirmation(
            model=model,
            candidates=redirects,
            confirmation=redirect_confirmation,
            target_identity=target_identity,
            migration_run_id=migration_run_id,
            snapshot_id=snapshot_id,
            plan_hash=plan_hash,
            confirmation_not_before=confirmation_not_before,
        )

    if approval.get("approved_image_path_change"):
        if not any(
            str(item.get("current_path") or "") != str(item.get("candidate_path") or "")
            for item in image_candidates
        ):
            raise MigrationApplyError(f"No reviewable image path change exists for {model}.")
    if not patch and not artifacts and not approval.get("approved_image_path_change"):
        raise MigrationApplyError(f"Approval for {model} selects no changes.")
    return patch, artifacts


def _require_redirect_confirmation(
    *,
    model: str,
    candidates: list[Mapping[str, Any]],
    confirmation: Mapping[str, Any] | None,
    target_identity: str,
    migration_run_id: str,
    snapshot_id: str,
    plan_hash: str,
    confirmation_not_before: str,
) -> None:
    if not candidates:
        raise MigrationApplyError(f"Slug change for {model} has no redirect requirement.")
    if not isinstance(confirmation, Mapping):
        raise MigrationApplyError(
            "This repository cannot apply redirects; an external applied-and-verified redirect confirmation is required."
        )
    _validate_redirect_confirmation_document(
        confirmation,
        expected_target_identity=target_identity,
        expected_migration_run_id=migration_run_id,
        expected_snapshot_id=snapshot_id,
        expected_plan_hash=plan_hash,
        not_before=confirmation_not_before,
    )
    confirmed = confirmation.get("redirects", [])
    namespace_paths = _redirect_namespace_paths(confirmation)
    for candidate in candidates:
        if _normalize_route_path(str(candidate.get("new_path") or "")) in namespace_paths:
            raise MigrationApplyError(
                f"SEO URL candidate is not globally unique for {model}: "
                f"{candidate.get('new_path')}"
            )
        match = next(
            (
                item
                for item in confirmed
                if isinstance(item, Mapping)
                and item.get("model") == model
                and _normalize_route_path(str(item.get("old_path") or ""))
                == _normalize_route_path(str(candidate.get("old_path") or ""))
                and _normalize_route_path(str(item.get("new_path") or ""))
                == _normalize_route_path(str(candidate.get("new_path") or ""))
                and item.get("status_code") == 301
            ),
            None,
        )
        if not match or not all(
            match.get(key) is True for key in ("approved", "applied", "verified")
        ):
            raise MigrationApplyError(
                f"Redirect for {model} is not externally applied and verified."
            )


def _record_external_redirect_preconfirmation(
    *,
    rollback: dict[str, Any],
    run_path: Path,
    model: str,
    candidates: list[Mapping[str, Any]],
    migration_run_id: str,
    snapshot_id: str,
    plan_hash: str,
    approval_hash: str,
    target_identity: str,
) -> None:
    operation = next(
        (
            item
            for item in rollback.get("operations", [])
            if isinstance(item, Mapping)
            and item.get("model") == model
            and item.get("field") == "seo_keyword_candidate"
        ),
        None,
    )
    if not isinstance(operation, dict):
        raise MigrationApplyError(
            f"Redirect cleanup rollback operation is missing for {model}."
        )
    operation["external_redirect_preconfirmed"] = True
    operation["external_redirect_preconfirmed_at"] = _utcnow()
    path = run_path / "redirect_cleanup_required.json"
    entries = [
        {
            "model": model,
            "old_path": str(item.get("old_path") or ""),
            "new_path": str(item.get("new_path") or ""),
            "status_code": 301,
            "required_action": "remove_forward_redirect_if_catalog_write_is_not_confirmed",
        }
        for item in candidates
    ]
    if not entries:
        raise MigrationApplyError(f"Redirect cleanup evidence is missing for {model}.")
    if path.is_file():
        payload = _read_json(path)
        expected_keys = {
            "schema_version",
            "migration_run_id",
            "snapshot_id",
            "plan_hash",
            "approval_hash",
            "target_identity",
            "created_at",
            "status",
            "redirects",
            "content_hash",
        }
        if set(payload) != expected_keys:
            raise MigrationApplyError(
                "Redirect cleanup evidence has an invalid exact shape."
            )
        material = dict(payload)
        stored_hash = str(material.pop("content_hash") or "")
        if _content_hash(material) != stored_hash:
            raise MigrationApplyError("Redirect cleanup evidence content hash changed.")
        expected_binding = {
            "migration_run_id": migration_run_id,
            "snapshot_id": snapshot_id,
            "plan_hash": plan_hash,
            "approval_hash": approval_hash,
            "target_identity": target_identity,
        }
        if any(payload.get(key) != value for key, value in expected_binding.items()):
            raise MigrationApplyError("Redirect cleanup evidence binding changed.")
        existing_entries = payload.get("redirects", [])
        if not isinstance(existing_entries, list):
            raise MigrationApplyError("Redirect cleanup evidence is invalid.")
        entries = [
            *[dict(item) for item in existing_entries if isinstance(item, Mapping)],
            *entries,
        ]
        created_at = str(payload.get("created_at") or _utcnow())
    else:
        created_at = _utcnow()
    deduped = {
        (item["model"], item["old_path"], item["new_path"]): item
        for item in entries
    }
    payload = {
        "schema_version": "1.0",
        "migration_run_id": migration_run_id,
        "snapshot_id": snapshot_id,
        "plan_hash": plan_hash,
        "approval_hash": approval_hash,
        "target_identity": target_identity,
        "created_at": created_at,
        "status": "external_forward_redirect_active_cleanup_required_on_failed_apply",
        "redirects": [deduped[key] for key in sorted(deduped)],
    }
    payload["content_hash"] = _content_hash(payload)
    _atomic_json(path, payload)


def _validate_slug_uniqueness(
    model: str, new_slug: str, products: Mapping[str, Mapping[str, Any]]
) -> None:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", new_slug):
        raise MigrationApplyError(f"Invalid SEO keyword candidate for {model}: {new_slug}")
    duplicates = sorted(
        other_model
        for other_model, row in products.items()
        if other_model != model
        and str(row.get("seo_keyword") or "").strip().casefold() == new_slug.casefold()
    )
    if duplicates:
        raise MigrationApplyError(
            f"SEO keyword candidate is not unique for {model}; conflicts with {duplicates}."
        )


def _validate_canonical_slug_change(
    *, model: str, current_url: str, candidate_url: str, new_slug: str
) -> None:
    current = urllib.parse.urlsplit(str(current_url or ""))
    candidate = urllib.parse.urlsplit(str(candidate_url or ""))
    if (
        candidate.username
        or candidate.password
        or candidate.query
        or candidate.fragment
        or candidate.path == ""
        or _normalize_route_path(candidate.path) != _normalize_route_path(f"/{new_slug}")
    ):
        raise MigrationApplyError(
            f"Canonical URL candidate is not the exact approved slug path for {model}."
        )
    current_is_absolute = bool(current.scheme or current.netloc)
    candidate_is_absolute = bool(candidate.scheme or candidate.netloc)
    if current_is_absolute:
        if (
            current.scheme.casefold() not in {"http", "https"}
            or not current.hostname
            or current.username
            or current.password
            or candidate.scheme.casefold() not in {"http", "https"}
            or not candidate.hostname
            or (
                current.scheme.casefold(),
                current.hostname.casefold(),
                current.port,
            )
            != (
                candidate.scheme.casefold(),
                candidate.hostname.casefold(),
                candidate.port,
            )
        ):
            raise MigrationApplyError(
                f"Canonical URL candidate changes the published origin for {model}."
            )
    elif candidate_is_absolute:
        raise MigrationApplyError(
            f"Relative published canonical URL cannot change to another origin for {model}."
        )


def _validate_approved_slug_set(
    *,
    approvals: Mapping[str, Mapping[str, Any]],
    fields_by_model: Mapping[str, Mapping[str, Mapping[str, Any]]],
    snapshot_products: Mapping[str, Mapping[str, Any]],
) -> None:
    candidates: dict[str, list[str]] = {}
    for model, approval in approvals.items():
        if approval.get("approved_slug_change") is not True:
            continue
        slug = str(
            fields_by_model.get(model, {})
            .get("seo_keyword_candidate", {})
            .get("candidate_value")
            or ""
        ).casefold()
        _validate_slug_uniqueness(model, slug, snapshot_products)
        candidates.setdefault(slug, []).append(model)
    duplicates = {
        slug: sorted(models)
        for slug, models in candidates.items()
        if slug and len(models) > 1
    }
    if duplicates:
        raise MigrationApplyError(
            f"Approved SEO keyword candidates are not unique: {duplicates}"
        )


def _preconfirm_approved_redirects(
    *,
    approvals: Mapping[str, Mapping[str, Any]],
    fields_by_model: Mapping[str, Mapping[str, Mapping[str, Any]]],
    snapshot_products: Mapping[str, Mapping[str, Any]],
    redirects_by_model: Mapping[str, list[Mapping[str, Any]]],
    confirmation: Mapping[str, Any] | None,
    target_identity: str,
    migration_run_id: str,
    snapshot_id: str,
    plan_hash: str,
    confirmation_not_before: str,
    rollback: dict[str, Any],
    run_path: Path,
    approval_hash: str,
    audit_path: Path,
) -> None:
    """Record externally active redirects before any later fallible preflight.

    A valid confirmation means the redirect owner has already changed an
    external production system.  Persist its cleanup obligation immediately,
    even if a later health, artifact, image, or importer gate rejects apply.
    """

    for model in sorted(approvals):
        approval = approvals[model]
        if approval.get("approved_slug_change") is not True:
            continue
        current = snapshot_products.get(model)
        fields = fields_by_model.get(model, {})
        slug_field = fields.get("seo_keyword_candidate", {})
        url_field = fields.get("canonical_url", {})
        if current is None:
            raise MigrationApplyError(
                f"Approved slug model is missing from snapshot: {model}"
            )
        if slug_field.get("classification") != "review_required" or url_field.get(
            "classification"
        ) != "review_required":
            raise MigrationApplyError(f"No reviewable slug change exists for {model}.")
        new_slug = str(slug_field.get("candidate_value") or "")
        _validate_slug_uniqueness(model, new_slug, snapshot_products)
        _validate_canonical_slug_change(
            model=model,
            current_url=str(current.get("canonical_url") or ""),
            candidate_url=str(url_field.get("candidate_value") or ""),
            new_slug=new_slug,
        )
        candidates = redirects_by_model.get(model, [])
        _require_redirect_confirmation(
            model=model,
            candidates=candidates,
            confirmation=confirmation,
            target_identity=target_identity,
            migration_run_id=migration_run_id,
            snapshot_id=snapshot_id,
            plan_hash=plan_hash,
            confirmation_not_before=confirmation_not_before,
        )
        _record_external_redirect_preconfirmation(
            rollback=rollback,
            run_path=run_path,
            model=model,
            candidates=candidates,
            migration_run_id=migration_run_id,
            snapshot_id=snapshot_id,
            plan_hash=plan_hash,
            approval_hash=approval_hash,
            target_identity=target_identity,
        )
        _atomic_json(run_path / "rollback_manifest.json", rollback)
        _append_audit(
            audit_path,
            {
                "event": "external_redirect_preconfirmed",
                "migration_run_id": migration_run_id,
                "snapshot_id": snapshot_id,
                "model": model,
                "cleanup_required_if_catalog_write_does_not_complete": True,
            },
        )


def _prepare_approved_images(
    *,
    model: str,
    image_candidates: list[Mapping[str, Any]],
    image_root: Path,
) -> list[dict[str, Any]]:
    root = image_root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise MigrationApplyError(f"Image root not found: {root}")
    operations: list[dict[str, Any]] = []
    for item in sorted(image_candidates, key=lambda value: int(value.get("position") or 0)):
        old_ref = str(item.get("current_path") or "")
        new_ref = str(item.get("candidate_path") or "")
        if not old_ref or not new_ref or old_ref == new_ref:
            continue
        if _is_besco_reference(old_ref) or _is_besco_reference(new_ref):
            raise MigrationApplyError("Description besco#.jpg files must never be renamed.")
        source = _safe_image_path(root, old_ref, model=model)
        target = _safe_image_path(root, new_ref, model=model)
        if os.path.normcase(str(source)) == os.path.normcase(str(target)):
            raise MigrationApplyError(
                f"Image migration source and target resolve to the same file: {old_ref}"
            )
        if not source.exists() or not source.is_file():
            raise MigrationApplyError(f"Approved image source does not exist: {source}")
        source_payload = source.read_bytes()
        if not source_payload:
            raise MigrationApplyError(f"Approved image source is empty: {source}")
        target_payload = (
            source_payload
            if is_jpeg_bytes(source_payload)
            else convert_image_bytes_to_jpg(source_payload)
        )
        if not is_jpeg_bytes(target_payload):
            raise MigrationApplyError(f"Approved image target is not valid JPEG: {new_ref}")
        reviewed_source_hash = str(item.get("source_hash") or "").removeprefix(
            "sha256:"
        )
        if not re.fullmatch(r"[0-9a-f]{64}", reviewed_source_hash):
            raise MigrationApplyError(
                f"Approved image source requires a reviewed SHA-256 hash: {old_ref}"
            )
        actual_source_hash = hashlib.sha256(source_payload).hexdigest()
        if reviewed_source_hash != actual_source_hash:
            raise MigrationApplyError(
                f"Published image source hash changed after review: {old_ref}"
            )
        if target.exists():
            existing_payload = target.read_bytes()
            if hashlib.sha256(existing_payload).digest() != hashlib.sha256(target_payload).digest():
                raise MigrationApplyError(
                    f"Image target already exists with different content: {target}"
                )
        target_hash = hashlib.sha256(target_payload).hexdigest()
        operations.append(
            {
                "model": model,
                "position": int(item.get("position") or 0),
                "role": item.get("role"),
                "old_path": old_ref,
                "new_path": new_ref,
                "source_file": str(source),
                "target_file": str(target),
                "source_hash": actual_source_hash,
                "target_hash": target_hash,
                "original_retained": source.is_file(),
                "besco_preserved": True,
                "copy_required": not target.exists(),
            }
        )
    if not operations:
        raise MigrationApplyError(f"Approved image change for {model} has no copy operations.")
    return operations


def _copy_prepared_images(operations: list[dict[str, Any]]) -> None:
    """Copy already-reviewed images and recheck bytes immediately before write."""

    for operation in operations:
        source = Path(str(operation.get("source_file") or ""))
        target = Path(str(operation.get("target_file") or ""))
        if not source.is_file():
            raise MigrationApplyError(f"Approved image source no longer exists: {source}")
        source_payload = source.read_bytes()
        source_hash = hashlib.sha256(source_payload).hexdigest()
        if source_hash != operation.get("source_hash"):
            raise MigrationApplyError(
                f"Approved image source changed after preflight: {source}"
            )
        target_payload = (
            source_payload
            if is_jpeg_bytes(source_payload)
            else convert_image_bytes_to_jpg(source_payload)
        )
        if hashlib.sha256(target_payload).hexdigest() != operation.get("target_hash"):
            raise MigrationApplyError(
                f"Approved image conversion changed after preflight: {target}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != operation.get(
                "target_hash"
            ):
                raise MigrationApplyError(
                    f"Image target changed after preflight: {target}"
                )
        else:
            _atomic_bytes(target, target_payload)
        if not source.is_file():
            raise MigrationApplyError("Original image was not retained after copy.")
        if hashlib.sha256(target.read_bytes()).hexdigest() != operation.get("target_hash"):
            raise MigrationApplyError(f"Copied image hash verification failed: {target}")


def _safe_image_path(root: Path, reference: str, *, model: str) -> Path:
    normalized = reference.replace("\\", "/").lstrip("/")
    if normalized.startswith("image/"):
        normalized = normalized[len("image/") :]
    parts = [part for part in normalized.split("/") if part]
    if len(parts) != 4 or parts[:3] != ["catalog", "01_main", model]:
        raise MigrationApplyError(f"Unsafe or mismatched image reference: {reference}")
    if any(part in {".", ".."} for part in parts) or not parts[-1].lower().endswith(".jpg"):
        raise MigrationApplyError(f"Unsafe image reference: {reference}")
    path = (root / Path(*parts)).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise MigrationApplyError(f"Image path escapes configured root: {reference}") from exc
    return path


def _apply_image_references(
    *,
    patch: dict[str, Any],
    current: Mapping[str, Any],
    operations: list[Mapping[str, Any]],
) -> None:
    ordered = sorted(operations, key=lambda item: int(item.get("position") or 0))
    all_current = [
        str(current.get("main_image") or current.get("image") or ""),
        *[str(value) for value in current.get("additional_images", []) or []],
    ]
    replacements = {
        str(item.get("old_path") or ""): str(item.get("new_path") or "")
        for item in ordered
    }
    updated = [replacements.get(path, path) for path in all_current]
    if not updated or not updated[0]:
        raise MigrationApplyError("Image reference update would leave the main image empty.")
    patch["image"] = updated[0]
    patch["additional_image"] = ":::".join(value for value in updated[1:] if value)
    description = str(patch.get("description", current.get("description") or ""))
    besco_before = _besco_references(str(current.get("description") or ""))
    for old, new in replacements.items():
        description = description.replace(old, new)
        description = description.replace(f"/image/{old}", f"/image/{new}")
    besco_after = _besco_references(description)
    if besco_before != besco_after:
        raise MigrationApplyError("Image migration altered a besco description reference.")
    if any(old in description for old in replacements if old):
        raise MigrationApplyError("Not every HTML reference was updated for image migration.")
    if description != str(current.get("description") or "") or "description" in patch:
        patch["description"] = description


def _besco_references(description: str) -> list[str]:
    return sorted(
        re.findall(
            r"(?:/image/)?catalog/01_bescos/[0-9]{6}/besco[1-9][0-9]*\.jpe?g",
            str(description or ""),
            re.I,
        )
    )


def _require_besco_references_preserved(*, before: str, after: str) -> None:
    if _besco_references(before) != _besco_references(after):
        raise MigrationApplyError(
            "Approved description would add, remove, or rename a besco#.jpg reference."
        )


def _selected_rollback_operations(
    *, plan: Mapping[str, Any], approvals: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    operations = plan.get("rollback_manifest", {}).get("operations", [])
    result: list[dict[str, Any]] = []
    for raw in operations:
        if not isinstance(raw, Mapping):
            continue
        model = str(raw.get("model") or "")
        approval = approvals.get(model)
        if approval is None:
            continue
        field = str(raw.get("field") or "")
        selected = field in set(approval.get("approved_fields", []))
        selected = selected or (
            field in {"seo_keyword_candidate", "canonical_url"}
            and approval.get("approved_slug_change") is True
        )
        selected = selected or (
            field == "gallery_image_candidate"
            and approval.get("approved_image_path_change") is True
        )
        if selected:
            result.append(dict(raw))
    return result


def _mark_rollback_applied(
    rollback: dict[str, Any], applied_keys: set[tuple[str, str]]
) -> None:
    for operation in rollback.get("operations", []):
        key = (str(operation.get("model")), str(operation.get("field")))
        if key in applied_keys:
            operation["applied"] = True
            operation["applied_at"] = _utcnow()
            operation["apply_confirmation"] = "confirmed"


def _mark_model_write_attempted(
    *,
    rollback: dict[str, Any],
    selected_operations: list[Mapping[str, Any]],
    model: str,
) -> None:
    selected_keys = {
        (str(item.get("model") or ""), str(item.get("field") or ""))
        for item in selected_operations
        if item.get("model") == model
    }
    attempted_at = _utcnow()
    for operation in rollback.get("operations", []):
        key = (str(operation.get("model") or ""), str(operation.get("field") or ""))
        if key in selected_keys:
            operation["write_attempted"] = True
            operation["write_attempted_at"] = attempted_at
            operation["apply_confirmation"] = "state_unknown"


def _materialize_rollback_expectations(
    *,
    rollback: dict[str, Any],
    selected_operations: list[Mapping[str, Any]],
    model: str,
    patch: Mapping[str, Any],
    current: Mapping[str, Any],
) -> None:
    selected_keys = {
        (str(item.get("model") or ""), str(item.get("field") or ""))
        for item in selected_operations
        if item.get("model") == model
    }
    for operation in rollback.get("operations", []):
        key = (str(operation.get("model") or ""), str(operation.get("field") or ""))
        if key not in selected_keys:
            continue
        logical = key[1]
        effective: Any = operation.get("expected_applied_value")
        if logical == "filter_values":
            expected_filters = operation.get("expected_applied_value")
            if isinstance(expected_filters, Mapping):
                effective = {
                    str(header): patch.get(str(header))
                    for header in expected_filters
                    if str(header) in patch
                }
        elif logical == "gallery_image_candidate":
            main = str(patch.get("image") or current.get("main_image") or "")
            additional_value = patch.get("additional_image")
            additional = (
                [item for item in str(additional_value or "").split(":::") if item]
                if additional_value is not None
                else [str(item) for item in current.get("additional_images", []) or []]
            )
            effective = [main, *additional]
            operation["effective_expected_applied_description"] = str(
                patch.get("description", current.get("description") or "")
            )
        elif logical == "seo_keyword_candidate":
            effective = patch.get("seo_keyword")
        elif logical == "canonical_url":
            effective = patch.get("product_url")
        else:
            csv_field = CSV_FIELD_MAP.get(logical)
            if csv_field in patch:
                effective = patch[csv_field]
                if logical == "related_products" and isinstance(
                    operation.get("expected_applied_value"), list
                ):
                    effective = [
                        item for item in str(effective or "").split(",") if item
                    ]
        operation["effective_expected_applied_value"] = effective


def _verify_rollback_manifest_integrity(rollback: Mapping[str, Any]) -> None:
    operations = rollback.get("operations")
    if not isinstance(operations, list):
        raise MigrationApplyError("Rollback operations are missing or invalid.")
    mutable_keys = {
        "write_attempted",
        "write_attempted_at",
        "apply_confirmation",
        "applied",
        "applied_at",
        "rolled_back",
        "rolled_back_at",
        "rollback_resolution",
        "effective_expected_applied_value",
        "effective_expected_applied_description",
        "external_redirect_preconfirmed",
        "external_redirect_preconfirmed_at",
        "external_redirect_cleanup_verified",
        "external_redirect_cleanup_verified_at",
    }
    immutable = [
        _immutable_rollback_operation(operation, mutable_keys=mutable_keys)
        for operation in operations
        if isinstance(operation, Mapping)
    ]
    if len(immutable) != len(operations) or _content_hash(immutable) != str(
        rollback.get("operations_hash") or ""
    ):
        raise MigrationApplyError(
            "Rollback manifest operation hash no longer matches; refusing write."
        )
    immutable_header_keys = (
        "schema_version",
        "snapshot_id",
        "migration_run_id",
        "target_identity",
        "created_at",
        "created_before_apply",
        "complete",
        "price_stock_status_excluded",
        "original_files_must_be_retained",
        "operations_hash",
    )
    if any(key not in rollback for key in immutable_header_keys) or _content_hash(
        {key: rollback[key] for key in immutable_header_keys}
    ) != str(rollback.get("manifest_hash") or ""):
        raise MigrationApplyError(
            "Rollback manifest immutable header hash no longer matches; refusing write."
        )


def _immutable_rollback_operation(
    operation: Mapping[str, Any], *, mutable_keys: set[str] | None = None
) -> dict[str, Any]:
    ignored = mutable_keys or {
        "write_attempted",
        "write_attempted_at",
        "apply_confirmation",
        "applied",
        "applied_at",
        "rolled_back",
        "rolled_back_at",
        "rollback_resolution",
        "effective_expected_applied_value",
        "effective_expected_applied_description",
        "external_redirect_preconfirmed",
        "external_redirect_preconfirmed_at",
        "external_redirect_cleanup_verified",
        "external_redirect_cleanup_verified_at",
    }
    return {key: value for key, value in operation.items() if key not in ignored}


def _bind_rollback_operations_to_apply_evidence(
    *,
    run_path: Path,
    apply_claim: Mapping[str, Any],
    operations: Mapping[str, list[dict[str, Any]]],
    external_cleanup_models: set[str],
) -> None:
    sealed_plan = _read_json(run_path / "apply.plan.json")
    try:
        sealed_plan = verify_migration_plan(sealed_plan)
    except MigrationPlanError as exc:
        raise MigrationApplyError("Sealed apply plan is invalid during rollback.") from exc
    if sealed_plan.get("plan_hash") != apply_claim.get("plan_hash"):
        raise MigrationApplyError("Sealed apply plan does not match the apply claim.")
    sealed_approval = _read_json(run_path / "apply.approval.json")
    if _content_hash(sealed_approval) != apply_claim.get("approval_hash"):
        raise MigrationApplyError("Sealed approval does not match the apply claim.")
    try:
        sealed_approval = validate_approval_manifest(
            sealed_approval,
            snapshot_id=str(apply_claim.get("snapshot_id") or ""),
            migration_run_id=str(apply_claim.get("migration_run_id") or ""),
            allowed_fields={*CSV_FIELD_MAP, "filter_values"},
        )
    except ApprovalValidationError as exc:
        raise MigrationApplyError("Sealed apply approval is invalid.") from exc

    approvals = _approval_products(sealed_approval)
    selected = _selected_rollback_operations(plan=sealed_plan, approvals=approvals)
    selected_keys = {
        (str(item.get("model") or ""), str(item.get("field") or ""))
        for item in selected
    }
    planned_operations = {
        (str(item.get("model") or ""), str(item.get("field") or "")): item
        for item in sealed_plan.get("rollback_manifest", {}).get("operations", [])
        if isinstance(item, Mapping)
    }
    scopes = {
        str(item.get("model") or ""): _normalize_authorization_scope(item)
        for item in apply_claim.get("scopes", [])
        if isinstance(item, Mapping)
    }
    started_models = _audited_write_started_models(run_path / "audit.jsonl")
    claim_path = run_path / "apply.claim.json"

    for model, model_operations in operations.items():
        if model not in started_models:
            if model not in external_cleanup_models or any(
                str(item.get("field") or "") != "seo_keyword_candidate"
                for item in model_operations
            ):
                raise MigrationApplyError(
                    f"Rollback state for {model} has no durable apply write-start audit."
                )
            _bind_external_redirect_cleanup_only(
                run_path=run_path,
                sealed_plan=sealed_plan,
                operations={model: model_operations},
                target_identity=str(apply_claim.get("target_identity") or ""),
            )
            continue
        scope = scopes.get(model)
        if scope is None:
            raise MigrationApplyError(
                f"Rollback model {model} is outside the claimed apply scope."
            )
        csv_path = run_path / "apply" / "patches" / f"{model}.csv"
        if not csv_path.is_file() or _sha256_file(csv_path) != scope["csv_sha256"]:
            raise MigrationApplyError(
                f"Claimed apply patch is missing or changed for rollback: {model}"
            )
        headers, row = _read_exact_partial_patch(csv_path, model=model)
        if headers != scope["headers"]:
            raise MigrationApplyError(
                f"Claimed apply patch headers changed before rollback: {model}"
            )
        stored_authorization = _read_json(
            run_path / "apply" / "authorizations" / f"{model}.json"
        )
        _verify_stored_adapter_authorization(
            stored_authorization,
            operation="apply",
            migration_run_id=str(apply_claim.get("migration_run_id") or ""),
            snapshot_id=str(apply_claim.get("snapshot_id") or ""),
            approval_hash=str(apply_claim.get("approval_hash") or ""),
            plan_hash=str(apply_claim.get("plan_hash") or ""),
            target_identity=str(apply_claim.get("target_identity") or ""),
            claim_path=claim_path,
            scope=scope,
        )

        for operation in model_operations:
            key = (model, str(operation.get("field") or ""))
            if key not in selected_keys:
                raise MigrationApplyError(
                    f"Rollback operation is outside the approved apply scope: {key}"
                )
            planned = planned_operations.get(key)
            if planned is None or _canonical_json(
                _immutable_rollback_operation(operation)
            ) != _canonical_json(_immutable_rollback_operation(planned)):
                raise MigrationApplyError(
                    f"Rollback operation no longer matches the sealed plan: {key}"
                )
            verified, verified_description = _expected_from_claimed_patch(
                operation=operation,
                row=row,
                headers=headers,
                scope=scope,
            )
            stored_effective = operation.get("effective_expected_applied_value")
            if _canonical_json(stored_effective) != _canonical_json(verified):
                raise MigrationApplyError(
                    f"Rollback expected-state checkpoint changed for {key}."
                )
            operation["_verified_expected_applied_value"] = verified
            if verified_description is not None:
                if _canonical_json(
                    operation.get("effective_expected_applied_description")
                ) != _canonical_json(verified_description):
                    raise MigrationApplyError(
                        f"Rollback description checkpoint changed for {key}."
                    )
                operation["_verified_expected_applied_description"] = (
                    verified_description
                )


def _bind_external_redirect_cleanup_only(
    *,
    run_path: Path,
    sealed_plan: Mapping[str, Any],
    operations: Mapping[str, list[dict[str, Any]]],
    target_identity: str,
) -> None:
    cleanup = _read_json(run_path / "redirect_cleanup_required.json")
    expected_keys = {
        "schema_version",
        "migration_run_id",
        "snapshot_id",
        "plan_hash",
        "approval_hash",
        "target_identity",
        "created_at",
        "status",
        "redirects",
        "content_hash",
    }
    if not isinstance(cleanup, Mapping) or set(cleanup) != expected_keys:
        raise MigrationApplyError("Redirect cleanup evidence has an invalid exact shape.")
    material = dict(cleanup)
    stored_hash = str(material.pop("content_hash") or "")
    if _content_hash(material) != stored_hash:
        raise MigrationApplyError("Redirect cleanup evidence content hash changed.")
    if (
        cleanup.get("schema_version") != "1.0"
        or cleanup.get("migration_run_id") != sealed_plan.get("migration_run_id")
        or cleanup.get("snapshot_id") != sealed_plan.get("snapshot_id")
        or cleanup.get("plan_hash") != sealed_plan.get("plan_hash")
        or cleanup.get("target_identity") != target_identity
    ):
        raise MigrationApplyError("Redirect cleanup evidence binding does not match.")
    sealed_approval = _read_json(run_path / "apply.approval.json")
    if _content_hash(sealed_approval) != cleanup.get("approval_hash"):
        raise MigrationApplyError("Redirect cleanup approval hash does not match.")
    approvals = _approval_products(sealed_approval)
    selected_keys = {
        (str(item.get("model") or ""), str(item.get("field") or ""))
        for item in _selected_rollback_operations(
            plan=sealed_plan, approvals=approvals
        )
    }
    planned = {
        (str(item.get("model") or ""), str(item.get("field") or "")): item
        for item in sealed_plan.get("rollback_manifest", {}).get("operations", [])
        if isinstance(item, Mapping)
    }
    cleanup_entries = {
        (
            str(item.get("model") or ""),
            _normalize_route_path(str(item.get("old_path") or "")),
            _normalize_route_path(str(item.get("new_path") or "")),
        )
        for item in cleanup.get("redirects", [])
        if isinstance(item, Mapping)
    }
    for model, model_operations in operations.items():
        for operation in model_operations:
            key = (model, str(operation.get("field") or ""))
            if (
                key[1] != "seo_keyword_candidate"
                or key not in selected_keys
                or operation.get("external_redirect_preconfirmed") is not True
                or operation.get("write_attempted") is True
                or operation.get("applied") is True
            ):
                raise MigrationApplyError(
                    f"Cleanup-only rollback contains a catalog write operation: {key}"
                )
            planned_operation = planned.get(key)
            if planned_operation is None or _canonical_json(
                _immutable_rollback_operation(operation)
            ) != _canonical_json(_immutable_rollback_operation(planned_operation)):
                raise MigrationApplyError(
                    f"Cleanup-only rollback operation differs from the sealed plan: {key}"
                )
            old_path = _normalize_route_path(
                f"/{str(operation.get('restore_value') or '')}"
            )
            new_path = _normalize_route_path(
                f"/{str(operation.get('expected_applied_value') or '')}"
            )
            if (model, old_path, new_path) not in cleanup_entries:
                raise MigrationApplyError(
                    f"Redirect cleanup entry is missing for {model}."
                )
            operation["_verified_expected_applied_value"] = operation.get(
                "expected_applied_value"
            )


def _read_exact_partial_patch(path: Path, *, model: str) -> tuple[list[str], dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            headers = list(reader.fieldnames or [])
    except (OSError, UnicodeError, csv.Error) as exc:
        raise MigrationApplyError(f"Could not read claimed apply patch: {model}") from exc
    if (
        len(rows) != 1
        or rows[0].get("model") != model
        or not headers
        or len(headers) != len(set(headers))
    ):
        raise MigrationApplyError(f"Claimed apply patch shape is invalid: {model}")
    return headers, {str(key): str(value or "") for key, value in rows[0].items()}


def _expected_from_claimed_patch(
    *,
    operation: Mapping[str, Any],
    row: Mapping[str, str],
    headers: list[str],
    scope: Mapping[str, Any],
) -> tuple[Any, str | None]:
    logical = str(operation.get("field") or "")
    header_set = set(headers)
    if logical == "filter_values":
        filter_headers = sorted(header for header in headers if header.startswith("filter_group:"))
        if not filter_headers:
            raise MigrationApplyError("Claimed filter rollback has no filter columns.")
        return ({header: row.get(header, "") for header in filter_headers}, None)
    if logical == "gallery_image_candidate":
        if not {"image", "additional_image"} <= header_set or scope.get(
            "image_operations_hash"
        ) == _content_hash([]):
            raise MigrationApplyError("Claimed image rollback has no image write scope.")
        gallery = [
            str(row.get("image") or ""),
            *[
                item
                for item in str(row.get("additional_image") or "").split(":::")
                if item
            ],
        ]
        description = (
            str(row.get("description") or "")
            if "description" in header_set
            else str(operation.get("expected_applied_description") or "")
        )
        return gallery, description
    if logical == "seo_keyword_candidate":
        required_header = "seo_keyword"
    elif logical == "canonical_url":
        required_header = "product_url"
    else:
        required_header = CSV_FIELD_MAP.get(logical, "")
    if not required_header or required_header not in header_set:
        raise MigrationApplyError(
            f"Rollback field {logical} is not present in the claimed apply patch."
        )
    value: Any = row.get(required_header, "")
    if logical == "related_products" and isinstance(
        operation.get("expected_applied_value"), list
    ):
        value = [item for item in str(value).split(",") if item]
    return value, None


def _audited_write_started_models(path: Path) -> set[str]:
    return _audited_event_models(path, event_name="product_write_started")


def _audited_event_models(path: Path, *, event_name: str) -> set[str]:
    if not path.is_file():
        raise MigrationApplyError("Apply audit log is missing before rollback.")
    models: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise MigrationApplyError("Apply audit log cannot be read before rollback.") from exc
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MigrationApplyError("Apply audit log contains invalid JSON.") from exc
        if isinstance(event, Mapping) and event.get("event") == event_name:
            model = str(event.get("model") or "")
            if re.fullmatch(r"\d{6}", model):
                models.add(model)
    return models


def _derive_rollback_operations(
    *,
    run_path: Path,
    rollback: Mapping[str, Any],
    sealed_plan: Mapping[str, Any],
    apply_claim: Mapping[str, Any] | None,
    target_identity: str,
) -> tuple[list[dict[str, Any]], set[str]]:
    """Derive rollback scope from sealed review inputs and durable audit events.

    Operational flags in ``rollback_manifest.json`` remain useful checkpoints,
    but they are never trusted to omit a reviewed operation.  This also makes
    an explicit rollback safe after a hard crash left ``apply_result`` running.
    """

    sealed_approval = _read_json(run_path / "apply.approval.json")
    try:
        sealed_approval = validate_approval_manifest(
            sealed_approval,
            snapshot_id=str(sealed_plan.get("snapshot_id") or ""),
            migration_run_id=str(sealed_plan.get("migration_run_id") or ""),
            allowed_fields={*CSV_FIELD_MAP, "filter_values"},
        )
    except ApprovalValidationError as exc:
        raise MigrationApplyError("Sealed apply approval is invalid during rollback.") from exc
    if apply_claim is not None and _content_hash(sealed_approval) != str(
        apply_claim.get("approval_hash") or ""
    ):
        raise MigrationApplyError("Sealed approval does not match the apply claim.")

    approvals = _approval_products(sealed_approval)
    selected = _selected_rollback_operations(plan=sealed_plan, approvals=approvals)
    planned = {
        (str(item.get("model") or ""), str(item.get("field") or "")): item
        for item in selected
    }
    manifest = {
        (str(item.get("model") or ""), str(item.get("field") or "")): item
        for item in rollback.get("operations", [])
        if isinstance(item, Mapping)
    }
    if set(planned) - set(manifest):
        raise MigrationApplyError(
            "Rollback manifest is missing reviewed operations from the sealed plan."
        )
    for key, operation in manifest.items():
        if key not in planned and any(
            operation.get(flag)
            for flag in (
                "write_attempted",
                "applied",
                "rolled_back",
                "external_redirect_preconfirmed",
            )
        ):
            raise MigrationApplyError(
                f"Rollback operation is outside the approved apply scope: {key}"
            )

    audit_path = run_path / "audit.jsonl"
    started_models = _audited_write_started_models(audit_path)
    rolled_back_models = _audited_event_models(
        audit_path, event_name="product_rollback_confirmed"
    )
    external_cleanup_models = _redirect_cleanup_models(
        run_path=run_path,
        sealed_plan=sealed_plan,
        sealed_approval=sealed_approval,
        target_identity=target_identity,
    )
    if apply_claim is None and started_models:
        raise MigrationApplyError(
            "Apply write-start audit exists without its immutable apply claim."
        )

    result: list[dict[str, Any]] = []
    for key in sorted(planned):
        model, field = key
        if model in rolled_back_models:
            continue
        started = model in started_models
        external = model in external_cleanup_models and field == "seo_keyword_candidate"
        if not started and not external:
            continue
        operation = dict(manifest[key])
        if _canonical_json(_immutable_rollback_operation(operation)) != _canonical_json(
            _immutable_rollback_operation(planned[key])
        ):
            raise MigrationApplyError(
                f"Rollback operation no longer matches the sealed plan: {key}"
            )
        operation["write_attempted"] = started
        operation["rolled_back"] = False
        operation["external_redirect_preconfirmed"] = external
        result.append(operation)
    return result, external_cleanup_models


def _redirect_cleanup_models(
    *,
    run_path: Path,
    sealed_plan: Mapping[str, Any],
    sealed_approval: Mapping[str, Any],
    target_identity: str,
) -> set[str]:
    path = run_path / "redirect_cleanup_required.json"
    if not path.is_file():
        return set()
    cleanup = _read_json(path)
    base_keys = {
        "schema_version",
        "migration_run_id",
        "snapshot_id",
        "plan_hash",
        "approval_hash",
        "target_identity",
        "created_at",
        "status",
        "redirects",
        "content_hash",
    }
    if frozenset(cleanup) not in {
        frozenset(base_keys),
        frozenset({*base_keys, "cleanup_verified_at"}),
    }:
        raise MigrationApplyError("Redirect cleanup evidence has an invalid exact shape.")
    material = {key: cleanup[key] for key in base_keys if key != "content_hash"}
    if cleanup.get("status") == "external_forward_redirect_cleanup_verified":
        material["status"] = (
            "external_forward_redirect_active_cleanup_required_on_failed_apply"
        )
    if _content_hash(material) != str(cleanup.get("content_hash") or ""):
        raise MigrationApplyError("Redirect cleanup evidence content hash changed.")
    if (
        cleanup.get("schema_version") != "1.0"
        or cleanup.get("migration_run_id") != sealed_plan.get("migration_run_id")
        or cleanup.get("snapshot_id") != sealed_plan.get("snapshot_id")
        or cleanup.get("plan_hash") != sealed_plan.get("plan_hash")
        or cleanup.get("approval_hash") != _content_hash(sealed_approval)
        or cleanup.get("target_identity") != target_identity
    ):
        raise MigrationApplyError("Redirect cleanup evidence binding changed.")
    redirects = cleanup.get("redirects")
    if not isinstance(redirects, list) or not redirects:
        raise MigrationApplyError("Redirect cleanup evidence has no redirect entries.")
    expected_entry_keys = {
        "model",
        "old_path",
        "new_path",
        "status_code",
        "required_action",
    }
    models: set[str] = set()
    for item in redirects:
        if (
            not isinstance(item, Mapping)
            or set(item) != expected_entry_keys
            or not re.fullmatch(r"\d{6}", str(item.get("model") or ""))
            or item.get("status_code") != 301
        ):
            raise MigrationApplyError("Redirect cleanup entry is invalid.")
        models.add(str(item["model"]))
    return models


def _verify_rollback_current_state(
    operations: Mapping[str, list[Mapping[str, Any]]],
    current_products: Mapping[str, Mapping[str, Any]],
) -> None:
    mismatches: list[str] = []
    for model, items in operations.items():
        current = current_products.get(model)
        if current is None:
            mismatches.append(f"{model}:missing")
            continue
        has_description_operation = any(
            str(item.get("field") or "") == "description" for item in items
        )
        for item in items:
            field = str(item.get("field") or "")
            observed = _logical_current_value(current, field)
            if "_verified_expected_applied_value" not in item:
                mismatches.append(f"{model}:{field}:unbound_expected_state")
                continue
            expected = item.get("_verified_expected_applied_value")
            restore = item.get("restore_value")
            if _canonical_json(observed) == _canonical_json(expected):
                item["_rollback_action"] = "restore"
            elif (
                item.get("write_attempted")
                or item.get("external_redirect_preconfirmed")
            ) and _canonical_json(observed) == _canonical_json(restore):
                item["_rollback_action"] = "noop"
            else:
                mismatches.append(f"{model}:{field}")
            if (
                field == "gallery_image_candidate"
                and item.get("_rollback_action") == "restore"
                and item.get("_verified_expected_applied_description") is not None
            ):
                if _canonical_json(current.get("description")) != _canonical_json(
                    item.get("_verified_expected_applied_description")
                ):
                    mismatches.append(f"{model}:description_image_references")
            if (
                field == "gallery_image_candidate"
                and item.get("_rollback_action") == "noop"
                and not has_description_operation
                and item.get("restore_description") is not None
                and _canonical_json(current.get("description"))
                != _canonical_json(item.get("restore_description"))
            ):
                mismatches.append(f"{model}:description_image_references")
    if mismatches:
        raise MigrationApplyError(
            "Rollback current-state verification failed; refusing overwrite: "
            + ", ".join(sorted(mismatches))
        )


def _artifact_rollback_entries(
    operations: list[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    return [
        artifact
        for operation in operations
        for artifact in operation.get("artifact_operations", [])
        if isinstance(artifact, Mapping)
    ]


def _required_coupled_artifact_bundle(
    *, rollback: Mapping[str, Any], model: str, field: str
) -> dict[str, Any]:
    operation = next(
        (
            item
            for item in rollback.get("operations", [])
            if isinstance(item, Mapping)
            and item.get("model") == model
            and item.get("field") == field
        ),
        None,
    )
    entries = (
        operation.get("artifact_operations", [])
        if isinstance(operation, Mapping)
        else []
    )
    result = {
        str(item.get("name") or ""): item.get("expected_applied_value")
        for item in entries
        if isinstance(item, Mapping)
    }
    required = {"structured_data_manifest", "product_feed_manifest"}
    if set(result) != required or any(
        not isinstance(result[name], Mapping) for name in required
    ):
        raise MigrationApplyError(
            f"{field} for {model} requires complete coupled structured-data "
            "and product-feed artifacts."
        )
    return result


def _prepare_artifact_rollback(
    run_path: Path, model: str, operations: list[Mapping[str, Any]]
) -> None:
    for artifact in _artifact_rollback_entries(operations):
        name = str(artifact.get("name") or "")
        if name not in {"structured_data_manifest", "product_feed_manifest"}:
            raise MigrationApplyError(f"Unsafe rollback artifact name for {model}: {name}")
        applied_path = run_path / "apply" / "artifacts" / model / f"{name}.json"
        if not applied_path.is_file():
            raise MigrationApplyError(
                f"Applied migration artifact is missing before rollback: {model}/{name}"
            )
        observed = _read_json(applied_path)
        expected = artifact.get("expected_applied_value")
        restore = artifact.get("restore_value")
        if _canonical_json(observed) not in {
            _canonical_json(expected),
            _canonical_json(restore),
        }:
            raise MigrationApplyError(
                f"Applied migration artifact changed after apply: {model}/{name}"
            )
        _atomic_json(
            run_path / "rollback" / "artifacts" / model / f"{name}.json",
            restore,
        )


def _restore_artifact_bundle(
    run_path: Path, model: str, operations: list[Mapping[str, Any]]
) -> None:
    _prepare_artifact_rollback(run_path, model, operations)
    for artifact in _artifact_rollback_entries(operations):
        name = str(artifact.get("name") or "")
        applied_path = run_path / "apply" / "artifacts" / model / f"{name}.json"
        restore = artifact.get("restore_value")
        if _canonical_json(_read_json(applied_path)) != _canonical_json(restore):
            _atomic_json(applied_path, restore)
        if _canonical_json(_read_json(applied_path)) != _canonical_json(
            restore
        ):
            raise MigrationApplyError(
                f"Rollback artifact verification failed: {model}/{name}"
            )


def _validate_reverse_redirects(
    operations: Mapping[str, list[Mapping[str, Any]]],
    confirmation: Mapping[str, Any] | None,
    *,
    target_identity: str,
    migration_run_id: str,
    snapshot_id: str,
    plan_hash: str,
    confirmation_not_before: str,
) -> None:
    for model, items in operations.items():
        slug_operation = next(
            (
                item
                for item in items
                if item.get("field") == "seo_keyword_candidate"
            ),
            None,
        )
        if slug_operation is None:
            continue
        if not isinstance(confirmation, Mapping):
            raise MigrationApplyError(
                "Slug rollback requires externally applied and verified reverse redirects."
            )
        _validate_redirect_confirmation_document(
            confirmation,
            expected_target_identity=target_identity,
            expected_migration_run_id=migration_run_id,
            expected_snapshot_id=snapshot_id,
            expected_plan_hash=plan_hash,
            not_before=confirmation_not_before,
        )
        new_slug = str(slug_operation.get("expected_applied_value") or "")
        old_slug = str(slug_operation.get("restore_value") or "")
        removed = next(
            (
                item
                for item in confirmation.get("removed_redirects", [])
                if isinstance(item, Mapping)
                and item.get("model") == model
                and _normalize_route_path(str(item.get("old_path") or ""))
                == _normalize_route_path(f"/{old_slug}")
                and _normalize_route_path(str(item.get("new_path") or ""))
                == _normalize_route_path(f"/{new_slug}")
                and item.get("status_code") == 301
                and item.get("removed") is True
                and item.get("verified") is True
            ),
            None,
        )
        if removed is None:
            raise MigrationApplyError(
                f"Forward redirect removal is not confirmed for slug rollback: {model}"
            )
        if slug_operation.get("_rollback_action") == "noop":
            # The catalog never left the old slug, but apply required the
            # forward redirect to be live before the uncertain write. Closing
            # that external side effect is still mandatory.
            continue
        confirmed = confirmation.get("redirects", [])
        match = next(
            (
                item
                for item in confirmed
                if isinstance(item, Mapping)
                and item.get("model") == model
                and _normalize_route_path(str(item.get("old_path") or ""))
                == _normalize_route_path(f"/{new_slug}")
                and _normalize_route_path(str(item.get("new_path") or ""))
                == _normalize_route_path(f"/{old_slug}")
                and item.get("status_code") == 301
            ),
            None,
        )
        if not match or not all(
            match.get(key) is True for key in ("approved", "applied", "verified")
        ):
            raise MigrationApplyError(
                f"Reverse redirect for slug rollback is not applied and verified: {model}"
            )
        if _normalize_route_path(f"/{old_slug}") in _redirect_namespace_paths(
            confirmation
        ):
            raise MigrationApplyError(
                f"Restored slug is not globally unique before rollback: {model}"
            )


def _validate_redirect_confirmation_document(
    confirmation: Mapping[str, Any],
    *,
    expected_target_identity: str,
    expected_migration_run_id: str,
    expected_snapshot_id: str,
    expected_plan_hash: str,
    not_before: str,
) -> None:
    expected_keys = {
        "schema_version",
        "environment",
        "target_identity",
        "migration_run_id",
        "snapshot_id",
        "plan_hash",
        "responsible_system",
        "confirmed_by",
        "confirmed_at",
        "redirects",
        "removed_redirects",
        "seo_url_namespace",
    }
    if set(confirmation) != expected_keys:
        raise MigrationApplyError("Redirect confirmation has an invalid exact shape.")
    if confirmation.get("schema_version") != "1.0" or confirmation.get(
        "environment"
    ) != "production":
        raise MigrationApplyError("Redirect confirmation schema/environment is invalid.")
    if (
        not expected_target_identity
        or confirmation.get("target_identity") != expected_target_identity
    ):
        raise MigrationApplyError(
            "Redirect confirmation target identity does not match the migration target."
        )
    if (
        confirmation.get("migration_run_id") != expected_migration_run_id
        or confirmation.get("snapshot_id") != expected_snapshot_id
        or confirmation.get("plan_hash") != expected_plan_hash
    ):
        raise MigrationApplyError(
            "Redirect confirmation is not bound to this migration run/snapshot/plan."
        )
    if not str(confirmation.get("responsible_system") or "").strip() or not str(
        confirmation.get("confirmed_by") or ""
    ).strip():
        raise MigrationApplyError("Redirect confirmation owner is missing.")
    parsed = _require_rfc3339_timestamp(
        confirmation.get("confirmed_at"), label="redirect confirmation"
    )
    lower_bound = _require_rfc3339_timestamp(
        not_before, label="redirect confirmation lower-bound"
    )
    now = datetime.now(timezone.utc)
    if (
        parsed < lower_bound
        or parsed > now
        or (now - parsed).total_seconds() > REDIRECT_EVIDENCE_MAX_AGE_SECONDS
    ):
        raise MigrationApplyError(
            "Redirect confirmation is stale, predates the run gate, or is future-dated."
        )
    redirects = confirmation.get("redirects")
    if not isinstance(redirects, list):
        raise MigrationApplyError("Redirect confirmation redirects must be an array.")
    entry_keys = {
        "old_path",
        "new_path",
        "status_code",
        "model",
        "approved",
        "applied",
        "verified",
    }
    if any(not isinstance(item, Mapping) or set(item) != entry_keys for item in redirects):
        raise MigrationApplyError("Redirect confirmation entry has an invalid exact shape.")
    for item in redirects:
        old_path = _normalize_route_path(str(item.get("old_path") or ""))
        new_path = _normalize_route_path(str(item.get("new_path") or ""))
        if (
            old_path == new_path
            or item.get("status_code") != 301
            or not re.fullmatch(r"\d{6}", str(item.get("model") or ""))
            or any(
                item.get(key) is not True
                for key in ("approved", "applied", "verified")
            )
        ):
            raise MigrationApplyError("Redirect confirmation entry is invalid.")
    removed_redirects = confirmation.get("removed_redirects")
    removed_keys = {
        "old_path",
        "new_path",
        "status_code",
        "model",
        "removed",
        "verified",
    }
    if not isinstance(removed_redirects, list) or any(
        not isinstance(item, Mapping)
        or set(item) != removed_keys
        or item.get("status_code") != 301
        or item.get("removed") is not True
        or item.get("verified") is not True
        for item in removed_redirects
    ):
        raise MigrationApplyError(
            "Removed redirect confirmation has an invalid exact shape."
        )
    namespace = confirmation.get("seo_url_namespace")
    if not isinstance(namespace, Mapping) or namespace.get(
        "target_identity"
    ) != expected_target_identity:
        raise MigrationApplyError(
            "SEO URL namespace target identity does not match the migration target."
        )
    if (
        namespace.get("migration_run_id") != expected_migration_run_id
        or namespace.get("snapshot_id") != expected_snapshot_id
        or namespace.get("plan_hash") != expected_plan_hash
    ):
        raise MigrationApplyError(
            "SEO URL namespace is not bound to this migration run/snapshot/plan."
        )
    namespace_captured = _require_rfc3339_timestamp(
        namespace.get("captured_at"), label="SEO URL namespace"
    )
    if (
        namespace_captured < lower_bound
        or namespace_captured > parsed
        or namespace_captured > now
        or (now - namespace_captured).total_seconds()
        > REDIRECT_EVIDENCE_MAX_AGE_SECONDS
    ):
        raise MigrationApplyError(
            "SEO URL namespace evidence is stale or newer than its confirmation."
        )
    _redirect_namespace_paths(confirmation)


def _redirect_namespace_paths(confirmation: Mapping[str, Any]) -> set[str]:
    namespace = confirmation.get("seo_url_namespace")
    keys = {
        "schema_version",
        "source_identity",
        "target_identity",
        "migration_run_id",
        "snapshot_id",
        "plan_hash",
        "captured_at",
        "complete",
        "row_count",
        "content_hash",
        "paths",
    }
    if not isinstance(namespace, Mapping) or set(namespace) != keys:
        raise MigrationApplyError("SEO URL namespace evidence has an invalid exact shape.")
    if namespace.get("schema_version") != "1.0" or namespace.get("complete") is not True:
        raise MigrationApplyError("SEO URL namespace evidence must be complete schema 1.0.")
    if not str(namespace.get("source_identity") or "").strip():
        raise MigrationApplyError("SEO URL namespace source identity is missing.")
    timestamp = str(namespace.get("captured_at") or "")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MigrationApplyError("SEO URL namespace timestamp is invalid.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MigrationApplyError("SEO URL namespace timestamp requires a timezone.")
    paths = namespace.get("paths")
    if not isinstance(paths, list) or any(
        not isinstance(path, str)
        or not path.startswith("/")
        or "?" in path
        or "#" in path
        for path in paths
    ):
        raise MigrationApplyError("SEO URL namespace paths are invalid.")
    normalized_paths = [_normalize_route_path(path) for path in paths]
    if (
        len(paths) != len(set(paths))
        or len(normalized_paths) != len(set(normalized_paths))
        or namespace.get("row_count") != len(paths)
    ):
        raise MigrationApplyError("SEO URL namespace row count or uniqueness is invalid.")
    expected_hash = f"sha256:{_content_hash({'paths': sorted(normalized_paths)})}"
    if namespace.get("content_hash") != expected_hash:
        raise MigrationApplyError("SEO URL namespace content hash does not match.")
    return set(normalized_paths)


def _normalize_route_path(path: str) -> str:
    raw = str(path or "")
    if not raw.startswith("/") or "?" in raw or "#" in raw:
        raise MigrationApplyError("Redirect path is invalid.")
    try:
        decoded = urllib.parse.unquote(raw, encoding="utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise MigrationApplyError("Redirect path encoding is invalid.") from exc
    decoded = unicodedata.normalize("NFC", decoded).replace("\\", "/")
    decoded = re.sub(r"/{2,}", "/", decoded)
    if decoded != "/":
        decoded = decoded.rstrip("/")
    if (
        not decoded.startswith("/")
        or "?" in decoded
        or "#" in decoded
        or any(ord(character) < 32 for character in decoded)
        or any(segment in {".", ".."} for segment in decoded.split("/"))
    ):
        raise MigrationApplyError("Redirect path routing semantics are ambiguous.")
    return decoded.casefold()


def _add_restore_value(
    patch: dict[str, Any], logical: str, operation: Mapping[str, Any]
) -> None:
    value = operation.get("restore_value")
    if logical == "filter_values":
        if isinstance(value, Mapping):
            for key, item in value.items():
                patch[str(key)] = item
        return
    if logical == "identifiers":
        if isinstance(value, Mapping):
            for key, item in value.items():
                patch[str(key)] = item
        return
    if logical == "gallery_image_candidate":
        paths = []
        if isinstance(value, list):
            paths = [
                str(item.get("current_path") or "")
                if isinstance(item, Mapping)
                else str(item or "")
                for item in value
            ]
        if paths:
            patch["image"] = paths[0]
            patch["additional_image"] = ":::".join(paths[1:])
        if operation.get("restore_description") is not None:
            patch["description"] = operation.get("restore_description")
        return
    if logical == "seo_keyword_candidate":
        patch["seo_keyword"] = value
        return
    if logical == "canonical_url":
        patch["product_url"] = value
        return
    if logical in ARTIFACT_ONLY_FIELDS:
        return
    csv_field = CSV_FIELD_MAP.get(logical)
    if csv_field:
        patch[csv_field] = (
            ",".join(str(item) for item in value)
            if logical == "related_products" and isinstance(value, list)
            else value
        )


def _logical_current_value(current: Mapping[str, Any], field: str) -> Any:
    aliases = {
        "filter_values": "filters",
        "gallery_image_candidate": "gallery_paths",
        "seo_keyword_candidate": "seo_keyword",
    }
    key = aliases.get(field, field)
    if key == "gallery_paths":
        return [
            str(current.get("main_image") or current.get("image") or ""),
            *[str(item) for item in current.get("additional_images", []) or []],
        ]
    if key == "identifiers":
        return {
            item: current.get(item, "")
            for item in ("ean", "gtin", "upc", "jan", "isbn")
            if item in current
        }
    return current.get(key)


def _current_for_csv_field(current: Mapping[str, Any], csv_field: str) -> Any:
    if csv_field.startswith("filter_group:"):
        filters = current.get("filters", {})
        return filters.get(csv_field) if isinstance(filters, Mapping) else None
    direct_aliases = {
        "image": "main_image",
        "additional_image": "additional_images",
        "product_url": "canonical_url",
        "meta_keyword": "meta_keywords",
        "related_product": "related_products",
    }
    if csv_field in direct_aliases:
        value = current.get(direct_aliases[csv_field])
        if csv_field == "additional_image" and isinstance(value, list):
            return ":::".join(str(item) for item in value)
        if csv_field == "related_product" and isinstance(value, list):
            return ",".join(str(item) for item in value)
        return value
    reverse = {value: key for key, value in CSV_FIELD_MAP.items()}
    logical = reverse.get(csv_field, csv_field)
    return _logical_current_value(current, logical)


def _write_partial_csv(path: Path, *, model: str, patch: Mapping[str, Any]) -> None:
    forbidden = {"price", "quantity", "status", "stock_status", "active"} & set(patch)
    if forbidden:
        raise MigrationApplyError(f"Protected columns reached partial writer: {sorted(forbidden)}")
    headers = ["model", *sorted(str(key) for key in patch)]
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerow({"model": model, **dict(patch)})
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _verify_patch_columns(path: Path, *, approved_patch: Mapping[str, Any]) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        headers = reader.fieldnames or []
    expected = ["model", *sorted(approved_patch)]
    if headers != expected or len(rows) != 1:
        raise MigrationApplyError("Generated partial CSV does not match approved fields.")
    if any(field in headers for field in ("price", "quantity", "status", "stock_status", "active")):
        raise MigrationApplyError("Generated partial CSV contains a protected field.")


def _publisher_target_identity(publisher: MigrationPublisher) -> str:
    identity = str(getattr(publisher, "target_identity", "") or "").strip()
    if not identity:
        raise MigrationApplyError(
            "Production publisher did not expose a resolved non-secret target identity."
        )
    return identity


def _require_preflight_success(result: Mapping[str, Any], *, model: str) -> None:
    _require_publisher_success(result, stage="partial_import_preflight", model=model)
    if result.get("dry_run") is not True:
        raise MigrationApplyError(
            f"OpenCart mapping preflight was not confirmed as dry-run for {model}."
        )
    step2 = result.get("step2")
    if not isinstance(step2, Mapping) or step2.get("mapping_ok") is not True:
        raise MigrationApplyError(
            f"OpenCart mapping preflight did not confirm every patch column for {model}."
        )
    profile_safety = step2.get("profile_safety")
    if (
        step2.get("unexpected_mappings") not in ({}, None)
        or step2.get("protected_mappings") not in ({}, None)
        or not isinstance(profile_safety, Mapping)
        or profile_safety.get("safe") is not True
        or sorted(profile_safety.get("attested_concepts", []))
        != ["create", "delete", "disable"]
    ):
        raise MigrationApplyError(
            f"OpenCart partial-import profile safety was not positively attested for {model}."
        )


def _begin_production_write_attempt(
    result: dict[str, Any],
    *,
    result_path: Path,
    audit_path: Path,
    run_id: str,
    snapshot_id: str,
    model: str,
    stage: str,
) -> None:
    already_confirmed = result.get("production_updated") is True
    result["production_write_attempted"] = True
    if not already_confirmed:
        result["production_updated"] = None
        result["production_update_state"] = "write_attempted_state_unknown"
    else:
        result["production_update_state"] = "partial_write_confirmed_next_write_unknown"
    _atomic_json(result_path, result)
    _append_audit(
        audit_path,
        {
            "event": "production_write_attempted",
            "migration_run_id": run_id,
            "snapshot_id": snapshot_id,
            "model": model,
            "stage": stage,
            "target_identity": result.get("publisher_target_identity"),
            "state_before_confirmation": result["production_update_state"],
        },
    )


def _require_publisher_success(result: Mapping[str, Any], *, stage: str, model: str) -> None:
    if not isinstance(result, Mapping) or result.get("ok") is not True:
        raise MigrationApplyError(
            f"Production adapter did not confirm {stage} for {model}."
        )


def _require_zero_destructive_import_counts(result: Mapping[str, Any], *, model: str) -> None:
    destructive_values = []
    for key in ("products_deleted", "deleted", "products_disabled", "disabled"):
        value = _find_numeric_key(result, key)
        if value not in {None, 0}:
            destructive_values.append(f"{key}={value}")
    partial_safety = result.get("partial_import_safety")
    if not isinstance(partial_safety, Mapping):
        destructive_values.append("partial_import_safety_missing")
    else:
        for key in (
            "destructive_counts_verified",
            "scope_counts_verified",
            "protected_columns_absent",
        ):
            if partial_safety.get(key) is not True:
                destructive_values.append(f"{key}=false_or_missing")
    if destructive_values:
        raise MigrationApplyError(
            f"Import reported destructive product changes for {model}: {destructive_values or ['unverified delete count']}"
        )


def _find_numeric_key(value: Any, wanted: str) -> int | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized_key = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
            if normalized_key == wanted:
                try:
                    return int(item)
                except (TypeError, ValueError):
                    return None
            nested = _find_numeric_key(item, wanted)
            if nested is not None:
                return nested
    if isinstance(value, list):
        for item in value:
            nested = _find_numeric_key(item, wanted)
            if nested is not None:
                return nested
    return None


def _blocking_live_failures(result: Mapping[str, Any]) -> list[str]:
    return [
        str(check.get("id") or "live_check")
        for check in result.get("checks", [])
        if isinstance(check, Mapping)
        and check.get("status") == "fail"
        and check.get("blocks_apply", check.get("blocks_publish", True))
    ]


def _image_live_validation_failures(result: Mapping[str, Any]) -> list[str]:
    required = {
        "live.http_success",
        "live.final_url",
        "live.canonical_url",
        "live.main_image",
        "live.gallery_order",
        "live.description_images",
        "live.product_structured_data",
    }
    checks = {
        str(check.get("id") or ""): str(check.get("status") or "not_run")
        for check in result.get("checks", [])
        if isinstance(check, Mapping)
    }
    return sorted(
        check_id
        for check_id in required
        if checks.get(check_id) not in (
            {"pass", "not_applicable"}
            if check_id == "live.gallery_order"
            else {"pass"}
        )
    )


def _not_run_live_result(
    model: str, *, expected: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    return build_not_run_report(
        expected or {},
        model=model,
        target_url="",
        reason="live_access_not_configured",
        access_status="not_configured",
    )


def evaluate_effective_seo_health(
    *,
    model: str,
    product_plan: Mapping[str, Any],
    current: Mapping[str, Any],
    patch: Mapping[str, Any],
    live_validation: Mapping[str, Any],
) -> dict[str, Any]:
    health_input = product_plan.get("seo_health_input", {})
    if not isinstance(health_input, Mapping):
        raise MigrationApplyError(f"Post-apply SEO-health input is missing for {model}.")
    row = _health_row_from_current(model, current)
    row.update(patch)
    row["model"] = model
    raw_deterministic = health_input.get("deterministic_product", {})
    if not isinstance(raw_deterministic, Mapping):
        raise MigrationApplyError(f"Post-apply deterministic SEO input is invalid for {model}.")
    deterministic = dict(raw_deterministic)
    deterministic.setdefault(
        "brand", str(row.get("manufacturer") or current.get("manufacturer") or "")
    )
    deterministic.setdefault("manufacturer", deterministic.get("brand", ""))
    deterministic.setdefault("mpn", str(row.get("mpn") or current.get("mpn") or ""))
    effective_slug = str(row.get("seo_keyword") or "")
    deterministic["published_seo_keyword"] = effective_slug
    deterministic["seo_keyword_candidate"] = effective_slug
    deterministic["seo_keyword"] = effective_slug
    identity = deterministic.get("seo_identity", {})
    identity = dict(identity) if isinstance(identity, Mapping) else {}
    identity.setdefault("primary_model", deterministic.get("mpn", ""))
    identity.update(
        {
            "published_seo_keyword": effective_slug,
            "seo_keyword_candidate": effective_slug,
            "seo_keyword_locked": bool(effective_slug),
        }
    )
    deterministic["seo_identity"] = identity
    # Product identity and Phase 2/3 artifacts are candidate evidence, not
    # proof of what this approved partial patch published.  They remain
    # explicitly not_run until the corresponding production consumers are
    # validated.
    deterministic.pop("product_identity", None)
    for phase2_key in (
        "image_assets",
        "presentation_section_image_metadata",
        "internal_links",
        "catalog_similarity",
        "description_heading",
    ):
        deterministic.pop(phase2_key, None)
    phase4 = (
        dict(health_input.get("phase4", {}))
        if isinstance(health_input.get("phase4"), Mapping)
        else {}
    )
    live_checks = [
        {
            "id": str(check.get("id") or "live.check"),
            "status": str(check.get("status") or "not_run"),
            "blocks_publish": bool(check.get("blocks_apply", False)),
            "message": str(check.get("message") or check.get("status") or "not_run"),
            "observed": check.get("observed"),
            "expected": check.get("expected"),
            "evidence": check.get("evidence", []),
        }
        for check in live_validation.get("checks", [])
        if isinstance(check, Mapping)
    ]
    phase4["rollout.production_validation"] = {
        "status": str(live_validation.get("status") or "not_run"),
        "blocks_publish": bool(_blocking_live_failures(live_validation)),
        "message": str(
            live_validation.get("reason")
            or "Post-apply live validation was evaluated."
        ),
        "observed": live_validation.get("coverage", {}),
        "expected": {"failed": 0, "coverage": 100},
        "subchecks": live_checks,
    }
    report = evaluate_seo_health(
        model=model,
        row=row,
        deterministic_product=dict(deterministic),
        profile="full",
        phase2={},
        phase3={},
        phase4=phase4,
        settings={"enforcement_mode": "blockers_only", "phase3": {"enabled": False}},
    )
    if report.get("publish_gate", {}).get("enforcement_mode") != "blockers_only":
        raise MigrationApplyError(
            "Post-apply SEO-health enforcement changed unexpectedly; strict is never automatic."
        )
    return report


def _health_row_from_current(
    model: str, current: Mapping[str, Any]
) -> dict[str, Any]:
    additional = current.get("additional_images", [])
    related = current.get("related_products", [])
    return {
        "model": model,
        "mpn": str(current.get("mpn") or ""),
        "name": str(current.get("name") or ""),
        "description": str(current.get("description") or ""),
        "meta_title": str(current.get("meta_title") or ""),
        "meta_description": str(current.get("meta_description") or ""),
        "meta_keyword": str(current.get("meta_keywords") or ""),
        "seo_keyword": str(current.get("seo_keyword") or ""),
        "product_url": str(current.get("canonical_url") or ""),
        "image": str(current.get("main_image") or ""),
        "additional_image": ":::".join(str(item) for item in additional)
        if isinstance(additional, list)
        else str(additional or ""),
        "related_product": ",".join(str(item) for item in related)
        if isinstance(related, list)
        else str(related or ""),
        "manufacturer": str(current.get("manufacturer") or ""),
        "price": str(current.get("price") or ""),
        "quantity": str(current.get("quantity") or ""),
        "stock_status": str(current.get("stock_status") or ""),
        "status": str(current.get("status") or ""),
    }


def _live_expected_state(
    *,
    current: Mapping[str, Any],
    patch: Mapping[str, Any],
    product_plan: Mapping[str, Any] | None = None,
    catalog_products: Mapping[str, Mapping[str, Any]] | None = None,
    approval: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    expected = {**dict(current), **dict(patch)}
    aliases = {
        "product_url": "canonical_url",
        "image": "main_image",
        "meta_keyword": "meta_keywords",
        "related_product": "related_products",
    }
    for csv_field, snapshot_field in aliases.items():
        if csv_field in patch:
            expected[snapshot_field] = patch[csv_field]
    if "additional_image" in patch:
        value = patch["additional_image"]
        expected["additional_images"] = (
            [item for item in str(value or "").split(":::") if item]
            if not isinstance(value, list)
            else list(value)
        )
    plan = product_plan if isinstance(product_plan, Mapping) else {}
    health_input = plan.get("seo_health_input", {})
    health_input = health_input if isinstance(health_input, Mapping) else {}
    phase2 = health_input.get("phase2", {})
    phase2 = phase2 if isinstance(phase2, Mapping) else {}
    approved_fields = set(
        approval.get("approved_fields", [])
        if isinstance(approval, Mapping)
        else []
    )
    internal_links = phase2.get("internal_links")
    if (
        approved_fields & {"description", "related_products", "category"}
        and isinstance(internal_links, (Mapping, list))
        and internal_links
    ):
        expected["internal_links"] = _resolve_reviewed_internal_links(
            internal_links, catalog_products or {}
        )
    description_heading = str(phase2.get("description_heading") or "").strip()
    if "description" in approved_fields and description_heading:
        expected["description_heading"] = description_heading
    return expected


def _resolve_reviewed_internal_links(
    value: Any, catalog_products: Mapping[str, Mapping[str, Any]]
) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _resolve_reviewed_internal_links(item, catalog_products)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _resolve_reviewed_internal_links(item, catalog_products)
            for item in value
        ]
    text = str(value or "").strip()
    if re.fullmatch(r"\d{6}", text):
        product = catalog_products.get(text, {})
        return str(product.get("canonical_url") or text)
    return value


def _is_besco_reference(value: str) -> bool:
    return "01_bescos" in value.casefold() or bool(
        re.search(r"(?:^|/)besco[1-9][0-9]*\.jpe?g$", value, re.I)
    )


def _run_adapter(command: list[str], report_path: Path) -> Mapping[str, Any]:
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=1200,
    )
    if completed.returncode != 0:
        raise MigrationApplyError(
            f"OpenCart adapter failed with exit code {completed.returncode}: "
            f"{_redact_sensitive_text(completed.stderr.strip() or completed.stdout.strip())}"
        )
    if not report_path.exists():
        raise MigrationApplyError("OpenCart adapter did not create its audit report.")
    payload = _read_json(report_path)
    if not isinstance(payload, Mapping):
        raise MigrationApplyError("OpenCart adapter report has an invalid shape.")
    return payload


def _append_audit(path: Path, event: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": _utcnow(),
        **dict(event),
    }
    line = _canonical_json(payload) + "\n"
    try:
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise MigrationApplyError(f"Production audit write failed closed: {exc}") from exc


def _claim_apply_run_once(
    path: Path,
    *,
    migration_run_id: str,
    snapshot_id: str,
    approval_hash: str,
    plan_hash: str,
    target_identity: str,
    scopes: list[Mapping[str, Any]],
) -> None:
    normalized_scopes = [_normalize_authorization_scope(item) for item in scopes]
    if not normalized_scopes:
        raise MigrationApplyError("Apply claim requires at least one exact product scope.")
    if len({item["model"] for item in normalized_scopes}) != len(normalized_scopes):
        raise MigrationApplyError("Apply claim contains duplicate product scopes.")
    _write_exclusive_json(
        path,
        {
            "schema_version": "1.0",
            "operation": "apply",
            "migration_run_id": migration_run_id,
            "snapshot_id": snapshot_id,
            "approval_hash": approval_hash,
            "plan_hash": plan_hash,
            "target_identity": target_identity,
            "claimed_at": _utcnow(),
            "one_shot": True,
            "scopes": normalized_scopes,
        },
        exists_message=(
            "This migration run already has an apply claim. Re-apply is forbidden; "
            "inspect its audit/result and use rollback or a new migration run."
        ),
    )


def _adapter_authorization(
    *,
    operation: str,
    migration_run_id: str,
    snapshot_id: str,
    approval_hash: str,
    plan_hash: str,
    target_identity: str,
    claim_path: Path,
    scope: Mapping[str, Any],
) -> dict[str, Any]:
    if operation not in {"apply", "rollback"}:
        raise MigrationApplyError("Adapter authorization operation is invalid.")
    exact_scope = _normalize_authorization_scope(scope)
    resolved_claim = claim_path.expanduser().resolve()
    if not resolved_claim.is_file():
        raise MigrationApplyError("Run-bound adapter claim is missing.")
    issued = datetime.now(timezone.utc)
    return {
        "schema_version": "1.0",
        "operation": operation,
        "migration_run_id": migration_run_id,
        "snapshot_id": snapshot_id,
        "approval_hash": approval_hash,
        "plan_hash": plan_hash,
        "target_identity": target_identity,
        **exact_scope,
        "claim_path": str(resolved_claim),
        "claim_hash": _sha256_file(resolved_claim),
        "issued_at": issued.isoformat(),
        "expires_at": (
            issued + timedelta(seconds=ADAPTER_AUTHORIZATION_TTL_SECONDS)
        ).isoformat(),
    }


def _verify_stored_adapter_authorization(
    authorization: Mapping[str, Any],
    *,
    operation: str,
    migration_run_id: str,
    snapshot_id: str,
    approval_hash: str,
    plan_hash: str,
    target_identity: str,
    claim_path: Path,
    scope: Mapping[str, Any],
) -> None:
    exact_scope = _normalize_authorization_scope(scope)
    expected_keys = {
        "schema_version",
        "operation",
        "migration_run_id",
        "snapshot_id",
        "approval_hash",
        "plan_hash",
        "target_identity",
        *exact_scope,
        "claim_path",
        "claim_hash",
        "issued_at",
        "expires_at",
    }
    if not isinstance(authorization, Mapping) or set(authorization) != expected_keys:
        raise MigrationApplyError(
            "Stored adapter authorization evidence has an invalid exact shape."
        )
    expected = {
        "schema_version": "1.0",
        "operation": operation,
        "migration_run_id": migration_run_id,
        "snapshot_id": snapshot_id,
        "approval_hash": approval_hash,
        "plan_hash": plan_hash,
        "target_identity": target_identity,
        **exact_scope,
        "claim_path": str(claim_path.expanduser().resolve()),
        "claim_hash": _sha256_file(claim_path.expanduser().resolve()),
    }
    if any(authorization.get(key) != value for key, value in expected.items()):
        raise MigrationApplyError("Stored adapter authorization binding changed.")
    issued = _require_rfc3339_timestamp(
        authorization.get("issued_at"), label="adapter authorization issue"
    )
    expires = _require_rfc3339_timestamp(
        authorization.get("expires_at"), label="adapter authorization expiry"
    )
    lifetime = (expires - issued).total_seconds()
    claim = _load_run_claim(
        claim_path,
        expected_operation=operation,
        migration_run_id=migration_run_id,
        snapshot_id=snapshot_id,
        target_identity=target_identity,
    )
    claimed = _require_rfc3339_timestamp(
        claim.get("claimed_at"), label="adapter authorization claim"
    )
    if (
        issued < claimed
        or lifetime <= 0
        or lifetime > ADAPTER_AUTHORIZATION_TTL_SECONDS
    ):
        raise MigrationApplyError(
            "Stored adapter authorization lifetime or claim ordering is invalid."
        )


def _claim_rollback_model(
    path: Path,
    *,
    migration_run_id: str,
    snapshot_id: str,
    approval_hash: str,
    plan_hash: str,
    target_identity: str,
    scope: Mapping[str, Any],
) -> None:
    exact_scope = _normalize_authorization_scope(scope)
    immutable = {
        "schema_version": "1.0",
        "operation": "rollback",
        "migration_run_id": migration_run_id,
        "snapshot_id": snapshot_id,
        "approval_hash": approval_hash,
        "plan_hash": plan_hash,
        "target_identity": target_identity,
        "one_shot": True,
        "scopes": [exact_scope],
    }
    _write_exclusive_json(
        path,
        {**immutable, "claimed_at": _utcnow()},
        exists_message=(
            "Rollback authorization claim appeared concurrently; inspect the run "
            "before retrying."
        ),
    )


def _next_rollback_claim_path(run_path: Path, model: str) -> Path:
    claim_dir = run_path / "rollback" / "claims"
    for attempt in range(1, 10000):
        path = claim_dir / f"{model}.attempt-{attempt:04d}.claim.json"
        if not path.exists():
            return path
    raise MigrationApplyError(
        f"Rollback authorization attempt limit reached for {model}."
    )


def _load_run_claim(
    path: Path,
    *,
    expected_operation: str,
    migration_run_id: str,
    snapshot_id: str,
    target_identity: str,
) -> dict[str, Any]:
    claim = _read_json(path)
    expected_keys = {
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
    if not isinstance(claim, Mapping) or set(claim) != expected_keys:
        raise MigrationApplyError("Run authorization claim has an invalid exact shape.")
    if (
        claim.get("schema_version") != "1.0"
        or claim.get("operation") != expected_operation
        or claim.get("migration_run_id") != migration_run_id
        or claim.get("snapshot_id") != snapshot_id
        or claim.get("target_identity") != target_identity
        or claim.get("one_shot") is not True
    ):
        raise MigrationApplyError("Run authorization claim binding does not match.")
    if not str(claim.get("approval_hash") or "") or not str(
        claim.get("plan_hash") or ""
    ):
        raise MigrationApplyError("Run authorization claim hashes are missing.")
    _require_rfc3339_timestamp(claim.get("claimed_at"), label="claim")
    scopes = claim.get("scopes")
    if not isinstance(scopes, list) or not scopes:
        raise MigrationApplyError("Run authorization claim scopes are missing.")
    normalized = [_normalize_authorization_scope(item) for item in scopes]
    if normalized != scopes or len({item["model"] for item in normalized}) != len(
        normalized
    ):
        raise MigrationApplyError("Run authorization claim scopes are invalid.")
    return dict(claim)


def _normalize_authorization_scope(scope: Mapping[str, Any]) -> dict[str, Any]:
    expected_keys = {"model", "csv_sha256", "headers", "image_operations_hash"}
    if not isinstance(scope, Mapping) or set(scope) != expected_keys:
        raise MigrationApplyError("Adapter authorization scope has an invalid exact shape.")
    model = str(scope.get("model") or "")
    csv_sha256 = str(scope.get("csv_sha256") or "")
    headers = scope.get("headers")
    image_operations_hash = str(scope.get("image_operations_hash") or "")
    if not re.fullmatch(r"\d{6}", model):
        raise MigrationApplyError("Adapter authorization scope model is invalid.")
    if not re.fullmatch(r"[0-9a-f]{64}", csv_sha256):
        raise MigrationApplyError("Adapter authorization CSV hash is invalid.")
    if (
        not isinstance(headers, list)
        or not headers
        or any(not isinstance(item, str) or not item for item in headers)
        or len(headers) != len(set(headers))
    ):
        raise MigrationApplyError("Adapter authorization headers are invalid.")
    if not re.fullmatch(r"[0-9a-f]{64}", image_operations_hash):
        raise MigrationApplyError("Adapter authorization image operation hash is invalid.")
    return {
        "model": model,
        "csv_sha256": csv_sha256,
        "headers": list(headers),
        "image_operations_hash": image_operations_hash,
    }


def _csv_headers(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            headers = list(csv.DictReader(handle).fieldnames or [])
    except (OSError, UnicodeError, csv.Error) as exc:
        raise MigrationApplyError(f"Could not read partial import headers: {exc}") from exc
    if not headers or len(headers) != len(set(headers)):
        raise MigrationApplyError("Partial import headers are missing or duplicated.")
    return headers


def _reject_existing_apply_claim(path: Path) -> None:
    if path.exists():
        raise MigrationApplyError(
            "This migration run already has an apply claim. Re-apply is forbidden; "
            "inspect its audit/result and use rollback or a new migration run."
        )


def _acquire_active_lock(
    path: Path, *, operation: str, run_path: Path
) -> Path:
    if path.exists() and operation == "rollback":
        _archive_recoverable_stale_apply_lock(path=path, run_path=run_path)
    _write_exclusive_json(
        path,
        {
            "schema_version": "1.0",
            "operation": operation,
            "acquired_at": _utcnow(),
            "owner_pid": os.getpid(),
            "host_id": _lock_host_id(),
            "run_path_hash": _content_hash(str(run_path.resolve())),
        },
        exists_message=(
            f"Another {operation} may be active, or a prior process crashed. "
            "Inspect the audit and state before manually clearing the lock."
        ),
    )
    return path


def _acquire_operation_locks(
    *, run_path: Path, target_identity: str, operation: str
) -> list[Path]:
    target_digest = _content_hash(target_identity)
    paths = [
        REPO_ROOT / "migration" / ".locks" / f"target-{target_digest}.active.lock",
        run_path / "run.active.lock",
    ]
    acquired: list[Path] = []
    try:
        for path in paths:
            acquired.append(
                _acquire_active_lock(
                    path, operation=operation, run_path=run_path
                )
            )
    except Exception:
        _release_operation_locks(acquired)
        raise
    return acquired


def _archive_recoverable_stale_apply_lock(*, path: Path, run_path: Path) -> None:
    """Reclaim a dead local apply lock only during an explicit rollback.

    The lock must be exact, belong to this run on this host, and name a process
    that is no longer alive.  Its bytes are preserved as recovery evidence.
    Locks from another host/run or a live owner remain fail-closed.
    """

    lock = _read_json(path)
    expected_keys = {
        "schema_version",
        "operation",
        "acquired_at",
        "owner_pid",
        "host_id",
        "run_path_hash",
    }
    owner_pid = lock.get("owner_pid")
    if (
        set(lock) != expected_keys
        or lock.get("schema_version") != "1.0"
        or lock.get("operation") != "apply"
        or lock.get("host_id") != _lock_host_id()
        or lock.get("run_path_hash") != _content_hash(str(run_path.resolve()))
        or not isinstance(owner_pid, int)
        or owner_pid <= 0
        or _process_is_alive(owner_pid)
    ):
        raise MigrationApplyError(
            "Existing migration lock is not a safely recoverable crashed apply; "
            "refusing automatic lock removal."
        )
    _require_rfc3339_timestamp(lock.get("acquired_at"), label="active lock")
    apply_result_path = run_path / "apply_result.json"
    if not apply_result_path.is_file() or _read_json(apply_result_path).get(
        "status"
    ) not in {"running", "failed", "applied"}:
        raise MigrationApplyError(
            "Stale apply lock has no compatible durable apply result evidence."
        )
    archive_dir = run_path / "recovery" / "stale-locks"
    archive_dir.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive = archive_dir / f"{path.name}.{suffix}.recovered.json"
    try:
        os.replace(path, archive)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise MigrationApplyError(
            f"Could not preserve stale apply lock for recovery: {path}"
        ) from exc


def _lock_host_id() -> str:
    return hashlib.sha256(
        socket.gethostname().strip().casefold().encode("utf-8")
    ).hexdigest()


def _process_is_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    if os.name == "nt":
        try:
            import ctypes

            process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not process:
                return False
            ctypes.windll.kernel32.CloseHandle(process)
            return True
        except Exception:
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _release_operation_locks(paths: list[Path]) -> None:
    first_error: Exception | None = None
    for path in reversed(paths):
        try:
            _release_active_lock(path)
        except Exception as exc:  # retain the first fail-closed error
            first_error = first_error or exc
    if first_error is not None:
        raise first_error


def _release_active_lock(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise MigrationApplyError(
            f"Could not release migration active lock; inspect before retry: {path}"
        ) from exc


def _write_exclusive_json(
    path: Path,
    payload: Mapping[str, Any],
    *,
    exists_message: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise MigrationApplyError(exists_message) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception as exc:
        # Leave the exclusive marker in place on uncertain failure. A human
        # must inspect it before authorizing another production attempt.
        raise MigrationApplyError(
            f"Could not durably write exclusive migration marker: {path}"
        ) from exc


def _persist_or_verify_reviewed_input(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        existing = _read_json(path)
        if _canonical_json(existing) != _canonical_json(payload):
            raise MigrationApplyError(
                f"Reviewed migration input already exists with different content: {path.name}"
            )
        return
    _write_exclusive_json(
        path,
        payload,
        exists_message=(
            f"Reviewed migration input appeared concurrently: {path.name}"
        ),
    )


def _atomic_json(path: Path, payload: Any) -> None:
    _atomic_bytes(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8"),
    )


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MigrationApplyError(f"Could not read migration artifact {path}: {exc}") from exc


def _content_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _latest_rfc3339_timestamp(*values: str, label: str) -> str:
    parsed = [
        _require_rfc3339_timestamp(value, label=label) for value in values
    ]
    return max(parsed).isoformat()


def _require_rfc3339_timestamp(value: Any, *, label: str) -> datetime:
    text = str(value or "")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MigrationApplyError(f"{label.capitalize()} timestamp is invalid.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MigrationApplyError(
            f"{label.capitalize()} timestamp must include a timezone."
        )
    return parsed


def _redact_sensitive_text(value: str) -> str:
    return re.sub(
        r"(?i)(user_token|access_token|token|password|secret|api_key)=([^&\s'\"]+)",
        r"\1=<redacted>",
        str(value or ""),
    )
