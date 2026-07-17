from __future__ import annotations

"""Operator CLI for the dry-run-first Product Factory SEO rollout."""

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

from ..local_env import load_local_env_if_present
from ..repo_paths import REPO_ROOT
from .approval import approved_product_map, load_approval_manifest
from .candidates import candidate_catalog_hash, load_candidate_catalog
from .execution import (
    CSV_FIELD_MAP,
    ApplyOptions,
    MigrationApplyError,
    OpenCartPartialCsvPublisher,
    apply_migration,
    evaluate_effective_seo_health,
    resolve_opencart_target_identity,
    rollback_migration,
)
from .live_validation import validate_live_product
from .monitoring import build_monitoring_report
from .planner import (
    MigrationPlanError,
    build_migration_plan,
    load_plan_artifacts,
    write_migration_artifacts,
)
from .snapshot import (
    SnapshotError,
    create_catalog_snapshot,
    load_catalog_snapshot,
    normalize_catalog_export,
)


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "migration"
APPROVABLE_FIELDS = frozenset(
    {
        *CSV_FIELD_MAP,
        "filter_values",
    }
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m product_factory.seo_migration")
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot", help="Create an immutable catalog snapshot.")
    snapshot.add_argument("--catalog-export", required=True)
    snapshot.add_argument("--environment", required=True)
    snapshot.add_argument("--source-identity", required=True)
    snapshot.add_argument(
        "--target-identity",
        default="unbound",
        help="Resolved non-secret OpenCart target fingerprint.",
    )
    snapshot.add_argument("--snapshot-id")
    _add_output_root(snapshot)

    plan = subparsers.add_parser("plan", help="Generate offline migration review artifacts.")
    plan.add_argument("--snapshot-id", required=True)
    plan.add_argument("--candidate-dir", required=True)
    plan.add_argument("--migration-run-id")
    plan.add_argument("--family", choices=("air_conditioner", "all"), default="all")
    plan.add_argument("--models", help="Comma-separated explicit six-digit model scope.")
    plan.add_argument("--models-file", help="Text file containing one six-digit model per line.")
    plan.add_argument("--canary-size", type=int, default=5)
    plan.add_argument(
        "--image-root",
        help=(
            "Optional local root above catalog/ used to hash published image "
            "sources into the immutable reviewed plan. Required before an "
            "image-path change can be approved."
        ),
    )
    plan.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Explicitly document offline dry-run mode (also the default).",
    )
    _add_output_root(plan)

    apply_parser = subparsers.add_parser("apply", help="Apply approved production patches.")
    apply_parser.add_argument("--apply", action="store_true", required=True)
    apply_parser.add_argument("--environment", required=True)
    apply_parser.add_argument("--snapshot-id", required=True)
    apply_parser.add_argument("--migration-run-id", required=True)
    apply_parser.add_argument("--approval-file", required=True)
    apply_parser.add_argument(
        "--catalog-export",
        required=True,
        help="Fresh full target export used to reject stale snapshots.",
    )
    apply_parser.add_argument("--confirm-production-write", required=True)
    apply_parser.add_argument("--target-identity", required=True)
    apply_parser.add_argument("--publisher", choices=("opencart",), required=True)
    apply_parser.add_argument("--opencart-import-profile", required=True)
    apply_parser.add_argument("--image-root")
    apply_parser.add_argument("--redirect-confirmation-file")
    apply_parser.add_argument("--canary", action="store_true")
    apply_parser.add_argument("--live-validate", action="store_true")
    _add_output_root(apply_parser)

    rollback = subparsers.add_parser("rollback", help="Restore one applied migration run.")
    rollback.add_argument("--rollback", required=True, dest="migration_run_id")
    rollback.add_argument("--environment", required=True)
    rollback.add_argument("--current-catalog-export", required=True)
    rollback.add_argument("--confirm-production-write", required=True)
    rollback.add_argument("--target-identity", required=True)
    rollback.add_argument("--publisher", choices=("opencart",), required=True)
    rollback.add_argument("--opencart-import-profile", required=True)
    rollback.add_argument("--redirect-confirmation-file")
    _add_output_root(rollback)

    live = subparsers.add_parser("validate-live", help="Run or explicitly skip live checks.")
    live.add_argument("--snapshot-id", required=True)
    live.add_argument("--model", required=True)
    live.add_argument("--target-url")
    live.add_argument("--migration-run-id")
    live.add_argument(
        "--approval-file",
        help="Optional applied approval; sealed run approval is used when available.",
    )
    live.add_argument("--timeout-seconds", type=float, default=10.0)
    _add_output_root(live)

    monitor = subparsers.add_parser("monitor", help="Generate post-rollout findings.")
    monitor.add_argument("--migration-run-id", required=True)
    monitor.add_argument("--snapshot-id", required=True)
    monitor.add_argument("--current-catalog-export", required=True)
    monitor.add_argument("--approval-file", required=True)
    _add_output_root(monitor)

    fingerprint = subparsers.add_parser(
        "target-fingerprint",
        help="Resolve the non-secret target fingerprint without network access.",
    )
    fingerprint.add_argument("--opencart-import-profile", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            return _snapshot_command(args)
        if args.command == "plan":
            return _plan_command(args)
        if args.command == "apply":
            return _apply_command(args)
        if args.command == "rollback":
            return _rollback_command(args)
        if args.command == "validate-live":
            return _live_command(args)
        if args.command == "monitor":
            return _monitor_command(args)
        if args.command == "target-fingerprint":
            load_local_env_if_present()
            _print_json(
                {
                    "target_identity": resolve_opencart_target_identity(
                        args.opencart_import_profile
                    ),
                    "network_access": False,
                    "production_writes": 0,
                }
            )
            return 0
        raise AssertionError(args.command)
    except (SnapshotError, MigrationPlanError, MigrationApplyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def _snapshot_command(args: argparse.Namespace) -> int:
    snapshot = create_catalog_snapshot(
        args.catalog_export,
        output_root=args.output_root,
        source_environment=args.environment,
        source_export_identity=args.source_identity,
        target_identity=args.target_identity,
        snapshot_id=args.snapshot_id,
    )
    _print_json(
        {
            "status": "created",
            "dry_run": True,
            "snapshot_id": snapshot["snapshot_id"],
            "row_count": snapshot["metadata"]["row_count"],
            "content_hash": snapshot["metadata"]["content_hash"],
            "catalog_hash": snapshot["metadata"]["catalog_hash"],
            "production_writes": 0,
        }
    )
    return 0


def _plan_command(args: argparse.Namespace) -> int:
    snapshot = load_catalog_snapshot(args.output_root, args.snapshot_id)
    candidates = load_candidate_catalog(args.candidate_dir)
    selected_models = _selected_models(args.models, args.models_file)
    if selected_models:
        missing = sorted(selected_models - set(candidates))
        if missing:
            raise MigrationPlanError(f"Requested candidate models are missing: {missing}")
        candidates = {model: candidates[model] for model in sorted(selected_models)}
    if args.family == "air_conditioner":
        candidates = {
            model: value
            for model, value in candidates.items()
            if _candidate_is_air_conditioner(value)
        }
        if not candidates:
            raise MigrationPlanError("No air-conditioner candidates were found in scope.")
    candidate_hash = candidate_catalog_hash(candidates)
    run_id = args.migration_run_id or _default_run_id(candidate_hash)
    plan = build_migration_plan(
        snapshot=snapshot,
        candidates=candidates,
        run_id=run_id,
        canary_size=args.canary_size,
        image_root=args.image_root,
    )
    run_dir = write_migration_artifacts(plan, args.output_root)
    _print_json(
        {
            "status": "dry_run_complete",
            "dry_run": True,
            "migration_run_id": run_id,
            "snapshot_id": args.snapshot_id,
            "artifact_dir": str(run_dir),
            "plan_hash": plan["plan_hash"],
            "summary": plan["summary"],
            "production_writes": 0,
        }
    )
    return 0


def _apply_command(args: argparse.Namespace) -> int:
    load_local_env_if_present()
    snapshot = load_catalog_snapshot(args.output_root, args.snapshot_id)
    run_dir = Path(args.output_root) / args.migration_run_id
    plan = load_plan_artifacts(run_dir)
    approval = load_approval_manifest(
        args.approval_file,
        snapshot_id=args.snapshot_id,
        migration_run_id=args.migration_run_id,
        allowed_fields=APPROVABLE_FIELDS,
    )
    current = normalize_catalog_export(args.catalog_export)
    redirect_confirmation = _optional_json(args.redirect_confirmation_file)
    publisher = OpenCartPartialCsvPublisher(
        import_profile=args.opencart_import_profile
    )
    live_validator = validate_live_product if args.live_validate else None
    result = apply_migration(
        snapshot=snapshot,
        plan=plan,
        approval=approval,
        options=ApplyOptions(
            apply=args.apply,
            environment=args.environment,
            confirmation=args.confirm_production_write,
            canary=args.canary,
            target_identity=args.target_identity,
        ),
        target_content_hash=current["catalog_hash"],
        run_dir=run_dir,
        publisher=publisher,
        image_root=args.image_root,
        redirect_confirmation=redirect_confirmation,
        live_validator=live_validator,
    )
    _print_json(result)
    return 0


def _rollback_command(args: argparse.Namespace) -> int:
    load_local_env_if_present()
    current_export = normalize_catalog_export(args.current_catalog_export)
    current_products = {
        row["model"]: row for row in current_export["products"]
    }
    run_dir = Path(args.output_root) / args.migration_run_id
    publisher = OpenCartPartialCsvPublisher(
        import_profile=args.opencart_import_profile
    )
    result = rollback_migration(
        migration_run_id=args.migration_run_id,
        environment=args.environment,
        confirmation=args.confirm_production_write,
        run_dir=run_dir,
        current_products=current_products,
        publisher=publisher,
        target_identity=args.target_identity,
        redirect_confirmation=_optional_json(args.redirect_confirmation_file),
    )
    _print_json(result)
    return 0


def _live_command(args: argparse.Namespace) -> int:
    snapshot = load_catalog_snapshot(args.output_root, args.snapshot_id)
    products = {row["model"]: row for row in snapshot["products"]}
    expected = products.get(args.model)
    if expected is None:
        raise ValueError(f"Model is missing from snapshot: {args.model}")
    if args.migration_run_id:
        effective_approval: Mapping[str, Any] | None = None
        run_dir = Path(args.output_root) / args.migration_run_id
        plan = load_plan_artifacts(run_dir)
        product_plan = next(
            (
                item
                for item in plan.get("products", [])
                if isinstance(item, Mapping) and item.get("model") == args.model
            ),
            {},
        )
        approval_path = (
            Path(args.approval_file)
            if args.approval_file
            else run_dir / "apply.approval.json"
        )
        if approval_path.is_file():
            approval = load_approval_manifest(
                approval_path,
                snapshot_id=args.snapshot_id,
                migration_run_id=args.migration_run_id,
                allowed_fields=APPROVABLE_FIELDS,
            )
            approval_item = approved_product_map(approval).get(args.model)
            if approval_item is not None:
                rollback_manifest = _read_json(run_dir / "rollback_manifest.json")
                state = _model_apply_state(rollback_manifest, args.model)
                if state not in {"unattempted", "rolled_back"}:
                    expected = _expected_after(
                        expected,
                        product_plan,
                        approval_item,
                        rollback_manifest=rollback_manifest,
                        model=args.model,
                    )
                    effective_approval = approval_item
        expected = _with_reviewed_live_expectations(
            expected,
            product_plan,
            catalog_products=products,
            approval=effective_approval,
        )
    report = validate_live_product(
        expected,
        model=args.model,
        target_url=args.target_url,
        timeout_seconds=args.timeout_seconds,
    )
    if args.migration_run_id:
        output_path = run_dir / "live_validation" / f"{args.model}.json"
        _atomic_json(output_path, report)
    _print_json(report)
    return 0 if report.get("status") != "fail" else 3


def _monitor_command(args: argparse.Namespace) -> int:
    snapshot = load_catalog_snapshot(args.output_root, args.snapshot_id)
    run_dir = Path(args.output_root) / args.migration_run_id
    plan = load_plan_artifacts(run_dir)
    approval = load_approval_manifest(
        args.approval_file,
        snapshot_id=args.snapshot_id,
        migration_run_id=args.migration_run_id,
        allowed_fields=APPROVABLE_FIELDS,
    )
    apply_claim = _optional_json_path(run_dir / "apply.claim.json")
    if apply_claim is not None and _content_hash(approval) != str(
        apply_claim.get("approval_hash") or ""
    ):
        raise ValueError(
            "Monitoring approval does not match the approval bound to the apply claim."
        )
    approvals = approved_product_map(approval)
    before = {row["model"]: row for row in snapshot["products"]}
    current_export = normalize_catalog_export(args.current_catalog_export)
    after = {row["model"]: row for row in current_export["products"]}
    plan_products = {
        str(product.get("model") or ""): product
        for product in plan.get("products", [])
        if isinstance(product, Mapping)
    }
    rollback_manifest = _read_json(run_dir / "rollback_manifest.json")
    apply_result = _optional_json_path(run_dir / "apply_result.json") or {}
    before_duplicates = _catalog_duplicate_counts(before)
    after_duplicates = _catalog_duplicate_counts(after)
    collateral_models = _catalog_drift_models(before, after) - set(approvals)
    report_models = sorted({*approvals, *collateral_models})
    reports = []
    for model in report_models:
        approval_item = approvals.get(model) or {
            "model": model,
            "approved_fields": [],
            "approved_slug_change": False,
            "approved_image_path_change": False,
            "notes": "unapproved collateral catalog drift",
        }
        product_plan = plan_products.get(model, {})
        live_result = _live_result_for_model(apply_result, model, run_dir=run_dir)
        apply_state = _model_apply_state(rollback_manifest, model)
        expected_after = (
            dict(before.get(model, {}))
            if model not in approvals or apply_state in {"unattempted", "rolled_back"}
            else _expected_after(
                before.get(model, {}),
                product_plan,
                approval_item,
                rollback_manifest=rollback_manifest,
                model=model,
            )
        )
        current_health = (
            evaluate_effective_seo_health(
                model=model,
                product_plan=product_plan,
                current=after.get(model, {}),
                patch={},
                live_validation=(
                    live_result
                    if live_result
                    else {
                        "model": model,
                        "status": "not_run",
                        "reason": "post_rollout_live_validation_unavailable",
                        "checks": [],
                    }
                ),
            )
            if isinstance(product_plan.get("seo_health_input"), Mapping)
            else {}
        )
        reports.append(
            build_monitoring_report(
                {
                    "migration_run_id": args.migration_run_id,
                    "model": model,
                    "before": before.get(model, {}),
                    "after": after.get(model, {}),
                    "expected_after": expected_after,
                    "approval": approval_item,
                    "seo_health": current_health,
                    "baseline_seo_health": product_plan.get("seo_health_before", {}),
                    "structured_artifacts": _structured_artifacts(
                        run_dir,
                        model,
                        product_plan=product_plan,
                        live_validation=live_result,
                    ),
                    "live_validation": live_result,
                    "rollback_manifest": rollback_manifest,
                    "applied": apply_state in {"applied", "unknown"},
                    "apply_state": apply_state,
                    "identifier_contract": "mpn_only",
                    "baseline_metrics": {
                        "duplicate_content_count": before_duplicates.get(model, 0)
                    },
                    "metrics": {
                        "duplicate_content_count": after_duplicates.get(model, 0)
                    },
                }
            )
        )
    summary = {
        "schema_version": "1.0",
        "migration_run_id": args.migration_run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "product_count": len(reports),
        "blocking_findings": sum(
            int(report.get("summary", {}).get("blocking_findings", 0))
            for report in reports
        ),
        "failed_products": sum(1 for report in reports if report.get("status") == "fail"),
        "reports": reports,
    }
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = run_dir / "monitoring" / f"{timestamp}.json"
    _atomic_json(output_path, summary)
    _print_json({**summary, "artifact": str(output_path)})
    return (
        0
        if summary["blocking_findings"] == 0
        and summary["failed_products"] == 0
        else 3
    )


def _expected_after(
    before: Mapping[str, Any],
    product_plan: Mapping[str, Any],
    approval: Mapping[str, Any],
    *,
    rollback_manifest: Mapping[str, Any] | None = None,
    model: str = "",
) -> dict[str, Any]:
    expected = dict(before)
    fields = {
        str(item.get("field") or ""): item
        for item in product_plan.get("fields", [])
        if isinstance(item, Mapping)
    }
    aliases = {
        "filter_values": "filters",
        "related_products": "related_products",
        "meta_keywords": "meta_keywords",
    }
    for field in approval.get("approved_fields", []):
        planned = fields.get(field, {})
        expected[aliases.get(field, field)] = planned.get("candidate_value")
    if approval.get("approved_slug_change"):
        expected["seo_keyword"] = fields.get("seo_keyword_candidate", {}).get(
            "candidate_value"
        )
        expected["canonical_url"] = fields.get("canonical_url", {}).get(
            "candidate_value"
        )
    if approval.get("approved_image_path_change"):
        gallery = fields.get("gallery_image_candidate", {}).get("candidate_value", [])
        paths = [
            str(item.get("candidate_path") or "")
            for item in gallery
            if isinstance(item, Mapping)
        ]
        if paths:
            expected["main_image"] = paths[0]
            expected["additional_images"] = paths[1:]
        effective_description = _effective_expected_image_description(
            rollback_manifest or {}, model
        )
        if effective_description is not None:
            expected["description"] = effective_description
    return expected


def _with_reviewed_live_expectations(
    expected: Mapping[str, Any],
    product_plan: Mapping[str, Any],
    *,
    catalog_products: Mapping[str, Mapping[str, Any]] | None = None,
    approval: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = dict(expected)
    health_input = product_plan.get("seo_health_input", {})
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
        result["internal_links"] = _resolve_reviewed_link_models(
            internal_links, catalog_products or {}
        )
    description_heading = str(phase2.get("description_heading") or "").strip()
    if "description" in approved_fields and description_heading:
        result["description_heading"] = description_heading
    return result


def _resolve_reviewed_link_models(
    value: Any, catalog_products: Mapping[str, Mapping[str, Any]]
) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _resolve_reviewed_link_models(item, catalog_products)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _resolve_reviewed_link_models(item, catalog_products) for item in value
        ]
    text = str(value or "").strip()
    if re.fullmatch(r"\d{6}", text):
        return str(catalog_products.get(text, {}).get("canonical_url") or text)
    return value


def _effective_expected_image_description(
    rollback_manifest: Mapping[str, Any], model: str
) -> str | None:
    for operation in rollback_manifest.get("operations", []):
        if not isinstance(operation, Mapping):
            continue
        if operation.get("model") != model or operation.get("field") != "gallery_image_candidate":
            continue
        value = operation.get("effective_expected_applied_description")
        return str(value) if value is not None else None
    return None


def _structured_artifacts(
    run_dir: Path,
    model: str,
    *,
    product_plan: Mapping[str, Any],
    live_validation: Mapping[str, Any],
) -> dict[str, Any]:
    """Describe candidate, local staging, and observed production separately.

    A migration-local JSON file is review/rollback evidence, not proof that an
    OpenCart page or another production consumer serves that artifact.
    """

    fields = {
        str(item.get("field") or ""): item
        for item in product_plan.get("fields", [])
        if isinstance(item, Mapping)
    }
    candidate: dict[str, Any] = {}
    for name in ("structured_data_manifest", "product_feed_manifest"):
        value = fields.get(name, {}).get("candidate_value")
        if isinstance(value, Mapping) and value:
            candidate[name] = dict(value)

    artifact_dir = run_dir / "apply" / "artifacts" / model
    staged: dict[str, Any] = {}
    if artifact_dir.exists():
        for path in sorted(artifact_dir.glob("*.json")):
            staged[path.stem] = _read_json(path)

    production = _live_structured_artifact(live_validation)
    return {
        "schema_version": "1.0",
        "candidate": {"available": bool(candidate), **candidate},
        "staged": {"available": bool(staged), **staged},
        "production": production,
    }


def _live_structured_artifact(live_validation: Mapping[str, Any]) -> dict[str, Any]:
    checks = {
        str(item.get("id") or ""): item
        for item in live_validation.get("checks", [])
        if isinstance(item, Mapping)
    }
    product_check = checks.get("live.product_structured_data")
    if not isinstance(product_check, Mapping) or product_check.get("status") == "not_run":
        return {
            "status": "not_run",
            "available": None,
            "source": "live_jsonld_validation",
            "reason": "production_structured_data_not_observed",
        }
    if product_check.get("status") != "pass":
        return {
            "status": "fail",
            "available": False,
            "source": "live_jsonld_validation",
            "reason": "live_product_jsonld_unavailable",
        }

    observed_product = product_check.get("observed")
    if isinstance(observed_product, Mapping):
        product_data = dict(observed_product)
    else:
        # Current live-validation reports expose the values parsed from
        # Product JSON-LD on their dedicated checks. Preserve those observed
        # values without copying candidate or staged values into production.
        offer: dict[str, Any] = {}
        price_check = checks.get("live.offer_price", {})
        availability_check = checks.get("live.availability", {})
        if isinstance(price_check, Mapping) and price_check.get("status") != "not_run":
            offer["price"] = price_check.get("observed")
        if (
            isinstance(availability_check, Mapping)
            and availability_check.get("status") != "not_run"
        ):
            offer["availability"] = availability_check.get("observed")
        product_data = {"@type": "Product"}
        if offer:
            product_data["offers"] = offer

    return {
        "status": "pass",
        "available": True,
        "source": "live_jsonld_validation",
        "product_structured_data": product_data,
    }


def _live_result_for_model(
    apply_result: Mapping[str, Any], model: str, *, run_dir: Path
) -> Mapping[str, Any]:
    standalone = run_dir / "live_validation" / f"{model}.json"
    standalone_result = _read_json(standalone) if standalone.is_file() else {}
    embedded = next(
        (
            item.get("live_validation", {})
            for item in apply_result.get("products", [])
            if isinstance(item, Mapping) and item.get("model") == model
        ),
        {},
    )
    if standalone_result and isinstance(embedded, Mapping) and embedded.get("checks"):
        standalone_time = _report_generated_at(standalone_result)
        embedded_time = _report_generated_at(embedded)
        if standalone_time is not None and (
            embedded_time is None or standalone_time >= embedded_time
        ):
            return standalone_result
        return embedded
    if standalone_result:
        return standalone_result
    if isinstance(embedded, Mapping) and embedded.get("checks"):
        return embedded
    return {}


def _report_generated_at(report: Mapping[str, Any]) -> datetime | None:
    value = report.get("generated_at")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _catalog_drift_models(
    before: Mapping[str, Mapping[str, Any]],
    after: Mapping[str, Mapping[str, Any]],
) -> set[str]:
    fields = (
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
        "status",
        "active",
        "price",
        "quantity",
        "stock_status",
    )
    return {
        model
        for model in set(before) | set(after)
        if _canonical_json(
            {field: before.get(model, {}).get(field) for field in fields}
        )
        != _canonical_json(
            {field: after.get(model, {}).get(field) for field in fields}
        )
    }


def _catalog_duplicate_counts(
    products: Mapping[str, Mapping[str, Any]],
) -> dict[str, int]:
    fields = ("name", "meta_title", "meta_description", "description")
    buckets: dict[tuple[str, str], list[str]] = {}
    for model, product in products.items():
        for field in fields:
            value = re.sub(
                r"\s+", " ", str(product.get(field) or "").strip().casefold()
            )
            if value:
                buckets.setdefault((field, value), []).append(model)
    result = {model: 0 for model in products}
    for models in buckets.values():
        if len(models) > 1:
            for model in models:
                result[model] += 1
    return result


def _model_apply_state(rollback: Mapping[str, Any], model: str) -> str:
    selected = {
        (str(item.get("model") or ""), str(item.get("field") or ""))
        for item in rollback.get("selected_operations", [])
        if isinstance(item, Mapping) and item.get("model") == model
    }
    if not selected:
        return "unattempted"
    operations = [
        item
        for item in rollback.get("operations", [])
        if isinstance(item, Mapping)
        and (str(item.get("model") or ""), str(item.get("field") or ""))
        in selected
    ]
    if operations and all(item.get("rolled_back") for item in operations):
        return "rolled_back"
    if any(item.get("applied") for item in operations):
        return "applied"
    if any(item.get("write_attempted") for item in operations):
        return "unknown"
    return "unattempted"


def _selected_models(models: str | None, models_file: str | None) -> set[str]:
    values: list[str] = []
    if models:
        values.extend(part.strip() for part in models.split(",") if part.strip())
    if models_file:
        path = Path(models_file)
        try:
            values.extend(
                line.strip()
                for line in path.read_text(encoding="utf-8-sig").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
        except OSError as exc:
            raise ValueError(f"Could not read models file: {path}") from exc
    invalid = sorted(value for value in values if not re.fullmatch(r"[0-9]{6}", value))
    if invalid:
        raise ValueError(f"Model scope contains invalid six-digit codes: {invalid}")
    return set(values)


def _candidate_is_air_conditioner(candidate: Mapping[str, Any]) -> bool:
    deterministic = candidate.get("deterministic_product", {})
    deterministic = deterministic if isinstance(deterministic, Mapping) else {}
    identity = deterministic.get("seo_identity", {})
    identity = identity if isinstance(identity, Mapping) else {}
    if identity.get("family") == "air_conditioner":
        return True
    values = candidate.get("values", {})
    text = " ".join(
        str(values.get(key) or "") for key in ("name", "category")
    ).casefold()
    return any(token in text for token in ("air conditioner", "klimat", "κλιματι"))


def _default_run_id(candidate_hash: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"phase4-{timestamp}-{candidate_hash[:10]}"


def _optional_json(path: str | None) -> Mapping[str, Any] | None:
    return _read_json(Path(path)) if path else None


def _optional_json_path(path: Path) -> Mapping[str, Any] | None:
    return _read_json(path) if path.exists() else None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read JSON file: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return payload


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _content_hash(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _add_output_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))


def _print_json(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
