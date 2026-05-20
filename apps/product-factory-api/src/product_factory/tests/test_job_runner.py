from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from product_factory.jobs import runner as job_runner
from product_factory.jobs.models import JobRecord, JobStatus, JobType
from product_factory.jobs.runner import (
    LogCallback,
    SequentialJobRunner,
    run_full_pipeline_job,
)
from product_factory.jobs.store import JobStore
from product_factory.services.authoring_service import (
    AuthoringStatus,
    IntroTextTaskStatus,
    SeoMetaTaskStatus,
)
from product_factory.services import (
    PrepareRequest,
    PublishRequest,
    RenderRequest,
    RunArtifacts,
    RunMetadata,
    RunStatus,
    RunType,
    ServiceError,
    ServiceErrorCode,
    ServiceResult,
)


def test_job_runner_env_defaults_and_invalid_values(monkeypatch) -> None:
    monkeypatch.delenv("PRODUCT_FACTORY_MAX_JOB_WORKERS", raising=False)
    monkeypatch.delenv("PRODUCT_FACTORY_JOB_TERMINATE_TIMEOUT_SECONDS", raising=False)
    assert job_runner.configured_max_workers() == 1
    assert job_runner.configured_terminate_timeout_seconds() == 30

    monkeypatch.setenv("PRODUCT_FACTORY_MAX_JOB_WORKERS", "0")
    monkeypatch.setenv("PRODUCT_FACTORY_JOB_TERMINATE_TIMEOUT_SECONDS", "bad")
    assert job_runner.configured_max_workers() == 1
    assert job_runner.configured_terminate_timeout_seconds() == 30

    monkeypatch.setenv("PRODUCT_FACTORY_MAX_JOB_WORKERS", "3")
    monkeypatch.setenv("PRODUCT_FACTORY_JOB_TERMINATE_TIMEOUT_SECONDS", "2")
    assert job_runner.configured_max_workers() == 3
    assert job_runner.configured_terminate_timeout_seconds() == 2


