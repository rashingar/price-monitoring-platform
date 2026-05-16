from __future__ import annotations

from dataclasses import dataclass, field, fields
from collections import deque
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

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
from ..services.authoring_service import (
    AuthoringStatus,
    authoring_service_error_from_exception,
    run_intro_text_authoring,
    run_seo_meta_authoring,
)
from ..services.models import RunStatus
from .models import JobRecord, JobStatus, JobType, is_terminal_job_status, utc_now_iso
from .store import JobStore


SCRAPER_ROOT = Path(__file__).resolve().parents[2]
MAX_WORKERS_ENV = "PRODUCT_FACTORY_MAX_JOB_WORKERS"
TERMINATE_TIMEOUT_ENV = "PRODUCT_FACTORY_JOB_TERMINATE_TIMEOUT_SECONDS"
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
    if record.job_type == JobType.AUTHORING_INTRO:
        return run_authoring_intro_job(record, log)
    if record.job_type == JobType.AUTHORING_SEO:
        return run_authoring_seo_job(record, log)
    if record.job_type == JobType.RENDER:
        return run_render_job(record, log)
    if record.job_type == JobType.PUBLISH:
        return run_publish_job(record, log)
    if record.job_type == JobType.FULL_PIPELINE:
        return run_full_pipeline_job(record, log)
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
        bestprice_status=record.payload.get("bestprice_status", 1),
        skroutz_status=record.payload.get("skroutz_status", 0),
        boxnow=record.payload.get("boxnow", 0),
        price=record.payload.get("price", 0),
        gallery_url=record.payload.get("gallery_url") or None,
        characteristics_url=record.payload.get("characteristics_url") or None,
        second_opencart_image_index=record.payload.get("second_opencart_image_index"),
        gallery_mode=record.payload.get("gallery_mode") or None,
    )
    gallery_extraction_url = request.gallery_url or request.url
    characteristics_extraction_url = request.characteristics_url or request.url
    log(f"Prepare product data extraction URL: {request.url}")
    log(f"Prepare gallery_url provided: {bool(request.gallery_url)}")
    log(f"Prepare gallery image extraction URL: {gallery_extraction_url}")
    log(f"Prepare characteristics_url provided: {bool(request.characteristics_url)}")
    log(f"Prepare characteristics/specifications extraction URL: {characteristics_extraction_url}")
    if request.gallery_url or request.characteristics_url:
        log("Prepare product data extraction remains on the main URL.")
    if request.characteristics_url:
        log("Prepare characteristics/specifications extraction uses the characteristics URL only.")
    if request.second_opencart_image_index is not None:
        log(f"Requested second OpenCart image index: {request.second_opencart_image_index}")
    if request.gallery_mode == "all":
        log("Prepare whole-gallery mode active.")
    log("Calling prepare service.")
    result = prepare_product_fn(request)
    _log_prepare_gallery_details(result, log)
    if "second_opencart_image_override_applied" in result.details:
        log(f"Second OpenCart image override applied: {bool(result.details['second_opencart_image_override_applied'])}")
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


