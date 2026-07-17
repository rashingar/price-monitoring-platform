from __future__ import annotations

"""Phase 1 SEO health evaluation and publish-gate calculation."""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import re
from typing import Any, Iterable, Mapping

from .normalize import normalize_for_match, normalize_whitespace
from .seo_identity import meta_title_length_status, valid_seo_keyword
from .normalize import slugify_greek_for_seo
from .product_identity import normalize_mpn_for_match


RULESET_VERSION = "phase1.0"
FULL_RULESET_VERSION = "full.1.0"
DEFAULT_ENFORCEMENT_MODE = "blockers_only"
DEFAULT_THRESHOLDS = {
    "minimum_score": 80,
    "minimum_coverage": 100,
    "blocking_failures_must_be_zero": True,
}

CHECK_WEIGHTS: tuple[tuple[str, str, int], ...] = (
    ("identity.brand_present", "identity", 3),
    ("identity.primary_identifier_present", "identity", 4),
    ("identity.commercial_series_preserved", "identity", 6),
    ("identity.model_pair_preserved", "identity", 4),
    ("identity.category_phrase_present", "identity", 3),
    ("identity.air_conditioner_capabilities_consistent", "identity", 4),
    ("meta_title.present", "meta_title", 2),
    ("meta_title.suffix", "meta_title", 2),
    ("meta_title.identity", "meta_title", 5),
    ("meta_title.search_intent", "meta_title", 4),
    ("meta_title.length", "meta_title", 5),
    ("meta_title.no_repetition", "meta_title", 2),
    ("meta_description.present", "meta_description", 2),
    ("meta_description.length", "meta_description", 5),
    ("meta_description.identity", "meta_description", 4),
    ("meta_description.verified_differentiators", "meta_description", 4),
    ("meta_description.complete_sentence", "meta_description", 2),
    ("meta_description.no_unsupported_numeric_claims", "meta_description", 3),
    ("seo_keyword.present", "seo_keyword", 2),
    ("seo_keyword.syntax", "seo_keyword", 4),
    ("seo_keyword.published_lock", "seo_keyword", 7),
    ("seo_keyword.identity", "seo_keyword", 4),
    ("seo_keyword.no_mutable_terms", "seo_keyword", 3),
    ("seo_keyword.unique_in_context", "seo_keyword", 2),
    ("technical.btu_normalized", "technical", 3),
    ("technical.energy_pair_consistent", "technical", 4),
    ("technical.capability_evidence", "technical", 3),
    ("contract.meta_keywords_optional", "contract", 2),
    ("contract.llm_ownership_respected", "contract", 2),
)

assert sum(weight for _, _, weight in CHECK_WEIGHTS) == 100

CHECK_DESCRIPTIONS = {
    "identity.brand_present": "A deterministic brand is present.",
    "identity.primary_identifier_present": "A deterministic primary identifier is present.",
    "identity.commercial_series_preserved": "Verified commercial series is preserved.",
    "identity.model_pair_preserved": "Verified indoor/outdoor model pair is preserved.",
    "identity.category_phrase_present": "The category phrase is present.",
    "identity.air_conditioner_capabilities_consistent": "A/C capability displays agree with verified three-state evidence.",
    "meta_title.present": "Meta title is present.",
    "meta_title.suffix": "Meta title has the store suffix.",
    "meta_title.identity": "Meta title retains deterministic identity.",
    "meta_title.search_intent": "Meta title includes a category or primary specification.",
    "meta_title.length": "Meta title fits the configured length bands.",
    "meta_title.no_repetition": "Meta title does not repeat components.",
    "meta_description.present": "Meta description is present.",
    "meta_description.length": "Meta description fits Phase 1 length bands.",
    "meta_description.identity": "Meta description includes required identity.",
    "meta_description.verified_differentiators": "Meta description includes verified differentiators.",
    "meta_description.complete_sentence": "Meta description ends as a complete sentence.",
    "meta_description.no_unsupported_numeric_claims": "Meta description numeric claims have deterministic evidence.",
    "seo_keyword.present": "SEO keyword is present.",
    "seo_keyword.syntax": "SEO keyword follows the stable slug syntax.",
    "seo_keyword.published_lock": "Published SEO keyword remains locked.",
    "seo_keyword.identity": "SEO keyword contains deterministic identity.",
    "seo_keyword.no_mutable_terms": "SEO keyword excludes mutable commercial terms.",
    "seo_keyword.unique_in_context": "SEO keyword has no catalog-context collision.",
    "technical.btu_normalized": "A/C BTU is normalized when verified.",
    "technical.energy_pair_consistent": "A/C energy data matches verified evidence.",
    "technical.capability_evidence": "A/C displayed capabilities have explicit evidence.",
    "contract.meta_keywords_optional": "The compatibility meta-keyword field may be empty.",
    "contract.llm_ownership_respected": "LLM output did not control deterministic identity fields.",
}

PHASE2_CHECK_DESCRIPTIONS = {
    "images.main_present": "A main product image is present.",
    "images.main_jpeg_valid": "The main product image bytes are JPEG.",
    "images.gallery_filename_policy": "New gallery filenames follow the stable JPG policy.",
    "images.gallery_sequence": "Gallery positions are contiguous and start at one.",
    "images.gallery_unique_paths": "Gallery public paths are unique.",
    "images.gallery_alt_quality": "Gallery images have meaningful distinct alt text.",
    "images.description_alt_quality": "Description image alts describe supported section features.",
    "content.single_h1_contract": "Description HTML does not create an additional H1.",
    "content.description_heading_distinct": "The supporting description heading differs from the product name.",
    "content.intro_catalog_uniqueness": "Introductory prose is sufficiently unique in catalog context.",
    "content.meta_description_catalog_uniqueness": "Meta description is sufficiently unique in catalog context.",
    "internal_linking.category_link": "A canonical category CTA link is available.",
    "internal_linking.related_products": "Deterministic related products are available when catalog context permits.",
}

PHASE3_CHECKS: tuple[tuple[str, str, float, str], ...] = (
    ("identity.internal_model_present", "identity", 0, "The internal OpenCart model is present."),
    ("identity.brand_present_phase3", "identity", 1, "The MPN identity has a manufacturer brand."),
    ("identity.mpn_present", "identity", 2, "The identity includes an MPN."),
    ("identity.mpn_verified", "identity", 2, "The selected MPN is verified evidence."),
    ("identity.mpn_not_internal_code", "identity", 0, "The MPN is not substituted with the internal model."),
    ("identity.mpn_scope_valid", "identity", 1, "The MPN has a supported product scope."),
    ("identity.complete_set_preserved", "identity", 1, "A sellable A/C set remains a complete-set identity."),
    ("identity.component_models_preserved", "identity", 0, "Verified indoor/outdoor component models are retained."),
    ("identity.no_component_set_conflict", "identity", 1, "No component identifier conflicts with a complete-set MPN."),
    ("identity.consistent_across_outputs", "identity", 1, "MPN identity agrees with the CSV and compact identity fields."),
    ("identity.provenance_present", "identity", 1, "Selected MPN provenance is present."),
    ("structured_data.product_json_valid", "structured_data", 1, "The Product structured-data candidate is valid."),
    ("structured_data.schema_type_product", "structured_data", 1, "Structured data declares schema.org Product."),
    ("structured_data.name_present", "structured_data", 0, "Structured data includes a product name."),
    ("structured_data.brand_matches", "structured_data", 1, "Structured-data brand matches product identity."),
    ("structured_data.sku_matches_internal_model", "structured_data", 1, "Structured-data SKU matches the internal model."),
    ("structured_data.mpn_matches_verified_identity", "structured_data", 1, "Structured-data MPN matches verified identity."),
    ("structured_data.url_matches_canonical", "structured_data", 0, "Structured-data URL matches the canonical product URL."),
    ("structured_data.images_present", "structured_data", 0, "Structured data includes final public image URLs."),
    ("structured_data.offer_consistent", "structured_data", 1, "Structured-data offer is consistent when present."),
    ("structured_data.forbidden_identifier_fields_absent", "structured_data", 0, "Structured data has no unsupported identifier fields."),
    ("feed.feed_json_valid", "feed", 1, "The product-feed candidate is valid."),
    ("feed.id_matches_internal_model", "feed", 0, "Feed id matches the internal model."),
    ("feed.brand_matches", "feed", 0, "Feed brand matches product identity."),
    ("feed.mpn_matches_verified_identity", "feed", 1, "Feed MPN matches verified identity."),
    ("feed.identifier_mode_mpn_only", "feed", 1, "Feed uses exactly the MPN-only identifier mode."),
    ("feed.price_and_availability_consistent", "feed", 1, "Feed price and availability are internally consistent."),
    ("feed.forbidden_identifier_fields_absent", "feed", 0, "Feed has no unsupported identifier fields."),
)

