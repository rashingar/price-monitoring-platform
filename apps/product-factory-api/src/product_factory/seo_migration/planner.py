from __future__ import annotations

"""Deterministic, offline Phase 4 migration planning and review artifacts."""

import csv
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit, urlunsplit

from ..seo_health import evaluate_seo_health
from .candidates import candidate_catalog_hash


CLASSIFICATIONS = {
    "unchanged",
    "safe_content_update",
    "review_required",
    "blocked",
    "unavailable",
}
PROTECTED_FIELDS = {"status", "active", "price", "quantity", "stock_status"}
REPORT_ONLY_FIELDS = {
    "identifiers",
    "image_alt_metadata",
    "structured_data_manifest",
    "product_feed_manifest",
}


class MigrationPlanError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FieldPolicy:
    field: str
    current_key: str
    candidate_key: str
    change_classification: str
    approval_requirement: str


FIELD_POLICIES: tuple[FieldPolicy, ...] = (
    FieldPolicy("name", "name", "name", "safe_content_update", "approved_fields:name"),
    FieldPolicy(
        "description",
        "description",
        "description",
        "safe_content_update",
        "approved_fields:description",
    ),
    FieldPolicy(
        "meta_title",
        "meta_title",
        "meta_title",
        "safe_content_update",
        "approved_fields:meta_title",
    ),
    FieldPolicy(
        "meta_description",
        "meta_description",
        "meta_description",
        "safe_content_update",
        "approved_fields:meta_description",
    ),
    FieldPolicy(
        "meta_keywords",
        "meta_keywords",
        "meta_keywords",
        "safe_content_update",
        "approved_fields:meta_keywords",
    ),
    FieldPolicy("category", "category", "category", "review_required", "approved_fields:category"),
    FieldPolicy("filter_values", "filters", "filters", "review_required", "approved_fields:filter_values"),
    FieldPolicy("manufacturer", "manufacturer", "manufacturer", "review_required", "approved_fields:manufacturer"),
    FieldPolicy("mpn", "mpn", "mpn", "review_required", "approved_fields:mpn"),
    FieldPolicy(
        "identifiers",
        "identifiers",
        "identifiers",
        "unavailable",
        "not_approvable:mpn_only_contract",
    ),
    FieldPolicy(
        "related_products",
        "related_products",
        "related_products",
        "safe_content_update",
        "approved_fields:related_products",
    ),
    FieldPolicy(
        "image_alt_metadata",
        "image_alt_metadata",
        "image_alt_metadata",
        "unavailable",
        "not_approvable:no_published_writer",
    ),
    FieldPolicy(
        "gallery_image_candidate",
        "gallery_paths",
        "gallery_candidates",
        "review_required",
        "approved_image_path_change",
    ),
    FieldPolicy(
        "seo_keyword_candidate",
        "seo_keyword",
        "seo_keyword_candidate",
        "review_required",
        "approved_slug_change",
    ),
    FieldPolicy(
        "canonical_url",
        "canonical_url",
        "canonical_url_candidate",
        "review_required",
        "approved_slug_change",
    ),
    FieldPolicy(
        "structured_data_manifest",
        "structured_data_manifest",
        "structured_data_manifest",
        "unavailable",
        "not_approvable:no_published_consumer",
    ),
    FieldPolicy(
        "product_feed_manifest",
        "product_feed_manifest",
        "product_feed_manifest",
        "unavailable",
        "not_approvable:no_published_consumer",
    ),
    FieldPolicy("status", "status", "status", "blocked", "never_approvable"),
    FieldPolicy("active", "active", "active", "blocked", "never_approvable"),
    FieldPolicy("price", "price", "price", "blocked", "never_approvable"),
    FieldPolicy("quantity", "quantity", "quantity", "blocked", "never_approvable"),
    FieldPolicy(
        "stock_status",
        "stock_status",
        "stock_status",
        "blocked",
        "never_approvable",
    ),
)


