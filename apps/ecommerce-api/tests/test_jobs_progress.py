import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models.base import Base  # noqa: E402
from ecommerce.db.repositories.jobs import create_queued_job, get_job_by_id, mark_running  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.jobs.progress import (  # noqa: E402
    JobProgressReporter,
    JobProgressState,
    JobProgressStepDefinition,
)

STEPS = (
    JobProgressStepDefinition("queued", "Queued"),
    JobProgressStepDefinition("download", "Download"),
    JobProgressStepDefinition("persist", "Persist"),
)


def test_job_progress_state_creates_initial_progress_payload() -> None:
    timestamp = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    state = JobProgressState.create(step_definitions=STEPS, initial_step="queued")
    state.start(timestamp)

    payload = state.payload(timestamp)

    assert payload == {
        "current_step": "queued",
        "current_step_label": "Queued",
        "step_started_at": "2026-05-15T12:00:00+00:00",
        "last_progress_at": "2026-05-15T12:00:00+00:00",
        "elapsed_seconds": 0.0,
        "current_step_elapsed_seconds": 0.0,
        "steps_completed": 0,
        "completed_steps": [],
        "warnings": [],
        "errors": [],
    }


def test_job_progress_state_advances_steps_and_records_completed_history() -> None:
    started_at = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    download_at = started_at + timedelta(seconds=3)
    observed_at = started_at + timedelta(seconds=7)
    state = JobProgressState.create(step_definitions=STEPS, initial_step="queued")
    state.start(started_at)
    state.advance_to("download", download_at)

    payload = state.payload(observed_at)

    assert payload["current_step"] == "download"
    assert payload["current_step_label"] == "Download"
    assert payload["steps_completed"] == 1
    assert payload["elapsed_seconds"] == 7.0
    assert payload["current_step_elapsed_seconds"] == 4.0
    assert payload["completed_steps"] == [
        {
            "step": "queued",
            "label": "Queued",
            "started_at": "2026-05-15T12:00:00+00:00",
            "completed_at": "2026-05-15T12:00:03+00:00",
            "elapsed_seconds": 3.0,
            "warnings": [],
            "errors": [],
        }
    ]


def test_job_progress_reporter_persists_nested_steps_completed(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    Base.metadata.create_all(get_engine(database_url))
    clock = _Clock(datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc))

    with session_scope(database_url) as session:
        create_queued_job(session, job_type="test_job", payload={}, job_id="job-progress")
        mark_running(session, "job-progress")

    with JobProgressReporter(
        "job-progress",
        step_definitions=STEPS,
        initial_step="queued",
        heartbeat_interval_seconds=60,
        now=clock,
    ) as reporter:
        reporter.report("download")
        reporter.report("persist")

    with session_scope(database_url) as session:
        job = get_job_by_id(session, "job-progress")
        assert job is not None
        progress = job.result_json["progress"]

    assert progress["current_step"] == "persist"
    assert progress["steps_completed"] == 2
    assert [step["step"] for step in progress["completed_steps"]] == ["queued", "download"]
    assert progress["completed_steps"][0]["elapsed_seconds"] == 2.0


def test_job_progress_state_supports_warnings_and_errors_per_step() -> None:
    started_at = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    state = JobProgressState.create(step_definitions=STEPS, initial_step="queued")
    state.start(started_at)
    state.add_warning("slow response")
    state.add_error("retry failed", details={"attempt": 1})

    current_payload = state.payload(started_at)
    state.advance_to("download", started_at + timedelta(seconds=2))
    next_payload = state.payload(started_at + timedelta(seconds=3))

    assert current_payload["warnings"] == ["slow response"]
    assert current_payload["errors"] == [{"message": "retry failed", "details": {"attempt": 1}}]
    assert next_payload["warnings"] == []
    assert next_payload["errors"] == []
    assert next_payload["completed_steps"][0]["warnings"] == ["slow response"]
    assert next_payload["completed_steps"][0]["errors"] == [{"message": "retry failed", "details": {"attempt": 1}}]


def test_job_progress_state_sanitizes_details_with_supplied_callback() -> None:
    def sanitizer(details: dict[str, Any] | None) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        for key, value in (details or {}).items():
            if key == "password":
                continue
            safe[key] = str(value).replace("supersecret", "[redacted]")
        return safe

    timestamp = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    state = JobProgressState.create(step_definitions=STEPS, initial_step="queued", details_sanitizer=sanitizer)
    state.start(timestamp)
    state.add_warning("loaded supersecret", details={"url": "https://example.test?token=supersecret"})

    payload = state.payload(timestamp, details={"password": "supersecret", "note": "using supersecret"})
    serialized = str(payload)

    assert "supersecret" not in serialized
    assert payload["details"] == {"note": "using [redacted]"}
    assert payload["warnings"] == [
        {
            "message": "loaded [redacted]",
            "details": {"url": "https://example.test?token=[redacted]"},
        }
    ]


def test_job_progress_reporter_recording_failures_do_not_raise(monkeypatch) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV_VAR, raising=False)
    clock = _Clock(datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc))

    with JobProgressReporter(
        "missing-job",
        step_definitions=STEPS,
        initial_step="queued",
        heartbeat_interval_seconds=60,
        now=clock,
    ) as reporter:
        reporter.report("download")
        reporter.add_warning("still safe")


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def __call__(self) -> datetime:
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value
