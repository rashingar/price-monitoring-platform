from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

ECOMMERCE_API_BASE_URL_ENV = "ECOMMERCE_API_BASE_URL"


@dataclass(frozen=True)
class SourceCaptureSyncResult:
    status: str
    message: str
    payload: dict[str, Any] | None = None


def sync_initial_source_capture(model: str, source_url: str) -> SourceCaptureSyncResult:
    base_url = str(os.environ.get(ECOMMERCE_API_BASE_URL_ENV) or "").strip().rstrip("/")
    if not base_url:
        return SourceCaptureSyncResult(
            status="skipped", message="ECOMMERCE_API_BASE_URL is not configured."
        )
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.post(
                f"{base_url}/api/products/from-source",
                json={"model": model, "source_urls": [source_url], "capture": True},
            )
        if response.status_code >= 400:
            return SourceCaptureSyncResult(
                status="failed",
                message=f"Ecommerce source capture returned HTTP {response.status_code}.",
                payload=_json_payload(response),
            )
        return SourceCaptureSyncResult(
            status="submitted",
            message="Initial source capture submitted.",
            payload=_json_payload(response),
        )
    except Exception as exc:
        return SourceCaptureSyncResult(
            status="failed", message=str(exc) or exc.__class__.__name__
        )


def _json_payload(response: httpx.Response) -> dict[str, Any] | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None
