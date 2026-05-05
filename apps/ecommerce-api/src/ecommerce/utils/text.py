"""Text helpers for strict MPN normalization, product-name comparison, and Greek money parsing."""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

PRODUCT_TEXT_STOPWORDS: frozenset[str] = frozenset(
    {
        "miele",
        "skoupa",
        "skoypa",
        "ilektriki",
        "me",
        "xoris",
        "sakoula",
        "kai",
        "cheiros",
        "xeiros",
        "stick",
        "epanafortizomeni",
        "asyrmati",
        "se",
        "bestprice",
        "gr",
    }
)

PRODUCT_TOKEN_EQUIVALENTS: dict[str, str] = {
    "kokkini": "red",
    "kokkino": "red",
    "mple": "blue",
    "ble": "blue",
    "leyki": "white",
    "leyko": "white",
    "lefki": "white",
    "lefko": "white",
    "mayri": "black",
    "mayro": "black",
    "mavri": "black",
    "mavro": "black",
    "gkri": "grey",
}

PRODUCT_SEARCH_NOISE_TOKENS: frozenset[str] = frozenset({"airclean"})

_GREEK_TO_LATIN = str.maketrans(
    {
        "α": "a",
        "β": "v",
        "γ": "g",
        "δ": "d",
        "ε": "e",
        "ζ": "z",
        "η": "i",
        "θ": "th",
        "ι": "i",
        "κ": "k",
        "λ": "l",
        "μ": "m",
        "ν": "n",
        "ξ": "x",
        "ο": "o",
        "π": "p",
        "ρ": "r",
        "σ": "s",
        "ς": "s",
        "τ": "t",
        "υ": "y",
        "φ": "f",
        "χ": "ch",
        "ψ": "ps",
        "ω": "o",
    }
)


def collapse_internal_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strict_normalize_mpn(value: str) -> str:
    return collapse_internal_spaces(value).casefold()


def normalize_product_text(value: str) -> str:
    text = collapse_internal_spaces(value)
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold()
    text = text.translate(_GREEK_TO_LATIN)
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return collapse_internal_spaces(text)


def product_tokens(value: str) -> tuple[str, ...]:
    normalized = normalize_product_text(value)
    if not normalized:
        return ()

    tokens: list[str] = []
    for token in normalized.split():
        token = PRODUCT_TOKEN_EQUIVALENTS.get(token, token)
        if len(token) < 2:
            continue
        if token in PRODUCT_TEXT_STOPWORDS:
            continue
        tokens.append(token)
    return tuple(tokens)


def build_product_search_queries(value: str) -> tuple[str, ...]:
    queries: list[str] = []
    raw_query = collapse_internal_spaces(value)
    if raw_query:
        queries.append(raw_query)

    tokens = product_tokens(value)
    concise_tokens = tuple(
        token
        for token in tokens
        if not _is_search_noise_token(token) and not _looks_like_variant_code(token)
    )
    broad_tokens = tuple(token for token in tokens if not _is_search_noise_token(token))

    for candidate_tokens in (concise_tokens, broad_tokens):
        if not candidate_tokens:
            continue
        query = f"Miele {' '.join(candidate_tokens)}"
        if query not in queries:
            queries.append(query)

    return tuple(queries)


def _is_search_noise_token(token: str) -> bool:
    if token in PRODUCT_SEARCH_NOISE_TOKENS:
        return True
    if re.fullmatch(r"\d{5,}", token):
        return True
    if re.fullmatch(r"\d+(?:x\d+)+", token):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?(?:w|v|l|lt)", token):
        return True
    return False


def _looks_like_variant_code(token: str) -> bool:
    if token in {"m1", "l1", "s1", "hx1", "hx2", "cx1"}:
        return False
    return bool(re.fullmatch(r"[a-z]{4,}\d+[a-z0-9]*", token))


def parse_greek_money_text(value: str) -> Decimal:
    text = collapse_internal_spaces(value)
    text = text.replace("\xa0", " ").replace("€", "").replace("β‚¬", "").replace("EUR", "").strip()
    if not text:
        raise ValueError("price parse failed")
    if not re.fullmatch(r"\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?", text):
        raise ValueError("price parse failed")

    normalized = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError("price parse failed") from exc
