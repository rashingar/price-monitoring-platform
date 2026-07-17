from __future__ import annotations

import csv
import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import pytest
from PIL import Image

from product_factory.seo_migration import execution as migration_execution
from product_factory.seo_migration.approval import validate_approval_manifest
from product_factory.seo_migration.candidates import load_candidate_catalog
from product_factory.seo_migration.execution import (
    ApplyOptions,
    MigrationApplyError,
    apply_migration,
    rollback_migration,
)
from product_factory.seo_migration.planner import (
    MigrationPlanError,
    build_migration_plan,
    compute_migration_plan_hash,
    load_plan_artifacts,
    verify_migration_plan,
    write_migration_artifacts,
)
from product_factory.seo_migration.snapshot import create_catalog_snapshot


RUN_ID = "phase4-run-001"
SNAPSHOT_ID = "phase4-snapshot-001"
SOURCE_IDENTITY = "opencart:seo-full:test"

SNAPSHOT_HEADERS = [
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
    "filter_group:BTU",
    "manufacturer",
    "related_products",
    "price",
    "quantity",
    "stock_status",
    "date_added",
    "last_modified",
]

CANDIDATE_HEADERS = [
    "model",
    "mpn",
    "ean",
    "gtin",
    "upc",
    "jan",
    "isbn",
    "name",
    "description",
    "category",
    "filter_group:BTU",
    "image",
    "additional_image",
    "manufacturer",
    "price",
    "quantity",
    "stock_status",
    "status",
    "meta_keyword",
    "meta_title",
    "meta_description",
    "seo_keyword",
    "product_url",
    "related_product",
]