assert sum(weight for _, _, weight, _ in PHASE3_CHECKS) == 20


# The Phase 1 profile above is an established compatibility contract and keeps
# its original 29 checks/100 points.  The full profile is a separate rollout
# view: it aggregates those deterministic subchecks (plus Phase 2/3/4
# subchecks) into the exact cross-phase groups approved for production rollout.
FULL_PROFILE_CHECK_WEIGHTS: tuple[tuple[str, int, int], ...] = (
    ("identity.completeness", 1, 8),
    ("identity.series_and_models", 1, 6),
    ("identity.capabilities_consistent", 1, 4),
    ("meta_title.quality", 1, 8),
    ("meta_description.quality", 1, 8),
    ("seo_keyword.valid_and_stable", 1, 8),
    ("contract.deterministic_ownership", 1, 3),
    ("images.gallery_filename_policy", 2, 5),
    ("images.path_sequence_and_format", 2, 4),
    ("images.alt_quality", 2, 4),
    ("content.heading_structure", 2, 2),
    ("internal_linking.related_and_category", 2, 3),
    ("content.catalog_uniqueness", 2, 2),
    ("identifiers.validity_and_provenance", 3, 5),
    ("structured_data.product_completeness", 3, 5),
    ("structured_data.offer_consistency", 3, 5),
    ("merchant.validation", 3, 5),
    ("rollout.migration_safety", 4, 5),
    ("rollout.redirect_and_canonical_coverage", 4, 4),
    ("rollout.production_validation", 4, 3),
    ("rollout.monitoring_and_rollback", 4, 3),
)

assert len(FULL_PROFILE_CHECK_WEIGHTS) == 21
assert sum(weight for _, _, weight in FULL_PROFILE_CHECK_WEIGHTS) == 100
assert {
    phase: sum(weight for _, check_phase, weight in FULL_PROFILE_CHECK_WEIGHTS if check_phase == phase)
    for phase in (1, 2, 3, 4)
} == {1: 45, 2: 20, 3: 20, 4: 15}


FULL_PROFILE_GROUP_METADATA: dict[str, dict[str, Any]] = {
    "identity.completeness": {
        "category": "identity",
        "description": "Required product identity and primary specification evidence are complete.",
        "subchecks": (
            "identity.brand_present",
            "identity.primary_identifier_present",
            "identity.category_phrase_present",
            "technical.btu_normalized",
        ),
    },
    "identity.series_and_models": {
        "category": "identity",
        "description": "Verified commercial series and model relationships are preserved.",
        "subchecks": (
            "identity.commercial_series_preserved",
            "identity.model_pair_preserved",
        ),
    },
    "identity.capabilities_consistent": {
        "category": "identity",
        "description": "Displayed capabilities and energy claims agree with deterministic evidence.",
        "subchecks": (
            "identity.air_conditioner_capabilities_consistent",
            "technical.energy_pair_consistent",
            "technical.capability_evidence",
        ),
    },
    "meta_title.quality": {
        "category": "meta_title",
        "description": "Meta title identity, intent, suffix, length, and repetition checks pass.",
        "subchecks": tuple(check_id for check_id, _, _ in CHECK_WEIGHTS if check_id.startswith("meta_title.")),
    },
    "meta_description.quality": {
        "category": "meta_description",
        "description": "Meta description identity, length, claims, and sentence-quality checks pass.",
        "subchecks": tuple(check_id for check_id, _, _ in CHECK_WEIGHTS if check_id.startswith("meta_description.")),
    },
    "seo_keyword.valid_and_stable": {
        "category": "seo_keyword",
        "description": "SEO keyword syntax, identity, uniqueness, and published lock are stable.",
        "subchecks": tuple(check_id for check_id, _, _ in CHECK_WEIGHTS if check_id.startswith("seo_keyword.")),
    },
    "contract.deterministic_ownership": {
        "category": "contract",
        "description": "Deterministic fields remain code-owned and compatibility metadata stays optional.",
        "subchecks": tuple(check_id for check_id, _, _ in CHECK_WEIGHTS if check_id.startswith("contract.")),
    },
    "images.gallery_filename_policy": {
        "category": "images",
        "description": "Gallery assets are present, valid JPEGs, and follow the candidate filename policy.",
        "subchecks": (
            "images.main_present",
            "images.main_jpeg_valid",
            "images.gallery_filename_policy",
        ),
    },
    "images.path_sequence_and_format": {
        "category": "images",
        "description": "Gallery paths are unique and positions form a valid ordered sequence.",
        "subchecks": (
            "images.gallery_sequence",
            "images.gallery_unique_paths",
        ),
    },
    "images.alt_quality": {
        "category": "images",
        "description": "Gallery and description-image alternative text is meaningful and evidence-based.",
        "subchecks": (
            "images.gallery_alt_quality",
            "images.description_alt_quality",
        ),
    },
    "content.heading_structure": {
        "category": "content",
        "description": "Description headings respect the storefront H1 contract and remain distinct.",
        "subchecks": (
            "content.single_h1_contract",
            "content.description_heading_distinct",
        ),
    },
    "internal_linking.related_and_category": {
        "category": "internal_linking",
        "description": "Canonical category and deterministic related-product links are available.",
        "subchecks": (
            "internal_linking.category_link",
            "internal_linking.related_products",
        ),
    },
    "content.catalog_uniqueness": {
        "category": "content",
        "description": "Introductory and meta-description content remain unique in catalog context.",
        "subchecks": (
            "content.intro_catalog_uniqueness",
            "content.meta_description_catalog_uniqueness",
        ),
    },
    "identifiers.validity_and_provenance": {
        "category": "identifiers",
        "description": "Internal model and supported MPN identity are valid, consistent, and sourced.",
        "subchecks": tuple(check_id for check_id, _, _, _ in PHASE3_CHECKS if check_id.startswith("identity.")),
    },
    "structured_data.product_completeness": {
        "category": "structured_data",
        "description": "Product structured data is complete and consistent with canonical product identity.",
        "subchecks": tuple(
            check_id
            for check_id, _, _, _ in PHASE3_CHECKS
            if check_id.startswith("structured_data.") and check_id != "structured_data.offer_consistent"
        ),
    },
    "structured_data.offer_consistency": {
        "category": "structured_data",
        "description": "Structured-data Offer values are internally consistent when available.",
        "subchecks": ("structured_data.offer_consistent",),
    },
    "merchant.validation": {
        "category": "feed",
        "description": "Merchant/feed candidate identity, price, availability, and field policy validate.",
        "subchecks": tuple(check_id for check_id, _, _, _ in PHASE3_CHECKS if check_id.startswith("feed.")),
    },
    "rollout.migration_safety": {
        "category": "rollout",
        "description": "Snapshot, approval, field scope, and rollback preconditions make migration reversible.",
        "subchecks": (),
    },
    "rollout.redirect_and_canonical_coverage": {
        "category": "rollout",
        "description": "Slug changes, redirects, and canonical updates are approved and fully accounted for.",
        "subchecks": (),
    },
    "rollout.production_validation": {
        "category": "rollout",
        "description": "Configured production validation checks completed successfully.",
        "subchecks": (),
    },
    "rollout.monitoring_and_rollback": {
        "category": "rollout",
        "description": "Post-rollout monitoring and verified rollback coverage are available.",
        "subchecks": (),
    },
}


