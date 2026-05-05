"""Source URL Agent evidence matching helpers."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re

from ecommerce.utils.text import normalize_product_text, product_tokens


@dataclass(frozen=True)
class MpnEvidence:
    fragment: str
    source: str


@dataclass(frozen=True)
class NameEvidence:
    score: float
    matched_tokens: tuple[str, ...]
    token_ratio: float
    sequence_ratio: float


def extract_mpn_evidence(mpn: str, title: str, body_text: str, html: str = "") -> MpnEvidence | None:
    needle = mpn.strip()
    haystacks = (
        ("title", title),
        ("body", body_text),
        ("html", html),
    )
    return _extract_from_haystacks(needle, haystacks)


def extract_name_evidence(row_name: str, title: str) -> NameEvidence | None:
    query_tokens = product_tokens(row_name)
    title_tokens = set(product_tokens(title))
    if not query_tokens or not title_tokens:
        return None

    matched_tokens = tuple(token for token in query_tokens if token in title_tokens)
    token_ratio = len(matched_tokens) / len(query_tokens)
    sequence_ratio = SequenceMatcher(
        None,
        normalize_product_text(row_name),
        normalize_product_text(title),
    ).ratio()
    score = (0.75 * token_ratio) + (0.25 * sequence_ratio)

    if len(matched_tokens) < 2:
        return None
    if token_ratio < 0.35 and sequence_ratio < 0.55:
        return None

    return NameEvidence(
        score=score,
        matched_tokens=matched_tokens,
        token_ratio=token_ratio,
        sequence_ratio=sequence_ratio,
    )


def _extract_from_haystacks(
    needle: str,
    haystacks: tuple[tuple[str, str], ...],
) -> MpnEvidence | None:
    for source, haystack in haystacks:
        exact_index = haystack.find(needle)
        if exact_index != -1:
            return MpnEvidence(
                fragment=haystack[exact_index : exact_index + len(needle)],
                source=source,
            )

    whitespace_parts = [re.escape(part) for part in needle.split()]
    if not whitespace_parts:
        return None
    pattern = re.compile(r"\s+".join(whitespace_parts), re.IGNORECASE)
    for source, haystack in haystacks:
        match = pattern.search(haystack)
        if match is not None:
            return MpnEvidence(fragment=match.group(0), source=source)

    return None