@dataclass
class FakePublisher:
    patch_calls: list[dict[str, Any]] = field(default_factory=list)
    image_calls: list[dict[str, Any]] = field(default_factory=list)
    preflight_calls: list[dict[str, Any]] = field(default_factory=list)
    target_identity: str = SOURCE_IDENTITY

    def preflight_patch(
        self, *, model: str, csv_path: Path, report_path: Path
    ) -> Mapping[str, Any]:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            headers = list(csv.DictReader(handle).fieldnames or [])
        result = {
            "ok": True,
            "dry_run": True,
            "step2": {
                "mapping_ok": True,
                "expected_headers": headers,
                "unexpected_mappings": {},
                "protected_mappings": {},
                "profile_safety": {
                    "safe": True,
                    "attested_concepts": ["create", "delete", "disable"],
                },
            },
        }
        self.preflight_calls.append({"model": model, "headers": headers})
        _write_json(report_path, result)
        return result

    def publish_images(
        self,
        *,
        model: str,
        operations: list[Mapping[str, Any]],
        report_path: Path,
        authorization: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.image_calls.append(
            {
                "model": model,
                "operations": deepcopy(operations),
                "report": report_path,
                "authorization": dict(authorization),
            }
        )
        result = {
            "ok": True,
            "status": "uploaded_and_verified",
            "uploaded": len(operations),
            "write_state": {
                "external_write_attempted": True,
                "upload_attempted": True,
                "upload_confirmed": True,
            },
        }
        _write_json(report_path, result)
        return result

    def publish_patch(
        self,
        *,
        model: str,
        csv_path: Path,
        report_path: Path,
        authorization: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            headers = list(reader.fieldnames or [])
        self.patch_calls.append(
            {
                "model": model,
                "csv_path": csv_path,
                "headers": headers,
                "row": rows[0],
                "report": report_path,
                "authorization": dict(authorization),
            }
        )
        result = {
            "ok": True,
            "products_deleted": 0,
            "products_disabled": 0,
            "partial_import_safety": {
                "lines_processed": 1,
                "products_created": 0,
                "products_updated": 1,
                "products_deleted": 0,
                "products_disabled": 0,
                "categories_created": 0,
                "destructive_counts_verified": True,
                "scope_counts_verified": True,
                "protected_columns_absent": True,
            },
        }
        _write_json(report_path, result)
        return result


@dataclass
class UnknownAfterTriggerPublisher(FakePublisher):
    def publish_patch(
        self,
        *,
        model: str,
        csv_path: Path,
        report_path: Path,
        authorization: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        super().publish_patch(
            model=model,
            csv_path=csv_path,
            report_path=report_path,
            authorization=authorization,
        )
        raise TimeoutError("fixture timeout after import trigger")


@dataclass
class UnsafeCounterPublisher(FakePublisher):
    def publish_patch(
        self,
        *,
        model: str,
        csv_path: Path,
        report_path: Path,
        authorization: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        result = dict(
            super().publish_patch(
                model=model,
                csv_path=csv_path,
                report_path=report_path,
                authorization=authorization,
            )
        )
        result["partial_import_safety"] = {
            **result["partial_import_safety"],
            "products_updated": None,
            "scope_counts_verified": False,
        }
        _write_json(report_path, result)
        return result


@dataclass
class FailingPreflightPublisher(FakePublisher):
    def preflight_patch(
        self, *, model: str, csv_path: Path, report_path: Path
    ) -> Mapping[str, Any]:
        result = {
            "ok": False,
            "dry_run": True,
            "error": "fixture mapping preflight failure",
        }
        _write_json(report_path, result)
        return result


@dataclass(frozen=True)
class MigrationCase:
    snapshot: dict[str, Any]
    candidates: dict[str, dict[str, Any]]
    plan: dict[str, Any]
    root: Path


@pytest.fixture
def migration_case(tmp_path: Path) -> MigrationCase:
    export_path = tmp_path / "exports" / "catalog.csv"
    _write_csv(
        export_path,
        SNAPSHOT_HEADERS,
        [_snapshot_row(index) for index in range(1, 7)],
    )
    snapshot = create_catalog_snapshot(
        export_path,
        output_root=tmp_path / "snapshot-output",
        source_environment="production",
        source_export_identity=SOURCE_IDENTITY,
        target_identity=SOURCE_IDENTITY,
        snapshot_id=SNAPSHOT_ID,
        timestamp="2026-07-12T09:00:00Z",
    )

    candidate_dir = tmp_path / "candidates"
    _write_csv(
        candidate_dir / "products.csv",
        CANDIDATE_HEADERS,
        [_candidate_row(index) for index in range(1, 7)],
    )
    candidates = load_candidate_catalog(candidate_dir)
    plan = build_migration_plan(
        snapshot=snapshot,
        candidates=candidates,
        run_id=RUN_ID,
        generated_at="2026-07-12T09:05:00Z",
        canary_size=5,
    )
    return MigrationCase(snapshot=snapshot, candidates=candidates, plan=plan, root=tmp_path)


def test_dry_run_is_default_and_writes_complete_review_artifacts(
    migration_case: MigrationCase,
) -> None:
    plan = migration_case.plan
    rebuilt = build_migration_plan(
        snapshot=migration_case.snapshot,
        candidates=migration_case.candidates,
        run_id=RUN_ID,
        generated_at="2026-07-12T09:05:00Z",
        canary_size=5,
    )

    assert plan["mode"] == "dry_run"
    assert rebuilt == plan
    assert plan["summary"]["dry_run"] is True
    assert plan["summary"]["production_writes"] == 0
    assert plan["summary"]["strict_enabled_automatically"] is False

    run_dir = write_migration_artifacts(plan, migration_case.root / "migration")
    required = {
        "summary.json",
        "products.csv",
        "products.json",
        "blocked.json",
        "redirect_candidates.csv",
        "image_candidates.csv",
        "rollback_manifest.json",
        "seo_health_summary.json",
    }
    assert required <= {path.name for path in run_dir.iterdir()}
    assert load_plan_artifacts(run_dir)["plan_hash"] == plan["plan_hash"]
    (run_dir / "plan.json").unlink()
    with pytest.raises(MigrationPlanError, match="Authoritative plan.json is missing"):
        load_plan_artifacts(run_dir)

    fields = _field_index(plan, "100001")
    assert fields["name"]["classification"] == "unchanged"
    assert fields["meta_title"]["classification"] == "safe_content_update"
    assert fields["category"]["classification"] == "review_required"
    assert fields["filter_values"]["classification"] == "review_required"
    assert fields["mpn"]["classification"] == "blocked"
    assert fields["status"]["classification"] == "blocked"
    assert fields["price"]["classification"] == "blocked"
    assert fields["active"]["classification"] == "unavailable"

    rollback = plan["rollback_manifest"]
    rollback_fields = {item["field"] for item in rollback["operations"]}
    assert rollback["complete"] is True
    assert rollback["created_before_apply"] is True
    assert rollback["price_stock_status_excluded"] is True
    assert {
        "description",
        "meta_title",
        "meta_description",
        "meta_keywords",
        "category",
        "filter_values",
        "related_products",
        "gallery_image_candidate",
        "seo_keyword_candidate",
        "canonical_url",
    } <= rollback_fields
    assert not {"status", "active", "price", "quantity", "stock_status"} & rollback_fields


def test_plan_hash_binds_generated_timestamp_used_by_review_evidence(
    migration_case: MigrationCase,
) -> None:
    tampered = deepcopy(migration_case.plan)
    tampered["generated_at"] = "2026-07-12T10:00:00Z"

    with pytest.raises(MigrationPlanError, match="content hash"):
        verify_migration_plan(tampered)


def test_apply_live_expectations_include_only_approval_effective_phase2() -> None:
    product_plan = {
        "seo_health_input": {
            "phase2": {
                "description_heading": "Candidate heading",
                "internal_links": {"canonical_category": "/candidate-category"},
            }
        }
    }
    meta_only = migration_execution._live_expected_state(
        current={"model": "123456"},
        patch={"meta_title": "Approved meta"},
        product_plan=product_plan,
        approval={"approved_fields": ["meta_title"]},
    )
    description = migration_execution._live_expected_state(
        current={"model": "123456"},
        patch={"description": "Approved description"},
        product_plan=product_plan,
        approval={"approved_fields": ["description"]},
    )

    assert "description_heading" not in meta_only
    assert "internal_links" not in meta_only
    assert description["description_heading"] == "Candidate heading"
    assert description["internal_links"]["canonical_category"] == (
        "/candidate-category"
    )


def test_slug_is_locked_by_default_redirect_is_generated_and_unapproved_write_blocks(
    migration_case: MigrationCase,
) -> None:
    plan = _allow_apply(migration_case.plan)
    current_slug = _snapshot_product(migration_case.snapshot, "100001")["seo_keyword"]
    slug_field = _field_index(plan, "100001")["seo_keyword_candidate"]

    assert current_slug == "midea-legacy-100001-air-conditioner"
    assert slug_field["classification"] == "review_required"
    assert slug_field["candidate_value"] == "midea-modern-100001-air-conditioner"
    assert plan["redirect_candidates"] == [
        {
            "old_path": "/midea-legacy-100001-air-conditioner",
            "new_path": "/midea-modern-100001-air-conditioner",
            "status_code": 301,
            "model": "100001",
            "approved": False,
            "applied": False,
            "verified": False,
            "reason": "repository_has_no_redirect_applicator; external confirmation required",
        }
    ]
    assert _snapshot_product(migration_case.snapshot, "100001")["seo_keyword"] == current_slug

    publisher = FakePublisher()
    approval = _approval(
        model="100001", approved_fields=["seo_keyword_candidate"]
    )
    with pytest.raises(MigrationApplyError, match="unsupported fields"):
        _apply(
            migration_case,
            plan=plan,
            approval=approval,
            publisher=publisher,
            run_dir=migration_case.root / "unapproved-slug",
        )
    assert publisher.patch_calls == []

    candidates = deepcopy(migration_case.candidates)
    _add_coupled_artifacts(candidates["100001"], model="100001")
    redirect_ready_plan = _allow_apply(
        build_migration_plan(
            snapshot=migration_case.snapshot,
            candidates=candidates,
            run_id=RUN_ID,
            generated_at="2026-07-12T09:05:00Z",
            canary_size=5,
        )
    )
    approved_flag_only = _approval(model="100001", approved_slug_change=True)
    with pytest.raises(MigrationApplyError, match="external applied-and-verified"):
        _apply(
            migration_case,
            plan=redirect_ready_plan,
            approval=approved_flag_only,
            publisher=publisher,
            run_dir=migration_case.root / "unconfirmed-slug",
        )


def test_apply_rejects_missing_flag_wrong_environment_and_stale_state(
    migration_case: MigrationCase,
) -> None:
    plan = _allow_apply(migration_case.plan)
    approval = _approval(model="100001", approved_fields=["meta_title"])
    publisher = FakePublisher()
    target_hash = migration_case.snapshot["metadata"]["catalog_hash"]

    with pytest.raises(MigrationApplyError, match="--apply flag"):
        apply_migration(
            snapshot=migration_case.snapshot,
            plan=plan,
            approval=approval,
            options=_options(apply=False),
            target_content_hash=target_hash,
            run_dir=migration_case.root / "missing-flag",
            publisher=publisher,
        )
    with pytest.raises(MigrationApplyError, match="exactly production"):
        apply_migration(
            snapshot=migration_case.snapshot,
            plan=plan,
            approval=approval,
            options=_options(environment="staging"),
            target_content_hash=target_hash,
            run_dir=migration_case.root / "wrong-environment",
            publisher=publisher,
        )

    stale_plan = deepcopy(plan)
    stale_plan["snapshot_content_hash"] = "sha256:stale"
    stale_plan["plan_hash"] = compute_migration_plan_hash(stale_plan)
    with pytest.raises(MigrationApplyError, match="Snapshot hash no longer matches"):
        _apply(
            migration_case,
            plan=stale_plan,
            approval=approval,
            publisher=publisher,
            run_dir=migration_case.root / "stale-snapshot",
        )
    with pytest.raises(MigrationApplyError, match="Catalog changed after the snapshot"):
        apply_migration(
            snapshot=migration_case.snapshot,
            plan=plan,
            approval=approval,
            options=_options(),
            target_content_hash="sha256:changed",
            run_dir=migration_case.root / "stale-catalog",
            publisher=publisher,
        )
    wrong_target_publisher = FakePublisher(target_identity="opencart-target:other")
    with pytest.raises(MigrationApplyError, match="Resolved OpenCart profile target"):
        _apply(
            migration_case,
            plan=plan,
            approval=approval,
            publisher=wrong_target_publisher,
            run_dir=migration_case.root / "wrong-target",
        )
    assert wrong_target_publisher.preflight_calls == []
    assert publisher.patch_calls == []


def test_rollback_rejects_environment_and_confirmation_before_lock_recovery(
    migration_case: MigrationCase,
) -> None:
    run_dir = migration_case.root / "rollback-flags"
    with pytest.raises(MigrationApplyError, match="exactly production"):
        rollback_migration(
            migration_run_id=RUN_ID,
            environment="staging",
            confirmation=f"ROLLBACK {RUN_ID}",
            run_dir=run_dir,
            current_products={},
            publisher=FakePublisher(),
            target_identity=SOURCE_IDENTITY,
        )
    with pytest.raises(MigrationApplyError, match="must be exactly"):
        rollback_migration(
            migration_run_id=RUN_ID,
            environment="production",
            confirmation="ROLLBACK wrong-run",
            run_dir=run_dir,
            current_products={},
            publisher=FakePublisher(),
            target_identity=SOURCE_IDENTITY,
        )
    assert not (run_dir / "run.active.lock").exists()


def test_apply_writes_only_approved_fields_and_never_protected_columns(
    migration_case: MigrationCase,
) -> None:
    plan = _allow_apply(migration_case.plan)
    approval = _approval(
        model="100001", approved_fields=["meta_title", "filter_values"]
    )
    publisher = FakePublisher()

    run_dir = migration_case.root / "approved-scope"
    result = _apply(
        migration_case,
        plan=plan,
        approval=approval,
        publisher=publisher,
        run_dir=run_dir,
    )

    assert result["status"] == "applied"
    assert len(publisher.patch_calls) == 1
    call = publisher.patch_calls[0]
    assert call["headers"] == ["model", "filter_group:BTU", "meta_title"]
    assert call["row"]["filter_group:BTU"] == "18000"
    assert call["row"]["meta_title"] == "Midea 100001 Modern Air Conditioner | eTranoulis"
    assert not {
        "status",
        "active",
        "price",
        "quantity",
        "stock_status",
        "seo_keyword",
        "product_url",
        "image",
    } & set(call["headers"])

    with pytest.raises(MigrationApplyError, match="Re-apply is forbidden"):
        _apply(
            migration_case,
            plan=plan,
            approval=approval,
            publisher=publisher,
            run_dir=run_dir,
        )
    assert len(publisher.patch_calls) == 1

    with pytest.raises(MigrationApplyError, match="unsupported fields"):
        _apply(
            migration_case,
            plan=plan,
            approval=_approval(model="100001", approved_fields=["identifiers"]),
            publisher=FakePublisher(),
            run_dir=migration_case.root / "identifier-write-forbidden",
        )


def test_canary_scope_requires_reviewed_proposal_and_health_blocker_stops_before_write(
    migration_case: MigrationCase,
) -> None:
    plan = _allow_apply(migration_case.plan)
    proposal = plan["canary_proposal"]
    proposed = set(proposal["proposed_models"])
    all_models = {product["model"] for product in plan["products"]}
    attributes = {
        attribute
        for product in proposal["products"]
        for attribute in product["attributes"]
    }

    assert proposal["operator_approval_required"] is True
    assert len(proposed) == 5
    assert {"active", "inactive", "legacy_image", "descriptive_image"} <= attributes
    assert {"with_gtin", "without_gtin"} <= attributes
    outside = (all_models - proposed).pop()
    publisher = FakePublisher()
    with pytest.raises(MigrationApplyError, match="outside the reviewed proposal"):
        _apply(
            migration_case,
            plan=plan,
            approval=_approval(model=outside, approved_fields=["meta_title"]),
            publisher=publisher,
            run_dir=migration_case.root / "canary-scope",
            canary=True,
        )

    blocked_plan = deepcopy(plan)
    blocked_model = sorted(proposed)[0]
    product = next(
        item for item in blocked_plan["products"] if item["model"] == blocked_model
    )
    next(
        field for field in product["fields"] if field["field"] == "meta_title"
    )["candidate_value"] = ""
    blocked_plan["plan_hash"] = compute_migration_plan_hash(blocked_plan)
    with pytest.raises(MigrationApplyError, match="Approval-effective preflight SEO health"):
        _apply(
            migration_case,
            plan=blocked_plan,
            approval=_approval(model=blocked_model, approved_fields=["meta_title"]),
            publisher=publisher,
            run_dir=migration_case.root / "health-blocker",
            canary=True,
        )
    assert publisher.patch_calls == []


def test_category_apply_rejects_unattested_autocreation_target(
    migration_case: MigrationCase,
) -> None:
    plan = _allow_apply(migration_case.plan)
    publisher = FakePublisher()

    with pytest.raises(MigrationApplyError, match="auto-creation is forbidden"):
        _apply(
            migration_case,
            plan=plan,
            approval=_approval(model="100001", approved_fields=["category"]),
            publisher=publisher,
            run_dir=migration_case.root / "new-category-forbidden",
        )

    assert publisher.patch_calls == []


def test_apply_rejects_reviewed_candidate_blocking_health(
    migration_case: MigrationCase,
) -> None:
    plan = _allow_apply(migration_case.plan)
    product = next(item for item in plan["products"] if item["model"] == "100001")
    product["seo_health_after"]["summary"]["blocking_failures"] = 1
    plan["plan_hash"] = compute_migration_plan_hash(plan)
    publisher = FakePublisher()

    with pytest.raises(MigrationApplyError, match="candidate SEO health.*blocking"):
        _apply(
            migration_case,
            plan=plan,
            approval=_approval(model="100001", approved_fields=["meta_title"]),
            publisher=publisher,
            run_dir=migration_case.root / "candidate-health-blocked",
        )

    assert publisher.patch_calls == []


@pytest.mark.parametrize(
    "publisher_factory,expected_confirmation",
    [
        (UnknownAfterTriggerPublisher, "state_unknown"),
        (UnsafeCounterPublisher, "confirmed"),
    ],
)
def test_uncertain_or_counter_failed_import_remains_rollback_eligible(
    migration_case: MigrationCase,
    publisher_factory: type[FakePublisher],
    expected_confirmation: str,
) -> None:
    model = "100001"
    plan = _allow_apply(migration_case.plan)
    approval = _approval(model=model, approved_fields=["meta_title"])
    run_dir = migration_case.root / f"uncertain-{expected_confirmation}"

    with pytest.raises(MigrationApplyError):
        _apply(
            migration_case,
            plan=plan,
            approval=approval,
            publisher=publisher_factory(),
            run_dir=run_dir,
        )

    manifest = json.loads(
        (run_dir / "rollback_manifest.json").read_text(encoding="utf-8")
    )
    operation = next(
        item
        for item in manifest["operations"]
        if item["model"] == model and item["field"] == "meta_title"
    )
    assert operation["write_attempted"] is True
    assert operation["apply_confirmation"] == expected_confirmation

    current_after = deepcopy(_snapshot_product(migration_case.snapshot, model))
    current_after["meta_title"] = _field_index(plan, model)["meta_title"][
        "candidate_value"
    ]
    rollback_publisher = FakePublisher()
    result = rollback_migration(
        migration_run_id=RUN_ID,
        environment="production",
        confirmation=f"ROLLBACK {RUN_ID}",
        run_dir=run_dir,
        current_products={model: current_after},
        publisher=rollback_publisher,
        target_identity=SOURCE_IDENTITY,
    )
    assert result["status"] == "rolled_back"
    assert rollback_publisher.patch_calls[-1]["row"]["meta_title"] == (
        _snapshot_product(migration_case.snapshot, model)["meta_title"]
    )


def test_stopped_rollout_does_not_issue_later_model_authorizations(
    migration_case: MigrationCase,
) -> None:
    plan = _allow_apply(migration_case.plan)
    approval = validate_approval_manifest(
        {
            "schema_version": "1.0",
            "snapshot_id": SNAPSHOT_ID,
            "migration_run_id": RUN_ID,
            "approved_by": "phase4-test-operator",
            "approved_at": "2026-07-12T09:10:00Z",
            "products": [
                {
                    "model": model,
                    "approved_fields": ["meta_title"],
                    "approved_slug_change": False,
                    "approved_image_path_change": False,
                    "notes": "two-model authorization expiry fixture",
                }
                for model in ("100001", "100002")
            ],
        },
        snapshot_id=SNAPSHOT_ID,
        migration_run_id=RUN_ID,
    )
    run_dir = migration_case.root / "stopped-authorization-scope"

    with pytest.raises(MigrationApplyError):
        _apply(
            migration_case,
            plan=plan,
            approval=approval,
            publisher=UnknownAfterTriggerPublisher(),
            run_dir=run_dir,
        )

    assert (run_dir / "apply" / "authorizations" / "100001.json").is_file()
    assert not (run_dir / "apply" / "authorizations" / "100002.json").exists()


def test_crash_state_rollback_ignores_mutable_rolled_back_flag_and_recovers_lock(
    migration_case: MigrationCase,
) -> None:
    model = "100001"
    plan = _allow_apply(migration_case.plan)
    run_dir = migration_case.root / "crash-recovery"
    _apply(
        migration_case,
        plan=plan,
        approval=_approval(model=model, approved_fields=["meta_title"]),
        publisher=FakePublisher(),
        run_dir=run_dir,
    )
    apply_result_path = run_dir / "apply_result.json"
    apply_result = json.loads(apply_result_path.read_text(encoding="utf-8"))
    apply_result["status"] = "running"
    _write_json(apply_result_path, apply_result)
    rollback_path = run_dir / "rollback_manifest.json"
    rollback = json.loads(rollback_path.read_text(encoding="utf-8"))
    operation = next(
        item
        for item in rollback["operations"]
        if item["model"] == model and item["field"] == "meta_title"
    )
    operation["rolled_back"] = True
    _write_json(rollback_path, rollback)
    _write_json(
        run_dir / "run.active.lock",
        {
            "schema_version": "1.0",
            "operation": "apply",
            "acquired_at": datetime.now(timezone.utc).isoformat(),
            "owner_pid": 99_999_999,
            "host_id": migration_execution._lock_host_id(),
            "run_path_hash": migration_execution._content_hash(str(run_dir.resolve())),
        },
    )
    current_after = deepcopy(_snapshot_product(migration_case.snapshot, model))
    current_after["meta_title"] = _field_index(plan, model)["meta_title"][
        "candidate_value"
    ]
    publisher = FakePublisher()

    result = rollback_migration(
        migration_run_id=RUN_ID,
        environment="production",
        confirmation=f"ROLLBACK {RUN_ID}",
        run_dir=run_dir,
        current_products={model: current_after},
        publisher=publisher,
        target_identity=SOURCE_IDENTITY,
    )

    assert result["status"] == "rolled_back"
    assert publisher.patch_calls[-1]["row"]["meta_title"] == (
        _snapshot_product(migration_case.snapshot, model)["meta_title"]
    )
    assert list((run_dir / "recovery" / "stale-locks").glob("*.json"))


def test_approved_image_change_requires_reviewed_source_hash(
    migration_case: MigrationCase,
) -> None:
    model = "100001"
    candidates = deepcopy(migration_case.candidates)
    _add_coupled_artifacts(candidates[model], model=model)
    current = _snapshot_product(migration_case.snapshot, model)
    plan = _allow_apply(
        build_migration_plan(
            snapshot=migration_case.snapshot,
            candidates=candidates,
            run_id=RUN_ID,
            generated_at="2026-07-12T09:05:00Z",
            canary_size=5,
        )
    )
    image_root = migration_case.root / "unreviewed-image-root"
    original = image_root / current["main_image"]
    original.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), "white").save(original, format="JPEG")

    with pytest.raises(MigrationApplyError, match="reviewed SHA-256"):
        apply_migration(
            snapshot=migration_case.snapshot,
            plan=plan,
            approval=_approval(model=model, approved_image_path_change=True),
            options=_options(),
            target_content_hash=migration_case.snapshot["metadata"]["catalog_hash"],
            publisher=FakePublisher(),
            run_dir=migration_case.root / "unreviewed-image-apply",
            image_root=image_root,
            live_validator=_passing_live_validator,
        )


def test_approved_image_change_copies_jpg_switches_references_and_retains_original(
    migration_case: MigrationCase,
) -> None:
    model = "100001"
    candidates = deepcopy(migration_case.candidates)
    _add_coupled_artifacts(candidates[model], model=model)
    current = _snapshot_product(migration_case.snapshot, model)
    image_root = migration_case.root / "image-root"
    original = image_root / current["main_image"]
    original.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), "white").save(original, format="JPEG")
    for reference in current["additional_images"]:
        gallery_source = image_root / reference
        gallery_source.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 8), "white").save(gallery_source, format="JPEG")
    plan = _allow_apply(
        build_migration_plan(
            snapshot=migration_case.snapshot,
            candidates=candidates,
            run_id=RUN_ID,
            generated_at="2026-07-12T09:05:00Z",
            canary_size=5,
            image_root=image_root,
        )
    )
    assert next(
        item
        for item in plan["image_candidates"]
        if item["model"] == model and item["position"] == 1
    )["source_hash"].startswith("sha256:")
    publisher = FakePublisher()

    result = apply_migration(
        snapshot=migration_case.snapshot,
        plan=plan,
        approval=_approval(model=model, approved_image_path_change=True),
        options=_options(),
        target_content_hash=migration_case.snapshot["metadata"]["catalog_hash"],
        publisher=publisher,
        run_dir=migration_case.root / "image-apply",
        image_root=image_root,
        live_validator=_passing_live_validator,
    )

    target_ref = "catalog/01_main/100001/midea-modern-100001-1.jpg"
    target = image_root / target_ref
    assert result["status"] == "applied"
    assert original.is_file()
    assert target.is_file()
    assert original.read_bytes() == target.read_bytes()
    assert publisher.image_calls[0]["operations"][0]["original_retained"] is True
    authorized_operations = publisher.image_calls[0]["operations"]
    authorized_hash = hashlib.sha256(
        json.dumps(
            authorized_operations,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    assert (
        publisher.image_calls[0]["authorization"]["image_operations_hash"]
        == authorized_hash
    )
    assert all("copy_confirmed" not in operation for operation in authorized_operations)
    patch = publisher.patch_calls[0]
    assert patch["row"]["image"] == target_ref
    assert patch["row"]["additional_image"] == current["additional_images"][0]
    assert target_ref in patch["row"]["description"]
    assert "besco1.jpg" in patch["row"]["description"]
    structured = json.loads(
        (
            migration_case.root
            / "image-apply"
            / "apply"
            / "artifacts"
            / model
            / "structured_data_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert target_ref in structured["image"][0]
    assert not {"price", "quantity", "status", "stock_status", "active"} & set(
        patch["headers"]
    )


def test_approved_description_and_image_compose_and_rollback_together(
    migration_case: MigrationCase,
) -> None:
    model = "100001"
    candidates = deepcopy(migration_case.candidates)
    current = _snapshot_product(migration_case.snapshot, model)
    _add_coupled_artifacts(candidates[model], model=model)
    candidates[model]["values"]["description"] = current["description"].replace(
        "verified air conditioner description",
        "approved updated air conditioner description",
    )
    image_root = migration_case.root / "combined-image-root"
    original_image = image_root / current["main_image"]
    original_image.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), "white").save(original_image, format="JPEG")
    for reference in current["additional_images"]:
        gallery_source = image_root / reference
        gallery_source.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 8), "white").save(gallery_source, format="JPEG")
    plan = _allow_apply(
        build_migration_plan(
            snapshot=migration_case.snapshot,
            candidates=candidates,
            run_id=RUN_ID,
            generated_at="2026-07-12T09:05:00Z",
            canary_size=5,
            image_root=image_root,
        )
    )
    publisher = FakePublisher()
    run_dir = migration_case.root / "combined-description-image"

    apply_migration(
        snapshot=migration_case.snapshot,
        plan=plan,
        approval=_approval(
            model=model,
            approved_fields=["description"],
            approved_image_path_change=True,
        ),
        options=_options(),
        target_content_hash=migration_case.snapshot["metadata"]["catalog_hash"],
        run_dir=run_dir,
        publisher=publisher,
        image_root=image_root,
        live_validator=_passing_live_validator,
    )

    applied = publisher.patch_calls[-1]["row"]
    assert "approved updated air conditioner description" in applied["description"]
    assert "midea-modern-100001-1.jpg" in applied["description"]
    assert "besco1.jpg" in applied["description"]
    current_after = deepcopy(current)
    current_after["description"] = applied["description"]
    current_after["main_image"] = applied["image"]
    current_after["additional_images"] = [
        item for item in applied["additional_image"].split(":::") if item
    ]

    rollback_migration(
        migration_run_id=RUN_ID,
        environment="production",
        confirmation=f"ROLLBACK {RUN_ID}",
        run_dir=run_dir,
        current_products={model: current_after},
        publisher=publisher,
        target_identity=SOURCE_IDENTITY,
    )

    restored = publisher.patch_calls[-1]["row"]
    assert restored["description"] == current["description"]
    assert restored["image"] == current["main_image"]


