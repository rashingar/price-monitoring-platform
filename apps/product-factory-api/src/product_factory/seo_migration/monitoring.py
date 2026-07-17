from __future__ import annotations

"""Deterministic post-rollout monitoring findings.

The input and output are plain mappings so the migration CLI can compose this
report from snapshot, apply, SEO-health, live-validation, and rollback
artifacts without introducing database or HTTP dependencies here.
"""

from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
import re
from typing import Any


FINDING_ORDER = (
    "seo_health.blocking_failures",
    "seo_health.score_regression",
    "rollout.unapproved_field_change",
    "rollout.unexpected_slug_change",
    "rollout.image_path_regression",
    "identifiers.missing",
    "structured_data.price_schema_mismatch",
    "structured_data.artifact_availability",
    "content.duplicate_increase",
    "rollout.live_validation",
    "rollout.rollback_availability",
)


def build_monitoring_report(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build stable Phase 4 findings from a mapping-based monitoring context."""

    before = _first_mapping(payload, "before", "snapshot_product", "baseline")
    after = _first_mapping(payload, "after", "current", "published")
    expected_after = _first_mapping(payload, "expected_after", "approved_candidate")
    approval = _first_mapping(payload, "approval", "product_approval")
    seo_health = _mapping(payload.get("seo_health")) or _mapping(after.get("seo_health"))
    baseline_seo_health = (
        _mapping(payload.get("baseline_seo_health"))
        or _mapping(payload.get("before_seo_health"))
        or _mapping(before.get("seo_health"))
    )

    findings = [
        _blocking_seo_finding(seo_health),
        _score_regression_finding(seo_health, baseline_seo_health),
        _unapproved_field_change_finding(after, expected_after),
        _slug_change_finding(before, after, expected_after, approval),
        _image_change_finding(before, after, expected_after, approval),
        _identifier_finding(
            after,
            contract=_text(payload.get("identifier_contract")) or "mpn_only",
        ),
        _price_schema_finding(payload, after),
        _structured_artifact_finding(payload, after),
        _duplicate_content_finding(payload, before, after, seo_health, baseline_seo_health),
        _live_validation_finding(_mapping(payload.get("live_validation"))),
        _rollback_finding(payload),
    ]
    counts = {
        status: sum(1 for finding in findings if finding["status"] == status)
        for status in ("pass", "warn", "fail", "not_applicable", "not_run")
    }
    blocking_count = sum(1 for finding in findings if finding["blocking"])
    if counts["fail"]:
        status = "fail"
    elif counts["warn"] or counts["not_run"]:
        status = "warn"
    else:
        status = "pass"
    return {
        "schema_version": "1.0",
        "migration_run_id": _text(payload.get("migration_run_id")),
        "model": _text(payload.get("model")) or _text(after.get("model")),
        "status": status,
        "summary": {
            "total_findings": len(findings),
            "passed": counts["pass"],
            "warnings": counts["warn"],
            "failed": counts["fail"],
            "not_applicable": counts["not_applicable"],
            "not_run": counts["not_run"],
            "blocking_findings": blocking_count,
        },
        "findings": findings,
    }


def _blocking_seo_finding(seo_health: Mapping[str, Any]) -> dict[str, Any]:
    if not seo_health:
        return _finding(
            "seo_health.blocking_failures",
            "not_run",
            message="Current SEO-health output was not supplied.",
        )
    summary = _mapping(seo_health.get("summary"))
    failed_checks = sorted(
        _text(check.get("id"))
        for check in _mapping_list(seo_health.get("checks"))
        if check.get("status") == "fail" and bool(check.get("blocks_publish"))
    )
    count = _integer(summary.get("blocking_failures"))
    blocking_count = max(count or 0, len(failed_checks))
    if blocking_count:
        evidence = failed_checks or [f"blocking_failure_count:{blocking_count}"]
        return _finding(
            "seo_health.blocking_failures",
            "fail",
            blocking=True,
            message=f"SEO health has {blocking_count} blocking failure(s).",
            evidence=evidence,
            observed=blocking_count,
            expected=0,
        )
    return _finding(
        "seo_health.blocking_failures",
        "pass",
        message="SEO health has no blocking failures.",
        observed=0,
        expected=0,
    )


def _score_regression_finding(
    seo_health: Mapping[str, Any], baseline_seo_health: Mapping[str, Any]
) -> dict[str, Any]:
    current = _number(seo_health.get("score")) if seo_health else None
    baseline = (
        _number(baseline_seo_health.get("score")) if baseline_seo_health else None
    )
    if current is None or baseline is None:
        return _finding(
            "seo_health.score_regression",
            "not_run",
            message="Before and after SEO-health scores were not both supplied.",
        )
    delta = current - baseline
    if delta < 0:
        return _finding(
            "seo_health.score_regression",
            "warn",
            message="SEO-health score regressed after rollout.",
            observed=_number_output(current),
            expected=f">={_number_output(baseline)}",
            evidence=[f"score_delta:{_number_output(delta)}"],
        )
    return _finding(
        "seo_health.score_regression",
        "pass",
        message="SEO-health score did not regress.",
        observed=_number_output(current),
        expected=f">={_number_output(baseline)}",
    )


def _slug_change_finding(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    expected_after: Mapping[str, Any],
    approval: Mapping[str, Any],
) -> dict[str, Any]:
    fields = ("seo_keyword", "canonical_url", "product_url")
    comparisons = _field_changes(before, after, fields)
    if comparisons is None:
        return _finding(
            "rollout.unexpected_slug_change",
            "not_run",
            message="Before and after slug/canonical state was not supplied.",
        )
    actual_changes = [change for change in comparisons if change["changed"]]
    unexpected = _unexpected_against_expected(after, expected_after, fields)
    approved = bool(approval.get("approved_slug_change", False))
    if unexpected or (actual_changes and not approved):
        evidence = [
            *_change_evidence(actual_changes),
            *[f"unexpected_after:{item}" for item in unexpected],
            f"approved_slug_change:{str(approved).lower()}",
        ]
        return _finding(
            "rollout.unexpected_slug_change",
            "fail",
            blocking=True,
            message="An unexpected or unapproved slug/canonical change was detected.",
            evidence=evidence,
        )
    return _finding(
        "rollout.unexpected_slug_change",
        "pass",
        message=(
            "Approved slug/canonical changes match the expected state."
            if actual_changes
            else "Published slug and canonical URL remained unchanged."
        ),
        evidence=_change_evidence(actual_changes),
    )


def _unapproved_field_change_finding(
    after: Mapping[str, Any], expected_after: Mapping[str, Any]
) -> dict[str, Any]:
    if not after or not expected_after:
        return _finding(
            "rollout.unapproved_field_change",
            "not_run",
            message="Current and approval-effective catalog state were not both supplied.",
        )
    fields = (
        "name",
        "description",
        "meta_title",
        "meta_description",
        "meta_keywords",
        "category",
        "filters",
        "manufacturer",
        "mpn",
        "ean",
        "gtin",
        "upc",
        "jan",
        "isbn",
        "related_products",
        "status",
        "active",
        "price",
        "quantity",
        "stock_status",
    )
    mismatches = [
        field
        for field in fields
        if field in expected_after
        and _stable_value(after.get(field))
        != _stable_value(expected_after.get(field))
    ]
    if mismatches:
        protected = sorted(
            set(mismatches)
            & {"status", "active", "price", "quantity", "stock_status"}
        )
        return _finding(
            "rollout.unapproved_field_change",
            "fail",
            blocking=True,
            message="Published catalog fields differ from the approval-effective state.",
            observed={field: after.get(field) for field in mismatches},
            expected={field: expected_after.get(field) for field in mismatches},
            evidence=[
                *[f"unexpected_field:{field}" for field in sorted(mismatches)],
                *[f"protected_field_changed:{field}" for field in protected],
            ],
        )
    return _finding(
        "rollout.unapproved_field_change",
        "pass",
        message="All monitored catalog fields match the approval-effective state.",
    )


def _image_change_finding(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    expected_after: Mapping[str, Any],
    approval: Mapping[str, Any],
) -> dict[str, Any]:
    fields = ("image", "main_image", "additional_image", "additional_images")
    comparisons = _field_changes(before, after, fields)
    if comparisons is None:
        return _finding(
            "rollout.image_path_regression",
            "not_run",
            message="Before and after image-path state was not supplied.",
        )
    actual_changes = [change for change in comparisons if change["changed"]]
    unexpected = _unexpected_against_expected(after, expected_after, fields)
    approved = bool(approval.get("approved_image_path_change", False))
    if unexpected or (actual_changes and not approved):
        evidence = [
            *_change_evidence(actual_changes),
            *[f"unexpected_after:{item}" for item in unexpected],
            f"approved_image_path_change:{str(approved).lower()}",
        ]
        return _finding(
            "rollout.image_path_regression",
            "fail",
            blocking=True,
            message="An unexpected or unapproved image-path change was detected.",
            evidence=evidence,
        )
    return _finding(
        "rollout.image_path_regression",
        "pass",
        message=(
            "Approved image-path changes match the expected state."
            if actual_changes
            else "Published image paths remained unchanged."
        ),
        evidence=_change_evidence(actual_changes),
    )


def _identifier_finding(
    after: Mapping[str, Any], *, contract: str
) -> dict[str, Any]:
    if not after:
        return _finding(
            "identifiers.missing",
            "not_run",
            message="Published identifier state was not supplied.",
        )
    mpn = _text(after.get("mpn"))
    gtin = _first_text(after, "gtin14", "gtin13", "gtin12", "gtin8", "gtin", "ean", "upc")
    normalized_contract = contract.strip().casefold().replace("-", "_")
    if not mpn:
        return _finding(
            "identifiers.missing",
            "fail",
            message="The published MPN is missing.",
            observed={"mpn": "", "gtin": gtin},
            expected={"mpn": "non-empty", "identifier_contract": normalized_contract},
            evidence=["mpn_missing"],
        )
    if not gtin and normalized_contract == "mpn_only":
        return _finding(
            "identifiers.missing",
            "warn",
            message="GTIN is missing but remains report-only under the MPN-only contract.",
            observed={"mpn": mpn, "gtin": ""},
            expected={"mpn": "non-empty", "gtin": "optional"},
            evidence=["gtin_missing_report_only", "identifier_contract:mpn_only"],
        )
    if not gtin:
        return _finding(
            "identifiers.missing",
            "fail",
            message="The configured identifier contract requires a GTIN.",
            observed={"mpn": mpn, "gtin": ""},
            expected={"gtin": "non-empty", "identifier_contract": normalized_contract},
            evidence=["gtin_missing"],
        )
    return _finding(
        "identifiers.missing",
        "pass",
        message="Required published identifiers are available.",
        observed={"mpn": mpn, "gtin": gtin},
        expected={"identifier_contract": normalized_contract},
    )


def _price_schema_finding(
    payload: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, Any]:
    price = _first_present(payload, "catalog_price", "price")
    if price is None:
        price = _first_present(after, "price")
    structured_data, structured_supplied = _structured_data(payload, after)
    if price is None:
        return _finding(
            "structured_data.price_schema_mismatch",
            "not_run",
            message="Published catalog price was not supplied.",
        )
    if not structured_supplied or not structured_data:
        return _finding(
            "structured_data.price_schema_mismatch",
            "not_run",
            message="Structured Product data was unavailable for price comparison.",
        )
    offer = _first_offer(structured_data)
    offer_price = _first_present(offer, "price", "lowPrice")
    if _decimal(price) is None or _decimal(offer_price) is None:
        return _finding(
            "structured_data.price_schema_mismatch",
            "fail",
            message="Catalog and structured-data prices could not both be validated.",
            observed={"catalog_price": price, "offer_price": offer_price},
            expected="matching numeric prices",
            evidence=["price_unavailable_or_invalid"],
        )
    mismatches: list[str] = []
    if _decimal(price) != _decimal(offer_price):
        mismatches.append("offer_price_mismatch")

    expected_availability = _normalize_availability(
        _first_present(after, "availability", "offer_availability")
    )
    offer_availability = _normalize_availability(
        _first_present(offer, "availability")
    )
    if expected_availability and offer_availability != expected_availability:
        mismatches.append("offer_availability_mismatch")

    if mismatches:
        return _finding(
            "structured_data.price_schema_mismatch",
            "fail",
            message="Structured-data Offer values do not match the published catalog state.",
            observed={
                "catalog_price": _decimal_output(price),
                "offer_price": _decimal_output(offer_price),
                "catalog_availability": expected_availability,
                "offer_availability": offer_availability,
            },
            expected="matching price and availability",
            evidence=mismatches,
        )
    return _finding(
        "structured_data.price_schema_mismatch",
        "pass",
        message="Structured-data Offer values match the published catalog state.",
        observed={
            "catalog_price": _decimal_output(price),
            "offer_price": _decimal_output(offer_price),
            "catalog_availability": expected_availability,
            "offer_availability": offer_availability,
        },
    )


def _structured_artifact_finding(
    payload: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, Any]:
    artifacts_supplied = "structured_artifacts" in payload or "structured_artifacts" in after
    artifacts = _mapping(payload.get("structured_artifacts")) or _mapping(
        after.get("structured_artifacts")
    )
    production = _mapping(artifacts.get("production"))
    if production:
        production_status = _text(production.get("status"))
        if production_status == "not_run" or production.get("available") is None:
            return _finding(
                "structured_data.artifact_availability",
                "not_run",
                message=(
                    "Production structured-data availability was not observed; "
                    "candidate and local staged artifacts are review evidence only."
                ),
                observed=_artifact_stage_summary(artifacts),
                expected={"production.product_structured_data": True},
                evidence=["production_consumer_not_run"],
            )
        if production_status == "fail" or production.get("available") is False:
            return _finding(
                "structured_data.artifact_availability",
                "fail",
                message="Live validation did not find Product structured data in production.",
                observed=_artifact_stage_summary(artifacts),
                expected={"production.product_structured_data": True},
                evidence=["unavailable:product_structured_data"],
            )
        # Only the live-observed namespace may prove production availability.
        artifacts = production

    structured_data, structured_supplied = _structured_data(payload, after)
    supplied = artifacts_supplied or structured_supplied
    if not supplied:
        return _finding(
            "structured_data.artifact_availability",
            "not_run",
            message="Structured artifact availability was not supplied.",
        )

    required_raw = payload.get("required_structured_artifacts")
    required = (
        sorted({_text(item) for item in required_raw if _text(item)})
        if isinstance(required_raw, list)
        else ["product_structured_data"]
    )
    availability: dict[str, bool] = {}
    for name in required:
        if name in {"product_structured_data", "structured_data"}:
            # An explicit artifact availability record is authoritative.  Do
            # not let an independently supplied JSON-LD mapping mask
            # ``{"available": false}`` from the artifact producer.
            value = artifacts.get(name) if name in artifacts else structured_data
        else:
            value = artifacts.get(name)
        availability[name] = _artifact_available(value)
    missing = sorted(name for name, available in availability.items() if not available)
    if missing:
        return _finding(
            "structured_data.artifact_availability",
            "fail",
            message="Required structured-data artifacts are unavailable.",
            observed=availability,
            expected={name: True for name in required},
            evidence=[f"unavailable:{name}" for name in missing],
        )
    return _finding(
        "structured_data.artifact_availability",
        "pass",
        message="Required structured-data artifacts are available.",
        observed=availability,
        expected={name: True for name in required},
    )


def _duplicate_content_finding(
    payload: Mapping[str, Any],
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    seo_health: Mapping[str, Any],
    baseline_seo_health: Mapping[str, Any],
) -> dict[str, Any]:
    baseline = _duplicate_count(
        _mapping(payload.get("baseline_metrics")) or before,
        baseline_seo_health,
    )
    current = _duplicate_count(
        _mapping(payload.get("metrics")) or after,
        seo_health,
    )
    if baseline is None or current is None:
        return _finding(
            "content.duplicate_increase",
            "not_run",
            message="Before and after duplicate-content metrics were not both supplied.",
        )
    if current > baseline:
        return _finding(
            "content.duplicate_increase",
            "warn",
            message="Duplicate-content findings increased after rollout.",
            observed=current,
            expected=f"<={baseline}",
            evidence=[f"duplicate_delta:{current - baseline}"],
        )
    return _finding(
        "content.duplicate_increase",
        "pass",
        message="Duplicate-content findings did not increase.",
        observed=current,
        expected=f"<={baseline}",
    )


def _live_validation_finding(
    live_validation: Mapping[str, Any]
) -> dict[str, Any]:
    if not live_validation:
        return _finding(
            "rollout.live_validation",
            "not_run",
            message="Live validation output was not supplied.",
        )
    checks = _mapping_list(live_validation.get("checks"))
    failed = sorted(
        _text(check.get("id")) for check in checks if check.get("status") == "fail"
    )
    not_run = sorted(
        _text(check.get("id")) for check in checks if check.get("status") == "not_run"
    )
    coverage = _mapping(live_validation.get("coverage")).get("percentage")
    if failed:
        return _finding(
            "rollout.live_validation",
            "fail",
            message="One or more live validation checks failed.",
            observed={"failed": len(failed), "coverage": coverage},
            expected={"failed": 0},
            evidence=failed,
        )
    if not_run:
        return _finding(
            "rollout.live_validation",
            "warn",
            message="Live validation coverage is reduced because checks were not run.",
            observed={"not_run": len(not_run), "coverage": coverage},
            expected={"not_run": 0, "coverage": 100},
            evidence=not_run,
        )
    return _finding(
        "rollout.live_validation",
        "pass",
        message="Live validation completed without failed checks.",
        observed={"failed": 0, "coverage": coverage},
        expected={"failed": 0},
    )


def _rollback_finding(payload: Mapping[str, Any]) -> dict[str, Any]:
    applied = _applied_state(payload)
    has_manifest_key = "rollback_manifest" in payload
    manifest = _mapping(payload.get("rollback_manifest"))
    if applied is False:
        return _finding(
            "rollout.rollback_availability",
            "not_applicable",
            message="No apply occurred; rollback availability is not applicable.",
        )
    if not has_manifest_key and applied is None:
        return _finding(
            "rollout.rollback_availability",
            "not_run",
            message="Apply state and rollback manifest were not supplied.",
        )
    available = bool(manifest) and manifest.get("available", True) is not False
    complete = bool(manifest) and manifest.get("complete", True) is not False
    if not available or not complete:
        evidence = []
        if not manifest:
            evidence.append("rollback_manifest_missing")
        if manifest and not available:
            evidence.append("rollback_unavailable")
        if manifest and not complete:
            evidence.append("rollback_manifest_incomplete")
        return _finding(
            "rollout.rollback_availability",
            "fail",
            blocking=True,
            message="Rollback is not available for the applied migration.",
            observed={"available": available, "complete": complete},
            expected={"available": True, "complete": True},
            evidence=evidence,
        )
    return _finding(
        "rollout.rollback_availability",
        "pass",
        message="Rollback is available for the applied migration.",
        observed={"available": True, "complete": True},
        expected={"available": True, "complete": True},
    )


def _finding(
    finding_id: str,
    status: str,
    *,
    blocking: bool = False,
    message: str,
    observed: Any = None,
    expected: Any = None,
    evidence: Iterable[Any] = (),
) -> dict[str, Any]:
    severity = (
        "blocker"
        if blocking
        else "error"
        if status == "fail"
        else "warning"
        if status == "warn"
        else "info"
    )
    return {
        "id": finding_id,
        "status": status,
        "severity": severity,
        "blocking": bool(blocking),
        "message": message,
        "observed": observed,
        "expected": expected,
        "evidence": list(evidence),
    }


def _field_changes(
    before: Mapping[str, Any], after: Mapping[str, Any], fields: Iterable[str]
) -> list[dict[str, Any]] | None:
    if not before or not after:
        return None
    result = []
    for field in fields:
        before_present = field in before
        after_present = field in after
        if not before_present and not after_present:
            continue
        old = _stable_value(before.get(field))
        new = _stable_value(after.get(field))
        result.append({"field": field, "before": old, "after": new, "changed": old != new})
    return result


def _unexpected_against_expected(
    after: Mapping[str, Any], expected_after: Mapping[str, Any], fields: Iterable[str]
) -> list[str]:
    if not expected_after:
        return []
    result = []
    for field in fields:
        if field not in expected_after:
            continue
        if _stable_value(after.get(field)) != _stable_value(expected_after.get(field)):
            result.append(field)
    return sorted(result)


def _change_evidence(changes: Iterable[Mapping[str, Any]]) -> list[str]:
    return [
        f"{_text(change.get('field'))}:{_text(change.get('before'))}->{_text(change.get('after'))}"
        for change in changes
    ]


def _structured_data(
    payload: Mapping[str, Any], after: Mapping[str, Any]
) -> tuple[Mapping[str, Any], bool]:
    artifacts = _mapping(payload.get("structured_artifacts")) or _mapping(
        after.get("structured_artifacts")
    )
    direct_candidates = (
        (payload, "structured_data"),
        (payload, "product_structured_data"),
        (after, "structured_data"),
        (after, "product_structured_data"),
    )
    production = _mapping(artifacts.get("production"))
    if production:
        if (
            _text(production.get("status")) == "not_run"
            or production.get("available") is None
        ):
            return {}, False
        value = production.get("product_structured_data")
        return (value if isinstance(value, Mapping) else {}), True

    direct_supplied = any(key in mapping for mapping, key in direct_candidates)
    for mapping, key in direct_candidates:
        value = mapping.get(key)
        if isinstance(value, Mapping):
            return value, direct_supplied

    legacy_candidates = (
        (artifacts, "product_structured_data"),
        (artifacts, "structured_data"),
    )
    supplied = any(key in mapping for mapping, key in legacy_candidates)
    for mapping, key in legacy_candidates:
        value = mapping.get(key)
        if isinstance(value, Mapping):
            return value, supplied
    return {}, supplied


def _artifact_stage_summary(artifacts: Mapping[str, Any]) -> dict[str, Any]:
    candidate = _mapping(artifacts.get("candidate"))
    staged = _mapping(artifacts.get("staged"))
    production = _mapping(artifacts.get("production"))
    return {
        "candidate_available": candidate.get("available"),
        "staged_available": staged.get("available"),
        "production_available": production.get("available"),
        "production_source": production.get("source"),
    }


def _first_offer(structured_data: Mapping[str, Any]) -> Mapping[str, Any]:
    offers = structured_data.get("offers")
    if isinstance(offers, Mapping):
        return offers
    if isinstance(offers, list):
        return next((item for item in offers if isinstance(item, Mapping)), {})
    return {}


def _artifact_available(value: Any) -> bool:
    if isinstance(value, Mapping):
        return bool(value) and value.get("available", True) is not False
    if isinstance(value, (str, list, tuple)):
        return bool(value)
    return value is True


def _duplicate_count(
    metrics: Mapping[str, Any], seo_health: Mapping[str, Any]
) -> int | None:
    for key in (
        "duplicate_content_count",
        "duplicate_count",
        "catalog_duplicate_count",
    ):
        if key in metrics:
            return _integer(metrics.get(key))
    if seo_health and "checks" in seo_health:
        relevant = [
            check
            for check in _mapping_list(seo_health.get("checks"))
            if any(
                token in _text(check.get("id"))
                for token in ("duplicate", "uniqueness", "catalog_uniqueness")
            )
        ]
        evaluated = [
            check
            for check in relevant
            if check.get("status") in {"pass", "warn", "fail"}
        ]
        if not evaluated:
            return None
        return sum(
            1
            for check in evaluated
            if check.get("status") in {"warn", "fail"}
        )
    return None


def _applied_state(payload: Mapping[str, Any]) -> bool | None:
    if isinstance(payload.get("applied"), bool):
        return bool(payload.get("applied"))
    if bool(payload.get("dry_run", False)):
        return False
    mode = _text(payload.get("mode")).casefold()
    status = _text(payload.get("apply_status")).casefold()
    if mode == "apply" or status in {"applied", "succeeded", "completed"}:
        return True
    if mode in {"dry_run", "dry-run"} or status in {"not_applied", "skipped"}:
        return False
    return None


def _first_mapping(payload: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
    return next(
        (
            value
            for key in keys
            for value in [payload.get(key)]
            if isinstance(value, Mapping)
        ),
        {},
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _first_present(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if key in mapping and _present(value):
            return value
    return None


def _first_text(mapping: Mapping[str, Any], *keys: str) -> str:
    return _text(_first_present(mapping, *keys))


def _stable_value(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_stable_value(item) for item in value)
    if isinstance(value, Mapping):
        return tuple(
            (str(key), _stable_value(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    return _text(value)


def _number(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _number_output(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral() else float(value)


def _decimal(value: Any) -> Decimal | None:
    text = _text(value).replace("\u00a0", "").replace(" ", "")
    text = re.sub(r"[^0-9,.-]", "", text)
    if not text:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _decimal_output(value: Any) -> str:
    parsed = _decimal(value)
    return format(parsed.normalize(), "f") if parsed is not None else ""


def _normalize_availability(value: Any) -> str:
    text = _text(value).casefold().rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[^a-z0-9]+", "", text)


def _integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _present(value: Any) -> bool:
    return value is not None and value != ""
