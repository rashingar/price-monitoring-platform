from __future__ import annotations

import threading
from pathlib import Path

import pytest

from product_factory.jobs.models import JobRecord, JobStatus, JobType
from product_factory.jobs.recovery import (
    RESTART_INTERRUPTED_ERROR_CODE,
    reconcile_persisted_jobs,
)
from product_factory.jobs.runner import LogCallback, SequentialJobRunner
from product_factory.jobs.store import JobStore


def test_startup_recovery_restores_queued_jobs_in_submission_order(
    tmp_path: Path,
) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    store.enqueue(JobType.FULL_PIPELINE, _payload("000001"), job_id="job-a")
    store.enqueue(JobType.FULL_PIPELINE, _payload("000002"), job_id="job-b")
    execution_order: list[str] = []
    active_count = 0
    max_active_count = 0
    lock = threading.Lock()

    def callback(record: JobRecord, log: LogCallback) -> None:
        nonlocal active_count, max_active_count
        with lock:
            active_count += 1
            max_active_count = max(max_active_count, active_count)
            execution_order.append(record.job_id)
        try:
            log(f"recovered {record.job_id}")
        finally:
            with lock:
                active_count -= 1

    runner = SequentialJobRunner(store, callback, max_workers=1)

    with fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    ):
        assert runner.wait_until_idle(timeout=2.0)

    assert execution_order == ["job-a", "job-b"]
    assert max_active_count == 1
    assert store.get_job("job-a").status == JobStatus.SUCCEEDED
    assert store.get_job("job-b").status == JobStatus.SUCCEEDED


def test_startup_recovery_is_idempotent_for_queued_jobs(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    store.enqueue(JobType.FULL_PIPELINE, _payload("000001"), job_id="job-a")
    release = threading.Event()
    started = threading.Event()
    executions: list[str] = []

    def callback(record: JobRecord, log: LogCallback) -> None:
        executions.append(record.job_id)
        started.set()
        release.wait(timeout=2.0)

    runner = SequentialJobRunner(store, callback, max_workers=1)
    try:
        reconcile_persisted_jobs(store, runner)
        reconcile_persisted_jobs(store, runner)
        assert started.wait(timeout=2.0)
        release.set()
        assert runner.wait_until_idle(timeout=2.0)
    finally:
        release.set()
        runner.stop()

    assert executions == ["job-a"]


def test_startup_recovery_preserves_current_runner_owned_running_job(
    tmp_path: Path,
) -> None:
    store = JobStore(tmp_path / "jobs")
    store.enqueue(JobType.FULL_PIPELINE, _payload("000001"), job_id="job-a")
    release = threading.Event()
    started = threading.Event()

    def callback(record: JobRecord, log: LogCallback) -> None:
        started.set()
        release.wait(timeout=2.0)

    runner = SequentialJobRunner(store, callback, max_workers=1)
    try:
        reconcile_persisted_jobs(store, runner)
        assert started.wait(timeout=2.0)
        reconcile_persisted_jobs(store, runner)
        assert store.get_job("job-a").status == JobStatus.RUNNING
        release.set()
        assert runner.wait_until_idle(timeout=2.0)
    finally:
        release.set()
        runner.stop()

    assert store.get_job("job-a").status == JobStatus.SUCCEEDED


def test_startup_recovery_marks_stale_running_job_interrupted(
    tmp_path: Path,
) -> None:
    store = JobStore(tmp_path / "jobs")
    record = store.enqueue(JobType.FULL_PIPELINE, _payload("000001"), job_id="job-a")
    store.mark_running(record.job_id, message="Job started.")
    runner = SequentialJobRunner(store, lambda record, log: None)
    try:
        reconcile_persisted_jobs(store, runner)
    finally:
        runner.stop()

    loaded = store.get_job(record.job_id)
    assert loaded.status == JobStatus.FAILED
    assert loaded.error_code == RESTART_INTERRUPTED_ERROR_CODE
    assert loaded.termination_mode == "interrupted_by_restart"
    assert any(
        "Startup recovery marked stale running job interrupted" in line
        for line in store.read_logs(record.job_id)
    )


def test_stale_running_record_no_longer_blocks_new_submission_after_startup(
    tmp_path: Path,
) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    stale = store.enqueue(JobType.FULL_PIPELINE, _payload("000001"), job_id="job-a")
    store.mark_running(stale.job_id, message="Job started.")
    runner = SequentialJobRunner(store, lambda record, log: None)

    with fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    ) as client:
        response = client.post("/api/jobs/full-pipeline", json=_payload("000001"))
        assert runner.wait_until_idle(timeout=2.0)

    assert response.status_code == 202
    assert store.get_job(stale.job_id).error_code == RESTART_INTERRUPTED_ERROR_CODE


def test_recovered_queued_job_blocks_duplicate_active_submission(
    tmp_path: Path,
) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    store.enqueue(JobType.FULL_PIPELINE, _payload("000001"), job_id="job-a")
    release = threading.Event()
    started = threading.Event()

    def callback(record: JobRecord, log: LogCallback) -> None:
        started.set()
        release.wait(timeout=2.0)

    runner = SequentialJobRunner(store, callback)

    with fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    ) as client:
        assert started.wait(timeout=2.0)
        response = client.post("/api/jobs/full-pipeline", json=_payload("000001"))
        release.set()
        assert runner.wait_until_idle(timeout=2.0)

    assert response.status_code == 409
    assert "already" in response.json()["detail"]


def test_app_shutdown_stops_recovery_worker_threads(tmp_path: Path) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    store.enqueue(JobType.FULL_PIPELINE, _payload("000001"), job_id="job-a")
    runner = SequentialJobRunner(store, lambda record, log: None)

    with fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    ):
        assert runner.wait_until_idle(timeout=2.0)
        assert any(thread.is_alive() for thread in runner._threads)

    assert not any(thread.is_alive() for thread in runner._threads)


def _payload(model: str) -> dict[str, str]:
    return {
        "model": model,
        "source_url": "https://www.electronet.gr/example",
    }
