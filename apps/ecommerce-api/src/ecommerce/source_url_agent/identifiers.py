"""Shared product identifier variants for source URL discovery."""

from __future__ import annotations

import re
import unicodedata

from ecommerce.source_url_agent.products import AgentProduct
from ecommerce.utils.text import collapse_internal_spaces

MAX_BRAVE_IDENTIFIER_VARIANTS = 2
SPLIT_AC_MPN_RE = re.compile(
    r"^([A-Za-z0-9]+)\/([A-Za-z0-9]+)-([A-Za-z0-9][A-Za-z0-9-]*)$"
)


def identifier_variants_for_product(product: AgentProduct) -> list[str]:
    identifier = collapse_internal_spaces(product.mpn) or collapse_internal_spaces(
        product.model
    )
    if not identifier:
        return []
    return identifier_variants(
        identifier,
        is_air_conditioner=is_air_conditioner_product(product),
    )


def identifier_variants(
    identifier: str, *, is_air_conditioner: bool = False
) -> list[str]:
    raw = collapse_internal_spaces(identifier)
    if not raw:
        return []
    variants = [raw]
    if is_air_conditioner:
        expanded = split_ac_mpn_variant(raw)
        if expanded and expanded.casefold() != raw.casefold():
            variants.append(expanded)
    return variants[:MAX_BRAVE_IDENTIFIER_VARIANTS]


def split_ac_mpn_variant(identifier: str) -> str:
    match = SPLIT_AC_MPN_RE.fullmatch(collapse_internal_spaces(identifier))
    if match is None:
        return ""
    first, second, suffix = match.groups()
    return f"{first}-{suffix}/{second}-{suffix}"


def is_air_conditioner_product(product: AgentProduct) -> bool:
    values = [
        product.category,
        product.raw_row.get("category", ""),
        product.raw_row.get("raw_category", ""),
        product.raw_row.get("category_name", ""),
        product.raw_row.get("sub_category", ""),
        product.raw_row.get("family", ""),
    ]
    return any(_is_air_conditioner_text(value) for value in values)


def _is_air_conditioner_text(value: object) -> bool:
    text = _normalized_text(value)
    if not text:
        return False
    compact = re.sub(r"[^a-z0-9\u0370-\u03ff]+", "", text)
    return any(
        marker in text or marker in compact
        for marker in (
            "air conditioner",
            "air conditioners",
            "airconditioner",
            "airconditioners",
            "klimatistiko",
            "klimatistika",
            "klimatisitiko",
            "klimatisitika",
            "\u03ba\u03bb\u03b9\u03bc\u03b1\u03c4\u03b9\u03c3\u03c4\u03b9\u03ba",
        )
    )


def _normalized_text(value: object) -> str:
    text = collapse_internal_spaces(value).casefold()
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
