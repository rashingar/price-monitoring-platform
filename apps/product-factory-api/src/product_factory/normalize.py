from __future__ import annotations

from functools import lru_cache
import json
import re
import unicodedata
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

from .repo_paths import LABEL_ALIASES_PATH

NBSP_PATTERN = re.compile(r"[\u00A0\u202F\u2007]")
WS_PATTERN = re.compile(r"\s+")
DASH_NULLS = {"", "-", "—", "–", "β€“", "β€”", "β’"}
GREEK_MATCH_RANGES = "\u0370-\u03ff\u1f00-\u1fff"
LABEL_ALIAS_FAMILY_PREFIX = "alias:"
_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_MOJIBAKE_MARKERS = frozenset("ΞΟ΅ΆΈΉΊΌΎΏΐΪΫάέήίΰϊϋόύώ™ƒ‡‚…„£»®µ­³½")
_LABEL_ALIAS_REGISTRY_PATH = LABEL_ALIASES_PATH

_GREEK_TRANSLIT = {
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
    "Ξ±": "a",
    "Ξ²": "v",
    "Ξ³": "g",
    "Ξ΄": "d",
    "Ξµ": "e",
    "Ξ¶": "z",
    "Ξ·": "i",
    "ΞΈ": "th",
    "ΞΉ": "i",
    "ΞΊ": "k",
    "Ξ»": "l",
    "ΞΌ": "m",
    "Ξ½": "n",
    "ΞΎ": "x",
    "ΞΏ": "o",
    "Ο€": "p",
    "Ο": "r",
    "Οƒ": "s",
    "Ο‚": "s",
    "Ο„": "t",
    "Ο…": "y",
    "Ο†": "f",
    "Ο‡": "ch",
    "Ο": "ps",
    "Ο‰": "o",
}


def strip_nbsp(text: str | None) -> str:
    if text is None:
        return ""
    return NBSP_PATTERN.sub(" ", unescape(str(text)))


def normalize_whitespace(text: str | None) -> str:
    return WS_PATTERN.sub(" ", strip_nbsp(text)).strip()


def safe_text(node: object) -> str:
    if node is None:
        return ""
    if hasattr(node, "get_text"):
        return normalize_whitespace(node.get_text(" ", strip=True))
    return normalize_whitespace(str(node))


def make_absolute_url(url: str | None, base: str) -> str:
    if not url:
        return ""
    return urljoin(base, url)


def parse_euro_price(text: str | None) -> float | None:
    if not text:
        return None
    cleaned_text = strip_nbsp(text)
    candidates = re.findall(
        r"(?:\d{1,3}(?:[.\s]\d{3})+|\d+)(?:[,.]\d{1,2})?\s*(?:€|β‚¬)?",
        cleaned_text,
    )
    if not candidates:
        return None
    for candidate in reversed(candidates):
        numeric = re.sub(r"[^0-9,.-]", "", candidate)
        if not numeric:
            continue
        if "," in numeric:
            numeric = numeric.replace(".", "").replace(",", ".")
        else:
            parts = numeric.split(".")
            if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
                numeric = "".join(parts)
        try:
            return float(numeric)
        except ValueError:
            continue
    return None


def nullify_dash_values(value: str | None) -> str | None:
    normalized = normalize_whitespace(value)
    return None if normalized in DASH_NULLS else normalized


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def strip_greek_accents(value: object) -> str:
    return _strip_accents(
        unicodedata.normalize(
            "NFC", normalize_whitespace("" if value is None else str(value))
        )
    )


def repair_mojibake_text(value: object) -> str:
    text = normalize_whitespace(None if value is None else str(value))
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    repaired = _repair_cp1253_utf8_mojibake(text)
    if repaired is not None and _repair_score(repaired) > _repair_score(text):
        text = repaired
    text = _CONTROL_PATTERN.sub("", text)
    return unicodedata.normalize("NFC", normalize_whitespace(text))


def normalize_greek_label(value: object) -> str:
    return repair_mojibake_text(value)


def normalize_label_key(value: object) -> str:
    return _normalize_match_key(repair_mojibake_text(value))


def normalize_for_match(text: str | None) -> str:
    return _normalize_match_key(repair_mojibake_text(text))


def _normalize_match_key(text: str | None) -> str:
    text = normalize_whitespace(text)
    if not text:
        return ""
    text = _strip_accents(text).lower()
    text = text.replace("&", " και ")
    text = re.sub(r"\bwatts\b", "watt", text, flags=re.IGNORECASE)
    text = re.sub(rf"[^a-z0-9{GREEK_MATCH_RANGES}\s]+", " ", text, flags=re.IGNORECASE)
    return normalize_whitespace(text)


def candidate_label_keys(value: object) -> set[str]:
    keys = {key for key in [_base_label_key(value)] if key}
    family_id = label_alias_family_id(value)
    if family_id:
        keys.add(f"{LABEL_ALIAS_FAMILY_PREFIX}{family_id}")
    return keys


def labels_equivalent(left: object, right: object) -> bool:
    left_keys = candidate_label_keys(left)
    right_keys = candidate_label_keys(right)
    if not left_keys or not right_keys:
        return False
    if left_keys & right_keys:
        return True
    compact_left = _compact_dimension_separator(_base_label_key(left))
    compact_right = _compact_dimension_separator(_base_label_key(right))
    return bool(compact_left and compact_left == compact_right)


def label_alias_family_id(value: object) -> str:
    key = _base_label_key(value)
    if not key:
        return ""
    return _label_alias_index().get(key, "")