def test_runner_executes_jobs_sequentially(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    events: list[tuple[str, str]] = []
    active_count = 0
    max_active_count = 0
    lock = threading.Lock()

    def callback(record: JobRecord, log: LogCallback) -> None:
        nonlocal active_count, max_active_count
        with lock:
            active_count += 1
            max_active_count = max(max_active_count, active_count)
            events.append(("start", record.job_id))
        log(f"callback {record.job_id}")
        time.sleep(0.02)
        with lock:
            events.append(("end", record.job_id))
            active_count -= 1

    runner = SequentialJobRunner(store, callback)
    first = store.enqueue(JobType.PREPARE, {"model": "111111"}, job_id="job-1")
    second = store.enqueue(JobType.RENDER, {"model": "222222"}, job_id="job-2")

    try:
        runner.enqueue(first.job_id)
        runner.enqueue(second.job_id)

        assert runner.wait_until_idle(timeout=2.0)
    finally:
        runner.stop()

    assert max_active_count == 1
    assert events == [
        ("start", "job-1"),
        ("end", "job-1"),
        ("start", "job-2"),
        ("end", "job-2"),
    ]
    assert store.get_job(first.job_id).status == JobStatus.SUCCEEDED
    assert store.get_job(second.job_id).status == JobStatus.SUCCEEDED
    assert "callback job-1" in store.read_logs(first.job_id)
    assert "callback job-2" in store.read_logs(second.job_id)


def test_runner_marks_job_failed_when_callback_raises(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")

    def callback(record: JobRecord, log: LogCallback) -> None:
        log(f"failing {record.job_id}")
        raise RuntimeError("boom")

    runner = SequentialJobRunner(store, callback)
    record = store.enqueue(JobType.PUBLISH, {"model": "233541"}, job_id="job-1")

    try:
        runner.enqueue(record.job_id)

        assert runner.wait_until_idle(timeout=2.0)
    finally:
        runner.stop()

    failed = store.get_job(record.job_id)
    logs = store.read_logs(record.job_id)
    assert failed.status == JobStatus.FAILED
    assert failed.error == "boom"
    assert "failing job-1" in logs
    assert "Failed publish job: boom" in logs


def test_runner_stop_active_job_preserves_cancelled_after_callback_finishes(
    tmp_path: Path,
) -> None:
    store = JobStore(tmp_path / "jobs")
    callback_started = threading.Event()
    release_callback = threading.Event()

    def callback(record: JobRecord, log: LogCallback) -> None:
        log(f"blocking {record.job_id}")
        callback_started.set()
        assert release_callback.wait(timeout=2.0)

    runner = SequentialJobRunner(store, callback)
    record = store.enqueue(JobType.RENDER, {"model": "233541"}, job_id="job-1")

    try:
        runner.enqueue(record.job_id)
        assert callback_started.wait(timeout=2.0)
        stopped = runner.stop_job(record.job_id, reason="operator stop")
        release_callback.set()
        assert runner.wait_until_idle(timeout=2.0)
    finally:
        release_callback.set()
        runner.stop()

    final = store.get_job(record.job_id)
    logs = store.read_logs(record.job_id)
    assert stopped.status == JobStatus.CANCELLED
    assert final.status == JobStatus.CANCELLED
    assert final.error == "operator stop"
    assert final.error_code == "JOB_STOPPED"
    assert "Stop requested by operator before subprocess started." in logs
    assert "Job finished after stop request; preserving cancelled status." in logs


def test_runner_stop_terminal_jobs_is_idempotent_and_does_not_append_logs(
    tmp_path: Path,
) -> None:
    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(store, job_runner.service_runner_callback)
    succeeded = store.enqueue(JobType.PREPARE, {"model": "111111"}, job_id="succeeded")
    failed = store.enqueue(JobType.RENDER, {"model": "222222"}, job_id="failed")
    cancelled = store.enqueue(JobType.PUBLISH, {"model": "333333"}, job_id="cancelled")
    store.mark_succeeded(succeeded.job_id, message="done")
    store.mark_failed(failed.job_id, "boom", message="failed")
    store.mark_cancelled(cancelled.job_id, reason="already stopped")
    before_records = {
        job_id: store.get_job(job_id).to_dict()
        for job_id in ("succeeded", "failed", "cancelled")
    }
    before_logs = {
        job_id: store.read_logs(job_id)
        for job_id in ("succeeded", "failed", "cancelled")
    }

    try:
        for job_id in ("succeeded", "failed", "cancelled"):
            runner.stop_job(job_id, reason="second stop")
    finally:
        runner.stop()

    assert {
        job_id: store.get_job(job_id).to_dict()
        for job_id in ("succeeded", "failed", "cancelled")
    } == before_records
    assert {
        job_id: store.read_logs(job_id)
        for job_id in ("succeeded", "failed", "cancelled")
    } == before_logs


def test_default_runner_calls_prepare_service_and_captures_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    store = JobStore(tmp_path / "jobs")
    calls: list[PrepareRequest] = []

    def fake_prepare_product(request: PrepareRequest) -> ServiceResult:
        calls.append(request)
        return ServiceResult(
            run=RunMetadata(
                model=request.model,
                run_type=RunType.PREPARE,
                status=RunStatus.COMPLETED,
                warnings=["prepare warning"],
                error_code=ServiceErrorCode.MISSING_ARTIFACT.value,
                error_detail="metadata missing",
            ),
            artifacts=RunArtifacts(
                scrape_dir=tmp_path / "work" / request.model / "scrape",
                llm_dir=tmp_path / "work" / request.model / "llm",
                source_json_path=tmp_path
                / "work"
                / request.model
                / "scrape"
                / f"{request.model}.source.json",
                llm_task_manifest_path=tmp_path
                / "work"
                / request.model
                / "llm"
                / "task_manifest.json",
                metadata_path=tmp_path / "work" / request.model / "prepare.run.json",
            ),
            details={
                "gallery_whole_mode": True,
                "gallery_extracted_before_source_filter_count": 4,
                "gallery_after_source_filter_count": 3,
                "gallery_skroutz_skip_last_applied": True,
                "gallery_source_filter_domain": "skroutz.gr",
            },
        )

    monkeypatch.setattr(job_runner, "prepare_product", fake_prepare_product)
    runner = SequentialJobRunner(store, job_runner.service_runner_callback)
    record = store.enqueue(
        JobType.PREPARE,
        {
            "model": "233541",
            "url": "https://www.electronet.gr/example",
            "photos": 6,
            "sections": 2,
            "skroutz_status": 1,
            "boxnow": 0,
            "price": "2099",
            "gallery_url": "https://www.electronet.gr/gallery",
            "characteristics_url": "https://www.electronet.gr/specs",
            "second_opencart_image_index": 4,
        },
        job_id="job-1",
    )

    try:
        runner.enqueue(record.job_id)

        assert runner.wait_until_idle(timeout=2.0)
    finally:
        runner.stop()

    loaded = store.get_job(record.job_id)
    logs = store.read_logs(record.job_id)
    assert calls == [
        PrepareRequest(
            model="233541",
            url="https://www.electronet.gr/example",
            photos=6,
            sections=2,
            skroutz_status=1,
            boxnow=0,
            price="2099",
            gallery_url="https://www.electronet.gr/gallery",
            characteristics_url="https://www.electronet.gr/specs",
            second_opencart_image_index=4,
        )
    ]
    assert loaded.status == JobStatus.SUCCEEDED
    assert loaded.message == "Prepare job succeeded."
    assert loaded.error == "metadata missing"
    assert loaded.error_code == ServiceErrorCode.MISSING_ARTIFACT.value
    assert loaded.artifacts == {
        "scrape_dir": str(tmp_path / "work" / "233541" / "scrape"),
        "llm_dir": str(tmp_path / "work" / "233541" / "llm"),
        "source_json_path": str(
            tmp_path / "work" / "233541" / "scrape" / "233541.source.json"
        ),
        "llm_task_manifest_path": str(
            tmp_path / "work" / "233541" / "llm" / "task_manifest.json"
        ),
        "metadata_path": str(tmp_path / "work" / "233541" / "prepare.run.json"),
    }
    assert "Calling prepare service." in logs
    assert "Prepare gallery_url provided: True" in logs
    assert (
        "Prepare gallery image extraction URL: https://www.electronet.gr/gallery"
        in logs
    )
    assert "Prepare characteristics_url provided: True" in logs
    assert (
        "Prepare characteristics/specifications extraction URL: https://www.electronet.gr/specs"
        in logs
    )
    assert "Requested second OpenCart image index: 4" in logs
    assert "Prepare service returned status: completed" in logs
    assert "Prepare warning: prepare warning" in logs
    assert "Prepare whole-gallery mode confirmed by artifacts." in logs
    assert "Prepare gallery source-filter counts: before=4, after=3" in logs
    assert (
        "Prepare Skroutz skip-last gallery rule applied for source domain: skroutz.gr"
        in logs
    )


def test_default_runner_marks_prepare_service_error_failed(
    tmp_path: Path, monkeypatch
) -> None:
    store = JobStore(tmp_path / "jobs")

    def fake_prepare_product(_request: PrepareRequest) -> ServiceResult:
        raise ServiceError(ServiceErrorCode.PARSE_FAILURE.value, "bad source")

    monkeypatch.setattr(job_runner, "prepare_product", fake_prepare_product)
    runner = SequentialJobRunner(store, job_runner.service_runner_callback)
    record = store.enqueue(
        JobType.PREPARE,
        {"model": "233541", "url": "https://www.electronet.gr/example"},
        job_id="job-1",
    )

    try:
        runner.enqueue(record.job_id)

        assert runner.wait_until_idle(timeout=2.0)
    finally:
        runner.stop()

    failed = store.get_job(record.job_id)
    logs = store.read_logs(record.job_id)
    assert failed.status == JobStatus.FAILED
    assert failed.error == "bad source"
    assert failed.error_code == ServiceErrorCode.PARSE_FAILURE.value
    assert "Calling prepare service." in logs
    assert "Failed prepare job [parse_failure]: bad source" in logs


def test_default_runner_calls_render_service_and_captures_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    store = JobStore(tmp_path / "jobs")
    calls: list[RenderRequest] = []

    def fake_render_product(request: RenderRequest) -> ServiceResult:
        calls.append(request)
        return ServiceResult(
            run=RunMetadata(
                model=request.model,
                run_type=RunType.RENDER,
                status=RunStatus.COMPLETED,
            ),
            artifacts=RunArtifacts(
                candidate_dir=tmp_path / "work" / request.model / "candidate",
                candidate_csv_path=tmp_path
                / "work"
                / request.model
                / "candidate"
                / f"{request.model}.csv",
                published_csv_path=tmp_path / "products" / f"{request.model}.csv",
                validation_report_path=tmp_path
                / "work"
                / request.model
                / "candidate"
                / f"{request.model}.validation.json",
                metadata_path=tmp_path / "work" / request.model / "render.run.json",
            ),
            details={"validation_ok": True, "published": True},
        )

    monkeypatch.setattr(job_runner, "render_product", fake_render_product)
    runner = SequentialJobRunner(store, job_runner.service_runner_callback)
    record = store.enqueue(JobType.RENDER, {"model": "233541"}, job_id="job-1")

    try:
        runner.enqueue(record.job_id)

        assert runner.wait_until_idle(timeout=2.0)
    finally:
        runner.stop()

    loaded = store.get_job(record.job_id)
    logs = store.read_logs(record.job_id)
    assert calls == [RenderRequest(model="233541")]
    assert loaded.status == JobStatus.SUCCEEDED
    assert loaded.message == "Render job succeeded."
    assert loaded.artifacts == {
        "candidate_dir": str(tmp_path / "work" / "233541" / "candidate"),
        "candidate_csv_path": str(
            tmp_path / "work" / "233541" / "candidate" / "233541.csv"
        ),
        "published_csv_path": str(tmp_path / "products" / "233541.csv"),
        "validation_report_path": str(
            tmp_path / "work" / "233541" / "candidate" / "233541.validation.json"
        ),
        "metadata_path": str(tmp_path / "work" / "233541" / "render.run.json"),
    }
    assert "Calling render service." in logs
    assert "Render service returned status: completed" in logs


def test_default_runner_marks_render_service_failed_status_failed(
    tmp_path: Path, monkeypatch
) -> None:
    store = JobStore(tmp_path / "jobs")

    def fake_render_product(request: RenderRequest) -> ServiceResult:
        return ServiceResult(
            run=RunMetadata(
                model=request.model,
                run_type=RunType.RENDER,
                status=RunStatus.FAILED,
                error_code=ServiceErrorCode.VALIDATION_FAILURE.value,
                error_detail="Candidate validation failed",
            ),
            artifacts=RunArtifacts(
                validation_report_path=tmp_path
                / "work"
                / request.model
                / "candidate"
                / f"{request.model}.validation.json",
            ),
        )

    monkeypatch.setattr(job_runner, "render_product", fake_render_product)
    runner = SequentialJobRunner(store, job_runner.service_runner_callback)
    record = store.enqueue(JobType.RENDER, {"model": "233541"}, job_id="job-1")

    try:
        runner.enqueue(record.job_id)

        assert runner.wait_until_idle(timeout=2.0)
    finally:
        runner.stop()

    failed = store.get_job(record.job_id)
    assert failed.status == JobStatus.FAILED
    assert failed.error == "Candidate validation failed"
    assert failed.error_code == ServiceErrorCode.VALIDATION_FAILURE.value
    assert failed.artifacts == {
        "validation_report_path": str(
            tmp_path / "work" / "233541" / "candidate" / "233541.validation.json"
        )
    }


def test_default_runner_calls_publish_service_and_captures_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    store = JobStore(tmp_path / "jobs")
    calls: list[PublishRequest] = []

    def fake_publish_product(request: PublishRequest) -> ServiceResult:
        calls.append(request)
        return ServiceResult(
            run=RunMetadata(
                model=request.model,
                run_type=RunType.PUBLISH,
                status=RunStatus.COMPLETED,
            ),
            artifacts=RunArtifacts(
                model_root=tmp_path / "work" / request.model,
                published_csv_path=request.current_job_product_file,
                metadata_path=tmp_path / "work" / request.model / "publish.run.json",
            ),
            details={
                "publish_status": "success",
                "upload_report_path": str(
                    tmp_path / "work" / request.model / "upload.opencart.json"
                ),
                "import_report_path": str(
                    tmp_path / "work" / request.model / "import.opencart.json"
                ),
            },
        )

    monkeypatch.setattr(job_runner, "publish_product", fake_publish_product)
    runner = SequentialJobRunner(store, job_runner.service_runner_callback)
    product_file = tmp_path / "products" / "233541.csv"
    record = store.enqueue(
        JobType.PUBLISH,
        {
            "model": "233541",
            "current_job_product_file": str(product_file),
        },
        job_id="job-1",
    )

    try:
        runner.enqueue(record.job_id)

        assert runner.wait_until_idle(timeout=2.0)
    finally:
        runner.stop()

    loaded = store.get_job(record.job_id)
    logs = store.read_logs(record.job_id)
    assert calls == [
        PublishRequest(model="233541", current_job_product_file=product_file)
    ]
    assert loaded.status == JobStatus.SUCCEEDED
    assert loaded.message == "Publish job succeeded."
    assert loaded.artifacts == {
        "model_root": str(tmp_path / "work" / "233541"),
        "published_csv_path": str(product_file),
        "metadata_path": str(tmp_path / "work" / "233541" / "publish.run.json"),
        "upload_report_path": str(
            tmp_path / "work" / "233541" / "upload.opencart.json"
        ),
        "import_report_path": str(
            tmp_path / "work" / "233541" / "import.opencart.json"
        ),
    }
    assert "Calling publish service." in logs
    assert "Publish service returned status: completed" in logs


def test_full_pipeline_runner_executes_all_stages_with_stubbed_services(
    tmp_path: Path,
) -> None:
    model = "233541"
    source_url = "https://www.electronet.gr/example"
    record = JobRecord(
        job_id="job-1",
        job_type=JobType.FULL_PIPELINE,
        status=JobStatus.RUNNING,
        model=model,
        payload={
            "model": model,
            "source_url": source_url,
            "source_resolution": {
                "method": "batch_intake",
                "selected_url": source_url,
            },
            "bestprice_enabled": True,
            "skroutz_enabled": True,
            "boxnow_enabled": True,
            "photos": 100,
            "sections": 20,
            "gallery_mode": "all",
        },
    )
    calls: list[object] = []
    logs: list[str] = []
    product_file = tmp_path / "products" / f"{model}.csv"
    _write_required_prepared_artifacts(tmp_path, model)

    result = run_full_pipeline_job(
        record,
        logs.append,
        prepare_product_fn=lambda request: calls.append(request)
        or _service_result(
            request.model,
            RunType.PREPARE,
            artifacts=_prepared_run_artifacts(tmp_path, model),
        ),
        run_intro_text_authoring_fn=lambda model, retry=False: calls.append(
            ("intro", model, retry)
        )
        or _authoring_status(tmp_path / "work" / model / "llm", model=model),
        run_seo_meta_authoring_fn=lambda model, retry=False: calls.append(
            ("seo", model, retry)
        )
        or _authoring_status(tmp_path / "work" / model / "llm", model=model),
        render_product_fn=lambda request: calls.append(request)
        or _service_result(
            request.model,
            RunType.RENDER,
            artifacts=RunArtifacts(published_csv_path=product_file),
        ),
        publish_product_fn=lambda request: calls.append(request)
        or _service_result(
            request.model,
            RunType.PUBLISH,
            artifacts=RunArtifacts(published_csv_path=request.current_job_product_file),
        ),
    )

    assert result.status == JobStatus.SUCCEEDED
    assert result.message == "Full pipeline job succeeded."
    assert calls[0] == PrepareRequest(
        model=model,
        url=source_url,
        photos=100,
        sections=20,
        bestprice_status=1,
        skroutz_status=1,
        boxnow=1,
        price=0,
        gallery_mode="all",
    )
    assert calls[1:4] == [
        ("intro", model, False),
        ("seo", model, False),
        RenderRequest(model=model),
    ]
    assert calls[4] == PublishRequest(
        model=model, current_job_product_file=product_file
    )
    assert "Full pipeline stage prepare starting." in logs
    assert "Prepare whole-gallery mode active." in logs
    assert "Full pipeline stage publish succeeded." in logs


def test_full_pipeline_retry_from_artifacts_skips_prepare_and_reruns_remaining_stages(
    tmp_path: Path,
    monkeypatch,
) -> None:
    model = "233541"
    _write_required_prepared_artifacts(tmp_path, model)
    monkeypatch.setattr(job_runner.repo_paths, "REPO_ROOT", tmp_path)
    record = JobRecord(
        job_id="job-1",
        job_type=JobType.FULL_PIPELINE,
        status=JobStatus.RUNNING,
        model=model,
        payload={
            "model": model,
            "source_url": "https://www.electronet.gr/example",
            "skip_prepare": True,
            "retry_mode": "from_prepared_artifacts",
        },
    )
    calls: list[object] = []
    logs: list[str] = []
    product_file = tmp_path / "products" / f"{model}.csv"

    result = run_full_pipeline_job(
        record,
        logs.append,
        prepare_product_fn=lambda request: calls.append(request)
        or _service_result(request.model, RunType.PREPARE),
        run_intro_text_authoring_fn=lambda model, retry=False: calls.append(
            ("intro", model, retry)
        )
        or _authoring_status(tmp_path / "work" / model / "llm", model=model),
        run_seo_meta_authoring_fn=lambda model, retry=False: calls.append(
            ("seo", model, retry)
        )
        or _authoring_status(tmp_path / "work" / model / "llm", model=model),
        render_product_fn=lambda request: calls.append(request)
        or _service_result(
            request.model,
            RunType.RENDER,
            artifacts=RunArtifacts(published_csv_path=product_file),
        ),
        publish_product_fn=lambda request: calls.append(request)
        or _service_result(
            request.model,
            RunType.PUBLISH,
            artifacts=RunArtifacts(published_csv_path=request.current_job_product_file),
        ),
    )

    assert result.status == JobStatus.SUCCEEDED
    assert calls == [
        ("intro", model, True),
        ("seo", model, True),
        RenderRequest(model=model),
        PublishRequest(model=model, current_job_product_file=product_file),
    ]
    assert (
        "Retry from prepared artifacts active; skipping prepare/source scraping."
        in logs
    )
    assert "Full pipeline stage prepare starting." not in logs


def test_full_pipeline_retry_from_artifacts_fails_when_prepared_artifacts_are_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    model = "233541"
    monkeypatch.setattr(job_runner.repo_paths, "REPO_ROOT", tmp_path)
    record = JobRecord(
        job_id="job-1",
        job_type=JobType.FULL_PIPELINE,
        status=JobStatus.RUNNING,
        model=model,
        payload={
            "model": model,
            "source_url": "https://www.electronet.gr/example",
            "skip_prepare": True,
        },
    )
    calls: list[str] = []
    logs: list[str] = []

    result = run_full_pipeline_job(
        record,
        logs.append,
        prepare_product_fn=lambda request: calls.append("prepare")
        or _service_result(request.model, RunType.PREPARE),
        run_intro_text_authoring_fn=lambda model, retry=False: calls.append("intro")
        or _authoring_status(Path("work") / model / "llm", model=model),
        run_seo_meta_authoring_fn=lambda model, retry=False: calls.append("seo")
        or _authoring_status(Path("work") / model / "llm", model=model),
        render_product_fn=lambda request: calls.append("render")
        or _service_result(request.model, RunType.RENDER),
        publish_product_fn=lambda request: calls.append("publish")
        or _service_result(request.model, RunType.PUBLISH),
    )

    assert result.status == JobStatus.FAILED
    assert result.error_code == "prepared_artifacts_missing"
    assert (
        result.message
        == "Cannot retry without scraping because prepared artifacts are missing."
    )
    assert calls == []
    assert (
        "Retry from prepared artifacts active; skipping prepare/source scraping."
        in logs
    )
    assert any("Prepared artifacts missing for retry:" in line for line in logs)


def test_full_pipeline_fails_before_authoring_when_prepare_artifacts_are_missing(
    tmp_path: Path,
) -> None:
    model = "233541"
    source_url = "https://www.electronet.gr/example"
    record = JobRecord(
        job_id="job-1",
        job_type=JobType.FULL_PIPELINE,
        status=JobStatus.RUNNING,
        model=model,
        payload={
            "model": model,
            "source_url": source_url,
            "bestprice_enabled": False,
            "skroutz_enabled": False,
            "boxnow_enabled": False,
        },
    )
    calls: list[str] = []
    logs: list[str] = []

    result = run_full_pipeline_job(
        record,
        logs.append,
        prepare_product_fn=lambda request: calls.append("prepare")
        or _service_result(request.model, RunType.PREPARE),
        run_intro_text_authoring_fn=lambda model, retry=False: calls.append("intro")
        or _authoring_status(tmp_path / "work" / model / "llm", model=model),
        run_seo_meta_authoring_fn=lambda model, retry=False: calls.append("seo")
        or _authoring_status(tmp_path / "work" / model / "llm", model=model),
        render_product_fn=lambda request: calls.append("render")
        or _service_result(request.model, RunType.RENDER),
        publish_product_fn=lambda request: calls.append("publish")
        or _service_result(request.model, RunType.PUBLISH),
    )

    assert result.status == JobStatus.FAILED
    assert result.message == "Full pipeline failed during prepare."
    assert result.error_code == "prepare_artifacts_missing"
    assert "required scrape/authoring artifacts" in (result.error or "")
    assert calls == ["prepare"]
    assert any("Full pipeline prepare artifacts missing:" in line for line in logs)
    assert (
        "Full pipeline stopping before authoring because source scraping failed."
        in logs
    )


def test_full_pipeline_batch_payload_uses_source_url_for_prepare(
    tmp_path: Path,
) -> None:
    model = "233541"
    source_url = "https://www.skroutz.gr/s/123/product.html"
    record = JobRecord(
        job_id="job-1",
        job_type=JobType.FULL_PIPELINE,
        status=JobStatus.RUNNING,
        model=model,
        payload={
            "model": model,
            "product_name": "Batch Product",
            "source_url": source_url,
            "source_resolution": {
                "method": "batch_intake",
                "batch_id": 7,
                "row_id": 73,
                "selected_url": source_url,
            },
        },
    )
    prepare_requests: list[PrepareRequest] = []

    result = run_full_pipeline_job(
        record,
        lambda _line: None,
        prepare_product_fn=lambda request: prepare_requests.append(request)
        or _service_result(
            request.model,
            RunType.PREPARE,
            status=RunStatus.FAILED,
            error_code=ServiceErrorCode.PARSE_FAILURE.value,
            error_detail="source scrape failed",
        ),
        run_intro_text_authoring_fn=lambda model, retry=False: _authoring_status(
            tmp_path / "work" / model / "llm", model=model
        ),
        run_seo_meta_authoring_fn=lambda model, retry=False: _authoring_status(
            tmp_path / "work" / model / "llm", model=model
        ),
        render_product_fn=lambda request: _service_result(
            request.model, RunType.RENDER
        ),
        publish_product_fn=lambda request: _service_result(
            request.model, RunType.PUBLISH
        ),
    )

    assert result.status == JobStatus.FAILED
    assert prepare_requests == [
        PrepareRequest(
            model=model,
            url=source_url,
            photos=100,
            sections=20,
            bestprice_status=0,
            skroutz_status=0,
            boxnow=0,
            price=0,
            gallery_mode="all",
        )
    ]


def test_full_pipeline_prepare_failure_stops_later_stages(
    tmp_path: Path,
) -> None:
    result, calls, logs = _run_full_pipeline_with_failure("prepare", tmp_path)

    assert result.status == JobStatus.FAILED
    assert result.message == "Full pipeline failed during prepare."
    assert result.error_code == ServiceErrorCode.VALIDATION_FAILURE.value
    assert calls == ["prepare"]
    assert any("Full pipeline stage prepare failed" in line for line in logs)


def test_full_pipeline_intro_authoring_failure_stops_later_stages(
    tmp_path: Path,
) -> None:
    result, calls, _logs = _run_full_pipeline_with_failure(
        "intro text authoring", tmp_path
    )

    assert result.status == JobStatus.FAILED
    assert result.message == "Full pipeline failed during intro text authoring."
    assert calls == ["prepare", "intro"]


def test_full_pipeline_seo_authoring_failure_stops_later_stages(
    tmp_path: Path,
) -> None:
    result, calls, _logs = _run_full_pipeline_with_failure(
        "SEO meta authoring", tmp_path
    )

    assert result.status == JobStatus.FAILED
    assert result.message == "Full pipeline failed during SEO meta authoring."
    assert calls == ["prepare", "intro", "seo"]


def test_full_pipeline_render_failure_stops_publish(tmp_path: Path) -> None:
    result, calls, _logs = _run_full_pipeline_with_failure("render", tmp_path)

    assert result.status == JobStatus.FAILED
    assert result.message == "Full pipeline failed during render."
    assert calls == ["prepare", "intro", "seo", "render"]


def test_full_pipeline_publish_failure_preserves_render_success(tmp_path: Path) -> None:
    result, calls, logs = _run_full_pipeline_with_failure("publish", tmp_path)

    assert result.status == JobStatus.SUCCEEDED
    assert result.message == "Full pipeline job succeeded with publish warning."
    assert calls == ["prepare", "intro", "seo", "render", "publish"]
    assert result.error_code == ServiceErrorCode.PUBLISH_FAILURE.value
    assert "Full pipeline publish warning: publish failed" in logs


def test_subprocess_runner_launches_child_and_records_process_metadata(
    tmp_path: Path,
) -> None:
    store = JobStore(tmp_path / "jobs")
    code = (
        "import sys;"
        "from product_factory.jobs.store import JobStore;"
        "s=JobStore(sys.argv[2]);"
        "s.append_log(sys.argv[1], 'child ran');"
        "s.update_artifacts(sys.argv[1], {'metadata_path': sys.argv[3]});"
        "s.mark_succeeded(sys.argv[1], message='child ok');"
        "print('child stdout')"
    )

    def command(record: JobRecord) -> list[str]:
        return [
            sys.executable,
            "-c",
            code,
            record.job_id,
            str(store.jobs_dir),
            str(tmp_path / "meta.json"),
        ]

    runner = SequentialJobRunner(store, command_builder=command)
    record = store.enqueue(JobType.RENDER, {"model": "233541"}, job_id="job-1")

    try:
        runner.enqueue(record.job_id)
        assert runner.wait_until_idle(timeout=5.0)
    finally:
        runner.stop()

    loaded = store.get_job(record.job_id)
    logs = store.read_logs(record.job_id)
    assert loaded.status == JobStatus.SUCCEEDED
    assert loaded.message == "child ok"
    assert loaded.process_id is not None
    assert loaded.command[:2] == [sys.executable, "-c"]
    assert loaded.stdout_log_path is not None
    assert loaded.stderr_log_path is not None
    assert loaded.artifacts == {"metadata_path": str(tmp_path / "meta.json")}
    assert "child ran" in logs
    assert "stdout: child stdout" in logs


def test_nonzero_child_exit_marks_failed_when_no_terminal_status_exists(
    tmp_path: Path,
) -> None:
    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(
        store,
        command_builder=lambda _record: [
            sys.executable,
            "-c",
            "import sys; sys.exit(7)",
        ],
    )
    record = store.enqueue(JobType.PUBLISH, {"model": "233541"}, job_id="job-1")

    try:
        runner.enqueue(record.job_id)
        assert runner.wait_until_idle(timeout=5.0)
    finally:
        runner.stop()

    loaded = store.get_job(record.job_id)
    assert loaded.status == JobStatus.FAILED
    assert loaded.exit_code == 7
    assert loaded.error == "Job subprocess exited with code 7."


def test_parent_preserves_terminal_status_written_by_child_on_nonzero_exit(
    tmp_path: Path,
) -> None:
    store = JobStore(tmp_path / "jobs")
    code = (
        "import sys;"
        "from product_factory.jobs.store import JobStore;"
        "s=JobStore(sys.argv[2]);"
        "s.mark_succeeded(sys.argv[1], message='child already done');"
        "sys.exit(9)"
    )
    runner = SequentialJobRunner(
        store,
        command_builder=lambda record: [
            sys.executable,
            "-c",
            code,
            record.job_id,
            str(store.jobs_dir),
        ],
    )
    record = store.enqueue(
        JobType.PREPARE,
        {"model": "233541", "url": "https://example.invalid"},
        job_id="job-1",
    )

    try:
        runner.enqueue(record.job_id)
        assert runner.wait_until_idle(timeout=5.0)
    finally:
        runner.stop()

    loaded = store.get_job(record.job_id)
    assert loaded.status == JobStatus.SUCCEEDED
    assert loaded.message == "child already done"
    assert loaded.exit_code == 9


def test_stop_queued_job_in_runner_queue_marks_cancelled_and_never_launches(
    tmp_path: Path,
) -> None:
    store = JobStore(tmp_path / "jobs")
    marker = tmp_path / "launched.txt"
    sleeper = "import time; time.sleep(0.5)"
    marker_code = f"from pathlib import Path; Path({str(marker)!r}).write_text('launched', encoding='utf-8')"

    def command(record: JobRecord) -> list[str]:
        return [
            sys.executable,
            "-c",
            sleeper if record.job_id == "job-1" else marker_code,
        ]

    runner = SequentialJobRunner(store, command_builder=command)
    first = store.enqueue(JobType.RENDER, {"model": "111111"}, job_id="job-1")
    second = store.enqueue(JobType.RENDER, {"model": "222222"}, job_id="job-2")

    try:
        runner.enqueue(first.job_id)
        runner.enqueue(second.job_id)
        while store.get_job(first.job_id).status != JobStatus.RUNNING:
            time.sleep(0.01)
        stopped = runner.stop_job(second.job_id, reason="operator stop")
        assert runner.wait_until_idle(timeout=5.0)
    finally:
        runner.stop()

    assert stopped.status == JobStatus.CANCELLED
    assert store.get_job(second.job_id).status == JobStatus.CANCELLED
    assert not marker.exists()
    assert "Stop requested by operator before job started." in store.read_logs(
        second.job_id
    )


def test_stop_running_child_graceful_terminate_marks_cancelled(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    code = "import time; print('ready', flush=True); time.sleep(30)"
    runner = SequentialJobRunner(
        store,
        command_builder=lambda _record: [sys.executable, "-c", code],
        terminate_timeout_seconds=5,
    )
    record = store.enqueue(JobType.RENDER, {"model": "233541"}, job_id="job-1")

    try:
        runner.enqueue(record.job_id)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            loaded = store.get_job(record.job_id)
            if loaded.process_id is not None:
                break
            time.sleep(0.01)
        stopped = runner.stop_job(record.job_id, reason="operator stop")
        assert runner.wait_until_idle(timeout=5.0)
    finally:
        runner.stop()

    final = store.get_job(record.job_id)
    assert stopped.status == JobStatus.CANCELLED
    assert final.status == JobStatus.CANCELLED
    assert final.terminate_sent_at is not None
    assert final.termination_mode in {"graceful", "process_exited"}


def test_stop_running_child_force_kills_after_timeout(
    tmp_path: Path, monkeypatch
) -> None:
    store = JobStore(tmp_path / "jobs")
    code = "import time; print('ready', flush=True); time.sleep(30)"
    monkeypatch.setattr(job_runner, "_terminate_process_tree", lambda _process: None)
    runner = SequentialJobRunner(
        store,
        command_builder=lambda _record: [sys.executable, "-c", code],
        terminate_timeout_seconds=1,
    )
    record = store.enqueue(JobType.RENDER, {"model": "233541"}, job_id="job-1")

    try:
        runner.enqueue(record.job_id)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            loaded = store.get_job(record.job_id)
            if loaded.process_id is not None:
                break
            time.sleep(0.01)
        stopped = runner.stop_job(record.job_id, reason="operator stop")
        assert runner.wait_until_idle(timeout=5.0)
    finally:
        runner.stop()

    final = store.get_job(record.job_id)
    assert stopped.status == JobStatus.KILLED
    assert final.status == JobStatus.KILLED
    assert final.killed_reason == "Process did not exit before terminate timeout."
    assert final.termination_mode == "force_kill"
    assert final.kill_sent_at is not None
    assert final.killed_at is not None


def test_same_model_jobs_do_not_run_concurrently_with_multiple_workers(
    tmp_path: Path,
) -> None:
    store = JobStore(tmp_path / "jobs")
    code = (
        "import sys,time;"
        "from pathlib import Path;"
        "Path(sys.argv[1]).write_text('started', encoding='utf-8');"
        "time.sleep(0.4);"
        "from product_factory.jobs.store import JobStore;"
        "JobStore(sys.argv[3]).mark_succeeded(sys.argv[2], message='done')"
    )

    def command(record: JobRecord) -> list[str]:
        marker = tmp_path / f"{record.job_id}.started"
        return [
            sys.executable,
            "-c",
            code,
            str(marker),
            record.job_id,
            str(store.jobs_dir),
        ]

    runner = SequentialJobRunner(store, command_builder=command, max_workers=2)
    first = store.enqueue(JobType.RENDER, {"model": " ABC123 "}, job_id="job-1")
    second = store.enqueue(JobType.PUBLISH, {"model": "abc123"}, job_id="job-2")

    try:
        runner.enqueue(first.job_id)
        runner.enqueue(second.job_id)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not (tmp_path / "job-1.started").exists():
            time.sleep(0.01)
        time.sleep(0.1)
        assert store.get_job(second.job_id).status == JobStatus.QUEUED
        assert not (tmp_path / "job-2.started").exists()
        assert runner.wait_until_idle(timeout=5.0)
    finally:
        runner.stop()

    assert store.get_job(first.job_id).status == JobStatus.SUCCEEDED
    assert store.get_job(second.job_id).status == JobStatus.SUCCEEDED


def _service_result(
    model: str,
    run_type: RunType,
    *,
    status: RunStatus = RunStatus.COMPLETED,
    error_code: str | None = None,
    error_detail: str | None = None,
    artifacts: RunArtifacts | None = None,
) -> ServiceResult:
    return ServiceResult(
        run=RunMetadata(
            model=model,
            run_type=run_type,
            status=status,
            error_code=error_code,
            error_detail=error_detail,
        ),
        artifacts=artifacts or RunArtifacts(),
    )


def _authoring_status(llm_dir: Path, *, model: str = "233541") -> AuthoringStatus:
    return AuthoringStatus(
        model=model,
        llm_dir=str(llm_dir),
        intro_text=IntroTextTaskStatus(
            status="valid",
            output_path=str(llm_dir / "intro_text.output.txt"),
            trace_path=str(llm_dir / "intro_text.retry_trace.json"),
            word_count=90,
            min_words=70,
            max_words=180,
            max_attempts=3,
        ),
        seo_meta=SeoMetaTaskStatus(
            status="valid",
            output_path=str(llm_dir / "seo_meta.output.json"),
        ),
        ready_for_render=True,
    )


def _write_required_prepared_artifacts(root: Path, model: str) -> None:
    scrape_dir = root / "work" / model / "scrape"
    llm_dir = root / "work" / model / "llm"
    scrape_dir.mkdir(parents=True)
    llm_dir.mkdir(parents=True)
    for path in [
        scrape_dir / f"{model}.source.json",
        scrape_dir / f"{model}.normalized.json",
        scrape_dir / f"{model}.report.json",
        llm_dir / "task_manifest.json",
        llm_dir / "intro_text.context.json",
        llm_dir / "seo_meta.context.json",
    ]:
        path.write_text("{}\n", encoding="utf-8")
    (llm_dir / "intro_text.prompt.txt").write_text("intro\n", encoding="utf-8")
    (llm_dir / "seo_meta.prompt.txt").write_text("seo\n", encoding="utf-8")


def _prepared_run_artifacts(root: Path, model: str) -> RunArtifacts:
    scrape_dir = root / "work" / model / "scrape"
    llm_dir = root / "work" / model / "llm"
    return RunArtifacts(
        source_json_path=scrape_dir / f"{model}.source.json",
        scrape_normalized_json_path=scrape_dir / f"{model}.normalized.json",
        source_report_json_path=scrape_dir / f"{model}.report.json",
        llm_task_manifest_path=llm_dir / "task_manifest.json",
        intro_text_context_path=llm_dir / "intro_text.context.json",
        intro_text_prompt_path=llm_dir / "intro_text.prompt.txt",
        seo_meta_context_path=llm_dir / "seo_meta.context.json",
        seo_meta_prompt_path=llm_dir / "seo_meta.prompt.txt",
    )


def _run_full_pipeline_with_failure(
    stage: str, tmp_path: Path
) -> tuple[object, list[str], list[str]]:
    model = "233541"
    if stage != "prepare":
        _write_required_prepared_artifacts(tmp_path, model)
    record = JobRecord(
        job_id="job-1",
        job_type=JobType.FULL_PIPELINE,
        status=JobStatus.RUNNING,
        model=model,
        payload={
            "model": model,
            "source_url": "https://www.electronet.gr/example",
            "bestprice_enabled": False,
            "skroutz_enabled": False,
            "boxnow_enabled": False,
            "photos": 100,
            "sections": 20,
            "gallery_mode": "all",
        },
    )
    calls: list[str] = []
    logs: list[str] = []

    def prepare_fn(request: PrepareRequest) -> ServiceResult:
        calls.append("prepare")
        return _stage_service_result(
            stage,
            "prepare",
            request.model,
            RunType.PREPARE,
            artifacts=_prepared_run_artifacts(tmp_path, model),
        )

    def intro_fn(model: str, retry: bool = False) -> AuthoringStatus:
        del retry
        calls.append("intro")
        if stage == "intro text authoring":
            raise ServiceError(ServiceErrorCode.PROVIDER_FAILURE.value, "intro failed")
        return _authoring_status(Path("work") / model / "llm", model=model)

    def seo_fn(model: str, retry: bool = False) -> AuthoringStatus:
        del retry
        calls.append("seo")
        if stage == "SEO meta authoring":
            raise ServiceError(ServiceErrorCode.PROVIDER_FAILURE.value, "seo failed")
        return _authoring_status(Path("work") / model / "llm", model=model)

    def render_fn(request: RenderRequest) -> ServiceResult:
        calls.append("render")
        return _stage_service_result(stage, "render", request.model, RunType.RENDER)

    def publish_fn(request: PublishRequest) -> ServiceResult:
        calls.append("publish")
        return _stage_service_result(stage, "publish", request.model, RunType.PUBLISH)

    result = run_full_pipeline_job(
        record,
        logs.append,
        prepare_product_fn=prepare_fn,
        run_intro_text_authoring_fn=intro_fn,
        run_seo_meta_authoring_fn=seo_fn,
        render_product_fn=render_fn,
        publish_product_fn=publish_fn,
    )
    return result, calls, logs


def _stage_service_result(
    failing_stage: str,
    current_stage: str,
    model: str,
    run_type: RunType,
    artifacts: RunArtifacts | None = None,
) -> ServiceResult:
    if failing_stage == current_stage:
        error_code = (
            ServiceErrorCode.PUBLISH_FAILURE.value
            if current_stage == "publish"
            else ServiceErrorCode.VALIDATION_FAILURE.value
        )
        return _service_result(
            model,
            run_type,
            status=RunStatus.FAILED,
            error_code=error_code,
            error_detail=f"{current_stage} failed",
        )
    success_artifacts = artifacts or (
        RunArtifacts(published_csv_path=Path("products") / f"{model}.csv")
        if current_stage == "render"
        else RunArtifacts()
    )
    return _service_result(model, run_type, artifacts=success_artifacts)
