"""Utilities for DB-backed product source URLs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ecommerce.source_capture.egress_policy import (
    EgressPolicyError,
    EgressTimeoutConfig,
    safe_get,
)


class SourceUrlValidationError(ValueError):
    """Raised when a source URL has an unsupported or malformed shape."""


KNOWN_SOURCE_DOMAINS = {
    "electronet.gr": "electronet",
    "www.electronet.gr": "electronet",
    "skroutz.gr": "skroutz",
    "www.skroutz.gr": "skroutz",
    "bestprice.gr": "bestprice",
    "www.bestprice.gr": "bestprice",
    "public.gr": "public",
    "www.public.gr": "public",
    "kotsovolos.gr": "kotsovolos",
    "www.kotsovolos.gr": "kotsovolos",
    "plaisio.gr": "plaisio",
    "www.plaisio.gr": "plaisio",
}
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


@dataclass(frozen=True)
class SourceUrlValidationResult:
    status: Literal["success", "failed", "inconclusive"]
    message: str
    http_status_code: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "message": self.message,
            "http_status_code": self.http_status_code,
        }


def normalize_source_url(url: str) -> str:
    text = _trim_url(url)
    parsed = _parse_supported_url(text)
    hostname = str(parsed.hostname or "").lower()
    netloc = hostname
    try:
        port = parsed.port
    except ValueError as exc:
        raise SourceUrlValidationError("Source URL has an invalid port.") from exc
    if port is not None:
        netloc = f"{netloc}:{port}"
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query or "", keep_blank_values=True)
            if key.strip().lower() not in TRACKING_PARAMS
        ],
        doseq=True,
    )
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "", query, ""))


def extract_source_domain(url: str) -> str:
    normalized = normalize_source_url(url)
    parsed = urlsplit(normalized)
    host = str(parsed.hostname or "").strip().lower()
    if not host:
        raise SourceUrlValidationError("Source URL must include a host.")
    return host


def infer_source_name(domain: str) -> str:
    return KNOWN_SOURCE_DOMAINS.get(str(domain or "").strip().lower(), "unknown")


def validate_source_url_shape(url: str) -> None:
    normalize_source_url(url)


def validate_source_url_reachability(
    url: str, *, timeout_seconds: float = 5.0
) -> SourceUrlValidationResult:
    try:
        normalized = normalize_source_url(url)
    except SourceUrlValidationError as exc:
        return SourceUrlValidationResult(status="failed", message=str(exc))

    try:
        response = safe_get(
            normalized,
            timeout=EgressTimeoutConfig(
                connect=min(timeout_seconds, 5.0),
                read=timeout_seconds,
                total=timeout_seconds,
            ),
            max_response_bytes=256_000,
        )
    except EgressPolicyError as exc:
        if exc.code in {"invalid_url", "unsupported_scheme"}:
            return SourceUrlValidationResult(status="failed", message=exc.message)
        if exc.code == "timeout":
            return SourceUrlValidationResult(
                status="inconclusive", message="URL validation timed out."
            )
        if exc.code == "blocked_private_host":
            return SourceUrlValidationResult(
                status="inconclusive",
                message="URL host is not eligible for reachability validation.",
            )
        if exc.code == "response_too_large":
            return SourceUrlValidationResult(
                status="inconclusive", message="URL validation response was too large."
            )
        if exc.code == "redirect_blocked":
            return SourceUrlValidationResult(
                status="inconclusive",
                message="URL redirect target is not eligible for reachability validation.",
            )
        return SourceUrlValidationResult(
            status="inconclusive", message=_short_message(exc.message)
        )

    status_code = response.status_code
    if 200 <= status_code < 400:
        return SourceUrlValidationResult(
            status="success", message="URL is reachable.", http_status_code=status_code
        )
    if status_code in {400, 401, 403, 404, 410}:
        return SourceUrlValidationResult(
            status="failed",
            message=f"URL returned HTTP {status_code}.",
            http_status_code=status_code,
        )
    return SourceUrlValidationResult(
        status="inconclusive",
        message=f"URL returned HTTP {status_code}.",
        http_status_code=status_code,
    )


def _trim_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        raise SourceUrlValidationError("Source URL is required.")
    return text


def _parse_supported_url(url: str):
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise SourceUrlValidationError("Source URL is malformed.") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise SourceUrlValidationError(
            "Source URL must start with http:// or https://."
        )
    if not parsed.hostname:
        raise SourceUrlValidationError("Source URL must include a host.")
    if any(character.isspace() for character in parsed.hostname):
        raise SourceUrlValidationError("Source URL host is malformed.")
    return parsed


def _short_message(message: str, *, limit: int = 240) -> str:
    single_line = " ".join(message.split())
    if len(single_line) <= limit:
        return single_line
    return f"{single_line[: limit - 3]}..."
