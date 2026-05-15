"""Source URL Agent progress definitions and durable job reporter."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ecommerce.jobs.progress import JobProgressReporter, JobProgressStepDefinition

SOURCE_URL_AGENT_JOB_TYPE = "source_url_agent_run"
SOURCE_URL_AGENT_HEARTBEAT_INTERVAL_SECONDS = 30

SOURCE_URL_AGENT_PROGRESS_STEP_DEFINITIONS: tuple[JobProgressStepDefinition, ...] = (
    JobProgressStepDefinition("product_selection_started", "Product selection started"),
    JobProgressStepDefinition("product_selection_completed", "Product selection completed"),
    JobProgressStepDefinition("source_registry_loaded", "Source registry loaded"),
    JobProgressStepDefinition("discovery_started", "Discovery started"),
    JobProgressStepDefinition("product_source_started", "Product-source started"),
    JobProgressStepDefinition("product_source_completed", "Product-source completed"),
    JobProgressStepDefinition("candidate_scoring_started", "Candidate scoring started"),
    JobProgressStepDefinition("candidate_scoring_completed", "Candidate scoring completed"),
    JobProgressStepDefinition("high_confidence_apply_started", "High-confidence apply started"),
    JobProgressStepDefinition("high_confidence_apply_completed", "High-confidence apply completed"),
    JobProgressStepDefinition("artifact_writing_started", "Artifact writing started"),
    JobProgressStepDefinition("artifact_writing_completed", "Artifact writing completed"),
    JobProgressStepDefinition("candidate_persistence_started", "Candidate persistence started"),
    JobProgressStepDefinition("candidate_persistence_completed", "Candidate persistence completed"),
    JobProgressStepDefinition("run_completed", "Run completed"),
)
SOURCE_URL_AGENT_PROGRESS_STEP_IDS = tuple(definition.id for definition in SOURCE_URL_AGENT_PROGRESS_STEP_DEFINITIONS)
SOURCE_URL_AGENT_PROGRESS_STEP_LABELS = {
    definition.id: definition.label
    for definition in SOURCE_URL_AGENT_PROGRESS_STEP_DEFINITIONS
}


class SourceUrlAgentProgressReporter(JobProgressReporter):
    def __init__(
        self,
        job_id: str,
        *,
        heartbeat_interval_seconds: float = SOURCE_URL_AGENT_HEARTBEAT_INTERVAL_SECONDS,
        now: Callable[[], Any] | None = None,
    ) -> None:
        super().__init__(
            job_id,
            step_definitions=SOURCE_URL_AGENT_PROGRESS_STEP_DEFINITIONS,
            initial_step="product_selection_started",
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            details_sanitizer=sanitize_source_url_agent_progress_details,
            now=now,
            heartbeat_thread_name=f"source-url-agent-heartbeat-{job_id}",
        )


def sanitize_source_url_agent_progress_details(details: dict[str, Any] | None) -> dict[str, Any]:
    if not details:
        return {}
    sanitized: dict[str, Any] = {}
    for key, value in details.items():
        normalized_key = str(key)
        if _is_sensitive_key(normalized_key):
            continue
        sanitized_value = _sanitize_value(value)
        if sanitized_value is not None:
            sanitized[normalized_key] = sanitized_value
    return sanitized


def _sanitize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        text = _sanitize_text(value)
        return text[:1000]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        nested = sanitize_source_url_agent_progress_details(value)
        return nested if nested else None
    if isinstance(value, (list, tuple)):
        items = [_sanitize_value(item) for item in value[:25]]
        return [item for item in items if item is not None]
    return _sanitize_text(str(value))[:1000]


def _sanitize_text(value: str) -> str:
    text = value or ""
    if "://" in text:
        return _sanitize_url(text)
    return re.sub(
        r"(?i)\b(access_token|authorization|cookie|password|passwd|pwd|refresh_token|secret|token|user_token)=([^&\s]+)",
        lambda match: f"{match.group(1)}=[redacted]",
        text,
    )


def _sanitize_url(value: str) -> str:
    try:
        parsed = urlparse(value)
    except ValueError:
        return _sanitize_text(value.replace("://", ""))
    if not parsed.scheme or not parsed.netloc:
        return _sanitize_text(value.replace("://", ""))
    query_items = [
        (key, "[redacted]" if _is_sensitive_key(key) else _sanitize_text(item_value))
        for key, item_value in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunparse(parsed._replace(query=urlencode(query_items), fragment=""))


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().casefold().replace("-", "_")
    if normalized in {"html", "raw_html", "body", "body_text", "body_text_sample", "page_content", "headers"}:
        return True
    return any(part in normalized for part in ("authorization", "cookie", "password", "secret", "token"))
