from __future__ import annotations

from typing import Any, Mapping

from .models import JobRecord, JobType

RETRY_MODE_FROM_PREPARED_ARTIFACTS = "from_prepared_artifacts"
RETRY_SOURCE_JOB_ID_KEY = "retry_source_job_id"
RETRY_MODE_KEY = "retry_mode"
SKIP_PREPARE_KEY = "skip_prepare"


def is_full_pipeline_retry_from_artifacts(payload: Mapping[str, Any] | None) -> bool:
    if payload is None:
        return False
    return (
        payload.get(SKIP_PREPARE_KEY) is True
        or payload.get(RETRY_MODE_KEY) == RETRY_MODE_FROM_PREPARED_ARTIFACTS
    )


def build_retry_from_artifacts_payload(record: JobRecord) -> dict[str, Any]:
    if record.job_type != JobType.FULL_PIPELINE:
        raise ValueError(
            "Retry from prepared artifacts is supported only for full_pipeline jobs."
        )
    payload = dict(record.payload)
    _validate_full_pipeline_payload(payload, operation="retry")
    payload[RETRY_SOURCE_JOB_ID_KEY] = record.job_id
    payload[RETRY_MODE_KEY] = RETRY_MODE_FROM_PREPARED_ARTIFACTS
    payload[SKIP_PREPARE_KEY] = True
    return payload


def build_start_from_scratch_payload(record: JobRecord) -> dict[str, Any]:
    if record.job_type != JobType.FULL_PIPELINE:
        raise ValueError("Start from scratch is supported only for full_pipeline jobs.")
    payload = dict(record.payload)
    payload.pop(RETRY_SOURCE_JOB_ID_KEY, None)
    payload.pop(RETRY_MODE_KEY, None)
    payload.pop(SKIP_PREPARE_KEY, None)
    _validate_full_pipeline_payload(payload, operation="start")
    return payload


def _validate_full_pipeline_payload(
    payload: Mapping[str, Any], *, operation: str
) -> None:
    missing = [
        key
        for key in ("model", "source_url")
        if not str(payload.get(key, "") or "").strip()
    ]
    if missing:
        raise ValueError(
            f"Full pipeline job payload is missing {', '.join(missing)}; cannot {operation} job."
        )
