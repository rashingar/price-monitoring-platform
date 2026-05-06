from __future__ import annotations

import json
from pathlib import Path

from product_factory.api.job_models import JobStatus, JobType
from product_factory.api.job_store import JobStore


def test_enqueue_persists_job_metadata_and_log_file(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")

    record = store.enqueue(
        JobType.PREPARE,
        {
            "model": "233541",
            "url": "https://www.electronet.gr/example",
            "photos": 6,
        },
        job_id="job-1",
    )

    metadata_path = tmp_path / "jobs" / "job-1.json"
    log_path = tmp_path / "jobs" / "job-1.log"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert record.job_id == "job-1"
    assert record.status == JobStatus.QUEUED
    assert metadata_path.exists()
    assert log_path.exists()
    assert payload["job_id"] == "job-1"
    assert payload["job_type"] == "prepare"
    assert payload["status"] == "queued"
    assert payload["model"] == "233541"
    assert payload["payload"]["photos"] == 6
    assert payload["log_path"] == str(log_path)
    assert payload["artifacts"] == {}


def test_enqueue_default_job_id_is_model_first(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")

    record = store.enqueue(JobType.RENDER, {"model": "233541"})

    assert record.job_id.startswith("233541-render-")
    assert (tmp_path / "jobs" / f"{record.job_id}.json").exists()


def test_store_lists_and_gets_jobs_from_disk(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    first = store.enqueue(JobType.PREPARE, {"model": "111111"}, job_id="job-1")
    second = store.enqueue(JobType.RENDER, {"model": "222222"}, job_id="job-2")

    jobs = store.list_jobs()

    assert [job.job_id for job in jobs] == [first.job_id, second.job_id]
    assert store.get_job("job-1") == first
    assert store.get_job("missing") is None


def test_store_lists_jobs_for_model_case_insensitively(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    first = store.enqueue(JobType.PREPARE, {"model": "ABC"}, job_id="job-1")
    store.enqueue(JobType.RENDER, {"model": "other"}, job_id="job-2")
    second = store.enqueue(JobType.PUBLISH, {"model": "abc"}, job_id="job-3")

    jobs = store.list_jobs_for_model(" abc ")

    assert [job.job_id for job in jobs] == [first.job_id, second.job_id]


def test_store_updates_statuses_and_reads_logs(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    record = store.enqueue(JobType.PUBLISH, {"model": "233541"}, job_id="job-1")

    running = store.mark_running(record.job_id, message="started")
    store.append_log(record.job_id, "line one")
    store.append_log(record.job_id, "line two")
    succeeded = store.mark_succeeded(record.job_id, message="done")

    loaded = store.get_job(record.job_id)
    assert running.status == JobStatus.RUNNING
    assert running.started_at is not None
    assert succeeded.status == JobStatus.SUCCEEDED
    assert succeeded.finished_at is not None
    assert succeeded.error is None
    assert succeeded.error_code is None
    assert loaded == succeeded
    assert store.read_logs(record.job_id) == ["line one", "line two"]


def test_store_marks_failed_with_error_detail(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    record = store.enqueue(JobType.RENDER, {"model": "233541"}, job_id="job-1")

    failed = store.mark_failed(record.job_id, "boom", message="failed")

    assert failed.status == JobStatus.FAILED
    assert failed.error == "boom"
    assert failed.error_code is None
    assert failed.message == "failed"
    assert failed.finished_at is not None


def test_store_marks_queued_job_cancelled_and_reloads_stop_metadata(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    record = store.enqueue(JobType.RENDER, {"model": "233541"}, job_id="job-1")

    cancelled = store.mark_cancelled(record.job_id, reason="operator request")
    loaded = JobStore(tmp_path / "jobs").get_job(record.job_id)

    assert cancelled.status == JobStatus.CANCELLED
    assert cancelled.finished_at is not None
    assert cancelled.message == "Job stopped by operator."
    assert cancelled.error == "operator request"
    assert cancelled.error_code == "JOB_STOPPED"
    assert cancelled.stop_requested_at is not None
    assert cancelled.stop_reason == "operator request"
    assert loaded == cancelled


def test_store_marks_running_job_killed_and_reloads_metadata(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    record = store.enqueue(JobType.RENDER, {"model": "233541"}, job_id="job-1")
    store.mark_running(record.job_id, message="started")

    killed = store.mark_killed(record.job_id)
    loaded = JobStore(tmp_path / "jobs").get_job(record.job_id)

    assert killed.status == JobStatus.KILLED
    assert killed.finished_at is not None
    assert killed.error_code == "JOB_KILLED"
    assert killed.termination_mode == "force_kill"
    assert killed.killed_reason == "Process did not exit before terminate timeout."
    assert loaded == killed


def test_store_loads_legacy_job_json_without_process_fields(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    (jobs_dir / "legacy.json").write_text(
        json.dumps(
            {
                "job_id": "legacy",
                "job_type": "prepare",
                "status": "queued",
                "model": "233541",
                "payload": {"model": "233541"},
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    loaded = JobStore(jobs_dir).get_job("legacy")

    assert loaded is not None
    assert loaded.status == JobStatus.QUEUED
    assert loaded.process_id is None
    assert loaded.command == []
    assert loaded.termination_mode is None


def test_store_persists_artifact_paths(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    record = store.enqueue(JobType.PREPARE, {"model": "233541"}, job_id="job-1")

    updated = store.update_artifacts(
        record.job_id,
        {
            "scrape_dir": tmp_path / "work" / "233541" / "scrape",
            "llm_dir": tmp_path / "work" / "233541" / "llm",
            "metadata_path": None,
        },
    )

    loaded = store.get_job(record.job_id)
    assert updated.artifacts == {
        "scrape_dir": str(tmp_path / "work" / "233541" / "scrape"),
        "llm_dir": str(tmp_path / "work" / "233541" / "llm"),
    }
    assert loaded == updated
