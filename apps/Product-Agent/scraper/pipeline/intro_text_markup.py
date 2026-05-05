from __future__ import annotations

import re
from html import escape
from typing import Any

from .normalize import normalize_whitespace

INTRO_TEXT_EMPHASIS_INVALID = "llm_intro_text_emphasis_invalid"
INTRO_TEXT_EMPHASIS_MISSING = "llm_intro_text_emphasis_missing"
INTRO_TEXT_EMPHASIS_OVERUSED = "llm_intro_text_emphasis_overused"
MAX_STRONG_SPANS = 8
MAX_EMPHASIZED_WORD_RATIO = 0.35

_TAG_RE = re.compile(r"<[^>]+>")
_STRONG_OPEN_RE = re.compile(r"<strong>", re.IGNORECASE)
_STRONG_CLOSE_RE = re.compile(r"</strong>", re.IGNORECASE)
_FORBIDDEN_MARKDOWN_RES = [
    re.compile(r"\*\*[^*]+\*\*"),
    re.compile(r"!\[[^\]]*\]\([^)]+\)"),
    re.compile(r"\[[^\]]+\]\([^)]+\)"),
    re.compile(r"(^|\n)\s{0,3}#{1,6}\s+"),
    re.compile(r"(^|\n)\s*(?:[-*+]\s+|\d+[.)]\s+)"),
]


def strip_intro_text_markup(value: str) -> str:
    text = str(value or "")
    text = _STRONG_OPEN_RE.sub(" ", text)
    text = _STRONG_CLOSE_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    return normalize_whitespace(text)


def normalize_intro_text_markup(value: str) -> tuple[str, list[str]]:
    raw = str(value or "")
    errors: list[str] = []
    if any(pattern.search(raw) for pattern in _FORBIDDEN_MARKDOWN_RES):
        errors.append(INTRO_TEXT_EMPHASIS_INVALID)

    parts = _TAG_RE.split(raw)
    tags = _TAG_RE.findall(raw)
    untagged = _TAG_RE.sub("", raw)
    if "<" in untagged or ">" in untagged:
        errors.append(INTRO_TEXT_EMPHASIS_INVALID)

    out: list[str] = []
    strong_text_parts: list[str] = []
    in_strong = False
    strong_spans: list[str] = []
    unsupported_html = False

    for index, text_part in enumerate(parts):
        if text_part:
            out.append(text_part)
            if in_strong:
                strong_text_parts.append(text_part)
        if index >= len(tags):
            continue
        tag = tags[index]
        if tag.lower() == "<strong>":
            if in_strong:
                errors.append(INTRO_TEXT_EMPHASIS_INVALID)
                continue
            in_strong = True
            strong_text_parts = []
            out.append("<strong>")
        elif tag.lower() == "</strong>":
            if not in_strong:
                errors.append(INTRO_TEXT_EMPHASIS_INVALID)
                continue
            emphasized_text = normalize_whitespace(" ".join(strong_text_parts))
            if not emphasized_text:
                errors.append(INTRO_TEXT_EMPHASIS_INVALID)
            strong_spans.append(emphasized_text)
            in_strong = False
            strong_text_parts = []
            out.append("</strong>")
        else:
            unsupported_html = True

    if in_strong:
        errors.append(INTRO_TEXT_EMPHASIS_INVALID)
    if unsupported_html:
        errors.append(INTRO_TEXT_EMPHASIS_INVALID)

    visible_word_count = count_intro_text_words(raw)
    emphasized_word_count = sum(count_intro_text_words(item) for item in strong_spans)
    ratio = emphasized_word_count / visible_word_count if visible_word_count else 0.0
    if len(strong_spans) > MAX_STRONG_SPANS or ratio > MAX_EMPHASIZED_WORD_RATIO:
        errors.append(INTRO_TEXT_EMPHASIS_OVERUSED)

    if errors:
        normalized = strip_intro_text_markup(raw)
    else:
        normalized = normalize_whitespace("".join(out))
    return normalized, _unique_codes(errors)


def count_intro_text_words(value: str) -> int:
    text = strip_intro_text_markup(value)
    return len([token for token in text.split(" ") if token])


def summarize_intro_text_emphasis(value: str) -> dict[str, Any]:
    normalized, errors = normalize_intro_text_markup(value)
    strong_spans = _extract_valid_strong_spans(normalized) if not errors else []
    visible_word_count = count_intro_text_words(value)
    emphasized_word_count = sum(count_intro_text_words(item) for item in strong_spans)
    ratio = emphasized_word_count / visible_word_count if visible_word_count else 0.0
    warning_codes = list(errors)
    if not strong_spans and INTRO_TEXT_EMPHASIS_INVALID not in warning_codes:
        warning_codes.append(INTRO_TEXT_EMPHASIS_MISSING)
    return {
        "strong_span_count": len(strong_spans),
        "emphasized_word_count": emphasized_word_count,
        "visible_word_count": visible_word_count,
        "emphasized_word_ratio": ratio,
        "emphasis_warning_codes": _unique_codes(warning_codes),
    }


def render_intro_text_markup_html(value: str) -> tuple[str, list[str]]:
    normalized, errors = normalize_intro_text_markup(value)
    if errors:
        return escape(strip_intro_text_markup(value)), errors
    out: list[str] = []
    parts = _TAG_RE.split(normalized)
    tags = _TAG_RE.findall(normalized)
    for index, text_part in enumerate(parts):
        if text_part:
            out.append(escape(text_part))
        if index < len(tags):
            tag = tags[index].lower()
            if tag in {"<strong>", "</strong>"}:
                out.append(tag)
    return "".join(out), []


def _extract_valid_strong_spans(value: str) -> list[str]:
    spans: list[str] = []
    in_strong = False
    strong_text_parts: list[str] = []
    parts = _TAG_RE.split(value)
    tags = _TAG_RE.findall(value)
    for index, text_part in enumerate(parts):
        if text_part and in_strong:
            strong_text_parts.append(text_part)
        if index >= len(tags):
            continue
        tag = tags[index].lower()
        if tag == "<strong>":
            in_strong = True
            strong_text_parts = []
        elif tag == "</strong>" and in_strong:
            spans.append(normalize_whitespace(" ".join(strong_text_parts)))
            in_strong = False
            strong_text_parts = []
    return [span for span in spans if span]


def _unique_codes(codes: list[str]) -> list[str]:
    out: list[str] = []
    for code in codes:
        if code not in out:
            out.append(code)
    return out
