from __future__ import annotations

from dataclasses import dataclass, field, fields
from collections import deque
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable

from ..services import (
    PrepareRequest,
    PublishRequest,
    RenderRequest,
    ServiceError,
    ServiceResult,
    prepare_product,
    publish_product,
    render_product,
)
from ..services.models import RunStatus
from .job_models import JobRecord, JobStatus, JobType, is_terminal_job_status, utc_now_iso
from .job_store import JobStore


SCRAPER_ROOT = Path(__file__).resolve().parents[2]
MAX_WORKERS_ENV = "PRODUCT_AGENT_MAX_JOB_WORKERS"
TERMINATE_TIMEOUT_ENV = "PRODUCT_AGENT_JOB_TERMINATE_TIMEOUT_SECONDS"
DEFAULT_TERMINATE_TIMEOUT_SECONDS = 30


LogCallback = Callable[[str], None]
JobRunnerCallback = Callable[[JobRecord, LogCallback], "JobRunResult | None"]


@dataclass(slots=True)
class JobRunResult:
    status: JobStatus = JobStatus.SUCCEEDED
    message: str | None = None
    error: str | None = None
    error_code: str | None = None
    artifacts: dict[str, str] = field(default_factory=dict)


def stub_runner_callback(record: JobRecord, log: LogCallback) -> None:
    log(f"Stub runner accepted {record.job_type.value} job; pipeline services were not invoked.")


def service_runner_callback(record: JobRecord, log: LogCallback) -> JobRunResult | None:
    if record.job_type == JobType.PREPARE:
        return run_prepare_job(record, log)
    if record.job_type == JobType.RENDER:
        return run_render_job(record, log)
    if record.job_type == JobType.PUBLISH:
        return run_publish_job(record, log)
    return stub_runner_callback(record, log)


def run_prepare_job(
    record: JobRecord,
    log: LogCallback,
    *,
    prepare_product_fn: Callable[[PrepareRequest], ServiceResult] | None = None,
) -> JobRunResult:
    prepare_product_fn = prepare_product_fn or prepare_product
    request = PrepareRequest(
        model=str(record.payload["model"]),
        url=str(record.payload["url"]),
        photos=record.payload.get("photos", 1),
        sections=record.payload.get("sections", 0),
        skroutz_status=record.payload.get("skroutz_status", 0),
        boxnow=record.payload.get("boxnow", 0),
        price=record.payload.get("price", 0),
    )
    log("Calling prepare service.")
    result = prepare_product_fn(request)
    return _job_result_from_service_result(
        "prepare",
        result,
        log,
        success_message="Prepare job succeeded.",
        failure_message="Prepare job failed.",
    )


def run_render_job(
    record: JobRecord,
    log: LogCallback,
    *,
    render_product_fn: Callable[[RenderRequest], ServiceResult] | None = None,
) -> JobRunResult:
    render_product_fn = render_product_fn or render_product
    request = RenderRequest(model=str(record.payload["model"]))
    log("Calling render service.")
    result = render_product_fn(request)
    return _job_result_from_service_result(
        "render",
        result,
        log,
        success_message="Render job succeeded.",
        failure_message="Render job failed.",
    )


def run_publish_job(
    record: JobRecord,
    log: LogCallback,
    *,
    publish_product_fn: Callable[[PublishRequest], ServiceResult] | None = None,
) -> JobRunResult:
    publish_product_fn = publish_product_fn or publish_product
    current_job_product_file = record.payload.get("current_job_product_file")
    request = PublishRequest(
        model=str(record.payload["model"]),
        current_job_product_file=Path(str(current_job_product_file)) if current_job_product_file else None,
    )
    log("Calling publish service.")
    result = publish_product_fn(request)
    return _job_result_from_service_result(
        "publish",
        result,
        log,
        success_message="Publish job succeeded.",
        failure_message="Publish job failed.",
    )


