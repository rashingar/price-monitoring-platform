"""Append-only JSONL audit log for Telegram Product Factory intake."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

DEFAULT_AUDIT_LOG_PATH = "output/product_factory_telegram/audit.jsonl"

_LOGGER = logging.getLogger(__name__)
_AUDIT_FIELDS = (
    "event_id",
    "event_type",
    "created_at",
    "chat_id",
    "user_id",
    "model",
    "product_name",
    "bestprice_status",
    "skroutz_status",
    "boxnow",
    "selected_source",
    "selected_url",
    "selected_title",
    "confidence",
    "selection_method",
    "job_id",
    "status",
    "message",
    "metadata",
)


def append_event(
    *,
    path: str | Path | None = None,
    event_type: str,
    chat_id: str | None = None,
    user_id: str | None = None,
    model: str | None = None,
    product_name: str | None = None,
    bestprice_status: int | None = None,
    skroutz_status: int | None = None,
    boxnow: int | None = None,
    selected_source: str | None = None,
    selected_url: str | None = None,
    selected_title: str | None = None,
    confidence: int | str | None = None,
    selection_method: str | None = None,
    job_id: str | None = None,
    status: str | None = None,
    message: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event_id": uuid4().hex,
        "event_type": event_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "chat_id": chat_id,
        "user_id": user_id,
        "model": model,
        "product_name": product_name,
        "bestprice_status": bestprice_status,
        "skroutz_status": skroutz_status,
        "boxnow": boxnow,
        "selected_source": selected_source,
        "selected_url": selected_url,
        "selected_title": selected_title,
        "confidence": confidence,
        "selection_method": selection_method,
        "job_id": job_id,
        "status": status,
        "message": message,
    }
    if metadata is not None:
        event["metadata"] = dict(metadata)

    audit_path = Path(path or DEFAULT_AUDIT_LOG_PATH)
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    except (OSError, TypeError):
        _LOGGER.warning(
            "Failed to append Telegram Product Factory audit event.", exc_info=True
        )
    return event


def iter_events(path: str | Path | None = None) -> Iterator[dict[str, Any]]:
    audit_path = Path(path or DEFAULT_AUDIT_LOG_PATH)
    if not audit_path.exists():
        return
    try:
        with audit_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except ValueError:
                    _LOGGER.warning(
                        "Skipping malformed Telegram Product Factory audit JSONL line."
                    )
                    continue
                if isinstance(event, dict):
                    yield {
                        field: event[field] for field in _AUDIT_FIELDS if field in event
                    }
    except (OSError, UnicodeDecodeError):
        _LOGGER.warning(
            "Failed to read Telegram Product Factory audit log.", exc_info=True
        )
        return


def latest_enqueued_job_for_model(path: str | Path | None, model: str) -> str | None:
    latest_job_id: str | None = None
    for event in iter_events(path):
        if event.get("event_type") != "product_factory_enqueue_succeeded":
            continue
        if str(event.get("model") or "") != model:
            continue
        job_id = str(event.get("job_id") or "").strip()
        if job_id:
            latest_job_id = job_id
    return latest_job_id
