"""Async Price Monitoring fetch execution lifecycle."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from ecommerce.artifacts import artifact_link_payload
from ecommerce.db.repositories.alerts import evaluate_alert_rules_for_run, has_active_alert_rules
from ecommerce.db.config import is_database_configured
from ecommerce.db.session import session_scope
from ecommerce.price_monitoring.fetch_run import (
    PriceMonitoringFetchError,
    PriceMonitoringFetchResult,
    resolve_price_monitoring_fetch_source,
    run_price_monitoring_fetch,
    write_price_monitoring_fetch_result,
)
from ecommerce.price_monitoring.persistence import persist_fetch_result_if_configured

MAX_FETCH_WORKERS_ENV_VAR = "ECOMMERCE_MAX_FETCH_WORKERS"
FETCH_STALE_AFTER_MINUTES_ENV_VAR = "ECOMMERCE_FETCH_STALE_AFTER_MINUTES"
SUBPROCESS_TERMINATE_TIMEOUT_SECONDS_ENV_VAR = "ECOMMERCE_SUBPROCESS_TERMINATE_TIMEOUT_SECONDS"
DEFAULT_MAX_FETCH_WORKERS = 3
MAX_FETCH_WORKERS_CAP = 8
DEFAULT_FETCH_STALE_AFTER_MINUTES = 30
DEFAULT_SUBPROCESS_TERMINATE_TIMEOUT_SECONDS = 30
FETCH_EXECUTION_FILENAME = "fetch_execution.json"
FETCH_EXECUTION_LOG_FILENAME = "fetch_execution.log"
FETCH_EXECUTIONS_DIRNAME = "fetch_executions"
ACTIVE_STATUSES = {"queued", "running"}
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "killed"}
FAILED_ARTIFACT_WARNING = "Execution failed. Artifacts may be partial or incomplete."
KILLED_REASON = "Process did not exit before terminate timeout."
KILLED_ARTIFACT_WARNING = "Execution was force killed. Artifacts may be partial or incomplete."


class ActiveFetchExecutionError(RuntimeError):
    """Raised when a run already has an active fetch execution."""

    def __init__(self, execution: "PriceMonitoringFetchExecution") -> None:
        super().__init__(f"Fetch execution {execution.execution_id} is already {execution.status}.")
        self.execution = execution


@dataclass
class PriceMonitoringFetchExecution:
    execution_type: str
    execution_id: str
    run_id: str
    status: str
    source: str
    catalog_url: str | None
    queued_at: str
    started_at: str | None
    completed_at: str | None
    cancelled_at: str | None
    cancel_reason: str
    input_csv_path: Path
    enriched_csv_path: Path | None
    fetch_summary_path: Path | None
    fetch_result_path: Path
    execution_path: Path
    log_path: Path
    warnings: list[str] = field(default_factory=list)
    error: str = ""
    killed_reason: str | None = None
    artifacts_are_diagnostic: bool = False
    artifact_warning: str | None = None
    observation_count: int = 0
    replaced_observation_count: int = 0
    catalog_snapshot_count: int | None = None
    matched_observation_count: int = 0
    unmatched_observation_count: int = 0
    was_refetch: bool = False
    fetch_attempt: int = 0
    persistence_status: str = "not_configured"
    persistence_warnings: list[str] = field(default_factory=list)
    alert_evaluation_status: str = "not_configured"
    alert_event_count: int = 0
    alert_duplicate_count: int = 0
    alert_warnings: list[str] = field(default_factory=list)
    fetch_input_mode: str = "source_urls"
    source_url_capture_used: bool = False
    source_url_capture_status: str = "not_run"
    source_url_capture_selected_count: int = 0
    source_url_capture_succeeded_count: int = 0
    source_url_capture_failed_count: int = 0
    source_url_capture_result_path: Path | None = None
    source_url_capture_warnings: list[str] = field(default_factory=list)
    source_url_capture_run_id: str = ""
    observation_batch_id: str = ""
    worker_id: str | None = None
    parent_process_id: int | None = None
    process_id: int | None = None
    process_group_id: int | None = None
    thread_name: str | None = None
    heartbeat_at: str | None = None
    command: list[str] = field(default_factory=list)
    exit_code: int | None = None
    termination_mode: str | None = None
    terminate_sent_at: str | None = None
    kill_sent_at: str | None = None
    killed_at: str | None = None
    stdout_log_path: Path | None = None
    stderr_log_path: Path | None = None

    def to_dict(self, *, include_artifacts: bool = False) -> dict[str, object]:
        payload = asdict(self)
        payload["input_csv_path"] = str(self.input_csv_path)
        payload["enriched_csv_path"] = str(self.enriched_csv_path) if self.enriched_csv_path is not None else ""
        payload["fetch_summary_path"] = str(self.fetch_summary_path) if self.fetch_summary_path is not None else ""
        payload["fetch_result_path"] = str(self.fetch_result_path)
        payload["source_url_capture_result_path"] = (
            str(self.source_url_capture_result_path) if self.source_url_capture_result_path is not None else ""
        )
        payload["execution_path"] = str(self.execution_path)
        payload["log_path"] = str(self.log_path)
        payload["stdout_log_path"] = str(self.stdout_log_path) if self.stdout_log_path is not None else ""
        payload["stderr_log_path"] = str(self.stderr_log_path) if self.stderr_log_path is not None else ""
        if include_artifacts:
            payload["artifacts"] = execution_artifacts(self)
        return payload


@dataclass(frozen=True)
class _FetchExecutionJob:
    run_dir: Path
    execution_id: str
    source: str
    catalog_url: str | None
    execution_type: str = "fetch"


@dataclass(frozen=True)
class _ActiveWorkerMetadata:
    worker_id: str
    process: subprocess.Popen | None
    process_id: int
    thread_name: str
    stdout_log_path: Path
    stderr_log_path: Path
    termination_requested: bool = False


_LOCK = threading.RLock()
_QUEUE: deque[_FetchExecutionJob] = deque()
_ACTIVE_EXECUTIONS: dict[str, _ActiveWorkerMetadata] = {}
_RUN_ACTIVE_EXECUTIONS: dict[str, str] = {}
_WORKER_THREADS: dict[str, threading.Thread] = {}
_FINALIZING_EXECUTIONS: set[str] = set()


def enqueue_fetch_execution(
    run_dir: Path,
    *,
    source: str | None = None,
    catalog_url: str | None = None,
) -> PriceMonitoringFetchExecution:
    run_dir = Path(run_dir)
    if not run_dir.exists():
        raise FileNotFoundError(f"Price monitoring run folder not found: {run_dir}")
    input_csv_path = run_dir / "input.csv"
    if not input_csv_path.exists():
        raise FileNotFoundError(f"Price monitoring input.csv not found: {input_csv_path}")

    resolved_source = resolve_price_monitoring_fetch_source(run_dir, source)
    with _LOCK:
        latest = load_latest_fetch_execution(run_dir)
        active_execution_id = _RUN_ACTIVE_EXECUTIONS.get(run_dir.name)
        if active_execution_id:
            latest = load_fetch_execution(run_dir, active_execution_id)
        if latest is not None and latest.status in ACTIVE_STATUSES:
            raise ActiveFetchExecutionError(latest)

        execution = _new_execution(run_dir, resolved_source, catalog_url)
        save_fetch_execution(execution)
        _write_latest_log_alias(execution, "")
        append_execution_log(execution, f"Queued fetch execution for source {resolved_source}.")
        _QUEUE.append(
            _FetchExecutionJob(
                run_dir=run_dir,
                execution_id=execution.execution_id,
                source=resolved_source,
                catalog_url=_optional_text(catalog_url) or None,
                execution_type="fetch",
            )
        )
        _RUN_ACTIVE_EXECUTIONS[execution.run_id] = execution.execution_id
        _ensure_worker_locked()
        return load_fetch_execution(run_dir, execution.execution_id)


def cancel_fetch_execution(run_dir: Path, execution_id: str, reason: str | None = None) -> PriceMonitoringFetchExecution:
    with _LOCK:
        execution = load_fetch_execution(run_dir, execution_id)
        if execution.status in TERMINAL_STATUSES:
            return execution
        if execution.execution_id in _FINALIZING_EXECUTIONS:
            append_execution_log(
                execution,
                "Cancellation requested after fetch completed and persistence started; execution will finish normally.",
            )
            return load_fetch_execution(run_dir, execution_id)

        previous_status = execution.status
        was_stale_running = previous_status == "running" and is_execution_stale(execution)
        now = _now_iso()
        execution.status = "cancelled"
        execution.completed_at = now
        execution.cancelled_at = now
        execution.cancel_reason = _optional_text(reason) or "Cancellation requested."
        removed_from_queue = _remove_queued_job_locked(execution.execution_id)
        active_metadata = _ACTIVE_EXECUTIONS.get(execution.execution_id)
        owned_by_process = active_metadata is not None
        if previous_status == "running" and not owned_by_process and was_stale_running:
            message = "Cancellation requested for stale running execution."
        elif previous_status == "running" and owned_by_process:
            execution.terminate_sent_at = now
            execution.termination_mode = "graceful"
            message = "Cancellation requested. Sending graceful termination to child process."
        else:
            message = "Cancellation requested before execution started."
        save_fetch_execution(execution)
        append_execution_log(execution, message)
        if previous_status == "queued":
            _clear_run_active_locked(execution)
            return load_fetch_execution(run_dir, execution_id)
        if previous_status == "running" and active_metadata is not None:
            return _terminate_active_execution(run_dir, execution_id, active_metadata)
        if previous_status == "running" and not owned_by_process:
            execution = load_fetch_execution(run_dir, execution_id)
            execution.termination_mode = "stale_metadata"
            save_fetch_execution(execution)
        if removed_from_queue or not owned_by_process:
            _clear_run_active_locked(execution)
        _ensure_worker_locked()
        return load_fetch_execution(run_dir, execution_id)


def cancel_latest_active_fetch_execution(run_dir: Path, reason: str | None = None) -> PriceMonitoringFetchExecution:
    latest = load_latest_fetch_execution(run_dir)
    if latest is None or latest.status not in ACTIVE_STATUSES:
        raise FileNotFoundError("No active fetch execution exists for this run.")
    return cancel_fetch_execution(run_dir, latest.execution_id, reason)


def load_latest_fetch_execution(run_dir: Path) -> PriceMonitoringFetchExecution | None:
    path = Path(run_dir) / FETCH_EXECUTION_FILENAME
    if not path.exists():
        return None
    return _execution_from_payload(_read_json(path), Path(run_dir), path)


def load_fetch_execution(run_dir: Path, execution_id: str) -> PriceMonitoringFetchExecution:
    path = Path(run_dir) / FETCH_EXECUTIONS_DIRNAME / f"{execution_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Price monitoring fetch execution not found: {path}")
    return _execution_from_payload(_read_json(path), Path(run_dir), path)


def list_fetch_executions(run_dir: Path) -> list[PriceMonitoringFetchExecution]:
    execution_dir = Path(run_dir) / FETCH_EXECUTIONS_DIRNAME
    if not execution_dir.exists():
        return []
    executions: list[PriceMonitoringFetchExecution] = []
    for path in execution_dir.glob("*.json"):
        try:
            executions.append(_execution_from_payload(_read_json(path), Path(run_dir), path))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    executions.sort(key=_execution_sort_key, reverse=True)
    return executions


def save_fetch_execution(execution: PriceMonitoringFetchExecution) -> None:
    if _should_preserve_existing_cancel_terminal(execution):
        return
    _atomic_write_json(execution.execution_path, execution.to_dict(include_artifacts=False))
    latest_path = execution.execution_path.parent.parent / FETCH_EXECUTION_FILENAME
    _atomic_write_json(latest_path, execution.to_dict(include_artifacts=False))


def append_execution_log(execution: PriceMonitoringFetchExecution, line: str) -> None:
    text = f"{_now_iso()} {line.rstrip()}\n"
    execution.log_path.parent.mkdir(parents=True, exist_ok=True)
    with execution.log_path.open("a", encoding="utf-8") as f:
        f.write(text)
    latest_log_path = execution.execution_path.parent.parent / FETCH_EXECUTION_LOG_FILENAME
    latest = load_latest_fetch_execution(execution.execution_path.parent.parent)
    if latest is not None and latest.execution_id == execution.execution_id:
        with latest_log_path.open("a", encoding="utf-8") as f:
            f.write(text)


def read_latest_execution_log_lines(run_dir: Path) -> list[str]:
    latest = load_latest_fetch_execution(run_dir)
    if latest is None:
        raise FileNotFoundError("No fetch execution exists for this run.")
    return read_execution_log_lines(run_dir, latest.execution_id)


def read_execution_log_lines(run_dir: Path, execution_id: str) -> list[str]:
    execution = load_fetch_execution(run_dir, execution_id)
    if not execution.log_path.exists():
        return []
    return execution.log_path.read_text(encoding="utf-8").splitlines()


def execution_response(execution: PriceMonitoringFetchExecution) -> dict[str, object]:
    payload = execution.to_dict(include_artifacts=True)
    stale_after_minutes = get_fetch_stale_after_minutes()
    payload["stale"] = is_execution_stale(execution, stale_after_minutes=stale_after_minutes)
    payload["stale_after_minutes"] = stale_after_minutes
    payload["queue_position"] = queue_position(execution.execution_id)
    return payload


def source_url_fetch_result_to_execution_payload(result: PriceMonitoringFetchResult) -> dict[str, object]:
    status = _normalize_fetch_status(result.status)
    payload = {
        "run_id": result.run_id,
        "execution_id": "",
        "execution_type": "fetch",
        "status": status,
        "source": result.source,
        "catalog_url": None,
        "queued_at": result.started_at,
        "started_at": result.started_at,
        "completed_at": result.completed_at,
        "cancelled_at": None,
        "cancel_reason": "",
        "input_csv_path": str(result.input_csv_path),
        "enriched_csv_path": str(result.enriched_csv_path) if result.enriched_csv_path is not None else "",
        "fetch_summary_path": str(result.fetch_summary_path) if result.fetch_summary_path is not None else "",
        "fetch_result_path": str(result.fetch_result_path),
        "execution_path": "",
        "log_path": "",
        "warnings": result.warnings,
        "error": result.error,
        "killed_reason": None,
        "artifacts_are_diagnostic": False,
        "artifact_warning": None,
        "observation_count": 0,
        "replaced_observation_count": 0,
        "catalog_snapshot_count": None,
        "matched_observation_count": 0,
        "unmatched_observation_count": 0,
        "was_refetch": False,
        "fetch_attempt": 0,
        "persistence_status": "unknown",
        "persistence_warnings": [],
        "alert_evaluation_status": "not_configured" if not is_database_configured() else "skipped",
        "alert_event_count": 0,
        "alert_duplicate_count": 0,
        "alert_warnings": [],
        "fetch_input_mode": result.fetch_input_mode,
        "source_url_capture_used": result.source_url_capture_used,
        "source_url_capture_status": result.source_url_capture_status,
        "source_url_capture_selected_count": result.source_url_capture_selected_count,
        "source_url_capture_succeeded_count": result.source_url_capture_succeeded_count,
        "source_url_capture_failed_count": result.source_url_capture_failed_count,
        "source_url_capture_result_path": str(result.source_url_capture_result_path) if result.source_url_capture_result_path else "",
        "source_url_capture_warnings": list(result.source_url_capture_warnings or []),
        "source_url_capture_run_id": result.source_url_capture_run_id,
        "observation_batch_id": result.observation_batch_id,
        "worker_id": None,
        "parent_process_id": None,
        "process_id": None,
        "process_group_id": None,
        "thread_name": None,
        "heartbeat_at": None,
        "command": [],
        "exit_code": None,
        "termination_mode": None,
        "terminate_sent_at": None,
        "kill_sent_at": None,
        "killed_at": None,
        "stdout_log_path": "",
        "stderr_log_path": "",
        "stale": False,
        "stale_after_minutes": get_fetch_stale_after_minutes(),
        "queue_position": None,
        "artifacts": [
            artifact_link_payload(path)
            for path in [
                result.input_csv_path,
                result.enriched_csv_path,
                result.fetch_summary_path,
                result.fetch_result_path,
            ]
            if path is not None
        ],
    }
    return payload


def queue_position(execution_id: str) -> int | None:
    with _LOCK:
        for index, job in enumerate(_QUEUE, start=1):
            if job.execution_id == execution_id:
                return index
    return None


def is_execution_stale(
    execution: PriceMonitoringFetchExecution,
    *,
    stale_after_minutes: int | None = None,
) -> bool:
    if execution.status != "running":
        return False
    threshold = stale_after_minutes or get_fetch_stale_after_minutes()
    heartbeat = _parse_iso(execution.heartbeat_at)
    if heartbeat is None:
        return True
    is_old = datetime.now(timezone.utc) - heartbeat > timedelta(minutes=threshold)
    with _LOCK:
        owned_by_process = execution.execution_id in _ACTIVE_EXECUTIONS
    return is_old or not owned_by_process


def get_max_fetch_workers() -> int:
    return _env_int(MAX_FETCH_WORKERS_ENV_VAR, DEFAULT_MAX_FETCH_WORKERS, minimum=1, maximum=MAX_FETCH_WORKERS_CAP)


def get_fetch_stale_after_minutes() -> int:
    return _env_int(FETCH_STALE_AFTER_MINUTES_ENV_VAR, DEFAULT_FETCH_STALE_AFTER_MINUTES, minimum=1)


def get_subprocess_terminate_timeout_seconds() -> int:
    return _env_int(
        SUBPROCESS_TERMINATE_TIMEOUT_SECONDS_ENV_VAR,
        DEFAULT_SUBPROCESS_TERMINATE_TIMEOUT_SECONDS,
        minimum=1,
    )


def execution_artifacts(execution: PriceMonitoringFetchExecution) -> list[dict]:
    paths: list[Path | None] = [
        execution.input_csv_path,
        execution.enriched_csv_path,
        execution.fetch_summary_path,
        execution.fetch_result_path,
        execution.source_url_capture_result_path,
        execution.execution_path,
        execution.log_path,
        execution.stdout_log_path,
        execution.stderr_log_path,
        execution.execution_path.parent.parent / FETCH_EXECUTION_FILENAME,
        execution.execution_path.parent.parent / FETCH_EXECUTION_LOG_FILENAME,
    ]
    seen: set[str] = set()
    artifacts = []
    for path in paths:
        if path is None:
            continue
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        artifacts.append(artifact_link_payload(path))
    return artifacts


def wait_for_worker_idle(timeout: float = 5.0) -> bool:
    deadline = datetime.now(timezone.utc).timestamp() + timeout
    while datetime.now(timezone.utc).timestamp() < deadline:
        with _LOCK:
            active = bool(_QUEUE or _ACTIVE_EXECUTIONS or _FINALIZING_EXECUTIONS)
            worker_alive = any(thread.is_alive() for thread in _WORKER_THREADS.values())
        if not active and not worker_alive:
            return True
        threading.Event().wait(0.01)
    return False


def evaluate_alerts_after_persistence(run_id: str, *, persistence_status: str) -> tuple[str, int, int, list[str]]:
    if not is_database_configured():
        return "not_configured", 0, 0, []
    if persistence_status != "persisted":
        return "skipped", 0, 0, []
    with session_scope() as session:
        if not has_active_alert_rules(session):
            return "skipped", 0, 0, []
        result = evaluate_alert_rules_for_run(session, run_id)
        return "evaluated", result.created_event_count, result.duplicate_event_count, result.warnings


def run_fetch_execution_child(run_dir: Path, execution_id: str) -> int:
    job = _FetchExecutionJob(
        run_dir=Path(run_dir),
        execution_id=execution_id,
        source="",
        catalog_url=None,
        execution_type="fetch",
    )
    try:
        execution = load_fetch_execution(job.run_dir, execution_id)
        if execution.execution_type != "fetch":
            raise ValueError(f"Unsupported execution type: {execution.execution_type}")
        if execution.status in {"cancelled", "killed"}:
            append_execution_log(execution, "Child process found execution already cancelled; exiting.")
            return 0
        _heartbeat(job.run_dir, job.execution_id)
        append_execution_log(execution, "Child process started fetch work.")
        _heartbeat(job.run_dir, job.execution_id)
        result = run_price_monitoring_fetch(
            job.run_dir,
            source=execution.source,
            catalog_url=execution.catalog_url,
            write_result=False,
        )
        _heartbeat(job.run_dir, job.execution_id)
        _complete_successful_execution(job, result)
        return 0
    except PriceMonitoringFetchError as exc:
        _complete_failed_execution(job, str(exc), exc.result)
        return 1
    except Exception as exc:
        _complete_failed_execution(job, _safe_error_message(exc), None)
        return 1


def _worker_entry(job: _FetchExecutionJob, worker_id: str) -> None:
    try:
        _process_job(job, worker_id)
    finally:
        with _LOCK:
            _ACTIVE_EXECUTIONS.pop(job.execution_id, None)
            _WORKER_THREADS.pop(job.execution_id, None)
            _clear_run_active_locked_by_id(job.run_dir.name, job.execution_id)
            _ensure_worker_locked()


def _process_job(job: _FetchExecutionJob, worker_id: str) -> None:
    process: subprocess.Popen | None = None
    try:
        execution, process = _start_execution(job.run_dir, job.execution_id, worker_id)
        if execution is None:
            return
        exit_code = process.wait()
        _append_child_output(execution)
        _reconcile_child_exit(job, exit_code)
    except Exception as exc:
        _complete_failed_execution(job, _safe_error_message(exc), None)
        return


def _start_execution(
    run_dir: Path,
    execution_id: str,
    worker_id: str,
) -> tuple[PriceMonitoringFetchExecution | None, subprocess.Popen | None]:
    with _LOCK:
        execution = load_fetch_execution(run_dir, execution_id)
        if execution.status == "cancelled":
            append_execution_log(execution, "Queued execution was cancelled; skipping fetch.")
            return None, None
        if execution.status != "queued":
            return None, None
        now = _now_iso()
        command = build_execution_command(execution.run_id, execution.execution_id, execution.execution_type)
        stdout_log_path = execution.execution_path.with_suffix(".stdout.log")
        stderr_log_path = execution.execution_path.with_suffix(".stderr.log")
        process = _launch_child_process(command, stdout_log_path=stdout_log_path, stderr_log_path=stderr_log_path)
        execution.status = "running"
        execution.started_at = now
        execution.worker_id = worker_id
        execution.parent_process_id = os.getpid()
        execution.process_id = process.pid
        execution.process_group_id = _process_group_id(process)
        execution.thread_name = threading.current_thread().name
        execution.heartbeat_at = now
        execution.command = command
        execution.stdout_log_path = stdout_log_path
        execution.stderr_log_path = stderr_log_path
        execution.termination_mode = "none"
        metadata = _ACTIVE_EXECUTIONS.get(execution_id)
        if metadata is not None:
            _ACTIVE_EXECUTIONS[execution_id] = _ActiveWorkerMetadata(
                worker_id=metadata.worker_id,
                process=process,
                process_id=process.pid,
                thread_name=metadata.thread_name,
                stdout_log_path=stdout_log_path,
                stderr_log_path=stderr_log_path,
                termination_requested=metadata.termination_requested,
            )
        save_fetch_execution(execution)
        append_execution_log(execution, f"Started subprocess fetch execution with pid {process.pid}.")
        return execution, process


def build_execution_command(run_id: str, execution_id: str, execution_type: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "ecommerce.jobs.run_price_monitoring_execution",
        "--run-id",
        run_id,
        "--execution-id",
        execution_id,
        "--execution-type",
        execution_type,
    ]


def _launch_child_process(
    command: list[str],
    *,
    stdout_log_path: Path,
    stderr_log_path: Path,
) -> subprocess.Popen:
    stdout_log_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_log_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_handle = stdout_log_path.open("w", encoding="utf-8")
    stderr_handle = stderr_log_path.open("w", encoding="utf-8")
    kwargs: dict[str, object] = {
        "stdout": stdout_handle,
        "stderr": stderr_handle,
        "text": True,
        "env": _child_process_env(),
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        return subprocess.Popen(command, **kwargs)
    finally:
        stdout_handle.close()
        stderr_handle.close()


def _child_process_env() -> dict[str, str]:
    env = dict(os.environ)
    source_path = str(Path(__file__).resolve().parents[2])
    existing = env.get("PYTHONPATH", "")
    paths = [source_path]
    if existing:
        paths.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(paths)
    return env


def _process_group_id(process: subprocess.Popen) -> int | None:
    if os.name == "nt":
        return process.pid
    try:
        return os.getpgid(process.pid)
    except OSError:
        return None


def _reconcile_child_exit(job: _FetchExecutionJob, exit_code: int) -> None:
    with _LOCK:
        execution = load_fetch_execution(job.run_dir, job.execution_id)
        if execution.exit_code is None:
            execution.exit_code = exit_code
        if execution.status in TERMINAL_STATUSES:
            if execution.status == "failed":
                _mark_artifacts_diagnostic(execution, FAILED_ARTIFACT_WARNING)
            if execution.status == "killed":
                _mark_killed_execution(execution, exit_code=exit_code)
            save_fetch_execution(execution)
            return
        if exit_code == 0:
            execution.status = "failed"
            execution.error = "Child process exited without writing a terminal execution status."
        else:
            execution.status = "failed"
            execution.error = f"Child process exited with code {exit_code}."
        execution.completed_at = _now_iso()
        execution.termination_mode = "process_exited"
        execution.heartbeat_at = _now_iso()
        _mark_artifacts_diagnostic(execution, FAILED_ARTIFACT_WARNING)
        save_fetch_execution(execution)
        append_execution_log(execution, execution.error)


def _append_child_output(execution: PriceMonitoringFetchExecution) -> None:
    if execution.stdout_log_path is not None:
        _append_prefixed_log_file(execution, execution.stdout_log_path, "[stdout]")
    if execution.stderr_log_path is not None:
        _append_prefixed_log_file(execution, execution.stderr_log_path, "[stderr]")


def _append_prefixed_log_file(execution: PriceMonitoringFetchExecution, path: Path, prefix: str) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for line in lines:
        append_execution_log(execution, f"{prefix} {line}")


def _terminate_active_execution(
    run_dir: Path,
    execution_id: str,
    metadata: _ActiveWorkerMetadata,
) -> PriceMonitoringFetchExecution:
    process = metadata.process
    if process is None:
        execution = load_fetch_execution(run_dir, execution_id)
        execution.termination_mode = "stale_metadata"
        save_fetch_execution(execution)
        append_execution_log(execution, "Cancellation requested for stale running execution.")
        _clear_run_active_locked(execution)
        return load_fetch_execution(run_dir, execution_id)

    _send_graceful_terminate(process)
    timeout = get_subprocess_terminate_timeout_seconds()
    try:
        exit_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        execution = load_fetch_execution(run_dir, execution_id)
        execution.kill_sent_at = _now_iso()
        save_fetch_execution(execution)
        append_execution_log(execution, "Graceful termination timed out; force killing child process tree.")
        _force_kill_process_tree(process)
        try:
            exit_code = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            exit_code = process.poll()
        execution = load_fetch_execution(run_dir, execution_id)
        if execution.status not in {"succeeded", "failed", "killed"}:
            _mark_killed_execution(execution, exit_code=exit_code)
            save_fetch_execution(execution)
            append_execution_log(execution, "Fetch execution process was force killed.")
        return load_fetch_execution(run_dir, execution_id)

    execution = load_fetch_execution(run_dir, execution_id)
    if execution.status not in TERMINAL_STATUSES:
        execution.status = "cancelled"
        execution.completed_at = _now_iso()
        execution.cancelled_at = execution.completed_at
        execution.termination_mode = "graceful"
        execution.exit_code = exit_code
        save_fetch_execution(execution)
        append_execution_log(execution, "Fetch execution process terminated gracefully.")
    elif execution.status == "cancelled" and execution.exit_code is None:
        execution.exit_code = exit_code
        execution.termination_mode = execution.termination_mode or "graceful"
        save_fetch_execution(execution)
    return load_fetch_execution(run_dir, execution_id)


def _send_graceful_terminate(process: subprocess.Popen) -> None:
    try:
        process.terminate()
    except OSError:
        return


def _force_kill_process_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except OSError:
        try:
            process.kill()
        except OSError:
            return


def _complete_successful_execution(job: _FetchExecutionJob, result: PriceMonitoringFetchResult) -> None:
    with _LOCK:
        execution = load_fetch_execution(job.run_dir, job.execution_id)
        if execution.status in TERMINAL_STATUSES:
            append_execution_log(execution, f"Fetch completed after {execution.status}; final status remains {execution.status}.")
            return
        _FINALIZING_EXECUTIONS.add(job.execution_id)
        append_execution_log(execution, "Fetch completed; publishing result and running persistence.")

    try:
        _heartbeat(job.run_dir, job.execution_id)
        write_price_monitoring_fetch_result(result.fetch_result_path, result)
        _heartbeat(job.run_dir, job.execution_id)
        with _LOCK:
            execution = load_fetch_execution(job.run_dir, job.execution_id)
            if execution.status in {"cancelled", "killed"}:
                append_execution_log(execution, f"Persistence skipped because execution is {execution.status}.")
                return
        append_execution_log(execution, "Persisting fetch observations.")
        persistence = persist_fetch_result_if_configured(result, trigger_type="manual")
        if str(getattr(persistence, "persistence_status", "unknown")) != "persisted":
            warnings = [str(item) for item in getattr(persistence, "warnings", [])]
            message = "Price monitoring DB persistence did not complete."
            if warnings:
                message = f"{message} {warnings[0]}"
            raise RuntimeError(message)
        _heartbeat(job.run_dir, job.execution_id)
        with _LOCK:
            execution = load_fetch_execution(job.run_dir, job.execution_id)
            if execution.status in {"cancelled", "killed"}:
                append_execution_log(execution, f"Alert evaluation skipped because execution is {execution.status}.")
                return
        append_execution_log(execution, "Evaluating alert rules if configured.")
        alert_status, alert_count, duplicate_count, alert_warnings = evaluate_alerts_after_persistence(
            result.run_id,
            persistence_status=str(getattr(persistence, "persistence_status", "unknown")),
        )
        _heartbeat(job.run_dir, job.execution_id)
        with _LOCK:
            execution = load_fetch_execution(job.run_dir, job.execution_id)
            if execution.status in TERMINAL_STATUSES:
                append_execution_log(execution, f"Success finalization skipped because execution is {execution.status}.")
                return
            execution.heartbeat_at = _now_iso()
            execution.status = "succeeded"
            execution.completed_at = _now_iso()
            execution.enriched_csv_path = result.enriched_csv_path
            execution.fetch_summary_path = result.fetch_summary_path
            execution.fetch_result_path = result.fetch_result_path
            execution.warnings = result.warnings
            execution.error = ""
            execution.observation_count = int(getattr(persistence, "observation_count", 0))
            execution.replaced_observation_count = int(getattr(persistence, "replaced_observation_count", 0))
            execution.catalog_snapshot_count = getattr(persistence, "catalog_snapshot_count", None)
            execution.matched_observation_count = int(getattr(persistence, "matched_observation_count", 0))
            execution.unmatched_observation_count = int(getattr(persistence, "unmatched_observation_count", 0))
            execution.was_refetch = bool(getattr(persistence, "was_refetch", False))
            execution.fetch_attempt = int(getattr(persistence, "fetch_attempt", execution.fetch_attempt))
            execution.persistence_status = str(getattr(persistence, "persistence_status", "unknown"))
            execution.persistence_warnings = [str(item) for item in getattr(persistence, "warnings", [])]
            execution.alert_evaluation_status = alert_status
            execution.alert_event_count = alert_count
            execution.alert_duplicate_count = duplicate_count
            execution.alert_warnings = alert_warnings
            _apply_source_url_capture_result(execution, result)
            save_fetch_execution(execution)
            append_execution_log(execution, "Fetch execution succeeded.")
    except Exception as exc:
        _complete_failed_execution(job, _safe_error_message(exc), result, write_result=False)
    finally:
        with _LOCK:
            _FINALIZING_EXECUTIONS.discard(job.execution_id)


def _complete_failed_execution(
    job: _FetchExecutionJob,
    error: str,
    result: PriceMonitoringFetchResult | None,
    *,
    write_result: bool = True,
) -> None:
    with _LOCK:
        execution = load_fetch_execution(job.run_dir, job.execution_id)
        if execution.status in TERMINAL_STATUSES:
            append_execution_log(execution, f"Fetch failed after {execution.status}; final status remains {execution.status}.")
            return
    with _LOCK:
        execution = load_fetch_execution(job.run_dir, job.execution_id)
        if execution.status in TERMINAL_STATUSES:
            append_execution_log(execution, f"Failure finalization skipped because execution is {execution.status}.")
            return
        execution.heartbeat_at = _now_iso()
        if result is not None and write_result:
            write_price_monitoring_fetch_result(result.fetch_result_path, result)
        execution.status = "failed"
        execution.completed_at = _now_iso()
        execution.error = error
        _mark_artifacts_diagnostic(execution, FAILED_ARTIFACT_WARNING)
        if result is not None:
            execution.enriched_csv_path = result.enriched_csv_path
            execution.fetch_summary_path = result.fetch_summary_path
            execution.fetch_result_path = result.fetch_result_path
            execution.warnings = result.warnings
            _apply_source_url_capture_result(execution, result)
        save_fetch_execution(execution)
        append_execution_log(execution, f"Fetch execution failed: {error}")


def _mark_artifacts_diagnostic(execution: PriceMonitoringFetchExecution, warning: str) -> None:
    execution.artifacts_are_diagnostic = True
    execution.artifact_warning = warning


def _apply_source_url_capture_result(
    execution: PriceMonitoringFetchExecution,
    result: PriceMonitoringFetchResult,
) -> None:
    execution.fetch_input_mode = result.fetch_input_mode
    execution.source_url_capture_used = result.source_url_capture_used
    execution.source_url_capture_status = result.source_url_capture_status
    execution.source_url_capture_selected_count = result.source_url_capture_selected_count
    execution.source_url_capture_succeeded_count = result.source_url_capture_succeeded_count
    execution.source_url_capture_failed_count = result.source_url_capture_failed_count
    execution.source_url_capture_result_path = result.source_url_capture_result_path
    execution.source_url_capture_warnings = list(result.source_url_capture_warnings or [])
    execution.source_url_capture_run_id = result.source_url_capture_run_id
    execution.observation_batch_id = result.observation_batch_id


def _mark_killed_execution(execution: PriceMonitoringFetchExecution, *, exit_code: int | None) -> None:
    now = _now_iso()
    execution.status = "killed"
    execution.completed_at = now
    execution.killed_at = now
    execution.kill_sent_at = execution.kill_sent_at or execution.killed_at
    execution.killed_reason = execution.killed_reason or KILLED_REASON
    execution.termination_mode = "force_kill"
    execution.exit_code = exit_code
    if not execution.error:
        execution.error = "Fetch execution process was force killed."
    _mark_artifacts_diagnostic(execution, KILLED_ARTIFACT_WARNING)


def _new_execution(run_dir: Path, source: str, catalog_url: str | None) -> PriceMonitoringFetchExecution:
    execution_id = uuid4().hex
    execution_dir = run_dir / FETCH_EXECUTIONS_DIRNAME
    queued_at = _now_iso()
    return PriceMonitoringFetchExecution(
        execution_id=execution_id,
        execution_type="fetch",
        run_id=run_dir.name,
        status="queued",
        source=source,
        catalog_url=_optional_text(catalog_url) or None,
        queued_at=queued_at,
        started_at=None,
        completed_at=None,
        cancelled_at=None,
        cancel_reason="",
        input_csv_path=run_dir / "input.csv",
        enriched_csv_path=None,
        fetch_summary_path=None,
        fetch_result_path=run_dir / "fetch_result.json",
        execution_path=execution_dir / f"{execution_id}.json",
        log_path=execution_dir / f"{execution_id}.log",
        was_refetch=(run_dir / "fetch_result.json").exists(),
        fetch_attempt=_next_fetch_attempt(run_dir),
    )


def _next_fetch_attempt(run_dir: Path) -> int:
    execution_dir = run_dir / FETCH_EXECUTIONS_DIRNAME
    existing = list(execution_dir.glob("*.json")) if execution_dir.exists() else []
    return len(existing) + 1


def _ensure_worker_locked() -> None:
    max_workers = get_max_fetch_workers()
    while _QUEUE and len(_ACTIVE_EXECUTIONS) < max_workers:
        job = _QUEUE.popleft()
        try:
            execution = load_fetch_execution(job.run_dir, job.execution_id)
        except FileNotFoundError:
            _clear_run_active_locked_by_id(job.run_dir.name, job.execution_id)
            continue
        if execution.status == "cancelled":
            append_execution_log(execution, "Queued execution was cancelled; skipping fetch.")
            _clear_run_active_locked(execution)
            continue
        if execution.status != "queued":
            _clear_run_active_locked(execution)
            continue
        worker_id = uuid4().hex[:12]
        thread_name = f"price-monitoring-fetch-{worker_id}"
        metadata = _ActiveWorkerMetadata(
            worker_id=worker_id,
            process=None,
            process_id=0,
            thread_name=thread_name,
            stdout_log_path=execution.execution_path.with_suffix(".stdout.log"),
            stderr_log_path=execution.execution_path.with_suffix(".stderr.log"),
        )
        thread = threading.Thread(target=_worker_entry, args=(job, worker_id), name=thread_name, daemon=True)
        _ACTIVE_EXECUTIONS[job.execution_id] = metadata
        _WORKER_THREADS[job.execution_id] = thread
        thread.start()


def _heartbeat(run_dir: Path, execution_id: str) -> None:
    with _LOCK:
        execution = load_fetch_execution(run_dir, execution_id)
        if execution.status not in ACTIVE_STATUSES:
            return
        execution.heartbeat_at = _now_iso()
        save_fetch_execution(execution)


def _remove_queued_job_locked(execution_id: str) -> bool:
    removed = False
    retained: deque[_FetchExecutionJob] = deque()
    while _QUEUE:
        job = _QUEUE.popleft()
        if job.execution_id == execution_id:
            removed = True
            continue
        retained.append(job)
    _QUEUE.extend(retained)
    return removed


def _clear_run_active_locked(execution: PriceMonitoringFetchExecution) -> None:
    _clear_run_active_locked_by_id(execution.run_id, execution.execution_id)


def _clear_run_active_locked_by_id(run_id: str, execution_id: str) -> None:
    if _RUN_ACTIVE_EXECUTIONS.get(run_id) == execution_id:
        _RUN_ACTIVE_EXECUTIONS.pop(run_id, None)


def _write_latest_log_alias(execution: PriceMonitoringFetchExecution, content: str) -> None:
    path = execution.execution_path.parent.parent / FETCH_EXECUTION_LOG_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _execution_from_payload(payload: dict[str, object], run_dir: Path, path: Path) -> PriceMonitoringFetchExecution:
    execution_id = str(payload.get("execution_id") or path.stem)
    execution_dir = run_dir / FETCH_EXECUTIONS_DIRNAME
    return PriceMonitoringFetchExecution(
        execution_id=execution_id,
        execution_type=str(payload.get("execution_type") or "fetch"),
        run_id=str(payload.get("run_id") or run_dir.name),
        status=_normalize_fetch_status(str(payload.get("status") or "")),
        source=str(payload.get("source") or ""),
        catalog_url=_none_or_text(payload.get("catalog_url")),
        queued_at=str(payload.get("queued_at") or payload.get("started_at") or ""),
        started_at=_none_or_text(payload.get("started_at")),
        completed_at=_none_or_text(payload.get("completed_at")),
        cancelled_at=_none_or_text(payload.get("cancelled_at")),
        cancel_reason=str(payload.get("cancel_reason") or ""),
        input_csv_path=Path(str(payload.get("input_csv_path") or run_dir / "input.csv")),
        enriched_csv_path=_path_or_none(payload.get("enriched_csv_path")),
        fetch_summary_path=_path_or_none(payload.get("fetch_summary_path")),
        fetch_result_path=Path(str(payload.get("fetch_result_path") or run_dir / "fetch_result.json")),
        execution_path=Path(str(payload.get("execution_path") or execution_dir / f"{execution_id}.json")),
        log_path=Path(str(payload.get("log_path") or execution_dir / f"{execution_id}.log")),
        warnings=[str(item) for item in _list_value(payload.get("warnings"))],
        error=str(payload.get("error") or ""),
        killed_reason=_none_or_text(payload.get("killed_reason")),
        artifacts_are_diagnostic=bool(payload.get("artifacts_are_diagnostic", False)),
        artifact_warning=_none_or_text(payload.get("artifact_warning")),
        observation_count=_int_value(payload.get("observation_count")),
        replaced_observation_count=_int_value(payload.get("replaced_observation_count")),
        catalog_snapshot_count=_optional_int_value(payload.get("catalog_snapshot_count")),
        matched_observation_count=_int_value(payload.get("matched_observation_count")),
        unmatched_observation_count=_int_value(payload.get("unmatched_observation_count")),
        was_refetch=bool(payload.get("was_refetch", False)),
        fetch_attempt=_int_value(payload.get("fetch_attempt")),
        persistence_status=str(payload.get("persistence_status") or "not_configured"),
        persistence_warnings=[str(item) for item in _list_value(payload.get("persistence_warnings"))],
        alert_evaluation_status=str(payload.get("alert_evaluation_status") or "not_configured"),
        alert_event_count=_int_value(payload.get("alert_event_count")),
        alert_duplicate_count=_int_value(payload.get("alert_duplicate_count")),
        alert_warnings=[str(item) for item in _list_value(payload.get("alert_warnings"))],
        fetch_input_mode=str(payload.get("fetch_input_mode") or "source_urls"),
        source_url_capture_used=bool(payload.get("source_url_capture_used", False)),
        source_url_capture_status=str(payload.get("source_url_capture_status") or "not_run"),
        source_url_capture_selected_count=_int_value(payload.get("source_url_capture_selected_count")),
        source_url_capture_succeeded_count=_int_value(payload.get("source_url_capture_succeeded_count")),
        source_url_capture_failed_count=_int_value(payload.get("source_url_capture_failed_count")),
        source_url_capture_result_path=_path_or_none(payload.get("source_url_capture_result_path")),
        source_url_capture_warnings=[str(item) for item in _list_value(payload.get("source_url_capture_warnings"))],
        source_url_capture_run_id=str(payload.get("source_url_capture_run_id") or ""),
        observation_batch_id=str(payload.get("observation_batch_id") or ""),
        worker_id=_none_or_text(payload.get("worker_id")),
        parent_process_id=_optional_int_value(payload.get("parent_process_id")),
        process_id=_optional_int_value(payload.get("process_id")),
        process_group_id=_optional_int_value(payload.get("process_group_id")),
        thread_name=_none_or_text(payload.get("thread_name")),
        heartbeat_at=_none_or_text(payload.get("heartbeat_at")),
        command=[str(item) for item in _list_value(payload.get("command"))],
        exit_code=_optional_int_value(payload.get("exit_code")),
        termination_mode=_none_or_text(payload.get("termination_mode")),
        terminate_sent_at=_none_or_text(payload.get("terminate_sent_at")),
        kill_sent_at=_none_or_text(payload.get("kill_sent_at")),
        killed_at=_none_or_text(payload.get("killed_at")),
        stdout_log_path=_path_or_none(payload.get("stdout_log_path")),
        stderr_log_path=_path_or_none(payload.get("stderr_log_path")),
    )


def _should_preserve_existing_cancel_terminal(execution: PriceMonitoringFetchExecution) -> bool:
    if not execution.execution_path.exists():
        return False
    try:
        existing = _read_json(execution.execution_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    existing_status = _normalize_fetch_status(str(existing.get("status") or ""))
    if existing_status == "killed" and execution.status != "killed":
        return True
    if existing_status == "cancelled" and execution.status in {"queued", "running", "succeeded", "failed"}:
        return True
    return False


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    _replace_with_retry(tmp_path, path)


def _read_json(path: Path) -> dict[str, object]:
    last_error: Exception | None = None
    for attempt in range(50):
        try:
            with path.open("r", encoding="utf-8-sig") as f:
                payload = json.load(f)
            break
        except (OSError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == 49:
                raise
            time.sleep(0.02)
    else:
        raise last_error or ValueError(f"Fetch execution metadata could not be read: {path}")
    if not isinstance(payload, dict):
        raise ValueError(f"Fetch execution metadata is not a JSON object: {path}")
    return payload


def _normalize_fetch_status(status: str) -> str:
    if status == "fetch_completed":
        return "succeeded"
    if status == "fetch_failed":
        return "failed"
    return status


def _safe_error_message(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return exc.__class__.__name__
    return message.splitlines()[0][:500]


def _optional_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _none_or_text(value: object) -> str | None:
    text = _optional_text(value)
    return text or None


def _path_or_none(value: object) -> Path | None:
    text = _optional_text(value)
    return Path(text) if text else None


def _list_value(value: object) -> list:
    return value if isinstance(value, list) else []


def _int_value(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _optional_int_value(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _replace_with_retry(source: Path, target: Path) -> None:
    for attempt in range(5):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.02)


def _execution_sort_key(execution: PriceMonitoringFetchExecution) -> tuple[str, str, str, str]:
    return (
        execution.queued_at or "",
        execution.started_at or "",
        execution.completed_at or "",
        execution.execution_path.name,
    )


def _parse_iso(value: str | None) -> datetime | None:
    text = _optional_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _env_int(env_var: str, default: int, *, minimum: int, maximum: int | None = None) -> int:
    text = _optional_text(os.environ.get(env_var))
    if not text:
        return default
    try:
        value = int(text)
    except ValueError:
        return default
    if value < minimum:
        return default
    if maximum is not None:
        return min(value, maximum)
    return value
