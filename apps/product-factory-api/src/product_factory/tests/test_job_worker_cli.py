from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from product_factory.api.job_models import JobStatus, JobType
from product_factory.api.job_runner import JobRunResult
from product_factory.api.job_store import JobStore
from product_factory.jobs import run_product_factory_job


def test_worker_cli_missing_job_returns_nonzero(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "product_factory.jobs.run_product_factory_job",
            "--job-id",
            "missing",
            "--job-root",
            str(tmp_path / "jobs"),
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode != 0
    assert "Job not found: missing" in result.stderr


@pytest.mark.parametrize(
    ("job_type", "runner_name", "payload"),
    [
        (JobType.PREPARE, "run_prepare_job", {"model": "233541", "url": "https://example.invalid"}),
        (JobType.RENDER, "run_render_job", {"model": "233541"}),
        (JobType.PUBLISH, "run_publish_job", {"model": "233541"}),
    ],
)
def test_worker_cli_runs_queued_job_through_stub_service(
    tmp_path: Path,
    monkeypatch,
    job_type: JobType,
    runner_name: str,
    payload: dict[str, str],
) -> None:
    store = JobStore(tmp_path / "jobs")
    record = store.enqueue(job_type, payload, job_id="job-1")

    def stub_runner(_record, log):
        log("stub service ran")
        return JobRunResult(
            status=JobStatus.SUCCEEDED,
            message="stub succeeded",
            artifacts={"metadata_path": tmp_path / "work" / "run.json"},
        )

    monkeypatch.setattr(run_product_factory_job, runner_name, stub_runner)

    exit_code = run_product_factory_job.main(["--job-id", record.job_id, "--job-root", str(store.jobs_dir)])

    loaded = store.get_job(record.job_id)
    assert exit_code == 0
    assert loaded.status == JobStatus.SUCCEEDED
    assert loaded.message == "stub succeeded"
    assert loaded.artifacts == {"metadata_path": str(tmp_path / "work" / "run.json")}
    assert "stub service ran" in store.read_logs(record.job_id)


def test_worker_cli_failure_writes_failed_metadata_and_exits_nonzero(tmp_path: Path, monkeypatch) -> None:
    store = JobStore(tmp_path / "jobs")
    record = store.enqueue(JobType.RENDER, {"model": "233541"}, job_id="job-1")

    def stub_runner(_record, log):
        log("stub service failed")
        return JobRunResult(status=JobStatus.FAILED, message="stub failed", error="boom", error_code="TEST")

    monkeypatch.setattr(run_product_factory_job, "run_render_job", stub_runner)

    exit_code = run_product_factory_job.main(["--job-id", record.job_id, "--job-root", str(store.jobs_dir)])

    loaded = store.get_job(record.job_id)
    assert exit_code != 0
    assert loaded.status == JobStatus.FAILED
    assert loaded.message == "stub failed"
    assert loaded.error == "boom"
    assert loaded.error_code == "TEST"
    assert "stub service failed" in store.read_logs(record.job_id)


def test_worker_cli_does_not_overwrite_cancelled_job(tmp_path: Path, monkeypatch) -> None:
    store = JobStore(tmp_path / "jobs")
    record = store.enqueue(JobType.RENDER, {"model": "233541"}, job_id="job-1")

    def stub_runner(_record, log):
        log("stub observed cancellation")
        store.mark_cancelled(record.job_id, reason="operator stop")
        return JobRunResult(status=JobStatus.SUCCEEDED, message="should not win")

    monkeypatch.setattr(run_product_factory_job, "run_render_job", stub_runner)

    exit_code = run_product_factory_job.main(["--job-id", record.job_id, "--job-root", str(store.jobs_dir)])

    loaded = store.get_job(record.job_id)
    assert exit_code != 0
    assert loaded.status == JobStatus.CANCELLED
    assert loaded.message == "Job stopped by operator."
    assert "Worker will not overwrite terminal cancelled status." in store.read_logs(record.job_id)
