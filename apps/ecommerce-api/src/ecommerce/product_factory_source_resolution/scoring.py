"""Candidate scoring for Product Factory source resolution."""

from __future__ import annotations

import re
from typing import Any

from ecommerce.product_factory_source_resolution.config import PreferredSourceConfig
from ecommerce.product_factory_source_resolution.models import SourceResolutionProduct


def score_candidate(*, product: SourceResolutionProduct, source: PreferredSourceConfig, item: Any, url: str) -> int:
    title = str(getattr(item, "title", "") or "")
    description = str(getattr(item, "description", "") or "")
    extra_snippets = " ".join(str(value) for value in getattr(item, "extra_snippets", ()) or ())
    haystack = " ".join([url, title, description, extra_snippets])
    score = min(40.0, max(0.0, source.weight * 0.4))
    score += _identity_score(product, haystack)
    score += _manufacturer_score(product, haystack)
    score += _name_overlap_score(product.name, haystack, limit=12.0)
    score += 8.0
    score += _title_description_score(product.name, title, description)
    rank = getattr(item, "rank", None)
    if isinstance(rank, int) and rank > 0:
        score += max(0.0, 6.0 - min(rank, 6))
    return min(100, int(round(score)))


def _identity_score(product: SourceResolutionProduct, haystack: str) -> float:
    normalized = _alnum(haystack)
    score = 0.0
    for value in (product.mpn, product.barcode, product.metadata.get("mpn", ""), product.metadata.get("barcode", "")):
        normalized_value = _alnum(str(value or ""))
        if normalized_value and normalized_value in normalized:
            score += 20.0
            break
    model = _alnum(product.model)
    if model and model in normalized:
        score += 5.0
    return min(score, 25.0)


def _manufacturer_score(product: SourceResolutionProduct, haystack: str) -> float:
    manufacturer = str(product.brand or product.metadata.get("manufacturer") or "").strip()
    if manufacturer and _alnum(manufacturer) in _alnum(haystack):
        return 8.0
    return 0.0


def _name_overlap_score(name: str, haystack: str, *, limit: float) -> float:
    tokens = _token_set(name)
    if not tokens:
        return 0.0
    haystack_tokens = _token_set(haystack)
    if not haystack_tokens:
        return 0.0
    overlap = len(tokens & haystack_tokens) / len(tokens)
    return limit * overlap


def _title_description_score(name: str, title: str, description: str) -> float:
    title_score = _name_overlap_score(name, title, limit=4.0)
    description_score = _name_overlap_score(name, description, limit=3.0)
    return title_score + description_score


def _token_set(value: str) -> set[str]:
    return {token for token in re.findall(r"[\w]+", value.casefold()) if len(token) >= 3}


def _alnum(value: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", value.casefold())
