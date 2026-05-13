from __future__ import annotations

import re
from typing import Any

from .intro_text_markup import (
    MAX_EMPHASIZED_WORD_RATIO,
    count_intro_text_words,
    normalize_intro_text_markup,
    strip_intro_text_markup,
)
from .deterministic_fields import extract_commercial_family_from_title
from .mapping import serialize_meta_keywords
from .models import CLIInput, ParsedProduct, SourceProductData, TaxonomyResolution
from .normalize import normalize_whitespace
from .text_health import detect_text_issues

INTRO_MIN_WORDS = 80
INTRO_MAX_WORDS = 180
HTML_TAG_RE = re.compile(r"<[^>]+>")
HTML_DETECT_RE = re.compile(r"<[^>]+>")
INTRO_TEXT_TASK = "intro_text"
SEO_META_TASK = "seo_meta"
MAX_TASK_KEY_SPECS = 6


def build_intro_text_context(
    cli: CLIInput,
    parsed: ParsedProduct,
    taxonomy: TaxonomyResolution,
    deterministic_product: dict[str, Any],
    intro_policy: Any | None = None,
) -> dict[str, Any]:
    source = parsed.source
    product_identity = _build_product_identity(source, deterministic_product, taxonomy)
    intro_word_min = _policy_int(intro_policy, "min_words", INTRO_MIN_WORDS)
    intro_word_max = _policy_int(intro_policy, "max_words", INTRO_MAX_WORDS)
    intro_max_emphasized_word_ratio = _policy_float(
        intro_policy,
        "max_emphasized_word_ratio",
        MAX_EMPHASIZED_WORD_RATIO,
    )
    return {
        "task": INTRO_TEXT_TASK,
        "input": {
            "model": cli.model,
            "url": cli.url,
        },
        "product": {
            **product_identity,
            "sub_category": str(taxonomy.sub_category or "").strip(),
        },
        "evidence": {
            "hero_summary": normalize_whitespace(source.hero_summary),
            "key_specs": _compact_key_specs(source.key_specs),
            "deterministic_differentiators": _compact_values(deterministic_product.get("name_differentiators", [])),
        },
        "writer_rules": {
            "language": "Greek",
            "llm_owned_fields": [INTRO_TEXT_TASK],
            "plain_text_only": False,
            "output_format": "single_greek_paragraph_with_limited_strong_html",
            "allowed_inline_html_tags": ["strong"],
            "paragraphs": 1,
            "word_count_range": {"min": intro_word_min, "max": intro_word_max},
            "forbidden_outputs": ["json", "markdown", "bullets", "cta_language", "unsupported_html"],
            "emphasis_policy": {
                "scope": "generic_all_categories",
                "purpose": "human_readability_and_topical_clarity",
                "preferred_span_count": {"min": 3, "max": 7},
                "max_emphasized_word_ratio": intro_max_emphasized_word_ratio,
                "bold_verified_facts_only": True,
                "avoid_full_sentence_emphasis": True,
                "avoid_generic_benefit_emphasis": True,
            },
        },
    }


def build_seo_meta_context(
    cli: CLIInput,
    parsed: ParsedProduct,
    taxonomy: TaxonomyResolution,
    deterministic_product: dict[str, Any],
) -> dict[str, Any]:
    source = parsed.source
    product_identity = _build_product_identity(source, deterministic_product, taxonomy)
    brand = product_identity["brand"]
    preferred_identifier = product_identity["preferred_identifier"]
    return {
        "task": SEO_META_TASK,
        "input": {
            "model": cli.model,
            "url": cli.url,
        },
        "product": {
            **product_identity,
            "sub_category": str(taxonomy.sub_category or "").strip(),
            "meta_title": str(deterministic_product.get("meta_title", "") or "").strip(),
            "seo_keyword": str(deterministic_product.get("seo_keyword", "") or "").strip(),
        },
        "evidence": {
            "meta_description_draft": _apply_preferred_identifier(
                str(deterministic_product.get("meta_description_draft", "") or ""),
                product_identity,
            ),
            "hero_summary": normalize_whitespace(source.hero_summary),
            "key_specs": _compact_key_specs(source.key_specs),
            "deterministic_differentiators": _compact_values(deterministic_product.get("name_differentiators", [])),
        },
        "writer_rules": {
            "language": "Greek",
            "llm_owned_fields": ["product.meta_description", "product.meta_keywords"],
            "meta_description_rule": (
                "Prefer 2 natural Greek sentences using verified evidence only and no HTML. "
                "Sentence 1 identifies the product using brand + preferred_identifier + category + strongest verified differentiators. "
                "When product.model_name is present, preferred_identifier is the model name and must be used in prose instead of the raw MPN. "
                "Sentence 2 adds 2-4 verified features/benefits only from evidence already present in context, with evidence priority: "
                "1. `hero_summary` 2. `key_specs` 3. `deterministic_differentiators`. "
                "For TVs prefer `115 ιντσών` rather than `115\"`; if `4K` is verified, prefer `4K Ultra HD ανάλυση`; if `8K` is verified, prefer `8K Ultra HD ανάλυση`. "
                "Aim for roughly `160-260` characters unless verified detail clearly justifies somewhat more."
            ),
            "meta_keywords_rule": "Return a structured JSON array of verified keywords only. Do not serialize as CSV. Always include brand and preferred_identifier; when product.model_name is present, prefer it over product.mpn.",
            "required_keywords": [value for value in [brand, preferred_identifier] if value],
        },
    }


