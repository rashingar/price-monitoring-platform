from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "msclkid",
}


def canonicalize_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        raise ValueError("Source URL is required.")
    parsed = urlsplit(text)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Source URL must start with http:// or https://.")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("Source URL must include a host.")
    netloc = host
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Source URL has an invalid port.") from exc
    if port is not None:
        netloc = f"{host}:{port}"
    path = _canonical_path(parsed.path or "")
    query = _canonical_query(parsed.query or "")
    return urlunsplit((scheme, netloc, path, query, ""))


def canonical_url_hash(url: str) -> str:
    return hashlib.sha256(canonicalize_url(url).encode("utf-8")).hexdigest()


def _canonical_path(path: str) -> str:
    if not path or path == "/":
        return ""
    return path.rstrip("/")


def _canonical_query(query: str) -> str:
    pairs = [
        (key, value)
        for key, value in parse_qsl(query, keep_blank_values=True)
        if key.strip().lower() not in TRACKING_PARAMS
    ]
    return urlencode(pairs, doseq=True)