def build_migration_plan(
    *,
    snapshot: Mapping[str, Any],
    candidates: Mapping[str, Mapping[str, Any]],
    run_id: str,
    generated_at: str | None = None,
    canary_size: int = 5,
    live_validation_by_model: Mapping[str, Mapping[str, Any]] | None = None,
    image_root: Path | str | None = None,
) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,127}", run_id):
        raise MigrationPlanError("Migration run id contains unsupported characters.")
    if not 5 <= canary_size <= 10:
        raise MigrationPlanError("Canary size must be between 5 and 10.")

    metadata = _snapshot_metadata(snapshot)
    snapshot_id = str(metadata.get("snapshot_id") or snapshot.get("snapshot_id") or "")
    if not snapshot_id:
        raise MigrationPlanError("Snapshot id is missing.")
    current_products = _snapshot_products(snapshot)
    available_fields = set(metadata.get("available_fields", snapshot.get("available_fields", [])) or [])
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    live_by_model = live_validation_by_model or {}
    reviewed_image_root = (
        Path(image_root).expanduser().resolve() if image_root is not None else None
    )
    if reviewed_image_root is not None and (
        not reviewed_image_root.exists() or not reviewed_image_root.is_dir()
    ):
        raise MigrationPlanError(
            f"Reviewed image root is missing or not a directory: {reviewed_image_root}"
        )

    products: list[dict[str, Any]] = []
    redirects: list[dict[str, Any]] = []
    image_candidates: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for model in sorted(set(current_products) & set(candidates)):
        current = _with_current_derived_values(current_products[model])
        candidate = _with_candidate_derived_values(current, candidates[model])
        entries: list[dict[str, Any]] = []
        for policy in FIELD_POLICIES:
            entry = _classify_field(
                model=model,
                policy=policy,
                current=current,
                candidate=candidate,
                current_available=available_fields,
                candidate_available=set(candidates[model].get("availability", [])),
                candidate_context=candidates[model],
                snapshot_id=snapshot_id,
            )
            entries.append(entry)
            if entry["classification"] == "blocked":
                blocked.append(dict(entry))

        redirects.extend(_redirect_candidates(model, current, candidate))
        image_candidates.extend(
            _image_candidates(
                model,
                current,
                candidate,
                candidates[model],
                image_root=reviewed_image_root,
            )
        )
        phase4 = _phase4_context(
            entries=entries,
            redirects=[item for item in redirects if item["model"] == model],
            live_validation=live_by_model.get(model),
        )
        before_health, after_health = _health_before_after(
            model=model,
            current=current,
            candidate=candidate,
            candidate_context=candidates[model],
            phase4=phase4,
            generated_at=timestamp,
        )
        for entry in entries:
            entry["seo_health_before"] = _health_brief(before_health)
            entry["seo_health_after"] = _health_brief(after_health)
        products.append(
            {
                "model": model,
                "family": _family(candidates[model], current, candidate),
                "current_status": current.get("status", ""),
                "fields": entries,
                "seo_health_before": before_health,
                "seo_health_after": after_health,
                "seo_health_input": {
                    "row": _health_row(candidate),
                    "deterministic_product": dict(
                        candidates[model].get("deterministic_product", {})
                    ),
                    "phase2": dict(candidates[model].get("phase2", {})),
                    "phase3": dict(candidates[model].get("phase3", {})),
                    "phase4": phase4,
                    "settings": {
                        "enforcement_mode": "blockers_only",
                        "phase3": {
                            "enabled": bool(candidates[model].get("phase3")),
                            "families": [_family(candidates[model], current, candidate)],
                            "mpn_require_verified": True,
                        },
                    },
                },
            }
        )

    missing_candidates = sorted(set(current_products) - set(candidates))
    candidate_only = sorted(set(candidates) - set(current_products))
    classification_counts = Counter(
        entry["classification"]
        for product in products
        for entry in product["fields"]
    )
    rollback_manifest = _rollback_manifest(
        snapshot_id=snapshot_id,
        run_id=run_id,
        generated_at=timestamp,
        products=products,
        target_identity=str(metadata.get("target_identity") or ""),
    )
    health_summary = _seo_health_summary(products)
    canary = propose_canary(
        products=products,
        current_products=current_products,
        candidates=candidates,
        size=canary_size,
        run_id=run_id,
    )
    plan: dict[str, Any] = {
        "schema_version": "1.0",
        "migration_run_id": run_id,
        "snapshot_id": snapshot_id,
        "generated_at": timestamp,
        "mode": "dry_run",
        "environment": str(metadata.get("source_environment") or metadata.get("environment") or ""),
        "target_identity": str(metadata.get("target_identity") or ""),
        "snapshot_content_hash": str(metadata.get("content_hash") or ""),
        "snapshot_catalog_hash": str(metadata.get("catalog_hash") or ""),
        "candidate_content_hash": candidate_catalog_hash(candidates),
        "summary": {
            "product_count": len(products),
            "snapshot_product_count": len(current_products),
            "candidate_product_count": len(candidates),
            "missing_candidates": missing_candidates,
            "candidate_only": candidate_only,
            "classifications": {
                key: int(classification_counts.get(key, 0))
                for key in sorted(CLASSIFICATIONS)
            },
            "blocked_field_count": len(blocked),
            "redirect_candidate_count": len(redirects),
            "image_candidate_count": len(image_candidates),
            "reviewed_image_source_hash_count": sum(
                1 for item in image_candidates if item.get("source_hash")
            ),
            "blocking_seo_health_failures": health_summary["blocking_failures"],
            "production_writes": 0,
            "dry_run": True,
            "enforcement_mode": "blockers_only",
            "strict_enabled_automatically": False,
        },
        "products": products,
        "blocked": blocked,
        "redirect_candidates": redirects,
        "image_candidates": image_candidates,
        "rollback_manifest": rollback_manifest,
        "seo_health_summary": health_summary,
        "canary_proposal": canary,
    }
    plan["plan_hash"] = compute_migration_plan_hash(plan)
    return plan


def write_migration_artifacts(
    plan: Mapping[str, Any], output_root: Path | str
) -> Path:
    root = Path(output_root).expanduser().resolve()
    run_id = str(plan.get("migration_run_id") or "")
    run_dir = root / run_id
    if run_dir.exists() and any(run_dir.iterdir()):
        raise MigrationPlanError(f"Migration run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        key: plan[key]
        for key in (
            "schema_version",
            "migration_run_id",
            "snapshot_id",
            "generated_at",
            "mode",
            "environment",
            "target_identity",
            "snapshot_content_hash",
            "snapshot_catalog_hash",
            "candidate_content_hash",
            "plan_hash",
            "summary",
        )
    }
    _atomic_json(run_dir / "summary.json", summary)
    _atomic_json(run_dir / "plan.json", plan)
    _atomic_json(run_dir / "products.json", plan.get("products", []))
    _write_products_csv(run_dir / "products.csv", plan.get("products", []))
    _atomic_json(run_dir / "blocked.json", plan.get("blocked", []))
    _write_dict_csv(
        run_dir / "redirect_candidates.csv",
        plan.get("redirect_candidates", []),
        (
            "old_path",
            "new_path",
            "status_code",
            "model",
            "approved",
            "applied",
            "verified",
            "reason",
        ),
    )
    _write_dict_csv(
        run_dir / "image_candidates.csv",
        plan.get("image_candidates", []),
        (
            "model",
            "position",
            "role",
            "current_path",
            "candidate_path",
            "source_file",
            "source_hash",
            "classification",
            "approval_requirement",
            "copy_before_switch",
            "preserve_original",
            "besco_preserved",
        ),
    )
    _atomic_json(run_dir / "rollback_manifest.json", plan.get("rollback_manifest", {}))
    _atomic_json(run_dir / "seo_health_summary.json", plan.get("seo_health_summary", {}))
    _atomic_json(run_dir / "canary_proposal.json", plan.get("canary_proposal", {}))
    return run_dir