def _job_result_from_service_result(
    operation: str,
    result: ServiceResult,
    log: LogCallback,
    *,
    success_message: str,
    failure_message: str,
) -> JobRunResult:
    log(f"{operation.capitalize()} service returned status: {result.run.status.value}")
    for warning in result.run.warnings:
        log(f"{operation.capitalize()} warning: {warning}")
    if result.run.error_code:
        log(f"{operation.capitalize()} service error code: {result.run.error_code}")
    if result.run.error_detail:
        log(f"{operation.capitalize()} service error detail: {result.run.error_detail}")

    artifacts = _artifact_paths(result)
    if result.run.status == RunStatus.FAILED:
        return JobRunResult(
            status=JobStatus.FAILED,
            message=failure_message,
            error=result.run.error_detail or f"{operation.capitalize()} service returned failed status.",
            error_code=result.run.error_code,
            artifacts=artifacts,
        )
    return JobRunResult(
        status=JobStatus.SUCCEEDED,
        message=success_message,
        error=result.run.error_detail,
        error_code=result.run.error_code,
        artifacts=artifacts,
    )


def _artifact_paths(result: ServiceResult) -> dict[str, str]:
    paths: dict[str, str] = {}
    for field in fields(result.artifacts):
        value = getattr(result.artifacts, field.name)
        if value is not None:
            paths[field.name] = str(value)
    for name, value in result.details.items():
        if name.endswith("_path") and value is not None:
            paths[name] = str(value)
    return paths


def configured_max_workers(env: MappingLike | None = None) -> int:
    return _positive_int_from_env(MAX_WORKERS_ENV, default=1, env=env)


def configured_terminate_timeout_seconds(env: MappingLike | None = None) -> int:
    return _positive_int_from_env(
        TERMINATE_TIMEOUT_ENV,
        default=DEFAULT_TERMINATE_TIMEOUT_SECONDS,
        env=env,
    )


class MappingLike:
    def get(self, key: str, default: object | None = None) -> object | None: ...


def _positive_int_from_env(name: str, *, default: int, env: MappingLike | None = None) -> int:
    source = os.environ if env is None else env
    value = source.get(name)
    try:
        parsed = int(str(value).strip()) if value is not None and str(value).strip() else default
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 1 else default


