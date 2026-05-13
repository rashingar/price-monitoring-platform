"""Composite and bundle mismatch detection for Source URL Agent candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ecommerce.source_url_agent.evidence import PageEvidence
from ecommerce.source_url_agent.products import AgentProduct
from ecommerce.utils.text import normalize_product_text


COMPOSITE_PHRASE_MARKERS: tuple[str, ...] = (
    "me esties",
    "me epagogikes",
    "me epagogikes esties",
    "me keramikes",
    "me keramikes esties",
    "foyrnos me esties",
    "fournos me esties",
    "mazi me",
)
BUNDLE_WORD_MARKERS: tuple[str, ...] = ("set", "kit", "bundle", "combo", "syndyasmos", "paketo", "package")
CONNECTOR_MARKERS: tuple[str, ...] = ("+", "&", "kai", "and", "with", "me", "mazi")
IDENTIFIER_RE = re.compile(r"(?<![A-Za-z0-9])(?=[A-Za-z0-9]{5,})(?:[A-Za-z]*\d){2,}[A-Za-z0-9]*(?![A-Za-z0-9])")


@dataclass(frozen=True)
class CompositeMismatchResult:
    is_mismatch: bool
    reason: str
    markers: tuple[str, ...]
    extra_identifiers: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "is_mismatch": self.is_mismatch,
            "reason": self.reason,
            "markers": list(self.markers),
            "extra_identifiers": list(self.extra_identifiers),
        }


def detect_composite_mismatch(product: AgentProduct, evidence: PageEvidence) -> CompositeMismatchResult:
    expected_identifiers = catalog_product_identifiers(product)
    if not expected_identifiers:
        return _no_mismatch()

    candidate_texts = _candidate_texts(evidence)
    candidate_text = " ".join(candidate_texts)
    candidate_identifiers = extract_product_code_identifiers(candidate_text)
    extra_identifiers = tuple(identifier for identifier in candidate_identifiers if identifier not in expected_identifiers)
    has_expected_identifier = evidence.exact_mpn_found or any(
        _identifier_in_text(identifier, text) for identifier in expected_identifiers for text in candidate_texts
    )
    if not has_expected_identifier:
        return _no_mismatch()

    markers: list[str] = []
    phrase_markers = _composite_phrase_markers(candidate_text)
    if phrase_markers:
        markers.extend(phrase_markers)
    if extra_identifiers and _expected_and_extra_are_connected(candidate_texts, expected_identifiers, extra_identifiers):
        markers.append("expected_identifier_joined_with_extra_identifier")
    if extra_identifiers:
        markers.extend(_bundle_word_markers(candidate_text))

    markers_tuple = tuple(dict.fromkeys(markers))
    if not markers_tuple:
        return _no_mismatch()
    if catalog_product_appears_composite(product):
        return _no_mismatch()

    return CompositeMismatchResult(
        is_mismatch=True,
        reason=_reason(markers_tuple, extra_identifiers),
        markers=markers_tuple,
        extra_identifiers=extra_identifiers,
    )


def catalog_product_appears_composite(product: AgentProduct) -> bool:
    product_text = " ".join((product.mpn, product.name))
    identifiers = catalog_product_identifiers(product)
    if _composite_phrase_markers(product_text) or _bundle_word_markers(product_text):
        return True
    if len(identifiers) < 2:
        return False
    if len(extract_product_code_identifiers(product.mpn)) >= 2:
        return True
    if _expected_and_extra_are_connected((product_text,), identifiers, identifiers):
        return True
    return True


def catalog_product_identifiers(product: AgentProduct) -> tuple[str, ...]:
    identifiers: list[str] = []
    for value in (product.mpn, product.name):
        identifiers.extend(extract_product_code_identifiers(value))
    return tuple(dict.fromkeys(identifiers))


def extract_product_code_identifiers(*values: str) -> tuple[str, ...]:
    identifiers: list[str] = []
    for value in values:
        for token in _identifier_tokens(value):
            normalized = _normalize_identifier(token)
            if _looks_like_product_code(normalized):
                identifiers.append(normalized)
    return tuple(dict.fromkeys(identifiers))


def _identifier_tokens(value: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for raw in re.findall(r"[A-Za-z0-9][A-Za-z0-9_/-]*", str(value or "")):
        split_parts = [part for part in re.split(r"[/_]", raw) if part]
        for part in split_parts:
            tokens.extend(IDENTIFIER_RE.findall(part))
            hyphen_parts = [item for item in part.split("-") if item]
            if len(hyphen_parts) == 2 and all(len(item) <= 4 for item in hyphen_parts):
                tokens.append("".join(hyphen_parts))
            elif len(hyphen_parts) > 2:
                tokens.extend(hyphen_parts)
    return tuple(tokens)


def _looks_like_product_code(identifier: str) -> bool:
    if len(identifier) < 5:
        return False
    digit_count = sum(char.isdigit() for char in identifier)
    letter_count = sum(char.isalpha() for char in identifier)
    return digit_count >= 2 and letter_count >= 1


def _candidate_texts(evidence: PageEvidence) -> tuple[str, ...]:
    jsonld_text = " ".join(_jsonld_values(item) for item in evidence.jsonld_products)
    return tuple(
        text
        for text in (
            evidence.title,
            evidence.canonical_url,
            evidence.requested_url,
            jsonld_text,
            evidence.body_text_sample,
        )
        if text
    )


def _jsonld_values(value: object) -> str:
    if isinstance(value, dict):
        return " ".join(_jsonld_values(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_jsonld_values(item) for item in value)
    return str(value or "")


def _composite_phrase_markers(value: str) -> tuple[str, ...]:
    normalized = f" {normalize_product_text(value)} "
    markers: list[str] = []
    for marker in sorted(COMPOSITE_PHRASE_MARKERS, key=len, reverse=True):
        if f" {marker} " not in normalized:
            continue
        if any(f" {marker} " in f" {existing} " for existing in markers):
            continue
        markers.append(marker)
    return tuple(marker for marker in COMPOSITE_PHRASE_MARKERS if marker in markers)


def _bundle_word_markers(value: str) -> tuple[str, ...]:
    tokens = set(normalize_product_text(value).split())
    return tuple(dict.fromkeys(marker for marker in BUNDLE_WORD_MARKERS if marker in tokens))


def _expected_and_extra_are_connected(
    texts: tuple[str, ...],
    expected_identifiers: tuple[str, ...],
    extra_identifiers: tuple[str, ...],
) -> bool:
    for text in texts:
        if _raw_plus_or_ampersand_join(text, expected_identifiers, extra_identifiers):
            return True
        tokens = normalize_product_text(text).split()
        for expected in expected_identifiers:
            expected_token = expected.casefold()
            expected_positions = [index for index, token in enumerate(tokens) if token == expected_token]
            if not expected_positions:
                continue
            for extra in extra_identifiers:
                extra_token = extra.casefold()
                extra_positions = [index for index, token in enumerate(tokens) if token == extra_token]
                for left in expected_positions:
                    for right in extra_positions:
                        if left == right or abs(left - right) > 6:
                            continue
                        between = tokens[min(left, right) + 1 : max(left, right)]
                        if any(token in CONNECTOR_MARKERS for token in between):
                            return True
    return False


def _raw_plus_or_ampersand_join(
    text: str,
    expected_identifiers: tuple[str, ...],
    extra_identifiers: tuple[str, ...],
) -> bool:
    normalized = str(text or "")
    for expected in expected_identifiers:
        for extra in extra_identifiers:
            if re.search(rf"\b{re.escape(expected)}\b\s*[+&]\s*\b{re.escape(extra)}\b", normalized, flags=re.IGNORECASE):
                return True
            if re.search(rf"\b{re.escape(extra)}\b\s*[+&]\s*\b{re.escape(expected)}\b", normalized, flags=re.IGNORECASE):
                return True
    return False


def _identifier_in_text(identifier: str, text: str) -> bool:
    return any(candidate == identifier for candidate in extract_product_code_identifiers(text))


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def _reason(markers: tuple[str, ...], extra_identifiers: tuple[str, ...]) -> str:
    if any(marker in COMPOSITE_PHRASE_MARKERS for marker in markers):
        return "candidate_contains_composite_phrase"
    if "expected_identifier_joined_with_extra_identifier" in markers:
        return "candidate_contains_expected_identifier_with_extra_identifier"
    if extra_identifiers:
        return "candidate_contains_bundle_marker_with_extra_identifier"
    return "candidate_contains_composite_marker"


def _no_mismatch() -> CompositeMismatchResult:
    return CompositeMismatchResult(is_mismatch=False, reason="", markers=(), extra_identifiers=())
