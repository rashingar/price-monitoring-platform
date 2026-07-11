from __future__ import annotations

"""Deterministic MPN-first product identity resolution.

This module deliberately treats the OpenCart model as an internal key.  The
only external identifier it resolves is the manufacturer MPN; it never
creates, stores, or evaluates alternate retail identifiers.
"""

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Iterable, Mapping

from .normalize import normalize_whitespace


MPN_STATUSES = {"verified", "inferred", "conflicting", "missing", "not_applicable"}
MPN_SCOPES = {
    "complete_product",
    "complete_set",
    "single_unit",
    "indoor_unit",
    "outdoor_unit",
    "component",
    "unknown",
}
_PLACEHOLDERS = {"-", "n/a", "na", "none", "unknown", "not available", "tbd"}
_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2212"
_LABEL_RE = re.compile(
    r"^\s*(?:mpn|model|manufacturer\s+model|product\s+model|"
    r"\u03ba\u03c9\u03b4\u03b9\u03ba\u03cc\u03c2\s+\u03bc\u03bf\u03bd\u03c4\u03ad\u03bb\u03bf\u03c5)\s*[:#-]?\s*",
    re.IGNORECASE,
)
_TITLE_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z][A-Za-z0-9._-]*\d[A-Za-z0-9._-]*)(?:\s*/\s*(?:[A-Za-z][A-Za-z0-9._-]*\d[A-Za-z0-9._-]*))?(?![A-Za-z0-9])"
)


@dataclass(slots=True)
class MpnCandidate:
    value: str
    scope: str = "unknown"
    source: str = ""
    source_url: str = ""
    confidence: float = 0.0
    status: str = "verified"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ProductIdentity:
    internal_model: str = ""
    brand: str = ""
    mpn: str = ""
    mpn_status: str = "missing"
    mpn_scope: str = "unknown"
    primary_model: str = ""
    set_model: str = ""
    component_models: list[str] = field(default_factory=list)
    commercial_series: str = ""
    family_key: str = ""
    source: str = ""
    source_url: str = ""
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    candidates: list[MpnCandidate] = field(default_factory=list)
    conflict_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["schema_version"] = "1.0"
        return {
            "schema_version": payload.pop("schema_version"),
            "internal_model": payload["internal_model"],
            "brand": payload["brand"],
            "mpn": payload["mpn"],
            "mpn_status": payload["mpn_status"],
            "mpn_scope": payload["mpn_scope"],
            "primary_model": payload["primary_model"],
            "set_model": payload["set_model"],
            "component_models": payload["component_models"],
            "commercial_series": payload["commercial_series"],
            "family_key": payload["family_key"],
            "source": payload["source"],
            "source_url": payload["source_url"],
            "confidence": payload["confidence"],
            "warnings": payload["warnings"],
            "candidates": payload["candidates"],
            "conflict_reason": payload["conflict_reason"],
        }


def normalize_mpn_display(value: object) -> str:
    """Normalize presentation without changing manufacturer-significant tokens."""
    text = normalize_whitespace(str(value or ""))
    text = _LABEL_RE.sub("", text)
    text = text.translate(str.maketrans({dash: "-" for dash in _DASHES}))
    text = re.sub(r"\s*/\s*", "/", text)
    text = normalize_whitespace(text).strip(" \t\r\n:;,")
    if not text or text.casefold() in _PLACEHOLDERS:
        return ""
    if len(text) > 80 or not any(char.isalnum() for char in text):
        return ""
    return text


def normalize_mpn_for_match(value: object) -> str:
    """Canonical comparison form; display punctuation remains untouched."""
    text = normalize_mpn_display(value).upper()
    text = re.sub(r"\s*([/-])\s*", r"\1", text)
    return re.sub(r"\s+", " ", text)


def extract_mpn_candidates(
    values: Iterable[object], *, source: str, source_url: str = "", confidence: float = 0.60,
    status: str = "inferred",
) -> list[MpnCandidate]:
    """Extract conservative title candidates; callers retain provenance."""
    candidates: list[MpnCandidate] = []
    for value in values:
        text = normalize_whitespace(str(value or ""))
        for match in _TITLE_TOKEN_RE.finditer(text):
            display = normalize_mpn_display(match.group(0))
            if not _is_syntax_valid(display):
                continue
            candidates.append(
                MpnCandidate(
                    value=display,
                    scope=_scope_for_value(display),
                    source=source,
                    source_url=source_url,
                    confidence=confidence,
                    status=status,
                )
            )
    return _dedupe_candidates(candidates)


