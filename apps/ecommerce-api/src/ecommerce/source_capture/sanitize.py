from __future__ import annotations

import hashlib
from typing import Any


SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-csrf-token",
    "x-xsrf-token",
    "csrf-token",
    "x-requested-with",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
}
SENSITIVE_KEY_MARKERS = ("token", "cookie", "session", "csrf", "authorization", "password", "fingerprint")


def content_hash(text: str | bytes | None) -> str | None:
    if text is None:
        return None
    payload = text if isinstance(text, bytes) else text.encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()


def sanitize_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    clean: dict[str, str] = {}
    for key, value in (headers or {}).items():
        name = str(key or "").strip()
        if not name:
            continue
        if name.lower() in SENSITIVE_HEADER_NAMES:
            continue
        clean[name] = str(value)
    return clean


def sanitize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): sanitize_json(item)
            for key, item in value.items()
            if not _is_sensitive_key(str(key))
        }
    if isinstance(value, list):
        return [sanitize_json(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered = key.strip().lower()
    return any(marker in lowered for marker in SENSITIVE_KEY_MARKERS)
