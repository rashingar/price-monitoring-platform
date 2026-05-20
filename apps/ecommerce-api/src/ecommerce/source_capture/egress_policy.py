from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from typing import Literal
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from ecommerce.source_capture.vendor_registry import VENDOR_SLUG_BY_DOMAIN

EgressErrorCode = Literal[
    "invalid_url",
    "unsupported_scheme",
    "blocked_private_host",
    "unknown_vendor",
    "redirect_blocked",
    "timeout",
    "http_error",
    "network_error",
    "response_too_large",
]

DEFAULT_MAX_RESPONSE_BYTES = 2_000_000
DEFAULT_USER_AGENT = "EcommerceSourceCapture/1.0"


@dataclass(frozen=True)
class EgressTimeoutConfig:
    connect: float = 5.0
    read: float = 20.0
    total: float = 30.0


@dataclass(frozen=True)
class EgressPolicyDecision:
    url: str
    host: str
    vendor_slug: str | None


@dataclass(frozen=True)
class SafeFetchResponse:
    url: str
    final_url: str
    status_code: int
    headers: dict[str, str]
    text: str
    content: bytes
    vendor_slug: str | None


class EgressPolicyError(ValueError):
    def __init__(self, code: EgressErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def validate_outbound_url(
    url: str,
    *,
    expected_vendor_slug: str | None = None,
    require_known_vendor: bool = False,
) -> EgressPolicyDecision:
    text = str(url or "").strip()
    if not text:
        raise EgressPolicyError("invalid_url", "URL is required.")
    try:
        parsed = urlsplit(text)
    except ValueError as exc:
        raise EgressPolicyError("invalid_url", "URL is malformed.") from exc

    scheme = parsed.scheme.lower()
    if not scheme:
        raise EgressPolicyError("invalid_url", "URL must include http:// or https://.")
    if scheme not in {"http", "https"}:
        raise EgressPolicyError(
            "unsupported_scheme", "URL must start with http:// or https://."
        )
    if not parsed.hostname:
        raise EgressPolicyError("invalid_url", "URL must include a host.")

    host = parsed.hostname.strip().lower()
    if any(character.isspace() for character in host):
        raise EgressPolicyError("invalid_url", "URL host is malformed.")
    if _is_private_or_reserved_host(host):
        raise EgressPolicyError(
            "blocked_private_host",
            "URL host is not eligible for outbound Ecommerce requests.",
        )

    vendor_slug = VENDOR_SLUG_BY_DOMAIN.get(host)
    if require_known_vendor and vendor_slug is None:
        raise EgressPolicyError(
            "unknown_vendor", "URL host is not registered for Ecommerce capture."
        )
    if expected_vendor_slug is not None and vendor_slug != expected_vendor_slug:
        raise EgressPolicyError(
            "unknown_vendor",
            f"URL host is not registered for {expected_vendor_slug} capture.",
        )

    return EgressPolicyDecision(
        url=_normalized_url(parsed, host),
        host=host,
        vendor_slug=vendor_slug,
    )


def validate_redirect_target(
    initial: EgressPolicyDecision, final_url: str
) -> EgressPolicyDecision:
    try:
        final = validate_outbound_url(
            final_url, require_known_vendor=initial.vendor_slug is not None
        )
    except EgressPolicyError as exc:
        raise EgressPolicyError(
            "redirect_blocked", f"Redirect target blocked: {exc.message}"
        ) from exc
    if initial.vendor_slug is not None and final.vendor_slug != initial.vendor_slug:
        raise EgressPolicyError(
            "redirect_blocked", "Redirect target changed to a different vendor domain."
        )
    return final


def safe_get(
    url: str,
    *,
    expected_vendor_slug: str | None = None,
    require_known_vendor: bool = False,
    timeout: EgressTimeoutConfig | None = None,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    headers: dict[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
    raise_for_status: bool = False,
    max_redirects: int = 5,
) -> SafeFetchResponse:
    decision = validate_outbound_url(
        url,
        expected_vendor_slug=expected_vendor_slug,
        require_known_vendor=require_known_vendor,
    )
    timeout_config = timeout or EgressTimeoutConfig()
    request_headers = {"User-Agent": DEFAULT_USER_AGENT, **(headers or {})}
    httpx_timeout = httpx.Timeout(
        timeout_config.total,
        connect=timeout_config.connect,
        read=timeout_config.read,
        write=timeout_config.total,
        pool=timeout_config.total,
    )
    try:
        with httpx.Client(
            follow_redirects=False,
            timeout=httpx_timeout,
            headers=request_headers,
            transport=transport,
        ) as client:
            current = decision
            for _redirect_count in range(max_redirects + 1):
                with client.stream("GET", current.url) as response:
                    if _is_redirect(response.status_code):
                        location = response.headers.get("location")
                        if location:
                            redirect_url = urljoin(current.url, location)
                            current = validate_redirect_target(decision, redirect_url)
                            continue

                    final = validate_redirect_target(decision, str(response.url))
                    content = _read_bounded_response(
                        response, max_response_bytes=max_response_bytes
                    )
                    if raise_for_status and response.status_code >= 400:
                        raise EgressPolicyError(
                            "http_error", f"URL returned HTTP {response.status_code}."
                        )
                    return SafeFetchResponse(
                        url=decision.url,
                        final_url=final.url,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        text=_decode_content(content, response),
                        content=content,
                        vendor_slug=final.vendor_slug,
                    )
            raise EgressPolicyError(
                "redirect_blocked", "URL exceeded the maximum redirect limit."
            )
    except EgressPolicyError:
        raise
    except httpx.TimeoutException as exc:
        raise EgressPolicyError("timeout", "Outbound request timed out.") from exc
    except httpx.HTTPError as exc:
        message = str(exc).strip() or exc.__class__.__name__
        raise EgressPolicyError("network_error", _short_message(message)) from exc


def _read_bounded_response(
    response: httpx.Response, *, max_response_bytes: int
) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_response_bytes:
                raise EgressPolicyError(
                    "response_too_large",
                    "Response body is larger than the configured maximum.",
                )
        except ValueError:
            pass

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_response_bytes:
            raise EgressPolicyError(
                "response_too_large",
                "Response body is larger than the configured maximum.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _is_redirect(status_code: int) -> bool:
    return status_code in {301, 302, 303, 307, 308}


def _normalized_url(parsed, host: str) -> str:
    netloc = host
    try:
        port = parsed.port
    except ValueError as exc:
        raise EgressPolicyError("invalid_url", "URL has an invalid port.") from exc
    if port is not None:
        netloc = f"{netloc}:{port}"
    return urlunsplit(
        (parsed.scheme.lower(), netloc, parsed.path or "", parsed.query or "", "")
    )


def _is_private_or_reserved_host(host: str) -> bool:
    if (
        host in {"localhost", "localhost.localdomain"}
        or host.endswith(".localhost")
        or host.endswith(".local")
    ):
        return True
    try:
        address = ip_address(host)
    except ValueError:
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    )


def _decode_content(content: bytes, response: httpx.Response) -> str:
    encoding = response.encoding or "utf-8"
    return content.decode(encoding, errors="replace")


def _short_message(message: str, *, limit: int = 240) -> str:
    single_line = " ".join(message.split())
    if len(single_line) <= limit:
        return single_line
    return f"{single_line[: limit - 3]}..."