def resolve_product_identity(
    *,
    internal_model: str,
    brand: str,
    source_mpn: str,
    source_name: str,
    source_url: str,
    source_title: str = "",
    family_key: str = "",
    seo_identity: Mapping[str, object] | None = None,
    explicit_candidates: Iterable[Mapping[str, object]] = (),
    existing_mpn: str = "",
    manual_override: Mapping[str, object] | None = None,
) -> ProductIdentity:
    """Resolve a reproducible identity from exact product evidence.

    A complete-set and component disagreement is deliberately left unresolved:
    automatic output must not turn a component identifier into a sellable-set
    identifier by preference alone.
    """
    seo = seo_identity if isinstance(seo_identity, Mapping) else {}
    family = normalize_whitespace(family_key or str(seo.get("family") or ""))
    identity = ProductIdentity(
        internal_model=normalize_whitespace(internal_model),
        brand=normalize_whitespace(brand),
        commercial_series=normalize_whitespace(str(seo.get("commercial_series") or "")),
        family_key=family,
    )
    override = _manual_override_candidate(manual_override, source_url)
    if override is not None:
        if _is_valid_external_mpn(override.value, identity.internal_model):
            return _identity_from_candidate(identity, override, seo, warnings=["manual_override"])
        identity.warnings.append("manual_override_invalid")

    candidates: list[MpnCandidate] = []
    existing = normalize_mpn_display(existing_mpn)
    if _is_valid_external_mpn(existing, identity.internal_model):
        candidates.append(MpnCandidate(existing, _scope_for_value(existing, seo), "existing_product", "", .99))
    source_value = normalize_mpn_display(source_mpn)
    if _is_valid_external_mpn(source_value, identity.internal_model):
        candidates.append(
            MpnCandidate(
                source_value,
                _scope_for_value(source_value, seo),
                _source_kind(source_name),
                source_url,
                _source_confidence(source_name),
            )
        )
    elif source_value:
        identity.warnings.append("source_mpn_rejected")

    for raw in explicit_candidates:
        if not isinstance(raw, Mapping):
            continue
        display = normalize_mpn_display(raw.get("value", ""))
        if not _is_valid_external_mpn(display, identity.internal_model):
            continue
        scope = str(raw.get("scope") or _scope_for_value(display, seo))
        candidates.append(
            MpnCandidate(
                display,
                scope if scope in MPN_SCOPES else "unknown",
                normalize_whitespace(str(raw.get("source") or "trusted_source")),
                normalize_whitespace(str(raw.get("source_url") or source_url)),
                float(raw.get("confidence") or .82),
                str(raw.get("status") or "verified"),
            )
        )

    candidates.extend(
        extract_mpn_candidates(
            [source_title], source="verified_title", source_url=source_url, confidence=.60, status="inferred"
        )
    )
    identity.candidates = _dedupe_candidates(candidates)
    _apply_component_metadata(identity, seo)
    if not identity.candidates:
        return identity

    conflict = _complete_set_component_conflict(identity.candidates)
    if family == "air_conditioner" and conflict:
        identity.mpn_status = "conflicting"
        identity.conflict_reason = "complete_set_and_component_identifier_conflict"
        identity.warnings.append(identity.conflict_reason)
        return identity

    selected = sorted(
        identity.candidates,
        key=lambda item: (-item.confidence, 0 if item.status == "verified" else 1, normalize_mpn_for_match(item.value)),
    )[0]
    return _identity_from_candidate(identity, selected, seo)


def validate_mpn_identity(
    identity: Mapping[str, object], *, csv_mpn: str = "", active: bool = False
) -> list[str]:
    """Return stable machine-readable consistency failures for candidate gating."""
    errors: list[str] = []
    mpn = normalize_mpn_display(identity.get("mpn", ""))
    internal_model = normalize_whitespace(str(identity.get("internal_model") or ""))
    status = str(identity.get("mpn_status") or "missing")
    scope = str(identity.get("mpn_scope") or "unknown")
    family = str(identity.get("family_key") or "")
    if status == "conflicting":
        errors.append("mpn_candidates_conflicting")
    if mpn and normalize_mpn_for_match(mpn) == normalize_mpn_for_match(internal_model):
        errors.append("mpn_is_internal_model")
    if mpn and scope not in MPN_SCOPES:
        errors.append("mpn_scope_invalid")
    if mpn and csv_mpn and normalize_mpn_for_match(mpn) != normalize_mpn_for_match(csv_mpn):
        errors.append("csv_mpn_identity_mismatch")
    if family == "air_conditioner" and scope == "complete_set":
        components = [normalize_mpn_for_match(value) for value in identity.get("component_models", [])]
        if "/" not in mpn or len(components) < 2:
            errors.append("complete_set_not_preserved")
    if active and status != "verified":
        errors.append("mpn_not_verified")
    return errors