def run_full_pipeline_job(
    record: JobRecord,
    log: LogCallback,
    *,
    prepare_product_fn: Callable[[PrepareRequest], ServiceResult] | None = None,
    run_intro_text_authoring_fn: Callable[..., AuthoringStatus] | None = None,
    run_seo_meta_authoring_fn: Callable[..., AuthoringStatus] | None = None,
    render_product_fn: Callable[[RenderRequest], ServiceResult] | None = None,
    publish_product_fn: Callable[[PublishRequest], ServiceResult] | None = None,
) -> JobRunResult:
    model = str(record.payload["model"])
    source_url = str(record.payload["source_url"])
    artifacts: dict[str, str] = {}

    log(f"Full pipeline source URL: {source_url}")
    log(
        "Full pipeline listing flags: "
        f"bestprice_enabled={bool(record.payload.get('bestprice_enabled', False))}, "
        f"skroutz_enabled={bool(record.payload.get('skroutz_enabled', False))}, "
        f"boxnow_enabled={bool(record.payload.get('boxnow_enabled', False))}"
    )

    prepare_record = _stage_record(
        record,
        JobType.PREPARE,
        _full_pipeline_prepare_payload(record.payload),
    )
    prepare_result = _run_full_pipeline_stage(
        "prepare",
        log,
        lambda: run_prepare_job(
            prepare_record,
            log,
            prepare_product_fn=prepare_product_fn,
        ),
    )
    _merge_stage_artifacts(artifacts, "prepare", prepare_result.artifacts)
    if prepare_result.status == JobStatus.FAILED:
        return _full_pipeline_failed_result("prepare", prepare_result, artifacts)

    intro_record = _stage_record(record, JobType.AUTHORING_INTRO, {"model": model})
    intro_result = _run_full_pipeline_stage(
        "intro text authoring",
        log,
        lambda: run_authoring_intro_job(
            intro_record,
            log,
            run_intro_text_authoring_fn=run_intro_text_authoring_fn,
        ),
    )
    _merge_stage_artifacts(artifacts, "intro_text_authoring", intro_result.artifacts)
    if intro_result.status == JobStatus.FAILED:
        return _full_pipeline_failed_result("intro text authoring", intro_result, artifacts)

    seo_record = _stage_record(record, JobType.AUTHORING_SEO, {"model": model})
    seo_result = _run_full_pipeline_stage(
        "SEO meta authoring",
        log,
        lambda: run_authoring_seo_job(
            seo_record,
            log,
            run_seo_meta_authoring_fn=run_seo_meta_authoring_fn,
        ),
    )
    _merge_stage_artifacts(artifacts, "seo_meta_authoring", seo_result.artifacts)
    if seo_result.status == JobStatus.FAILED:
        return _full_pipeline_failed_result("SEO meta authoring", seo_result, artifacts)

    render_record = _stage_record(record, JobType.RENDER, {"model": model})
    render_result = _run_full_pipeline_stage(
        "render",
        log,
        lambda: run_render_job(
            render_record,
            log,
            render_product_fn=render_product_fn,
        ),
    )
    _merge_stage_artifacts(artifacts, "render", render_result.artifacts)
    if render_result.status == JobStatus.FAILED:
        return _full_pipeline_failed_result("render", render_result, artifacts)

    publish_payload = {"model": model}
    if render_result.artifacts.get("published_csv_path"):
        publish_payload["current_job_product_file"] = render_result.artifacts["published_csv_path"]
    publish_record = _stage_record(record, JobType.PUBLISH, publish_payload)
    publish_result = _run_full_pipeline_stage(
        "publish",
        log,
        lambda: run_publish_job(
            publish_record,
            log,
            publish_product_fn=publish_product_fn,
        ),
    )
    _merge_stage_artifacts(artifacts, "publish", publish_result.artifacts)
    if publish_result.status == JobStatus.FAILED:
        return _full_pipeline_failed_result("publish", publish_result, artifacts)

    return JobRunResult(
        status=JobStatus.SUCCEEDED,
        message="Full pipeline job succeeded.",
        error=publish_result.error,
        error_code=publish_result.error_code,
        artifacts=artifacts,
    )


def run_authoring_intro_job(
    record: JobRecord,
    log: LogCallback,
    *,
    run_intro_text_authoring_fn: Callable[..., AuthoringStatus] | None = None,
) -> JobRunResult:
    run_intro_text_authoring_fn = run_intro_text_authoring_fn or run_intro_text_authoring
    model = str(record.payload["model"])
    retry = bool(record.payload.get("retry", False))
    log("Calling intro text authoring service.")
    try:
        status = run_intro_text_authoring_fn(model, retry=retry)
    except Exception as exc:
        service_error = authoring_service_error_from_exception(exc)
        log(f"Intro text authoring failed [{service_error.code}]: {service_error.message}")
        return _failed_authoring_result("Intro text authoring failed.", service_error)
    log("Intro text authoring succeeded.")
    return JobRunResult(
        status=JobStatus.SUCCEEDED,
        message="Intro text authoring succeeded.",
        artifacts=_authoring_artifacts(status, "intro_text"),
    )


