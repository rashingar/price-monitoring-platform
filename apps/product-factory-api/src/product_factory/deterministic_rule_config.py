from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .normalize import normalize_for_match, normalize_whitespace
from .repo_paths import NAME_RULES_PATH

VALID_SOURCE_SCOPES = frozenset(
    {
        normalize_for_match("any"),
        normalize_for_match("skroutz"),
        normalize_for_match("manufacturer_tefal"),
    }
)
DEFAULT_GENERIC_OUTPUTS = {
    "name": "all",
    "meta_title": "first_2",
    "seo_keyword": "name",
}


@dataclass(frozen=True, slots=True)
class GenericOutputProfile:
    name: str
    meta_title: str
    seo_keyword: str


@dataclass(frozen=True, slots=True)
class GenericNameRule:
    source_scope: str
    match_leaf_category: str
    match_sub_category: str
    category_phrase: str
    differentiator_specs: tuple[tuple[tuple[str, ...], ...], ...]
    max_differentiators: int


@dataclass(frozen=True, slots=True)
class ResolvedGenericNameRule:
    rule: GenericNameRule
    matched_exact: bool
    outputs: GenericOutputProfile


@dataclass(frozen=True, slots=True)
class SourceScopedRule:
    source_scopes: tuple[str, ...]
    match_family: str
    match_leaf_category: str
    match_sub_category: str
    category_phrase: str
    strategy_id: str
    outputs: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class DeterministicRuleConfig:
    generic_outputs: GenericOutputProfile
    generic_rules: tuple[GenericNameRule, ...]
    source_rules: tuple[SourceScopedRule, ...]
    default_rule: GenericNameRule


def _normalize_source_scopes(value: Any, *, default_scope: str) -> tuple[str, ...]:
    raw_values = value if isinstance(value, list) else [value or default_scope]
    scopes: list[str] = []
    for raw in raw_values:
        normalized = normalize_for_match(raw) or normalize_for_match(default_scope)
        if normalized not in VALID_SOURCE_SCOPES:
            raise ValueError(f"Unsupported deterministic rule source_scope: {raw!r}")
        if normalized not in scopes:
            scopes.append(normalized)
    return tuple(scopes)


def _normalize_alias_group(raw_group: Any) -> tuple[tuple[str, ...], ...]:
    if isinstance(raw_group, list) and raw_group and isinstance(raw_group[0], list):
        alias_groups = raw_group
    else:
        alias_groups = [raw_group]

    normalized_groups: list[tuple[str, ...]] = []
    for aliases in alias_groups:
        if isinstance(aliases, str):
            normalized_aliases = [normalize_whitespace(aliases)]
        elif isinstance(aliases, list):
            normalized_aliases = [normalize_whitespace(alias) for alias in aliases if normalize_whitespace(alias)]
        else:
            raise ValueError(f"Invalid differentiator alias group: {aliases!r}")
        normalized_aliases = [alias for alias in normalized_aliases if alias]
        if not normalized_aliases:
            continue
        normalized_groups.append(tuple(normalized_aliases))
    return tuple(normalized_groups)


def _normalize_differentiator_specs(raw_specs: Any) -> tuple[tuple[tuple[str, ...], ...], ...]:
    if not isinstance(raw_specs, list):
        raise ValueError("deterministic rule differentiator_specs must be a list")
    out: list[tuple[tuple[str, ...], ...]] = []
    for raw_group in raw_specs:
        normalized = _normalize_alias_group(raw_group)
        if normalized:
            out.append(normalized)
    return tuple(out)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _parse_generic_output_profile(payload: dict[str, Any]) -> GenericOutputProfile:
    values = {**DEFAULT_GENERIC_OUTPUTS, **payload}
    return GenericOutputProfile(
        name=normalize_for_match(values.get("name")) or DEFAULT_GENERIC_OUTPUTS["name"],
        meta_title=normalize_for_match(values.get("meta_title")) or DEFAULT_GENERIC_OUTPUTS["meta_title"],
        seo_keyword=normalize_for_match(values.get("seo_keyword")) or DEFAULT_GENERIC_OUTPUTS["seo_keyword"],
    )


def _parse_generic_rule(
    payload: dict[str, Any],
    *,
    default_scope: str,
    default_max_differentiators: int,
) -> GenericNameRule:
    match = payload.get("match") if isinstance(payload.get("match"), dict) else {}
    source_scope = _normalize_source_scopes(payload.get("source_scope"), default_scope=default_scope)[0]
    match_leaf_category = normalize_whitespace(match.get("leaf_category"))
    match_sub_category = normalize_whitespace(match.get("sub_category"))
    if not match_leaf_category and not match_sub_category:
        raise ValueError("generic deterministic rule requires match.leaf_category or match.sub_category")
    category_phrase = normalize_whitespace(payload.get("category_phrase"))
    is_default_rule = match_leaf_category == "__default__"
    if not category_phrase and not is_default_rule:
        raise ValueError("generic deterministic rule requires category_phrase")
    differentiator_specs = _normalize_differentiator_specs(payload.get("differentiator_specs", []))
    max_differentiators = int(payload.get("max_differentiators") or len(differentiator_specs) or default_max_differentiators)
    return GenericNameRule(
        source_scope=source_scope,
        match_leaf_category=match_leaf_category,
        match_sub_category=match_sub_category,
        category_phrase=category_phrase,
        differentiator_specs=differentiator_specs,
        max_differentiators=max_differentiators,
    )


