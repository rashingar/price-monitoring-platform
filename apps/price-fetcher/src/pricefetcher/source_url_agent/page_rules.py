"""Generic product-page rejection rules for Source URL Agent Mode."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

from pricefetcher.utils.text import collapse_internal_spaces


REVIEW_TITLE_RE = re.compile(r"(\breview\b|Αξιολόγησε|Αξιολογήστε)", re.IGNORECASE)
BLOCKED_URL_WORD_RE = re.compile(r"(collection|promo|campaign|banner)", re.IGNORECASE)


def is_review_url(url: str) -> bool:
    path = unquote(urlsplit(str(url or "").strip()).path or "").rstrip("/")
    if not path:
        return False
    return path.casefold().endswith("/review") or path.casefold() == "review"


def url_rejection_reason(url: str) -> str:
    if is_review_url(url):
        return "url_ends_with_review"
    if BLOCKED_URL_WORD_RE.search(unquote(str(url or ""))):
        return "url_contains_non_product_marker"
    return ""


def review_page_rejection_reason(*, candidate_url: str = "", canonical_url: str = "", title: str = "") -> str:
    candidate_reason = url_rejection_reason(candidate_url)
    if candidate_reason:
        return f"candidate_{candidate_reason}"
    canonical_reason = url_rejection_reason(canonical_url)
    if canonical_reason:
        return f"canonical_{canonical_reason}"
    if REVIEW_TITLE_RE.search(collapse_internal_spaces(title)):
        return "title_contains_review_marker"
    return ""
