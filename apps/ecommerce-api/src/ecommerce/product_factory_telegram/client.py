"""Small clients used by Telegram Product Factory intake."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ProductFactoryJob:
    job_id: str
    status: str
    raw: dict[str, Any]


class ProductFactoryClientError(RuntimeError):
    pass


class ProductFactoryClient:
    def __init__(self, base_url: str, *, timeout: float = 20.0) -> None:
        self._base_url = str(base_url or "").rstrip("/")
        self._timeout = timeout

    def start_full_pipeline(self, payload: dict[str, Any]) -> ProductFactoryJob:
        url = f"{self._base_url}/api/jobs/full-pipeline"
        try:
            response = httpx.post(url, json=payload, timeout=self._timeout)
        except httpx.RequestError as exc:
            raise ProductFactoryClientError("Product Factory API is unavailable; no job was started.") from exc

        if response.status_code >= 400:
            raise ProductFactoryClientError(_product_factory_error_message(response))

        try:
            data = response.json()
        except ValueError as exc:
            raise ProductFactoryClientError("Product Factory API returned an invalid response; no job was started.") from exc
        if not isinstance(data, dict) or not data.get("job_id"):
            raise ProductFactoryClientError("Product Factory API response did not include a job_id; no job was started.")
        return ProductFactoryJob(
            job_id=str(data["job_id"]),
            status=str(data.get("status") or ""),
            raw=data,
        )


class TelegramDeliveryError(RuntimeError):
    pass


class TelegramBotClient:
    def __init__(self, bot_token: str, *, timeout: float = 10.0) -> None:
        self._bot_token = bot_token
        self._timeout = timeout

    def send_message(self, chat_id: str, text: str) -> None:
        if not self._bot_token:
            raise TelegramDeliveryError("Telegram bot token is not configured.")
        try:
            response = httpx.post(
                f"https://api.telegram.org/bot{self._bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=self._timeout,
            )
        except httpx.RequestError as exc:
            raise TelegramDeliveryError("Telegram message delivery failed.") from exc
        if response.status_code >= 400:
            raise TelegramDeliveryError("Telegram message delivery failed.")


def _product_factory_error_message(response: httpx.Response) -> str:
    detail = ""
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        raw_detail = payload.get("detail")
        if isinstance(raw_detail, str):
            detail = raw_detail.strip()
        elif raw_detail:
            detail = "Product Factory API rejected the request."
    if response.status_code >= 500:
        return "Product Factory API is unavailable; no job was started."
    if detail:
        return f"Product Factory API rejected the request: {detail}"
    return f"Product Factory API rejected the request with HTTP {response.status_code}; no job was started."