def round_half_up(value: Decimal | float | int) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_score(checks: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    materialized = list(checks)
    active_weight = sum(Decimal(str(check.get("weight", 0))) for check in materialized)
    evaluated_weight = sum(
        Decimal(str(check.get("weight", 0)))
        for check in materialized
        if check.get("status") != "not_run"
    )
    applicable = [
        check for check in materialized if check.get("status") in {"pass", "warn", "fail"}
    ]
    applicable_weight = sum(Decimal(str(check.get("weight", 0))) for check in applicable)
    earned_weight = sum(Decimal(str(check.get("earned_points", 0))) for check in applicable)
    score = round_half_up(Decimal("100") * earned_weight / applicable_weight) if applicable_weight else 0
    coverage = round_half_up(Decimal("100") * evaluated_weight / active_weight) if active_weight else 0
    counts = {status: 0 for status in ("pass", "warn", "fail", "not_applicable", "not_run")}
    for check in materialized:
        status = str(check.get("status", "not_run"))
        if status in counts:
            counts[status] += 1
    return {
        "score": score,
        "coverage": {
            "active_weight": float(active_weight),
            "evaluated_weight": float(evaluated_weight),
            "percentage": coverage,
        },
        "summary": {
            "total_checks": len(materialized),
            "passed": counts["pass"],
            "warnings": counts["warn"],
            "failed": counts["fail"],
            "not_applicable": counts["not_applicable"],
            "not_run": counts["not_run"],
            "applicable_weight": float(applicable_weight),
            "earned_weight": float(earned_weight),
            "blocking_failures": sum(
                1
                for check in materialized
                if check.get("status") == "fail" and check.get("blocks_publish")
            ),
        },
    }


def grade_for_score(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def evaluate_seo_health(
    *,
    model: str,
    row: Mapping[str, Any],
    deterministic_product: Mapping[str, Any],
    catalog_seo_keywords: Iterable[str] = (),
    settings: Mapping[str, Any] | None = None,
    profile: str = "phase1",
    phase2: Mapping[str, Any] | None = None,
    phase3: Mapping[str, Any] | None = None,
    phase4: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    identity = deterministic_product.get("seo_identity", {})
    identity = identity if isinstance(identity, Mapping) else {}
    air_conditioner = identity.get("family") == "air_conditioner"
    phase1_checks = _evaluate_checks(
        row=row,
        deterministic_product=deterministic_product,
        identity=identity,
        air_conditioner=air_conditioner,
        catalog_seo_keywords=catalog_seo_keywords,
    )
    phase3_settings = (settings or {}).get("phase3", {})
    phase3_settings = phase3_settings if isinstance(phase3_settings, Mapping) else {}
    product_identity = deterministic_product.get("product_identity", {})
    product_identity = product_identity if isinstance(product_identity, Mapping) else {}
    if profile == "full":
        checks = _evaluate_full_profile_checks(
            row=row,
            deterministic_product=deterministic_product,
            phase1_checks=phase1_checks,
            product_identity=product_identity,
            phase2=phase2,
            phase3=phase3,
            phase3_settings=phase3_settings,
            phase4=phase4,
        )
    else:
        # Compatibility path: keep the established Phase 1 profile, including
        # its opt-in Phase 3 rescaling behavior, exactly as it was before the
        # full rollout profile existed.
        checks = phase1_checks
        active_families = {str(value) for value in phase3_settings.get("families", [])}
        phase3_active = bool(phase3_settings.get("enabled", False)) and str(product_identity.get("family_key") or "") in active_families
        if phase3_active:
            checks = _rescale_checks(checks, factor=Decimal("0.8"))
            checks.extend(
                _evaluate_phase3_checks(
                    row=row,
                    product_identity=product_identity,
                    phase3=phase3 or {},
                    require_verified=bool(phase3_settings.get("mpn_require_verified", True)),
                )
            )
    totals = calculate_score(checks)
    gate = _publish_gate(totals, settings)
    return {
        "schema_version": "1.0",
        "ruleset_version": str(
            (settings or {}).get("ruleset_version")
            or (FULL_RULESET_VERSION if profile == "full" else RULESET_VERSION)
        ),
        "profile": profile,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": str(model),
        "seo_keyword": str(row.get("seo_keyword", "") or ""),
        "product_url": str(row.get("product_url", "") or ""),
        "score": totals["score"],
        "grade": grade_for_score(totals["score"]),
        "coverage": totals["coverage"],
        "summary": totals["summary"],
        "publish_gate": gate,
        "checks": checks,
    }


def seo_health_allows_publish(report: Mapping[str, Any]) -> bool:
    gate = report.get("publish_gate", {})
    return bool(gate.get("enforced_allowed", False)) if isinstance(gate, Mapping) else False


def validate_seo_health_contract(report: Mapping[str, Any]) -> list[str]:
    """Dependency-free guard for the checked-in Draft 2020-12 contract."""
    top_level = {
        "schema_version", "ruleset_version", "profile", "generated_at", "model",
        "seo_keyword", "product_url", "score", "grade", "coverage", "summary",
        "publish_gate", "checks",
    }
    errors: list[str] = []
    if set(report) != top_level:
        errors.append("top_level_shape_invalid")
    if report.get("schema_version") != "1.0": errors.append("schema_version_invalid")
    if not re.fullmatch(r"[0-9]{6}", str(report.get("model", ""))): errors.append("model_invalid")
    if report.get("profile") not in {"phase1", "full"}: errors.append("profile_invalid")
    if report.get("grade") not in {"A", "B", "C", "D", "F"}: errors.append("grade_invalid")
    checks = report.get("checks")
    if not isinstance(checks, list): return [*errors, "checks_invalid"]
    expected_check_keys = {"id", "phase", "category", "description", "status", "severity", "blocks_publish", "weight", "earned_points", "message", "observed", "expected", "applicable_reason", "evidence", "remediation"}
    for check in checks:
        if not isinstance(check, Mapping) or set(check) != expected_check_keys:
            errors.append("check_shape_invalid")
            continue
        if not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", str(check.get("id", ""))): errors.append("check_id_invalid")
        if check.get("status") not in {"pass", "warn", "fail", "not_applicable", "not_run"}: errors.append("check_status_invalid")
        if not isinstance(check.get("evidence"), list): errors.append("check_evidence_invalid")
    return errors


def _rescale_checks(checks: Iterable[Mapping[str, Any]], *, factor: Decimal) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for check in checks:
        copy = dict(check)
        copy["weight"] = float(Decimal(str(copy.get("weight", 0))) * factor)
        copy["earned_points"] = float(Decimal(str(copy.get("earned_points", 0))) * factor)
        result.append(copy)
    return result


def _evaluate_checks(
    *,
    row: Mapping[str, Any],
    deterministic_product: Mapping[str, Any],
    identity: Mapping[str, Any],
    air_conditioner: bool,
    catalog_seo_keywords: Iterable[str],
) -> list[dict[str, Any]]:
    brand = _text(deterministic_product.get("brand"))
    primary = _text(identity.get("primary_model")) or _text(deterministic_product.get("mpn"))
    series = _text(identity.get("commercial_series"))
    set_model = _text(identity.get("set_model"))
    category = _text(deterministic_product.get("category_phrase"))
    name = _text(row.get("name"))
    title = _text(row.get("meta_title"))
    description = _text(row.get("meta_description"))
    keyword = _text(row.get("seo_keyword"))
    published = _text(deterministic_product.get("published_seo_keyword"))
    candidate = _text(deterministic_product.get("seo_keyword_candidate"))
    checks: list[dict[str, Any]] = []

    def add(check_id: str, status: str, observed: Any = None, expected: Any = None, *, blocks: bool = False, message: str = "", applicable_reason: str = "") -> None:
        category_name, weight = next((category, weight) for item_id, category, weight in CHECK_WEIGHTS if item_id == check_id)
        severity = "blocker" if blocks and status == "fail" else ("error" if status == "fail" else ("warning" if status == "warn" else "info"))
        earned = weight if status == "pass" else (weight * 0.5 if status == "warn" else 0)
        checks.append({
            "id": check_id,
            "phase": 1,
            "category": category_name,
            "description": CHECK_DESCRIPTIONS[check_id],
            "status": status,
            "severity": severity,
            "blocks_publish": bool(blocks and status == "fail"),
            "weight": weight,
            "earned_points": earned,
            "message": message or status,
            "observed": observed,
            "expected": expected,
            "applicable_reason": applicable_reason,
            "evidence": [],
            "remediation": "Correct deterministic evidence or the LLM-owned meta field, then render again.",
        })

    add("identity.brand_present", "pass" if brand else "fail", brand, "non-empty", blocks=True)
    add("identity.primary_identifier_present", "pass" if primary else "fail", primary, "non-empty", blocks=True)
    if air_conditioner:
        add("identity.commercial_series_preserved", "pass" if not series or _contains(name, series) else "fail", name, series or "no verified series", blocks=bool(series))
        pair_expected = bool(_text(identity.get("indoor_model")) and _text(identity.get("outdoor_model")))
        add("identity.model_pair_preserved", "pass" if not pair_expected or _contains(name, set_model) else "fail", name, set_model or "no verified pair", blocks=pair_expected)
        add("identity.category_phrase_present", "pass" if _contains(name, category) else "fail", name, category, blocks=True)
        displayed = {"inverter": "Inverter", "wifi": "Wi-Fi", "ionizer": "Ιονιστ"}
        inconsistent = [key for key, term in displayed.items() if identity.get(key) is False and _contains(name, term)]
        add("identity.air_conditioner_capabilities_consistent", "fail" if inconsistent else "pass", inconsistent, "no unsupported capability", blocks=bool(inconsistent))
    else:
        for check_id in ("identity.commercial_series_preserved", "identity.model_pair_preserved", "identity.air_conditioner_capabilities_consistent"):
            add(check_id, "not_applicable", applicable_reason="air_conditioner profile is inactive")
        add("identity.category_phrase_present", "pass" if category else "warn", category, "non-empty")

    add("meta_title.present", "pass" if title else "fail", title, "non-empty", blocks=True)
    add("meta_title.suffix", "pass" if title.endswith(" | eTranoulis") else "fail", title, "suffix", blocks=True)
    title_identity = all(_contains(title, value) for value in [brand, primary] if value)
    add("meta_title.identity", "pass" if title_identity else "fail", title, [brand, primary], blocks=not title_identity)
    add("meta_title.search_intent", "pass" if _contains(title, category) or _contains(title, _text(identity.get("btu"))) else "warn", title, [category, identity.get("btu")])
    add("meta_title.length", meta_title_length_status(title), len(title), "<=65 pass; 66-75 warning; >75 fail")
    title_tokens = [normalize_for_match(token) for token in title.removesuffix(" | eTranoulis").split()]
    add("meta_title.no_repetition", "warn" if len(title_tokens) != len(set(title_tokens)) else "pass", title)

    add("meta_description.present", "pass" if description else "fail", description, "non-empty", blocks=True)
    description_status = _meta_description_length_status(description) if air_conditioner else ("pass" if description else "fail")
    add("meta_description.length", description_status, len(description), "130-180 pass; 110-129 warning; otherwise fail", blocks=description_status == "fail" and bool(description))
    identity_required = [brand, series or primary] if air_conditioner else [brand]
    identity_ok = all(_contains(description, value) for value in identity_required if value)
    identity_status = "pass" if identity_ok else ("fail" if air_conditioner else "warn")
    add("meta_description.identity", identity_status, description, identity_required, blocks=air_conditioner and not identity_ok)
    differentiators = _verified_differentiators(identity)
    mentioned = sum(1 for value in differentiators if _contains(description, value))
    required_count = 2 if len(differentiators) >= 2 else len(differentiators)
    differentiator_status = "pass" if not air_conditioner or mentioned >= required_count else "fail"
    add("meta_description.verified_differentiators", differentiator_status, mentioned, required_count, blocks=air_conditioner and differentiator_status == "fail")
    complete = bool(re.search(r"[.!;·;]\s*$", description))
    add("meta_description.complete_sentence", "pass" if complete else "fail", description, "terminal punctuation", blocks=bool(description) and not complete)
    unsupported_numbers = _unsupported_numeric_claims(description, identity)
    numeric_status = "pass" if not unsupported_numbers else ("fail" if air_conditioner else "warn")
    add("meta_description.no_unsupported_numeric_claims", numeric_status, unsupported_numbers, "deterministic numeric evidence", blocks=air_conditioner and bool(unsupported_numbers))

    add("seo_keyword.present", "pass" if keyword else "fail", keyword, "non-empty", blocks=True)
    add("seo_keyword.syntax", "pass" if valid_seo_keyword(keyword) and len(keyword) <= 96 else "fail", keyword, "^[a-z0-9]+(?:-[a-z0-9]+)*$", blocks=True)
    lock_ok = (not published and keyword == candidate) or (bool(published) and keyword == published)
    add("seo_keyword.published_lock", "pass" if lock_ok else "fail", keyword, published or candidate, blocks=not lock_ok)
    keyword_identity = _keyword_identity_ok(keyword, brand, primary)
    add("seo_keyword.identity", "pass" if keyword_identity else "fail", keyword, [brand, primary], blocks=not keyword_identity)
    mutable_terms = [term for term in ("price", "sale", "offer", "availability", "delivery") if term in keyword]
    add("seo_keyword.no_mutable_terms", "pass" if not mutable_terms else "fail", mutable_terms, "no mutable terms")
    catalog = {normalize_whitespace(value) for value in catalog_seo_keywords if normalize_whitespace(value)}
    collision = keyword in (catalog - {published})
    add("seo_keyword.unique_in_context", "fail" if collision else "pass", keyword, "unique", blocks=collision)

    if air_conditioner:
        btu = _text(identity.get("btu"))
        add("technical.btu_normalized", "pass" if not btu or bool(re.fullmatch(r"\d+ BTU", btu)) else "fail", btu, "NNNN BTU")
        cooling, heating = _text(identity.get("cooling_energy_class")), _text(identity.get("heating_energy_class"))
        energy = f"{cooling}/{heating}" if cooling and heating else cooling or heating
        add("technical.energy_pair_consistent", "pass" if not energy or _contains(name, energy) else "fail", name, energy, blocks=bool(energy) and not _contains(name, energy))
        capability_unsupported = any(identity.get(key) is False and _contains(name, term) for key, term in (("inverter", "Inverter"), ("wifi", "Wi-Fi"), ("ionizer", "Ιονιστ")))
        add("technical.capability_evidence", "fail" if capability_unsupported else "pass", capability_unsupported, False, blocks=capability_unsupported)
    else:
        for check_id in ("technical.btu_normalized", "technical.energy_pair_consistent", "technical.capability_evidence"):
            add(check_id, "not_applicable", applicable_reason="air_conditioner profile is inactive")
    add("contract.meta_keywords_optional", "pass", _text(row.get("meta_keyword")), "empty allowed")
    llm_product = deterministic_product.get("llm_product", {})
    identity_keys = {"brand", "mpn", "name", "meta_title", "seo_keyword"}
    llm_controls_identity = isinstance(llm_product, Mapping) and bool(identity_keys & set(llm_product))
    add("contract.llm_ownership_respected", "fail" if llm_controls_identity else "pass", llm_controls_identity, False, blocks=llm_controls_identity)
    return checks


def _evaluate_phase3_checks(
    *,
    row: Mapping[str, Any],
    product_identity: Mapping[str, Any],
    phase3: Mapping[str, Any],
    require_verified: bool,
) -> list[dict[str, Any]]:
    """Evaluate active A/C MPN identity and candidate-artifact consistency."""
    artifacts = phase3 if isinstance(phase3, Mapping) else {}
    structured = artifacts.get("structured_data", {})
    structured = structured if isinstance(structured, Mapping) else {}
    feed = artifacts.get("feed", {})
    feed = feed if isinstance(feed, Mapping) else {}
    artifact_errors = [str(error) for error in artifacts.get("errors", [])]
    structured_enabled = bool(artifacts.get("structured_data_enabled", True))
    feed_enabled = bool(artifacts.get("product_feed_enabled", True))
    mpn = _text(product_identity.get("mpn"))
    internal_model = _text(product_identity.get("internal_model"))
    brand = _text(product_identity.get("brand"))
    status = str(product_identity.get("mpn_status") or "missing")
    scope = str(product_identity.get("mpn_scope") or "unknown")
    components = [_text(value) for value in product_identity.get("component_models", []) if _text(value)]
    primary = _text(product_identity.get("primary_model"))
    set_model = _text(product_identity.get("set_model"))
    commercial_series = _text(product_identity.get("commercial_series"))
    checks: list[dict[str, Any]] = []
    lookup = {check_id: (category, weight, description) for check_id, category, weight, description in PHASE3_CHECKS}

    def add(
        check_id: str,
        check_status: str,
        observed: Any = None,
        expected: Any = None,
        *,
        blocks: bool = False,
        reason: str = "",
    ) -> None:
        category, weight, description = lookup[check_id]
        earned = weight if check_status == "pass" else (weight * .5 if check_status == "warn" else 0)
        checks.append({
            "id": check_id,
            "phase": 3,
            "category": category,
            "description": description,
            "status": check_status,
            "severity": "blocker" if blocks and check_status == "fail" else ("error" if check_status == "fail" else ("warning" if check_status == "warn" else "info")),
            "blocks_publish": bool(blocks and check_status == "fail"),
            "weight": weight,
            "earned_points": earned,
            "message": reason or check_status,
            "observed": observed,
            "expected": expected,
            "applicable_reason": "Phase 3 air-conditioner enforcement is active.",
            "evidence": [],
            "remediation": "Correct MPN evidence or candidate artifact data, then render again.",
        })

    add("identity.internal_model_present", "pass" if internal_model else "fail", internal_model, "6-digit internal model", blocks=True)
    add("identity.brand_present_phase3", "pass" if brand else "fail", brand, "non-empty", blocks=True)
    add("identity.mpn_present", "pass" if mpn else "fail", mpn, "non-empty", blocks=require_verified)
    verified_status = "pass" if status == "verified" else ("fail" if require_verified else "warn")
    add("identity.mpn_verified", verified_status, status, "verified", blocks=require_verified)
    internal_substitution = bool(mpn and normalize_mpn_for_match(mpn) == normalize_mpn_for_match(internal_model))
    add("identity.mpn_not_internal_code", "fail" if internal_substitution else "pass", mpn, internal_model, blocks=internal_substitution)
    add("identity.mpn_scope_valid", "pass" if scope in {"complete_product", "complete_set", "single_unit", "indoor_unit", "outdoor_unit", "component"} else "fail", scope, "supported scope", blocks=True)
    complete_expected = scope == "complete_set" or bool(set_model and len(components) >= 2)
    complete_ok = not complete_expected or (scope == "complete_set" and bool(mpn) and normalize_mpn_for_match(mpn) == normalize_mpn_for_match(set_model) and len(components) >= 2)
    add("identity.complete_set_preserved", "pass" if complete_ok else "fail", {"mpn": mpn, "set_model": set_model}, "verified complete-set MPN", blocks=not complete_ok)
    components_ok = not complete_expected or len(components) >= 2
    add("identity.component_models_preserved", "pass" if components_ok else "fail", components, "indoor and outdoor models", blocks=not components_ok)
    conflict = status == "conflicting" or "complete_set_and_component_identifier_conflict" in [str(value) for value in product_identity.get("warnings", [])]
    add("identity.no_component_set_conflict", "fail" if conflict else "pass", status, "no conflict", blocks=conflict)
    csv_ok = not mpn or normalize_mpn_for_match(mpn) == normalize_mpn_for_match(row.get("mpn", ""))
    compact_ok = not primary or (_contains(_text(row.get("name")), primary) and _contains(_text(row.get("meta_title")), primary))
    slug_ok = not primary or slugify_greek_for_seo(primary) in _text(row.get("seo_keyword"))
    heading = _text(artifacts.get("description_heading"))
    heading_ok = not heading or (_contains(heading, brand) and (_contains(heading, primary) or _contains(heading, commercial_series)))
    outputs_ok = csv_ok and compact_ok and slug_ok and heading_ok
    add("identity.consistent_across_outputs", "pass" if outputs_ok else "fail", {"csv_mpn": row.get("mpn", ""), "primary_model": primary, "description_heading": heading}, "identity-compatible CSV/name/title/slug/heading", blocks=not outputs_ok)
    add("identity.provenance_present", "pass" if _text(product_identity.get("source")) else "fail", product_identity.get("source"), "source", blocks=True)

    def artifact_status(enabled: bool, condition: bool) -> str:
        return "not_applicable" if not enabled else ("pass" if condition else "fail")

    structured_invalid = any(error.startswith("structured_") or error.startswith("forbidden_identifier") for error in artifact_errors)
    add("structured_data.product_json_valid", artifact_status(structured_enabled, bool(structured) and not structured_invalid), artifact_errors, "valid Product JSON", blocks=structured_enabled)
    add("structured_data.schema_type_product", artifact_status(structured_enabled, structured.get("@type") == "Product"), structured.get("@type"), "Product", blocks=structured_enabled)
    add("structured_data.name_present", artifact_status(structured_enabled, bool(_text(structured.get("name")))), structured.get("name"), "non-empty")
    structured_brand = structured.get("brand", {})
    structured_brand_name = _text(structured_brand.get("name")) if isinstance(structured_brand, Mapping) else ""
    add("structured_data.brand_matches", artifact_status(structured_enabled, normalize_for_match(structured_brand_name) == normalize_for_match(brand)), structured_brand_name, brand, blocks=structured_enabled)
    add("structured_data.sku_matches_internal_model", artifact_status(structured_enabled, _text(structured.get("sku")) == internal_model), structured.get("sku"), internal_model, blocks=structured_enabled)
    structured_mpn_ok = (status != "verified" and "mpn" not in structured) or (status == "verified" and normalize_mpn_for_match(structured.get("mpn", "")) == normalize_mpn_for_match(mpn))
    add("structured_data.mpn_matches_verified_identity", artifact_status(structured_enabled, structured_mpn_ok), structured.get("mpn", ""), mpn, blocks=structured_enabled)
    add("structured_data.url_matches_canonical", artifact_status(structured_enabled, _text(structured.get("url")) == _text(row.get("product_url"))), structured.get("url"), row.get("product_url"))
    add("structured_data.images_present", artifact_status(structured_enabled, bool(structured.get("image"))), structured.get("image"), "public image URLs")
    offer_ok = "offers" not in structured or isinstance(structured.get("offers"), Mapping)
    add("structured_data.offer_consistent", artifact_status(structured_enabled, offer_ok), structured.get("offers"), "omitted or valid offer", blocks=structured_enabled)
    add("structured_data.forbidden_identifier_fields_absent", artifact_status(structured_enabled, not any(error.startswith("forbidden_identifier") for error in artifact_errors)), artifact_errors, "no unsupported identifier fields", blocks=structured_enabled)

    feed_invalid = any(error.startswith("feed_") or error.startswith("forbidden_identifier") for error in artifact_errors)
    add("feed.feed_json_valid", artifact_status(feed_enabled, bool(feed) and not feed_invalid), artifact_errors, "valid feed JSON", blocks=feed_enabled)
    add("feed.id_matches_internal_model", artifact_status(feed_enabled, _text(feed.get("id")) == internal_model), feed.get("id"), internal_model)
    add("feed.brand_matches", artifact_status(feed_enabled, normalize_for_match(_text(feed.get("brand"))) == normalize_for_match(brand)), feed.get("brand"), brand)
    feed_mpn_ok = (status != "verified" and "mpn" not in feed) or (status == "verified" and normalize_mpn_for_match(feed.get("mpn", "")) == normalize_mpn_for_match(mpn))
    add("feed.mpn_matches_verified_identity", artifact_status(feed_enabled, feed_mpn_ok), feed.get("mpn", ""), mpn, blocks=feed_enabled)
    add("feed.identifier_mode_mpn_only", artifact_status(feed_enabled, feed.get("identifier_mode") == "mpn_only"), feed.get("identifier_mode"), "mpn_only", blocks=feed_enabled)
    price = feed.get("price")
    price_ok = price is None or (isinstance(price, Mapping) and _text(price.get("value")) and price.get("currency") == "EUR")
    availability_ok = "availability" not in feed or feed.get("availability") in {"in_stock", "out_of_stock"}
    add("feed.price_and_availability_consistent", artifact_status(feed_enabled, price_ok and availability_ok), {"price": price, "availability": feed.get("availability")}, "valid optional price and availability", blocks=feed_enabled)
    add("feed.forbidden_identifier_fields_absent", artifact_status(feed_enabled, not any(error.startswith("forbidden_identifier") for error in artifact_errors)), artifact_errors, "no unsupported identifier fields", blocks=feed_enabled)
    return checks


def _evaluate_phase2_checks(*, row: Mapping[str, Any], deterministic_product: Mapping[str, Any], phase2: Mapping[str, Any]) -> list[dict[str, Any]]:
    assets = phase2.get("image_assets", deterministic_product.get("image_assets", []))
    assets = list(assets) if isinstance(assets, list) else []
    sections = phase2.get("sections", deterministic_product.get("presentation_section_image_metadata", []))
    sections = list(sections) if isinstance(sections, list) else []
    links = phase2.get("internal_links", deterministic_product.get("internal_links", {}))
    links = links if isinstance(links, Mapping) else {}
    similarities = phase2.get("catalog_similarity", {})
    similarities = similarities if isinstance(similarities, Mapping) else {}
    heading = _text(phase2.get("description_heading", deterministic_product.get("description_heading", "")))
    name = _text(row.get("name"))
    description = _text(row.get("description"))
    ids = list(PHASE2_CHECK_DESCRIPTIONS)

    def status(condition: bool, *, missing: bool = False) -> str:
        return "not_run" if missing else ("pass" if condition else "warn")

    sequence = [int(asset.get("position") or 0) for asset in assets]
    filenames_ok = all(valid_seo_filename(str(asset.get("filename_candidate") or "")) for asset in assets)
    paths = [str(asset.get("public_path") or "") for asset in assets]
    alts = [str(asset.get("alt") or "") for asset in assets]
    intro_similarity = similarities.get("intro", similarities.get("description", {}))
    meta_similarity = similarities.get("meta_description", {})
    result_conditions = {
        "images.main_present": bool(assets and assets[0].get("role") == "main"),
        "images.main_jpeg_valid": bool(assets and assets[0].get("jpeg_valid")),
        "images.gallery_filename_policy": filenames_ok,
        "images.gallery_sequence": sequence == list(range(1, len(sequence) + 1)),
        "images.gallery_unique_paths": len(paths) == len(set(paths)),
        "images.gallery_alt_quality": bool(alts and all(alts) and len(set(alts)) == len(alts)),
        "images.description_alt_quality": all(str(section.get("image_alt_confidence") or "") != "low" for section in sections),
        "content.single_h1_contract": "<h1" not in description.casefold(),
        "content.description_heading_distinct": bool(not heading or normalize_for_match(heading) != normalize_for_match(name)),
        "content.intro_catalog_uniqueness": float(intro_similarity.get("score", 0) or 0) < .90,
        "content.meta_description_catalog_uniqueness": float(meta_similarity.get("score", 0) or 0) < .90,
        "internal_linking.category_link": bool(links.get("canonical_category")),
        "internal_linking.related_products": bool(links.get("related_products", [])) or not bool(phase2.get("catalog_available", False)),
    }
    checks: list[dict[str, Any]] = []
    for check_id in ids:
        missing = check_id.startswith("images.") and not assets
        checks.append({
            "id": check_id, "phase": 2, "category": check_id.split(".", 1)[0],
            "description": PHASE2_CHECK_DESCRIPTIONS[check_id],
            "status": status(result_conditions[check_id], missing=missing),
            "severity": "warning" if not result_conditions[check_id] else "info",
            "blocks_publish": False, "weight": 0, "earned_points": 0,
            "message": "phase2_full_profile_report_only", "observed": result_conditions[check_id],
            "expected": True, "applicable_reason": "Phase 2 full profile is report-only.",
            "evidence": [], "remediation": "Review the Phase 2 candidate metadata and render again.",
        })
    return checks


_CHECK_STATUSES = {"pass", "warn", "fail", "not_applicable", "not_run"}
_ATTENTION_STATUSES = {"fail", "warn", "not_run"}
_EVIDENCE_SOURCES = {
    "source", "manufacturer", "deterministic", "llm", "catalog", "runtime", "settings"
}


def _evaluate_full_profile_checks(
    *,
    row: Mapping[str, Any],
    deterministic_product: Mapping[str, Any],
    phase1_checks: Iterable[Mapping[str, Any]],
    product_identity: Mapping[str, Any],
    phase2: Mapping[str, Any] | None,
    phase3: Mapping[str, Any] | None,
    phase3_settings: Mapping[str, Any],
    phase4: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Build the exact 100-point grouped rollout profile.

    Missing Phase 2/3/4 execution evidence is represented as ``not_run``.  It
    therefore remains outside the score denominator while lowering coverage;
    it is never silently converted into a pass or a strict-mode transition.
    """

    phase1_lookup = {str(check.get("id")): dict(check) for check in phase1_checks}

    phase2_payload = dict(phase2) if isinstance(phase2, Mapping) else {}
    phase2_checks = _evaluate_phase2_checks(
        row=row,
        deterministic_product=deterministic_product,
        phase2=phase2_payload,
    )
    phase2_context_available = any(
        bool(phase2_payload.get(key))
        for key in (
            "image_assets",
            "sections",
            "internal_links",
            "catalog_similarity",
            "description_heading",
        )
    ) or any(
        bool(deterministic_product.get(key))
        for key in (
            "image_assets",
            "presentation_section_image_metadata",
            "internal_links",
            "catalog_similarity",
            "description_heading",
        )
    )
    if not phase2_context_available:
        phase2_checks = [
            _check_not_run(check, "Phase 2 candidate evidence was not supplied.")
            for check in phase2_checks
        ]
    else:
        similarity_payload = phase2_payload.get(
            "catalog_similarity", deterministic_product.get("catalog_similarity")
        )
        similarity_mapping = (
            similarity_payload if isinstance(similarity_payload, Mapping) else {}
        )
        intro_similarity = similarity_mapping.get(
            "intro", similarity_mapping.get("description")
        )
        meta_similarity = similarity_mapping.get("meta_description")
        catalog_context_by_check = {
            "content.intro_catalog_uniqueness": bool(
                isinstance(intro_similarity, Mapping)
                and "score" in intro_similarity
            ),
            "content.meta_description_catalog_uniqueness": bool(
                isinstance(meta_similarity, Mapping) and "score" in meta_similarity
            ),
        }
        links_payload = phase2_payload.get(
            "internal_links", deterministic_product.get("internal_links")
        )
        links_context_available = bool(
            isinstance(links_payload, Mapping) and links_payload
        )
        sections_payload = phase2_payload.get(
            "sections",
            deterministic_product.get("presentation_section_image_metadata"),
        )
        sections_context_available = bool(
            isinstance(sections_payload, list) and sections_payload
        )
        heading_context_available = bool(
            _text(
                phase2_payload.get(
                    "description_heading",
                    deterministic_product.get("description_heading", ""),
                )
            )
        )
        phase2_checks = [
            _check_not_run(check, "Catalog similarity evidence was not supplied.")
            if str(check.get("id")) in {
                "content.intro_catalog_uniqueness",
                "content.meta_description_catalog_uniqueness",
            }
            and not catalog_context_by_check[str(check.get("id"))]
            else _check_not_run(check, "Internal-link evidence was not supplied.")
            if str(check.get("id")).startswith("internal_linking.")
            and not links_context_available
            else _check_not_run(check, "Presentation-section alt evidence was not supplied.")
            if str(check.get("id")) == "images.description_alt_quality"
            and not sections_context_available
            else _check_not_run(check, "Description-heading evidence was not supplied.")
            if str(check.get("id")) == "content.description_heading_distinct"
            and not heading_context_available
            else dict(check)
            for check in phase2_checks
        ]
    phase2_lookup = {str(check.get("id")): check for check in phase2_checks}

    phase3_payload = dict(phase3) if isinstance(phase3, Mapping) else {}
    if "structured_data" not in phase3_payload and isinstance(
        phase3_payload.get("structured_data_manifest"), Mapping
    ):
        phase3_payload["structured_data"] = phase3_payload["structured_data_manifest"]
    if "feed" not in phase3_payload and isinstance(
        phase3_payload.get("product_feed"), Mapping
    ):
        phase3_payload["feed"] = phase3_payload["product_feed"]
    resolved_product_identity = dict(product_identity)
    if not resolved_product_identity and isinstance(phase3_payload.get("identity"), Mapping):
        resolved_product_identity = dict(phase3_payload["identity"])
    phase3_checks = _evaluate_phase3_checks(
        row=row,
        product_identity=resolved_product_identity,
        phase3=phase3_payload,
        require_verified=bool(phase3_settings.get("mpn_require_verified", True)),
    )
    identity_available = bool(resolved_product_identity)
    structured_enabled = bool(phase3_payload.get("structured_data_enabled", True))
    feed_enabled = bool(phase3_payload.get("product_feed_enabled", True))
    structured_available = "structured_data" in phase3_payload or not structured_enabled
    feed_available = "feed" in phase3_payload or not feed_enabled
    phase3_checks = [
        _check_not_run(check, "Product-identity evidence was not supplied.")
        if str(check.get("id")).startswith("identity.") and not identity_available
        else _check_not_run(check, "Structured-data validation was not run.")
        if str(check.get("id")).startswith("structured_data.") and not structured_available
        else _check_not_run(check, "Merchant/feed validation was not run.")
        if str(check.get("id")).startswith("feed.") and not feed_available
        else dict(check)
        for check in phase3_checks
    ]
    phase3_lookup = {str(check.get("id")): check for check in phase3_checks}

    phase4_payload = phase4 if isinstance(phase4, Mapping) else {}
    lookups = {1: phase1_lookup, 2: phase2_lookup, 3: phase3_lookup}
    default_sources = {1: "deterministic", 2: "runtime", 3: "runtime"}
    grouped: list[dict[str, Any]] = []
    for group_id, group_phase, weight in FULL_PROFILE_CHECK_WEIGHTS:
        metadata = FULL_PROFILE_GROUP_METADATA[group_id]
        if group_phase == 4:
            grouped.append(
                _evaluate_phase4_group(
                    group_id=group_id,
                    weight=weight,
                    metadata=metadata,
                    payload=phase4_payload.get(group_id),
                )
            )
            continue
        lookup = lookups[group_phase]
        subchecks = [
            lookup.get(
                subcheck_id,
                _missing_internal_subcheck(subcheck_id, group_phase),
            )
            for subcheck_id in metadata["subchecks"]
        ]
        grouped.append(
            _build_grouped_check(
                group_id=group_id,
                phase=group_phase,
                weight=weight,
                metadata=metadata,
                subchecks=subchecks,
                default_evidence_source=default_sources[group_phase],
            )
        )
    return grouped


def _evaluate_phase4_group(
    *,
    group_id: str,
    weight: int,
    metadata: Mapping[str, Any],
    payload: object,
) -> dict[str, Any]:
    raw = dict(payload) if isinstance(payload, Mapping) else {}
    explicit_status = str(raw.get("status") or "")
    if explicit_status not in _CHECK_STATUSES:
        explicit_status = "not_run"
    raw_subchecks = raw.get("subchecks")
    subchecks: list[dict[str, Any]] = []
    if isinstance(raw_subchecks, list):
        for index, item in enumerate(raw_subchecks, start=1):
            if not isinstance(item, Mapping):
                continue
            subcheck = dict(item)
            subcheck_id = normalize_whitespace(
                str(subcheck.get("id") or f"{group_id}.subcheck_{index}")
            )
            status = str(subcheck.get("status") or "not_run")
            if status not in _CHECK_STATUSES:
                status = "not_run"
            subchecks.append({
                **subcheck,
                "id": subcheck_id,
                "status": status,
                "blocks_publish": bool(subcheck.get("blocks_publish", False)),
                "message": str(subcheck.get("message") or status),
            })

    attention_present = any(
        str(subcheck.get("status")) in _ATTENTION_STATUSES for subcheck in subchecks
    )
    if not subchecks or (explicit_status in _ATTENTION_STATUSES and not attention_present):
        subchecks.append({
            "id": f"{group_id}.group_status",
            "status": explicit_status,
            "blocks_publish": bool(raw.get("blocks_publish", False)),
            "message": str(
                raw.get("message")
                or ("Phase 4 rollout evidence was not supplied." if not payload else explicit_status)
            ),
            "observed": raw.get("observed"),
            "expected": raw.get("expected"),
            "evidence": raw.get("evidence", []),
        })

    return _build_grouped_check(
        group_id=group_id,
        phase=4,
        weight=weight,
        metadata=metadata,
        subchecks=subchecks,
        default_evidence_source="runtime",
        explicit_status=explicit_status,
        overrides=raw,
    )


def _build_grouped_check(
    *,
    group_id: str,
    phase: int,
    weight: int,
    metadata: Mapping[str, Any],
    subchecks: Iterable[Mapping[str, Any]],
    default_evidence_source: str,
    explicit_status: str = "",
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    materialized = [dict(check) for check in subchecks]
    statuses = [str(check.get("status") or "not_run") for check in materialized]
    if explicit_status in _CHECK_STATUSES:
        statuses.append(explicit_status)
    status = _aggregate_group_status(statuses)
    raw_overrides = overrides if isinstance(overrides, Mapping) else {}
    blocks_requested = bool(raw_overrides.get("blocks_publish", False)) or any(
        bool(check.get("blocks_publish", False))
        and str(check.get("status")) == "fail"
        for check in materialized
    )
    blocks_publish = bool(status == "fail" and blocks_requested)
    earned = weight if status == "pass" else (weight * .5 if status == "warn" else 0)
    evidence = [
        _attention_evidence(check, default_source=default_evidence_source)
        for check in materialized
        if str(check.get("status")) in _ATTENTION_STATUSES
    ]
    observed = (
        raw_overrides.get("observed")
        if "observed" in raw_overrides
        else {str(check.get("id")): str(check.get("status")) for check in materialized}
    )
    expected = (
        raw_overrides.get("expected")
        if "expected" in raw_overrides
        else "all applicable subchecks pass"
    )
    message = str(raw_overrides.get("message") or _group_message(status, evidence))
    return {
        "id": group_id,
        "phase": phase,
        "category": str(metadata["category"]),
        "description": str(metadata["description"]),
        "status": status,
        "severity": (
            "blocker"
            if blocks_publish
            else "error"
            if status == "fail"
            else "warning"
            if status in {"warn", "not_run"}
            else "info"
        ),
        "blocks_publish": blocks_publish,
        "weight": weight,
        "earned_points": earned,
        "message": message,
        "observed": observed,
        "expected": expected,
        "applicable_reason": f"Full SEO-health profile Phase {phase} group.",
        "evidence": evidence,
        "remediation": (
            "Complete and verify rollout evidence before applying or expanding the migration."
            if phase == 4
            else "Review each listed subcheck, correct its deterministic evidence, and evaluate again."
        ),
    }


def _aggregate_group_status(statuses: Iterable[str]) -> str:
    materialized = [status if status in _CHECK_STATUSES else "not_run" for status in statuses]
    if "fail" in materialized:
        return "fail"
    if "not_run" in materialized:
        return "not_run"
    if "warn" in materialized:
        return "warn"
    if "pass" in materialized:
        return "pass"
    return "not_applicable"


def _attention_evidence(check: Mapping[str, Any], *, default_source: str) -> dict[str, Any]:
    source = str(check.get("source") or "")
    nested_evidence = check.get("evidence")
    if source not in _EVIDENCE_SOURCES and isinstance(nested_evidence, list):
        source = next(
            (
                str(item.get("source"))
                for item in nested_evidence
                if isinstance(item, Mapping) and str(item.get("source")) in _EVIDENCE_SOURCES
            ),
            "",
        )
    if source not in _EVIDENCE_SOURCES:
        source = default_source
    value = {
        "status": str(check.get("status") or "not_run"),
        "message": str(check.get("message") or check.get("status") or "not_run"),
        "observed": check.get("observed"),
        "expected": check.get("expected"),
    }
    if nested_evidence:
        value["evidence"] = nested_evidence
    evidence: dict[str, Any] = {
        "source": source,
        "field": str(check.get("id") or "unknown.subcheck"),
        "value": value,
    }
    if normalize_whitespace(str(check.get("path") or "")):
        evidence["path"] = normalize_whitespace(str(check.get("path")))
    return evidence


def _check_not_run(check: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        **dict(check),
        "status": "not_run",
        "severity": "warning",
        "blocks_publish": False,
        "earned_points": 0,
        "message": reason,
        "observed": None,
        "applicable_reason": reason,
        "evidence": [],
    }


def _missing_internal_subcheck(check_id: str, phase: int) -> dict[str, Any]:
    return {
        "id": check_id,
        "phase": phase,
        "status": "not_run",
        "blocks_publish": False,
        "message": "The deterministic subcheck was unavailable.",
        "observed": None,
        "expected": "subcheck result",
        "evidence": [],
    }


def _group_message(status: str, evidence: list[Mapping[str, Any]]) -> str:
    if status == "pass":
        return "all_applicable_subchecks_passed"
    if status == "not_applicable":
        return "all_subchecks_not_applicable"
    if status == "not_run":
        return f"subchecks_not_run:{len(evidence)}"
    return f"subchecks_{status}:{len(evidence)}"


def valid_seo_filename(value: str) -> bool:
    return bool(re.fullmatch(r"^[a-z0-9]+(?:-[a-z0-9]+)*-[1-9][0-9]*\.jpg$", value))


def _publish_gate(totals: Mapping[str, Any], settings: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = settings or {}
    thresholds = {**DEFAULT_THRESHOLDS, **dict(raw.get("thresholds", {}))} if isinstance(raw.get("thresholds", {}), Mapping) else dict(DEFAULT_THRESHOLDS)
    mode = str(raw.get("enforcement_mode") or DEFAULT_ENFORCEMENT_MODE)
    if mode not in {"report_only", "blockers_only", "strict"}:
        mode = DEFAULT_ENFORCEMENT_MODE
    score = int(totals["score"])
    coverage = int(totals["coverage"]["percentage"])
    summary = totals["summary"]
    recommended_allowed = score >= int(thresholds["minimum_score"]) and coverage >= int(thresholds["minimum_coverage"]) and summary["blocking_failures"] == 0
    if not recommended_allowed:
        status = "fail"
    elif score >= 90 and summary["warnings"] == 0 and summary["failed"] == 0:
        status = "pass"
    else:
        status = "warn"
    enforced = True if mode == "report_only" else (summary["blocking_failures"] == 0 if mode == "blockers_only" else recommended_allowed)
    reasons: list[str] = []
    if score < int(thresholds["minimum_score"]): reasons.append("score_below_minimum")
    if coverage < int(thresholds["minimum_coverage"]): reasons.append("coverage_below_minimum")
    if summary["blocking_failures"]: reasons.append("blocking_failures_present")
    return {"recommended_status": status, "recommended_allowed": recommended_allowed, "enforcement_mode": mode, "enforced_allowed": enforced, "thresholds": thresholds, "reasons": reasons}


def _meta_description_length_status(value: str) -> str:
    length = len(value)
    if 130 <= length <= 180: return "pass"
    if 110 <= length <= 129: return "warn"
    return "fail"


def _verified_differentiators(identity: Mapping[str, Any]) -> list[str]:
    return [value for value in [_text(identity.get("btu")), _text(identity.get("cooling_energy_class")), "Wi-Fi" if identity.get("wifi") is True else "", "Inverter" if identity.get("inverter") is True else "", *_text_list(identity.get("verified_features"))] if value]


def _unsupported_numeric_claims(description: str, identity: Mapping[str, Any]) -> list[str]:
    allowed_text = " ".join(str(value) for value in identity.values() if value is not None)
    allowed = {number.replace(",", ".") for number in re.findall(r"\d+(?:[.,]\d+)?", allowed_text)}
    return [number for number in re.findall(r"\d+(?:[.,]\d+)?", description) if number.replace(",", ".") not in allowed]


def _keyword_identity_ok(keyword: str, brand: str, primary: str) -> bool:
    brand_token = slugify_greek_for_seo(brand)
    primary_token = slugify_greek_for_seo(primary)
    return bool(brand_token and primary_token and brand_token in keyword and primary_token in keyword)


def _contains(value: str, phrase: str) -> bool:
    return bool(normalize_for_match(phrase)) and normalize_for_match(phrase) in normalize_for_match(value)


def _text(value: object) -> str:
    return normalize_whitespace(str(value or ""))


def _text_list(value: object) -> list[str]:
    return [_text(item) for item in value] if isinstance(value, list) else []
