from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class JobType(str, Enum):
    PREPARE = "prepare"
    RENDER = "render"
    PUBLISH = "publish"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    KILLED = "killed"


TERMINAL_JOB_STATUSES = frozenset(
    {
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
        JobStatus.KILLED,
    }
)
STOPPABLE_JOB_STATUSES = frozenset(
    {
        JobStatus.QUEUED,
        JobStatus.RUNNING,
    }
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def coerce_job_type(value: JobType | str) -> JobType:
    return value if isinstance(value, JobType) else JobType(str(value))


def coerce_job_status(value: JobStatus | str) -> JobStatus:
    return value if isinstance(value, JobStatus) else JobStatus(str(value))


def is_terminal_job_status(status: JobStatus | str) -> bool:
    return coerce_job_status(status) in TERMINAL_JOB_STATUSES


def can_stop_job_status(status: JobStatus | str) -> bool:
    return coerce_job_status(status) in STOPPABLE_JOB_STATUSES


@dataclass(slots=True)
class JobRecord:
    job_id: str
    job_type: JobType
    status: JobStatus
    model: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    started_at: str | None = None
    finished_at: str | None = None
    message: str | None = None
    error: str | None = None
    error_code: str | None = None
    log_path: str | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
    stop_requested_at: str | None = None
    stop_reason: str | None = None
    parent_process_id: int | None = None
    process_id: int | None = None
    process_group_id: int | None = None
    command: list[str] = field(default_factory=list)
    exit_code: int | None = None
    termination_mode: str | None = None
    terminate_sent_at: str | None = None
    kill_sent_at: str | None = None
    killed_at: str | None = None
    killed_reason: str | None = None
    stdout_log_path: str | None = None
    stderr_log_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type.value,
            "status": self.status.value,
            "model": self.model,
            "payload": self.payload,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "message": self.message,
            "error": self.error,
            "error_code": self.error_code,
            "log_path": self.log_path,
            "artifacts": self.artifacts,
            "stop_requested_at": self.stop_requested_at,
            "stop_reason": self.stop_reason,
            "parent_process_id": self.parent_process_id,
            "process_id": self.process_id,
            "process_group_id": self.process_group_id,
            "command": self.command,
            "exit_code": self.exit_code,
            "termination_mode": self.termination_mode,
            "terminate_sent_at": self.terminate_sent_at,
            "kill_sent_at": self.kill_sent_at,
            "killed_at": self.killed_at,
            "killed_reason": self.killed_reason,
            "stdout_log_path": self.stdout_log_path,
            "stderr_log_path": self.stderr_log_path,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> JobRecord:
        job_payload = payload.get("payload", {})
        if not isinstance(job_payload, dict):
            job_payload = {}
        artifacts = payload.get("artifacts", {})
        if not isinstance(artifacts, dict):
            artifacts = {}
        command = payload.get("command", [])
        if not isinstance(command, list):
            command = []
        return cls(
            job_id=str(payload["job_id"]),
            job_type=coerce_job_type(payload["job_type"]),
            status=coerce_job_status(payload["status"]),
            model=str(payload.get("model", "")),
            payload=dict(job_payload),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
            started_at=_optional_str(payload.get("started_at")),
            finished_at=_optional_str(payload.get("finished_at")),
            message=_optional_str(payload.get("message")),
            error=_optional_str(payload.get("error")),
            error_code=_optional_str(payload.get("error_code")),
            log_path=_optional_str(payload.get("log_path")),
            artifacts={str(key): str(value) for key, value in artifacts.items()},
            stop_requested_at=_optional_str(payload.get("stop_requested_at")),
            stop_reason=_optional_str(payload.get("stop_reason")),
            parent_process_id=_optional_int(payload.get("parent_process_id")),
            process_id=_optional_int(payload.get("process_id")),
            process_group_id=_optional_int(payload.get("process_group_id")),
            command=[str(part) for part in command],
            exit_code=_optional_int(payload.get("exit_code")),
            termination_mode=_optional_str(payload.get("termination_mode")),
            terminate_sent_at=_optional_str(payload.get("terminate_sent_at")),
            kill_sent_at=_optional_str(payload.get("kill_sent_at")),
            killed_at=_optional_str(payload.get("killed_at")),
            killed_reason=_optional_str(payload.get("killed_reason")),
            stdout_log_path=_optional_str(payload.get("stdout_log_path")),
            stderr_log_path=_optional_str(payload.get("stderr_log_path")),
        )


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