def build_task_manifest(
    *,
    llm_dir: str,
    intro_text_context_path: str,
    intro_text_prompt_path: str,
    intro_text_output_path: str,
    seo_meta_context_path: str,
    seo_meta_prompt_path: str,
    seo_meta_output_path: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "prepare_mode": "split_tasks",
        "primary_outputs": {
            "llm_dir": llm_dir,
            "tasks": {
                INTRO_TEXT_TASK: {
                    "context_path": intro_text_context_path,
                    "prompt_path": intro_text_prompt_path,
                    "expected_output_path": intro_text_output_path,
                    "output_mode": "plain_text",
                    "llm_owned_fields": [INTRO_TEXT_TASK],
                },
                SEO_META_TASK: {
                    "context_path": seo_meta_context_path,
                    "prompt_path": seo_meta_prompt_path,
                    "expected_output_path": seo_meta_output_path,
                    "output_mode": "json",
                    "llm_owned_fields": ["product.meta_description", "product.meta_keywords"],
                },
            },
        },
    }


def count_html_words(value: str) -> int:
    text = normalize_whitespace(HTML_TAG_RE.sub(" ", value or ""))
    return len([token for token in text.split(" ") if token])


def validate_intro_text_output(
    payload: str | dict[str, Any],
    *,
    intro_word_min: int = INTRO_MIN_WORDS,
    intro_word_max: int = INTRO_MAX_WORDS,
    intro_max_emphasized_word_ratio: float = MAX_EMPHASIZED_WORD_RATIO,
) -> tuple[str, list[str]]:
    errors: list[str] = []
    value = payload.get("intro_text", "") if isinstance(payload, dict) else payload
    if not isinstance(value, str):
        return "", ["llm_intro_text_invalid"]
    normalized, markup_errors = normalize_intro_text_markup(
        value,
        max_emphasized_word_ratio=intro_max_emphasized_word_ratio,
    )
    unsupported_tags = [
        tag for tag in HTML_DETECT_RE.findall(value)
        if tag.lower() not in {"<strong>", "</strong>"}
    ]
    if unsupported_tags:
        errors.append("llm_intro_text_html_invalid")
    errors.extend(markup_errors)
    visible_text = strip_intro_text_markup(normalized)
    if detect_text_issues(visible_text):
        errors.append("llm_intro_text_encoding_invalid")
    word_count = count_intro_text_words(normalized)
    if word_count < intro_word_min or word_count > intro_word_max:
        errors.append("llm_intro_text_word_count_invalid")
    return normalized, _unique_codes(errors)


