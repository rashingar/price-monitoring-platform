from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from .models import SourceProductData, SpecItem
from .normalize import (
    candidate_label_keys,
    normalize_for_match,
    normalize_whitespace,
    safe_text,
)

_PAIR_RE = re.compile(
    r"(?P<label>[^:]{2,90}?):\s*(?P<value>.+?)(?=(?:\s+[A-Za-zΑ-ΩΆ-Ώα-ωά-ώ][^:]{1,90}:)|$)"
)
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!;·•])\s+")
_TRAILING_VALUE_PUNCTUATION_RE = re.compile(r"[\s.;·•]+$")
_LABEL_REJECT_RE = re.compile(r"^[\W\d_]+$")
_LABEL_DENY_TOKENS = {"model", "art no", "artno", "κωδικος", "κωδικός"}
_VALUE_REJECT = {"", "-", "—", "–", "n/a", "na"}


@dataclass(frozen=True, slots=True)
class DescriptionSpec:
    label: str
    value: str
    source: str


def extract_description_specs(source: SourceProductData) -> list[DescriptionSpec]:
    """Return explicit label/value facts from free-form source descriptions."""
    seen: set[tuple[str, str]] = set()
    specs: list[DescriptionSpec] = []
    for source_name, chunk in _iter_description_chunks(source):
        for label, value in _scan_label_value_pairs(chunk):
            key = (normalize_for_match(label), normalize_for_match(value))
            if not key[0] or not key[1] or key in seen:
                continue
            seen.add(key)
            specs.append(DescriptionSpec(label=label, value=value, source=source_name))
    return specs


def build_description_spec_items(source: SourceProductData) -> list[SpecItem]:
    return [
        SpecItem(label=spec.label, value=spec.value)
        for spec in extract_description_specs(source)
    ]


def build_description_spec_lookup(source: SourceProductData) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for spec in extract_description_specs(source):
        for key in candidate_label_keys(spec.label) or {
            normalize_whitespace(spec.label)
        }:
            if key and spec.value and key not in lookup:
                lookup[key] = spec.value
    return lookup


def _iter_description_chunks(source: SourceProductData) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    html = normalize_whitespace(source.presentation_source_html)
    if html:
        chunks.extend(_html_description_chunks(html))
    for field_name, text in (
        ("hero_summary", source.hero_summary),
        ("presentation_source_text", source.presentation_source_text),
        ("manufacturer_source_text", source.manufacturer_source_text),
    ):
        normalized = normalize_whitespace(text)
        if normalized:
            for sentence in _split_description_text(normalized):
                chunks.append((field_name, sentence))
    return chunks


def _html_description_chunks(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    chunks: list[tuple[str, str]] = []
    for dt in soup.select("dt"):
        dd = dt.find_next_sibling("dd")
        label = safe_text(dt)
        value = safe_text(dd)
        if label and value:
            chunks.append(("presentation_source_html:dt_dd", f"{label}: {value}"))
    for row in soup.select("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) >= 2:
            label = safe_text(cells[0])
            value = safe_text(cells[1])
            if label and value:
                chunks.append(("presentation_source_html:table", f"{label}: {value}"))
    for node in _description_text_nodes(soup):
        text = safe_text(node)
        if text:
            chunks.append(("presentation_source_html:text", text))
    return chunks


def _description_text_nodes(soup: BeautifulSoup) -> list[Tag]:
    nodes: list[Tag] = []
    for selector in ("li", "p", ".body-text"):
        for node in soup.select(selector):
            if isinstance(node, Tag) and node not in nodes:
                nodes.append(node)
    if nodes:
        return nodes
    body = soup.body or soup
    return [body] if isinstance(body, Tag) else []


def _split_description_text(text: str) -> list[str]:
    out: list[str] = []
    for chunk in _SENTENCE_BOUNDARY_RE.split(text):
        normalized = normalize_whitespace(chunk)
        if normalized:
            out.append(normalized)
    return out or [normalize_whitespace(text)]


def _scan_label_value_pairs(text: str) -> list[tuple[str, str]]:
    normalized = normalize_whitespace(text)
    if ":" not in normalized:
        return []
    pairs: list[tuple[str, str]] = []
    for match in _PAIR_RE.finditer(normalized):
        label = _clean_description_label(match.group("label"))
        value = _clean_description_value(match.group("value"))
        if _valid_description_pair(label, value):
            pairs.append((label, value))
    return pairs


def _clean_description_label(value: str) -> str:
    return normalize_whitespace(value).strip(" -–—•.;")


def _clean_description_value(value: str) -> str:
    cleaned = normalize_whitespace(value)
    cleaned = _TRAILING_VALUE_PUNCTUATION_RE.sub("", cleaned)
    return normalize_whitespace(cleaned)


def _valid_description_pair(label: str, value: str) -> bool:
    if not label or not value:
        return False
    if len(label) > 90 or len(value) > 260:
        return False
    if "|" in label:
        return False
    normalized_label = normalize_for_match(label)
    if any(token in normalized_label for token in _LABEL_DENY_TOKENS):
        return False
    if _LABEL_REJECT_RE.fullmatch(label):
        return False
    if normalize_for_match(value) in _VALUE_REJECT:
        return False
    if normalize_for_match(label) == normalize_for_match(value):
        return False
    return True