def load_plan_artifacts(run_dir: Path | str) -> dict[str, Any]:
    path = Path(run_dir).expanduser().resolve()
    full_plan_path = path / "plan.json"
    if not full_plan_path.is_file():
        raise MigrationPlanError(
            "Authoritative plan.json is missing; split review artifacts are never "
            "accepted for apply or rollback. Re-run the dry-run plan."
        )
    plan = _read_json(full_plan_path)
    if not isinstance(plan, Mapping):
        raise MigrationPlanError("Migration plan artifact is invalid.")
    return verify_migration_plan(plan)


def compute_migration_plan_hash(plan: Mapping[str, Any]) -> str:
    material = deepcopy(dict(plan))
    material.pop("plan_hash", None)
    return _content_hash(material)


def verify_migration_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, Mapping):
        raise MigrationPlanError("Migration plan artifact is invalid.")
    expected = str(plan.get("plan_hash") or "")
    actual = compute_migration_plan_hash(plan)
    if not expected or expected != actual:
        raise MigrationPlanError("Migration plan content hash no longer matches.")
    return deepcopy(dict(plan))


def propose_canary(
    *,
    products: Iterable[Mapping[str, Any]],
    current_products: Mapping[str, Mapping[str, Any]],
    candidates: Mapping[str, Mapping[str, Any]],
    size: int,
    run_id: str,
) -> dict[str, Any]:
    eligible: list[dict[str, Any]] = []
    for product in products:
        model = str(product.get("model") or "")
        if str(product.get("family") or "") != "air_conditioner":
            continue
        current = current_products.get(model, {})
        candidate = candidates.get(model, {})
        deterministic = candidate.get("deterministic_product", {})
        deterministic = deterministic if isinstance(deterministic, Mapping) else {}
        identity = deterministic.get("seo_identity", {})
        identity = identity if isinstance(identity, Mapping) else {}
        main_image = str(current.get("main_image") or current.get("image") or "")
        identifiers = {
            key: current.get(key)
            for key in ("ean", "gtin", "upc", "jan", "isbn")
            if key in current
        }
        active_raw = str(current.get("active") or "").strip().casefold()
        if active_raw in {"1", "true", "active", "enabled", "yes"}:
            active: bool | None = True
        elif active_raw in {"0", "false", "inactive", "disabled", "no"}:
            active = False
        else:
            active = None
        status = str(current.get("status") or "").strip().casefold()
        attributes = {
            "series" if str(identity.get("commercial_series") or "") else "no_series",
            "legacy_image" if _legacy_image(model, main_image) else "descriptive_image",
            "with_gtin" if any(str(value or "") for value in identifiers.values()) else "without_gtin",
            "status_enabled"
            if status in {"1", "true", "active", "enabled"}
            else "status_disabled",
        }
        attributes.add(
            "active" if active is True else "inactive" if active is False else "activity_unavailable"
        )
        eligible.append(
            {
                "model": model,
                "active": active,
                "activity_available": active is not None,
                "attributes": sorted(attributes),
                "operator_approval_required": True,
                "inactive_requires_explicit_selection": active is False,
            }
        )

    selected: list[dict[str, Any]] = []
    uncovered = {
        "active",
        "inactive",
        "series",
        "no_series",
        "legacy_image",
        "descriptive_image",
        "with_gtin",
        "without_gtin",
    }
    remaining = sorted(eligible, key=lambda item: item["model"])
    while remaining and len(selected) < size:
        best = max(
            remaining,
            key=lambda item: (
                len(set(item["attributes"]) & uncovered),
                1 if item["active"] is True else 0,
                tuple(-ord(char) for char in item["model"]),
            ),
        )
        selected.append(best)
        uncovered -= set(best["attributes"])
        remaining.remove(best)
    return {
        "schema_version": "1.0",
        "migration_run_id": run_id,
        "status": "proposed",
        "operator_approval_required": True,
        "selection_is_not_approval": True,
        "requested_size": size,
        "available_count": len(eligible),
        "proposed_models": [item["model"] for item in selected],
        "products": selected,
        "coverage_gaps": sorted(uncovered),
        "instructions": (
            "Approve only intended models by placing them in the machine-readable "
            "approval manifest; proposal membership alone never authorizes apply."
        ),
    }


def _classify_field(
    *,
    model: str,
    policy: FieldPolicy,
    current: Mapping[str, Any],
    candidate: Mapping[str, Any],
    current_available: set[str],
    candidate_available: set[str],
    candidate_context: Mapping[str, Any],
    snapshot_id: str,
) -> dict[str, Any]:
    current_value = current.get(policy.current_key)
    candidate_value = candidate.get(policy.candidate_key)
    current_key_available = _current_available(policy.current_key, current_available, current)
    candidate_key_available = _candidate_available(
        policy.candidate_key, candidate_available, candidate
    )
    reason = "values_match"
    classification = "unchanged"

    if not candidate_key_available:
        classification = "unavailable"
        reason = "candidate_field_unavailable"
    elif not current_key_available:
        classification = "unavailable"
        reason = "published_field_unavailable_in_snapshot"
    elif policy.field == "gallery_image_candidate" and _equivalent(
        current_value,
        [
            str(item.get("candidate_path") or "")
            for item in candidate_value
            if isinstance(item, Mapping)
        ]
        if isinstance(candidate_value, list)
        else candidate_value,
    ):
        classification = "unchanged"
    elif _equivalent(current_value, candidate_value):
        classification = "unchanged"
    elif policy.field in PROTECTED_FIELDS:
        classification = "blocked"
        reason = f"{policy.field}_changes_are_outside_seo_migration_scope"
    elif policy.field == "mpn":
        conflict, conflict_reason = _identifier_conflict(
            policy.field, current_value, candidate_value, candidate_context
        )
        classification = "blocked" if conflict else "review_required"
        reason = conflict_reason
    elif policy.field == "identifiers":
        conflict, conflict_reason = _identifier_conflict(
            policy.field, current_value, candidate_value, candidate_context
        )
        classification = "blocked" if conflict else "unavailable"
        reason = (
            conflict_reason
            if conflict
            else "gtin_ean_fields_are_report_only_under_mpn_only_contract"
        )
    elif policy.field in REPORT_ONLY_FIELDS:
        classification = "unavailable"
        reason = "candidate_has_no_confirmed_published_writer_or_consumer"
    else:
        classification = policy.change_classification
        reason = _change_reason(policy.field, classification)

    if classification not in CLASSIFICATIONS:
        raise AssertionError(classification)
    return {
        "model": model,
        "field": policy.field,
        "current_value": current_value,
        "candidate_value": candidate_value,
        "classification": classification,
        "reason": reason,
        "evidence": [
            {
                "source": "catalog_snapshot",
                "field": policy.current_key,
                "snapshot_id": snapshot_id,
                "value_hash": _content_hash(current_value),
            },
            {
                "source": "phase1_3_candidate",
                "field": policy.candidate_key,
                "artifacts": dict(candidate_context.get("evidence", {})),
                "value_hash": _content_hash(candidate_value),
            },
        ],
        "seo_health_before": {},
        "seo_health_after": {},
        "approval_requirement": (
            "none" if classification in {"unchanged", "unavailable", "blocked"}
            else policy.approval_requirement
        ),
    }


