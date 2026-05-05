from __future__ import annotations

from urllib.parse import urlsplit

from ecommerce.source_capture.vendor_registry import VENDOR_SLUG_BY_DOMAIN


def detect_vendor_slug(url: str) -> str | None:
    host = str(urlsplit(str(url or "").strip()).hostname or "").lower()
    return VENDOR_SLUG_BY_DOMAIN.get(host)