def run_authoring_seo_job(
    record: JobRecord,
    log: LogCallback,
    *,
    run_seo_meta_authoring_fn: Callable[..., AuthoringStatus] | None = None,
) -> JobRunResult:
    run_seo_meta_authoring_fn = run_seo_meta_authoring_fn or run_seo_meta_authoring
    model = str(record.payload["model"])
    retry = bool(record.payload.get("retry", False))
    log("Calling SEO meta authoring service.")
    try:
        status = run_seo_meta_authoring_fn(model, retry=retry)
    except Exception as exc:
        service_error = authoring_service_error_from_exception(exc)
        log(f"SEO meta authoring failed [{service_error.code}]: {service_error.message}")
        return _failed_authoring_result("SEO meta authoring failed.", service_error)
    log("SEO meta authoring succeeded.")
    return JobRunResult(
        status=JobStatus.SUCCEEDED,
        message="SEO meta authoring succeeded.",
        artifacts=_authoring_artifacts(status, "seo_meta"),
    )


def _stage_record(
    parent: JobRecord,
    job_type: JobType,
    payload: dict[str, Any],
) -> JobRecord:
    return JobRecord(
        job_id=parent.job_id,
        job_type=job_type,
        status=parent.status,
        model=parent.model,
        payload=payload,
    )


def _full_pipeline_prepare_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": payload["model"],
        "url": payload["source_url"],
        "photos": payload.get("photos", 100),
        "sections": payload.get("sections", 20),
        "bestprice_status": int(bool(payload.get("bestprice_enabled", False))),
        "skroutz_status": int(bool(payload.get("skroutz_enabled", False))),
        "boxnow": int(bool(payload.get("boxnow_enabled", False))),
        "price": 0,
        "gallery_mode": payload.get("gallery_mode") or "all",
    }


def _log_prepare_gallery_details(result: ServiceResult, log: LogCallback) -> None:
    details = result.details
    if bool(details.get("gallery_whole_mode", False)):
        log("Prepare whole-gallery mode confirmed by artifacts.")
    before_count = details.get("gallery_extracted_before_source_filter_count")
    after_count = details.get("gallery_after_source_filter_count")
    if before_count is not None or after_count is not None:
        log(f"Prepare gallery source-filter counts: before={before_count}, after={after_count}")
    if bool(details.get("gallery_skroutz_skip_last_applied", False)):
        domain = str(details.get("gallery_source_filter_domain", "") or "")
        log(f"Prepare Skroutz skip-last gallery rule applied for source domain: {domain}")


def _run_full_pipeline_stage(
    stage: str,
    log: LogCallback,
    callback: Callable[[], JobRunResult],
) -> JobRunResult:
    log(f"Full pipeline stage {stage} starting.")
    try:
        result = callback()
    except ServiceError as exc:
        log(f"Full pipeline stage {stage} failed [{exc.code}]: {exc.message}")
        return JobRunResult(
            status=JobStatus.FAILED,
            message=f"Full pipeline failed during {stage}.",
            error=exc.message,
            error_code=exc.code,
        )
    except Exception as exc:
        log(f"Full pipeline stage {stage} failed: {exc}")
        return JobRunResult(
            status=JobStatus.FAILED,
            message=f"Full pipeline failed during {stage}.",
            error=str(exc),
        )
    if result.status == JobStatus.FAILED:
        log(f"Full pipeline stage {stage} failed: {result.error or result.message or 'stage failed'}")
    else:
        log(f"Full pipeline stage {stage} succeeded.")
    return result