def label_aliases_for(value: object) -> list[str]:
    family_id = label_alias_family_id(value)
    if not family_id:
        return []
    return list(_label_alias_families().get(family_id, ()))


def _base_label_key(value: object) -> str:
    return normalize_label_key(value)


def _without_parenthetical_key(value: object) -> str:
    text = normalize_greek_label(value)
    without_parenthetical = re.sub(r"\s*\([^)]*\)\s*", " ", text).strip()
    if without_parenthetical == text:
        return ""
    return normalize_label_key(without_parenthetical)


def _compact_dimension_separator(value: str) -> str:
    return normalize_whitespace(re.sub(r"\b[χx]\b", " ", value))


def _repair_cp1253_utf8_mojibake(text: str) -> str | None:
    if not _looks_like_greek_mojibake(text):
        return None
    encoded = bytearray()
    for ch in text:
        codepoint = ord(ch)
        if 0x80 <= codepoint <= 0x9F:
            encoded.append(codepoint)
            continue
        try:
            encoded.extend(ch.encode("cp1253"))
        except UnicodeEncodeError:
            return None
    try:
        return encoded.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _looks_like_greek_mojibake(text: str) -> bool:
    if not text:
        return False
    marker_count = sum(
        1 for ch in text if ch in _MOJIBAKE_MARKERS or 0x80 <= ord(ch) <= 0x9F
    )
    if marker_count < 2:
        return False
    greek_lower_count = sum(1 for ch in text if "α" <= ch <= "ω")
    return marker_count >= greek_lower_count + 2


def _repair_score(text: str) -> int:
    greek_letters = sum(
        1 for ch in text if "\u0370" <= ch <= "\u03ff" or "\u1f00" <= ch <= "\u1fff"
    )
    controls = sum(1 for ch in text if 0x80 <= ord(ch) <= 0x9F)
    mojibake_markers = sum(
        1 for ch in text if ch in {"Ξ", "Ο", "™", "ƒ", "‡", "‚", "…", "„"}
    )
    replacement = text.count("\ufffd")
    return greek_letters * 4 - controls * 8 - mojibake_markers * 2 - replacement * 10


@lru_cache(maxsize=1)
def load_label_alias_registry(
    path: str | Path = _LABEL_ALIAS_REGISTRY_PATH,
) -> dict[str, object]:
    registry_path = Path(path)
    if not registry_path.exists():
        return {"schema_version": 1, "families": []}
    with registry_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Label alias registry must be a JSON object: {registry_path}")
    families = payload.get("families", [])
    if not isinstance(families, list):
        raise ValueError(
            f"Label alias registry families must be a list: {registry_path}"
        )
    return payload


@lru_cache(maxsize=1)
def _label_alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for family in load_label_alias_registry().get("families", []):
        if not isinstance(family, dict):
            continue
        family_id = normalize_whitespace(str(family.get("family_id", "")))
        if not family_id:
            continue
        values = [
            family.get("canonical_label", ""),
            *list(
                family.get("aliases", [])
                if isinstance(family.get("aliases"), list)
                else []
            ),
            *list(
                family.get("mojibake_examples", [])
                if isinstance(family.get("mojibake_examples"), list)
                else []
            ),
        ]
        for value in values:
            key = _base_label_key(value)
            if key:
                index.setdefault(key, family_id)
            parenthetical_key = _without_parenthetical_key(value)
            if parenthetical_key:
                index.setdefault(parenthetical_key, family_id)
    return index


@lru_cache(maxsize=1)
def _label_alias_families() -> dict[str, tuple[str, ...]]:
    families: dict[str, tuple[str, ...]] = {}
    for family in load_label_alias_registry().get("families", []):
        if not isinstance(family, dict):
            continue
        family_id = normalize_whitespace(str(family.get("family_id", "")))
        if not family_id:
            continue
        values = [
            family.get("canonical_label", ""),
            *list(
                family.get("aliases", [])
                if isinstance(family.get("aliases"), list)
                else []
            ),
            *list(
                family.get("mojibake_examples", [])
                if isinstance(family.get("mojibake_examples"), list)
                else []
            ),
        ]
        aliases: list[str] = []
        for value in values:
            raw_alias = normalize_whitespace(str(value or ""))
            if raw_alias and raw_alias not in aliases:
                aliases.append(raw_alias)
            alias = normalize_greek_label(value)
            if alias and alias not in aliases:
                aliases.append(alias)
        families[family_id] = tuple(aliases)
    return families


def slugify_greek_for_seo(text: str | None) -> str:
    text = normalize_whitespace(text)
    if not text:
        return ""
    text = _strip_accents(text).lower()
    text = text.replace("ου", "ou").replace("ΞΏΟ…", "ou")
    text = re.sub(r"(?<=\d)[.,](?=\d)", "", text)
    chars: list[str] = []
    for ch in text:
        if ch in _GREEK_TRANSLIT:
            chars.append(_GREEK_TRANSLIT[ch])
        elif ch.isalnum():
            chars.append(ch)
        else:
            chars.append("-")
    slug = "".join(chars)
    slug = re.sub(r"[^a-z0-9-]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug


def dedupe_urls_preserve_order(urls: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        url = normalize_whitespace(raw)
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def clean_breadcrumbs(items: list[str]) -> list[str]:
    cleaned: list[str] = []
    previous = None
    for item in items:
        value = normalize_whitespace(item)
        if not value:
            continue
        if value == previous:
            continue
        cleaned.append(value)
        previous = value
    return cleaned


def split_visible_lines(text: str | None) -> list[str]:
    if not text:
        return []
    lines = [normalize_whitespace(line) for line in strip_nbsp(text).splitlines()]
    return [line for line in lines if line]
