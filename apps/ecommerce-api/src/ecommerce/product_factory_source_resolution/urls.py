"""Product URL filtering and normalization."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from ecommerce.product_factory_source_resolution.config import PreferredSourceConfig, SourceResolutionConfig


def classify_supported_product_url(url: str, config: SourceResolutionConfig) -> tuple[PreferredSourceConfig, str] | None:
    source = config.classify_url(url)
    if source is None:
        return None
    normalized = normalized_product_url(url, source)
    if not normalized:
        return None
    return source, normalized


def normalized_product_url(url: str, source: PreferredSourceConfig) -> str:
    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path or "/"
    normalized = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"
    if not looks_like_product_path(path):
        return ""
    if not matches_product_pattern(normalized, path, source.product_url_patterns):
        return ""
    return normalized


def looks_like_product_path(path: str) -> bool:
    normalized = path.strip().casefold()
    if normalized in {"", "/"}:
        return False
    blocked = (
        "/search",
        "/category",
        "/categories",
        "/cat/",
        "/cart",
        "/checkout",
        "/account",
        "/login",
        "/blog",
        "/compare",
        "/wishlist",
    )
    return not any(item in normalized for item in blocked)


def matches_product_pattern(url: str, path: str, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if pattern == "/":
            return True
        try:
            if re.search(pattern, url, flags=re.IGNORECASE) or re.search(pattern, path, flags=re.IGNORECASE):
                return True
        except re.error:
            if pattern.casefold() in path.casefold() or pattern.casefold() in url.casefold():
                return True
    return False