def test_rollback_verifies_current_state_then_restores_metadata_and_filters(
    migration_case: MigrationCase,
) -> None:
    plan = _allow_apply(migration_case.plan)
    model = "100001"
    approval = _approval(
        model=model, approved_fields=["meta_title", "filter_values"]
    )
    publisher = FakePublisher()
    run_dir = migration_case.root / "rollback-run"
    _apply(
        migration_case,
        plan=plan,
        approval=approval,
        publisher=publisher,
        run_dir=run_dir,
    )

    rollback_path = run_dir / "rollback_manifest.json"
    original_manifest = json.loads(rollback_path.read_text(encoding="utf-8"))
    tampered_manifest = deepcopy(original_manifest)
    next(
        item
        for item in tampered_manifest["operations"]
        if item["model"] == model and item["field"] == "meta_title"
    )["restore_value"] = "Tampered rollback value"
    _write_json(rollback_path, tampered_manifest)
    with pytest.raises(MigrationApplyError, match="operation hash no longer matches"):
        rollback_migration(
            migration_run_id=RUN_ID,
            environment="production",
            confirmation=f"ROLLBACK {RUN_ID}",
            run_dir=run_dir,
            current_products={model: _snapshot_product(migration_case.snapshot, model)},
            publisher=publisher,
            target_identity=SOURCE_IDENTITY,
        )
    _write_json(rollback_path, original_manifest)

    scope_attack = deepcopy(original_manifest)
    description_operation = next(
        item
        for item in scope_attack["operations"]
        if item["model"] == model and item["field"] == "description"
    )
    description_operation["write_attempted"] = True
    description_operation["apply_confirmation"] = "state_unknown"
    description_operation["effective_expected_applied_value"] = (
        description_operation["restore_value"]
    )
    _write_json(rollback_path, scope_attack)
    with pytest.raises(MigrationApplyError, match="outside the approved apply scope"):
        rollback_migration(
            migration_run_id=RUN_ID,
            environment="production",
            confirmation=f"ROLLBACK {RUN_ID}",
            run_dir=run_dir,
            current_products={model: _snapshot_product(migration_case.snapshot, model)},
            publisher=publisher,
            target_identity=SOURCE_IDENTITY,
        )
    _write_json(rollback_path, original_manifest)

    expected_state_attack = deepcopy(original_manifest)
    next(
        item
        for item in expected_state_attack["operations"]
        if item["model"] == model and item["field"] == "meta_title"
    )["effective_expected_applied_value"] = "Attacker-selected current value"
    _write_json(rollback_path, expected_state_attack)
    with pytest.raises(MigrationApplyError, match="expected-state checkpoint changed"):
        rollback_migration(
            migration_run_id=RUN_ID,
            environment="production",
            confirmation=f"ROLLBACK {RUN_ID}",
            run_dir=run_dir,
            current_products={
                model: {
                    **_snapshot_product(migration_case.snapshot, model),
                    "meta_title": "Attacker-selected current value",
                }
            },
            publisher=publisher,
            target_identity=SOURCE_IDENTITY,
        )
    _write_json(rollback_path, original_manifest)

    fields = _field_index(plan, model)
    current_after = deepcopy(_snapshot_product(migration_case.snapshot, model))
    current_after["meta_title"] = fields["meta_title"]["candidate_value"]
    current_after["filters"] = fields["filter_values"]["candidate_value"]
    mismatched = deepcopy(current_after)
    mismatched["meta_title"] = "Manual edit after migration"

    with pytest.raises(MigrationApplyError, match="current-state verification failed"):
        rollback_migration(
            migration_run_id=RUN_ID,
            environment="production",
            confirmation=f"ROLLBACK {RUN_ID}",
            run_dir=run_dir,
            current_products={model: mismatched},
            publisher=publisher,
            target_identity=SOURCE_IDENTITY,
        )
    assert len(publisher.patch_calls) == 1

    result = rollback_migration(
        migration_run_id=RUN_ID,
        environment="production",
        confirmation=f"ROLLBACK {RUN_ID}",
        run_dir=run_dir,
        current_products={model: current_after},
        publisher=publisher,
        target_identity=SOURCE_IDENTITY,
    )

    assert result["status"] == "rolled_back"
    assert result["price_stock_status_excluded"] is True
    rollback_call = publisher.patch_calls[-1]
    original = _snapshot_product(migration_case.snapshot, model)
    assert rollback_call["headers"] == ["model", "filter_group:BTU", "meta_title"]
    assert rollback_call["row"]["filter_group:BTU"] == "12000"
    assert rollback_call["row"]["meta_title"] == original["meta_title"]
    assert not {"price", "quantity", "status", "stock_status", "active"} & set(
        rollback_call["headers"]
    )
    persisted = json.loads((run_dir / "rollback_manifest.json").read_text(encoding="utf-8"))
    selected = [
        item
        for item in persisted["operations"]
        if item["model"] == model and item["field"] in {"meta_title", "filter_values"}
    ]
    assert selected and all(item["rolled_back"] is True for item in selected)


