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
    job_type: str = ""
    model: str = ""
    message: str | None = None
    error: str | None = None
    error_code: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


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
        return _job_from_mapping(data)

    def get_job(self, job_id: str) -> ProductFactoryJob:
        url = f"{self._base_url}/api/jobs/{job_id}"
        try:
            response = httpx.get(url, timeout=self._timeout)
        except httpx.RequestError as exc:
            raise ProductFactoryClientError("Product Factory API is unavailable; job status could not be fetched.") from exc
        if response.status_code == 404:
            raise ProductFactoryClientError(f"Product Factory job {job_id} was not found.")
        if response.status_code >= 400:
            raise ProductFactoryClientError(_product_factory_status_error_message(response))

        try:
            data = response.json()
        except ValueError as exc:
            raise ProductFactoryClientError("Product Factory API returned an invalid job status response.") from exc
        if not isinstance(data, dict) or not data.get("job_id"):
            raise ProductFactoryClientError("Product Factory API returned an invalid job status response.")
        return _job_from_mapping(data)

    def list_jobs_by_model(self, model: str) -> list[ProductFactoryJob]:
        url = f"{self._base_url}/api/jobs/by-model/{model}"
        try:
            response = httpx.get(url, timeout=self._timeout)
        except httpx.RequestError as exc:
            raise ProductFactoryClientError("Product Factory API is unavailable; jobs by model could not be fetched.") from exc
        if response.status_code == 404:
            raise ProductFactoryClientError(f"Product Factory jobs for model {model} were not found.")
        if response.status_code >= 400:
            raise ProductFactoryClientError(_product_factory_status_error_message(response))

        try:
            data = response.json()
        except ValueError as exc:
            raise ProductFactoryClientError("Product Factory API returned an invalid jobs-by-model response.") from exc
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
            raise ProductFactoryClientError("Product Factory API returned an invalid jobs-by-model response.")
        return [_job_from_mapping(item) for item in data["jobs"] if isinstance(item, dict) and item.get("job_id")]


class TelegramDeliveryError(RuntimeError):
    pass


class TelegramBotClient:
    def __init__(self, bot_token: str, *, timeout: float = 10.0) -> None:
        self._bot_token = bot_token
        self._timeout = timeout

    def send_message(self, chat_id: str, text: str, *, reply_markup: dict[str, Any] | None = None) -> None:
        if not self._bot_token:
            raise TelegramDeliveryError("Telegram bot token is not configured.")
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        try:
            response = httpx.post(
                f"https://api.telegram.org/bot{self._bot_token}/sendMessage",
                json=payload,
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


def _product_factory_status_error_message(response: httpx.Response) -> str:
    detail = ""
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        raw_detail = payload.get("detail")
        if isinstance(raw_detail, str):
            detail = raw_detail.strip()
    if response.status_code >= 500:
        return "Product Factory API is unavailable; job status could not be fetched."
    if detail:
        return f"Product Factory API rejected the status request: {detail}"
    return f"Product Factory API rejected the status request with HTTP {response.status_code}."


def _job_from_mapping(data: dict[str, Any]) -> ProductFactoryJob:
    return ProductFactoryJob(
        job_id=str(data["job_id"]),
        status=str(data.get("status") or ""),
        raw=data,
        job_type=str(data.get("job_type") or ""),
        model=str(data.get("model") or ""),
        message=_optional_text(data.get("message")),
        error=_optional_text(data.get("error")),
        error_code=_optional_text(data.get("error_code")),
        created_at=_optional_text(data.get("created_at")),
        updated_at=_optional_text(data.get("updated_at")),
        started_at=_optional_text(data.get("started_at")),
        finished_at=_optional_text(data.get("finished_at")),
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