class SequentialJobRunner:
    def __init__(
        self,
        store: JobStore,
        callback: JobRunnerCallback | None = None,
        *,
        command_builder: Callable[[JobRecord], list[str]] | None = None,
        max_workers: int | None = None,
        terminate_timeout_seconds: int | None = None,
    ) -> None:
        self._store = store
        self._callback = callback
        self._command_builder = command_builder or self._default_command
        self._max_workers = max(1, max_workers or configured_max_workers())
        self._terminate_timeout_seconds = max(
            1,
            terminate_timeout_seconds or configured_terminate_timeout_seconds(),
        )
        self._queue: deque[str] = deque()
        self._condition = threading.Condition(threading.RLock())
        self._threads: list[threading.Thread] = []
        self._active_job_ids: set[str] = set()
        self._active_models: set[str] = set()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._reader_threads: dict[str, list[threading.Thread]] = {}
        self._stopping = False

    @property
    def active_job_id(self) -> str | None:
        with self._condition:
            return next(iter(self._active_job_ids), None)

    def enqueue(self, job_id: str) -> None:
        with self._condition:
            if self._stopping:
                raise RuntimeError("Job runner is stopping.")
            self._ensure_workers_started_locked()
            self._queue.append(job_id)
            self._condition.notify_all()

    def stop_job(self, job_id: str, *, reason: str | None = None) -> JobRecord:
        record = self._store.get_job(job_id)
        if record is None:
            raise KeyError(job_id)
        if is_terminal_job_status(record.status):
            return record
        if record.status == JobStatus.QUEUED:
            record = self._store.mark_cancelled(job_id, reason=reason)
            self._remove_queued_job(job_id)
            self._store.append_log(job_id, "Stop requested by operator before job started.")
            return record
        if record.status == JobStatus.RUNNING:
            with self._condition:
                process = self._processes.get(job_id)
                is_active_job = job_id in self._active_job_ids
            if process is None:
                if is_active_job:
                    record = self._store.mark_cancelled(job_id, reason=reason)
                    self._store.update_process_metadata(job_id, termination_mode="graceful")
                    self._store.append_log(job_id, "Stop requested by operator before subprocess started.")
                    return record
                record = self._store.mark_cancelled(job_id, reason=reason)
                self._store.update_process_metadata(job_id, termination_mode="stale_metadata")
                self._store.append_log(job_id, "Stop requested for stale running job record.")
                return record
            return self._terminate_running_job(job_id, process, reason=reason)
        return record

    def wait_until_idle(self, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        with self._condition:
            while not self._is_idle_locked():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def stop(self, timeout: float = 5.0) -> None:
        with self._condition:
            self._stopping = True
            self._condition.notify_all()
            threads = list(self._threads)
        deadline = time.monotonic() + timeout
        for thread in threads:
            remaining = max(0.0, deadline - time.monotonic())
            thread.join(remaining)

    def _ensure_workers_started_locked(self) -> None:
        self._threads = [thread for thread in self._threads if thread.is_alive()]
        while len(self._threads) < self._max_workers:
            index = len(self._threads) + 1
            thread = threading.Thread(
                target=self._run_loop,
                name=f"product-agent-api-job-runner-{index}",
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()

    def _run_loop(self) -> None:
        while True:
            with self._condition:
                job_id = self._take_next_job_locked()
                if job_id is None:
                    return
            try:
                self._run_job(job_id)
            finally:
                self._finish_active_job(job_id)

    def _take_next_job_locked(self) -> str | None:
        while True:
            if self._stopping:
                return None
            for index, job_id in enumerate(self._queue):
                record = self._store.get_job(job_id)
                if record is None or record.status != JobStatus.QUEUED:
                    del self._queue[index]
                    break
                normalized_model = _normalized_model(record.model)
                if normalized_model and normalized_model in self._active_models:
                    continue
                del self._queue[index]
                self._active_job_ids.add(job_id)
                if normalized_model:
                    self._active_models.add(normalized_model)
                self._condition.notify_all()
                return job_id
            else:
                self._condition.wait()

    def _finish_active_job(self, job_id: str) -> None:
        with self._condition:
            self._processes.pop(job_id, None)
            self._reader_threads.pop(job_id, None)
            self._active_job_ids.discard(job_id)
            record = self._store.get_job(job_id)
            if record is not None:
                normalized_model = _normalized_model(record.model)
                if normalized_model:
                    self._active_models.discard(normalized_model)
            self._condition.notify_all()

    def _run_job(self, job_id: str) -> None:
        record = self._store.get_job(job_id)
        if record is None or record.status != JobStatus.QUEUED:
            return
        record = self._store.mark_running(job_id, message="Job started.")
        if record.status != JobStatus.RUNNING:
            return

        if self._callback is not None:
            self._run_callback_job(record)
            return

        self._store.append_log(job_id, f"Started {record.job_type.value} job subprocess.")
        command = self._command_builder(record)
        stdout_path = self._store.jobs_dir / f"{job_id}.stdout.log"
        stderr_path = self._store.jobs_dir / f"{job_id}.stderr.log"
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.touch(exist_ok=True)
        stderr_path.touch(exist_ok=True)

        popen_kwargs: dict[str, object] = {
            "cwd": str(SCRAPER_ROOT),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True

        try:
            process = subprocess.Popen(command, **popen_kwargs)
        except Exception as exc:
            self._store.append_log(job_id, f"Failed to launch job subprocess: {exc}")
            if not self._is_terminal(job_id):
                self._store.mark_failed(job_id, str(exc), message="Job failed.")
            return

        process_group_id = _process_group_id(process.pid)
        self._store.update_process_metadata(
            job_id,
            parent_process_id=os.getpid(),
            process_id=process.pid,
            process_group_id=process_group_id,
            command=command,
            termination_mode="none",
            stdout_log_path=str(stdout_path),
            stderr_log_path=str(stderr_path),
        )
        with self._condition:
            self._processes[job_id] = process
            self._reader_threads[job_id] = [
                self._start_stream_reader(job_id, process.stdout, stdout_path, "stdout"),
                self._start_stream_reader(job_id, process.stderr, stderr_path, "stderr"),
            ]
            self._condition.notify_all()

        exit_code = process.wait()
        self._join_reader_threads(job_id)
        current = self._store.get_job(job_id)
        if current is None:
            return
        if is_terminal_job_status(current.status):
            if current.status in {JobStatus.CANCELLED, JobStatus.KILLED}:
                self._store.append_log(job_id, f"Job subprocess exited with code {exit_code}; preserving {current.status.value}.")
                return
            self._store.set_terminal_exit_metadata(
                job_id,
                exit_code=exit_code,
                termination_mode="process_exited",
            )
            self._store.append_log(job_id, f"Job subprocess exited with code {exit_code}; preserving {current.status.value}.")
            return
        self._store.set_terminal_exit_metadata(
            job_id,
            exit_code=exit_code,
            termination_mode="process_exited",
        )
        current = self._store.get_job(job_id)
        if current is None:
            return
        if current.terminate_sent_at is not None:
            self._store.append_log(
                job_id,
                "Job subprocess exited after terminate request; awaiting cancellation reconciliation.",
            )
            return
        if exit_code == 0:
            self._store.append_log(job_id, "Job subprocess exited successfully without terminal metadata; marking succeeded.")
            self._store.mark_succeeded(job_id, message="Job succeeded.")
            return
        self._store.append_log(job_id, f"Job subprocess exited with code {exit_code}; marking failed.")
        self._store.mark_failed(job_id, f"Job subprocess exited with code {exit_code}.", message="Job failed.")

    def _run_callback_job(self, record: JobRecord) -> None:
        job_id = record.job_id

        def log(line: str) -> None:
            self._store.append_log(job_id, line)

        def preserve_cancelled_or_killed_if_requested() -> bool:
            current_record = self._store.get_job(job_id)
            if current_record is not None and current_record.status in {JobStatus.CANCELLED, JobStatus.KILLED}:
                log(f"Job finished after stop request; preserving {current_record.status.value} status.")
                return True
            return False

        try:
            log(f"Started {record.job_type.value} job.")
            result = self._callback(record, log) or JobRunResult()
            if preserve_cancelled_or_killed_if_requested():
                return
            if result.artifacts:
                self._store.update_artifacts(job_id, result.artifacts)
        except ServiceError as exc:
            log(f"Failed {record.job_type.value} job [{exc.code}]: {exc.message}")
            if preserve_cancelled_or_killed_if_requested():
                return
            self._store.mark_failed(job_id, exc.message, message="Job failed.", error_code=exc.code)
        except Exception as exc:
            log(f"Failed {record.job_type.value} job: {exc}")
            if preserve_cancelled_or_killed_if_requested():
                return
            self._store.mark_failed(job_id, str(exc), message="Job failed.")
        else:
            if result.status == JobStatus.FAILED:
                log(f"Failed {record.job_type.value} job: {result.error}")
                if preserve_cancelled_or_killed_if_requested():
                    return
                self._store.mark_failed(
                    job_id,
                    result.error or "Job failed.",
                    message=result.message or "Job failed.",
                    error_code=result.error_code,
                )
                return
            log(f"Finished {record.job_type.value} job.")
            if preserve_cancelled_or_killed_if_requested():
                return
            self._store.mark_succeeded(
                job_id,
                message=result.message or "Job succeeded.",
                error=result.error,
                error_code=result.error_code,
            )

    def _terminate_running_job(
        self,
        job_id: str,
        process: subprocess.Popen[str],
        *,
        reason: str | None,
    ) -> JobRecord:
        current = self._store.get_job(job_id)
        if current is None:
            raise KeyError(job_id)
        if is_terminal_job_status(current.status):
            return current

        terminate_sent_at = utc_now_iso()
        self._store.update_process_metadata(
            job_id,
            terminate_sent_at=terminate_sent_at,
            termination_mode="graceful",
        )
        self._store.append_log(job_id, "Stop requested by operator. Sending graceful terminate to job process.")
        _terminate_process_tree(process)
        try:
            exit_code = process.wait(timeout=self._terminate_timeout_seconds)
        except subprocess.TimeoutExpired:
            before_kill = self._store.get_job(job_id)
            if before_kill is not None and is_terminal_job_status(before_kill.status):
                return before_kill
            kill_sent_at = utc_now_iso()
            self._store.update_process_metadata(job_id, kill_sent_at=kill_sent_at)
            self._store.append_log(job_id, "Graceful terminate timed out. Force killing job process tree.")
            _kill_process_tree(process)
            exit_code = process.wait()
            self._join_reader_threads(job_id)
            if not self._is_terminal(job_id):
                killed = self._store.mark_killed(
                    job_id,
                    reason="Process did not exit before terminate timeout.",
                )
                self._store.update_process_metadata(
                    job_id,
                    exit_code=exit_code,
                    kill_sent_at=kill_sent_at,
                    killed_at=killed.killed_at,
                    killed_reason=killed.killed_reason,
                    termination_mode="force_kill",
                )
                self._store.append_log(job_id, "Job process tree was force killed.")
                return self._store.get_job(job_id) or killed
            return self._store.get_job(job_id) or current

        self._join_reader_threads(job_id)
        self._store.set_terminal_exit_metadata(
            job_id,
            exit_code=exit_code,
            termination_mode="graceful",
        )
        after_exit = self._store.get_job(job_id)
        if after_exit is not None and is_terminal_job_status(after_exit.status):
            return after_exit
        cancelled = self._store.mark_cancelled(job_id, reason=reason)
        self._store.update_process_metadata(job_id, exit_code=exit_code, termination_mode="graceful")
        self._store.append_log(job_id, "Job process exited after graceful terminate; marking cancelled.")
        return cancelled

    def _start_stream_reader(
        self,
        job_id: str,
        stream: object,
        path: Path,
        label: str,
    ) -> threading.Thread:
        def read_stream() -> None:
            if stream is None:
                return
            with path.open("a", encoding="utf-8") as handle:
                for line in stream:  # type: ignore[union-attr]
                    text = str(line).rstrip()
                    handle.write(text + "\n")
                    self._store.append_log(job_id, f"{label}: {text}")

        thread = threading.Thread(
            target=read_stream,
            name=f"product-agent-job-{job_id}-{label}-reader",
            daemon=True,
        )
        thread.start()
        return thread

    def _join_reader_threads(self, job_id: str) -> None:
        with self._condition:
            threads = list(self._reader_threads.get(job_id, []))
        for thread in threads:
            thread.join(timeout=1.0)

    def _remove_queued_job(self, job_id: str) -> None:
        with self._condition:
            self._queue = deque(queued_job_id for queued_job_id in self._queue if queued_job_id != job_id)
            self._condition.notify_all()

    def _default_command(self, record: JobRecord) -> list[str]:
        return [
            sys.executable,
            "-m",
            "product_factory.jobs.run_product_agent_job",
            "--job-id",
            record.job_id,
            "--job-root",
            str(self._store.jobs_dir),
        ]

    def _is_terminal(self, job_id: str) -> bool:
        current = self._store.get_job(job_id)
        return current is not None and is_terminal_job_status(current.status)

    def _is_idle_locked(self) -> bool:
        return not self._queue and not self._active_job_ids


def _normalized_model(model: str) -> str:
    return model.strip().lower()


def _process_group_id(pid: int) -> int | None:
    if os.name == "nt":
        return pid
    try:
        return os.getpgid(pid)
    except OSError:
        return None


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.terminate()
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