def test_slug_rollback_restores_coupled_structured_and_feed_artifacts(
    migration_case: MigrationCase,
) -> None:
    model = "100001"
    candidates = deepcopy(migration_case.candidates)
    candidate = candidates[model]
    candidate["values"]["structured_data_manifest"] = {
        "@type": "Product",
        "url": "https://www.etranoulis.gr/midea-modern-100001-air-conditioner",
    }
    candidate["values"]["product_feed_manifest"] = {
        "id": model,
        "link": "https://www.etranoulis.gr/midea-modern-100001-air-conditioner",
    }
    candidate["available_fields"] = sorted(
        {
            *candidate.get("available_fields", []),
            "structured_data_manifest",
            "product_feed_manifest",
        }
    )
    plan = _allow_apply(
        build_migration_plan(
            snapshot=migration_case.snapshot,
            candidates=candidates,
            run_id=RUN_ID,
            generated_at="2026-07-12T09:05:00Z",
            canary_size=5,
        )
    )
    current = _snapshot_product(migration_case.snapshot, model)
    new_slug = _field_index(plan, model)["seo_keyword_candidate"]["candidate_value"]
    old_slug = current["seo_keyword"]
    run_dir = migration_case.root / "slug-artifact-rollback"
    publisher = FakePublisher()
    live_expected: dict[str, Any] = {}

    def live_validator(*, model: str, expected: Mapping[str, Any]) -> dict[str, Any]:
        live_expected.update(expected)
        return {
            "model": model,
            "status": "not_run",
            "reason": "fixture_live_access_unavailable",
            "checks": [],
        }

    apply_migration(
        snapshot=migration_case.snapshot,
        plan=plan,
        approval=_approval(model=model, approved_slug_change=True),
        options=_options(),
        target_content_hash=migration_case.snapshot["metadata"]["catalog_hash"],
        run_dir=run_dir,
        publisher=publisher,
        live_validator=live_validator,
        redirect_confirmation=_redirect_confirmation(
            model=model,
            old_path=f"/{old_slug}",
            new_path=f"/{new_slug}",
            plan_hash=plan["plan_hash"],
        ),
    )

    structured_path = (
        run_dir / "apply" / "artifacts" / model / "structured_data_manifest.json"
    )
    assert json.loads(structured_path.read_text(encoding="utf-8"))["url"].endswith(
        new_slug
    )
    assert live_expected["canonical_url"].endswith(new_slug)
    current_after = deepcopy(current)
    current_after["seo_keyword"] = new_slug
    current_after["canonical_url"] = f"https://www.etranoulis.gr/{new_slug}"
    rollback_migration(
        migration_run_id=RUN_ID,
        environment="production",
        confirmation=f"ROLLBACK {RUN_ID}",
        run_dir=run_dir,
        current_products={model: current_after},
        publisher=publisher,
        target_identity=SOURCE_IDENTITY,
        redirect_confirmation=_redirect_confirmation(
            model=model,
            old_path=f"/{new_slug}",
            new_path=f"/{old_slug}",
            remove_forward=True,
            plan_hash=plan["plan_hash"],
        ),
    )

    restored = json.loads(structured_path.read_text(encoding="utf-8"))
    assert restored["url"].endswith(old_slug)
    assert (
        run_dir
        / "rollback"
        / "artifacts"
        / model
        / "product_feed_manifest.json"
    ).is_file()


