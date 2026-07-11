from __future__ import annotations

"""Phase 1 SEO health evaluation and publish-gate calculation."""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import re
from typing import Any, Iterable, Mapping

from .normalize import normalize_for_match, normalize_whitespace
from .seo_identity import meta_title_length_status, valid_seo_keyword
from .normalize import slugify_greek_for_seo


RULESET_VERSION = "phase1.0"
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


def round_half_up(value: Decimal | float | int) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_score(checks: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    materialized = list(checks)
    active_weight = sum(int(check.get("weight", 0)) for check in materialized)
    evaluated_weight = sum(
        int(check.get("weight", 0))
        for check in materialized
        if check.get("status") != "not_run"
    )
    applicable = [
        check for check in materialized if check.get("status") in {"pass", "warn", "fail"}
    ]
    applicable_weight = sum(int(check.get("weight", 0)) for check in applicable)
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
            "active_weight": active_weight,
            "evaluated_weight": evaluated_weight,
            "percentage": coverage,
        },
        "summary": {
            "total_checks": len(materialized),
            "passed": counts["pass"],
            "warnings": counts["warn"],
            "failed": counts["fail"],
            "not_applicable": counts["not_applicable"],
            "not_run": counts["not_run"],
            "applicable_weight": applicable_weight,
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
) -> dict[str, Any]:
    identity = deterministic_product.get("seo_identity", {})
    identity = identity if isinstance(identity, Mapping) else {}
    air_conditioner = identity.get("family") == "air_conditioner"
    checks = _evaluate_checks(
        row=row,
        deterministic_product=deterministic_product,
        identity=identity,
        air_conditioner=air_conditioner,
        catalog_seo_keywords=catalog_seo_keywords,
    )
    totals = calculate_score(checks)
    gate = _publish_gate(totals, settings)
    return {
        "schema_version": "1.0",
        "ruleset_version": str((settings or {}).get("ruleset_version") or RULESET_VERSION),
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
