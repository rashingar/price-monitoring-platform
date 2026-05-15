import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.db.models import Base  # noqa: E402
from ecommerce.db.models.jobs import EcommerceJob  # noqa: E402
from ecommerce.db.session import create_session_factory, get_engine, session_scope  # noqa: E402
from ecommerce.db.repositories.jobs import create_queued_job, get_job_by_id, heartbeat, list_jobs, mark_running, mark_succeeded, record_progress, request_cancel  # noqa: E402
from ecommerce.jobs.durable import execute_job  # noqa: E402


def _database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"


def _create_schema(database_url: str) -> None:
    Base.metadata.create_all(get_engine(database_url))


def test_create_get_and_list_jobs_with_filters(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        first = create_queued_job(session, job_type="vendor_capture", payload={"source": "skroutz"}, job_id="job-1")
        create_queued_job(session, job_type="url_validation", payload={"url": "https://example.test"}, job_id="job-2")

        assert first.status == "queued"
        assert first.payload_json == {"source": "skroutz"}
        assert get_job_by_id(session, "job-1") is not None
        assert [job.job_id for job in list_jobs(session, job_type="vendor_capture")] == ["job-1"]
        assert [job.job_id for job in list_jobs(session, status="queued")] == ["job-2", "job-1"]


def test_mark_running_heartbeat_and_success(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        create_queued_job(session, job_type="diagnostic", payload={}, job_id="job-1")
        running = mark_running(session, "job-1")
        assert running.status == "running"
        beat = heartbeat(session, "job-1")
        succeeded = mark_succeeded(session, "job-1", result={"ok": True})

        assert succeeded.status == "succeeded"
        assert succeeded.result_json == {"ok": True}
        assert succeeded.error_message is None
        assert succeeded.attempt_count == 1
        assert succeeded.started_at is not None
        assert beat.heartbeat_at is not None
        assert succeeded.completed_at is not None


def test_execute_job_marks_cancelled_before_start_and_skips_handler(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    _create_schema(database_url)
    called = False

    def mark_called(_payload):
        nonlocal called
        called = True

    with session_scope(database_url) as session:
        create_queued_job(session, job_type="diagnostic", payload={}, job_id="job-1")
        request_cancel(session, "job-1")

    session = create_session_factory(database_url)()
    try:
        job = execute_job(session, "job-1", mark_called)
    finally:
        session.close()

    assert called is False
    assert job.status == "cancelled"
    assert job.attempt_count == 0
    assert job.completed_at is not None


def test_execute_job_persists_failure_even_when_handler_raises(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        create_queued_job(session, job_type="diagnostic", payload={"id": 1}, job_id="job-1")

    def fail(_payload):
        raise RuntimeError("diagnostic failed")

    session = create_session_factory(database_url)()
    try:
        with pytest.raises(RuntimeError, match="diagnostic failed"):
            execute_job(session, "job-1", fail)
    finally:
        session.close()

    with session_scope(database_url) as session:
        job = session.query(EcommerceJob).filter_by(job_id="job-1").one()
        assert job.status == "failed"
        assert job.error_message == "diagnostic failed"
        assert job.attempt_count == 1
        assert job.completed_at is not None


def test_execute_job_preserves_running_progress_on_success(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        create_queued_job(session, job_type="diagnostic", payload={}, job_id="job-1")

    def complete_with_progress(_payload):
        with session_scope(database_url) as progress_session:
            record_progress(
                progress_session,
                "job-1",
                progress={
                    "current_step": "download_waiting",
                    "current_step_label": "Download waiting",
                    "steps_completed": 3,
                    "last_progress_at": "2026-05-15T12:00:00+00:00",
                },
            )
        return {"ok": True}

    session = create_session_factory(database_url)()
    try:
        job = execute_job(session, "job-1", complete_with_progress)
    finally:
        session.close()

    assert job.status == "succeeded"
    assert job.result_json["ok"] is True
    assert job.result_json["progress"]["current_step"] == "download_waiting"