def test_failed_slug_preflight_retains_external_redirect_cleanup_rollback(
    migration_case: MigrationCase,
) -> None:
    model = "100001"
    candidates = deepcopy(migration_case.candidates)
    _add_coupled_artifacts(candidates[model], model=model)
    plan = _allow_apply(
        build_migration_plan(
            snapshot=migration_case.snapshot,
            candidates=candidates,
            run_id=RUN_ID,
            generated_at="2026-07-12T09:05:00Z",
            canary_size=5,
        )
    )
    current = _snapshot_product(migration_case.snapshot, model)
    old_slug = current["seo_keyword"]
    new_slug = _field_index(plan, model)["seo_keyword_candidate"]["candidate_value"]
    run_dir = migration_case.root / "slug-preflight-cleanup"

    with pytest.raises(MigrationApplyError, match="preflight"):
        apply_migration(
            snapshot=migration_case.snapshot,
            plan=plan,
            approval=_approval(model=model, approved_slug_change=True),
            options=_options(),
            target_content_hash=migration_case.snapshot["metadata"]["catalog_hash"],
            run_dir=run_dir,
            publisher=FailingPreflightPublisher(),
            redirect_confirmation=_redirect_confirmation(
                model=model,
                old_path=f"/{old_slug}",
                new_path=f"/{new_slug}",
                plan_hash=plan["plan_hash"],
            ),
        )

    assert not (run_dir / "apply.claim.json").exists()
    cleanup = json.loads(
        (run_dir / "redirect_cleanup_required.json").read_text(encoding="utf-8")
    )
    assert cleanup["redirects"][0]["old_path"] == f"/{old_slug}"
    audit_path = run_dir / "audit.jsonl"
    audit_lines = [
        line
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("event") != "external_redirect_preconfirmed"
    ]
    audit_path.write_text("\n".join(audit_lines) + "\n", encoding="utf-8")
    rollback_publisher = FakePublisher()
    result = rollback_migration(
        migration_run_id=RUN_ID,
        environment="production",
        confirmation=f"ROLLBACK {RUN_ID}",
        run_dir=run_dir,
        current_products={model: current},
        publisher=rollback_publisher,
        target_identity=SOURCE_IDENTITY,
        redirect_confirmation=_redirect_confirmation(
            model=model,
            old_path=f"/{new_slug}",
            new_path=f"/{old_slug}",
            remove_forward=True,
            plan_hash=plan["plan_hash"],
        ),
    )

    assert result["status"] == "rolled_back"
    assert result["products"][0]["status"] == "resolved_noop"
    assert rollback_publisher.patch_calls == []


