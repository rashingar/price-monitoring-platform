import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models import Base  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.jobs.durable import create_queued_job, mark_running  # noqa: E402


def _client(tmp_path: Path, monkeypatch) -> tuple[TestClient, str]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    Base.metadata.create_all(get_engine(database_url))
    return TestClient(create_app()), database_url


def test_jobs_api_lists_and_filters_jobs(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        create_queued_job(session, job_type="vendor_capture", payload={"source": "skroutz"}, job_id="job-1")
        create_queued_job(session, job_type="url_validation", payload={"url": "https://example.test"}, job_id="job-2")
        mark_running(session, "job-2")

    response = client.get("/api/jobs", params={"status": "queued"})

    assert response.status_code == 200
    payload = response.json()
    assert [item["job_id"] for item in payload["items"]] == ["job-1"]
    assert payload["items"][0]["payload"] == {"source": "skroutz"}
    assert payload["items"][0]["error_message"] is None


def test_jobs_api_gets_job_by_id(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        create_queued_job(session, job_type="diagnostic", payload={"source_url_id": 101}, job_id="job-1")

    response = client.get("/api/jobs/job-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == "job-1"
    assert payload["job_type"] == "diagnostic"
    assert payload["status"] == "queued"
    assert payload["cancel_requested"] is False


def test_jobs_api_cancel_requests_cancellation(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        create_queued_job(session, job_type="diagnostic", payload={}, job_id="job-1")

    response = client.post("/api/jobs/job-1/cancel")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == "job-1"
    assert payload["status"] == "queued"
    assert payload["cancel_requested"] is True


def test_jobs_api_returns_404_for_missing_job(tmp_path: Path, monkeypatch) -> None:
    client, _database_url = _client(tmp_path, monkeypatch)

    response = client.get("/api/jobs/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found."


def test_jobs_api_returns_503_when_database_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, "")

    response = TestClient(create_app()).get("/api/jobs")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ecommerce_jobs_database_required"
