from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from .models import NormalizedPresentationSection, NormalizedPresentationSectionMetrics
from .normalize import normalize_for_match, normalize_whitespace

ALPHABETIC_RE = re.compile(r"[^\W\d_]", re.UNICODE)
WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
REPEATED_WORD_RE = re.compile(r"\b([^\W\d_]{2,})\b(?:\s+\1\b){3,}", re.IGNORECASE)
NOISY_TAGS = {"script", "style", "noscript", "iframe", "svg", "img", "picture", "source", "video", "audio", "canvas"}

MISSING_QUALITY = "missing"
WEAK_QUALITY = "weak"
USABLE_QUALITY = "usable"

REASON_MISSING_EXTRACTION = "missing_extraction"
REASON_MISSING_EMPTY_AFTER_CLEAN = "missing_empty_after_clean"
REASON_MISSING_IMAGE_ONLY = "missing_image_only"
REASON_WEAK_SHORT_BODY = "weak_short_body"
REASON_WEAK_MISSING_TITLE = "weak_missing_title"
REASON_WEAK_NOISY_BODY = "weak_noisy_body"
REASON_WEAK_DUPLICATE = "weak_duplicate"
REASON_USABLE_CLEAN = "usable_clean"

MISSING_MIN_WORDS = 6
MISSING_MIN_ALPHA_CHARS = 30
USABLE_MIN_WORDS = 25
USABLE_MIN_ALPHA_CHARS = 120


def normalize_presentation_sections(
    sections: list[dict[str, Any]] | None,
    *,
    sections_requested: int | None = None,
) -> list[NormalizedPresentationSection]:
    items = list(sections or [])
    total = len(items)
    if sections_requested is not None:
        total = max(total, max(int(sections_requested), 0))

    normalized: list[NormalizedPresentationSection] = []
    accepted_body_keys: set[str] = set()
    for index in range(total):
        raw_section = items[index] if index < len(items) else None
        section = _normalize_section(raw_section, source_index=index + 1)
        body_key = normalize_for_match(section.body_text)
        if section.quality != MISSING_QUALITY and body_key:
            if body_key in accepted_body_keys:
                section.quality = WEAK_QUALITY
                section.reason = REASON_WEAK_DUPLICATE
                section.metrics.is_duplicate = True
            else:
                accepted_body_keys.add(body_key)
        normalized.append(section)
    return normalized


def _normalize_section(raw_section: dict[str, Any] | None, *, source_index: int) -> NormalizedPresentationSection:
    if not isinstance(raw_section, dict):
        return NormalizedPresentationSection(
            source_index=source_index,
            quality=MISSING_QUALITY,
            reason=REASON_MISSING_EXTRACTION,
        )

    title = _clean_text_field(raw_section.get("title", ""))
    body_raw = raw_section.get("body_text") or raw_section.get("paragraph") or raw_section.get("body_html") or raw_section.get("body") or ""
    body_text = _clean_body_text(body_raw)
    image_url = normalize_whitespace(raw_section.get("image_url") or raw_section.get("resolved_image_url") or "")
    metrics = _build_metrics(title=title, body_text=body_text, image_url=image_url)

    quality, reason = _classify_section(title=title, body_text=body_text, image_url=image_url, metrics=metrics)
    return NormalizedPresentationSection(
        source_index=source_index,
        title=title,
        body_text=body_text,
        image_url=image_url,
        quality=quality,
        reason=reason,
        metrics=metrics,
    )


def _build_metrics(*, title: str, body_text: str, image_url: str) -> NormalizedPresentationSectionMetrics:
    word_tokens = [
        token
        for token in WORD_RE.findall(body_text)
        if token and any(ALPHABETIC_RE.match(ch) for ch in token)
    ]
    alphabetic_char_count = sum(1 for ch in body_text if ALPHABETIC_RE.match(ch))
    char_count = len(body_text)
    alpha_ratio = (alphabetic_char_count / char_count) if char_count else 0.0
    normalized_tokens = [normalize_for_match(token) for token in word_tokens]
    normalized_tokens = [token for token in normalized_tokens if token]
    unique_word_ratio = (len(set(normalized_tokens)) / len(normalized_tokens)) if normalized_tokens else 0.0
    return NormalizedPresentationSectionMetrics(
        word_count=len(word_tokens),
        alphabetic_char_count=alphabetic_char_count,
        char_count=char_count,
        alpha_ratio=round(alpha_ratio, 4),
        unique_word_ratio=round(unique_word_ratio, 4),
        has_title=bool(title),
        has_image=bool(image_url),
    )


def _classify_section(
    *,
    title: str,
    body_text: str,
    image_url: str,
    metrics: NormalizedPresentationSectionMetrics,
) -> tuple[str, str]:
    if not body_text:
        return MISSING_QUALITY, REASON_MISSING_IMAGE_ONLY if image_url else REASON_MISSING_EMPTY_AFTER_CLEAN
    if metrics.word_count < MISSING_MIN_WORDS or metrics.alphabetic_char_count < MISSING_MIN_ALPHA_CHARS:
        return MISSING_QUALITY, REASON_MISSING_IMAGE_ONLY if image_url and metrics.alphabetic_char_count == 0 else REASON_MISSING_EMPTY_AFTER_CLEAN
    if _looks_noisy(body_text, metrics):
        return WEAK_QUALITY, REASON_WEAK_NOISY_BODY
    if not title:
        return WEAK_QUALITY, REASON_WEAK_MISSING_TITLE
    if metrics.word_count >= USABLE_MIN_WORDS and metrics.alphabetic_char_count >= USABLE_MIN_ALPHA_CHARS:
        return USABLE_QUALITY, REASON_USABLE_CLEAN
    return WEAK_QUALITY, REASON_WEAK_SHORT_BODY


def _clean_text_field(value: Any) -> str:
    return _extract_visible_text(value, strip_urls=True)


def _clean_body_text(value: Any) -> str:
    return _extract_visible_text(value, strip_urls=True)


def _extract_visible_text(value: Any, *, strip_urls: bool) -> str:
    raw_text = str(value or "")
    if "<" in raw_text and ">" in raw_text:
        soup = BeautifulSoup(raw_text, "lxml")
        for tag in soup.find_all(NOISY_TAGS):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
    else:
        text = raw_text
    if strip_urls:
        text = URL_RE.sub(" ", text)
    return normalize_whitespace(text)


def _looks_noisy(body_text: str, metrics: NormalizedPresentationSectionMetrics) -> bool:
    if not body_text:
        return False
    if metrics.alpha_ratio < 0.55:
        return True
    if metrics.word_count >= MISSING_MIN_WORDS and metrics.unique_word_ratio < 0.45:
        return True
    if REPEATED_WORD_RE.search(body_text):
        return True
    return False