def test_slug_redirect_cleanup_is_recorded_before_health_gate_failure(
    migration_case: MigrationCase,
) -> None:
    model = "100001"
    candidates = deepcopy(migration_case.candidates)
    _add_coupled_artifacts(candidates[model], model=model)
    plan = _allow_apply(
        build_migration_plan(
            snapshot=migration_case.snapshot,
            candidates=candidates,
            run_id=RUN_ID,
            generated_at="2026-07-12T09:05:00Z",
            canary_size=5,
        )
    )
    product = next(item for item in plan["products"] if item["model"] == model)
    product["seo_health_after"]["summary"]["blocking_failures"] = 1
    plan["plan_hash"] = compute_migration_plan_hash(plan)
    old_slug = _snapshot_product(migration_case.snapshot, model)["seo_keyword"]
    new_slug = _field_index(plan, model)["seo_keyword_candidate"]["candidate_value"]
    run_dir = migration_case.root / "slug-health-cleanup"

    with pytest.raises(MigrationApplyError, match="candidate SEO health"):
        apply_migration(
            snapshot=migration_case.snapshot,
            plan=plan,
            approval=_approval(model=model, approved_slug_change=True),
            options=_options(),
            target_content_hash=migration_case.snapshot["metadata"]["catalog_hash"],
            run_dir=run_dir,
            publisher=FakePublisher(),
            redirect_confirmation=_redirect_confirmation(
                model=model,
                old_path=f"/{old_slug}",
                new_path=f"/{new_slug}",
                plan_hash=plan["plan_hash"],
            ),
        )

    assert (run_dir / "redirect_cleanup_required.json").is_file()
    assert not (run_dir / "apply.claim.json").exists()