def _manual_override_candidate(
    override: Mapping[str, object] | None, source_url: str
) -> MpnCandidate | None:
    if not isinstance(override, Mapping):
        return None
    value = normalize_mpn_display(override.get("value", ""))
    scope = str(override.get("scope") or "unknown")
    reason = normalize_whitespace(str(override.get("reason") or ""))
    if not value or scope not in MPN_SCOPES or not reason:
        return None
    return MpnCandidate(value, scope, "manual_override", source_url, 1.0, "verified")


def _identity_from_candidate(
    identity: ProductIdentity, candidate: MpnCandidate, seo: Mapping[str, object], *, warnings: list[str] | None = None
) -> ProductIdentity:
    identity.mpn = candidate.value
    identity.mpn_status = candidate.status if candidate.status in MPN_STATUSES else "verified"
    identity.mpn_scope = candidate.scope if candidate.scope in MPN_SCOPES else _scope_for_value(candidate.value, seo)
    identity.source = candidate.source
    identity.source_url = candidate.source_url
    identity.confidence = candidate.confidence
    if warnings:
        identity.warnings.extend(warnings)
    _apply_component_metadata(identity, seo)
    if identity.mpn_scope == "complete_set":
        identity.set_model = candidate.value
        if not identity.component_models:
            identity.component_models = _split_set(candidate.value)
        identity.primary_model = identity.component_models[0] if identity.component_models else candidate.value
    elif not identity.primary_model:
        identity.primary_model = candidate.value
    return identity


def _apply_component_metadata(identity: ProductIdentity, seo: Mapping[str, object]) -> None:
    values = [
        normalize_mpn_display(seo.get("indoor_model", "")),
        normalize_mpn_display(seo.get("outdoor_model", "")),
    ]
    values.extend(normalize_mpn_display(value) for value in seo.get("component_models", []) if value)
    if not any(values):
        values.extend(_split_set(normalize_mpn_display(seo.get("set_model", ""))))
    identity.component_models = _unique(values)
    identity.set_model = normalize_mpn_display(seo.get("set_model", ""))
    identity.primary_model = normalize_mpn_display(seo.get("primary_model", ""))


def _scope_for_value(value: str, seo: Mapping[str, object] | None = None) -> str:
    normalized = normalize_mpn_display(value)
    if "/" in normalized and len(_split_set(normalized)) >= 2:
        return "complete_set"
    if isinstance(seo, Mapping):
        key = normalize_mpn_for_match(normalized)
        if key and key == normalize_mpn_for_match(seo.get("indoor_model", "")):
            return "indoor_unit"
        if key and key == normalize_mpn_for_match(seo.get("outdoor_model", "")):
            return "outdoor_unit"
    return "single_unit" if normalized else "unknown"


def _complete_set_component_conflict(candidates: Iterable[MpnCandidate]) -> bool:
    materialized = list(candidates)
    set_values = {normalize_mpn_for_match(item.value) for item in materialized if item.scope == "complete_set"}
    component_values = {
        normalize_mpn_for_match(item.value)
        for item in materialized
        if item.scope in {"indoor_unit", "outdoor_unit", "component", "single_unit"}
    }
    if not set_values or not component_values:
        return False
    return any(value and value not in set_values for value in component_values)


def _dedupe_candidates(candidates: Iterable[MpnCandidate]) -> list[MpnCandidate]:
    deduped: dict[str, MpnCandidate] = {}
    for candidate in candidates:
        key = normalize_mpn_for_match(candidate.value)
        if not key:
            continue
        prior = deduped.get(key)
        if prior is None or (candidate.confidence, candidate.status == "verified") > (prior.confidence, prior.status == "verified"):
            deduped[key] = candidate
    return [deduped[key] for key in sorted(deduped)]


def _is_syntax_valid(value: str) -> bool:
    return bool(value and any(char.isalpha() for char in value) and any(char.isdigit() for char in value))


def _is_valid_external_mpn(value: str, internal_model: str) -> bool:
    if not value or not _is_syntax_valid(value):
        return False
    return normalize_mpn_for_match(value) != normalize_mpn_for_match(internal_model)


def _split_set(value: str) -> list[str]:
    return _unique(normalize_mpn_display(part) for part in value.split("/") if normalize_mpn_display(part))


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_mpn_display(value)
        key = normalize_mpn_for_match(normalized)
        if key and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def _source_kind(source_name: str) -> str:
    value = normalize_whitespace(source_name).casefold()
    if "manufacturer" in value or "official" in value:
        return "manufacturer"
    if value == "electronet":
        return "electronet"
    return "trusted_retailer"


def _source_confidence(source_name: str) -> float:
    return {"manufacturer": .98, "electronet": .92}.get(_source_kind(source_name), .82)