def _merge_stage_artifacts(
    merged: dict[str, str],
    stage: str,
    stage_artifacts: dict[str, str],
) -> None:
    for name, path in stage_artifacts.items():
        merged.setdefault(name, path)
        merged[f"{stage}_{name}"] = path


def _full_pipeline_failed_result(
    stage: str,
    result: JobRunResult,
    artifacts: dict[str, str],
) -> JobRunResult:
    error = result.error or result.message or f"Full pipeline stage {stage} failed."
    return JobRunResult(
        status=JobStatus.FAILED,
        message=f"Full pipeline failed during {stage}.",
        error=f"Full pipeline stage {stage} failed: {error}",
        error_code=result.error_code,
        artifacts=artifacts,
    )


def _failed_authoring_result(message: str, exc: ServiceError) -> JobRunResult:
    detail_code = exc.details.get("error_code")
    error_code = str(detail_code) if detail_code else exc.code
    return JobRunResult(
        status=JobStatus.FAILED,
        message=message,
        error=exc.message,
        error_code=error_code,
        artifacts=_authoring_error_artifacts(exc),
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


def _authoring_artifacts(status: AuthoringStatus, stage: str) -> dict[str, str]:
    llm_dir = Path(status.llm_dir)
    paths: dict[str, Path | None] = {
        "llm_dir": llm_dir,
        "llm_task_manifest_path": llm_dir / "task_manifest.json",
    }
    if stage == "intro_text":
        output_path = Path(status.intro_text.output_path)
        paths.update(
            {
                "intro_text_output_path": output_path,
                "intro_text_prompt_path": llm_dir / "intro_text.prompt.txt",
                "intro_text_context_path": llm_dir / "intro_text.context.json",
                "intro_text_trace_path": Path(status.intro_text.trace_path) if status.intro_text.trace_path else None,
                "intro_text_preview_path": _write_intro_preview(output_path),
            }
        )
    if stage == "seo_meta":
        output_path = Path(status.seo_meta.output_path)
        paths.update(
            {
                "seo_meta_output_path": output_path,
                "seo_meta_prompt_path": llm_dir / "seo_meta.prompt.txt",
                "seo_meta_context_path": llm_dir / "seo_meta.context.json",
                "seo_meta_trace_path": llm_dir / "seo_meta.retry_trace.json",
                "seo_meta_preview_path": _write_seo_preview(output_path),
            }
        )
    return {name: str(path) for name, path in paths.items() if path is not None}


def _authoring_error_artifacts(exc: ServiceError) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for name in ("output_path", "trace_path"):
        value = exc.details.get(name)
        if value:
            artifacts[name] = str(value)
    return artifacts


def _write_intro_preview(output_path: Path) -> Path | None:
    if not output_path.exists():
        return None
    preview_path = output_path.with_name("intro_text.preview.html")
    preview_path.write_text(output_path.read_text(encoding="utf-8"), encoding="utf-8")
    return preview_path


def _write_seo_preview(output_path: Path) -> Path | None:
    if not output_path.exists():
        return None
    preview_path = output_path.with_name("seo_meta.preview.json")
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        preview_path.write_text(output_path.read_text(encoding="utf-8"), encoding="utf-8")
        return preview_path
    product = payload.get("product", {}) if isinstance(payload, dict) else {}
    preview = {
        "meta_title": product.get("meta_title") if isinstance(product, dict) else None,
        "meta_description": product.get("meta_description") if isinstance(product, dict) else None,
        "meta_keywords": product.get("meta_keywords") if isinstance(product, dict) else None,
        "seo_keyword": product.get("seo_keyword") if isinstance(product, dict) else None,
    }
    preview_path.write_text(json.dumps(preview, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return preview_path


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
                name=f"product-factory-api-job-runner-{index}",
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
            name=f"product-factory-job-{job_id}-{label}-reader",
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
            "product_factory.jobs.run_product_factory_job",
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
