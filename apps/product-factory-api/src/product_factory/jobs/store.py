from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from ..repo_paths import REPO_ROOT
from .models import JobRecord, JobStatus, JobType, coerce_job_type, utc_now_iso

DEFAULT_JOBS_DIR = REPO_ROOT / "work" / "api" / "jobs"
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class JobStore:
    def __init__(self, jobs_dir: Path | str = DEFAULT_JOBS_DIR) -> None:
        self.jobs_dir = Path(jobs_dir)
        self._lock = RLock()

    def enqueue(
        self,
        job_type: JobType | str,
        payload: Mapping[str, Any],
        *,
        job_id: str | None = None,
    ) -> JobRecord:
        coerced_job_type = coerce_job_type(job_type)
        job_id = job_id or _default_job_id(coerced_job_type, payload)
        self._validate_job_id(job_id)
        now = utc_now_iso()
        record = JobRecord(
            job_id=job_id,
            job_type=coerced_job_type,
            status=JobStatus.QUEUED,
            model=str(payload.get("model", "")),
            payload=dict(payload),
            created_at=now,
            updated_at=now,
            log_path=str(self.log_path(job_id)),
        )
        with self._lock:
            self._ensure_jobs_dir()
            self._write_record(record)
            self.log_path(job_id).touch(exist_ok=True)
        return record

    def enqueue_full_pipeline_unless_active(
        self,
        payload: Mapping[str, Any],
        *,
        job_id: str | None = None,
    ) -> JobRecord:
        normalized = _normalized_model(str(payload.get("model", "")))
        with self._lock:
            if normalized:
                active = self._active_full_pipeline_for_model_locked(normalized)
                if active is not None:
                    raise ActiveFullPipelineJobConflict(active)
            return self.enqueue(JobType.FULL_PIPELINE, payload, job_id=job_id)

    def list_jobs(self) -> list[JobRecord]:
        with self._lock:
            if not self.jobs_dir.exists():
                return []
            records = [
                self._read_record_path(path) for path in self.jobs_dir.glob("*.json")
            ]
        return sorted(records, key=lambda record: (record.created_at, record.job_id))

    def list_jobs_for_model(self, model: str) -> list[JobRecord]:
        normalized = _normalized_model(model)
        if not normalized:
            return []
        return [
            record
            for record in self.list_jobs()
            if _normalized_model(record.model) == normalized
        ]

    def list_non_terminal_jobs(self) -> list[JobRecord]:
        return [
            record
            for record in self.list_jobs()
            if record.status not in {
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
                JobStatus.KILLED,
            }
        ]

    def get_job(self, job_id: str) -> JobRecord | None:
        self._validate_job_id(job_id)
        path = self.metadata_path(job_id)
        with self._lock:
            if not path.exists():
                return None
            return self._read_record_path(path)

    def mark_running(self, job_id: str, *, message: str | None = None) -> JobRecord:
        now = utc_now_iso()
        with self._lock:
            record = self._require_job(job_id)
            if record.status != JobStatus.QUEUED:
                return record
            record.status = JobStatus.RUNNING
            record.started_at = record.started_at or now
            record.updated_at = now
            record.message = message
            self._write_record(record)
            return record

    def mark_succeeded(
        self,
        job_id: str,
        *,
        message: str | None = None,
        error: str | None = None,
        error_code: str | None = None,
    ) -> JobRecord:
        now = utc_now_iso()
        with self._lock:
            record = self._require_job(job_id)
            if record.status in {
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
                JobStatus.KILLED,
            }:
                return record
            record.status = JobStatus.SUCCEEDED
            record.finished_at = now
            record.updated_at = now
            record.message = message
            record.error = error
            record.error_code = error_code
            self._write_record(record)
            return record

    def mark_failed(
        self,
        job_id: str,
        error: str,
        *,
        message: str | None = None,
        error_code: str | None = None,
    ) -> JobRecord:
        now = utc_now_iso()
        with self._lock:
            record = self._require_job(job_id)
            if record.status in {
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
                JobStatus.KILLED,
            }:
                return record
            record.status = JobStatus.FAILED
            record.finished_at = now
            record.updated_at = now
            record.message = message
            record.error = error
            record.error_code = error_code
            self._write_record(record)
            return record

    def mark_cancelled(
        self,
        job_id: str,
        *,
        reason: str | None = None,
        message: str | None = None,
        error_code: str | None = "JOB_STOPPED",
    ) -> JobRecord:
        now = utc_now_iso()
        stop_message = message or "Job stopped by operator."
        stop_error = reason or "Job stopped by operator."
        with self._lock:
            record = self._require_job(job_id)
            if record.status in {
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
                JobStatus.KILLED,
            }:
                return record
            record.status = JobStatus.CANCELLED
            record.finished_at = record.finished_at or now
            record.updated_at = now
            record.message = stop_message
            record.error = stop_error
            record.error_code = error_code
            record.stop_requested_at = now
            if reason is not None:
                record.stop_reason = reason
            self._write_record(record)
            return record

    def mark_killed(
        self,
        job_id: str,
        *,
        reason: str = "Process did not exit before terminate timeout.",
        message: str | None = None,
        error_code: str | None = "JOB_KILLED",
    ) -> JobRecord:
        now = utc_now_iso()
        with self._lock:
            record = self._require_job(job_id)
            if record.status in {
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
                JobStatus.KILLED,
            }:
                return record
            record.status = JobStatus.KILLED
            record.finished_at = record.finished_at or now
            record.updated_at = now
            record.message = message or "Job process was force killed."
            record.error = (
                record.error
                or "Job process was force killed after graceful termination timed out."
            )
            record.error_code = error_code
            record.kill_sent_at = record.kill_sent_at or now
            record.killed_at = record.killed_at or now
            record.killed_reason = reason
            record.termination_mode = "force_kill"
            self._write_record(record)
            return record

    def update_process_metadata(
        self,
        job_id: str,
        *,
        parent_process_id: int | None = None,
        process_id: int | None = None,
        process_group_id: int | None = None,
        command: list[str] | None = None,
        exit_code: int | None = None,
        termination_mode: str | None = None,
        terminate_sent_at: str | None = None,
        kill_sent_at: str | None = None,
        killed_at: str | None = None,
        killed_reason: str | None = None,
        stdout_log_path: str | None = None,
        stderr_log_path: str | None = None,
    ) -> JobRecord:
        with self._lock:
            record = self._require_job(job_id)
            if parent_process_id is not None:
                record.parent_process_id = parent_process_id
            if process_id is not None:
                record.process_id = process_id
            if process_group_id is not None:
                record.process_group_id = process_group_id
            if command is not None:
                record.command = list(command)
            if exit_code is not None:
                record.exit_code = exit_code
            if termination_mode is not None:
                record.termination_mode = termination_mode
            if terminate_sent_at is not None:
                record.terminate_sent_at = terminate_sent_at
            if kill_sent_at is not None:
                record.kill_sent_at = kill_sent_at
            if killed_at is not None:
                record.killed_at = killed_at
            if killed_reason is not None:
                record.killed_reason = killed_reason
            if stdout_log_path is not None:
                record.stdout_log_path = stdout_log_path
            if stderr_log_path is not None:
                record.stderr_log_path = stderr_log_path
            record.updated_at = utc_now_iso()
            self._write_record(record)
            return record

    def set_terminal_exit_metadata(
        self,
        job_id: str,
        *,
        exit_code: int,
        termination_mode: str,
    ) -> JobRecord:
        with self._lock:
            record = self._require_job(job_id)
            record.exit_code = exit_code
            record.termination_mode = termination_mode
            record.updated_at = utc_now_iso()
            self._write_record(record)
            return record

    def update_artifacts(
        self, job_id: str, artifacts: Mapping[str, object | None]
    ) -> JobRecord:
        with self._lock:
            record = self._require_job(job_id)
            record.artifacts = {
                str(name): str(path)
                for name, path in artifacts.items()
                if path is not None
            }
            record.updated_at = utc_now_iso()
            self._write_record(record)
            return record

    def append_log(self, job_id: str, line: str) -> None:
        self._validate_job_id(job_id)
        with self._lock:
            self._ensure_jobs_dir()
            with self.log_path(job_id).open("a", encoding="utf-8") as handle:
                handle.write(f"{line.rstrip()}\n")

    def read_logs(self, job_id: str) -> list[str]:
        self._validate_job_id(job_id)
        path = self.log_path(job_id)
        with self._lock:
            if not path.exists():
                return []
            return path.read_text(encoding="utf-8").splitlines()

    def metadata_path(self, job_id: str) -> Path:
        self._validate_job_id(job_id)
        return self.jobs_dir / f"{job_id}.json"

    def log_path(self, job_id: str) -> Path:
        self._validate_job_id(job_id)
        return self.jobs_dir / f"{job_id}.log"

    def _ensure_jobs_dir(self) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def _require_job(self, job_id: str) -> JobRecord:
        record = self.get_job(job_id)
        if record is None:
            raise KeyError(job_id)
        return record

    def _read_record_path(self, path: Path) -> JobRecord:
        return JobRecord.from_mapping(json.loads(path.read_text(encoding="utf-8")))

    def _write_record(self, record: JobRecord) -> None:
        path = self.metadata_path(record.job_id)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(path)

    def _active_full_pipeline_for_model_locked(
        self, normalized_model: str
    ) -> JobRecord | None:
        if not self.jobs_dir.exists():
            return None
        records = [
            self._read_record_path(path) for path in self.jobs_dir.glob("*.json")
        ]
        for record in sorted(records, key=lambda item: (item.created_at, item.job_id)):
            if (
                record.job_type == JobType.FULL_PIPELINE
                and record.status in {JobStatus.QUEUED, JobStatus.RUNNING}
                and _normalized_model(record.model) == normalized_model
            ):
                return record
        return None

    @staticmethod
    def _validate_job_id(job_id: str) -> None:
        if not job_id or not _JOB_ID_RE.fullmatch(job_id):
            raise ValueError(f"Invalid job id: {job_id!r}")


def _default_job_id(job_type: JobType, payload: Mapping[str, Any]) -> str:
    model_part = _job_id_part(str(payload.get("model", "") or "model"))
    type_part = _job_id_part(job_type.value)
    return f"{model_part}-{type_part}-{uuid.uuid4().hex[:12]}"


def _job_id_part(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip())
    normalized = normalized.strip("-_")
    return normalized[:64] or "job"


def _normalized_model(model: str) -> str:
    return str(model or "").strip().casefold()


class ActiveFullPipelineJobConflict(RuntimeError):
    def __init__(self, active_job: JobRecord) -> None:
        self.active_job = active_job
        super().__init__(
            f"Full Product Factory workflow for model {active_job.model} is already "
            f"{active_job.status.value} as job {active_job.job_id}."
        )