def _with_current_derived_values(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["gallery_paths"] = [
        str(row.get("main_image") or row.get("image") or ""),
        *[str(value) for value in row.get("additional_images", []) or []],
    ]
    result["gallery_paths"] = [value for value in result["gallery_paths"] if value]
    result["identifiers"] = {
        key: str(row.get(key) or "")
        for key in ("ean", "gtin", "upc", "jan", "isbn")
        if key in row
    }
    result.setdefault("image_alt_metadata", row.get("image_alt_metadata"))
    result.setdefault("structured_data_manifest", row.get("structured_data_manifest"))
    result.setdefault("product_feed_manifest", row.get("product_feed_manifest"))
    return result


def _with_candidate_derived_values(
    current: Mapping[str, Any], candidate_context: Mapping[str, Any]
) -> dict[str, Any]:
    values = dict(candidate_context.get("values", {}))
    if "gallery_candidates" not in values:
        paths = [
            str(values.get("main_image") or ""),
            *[str(value) for value in values.get("additional_images", []) or []],
        ]
        values["gallery_candidates"] = [
            {
                "position": index,
                "role": "main" if index == 1 else "gallery",
                "current_path": (
                    current.get("gallery_paths", [])[index - 1]
                    if index <= len(current.get("gallery_paths", []))
                    else ""
                ),
                "candidate_path": path,
                "local_path": "",
                "content_hash": "",
                "jpeg_valid": False,
                "alt": "",
            }
            for index, path in enumerate((path for path in paths if path), start=1)
        ]
    values.setdefault("seo_keyword_candidate", values.get("seo_keyword", ""))
    values["canonical_url_candidate"] = _canonical_candidate_url(
        current_url=str(current.get("canonical_url") or ""),
        row_candidate_url=str(values.get("canonical_url") or ""),
        candidate_slug=str(values.get("seo_keyword_candidate") or ""),
    )
    return values


def _current_available(
    key: str, available: set[str], current: Mapping[str, Any]
) -> bool:
    aliases = {
        "gallery_paths": {"main_image", "additional_images"},
        "identifiers": {"ean", "gtin", "upc", "jan", "isbn", "identifiers"},
    }
    if key in {"structured_data_manifest", "product_feed_manifest", "image_alt_metadata"}:
        return key in available or current.get(key) is not None
    return key in available or bool(aliases.get(key, set()) & available)


def _candidate_available(
    key: str, available: set[str], candidate: Mapping[str, Any]
) -> bool:
    if key == "canonical_url_candidate":
        return "seo_keyword_candidate" in available or "seo_keyword" in available
    if key == "gallery_candidates":
        return "gallery_candidates" in available or "main_image" in available
    if key in {
        "image_alt_metadata",
        "structured_data_manifest",
        "product_feed_manifest",
    }:
        return key in available and candidate.get(key) is not None
    if key == "seo_keyword_candidate":
        return (
            "seo_keyword_candidate" in available or "seo_keyword" in available
        ) and candidate.get(key) is not None
    return key in available


def _identifier_conflict(
    field: str,
    current: Any,
    candidate: Any,
    candidate_context: Mapping[str, Any],
) -> tuple[bool, str]:
    if field == "mpn":
        left = str(current or "").strip().casefold()
        right = str(candidate or "").strip().casefold()
        identity = candidate_context.get("phase3", {}).get("identity", {})
        identity = identity if isinstance(identity, Mapping) else {}
        status = str(identity.get("mpn_status") or "").strip().casefold()
        if left and right and left != right:
            return True, "identifier_conflict_existing_mpn_differs"
        if right and left != right and status != "verified":
            return True, "identifier_provenance_not_verified"
        return False, "identifier_addition_requires_review"
    left_map = current if isinstance(current, Mapping) else {}
    right_map = candidate if isinstance(candidate, Mapping) else {}
    conflicts = [
        key
        for key in sorted(set(left_map) & set(right_map))
        if str(left_map.get(key) or "").strip()
        and str(right_map.get(key) or "").strip()
        and str(left_map.get(key)).strip().casefold()
        != str(right_map.get(key)).strip().casefold()
    ]
    if conflicts:
        return True, f"identifier_conflict:{','.join(conflicts)}"
    return False, "identifier_change_requires_review"


def _change_reason(field: str, classification: str) -> str:
    if field == "seo_keyword_candidate":
        return "published_slug_locked_candidate_requires_individual_approval_and_redirect"
    if field == "canonical_url":
        return "canonical_url_change_is_coupled_to_approved_slug_and_redirect"
    if field == "gallery_image_candidate":
        return "published_image_paths_are_locked_without_individual_copy_approval"
    if field in {"category", "filter_values"}:
        return "taxonomy_change_requires_operator_review"
    return (
        "content_candidate_differs_and_is_approval_eligible"
        if classification == "safe_content_update"
        else "change_requires_operator_review"
    )


def _redirect_candidates(
    model: str, current: Mapping[str, Any], candidate: Mapping[str, Any]
) -> list[dict[str, Any]]:
    old_path = _url_path(
        str(current.get("canonical_url") or ""),
        fallback_slug=str(current.get("seo_keyword") or ""),
    )
    new_path = _url_path(
        str(candidate.get("canonical_url_candidate") or ""),
        fallback_slug=str(candidate.get("seo_keyword_candidate") or ""),
    )
    if not old_path or not new_path or old_path == new_path:
        return []
    return [
        {
            "old_path": old_path,
            "new_path": new_path,
            "status_code": 301,
            "model": model,
            "approved": False,
            "applied": False,
            "verified": False,
            "reason": "repository_has_no_redirect_applicator; external confirmation required",
        }
    ]


def _image_candidates(
    model: str,
    current: Mapping[str, Any],
    candidate: Mapping[str, Any],
    candidate_context: Mapping[str, Any],
    *,
    image_root: Path | None,
) -> list[dict[str, Any]]:
    gallery = candidate.get("gallery_candidates", [])
    if not isinstance(gallery, list):
        return []
    result: list[dict[str, Any]] = []
    for fallback, raw in enumerate(gallery, start=1):
        item = raw if isinstance(raw, Mapping) else {}
        position = int(item.get("position") or fallback)
        # Published paths are authoritative only in the immutable catalog
        # snapshot. Candidate artifacts may describe a proposed filename, but
        # must never redirect which published source file is copied.
        current_path = (
            str(current["gallery_paths"][position - 1])
            if position <= len(current.get("gallery_paths", []))
            else ""
        )
        candidate_path = str(item.get("candidate_path") or "")
        source_hash = str(item.get("current_source_hash") or "")
        if (
            image_root is not None
            and current_path
            and candidate_path
            and current_path != candidate_path
        ):
            source_path = _reviewed_image_source_path(
                image_root, current_path, model=model
            )
            if not source_path.is_file():
                raise MigrationPlanError(
                    f"Published image source is missing during reviewed planning: {current_path}"
                )
            try:
                source_payload = source_path.read_bytes()
            except OSError as exc:
                raise MigrationPlanError(
                    f"Published image source cannot be read during reviewed planning: {current_path}"
                ) from exc
            if not source_payload:
                raise MigrationPlanError(
                    f"Published image source is empty during reviewed planning: {current_path}"
                )
            source_hash = "sha256:" + hashlib.sha256(source_payload).hexdigest()
        result.append(
            {
                "model": model,
                "position": position,
                "role": str(item.get("role") or ("main" if position == 1 else "gallery")),
                "current_path": current_path,
                "candidate_path": candidate_path,
                "source_file": current_path,
                "source_hash": source_hash,
                "candidate_source_file": str(item.get("local_path") or ""),
                "candidate_source_hash": str(item.get("content_hash") or ""),
                "classification": (
                    "unchanged"
                    if current_path and current_path == candidate_path
                    else "review_required"
                ),
                "approval_requirement": (
                    "none"
                    if current_path and current_path == candidate_path
                    else "approved_image_path_change"
                ),
                "copy_before_switch": True,
                "preserve_original": True,
                "besco_preserved": True,
                "candidate_artifacts": dict(candidate_context.get("evidence", {})),
            }
        )
    return result


def _reviewed_image_source_path(root: Path, reference: str, *, model: str) -> Path:
    normalized = reference.replace("\\", "/").lstrip("/")
    if not normalized or re.match(r"^[A-Za-z]:", normalized):
        raise MigrationPlanError(f"Unsafe published image source path: {reference}")
    expected_prefix = f"catalog/01_main/{model}/"
    if not normalized.startswith(expected_prefix) or ".." in Path(normalized).parts:
        raise MigrationPlanError(
            f"Published image source is outside the model gallery: {reference}"
        )
    resolved = (root / Path(normalized)).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise MigrationPlanError(
            f"Published image source escapes the reviewed image root: {reference}"
        ) from exc
    return resolved


def _phase4_context(
    *,
    entries: list[Mapping[str, Any]],
    redirects: list[Mapping[str, Any]],
    live_validation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    protected_ok = all(
        entry.get("classification") in {"unchanged", "blocked", "unavailable"}
        for entry in entries
        if entry.get("field") in PROTECTED_FIELDS
    )
    redirect_status = "warn" if redirects else "pass"
    live_checks = list((live_validation or {}).get("checks", []))
    if not live_validation or not live_checks:
        live_status = "not_run"
    elif any(check.get("status") == "fail" for check in live_checks):
        live_status = "fail"
    elif any(check.get("status") in {"warn", "not_run"} for check in live_checks):
        live_status = "warn"
    else:
        live_status = "pass"
    return {
        "rollout.migration_safety": {
            "status": "pass" if protected_ok else "fail",
            "blocks_publish": not protected_ok,
            "message": "Dry-run plan protects all out-of-scope fields.",
            "observed": {"dry_run": True, "protected_fields_guarded": protected_ok},
            "expected": True,
            "subchecks": [
                {"id": "dry_run_default", "status": "pass", "message": "Planner is offline and dry-run only."},
                {"id": "protected_fields_guarded", "status": "pass" if protected_ok else "fail", "message": "Status, activation, price, quantity, and stock are never approval-eligible."},
                {"id": "rollback_manifest_available", "status": "pass", "message": "Rollback operations are generated before apply."},
            ],
        },
        "rollout.redirect_and_canonical_coverage": {
            "status": redirect_status,
            "blocks_publish": False,
            "message": (
                "Redirect candidates require external apply/verification before slug apply."
                if redirects
                else "Published slug and canonical URL remain unchanged."
            ),
            "observed": {"redirect_candidates": len(redirects), "repository_redirect_support": False},
            "expected": "locked or externally confirmed 301",
            "subchecks": [
                {"id": "published_slug_locked", "status": "pass", "message": "Dry-run never changes a published slug."},
                {"id": "redirect_requirement_generated", "status": redirect_status, "message": "External 301 ownership is explicit."},
            ],
        },
        "rollout.production_validation": {
            "status": live_status,
            "blocks_publish": live_status == "fail",
            "message": "Live validation is not run without configured public access." if live_status == "not_run" else "Live validation result aggregated.",
            "observed": live_validation or {"configured": False},
            "expected": "all configured live checks pass",
            "subchecks": live_checks or [
                {"id": "live_access_configured", "status": "not_run", "message": "No live access configured."}
            ],
        },
        "rollout.monitoring_and_rollback": {
            "status": "pass",
            "blocks_publish": False,
            "message": "Monitoring inputs and complete pre-apply rollback data are generated.",
            "observed": {"rollback_manifest": True, "monitoring_report_supported": True},
            "expected": True,
            "subchecks": [
                {"id": "rollback_available", "status": "pass", "message": "Rollback values come from the immutable snapshot."},
                {"id": "monitoring_supported", "status": "pass", "message": "Post-rollout comparison is available as an explicit operator command."},
            ],
        },
    }


def _health_before_after(
    *,
    model: str,
    current: Mapping[str, Any],
    candidate: Mapping[str, Any],
    candidate_context: Mapping[str, Any],
    phase4: Mapping[str, Any],
    generated_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    deterministic = deepcopy(
        dict(candidate_context.get("deterministic_product", {}))
    )
    deterministic.setdefault("brand", str(candidate.get("manufacturer") or current.get("manufacturer") or ""))
    deterministic.setdefault("mpn", str(candidate.get("mpn") or current.get("mpn") or ""))
    before_deterministic = deepcopy(deterministic)
    before_deterministic.pop("product_identity", None)
    for phase2_key in (
        "image_assets",
        "presentation_section_image_metadata",
        "internal_links",
        "catalog_similarity",
        "description_heading",
    ):
        before_deterministic.pop(phase2_key, None)
    before_deterministic["published_seo_keyword"] = str(current.get("seo_keyword") or "")
    before_deterministic["seo_keyword_candidate"] = str(current.get("seo_keyword") or "")
    before = evaluate_seo_health(
        model=model,
        row=_health_row(current),
        deterministic_product=before_deterministic,
        profile="full",
        phase2={},
        phase3={},
        phase4={
            **phase4,
            "rollout.production_validation": {
                **dict(phase4.get("rollout.production_validation", {})),
                "status": "not_run",
            },
        },
        settings={"enforcement_mode": "blockers_only"},
    )
    after = evaluate_seo_health(
        model=model,
        row=_health_row(candidate),
        deterministic_product=deterministic,
        profile="full",
        phase2=candidate_context.get("phase2", {}),
        phase3=candidate_context.get("phase3", {}),
        phase4=phase4,
        settings={
            "enforcement_mode": "blockers_only",
            "phase3": {
                "enabled": bool(candidate_context.get("phase3")),
                "families": [_family(candidate_context, current, candidate)],
                "mpn_require_verified": True,
            },
        },
    )
    before["generated_at"] = generated_at
    after["generated_at"] = generated_at
    return before, after


def _health_row(values: Mapping[str, Any]) -> dict[str, Any]:
    gallery = values.get("gallery_candidates", [])
    gallery_paths = [
        str(item.get("candidate_path") or "")
        for item in gallery
        if isinstance(item, Mapping)
    ] if isinstance(gallery, list) else list(values.get("gallery_paths", []) or [])
    return {
        "model": str(values.get("model") or ""),
        "mpn": str(values.get("mpn") or ""),
        "name": str(values.get("name") or ""),
        "description": str(values.get("description") or ""),
        "meta_title": str(values.get("meta_title") or ""),
        "meta_description": str(values.get("meta_description") or ""),
        "meta_keyword": str(values.get("meta_keywords") or ""),
        "seo_keyword": str(values.get("seo_keyword_candidate") or values.get("seo_keyword") or ""),
        "product_url": str(values.get("canonical_url_candidate") or values.get("canonical_url") or ""),
        "image": gallery_paths[0] if gallery_paths else str(values.get("main_image") or ""),
        "additional_image": ":::".join(gallery_paths[1:]),
        "price": str(values.get("price") or ""),
        "quantity": str(values.get("quantity") or ""),
        "status": str(values.get("status") or ""),
    }


def _rollback_manifest(
    *,
    snapshot_id: str,
    run_id: str,
    generated_at: str,
    products: list[Mapping[str, Any]],
    target_identity: str,
) -> dict[str, Any]:
    operations: list[dict[str, Any]] = []
    for product in products:
        model = str(product.get("model") or "")
        product_fields = {
            str(item.get("field") or ""): item
            for item in product.get("fields", [])
            if isinstance(item, Mapping)
        }
        for field in product.get("fields", []):
            if field.get("classification") not in {"safe_content_update", "review_required"}:
                continue
            logical_field = str(field.get("field") or "")
            restore_value = field.get("current_value")
            expected_value = field.get("candidate_value")
            extra: dict[str, Any] = {}
            if logical_field == "gallery_image_candidate":
                expected_value = [
                    str(item.get("candidate_path") or "")
                    for item in expected_value
                    if isinstance(item, Mapping)
                ] if isinstance(expected_value, list) else []
                extra = {
                    "restore_description": product_fields.get("description", {}).get(
                        "current_value"
                    ),
                    "expected_applied_description": _description_with_gallery_references(
                        str(product_fields.get("description", {}).get("current_value") or ""),
                        list(restore_value or []) if isinstance(restore_value, list) else [],
                        expected_value,
                    ),
                }
                artifact_operations: list[dict[str, Any]] = []
                canonical_url = str(
                    product_fields.get("canonical_url", {}).get("current_value") or ""
                )
                current_gallery = [str(item or "") for item in restore_value or []]
                for artifact_name in (
                    "structured_data_manifest",
                    "product_feed_manifest",
                ):
                    artifact_value = product_fields.get(artifact_name, {}).get(
                        "candidate_value"
                    )
                    if not isinstance(artifact_value, Mapping):
                        continue
                    artifact_operations.append(
                        {
                            "name": artifact_name,
                            "restore_value": _artifact_with_gallery_and_url(
                                artifact_name,
                                artifact_value,
                                gallery_paths=current_gallery,
                                canonical_url=canonical_url,
                            ),
                            "expected_applied_value": _artifact_with_gallery_and_url(
                                artifact_name,
                                artifact_value,
                                gallery_paths=expected_value,
                                canonical_url=canonical_url,
                            ),
                            "published_consumer": "unavailable",
                        }
                    )
                if artifact_operations:
                    extra["artifact_operations"] = artifact_operations
            elif logical_field == "seo_keyword_candidate":
                artifact_operations: list[dict[str, Any]] = []
                old_url = str(
                    product_fields.get("canonical_url", {}).get("current_value") or ""
                )
                new_url = str(
                    product_fields.get("canonical_url", {}).get("candidate_value") or ""
                )
                published_gallery = [
                    str(item or "")
                    for item in product_fields.get(
                        "gallery_image_candidate", {}
                    ).get("current_value", [])
                ]
                for artifact_name in (
                    "structured_data_manifest",
                    "product_feed_manifest",
                ):
                    artifact_value = product_fields.get(artifact_name, {}).get(
                        "candidate_value"
                    )
                    if not isinstance(artifact_value, Mapping):
                        continue
                    restore_artifact = _artifact_with_gallery_and_url(
                        artifact_name,
                        artifact_value,
                        gallery_paths=published_gallery,
                        canonical_url=old_url,
                    )
                    expected_artifact = _artifact_with_gallery_and_url(
                        artifact_name,
                        artifact_value,
                        gallery_paths=published_gallery,
                        canonical_url=new_url,
                    )
                    artifact_operations.append(
                        {
                            "name": artifact_name,
                            "restore_value": restore_artifact,
                            "expected_applied_value": expected_artifact,
                            "published_consumer": "unavailable",
                        }
                    )
                if artifact_operations:
                    extra["artifact_operations"] = artifact_operations
            operations.append(
                {
                    "model": model,
                    "field": logical_field,
                    "restore_value": restore_value,
                    "expected_applied_value": expected_value,
                    "approval_requirement": field.get("approval_requirement"),
                    "write_attempted": False,
                    "apply_confirmation": "not_attempted",
                    "applied": False,
                    "rolled_back": False,
                    **extra,
                }
            )
    operations_hash = _content_hash(
        [_immutable_rollback_operation(operation) for operation in operations]
    )
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "snapshot_id": snapshot_id,
        "migration_run_id": run_id,
        "target_identity": target_identity,
        "created_at": generated_at,
        "created_before_apply": True,
        "complete": True,
        "status": "planned",
        "price_stock_status_excluded": True,
        "original_files_must_be_retained": True,
        "operations_hash": operations_hash,
        "operations": operations,
        "structured_data_and_feed_artifacts": [
            {
                "model": operation["model"],
                **artifact,
            }
            for operation in operations
            for artifact in operation.get("artifact_operations", [])
        ],
    }
    manifest["manifest_hash"] = _content_hash(
        {
            key: manifest[key]
            for key in (
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
        }
    )
    return manifest


def _immutable_rollback_operation(operation: Mapping[str, Any]) -> dict[str, Any]:
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
    return {
        key: value
        for key, value in operation.items()
        if key not in mutable_keys
    }


def _artifact_with_gallery_and_url(
    name: str,
    payload: Mapping[str, Any],
    *,
    gallery_paths: list[str],
    canonical_url: str,
) -> dict[str, Any]:
    result = deepcopy(dict(payload))
    existing_images: list[str] = []
    if name == "structured_data_manifest":
        raw_images = result.get("image")
        if isinstance(raw_images, list):
            existing_images = [str(item or "") for item in raw_images]
        elif raw_images:
            existing_images = [str(raw_images)]
        result["url"] = canonical_url
        result["image"] = [
            _artifact_image_url(path, existing_images, canonical_url, position)
            for position, path in enumerate(gallery_paths)
            if path
        ]
    elif name == "product_feed_manifest":
        existing_images = [
            str(result.get("image_link") or ""),
            *[
                str(item or "")
                for item in result.get("additional_image_links", []) or []
            ],
        ]
        result["link"] = canonical_url
        rewritten = [
            _artifact_image_url(path, existing_images, canonical_url, position)
            for position, path in enumerate(gallery_paths)
            if path
        ]
        result["image_link"] = rewritten[0] if rewritten else ""
        result["additional_image_links"] = rewritten[1:]
    return result


def _artifact_image_url(
    path: str,
    existing_images: list[str],
    canonical_url: str,
    position: int,
) -> str:
    existing = existing_images[position] if position < len(existing_images) else ""
    parsed = urlsplit(existing or canonical_url)
    normalized_path = str(path).replace("\\", "/").lstrip("/")
    image_path = f"/image/{normalized_path}"
    if parsed.scheme and parsed.netloc:
        return urlunsplit((parsed.scheme, parsed.netloc, image_path, "", ""))
    return image_path


def _description_with_gallery_references(
    description: str, current_paths: list[Any], candidate_paths: list[Any]
) -> str:
    result = description
    for old, new in zip(current_paths, candidate_paths):
        old_value = str(old or "")
        new_value = str(new or "")
        if old_value and new_value:
            result = result.replace(old_value, new_value)
            result = result.replace(f"/image/{old_value}", f"/image/{new_value}")
    return result


def _seo_health_summary(products: list[Mapping[str, Any]]) -> dict[str, Any]:
    rows = []
    for product in products:
        before = product.get("seo_health_before", {})
        after = product.get("seo_health_after", {})
        rows.append(
            {
                "model": product.get("model"),
                "before_score": before.get("score"),
                "after_score": after.get("score"),
                "score_delta": (
                    int(after.get("score", 0)) - int(before.get("score", 0))
                    if isinstance(before.get("score"), int) and isinstance(after.get("score"), int)
                    else None
                ),
                "before_coverage": before.get("coverage", {}).get("percentage"),
                "after_coverage": after.get("coverage", {}).get("percentage"),
                "blocking_failures": after.get("summary", {}).get("blocking_failures", 0),
                "enforcement_mode": after.get("publish_gate", {}).get("enforcement_mode"),
            }
        )
    return {
        "schema_version": "1.0",
        "profile": "full",
        "weights_total": 100,
        "enforcement_mode": "blockers_only",
        "strict_enabled_automatically": False,
        "product_count": len(rows),
        "blocking_failures": sum(int(row.get("blocking_failures") or 0) for row in rows),
        "score_regressions": sum(1 for row in rows if (row.get("score_delta") or 0) < 0),
        "products": rows,
    }


def _health_brief(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "profile": report.get("profile"),
        "score": report.get("score"),
        "coverage": report.get("coverage", {}).get("percentage"),
        "blocking_failures": report.get("summary", {}).get("blocking_failures"),
        "enforcement_mode": report.get("publish_gate", {}).get("enforcement_mode"),
    }


def _family(
    candidate_context: Mapping[str, Any],
    current: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> str:
    deterministic = candidate_context.get("deterministic_product", {})
    deterministic = deterministic if isinstance(deterministic, Mapping) else {}
    identity = deterministic.get("seo_identity", {})
    identity = identity if isinstance(identity, Mapping) else {}
    family = str(identity.get("family") or candidate_context.get("family") or "")
    if family:
        return family
    text = " ".join(
        str(value or "")
        for value in (candidate.get("category"), current.get("category"), candidate.get("name"))
    ).casefold()
    return "air_conditioner" if any(token in text for token in ("air conditioner", "klimat", "κλιματι")) else ""


def _canonical_candidate_url(
    *, current_url: str, row_candidate_url: str, candidate_slug: str
) -> str:
    if not candidate_slug:
        return row_candidate_url
    parsed = urlsplit(current_url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return urlunsplit((parsed.scheme, parsed.netloc, f"/{candidate_slug}", "", ""))
    parsed_candidate = urlsplit(row_candidate_url)
    if parsed_candidate.scheme in {"http", "https"} and parsed_candidate.netloc:
        return urlunsplit(
            (parsed_candidate.scheme, parsed_candidate.netloc, f"/{candidate_slug}", "", "")
        )
    return f"/{candidate_slug}"


def _url_path(value: str, *, fallback_slug: str) -> str:
    parsed = urlsplit(value)
    path = parsed.path.strip() if (parsed.scheme or parsed.netloc) else value.strip()
    if not path and fallback_slug:
        path = f"/{fallback_slug}"
    if path and not path.startswith("/"):
        path = f"/{path}"
    return path.rstrip("/") or "/"


def _legacy_image(model: str, path: str) -> bool:
    filename = Path(urlsplit(path).path).name
    return bool(re.fullmatch(rf"{re.escape(model)}-[1-9][0-9]*\.(?:jpe?g|webp)", filename, re.I))


def _equivalent(left: Any, right: Any) -> bool:
    return _canonical_json(left) == _canonical_json(right)


def _snapshot_metadata(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    value = snapshot.get("metadata", {})
    return dict(value) if isinstance(value, Mapping) else {}


def _snapshot_products(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = snapshot.get("products", [])
    if not isinstance(rows, list):
        raise MigrationPlanError("Snapshot products must be a list.")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise MigrationPlanError("Snapshot product row must be an object.")
        model = str(row.get("model") or "").strip()
        if not model or model in result:
            raise MigrationPlanError(f"Snapshot contains missing or duplicate model: {model!r}")
        result[model] = dict(row)
    return result


def _content_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _atomic_json(path: Path, payload: Any) -> None:
    _atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n")


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _write_products_csv(path: Path, products: Any) -> None:
    rows = []
    for product in products if isinstance(products, list) else []:
        for field in product.get("fields", []):
            rows.append(
                {
                    "model": product.get("model", ""),
                    "field": field.get("field", ""),
                    "current_value": _canonical_json(field.get("current_value")),
                    "candidate_value": _canonical_json(field.get("candidate_value")),
                    "classification": field.get("classification", ""),
                    "reason": field.get("reason", ""),
                    "evidence": _canonical_json(field.get("evidence", [])),
                    "seo_health_before": _canonical_json(field.get("seo_health_before", {})),
                    "seo_health_after": _canonical_json(field.get("seo_health_after", {})),
                    "approval_requirement": field.get("approval_requirement", ""),
                }
            )
    _write_dict_csv(
        path,
        rows,
        (
            "model",
            "field",
            "current_value",
            "candidate_value",
            "classification",
            "reason",
            "evidence",
            "seo_health_before",
            "seo_health_after",
            "approval_requirement",
        ),
    )


def _write_dict_csv(path: Path, rows: Any, fieldnames: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for raw in rows if isinstance(rows, list) else []:
                writer.writerow(
                    {
                        key: (
                            _canonical_json(value)
                            if isinstance(value, (dict, list))
                            else value
                        )
                        for key, value in dict(raw).items()
                    }
                )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MigrationPlanError(f"Could not read migration artifact {path}: {exc}") from exc


def _read_dict_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except (OSError, UnicodeError, csv.Error) as exc:
        raise MigrationPlanError(f"Could not read migration artifact {path}: {exc}") from exc