def test_slug_redirect_rejects_stale_global_namespace_evidence(
    migration_case: MigrationCase,
) -> None:
    model = "100001"
    candidates = deepcopy(migration_case.candidates)
    _add_coupled_artifacts(candidates[model], model=model)
    plan = _allow_apply(
        build_migration_plan(
            snapshot=migration_case.snapshot,
            candidates=candidates,
            run_id=RUN_ID,
            generated_at="2026-07-12T09:05:00Z",
            canary_size=5,
        )
    )
    old_slug = _snapshot_product(migration_case.snapshot, model)["seo_keyword"]
    new_slug = _field_index(plan, model)["seo_keyword_candidate"]["candidate_value"]
    confirmation = _redirect_confirmation(
        model=model,
        old_path=f"/{old_slug}",
        new_path=f"/{new_slug}",
        plan_hash=plan["plan_hash"],
    )
    confirmation["seo_url_namespace"]["captured_at"] = (
        datetime.now(timezone.utc) - timedelta(days=2)
    ).isoformat()

    with pytest.raises(MigrationApplyError, match="namespace evidence is stale"):
        apply_migration(
            snapshot=migration_case.snapshot,
            plan=plan,
            approval=_approval(model=model, approved_slug_change=True),
            options=_options(),
            target_content_hash=migration_case.snapshot["metadata"]["catalog_hash"],
            run_dir=migration_case.root / "stale-redirect-namespace",
            publisher=FakePublisher(),
            redirect_confirmation=confirmation,
        )


def test_slug_redirect_evidence_cannot_predate_reviewed_plan(
    migration_case: MigrationCase,
) -> None:
    model = "100001"
    now = datetime.now(timezone.utc)
    candidates = deepcopy(migration_case.candidates)
    _add_coupled_artifacts(candidates[model], model=model)
    plan = _allow_apply(
        build_migration_plan(
            snapshot=migration_case.snapshot,
            candidates=candidates,
            run_id=RUN_ID,
            generated_at=(now - timedelta(minutes=30)).isoformat(),
            canary_size=5,
        )
    )
    approval = validate_approval_manifest(
        {
            "schema_version": "1.0",
            "snapshot_id": SNAPSHOT_ID,
            "migration_run_id": RUN_ID,
            "approved_by": "phase4-test-operator",
            "approved_at": (now - timedelta(hours=2)).isoformat(),
            "products": [
                {
                    "model": model,
                    "approved_fields": [],
                    "approved_slug_change": True,
                    "approved_image_path_change": False,
                    "notes": "redirect must follow the reviewed plan",
                }
            ],
        },
        snapshot_id=SNAPSHOT_ID,
        migration_run_id=RUN_ID,
    )
    old_slug = _snapshot_product(migration_case.snapshot, model)["seo_keyword"]
    new_slug = _field_index(plan, model)["seo_keyword_candidate"]["candidate_value"]
    confirmation = _redirect_confirmation(
        model=model,
        old_path=f"/{old_slug}",
        new_path=f"/{new_slug}",
        plan_hash=plan["plan_hash"],
    )
    before_plan = (now - timedelta(hours=1)).isoformat()
    confirmation["confirmed_at"] = before_plan
    confirmation["seo_url_namespace"]["captured_at"] = before_plan

    with pytest.raises(MigrationApplyError, match="predates the run gate"):
        apply_migration(
            snapshot=migration_case.snapshot,
            plan=plan,
            approval=approval,
            options=_options(),
            target_content_hash=migration_case.snapshot["metadata"]["catalog_hash"],
            run_dir=migration_case.root / "redirect-predates-plan",
            publisher=FakePublisher(),
            redirect_confirmation=confirmation,
        )


def _snapshot_row(index: int) -> dict[str, str]:
    model = f"{100000 + index:06d}"
    main_image = (
        f"catalog/01_main/{model}/{model}-1.jpg"
        if index <= 3
        else f"catalog/01_main/{model}/midea-series-{model}-1.jpg"
    )
    additional = f"catalog/01_main/{model}/{model}-2.jpg"
    slug = f"midea-legacy-{model}-air-conditioner"
    identifier = f"520{model}0000" if index % 2 else ""
    status = "1" if index % 2 else "0"
    return {
        "model": model,
        "product_id": str(5000 + index),
        "status": status,
        "active": "true" if status == "1" else "false",
        "name": f"Midea Legacy {model} Air Conditioner 12000 BTU",
        "description": (
            f'<p>Midea {model} verified air conditioner description for migration.</p>'
            f'<img src="/image/{main_image}">'
            f'<img src="/image/catalog/01_bescos/{model}/besco1.jpg">'
        ),
        "meta_title": f"Midea {model} Air Conditioner | eTranoulis",
        "meta_description": (
            f"Midea {model} air conditioner with verified 12000 BTU specifications "
            "for efficient cooling and dependable everyday comfort in the home."
        ),
        "meta_keywords": f"Midea, {model}, air conditioner",
        "seo_keyword": slug,
        "canonical_url": f"https://www.etranoulis.gr/{slug}",
        "mpn": f"MPN-{model}",
        "ean": identifier,
        "gtin": identifier,
        "upc": "",
        "jan": "",
        "isbn": "",
        "main_image": main_image,
        "additional_images": additional,
        "category": "Climate///Air Conditioners",
        "filter_group:BTU": "18000" if index == 2 else "12000",
        "manufacturer": "Midea",
        "related_products": "100010,100011",
        "price": "799.00",
        "quantity": "2",
        "stock_status": "In stock",
        "date_added": "2025-01-01T00:00:00Z",
        "last_modified": "2026-07-12T08:00:00Z",
    }