def _parse_source_rule(payload: dict[str, Any], *, default_scope: str) -> SourceScopedRule:
    match = payload.get("match") if isinstance(payload.get("match"), dict) else {}
    source_scopes = _normalize_source_scopes(payload.get("source_scope"), default_scope=default_scope)
    match_family = normalize_for_match(match.get("family"))
    match_leaf_category = normalize_whitespace(match.get("leaf_category"))
    match_sub_category = normalize_whitespace(match.get("sub_category"))
    if not match_family:
        raise ValueError("source deterministic rule requires match.family")
    strategy_id = normalize_whitespace(payload.get("strategy_id"))
    if not strategy_id:
        raise ValueError("source deterministic rule requires strategy_id")
    category_phrase = normalize_whitespace(payload.get("category_phrase"))
    if not category_phrase:
        raise ValueError("source deterministic rule requires category_phrase")

    raw_outputs = payload.get("outputs")
    if not isinstance(raw_outputs, dict) or not raw_outputs:
        raise ValueError("source deterministic rule requires outputs")

    outputs: dict[str, tuple[str, ...]] = {}
    for key, raw_value in raw_outputs.items():
        normalized_key = normalize_whitespace(str(key))
        if normalized_key not in {"name", "meta_title", "seo_keyword"}:
            raise ValueError(f"Unsupported source deterministic rule output: {key!r}")
        if not isinstance(raw_value, list):
            raise ValueError(f"source deterministic rule output {key!r} must be a list")
        values = tuple(normalize_whitespace(str(item)) for item in raw_value if normalize_whitespace(str(item)))
        if not values:
            raise ValueError(f"source deterministic rule output {key!r} must contain values")
        outputs[normalized_key] = values

    return SourceScopedRule(
        source_scopes=source_scopes,
        match_family=match_family,
        match_leaf_category=match_leaf_category,
        match_sub_category=match_sub_category,
        category_phrase=category_phrase,
        strategy_id=strategy_id,
        outputs=outputs,
    )


@lru_cache(maxsize=None)
def load_deterministic_rule_config(path: str = str(NAME_RULES_PATH)) -> DeterministicRuleConfig:
    payload = _load_json(Path(path))
    rule_defaults = payload.get("rule_defaults") if isinstance(payload.get("rule_defaults"), dict) else {}
    default_scope = normalize_for_match(rule_defaults.get("source_scope")) or "any"
    if default_scope not in VALID_SOURCE_SCOPES:
        raise ValueError(f"Unsupported deterministic rule default source_scope: {rule_defaults.get('source_scope')!r}")
    generic_outputs = _parse_generic_output_profile(
        payload.get("generic_outputs") if isinstance(payload.get("generic_outputs"), dict) else {}
    )

    generic_rules = tuple(
        _parse_generic_rule(rule, default_scope=default_scope, default_max_differentiators=3)
        for rule in payload.get("rules", [])
        if isinstance(rule, dict)
    )
    default_rule = _parse_generic_rule(
        payload.get("default") if isinstance(payload.get("default"), dict) else {},
        default_scope=default_scope,
        default_max_differentiators=3,
    )
    source_rules = tuple(
        _parse_source_rule(rule, default_scope=default_scope)
        for rule in payload.get("source_rules", [])
        if isinstance(rule, dict)
    )

    return DeterministicRuleConfig(
        generic_outputs=generic_outputs,
        generic_rules=generic_rules,
        source_rules=source_rules,
        default_rule=default_rule,
    )


def _source_scope_matches(scope: str, source_name: str) -> bool:
    return scope == "any" or scope == normalize_for_match(source_name)


def _matches_generic_rule(rule: GenericNameRule, *, source_name: str, sub_category: str, leaf_category: str) -> tuple[bool, bool]:
    if not _source_scope_matches(rule.source_scope, source_name):
        return False, False

    normalized_sub = normalize_for_match(sub_category)
    normalized_leaf = normalize_for_match(leaf_category)
    targets = [
        target
        for target in (normalize_for_match(rule.match_sub_category), normalize_for_match(rule.match_leaf_category))
        if target
    ]
    candidates = [candidate for candidate in (normalized_sub, normalized_leaf) if candidate]
    exact = any(target == candidate for target in targets for candidate in candidates)
    return exact, exact


def resolve_generic_name_rule(
    *,
    source_name: str,
    leaf_category: str,
    sub_category: str,
    path: str = str(NAME_RULES_PATH),
) -> ResolvedGenericNameRule | None:
    config = load_deterministic_rule_config(path)

    for rule in config.generic_rules:
        matches, exact = _matches_generic_rule(
            rule,
            source_name=source_name,
            sub_category=sub_category,
            leaf_category=leaf_category,
        )
        if matches and exact:
            return ResolvedGenericNameRule(rule=rule, matched_exact=True, outputs=config.generic_outputs)

    for rule in config.generic_rules:
        matches, exact = _matches_generic_rule(
            rule,
            source_name=source_name,
            sub_category=sub_category,
            leaf_category=leaf_category,
        )
        if matches and not exact:
            return ResolvedGenericNameRule(rule=rule, matched_exact=False, outputs=config.generic_outputs)
    return None


def resolve_source_scoped_rule(
    *,
    source_name: str,
    family: str,
    leaf_category: str,
    sub_category: str,
    path: str = str(NAME_RULES_PATH),
) -> SourceScopedRule | None:
    config = load_deterministic_rule_config(path)
    normalized_source = normalize_for_match(source_name)
    normalized_family = normalize_for_match(family)
    normalized_leaf = normalize_for_match(leaf_category)
    normalized_sub = normalize_for_match(sub_category)

    for rule in config.source_rules:
        if "any" not in rule.source_scopes and normalized_source not in rule.source_scopes:
            continue
        if normalized_family != rule.match_family:
            continue
        if rule.match_leaf_category and normalize_for_match(rule.match_leaf_category) != normalized_leaf:
            continue
        if rule.match_sub_category and normalize_for_match(rule.match_sub_category) != normalized_sub:
            continue
        return rule
    return None
