import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.catalog_update import CATALOG_UPDATE_JOB_TYPE  # noqa: E402
from ecommerce.catalog_update import service as catalog_update_service  # noqa: E402
from ecommerce.db.models import Base  # noqa: E402
from ecommerce.db.models.jobs import EcommerceJob  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.jobs.durable import DurableJobRegistry, create_queued_job, mark_running, request_cancel  # noqa: E402
from ecommerce.jobs.worker import build_default_registry, run_worker_iteration  # noqa: E402


def _database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"


def _create_schema(database_url: str) -> None:
    Base.metadata.create_all(get_engine(database_url))


def _job(database_url: str, job_id: str) -> EcommerceJob:
    with session_scope(database_url) as session:
        return session.query(EcommerceJob).filter_by(job_id=job_id).one()


def test_worker_picks_queued_job_and_runs_registered_catalog_handler(tmp_path: Path, monkeypatch) -> None:
    database_url = _database_url(tmp_path)
    _create_schema(database_url)
    seen_job_ids: list[str] = []

    def fake_catalog_update(job_id: str):
        seen_job_ids.append(job_id)
        return {"job_id": job_id, "ingest": {"imported": 3}}

    monkeypatch.setattr(catalog_update_service, "run_catalog_update", fake_catalog_update)
    with session_scope(database_url) as session:
        create_queued_job(session, job_type=CATALOG_UPDATE_JOB_TYPE, payload={}, job_id="job-1")

    result = run_worker_iteration(registry=build_default_registry(), database_url=database_url)

    job = _job(database_url, "job-1")
    assert result.claimed == 1
    assert result.executed == 1
    assert seen_job_ids == ["job-1"]
    assert job.status == "succeeded"
    assert job.result_json == {"job_id": "job-1", "ingest": {"imported": 3}}


def test_worker_honors_job_type_filter(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    _create_schema(database_url)
    registry = DurableJobRegistry()
    calls: list[str] = []
    registry.register(CATALOG_UPDATE_JOB_TYPE, lambda job_id, _payload: calls.append(job_id) or {"ok": job_id})
    registry.register("other_job", lambda job_id, _payload: calls.append(job_id) or {"ok": job_id})

    old_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    with session_scope(database_url) as session:
        create_queued_job(session, job_type="other_job", payload={}, job_id="job-other", created_at=old_time)
        create_queued_job(session, job_type=CATALOG_UPDATE_JOB_TYPE, payload={}, job_id="job-catalog")

    result = run_worker_iteration(registry=registry, job_type=CATALOG_UPDATE_JOB_TYPE, database_url=database_url)

    assert result.claimed == 1
    assert calls == ["job-catalog"]
    assert _job(database_url, "job-catalog").status == "succeeded"
    assert _job(database_url, "job-other").status == "queued"


def test_worker_honors_pre_start_cancellation(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    _create_schema(database_url)
    registry = DurableJobRegistry()
    calls: list[str] = []
    registry.register(CATALOG_UPDATE_JOB_TYPE, lambda job_id, _payload: calls.append(job_id))

    with session_scope(database_url) as session:
        create_queued_job(session, job_type=CATALOG_UPDATE_JOB_TYPE, payload={}, job_id="job-1")
        request_cancel(session, "job-1")

    result = run_worker_iteration(registry=registry, database_url=database_url)

    job = _job(database_url, "job-1")
    assert result.cancelled == 1
    assert calls == []
    assert job.status == "cancelled"
    assert job.attempt_count == 0


def test_worker_marks_stale_running_jobs_failed(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    _create_schema(database_url)
    registry = DurableJobRegistry()
    registry.register(CATALOG_UPDATE_JOB_TYPE, lambda _job_id, _payload: {"ok": True})
    now = datetime.now(timezone.utc)

    with session_scope(database_url) as session:
        create_queued_job(session, job_type=CATALOG_UPDATE_JOB_TYPE, payload={}, job_id="job-stale")
        mark_running(session, "job-stale", started_at=now - timedelta(minutes=90))

    result = run_worker_iteration(
        registry=registry,
        database_url=database_url,
        stale_running_after_minutes=60,
        now=now,
    )

    job = _job(database_url, "job-stale")
    assert result.stale_failed == 1
    assert job.status == "failed"
    assert "Marked failed by Ecommerce durable job worker" in str(job.error_message)


def test_worker_persists_failed_handler_as_failed(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    _create_schema(database_url)
    registry = DurableJobRegistry()

    def fail(_job_id: str, _payload):
        raise RuntimeError("catalog update exploded")

    registry.register(CATALOG_UPDATE_JOB_TYPE, fail)
    with session_scope(database_url) as session:
        create_queued_job(session, job_type=CATALOG_UPDATE_JOB_TYPE, payload={}, job_id="job-1")

    result = run_worker_iteration(registry=registry, database_url=database_url)

    job = _job(database_url, "job-1")
    assert result.executed == 1
    assert job.status == "failed"
    assert job.error_message == "catalog update exploded"


def test_worker_dry_run_does_not_execute_handler_or_mutate_jobs(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    _create_schema(database_url)
    registry = DurableJobRegistry()
    calls: list[str] = []
    registry.register(CATALOG_UPDATE_JOB_TYPE, lambda job_id, _payload: calls.append(job_id) or {"ok": True})

    with session_scope(database_url) as session:
        create_queued_job(session, job_type=CATALOG_UPDATE_JOB_TYPE, payload={}, job_id="job-1")

    result = run_worker_iteration(registry=registry, database_url=database_url, dry_run=True)

    job = _job(database_url, "job-1")
    assert result.dry_run is True
    assert result.claimed == 1
    assert calls == []
    assert job.status == "queued"
    assert job.attempt_count == 0