def _candidate_row(index: int) -> dict[str, str]:
    current = _snapshot_row(index)
    model = current["model"]
    if index == 1:
        return {
            "model": model,
            "mpn": "CONFLICTING-MPN",
            "ean": current["ean"],
            "gtin": current["gtin"],
            "upc": "",
            "jan": "",
            "isbn": "",
            "name": current["name"],
            "description": f"Updated verified description for Midea {model}.",
            "category": "Climate///Cooling",
            "filter_group:BTU": "18000",
            "image": f"catalog/01_main/{model}/midea-modern-{model}-1.jpg",
            "additional_image": current["additional_images"],
            "manufacturer": "Midea Updated",
            "price": "1.00",
            "quantity": "0",
            "stock_status": "Backorder",
            "status": "0",
            "meta_keyword": f"Midea, modern, {model}",
            "meta_title": f"Midea {model} Modern Air Conditioner | eTranoulis",
            "meta_description": f"Updated metadata for Midea {model} air conditioner.",
            "seo_keyword": f"midea-modern-{model}-air-conditioner",
            "product_url": f"https://www.etranoulis.gr/midea-modern-{model}-air-conditioner",
            "related_product": "100012,100013",
        }
    candidate = {
        "model": model,
        "mpn": current["mpn"],
        "ean": current["ean"],
        "gtin": current["gtin"],
        "upc": "",
        "jan": "",
        "isbn": "",
        "name": current["name"],
        "description": current["description"],
        "category": current["category"],
        "filter_group:BTU": current["filter_group:BTU"],
        "image": current["main_image"],
        "additional_image": current["additional_images"],
        "manufacturer": current["manufacturer"],
        "price": current["price"],
        "quantity": current["quantity"],
        "stock_status": current["stock_status"],
        "status": current["status"],
        "meta_keyword": current["meta_keywords"],
        "meta_title": f"Midea {model} Updated Air Conditioner | eTranoulis",
        "meta_description": current["meta_description"],
        "seo_keyword": current["seo_keyword"],
        "product_url": current["canonical_url"],
        "related_product": current["related_products"],
    }
    return candidate


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _field_index(plan: Mapping[str, Any], model: str) -> dict[str, dict[str, Any]]:
    product = next(item for item in plan["products"] if item["model"] == model)
    return {item["field"]: item for item in product["fields"]}


def _snapshot_product(snapshot: Mapping[str, Any], model: str) -> dict[str, Any]:
    return dict(next(item for item in snapshot["products"] if item["model"] == model))


def _allow_apply(plan: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(plan))
    for product in result["products"]:
        fields = {
            str(item["field"]): item
            for item in product["fields"]
            if isinstance(item, Mapping)
        }
        current_slug = str(fields["seo_keyword_candidate"]["current_value"])
        product["seo_health_input"]["deterministic_product"] = {
            "brand": "Midea",
            "mpn": str(fields["mpn"]["current_value"]),
            "category_phrase": "Air Conditioner",
            "published_seo_keyword": current_slug,
            "seo_keyword_candidate": str(
                fields["seo_keyword_candidate"]["candidate_value"]
            ),
            "seo_identity": {"primary_model": product["model"]},
        }
        product["seo_health_after"]["summary"]["blocking_failures"] = 0
    result["summary"]["blocking_seo_health_failures"] = 0
    result["plan_hash"] = compute_migration_plan_hash(result)
    return result


def _approval(
    *,
    model: str,
    approved_fields: list[str] | None = None,
    approved_slug_change: bool = False,
    approved_image_path_change: bool = False,
) -> dict[str, Any]:
    payload = {
        "schema_version": "1.0",
        "snapshot_id": SNAPSHOT_ID,
        "migration_run_id": RUN_ID,
        "approved_by": "phase4-test-operator",
        "approved_at": "2026-07-12T09:10:00Z",
        "products": [
            {
                "model": model,
                "approved_fields": list(approved_fields or []),
                "approved_slug_change": approved_slug_change,
                "approved_image_path_change": approved_image_path_change,
                "notes": "isolated fixture approval",
            }
        ],
    }
    return validate_approval_manifest(
        payload, snapshot_id=SNAPSHOT_ID, migration_run_id=RUN_ID
    )


def _redirect_confirmation(
    *,
    model: str,
    old_path: str,
    new_path: str,
    remove_forward: bool = False,
    plan_hash: str,
) -> dict[str, Any]:
    confirmed_at = datetime.now(timezone.utc)
    captured_at = confirmed_at
    paths = [old_path]
    namespace_material = json.dumps(
        {"paths": sorted(paths)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": "1.0",
        "environment": "production",
        "target_identity": SOURCE_IDENTITY,
        "migration_run_id": RUN_ID,
        "snapshot_id": SNAPSHOT_ID,
        "plan_hash": plan_hash,
        "responsible_system": "fixture-redirect-owner",
        "confirmed_by": "phase4-test-operator",
        "confirmed_at": confirmed_at.isoformat(),
        "redirects": [
            {
                "old_path": old_path,
                "new_path": new_path,
                "status_code": 301,
                "model": model,
                "approved": True,
                "applied": True,
                "verified": True,
            }
        ],
        "removed_redirects": (
            [
                {
                    "old_path": new_path,
                    "new_path": old_path,
                    "status_code": 301,
                    "model": model,
                    "removed": True,
                    "verified": True,
                }
            ]
            if remove_forward
            else []
        ),
        "seo_url_namespace": {
            "schema_version": "1.0",
            "source_identity": "fixture-global-seo-url-export",
            "target_identity": SOURCE_IDENTITY,
            "migration_run_id": RUN_ID,
            "snapshot_id": SNAPSHOT_ID,
            "plan_hash": plan_hash,
            "captured_at": captured_at.isoformat(),
            "complete": True,
            "row_count": len(paths),
            "content_hash": (
                "sha256:" + hashlib.sha256(namespace_material).hexdigest()
            ),
            "paths": paths,
        },
    }


def _add_coupled_artifacts(candidate: dict[str, Any], *, model: str) -> None:
    candidate["values"]["structured_data_manifest"] = {
        "@type": "Product",
        "url": f"https://www.etranoulis.gr/{candidate['values']['seo_keyword']}",
        "image": [
            f"https://www.etranoulis.gr/image/{candidate['values']['main_image']}"
        ],
    }
    candidate["values"]["product_feed_manifest"] = {
        "id": model,
        "link": f"https://www.etranoulis.gr/{candidate['values']['seo_keyword']}",
        "image_link": (
            f"https://www.etranoulis.gr/image/{candidate['values']['main_image']}"
        ),
        "additional_image_links": [],
    }


def _passing_live_validator(*, model: str, expected: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "live.http_success",
        "live.final_url",
        "live.canonical_url",
        "live.main_image",
        "live.gallery_order",
        "live.description_images",
        "live.product_structured_data",
    }
    return {
        "model": model,
        "status": "pass",
        "coverage": {"percentage": 100},
        "checks": [
            {
                "id": check_id,
                "status": "pass",
                "blocks_apply": False,
                "observed": expected.get("canonical_url"),
                "expected": expected.get("canonical_url"),
            }
            for check_id in sorted(required)
        ],
    }


def _options(
    *, apply: bool = True, environment: str = "production", canary: bool = False
) -> ApplyOptions:
    return ApplyOptions(
        apply=apply,
        environment=environment,
        confirmation=f"APPLY {RUN_ID}",
        canary=canary,
        target_identity=SOURCE_IDENTITY,
    )


def _apply(
    migration_case: MigrationCase,
    *,
    plan: Mapping[str, Any],
    approval: Mapping[str, Any],
    publisher: FakePublisher,
    run_dir: Path,
    canary: bool = False,
    image_root: Path | None = None,
) -> dict[str, Any]:
    return apply_migration(
        snapshot=migration_case.snapshot,
        plan=plan,
        approval=approval,
        options=_options(canary=canary),
        target_content_hash=migration_case.snapshot["metadata"]["catalog_hash"],
        run_dir=run_dir,
        publisher=publisher,
        image_root=image_root,
    )