def validate_seo_meta_output(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {}, ["llm_seo_meta_not_object"]
    if set(payload) != {"product"}:
        errors.append("llm_seo_meta_root_shape_invalid")
    product = payload.get("product")
    if not isinstance(product, dict):
        return {}, ["llm_seo_meta_product_invalid"]
    product_keys = set(product)
    if product_keys not in ({"meta_description", "meta_keywords"}, {"meta_description", "meta_keywords", "name_tail_polished"}):
        errors.append("llm_seo_meta_shape_invalid")
    meta_description = product.get("meta_description", "")
    meta_keywords = product.get("meta_keywords", [])
    if not isinstance(meta_description, str):
        errors.append("llm_seo_meta_description_invalid")
    elif detect_text_issues(meta_description):
        errors.append("llm_seo_meta_description_encoding_invalid")
    if not isinstance(meta_keywords, list) or any(not isinstance(item, str) for item in meta_keywords):
        errors.append("llm_seo_meta_keywords_invalid")
    elif any(detect_text_issues(item) for item in meta_keywords):
        errors.append("llm_seo_meta_keywords_encoding_invalid")
    return {
        "product": {
            "meta_description": normalize_whitespace(meta_description),
            "meta_keywords": [normalize_whitespace(item) for item in meta_keywords if normalize_whitespace(item)],
            "meta_keyword_csv": serialize_meta_keywords(meta_keywords),
        }
    }, errors


def count_plain_text_words(value: str) -> int:
    return count_intro_text_words(value)


def _build_product_identity(
    source: SourceProductData,
    deterministic_product: dict[str, Any],
    taxonomy: TaxonomyResolution,
) -> dict[str, str]:
    name = str(deterministic_product.get("name", "") or source.name or "").strip()
    brand = str(deterministic_product.get("brand", "") or source.brand or "").strip()
    mpn = str(deterministic_product.get("mpn", "") or source.mpn or "").strip()
    category = str(deterministic_product.get("category_phrase", "") or taxonomy.leaf_category or "").strip()
    model_name = _extract_model_name(source, deterministic_product, brand, mpn)
    preferred_identifier = model_name or mpn
    copy_name = _build_copy_name(name, brand, preferred_identifier, category)
    return {
        "name": name,
        "copy_name": copy_name,
        "brand": brand,
        "model_name": model_name,
        "mpn": mpn,
        "preferred_identifier": preferred_identifier,
        "category": category,
    }


def _extract_model_name(source: SourceProductData, deterministic_product: dict[str, Any], brand: str, mpn: str) -> str:
    explicit_candidates = [
        deterministic_product.get("model_name", ""),
        deterministic_product.get("commercial_model_name", ""),
        deterministic_product.get("model_family", ""),
    ]
    for candidate in explicit_candidates:
        model_name = normalize_whitespace(str(candidate or ""))
        if _looks_like_model_name(model_name, brand, mpn):
            return model_name

    for title in [source.name, deterministic_product.get("source_name", ""), deterministic_product.get("name", "")]:
        family = extract_commercial_family_from_title(str(title or ""), brand, mpn)
        if _looks_like_model_name(family, brand, mpn):
            return family
    return ""


def _build_copy_name(name: str, brand: str, preferred_identifier: str, category: str) -> str:
    if not brand or not preferred_identifier:
        return name
    parts = [brand, preferred_identifier]
    if category and category.casefold() not in {brand.casefold(), preferred_identifier.casefold()}:
        parts.append(category)
    return normalize_whitespace(" ".join(parts))


def _apply_preferred_identifier(value: str, product_identity: dict[str, str]) -> str:
    normalized = normalize_whitespace(value)
    model_name = product_identity.get("model_name", "")
    mpn = product_identity.get("mpn", "")
    if not normalized or not model_name or not mpn:
        return normalized
    return normalize_whitespace(re.sub(re.escape(mpn), model_name, normalized, flags=re.IGNORECASE))


def _looks_like_model_name(value: str, brand: str, mpn: str) -> bool:
    normalized = normalize_whitespace(value)
    if not normalized:
        return False
    lowered = normalized.casefold()
    if lowered in {brand.casefold(), mpn.casefold()}:
        return False
    if not any(char.isalpha() for char in normalized):
        return False
    tokens = normalized.split()
    if len(tokens) > 6:
        return False
    if "_" in normalized:
        return False
    if len(tokens) == 1 and re.fullmatch(r"[A-Z0-9._/-]+", normalized):
        return False
    return True


def _compact_key_specs(items: list[Any]) -> list[dict[str, str]]:
    compact: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        label = normalize_whitespace(getattr(item, "label", ""))
        value = normalize_whitespace(getattr(item, "value", ""))
        if not label or not value:
            continue
        key = (label.casefold(), value.casefold())
        if key in seen:
            continue
        seen.add(key)
        compact.append({"label": label, "value": value})
        if len(compact) >= MAX_TASK_KEY_SPECS:
            break
    return compact


def _compact_values(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    compact: list[str] = []
    seen: set[str] = set()
    for item in values:
        value = normalize_whitespace(item)
        if not value:
            continue
        lowered = value.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        compact.append(value)
    return compact


def _policy_int(policy: Any | None, field_name: str, default: int) -> int:
    if policy is None:
        return default
    if isinstance(policy, dict):
        value = policy.get(field_name, default)
    else:
        value = getattr(policy, field_name, default)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _policy_float(policy: Any | None, field_name: str, default: float) -> float:
    if policy is None:
        return default
    if isinstance(policy, dict):
        value = policy.get(field_name, default)
    else:
        value = getattr(policy, field_name, default)
    return float(value) if isinstance(value, (float, int)) and not isinstance(value, bool) else default


def _unique_codes(codes: list[str]) -> list[str]:
    out: list[str] = []
    for code in codes:
        if code not in out:
            out.append(code)
    return out
