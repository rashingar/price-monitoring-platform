import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.api import routes_price_monitoring  # noqa: E402
from ecommerce.db.models import Base, MonitoringRun  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.dev import start as dev_start  # noqa: E402
from ecommerce.jobs import run_price_monitoring_execution  # noqa: E402
from ecommerce.price_monitoring import fetch_execution  # noqa: E402
from ecommerce.price_monitoring.fetch_execution import wait_for_worker_idle  # noqa: E402
from ecommerce.price_monitoring.fetch_run import (  # noqa: E402
    PriceMonitoringFetchError,
    PriceMonitoringFetchResult,
    run_price_monitoring_fetch,
)
from ecommerce.vendor_sources.capture import SourceUrlCaptureRunResult  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_execution_scheduler_state(monkeypatch):
    monkeypatch.setattr(routes_price_monitoring, "require_database_ready_for_price_monitoring", lambda: None)
    fetch_execution._QUEUE.clear()
    fetch_execution._ACTIVE_EXECUTIONS.clear()
    fetch_execution._RUN_ACTIVE_EXECUTIONS.clear()
    fetch_execution._WORKER_THREADS.clear()
    fetch_execution._FINALIZING_EXECUTIONS.clear()
    yield
    fetch_execution._QUEUE.clear()
    fetch_execution._ACTIVE_EXECUTIONS.clear()
    fetch_execution._RUN_ACTIVE_EXECUTIONS.clear()
    fetch_execution._WORKER_THREADS.clear()
    fetch_execution._FINALIZING_EXECUTIONS.clear()


def test_post_fetch_returns_202_and_get_returns_latest_execution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_run(run_dir)
    original_ensure_worker = fetch_execution._ensure_worker_locked
    monkeypatch.setattr(fetch_execution, "_ensure_worker_locked", lambda: None)

    response = TestClient(create_app()).post("/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"})

    assert response.status_code == 202
    payload = response.json()
    assert payload["execution_id"]
    assert payload["status"] == "queued"
    assert (run_dir / "fetch_execution.json").exists()

    get_payload = TestClient(create_app()).get("/api/price-monitoring/runs/run-1/fetch").json()
    assert get_payload["execution_id"] == payload["execution_id"]
    assert get_payload["status"] == "queued"

    cancel = TestClient(create_app()).post(
        f"/api/price-monitoring/runs/run-1/fetch/{payload['execution_id']}/cancel",
        json={"reason": "test cleanup"},
    )
    assert cancel.status_code == 200
    monkeypatch.setattr(fetch_execution, "_ensure_worker_locked", original_ensure_worker)
    with fetch_execution._LOCK:
        original_ensure_worker()
    assert wait_for_worker_idle()


def test_post_fetch_uses_current_enqueue_signature(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_run(run_dir)
    captured: dict[str, object] = {}

    def fake_enqueue(run_dir_arg: Path, *, source: str | None = None, catalog_url: str | None = None):
        captured["run_dir"] = run_dir_arg
        captured["source"] = source
        captured["catalog_url"] = catalog_url
        execution = fetch_execution._new_execution(run_dir_arg, source or "skroutz", catalog_url)
        fetch_execution.save_fetch_execution(execution)
        return execution

    monkeypatch.setattr(routes_price_monitoring, "enqueue_fetch_execution", fake_enqueue)

    response = TestClient(create_app()).post(
        "/api/price-monitoring/runs/run-1/fetch",
        json={"source": "skroutz", "catalog_url": "https://example.test/catalog"},
    )

    assert response.status_code == 202
    assert Path(captured["run_dir"]).resolve() == run_dir
    assert captured["source"] == "skroutz"
    assert captured["catalog_url"] == "https://example.test/catalog"


def test_execution_cli_rejects_unsupported_type(capsys) -> None:
    code = run_price_monitoring_execution.main(
        ["--run-id", "run-1", "--execution-id", "exec-1", "--execution-type", "review"]
    )

    assert code != 0
    assert "Unsupported execution type" in capsys.readouterr().err


def test_execution_cli_fetch_completes_existing_execution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    Base.metadata.create_all(get_engine(database_url))
    run_dir = _run_dir(tmp_path)
    _write_run(run_dir)
    queued_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    _write_execution_metadata(run_dir, "exec-1", status="running", queued_at=queued_at, started_at=queued_at)

    fake_fetch = lambda run_dir, source=None, catalog_url=None, write_result=True: _route_fetch_success(
        run_dir,
        source=source,
        catalog_url=catalog_url,
        write_result=write_result,
    )
    monkeypatch.setattr(fetch_execution, "run_price_monitoring_fetch", fake_fetch)
    monkeypatch.setattr(run_price_monitoring_execution.fetch_execution, "run_price_monitoring_fetch", fake_fetch)

    code = run_price_monitoring_execution.main(
        ["--run-id", "run-1", "--execution-id", "exec-1", "--execution-type", "fetch"]
    )
    payload = TestClient(create_app()).get("/api/price-monitoring/runs/run-1/fetch/exec-1").json()

    assert code == 0
    assert payload["status"] == "succeeded"
    assert Path(payload["fetch_result_path"]).exists()


def test_execution_cli_fetch_failure_writes_failed_metadata(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_run(run_dir)
    queued_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    _write_execution_metadata(run_dir, "exec-1", status="running", queued_at=queued_at, started_at=queued_at)

    def fail_fetch(*_args, **_kwargs):
        raise PriceMonitoringFetchError("cli fetch failed")

    monkeypatch.setattr(fetch_execution, "run_price_monitoring_fetch", fail_fetch)
    monkeypatch.setattr(run_price_monitoring_execution.fetch_execution, "run_price_monitoring_fetch", fail_fetch)

    code = run_price_monitoring_execution.main(
        ["--run-id", "run-1", "--execution-id", "exec-1", "--execution-type", "fetch"]
    )
    payload = TestClient(create_app()).get("/api/price-monitoring/runs/run-1/fetch/exec-1").json()

    assert code != 0
    assert payload["status"] == "failed"
    assert payload["error"] == "cli fetch failed"


def test_successful_execution_writes_result_metadata_and_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("ECOMMERCE_DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    _write_run(_run_dir(tmp_path))
    _use_fake_child(monkeypatch, tmp_path, mode="success")
    client = TestClient(create_app())

    response = client.post("/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"})

    assert response.status_code == 202
    assert response.json()["execution_id"]
    assert wait_for_worker_idle()
    payload = client.get("/api/price-monitoring/runs/run-1/fetch").json()
    assert payload["status"] == "succeeded"
    assert payload["command"]
    assert payload["process_id"]
    assert payload["exit_code"] == 0
    assert payload["persistence_status"] == "not_configured"
    assert Path(payload["fetch_result_path"]).exists()
    assert Path(payload["execution_path"]).exists()
    assert any(artifact["name"] == "fetch_result.json" for artifact in payload["artifacts"])
    assert any(artifact["name"] == "fetch_execution.json" for artifact in payload["artifacts"])


def test_nonzero_child_exit_marks_failed_when_child_writes_no_terminal_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_run(_run_dir(tmp_path))
    _use_fake_child(monkeypatch, tmp_path, mode="exit_only")
    client = TestClient(create_app())

    assert client.post("/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}).status_code == 202
    assert wait_for_worker_idle()
    payload = client.get("/api/price-monitoring/runs/run-1/fetch").json()

    assert payload["status"] == "failed"
    assert payload["exit_code"] == 3
    assert "Child process exited with code 3" in payload["error"]
    assert payload["artifacts_are_diagnostic"] is True
    assert payload["artifact_warning"] == "Execution failed. Artifacts may be partial or incomplete."


def test_failed_execution_records_error_without_succeeded_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_run(_run_dir(tmp_path))
    _use_fake_child(monkeypatch, tmp_path, mode="fail")
    client = TestClient(create_app())

    assert client.post("/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}).status_code == 202
    assert wait_for_worker_idle()
    payload = client.get("/api/price-monitoring/runs/run-1/fetch").json()

    assert payload["status"] == "failed"
    assert "Child failed intentionally" in payload["error"]
    assert payload["artifacts_are_diagnostic"] is True
    assert payload["artifact_warning"] == "Execution failed. Artifacts may be partial or incomplete."
    assert Path(payload["execution_path"]).exists()


def test_cancel_queued_execution_is_terminal_and_logged(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_run(_run_dir(tmp_path))
    original_ensure_worker = fetch_execution._ensure_worker_locked
    monkeypatch.setattr(fetch_execution, "_ensure_worker_locked", lambda: None)
    client = TestClient(create_app())
    queued = client.post("/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}).json()

    cancelled = client.post(
        f"/api/price-monitoring/runs/run-1/fetch/{queued['execution_id']}/cancel",
        json={"reason": "not now"},
    ).json()

    assert cancelled["status"] == "cancelled"
    assert cancelled["completed_at"]
    assert cancelled["cancelled_at"]
    assert "not now" in cancelled["cancel_reason"]
    lines = client.get("/api/price-monitoring/runs/run-1/fetch/logs").json()["lines"]
    assert any("Cancellation requested" in line for line in lines)

    monkeypatch.setattr(fetch_execution, "_ensure_worker_locked", original_ensure_worker)
    with fetch_execution._LOCK:
        original_ensure_worker()
    assert wait_for_worker_idle()
    assert client.get("/api/price-monitoring/runs/run-1/fetch").json()["status"] == "cancelled"


def test_cancel_running_execution_late_completion_does_not_persist_or_overwrite(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_run(_run_dir(tmp_path))
    _use_fake_child(monkeypatch, tmp_path, mode="sleep", sleep_seconds=30)
    client = TestClient(create_app())
    execution = client.post("/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}).json()
    assert _wait_for_status(client, "run-1", "running")

    cancelled = client.post(f"/api/price-monitoring/runs/run-1/fetch/{execution['execution_id']}/cancel").json()
    assert wait_for_worker_idle()
    latest = client.get("/api/price-monitoring/runs/run-1/fetch").json()

    assert cancelled["status"] == "cancelled"
    assert latest["status"] == "cancelled"


def test_cancel_running_execution_force_kills_after_timeout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ECOMMERCE_SUBPROCESS_TERMINATE_TIMEOUT_SECONDS", "1")
    monkeypatch.chdir(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_run(run_dir)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    _write_execution_metadata(run_dir, "exec-1", status="running", queued_at=now, started_at=now, heartbeat_at=now)
    fake_process = _FakeTimeoutProcess(pid=4242)
    fetch_execution._ACTIVE_EXECUTIONS["exec-1"] = fetch_execution._ActiveWorkerMetadata(
        worker_id="worker-1",
        process=fake_process,
        process_id=fake_process.pid,
        thread_name="test-thread",
        stdout_log_path=run_dir / "fetch_executions" / "exec-1.stdout.log",
        stderr_log_path=run_dir / "fetch_executions" / "exec-1.stderr.log",
    )
    fetch_execution._RUN_ACTIVE_EXECUTIONS["run-1"] = "exec-1"
    monkeypatch.setattr(fetch_execution, "_send_graceful_terminate", lambda _process: None)
    monkeypatch.setattr(fetch_execution, "_force_kill_process_tree", lambda process: process.kill())
    client = TestClient(create_app())

    killed = client.post("/api/price-monitoring/runs/run-1/fetch/exec-1/cancel").json()
    repeated = client.post("/api/price-monitoring/runs/run-1/fetch/exec-1/cancel").json()

    assert killed["status"] == "killed"
    assert killed["termination_mode"] == "force_kill"
    assert killed["kill_sent_at"]
    assert killed["killed_at"]
    assert killed["killed_reason"] == "Process did not exit before terminate timeout."
    assert killed["artifacts_are_diagnostic"] is True
    assert killed["artifact_warning"] == "Execution was force killed. Artifacts may be partial or incomplete."
    assert repeated["status"] == "killed"
    fetch_execution._ACTIVE_EXECUTIONS.pop("exec-1", None)
    fetch_execution._RUN_ACTIVE_EXECUTIONS.pop("run-1", None)


def test_active_execution_conflict_returns_409(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_run(_run_dir(tmp_path))
    _use_fake_child(monkeypatch, tmp_path, mode="sleep", sleep_seconds=30)
    client = TestClient(create_app())
    assert client.post("/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}).status_code == 202
    assert _wait_for_status(client, "run-1", "running")

    conflict = client.post("/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"})
    client.post("/api/price-monitoring/runs/run-1/fetch/cancel")
    assert wait_for_worker_idle()

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["status"] == "running"


def test_killed_execution_does_not_block_refetch_and_increments_attempt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_run(run_dir)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    _write_execution_metadata(
        run_dir,
        "killed-1",
        status="killed",
        queued_at=now,
        started_at=now,
        completed_at=now,
        catalog_url="https://example.test/catalog",
    )
    monkeypatch.setattr(fetch_execution, "_ensure_worker_locked", lambda: None)
    client = TestClient(create_app())

    response = client.post("/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"})
    killed = client.get("/api/price-monitoring/runs/run-1/fetch/killed-1").json()

    assert response.status_code == 202
    payload = response.json()
    assert payload["execution_id"] != "killed-1"
    assert payload["fetch_attempt"] == 2
    assert killed["status"] == "killed"
    assert killed["source"] == "skroutz"
    assert killed["catalog_url"] == "https://example.test/catalog"


def test_different_runs_execute_concurrently_up_to_worker_cap(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ECOMMERCE_MAX_FETCH_WORKERS", "2")
    monkeypatch.chdir(tmp_path)
    for run_id in ["run-1", "run-2"]:
        _write_run(_run_dir_named(tmp_path, run_id))
    _use_fake_child(monkeypatch, tmp_path, mode="sleep", sleep_seconds=2)
    client = TestClient(create_app())

    assert client.post("/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}).status_code == 202
    assert client.post("/api/price-monitoring/runs/run-2/fetch", json={"source": "skroutz"}).status_code == 202
    assert _wait_for_status(client, "run-1", "running")
    assert _wait_for_status(client, "run-2", "running")
    assert wait_for_worker_idle()


def test_worker_cap_queues_extra_runs_and_queue_position_clears_on_start(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ECOMMERCE_MAX_FETCH_WORKERS", "1")
    monkeypatch.chdir(tmp_path)
    for run_id in ["run-1", "run-2"]:
        _write_run(_run_dir_named(tmp_path, run_id))
    _use_fake_child(monkeypatch, tmp_path, mode="sleep", sleep_seconds=1)
    client = TestClient(create_app())
    assert client.post("/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}).status_code == 202
    queued = client.post("/api/price-monitoring/runs/run-2/fetch", json={"source": "skroutz"}).json()

    assert queued["status"] == "queued"
    assert queued["queue_position"] == 1
    assert client.get("/api/price-monitoring/runs/run-2/fetch").json()["queue_position"] == 1

    assert _wait_for_status(client, "run-2", "running", timeout=5)
    running = client.get("/api/price-monitoring/runs/run-2/fetch").json()
    assert running["status"] in {"running", "succeeded"}
    assert running["queue_position"] is None
    assert wait_for_worker_idle()


def test_running_execution_exposes_worker_metadata_and_fresh_stale_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_run(_run_dir(tmp_path))
    _use_fake_child(monkeypatch, tmp_path, mode="sleep", sleep_seconds=30)
    client = TestClient(create_app())
    assert client.post("/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}).status_code == 202
    assert _wait_for_status(client, "run-1", "running")

    payload = client.get("/api/price-monitoring/runs/run-1/fetch").json()
    client.post("/api/price-monitoring/runs/run-1/fetch/cancel")

    assert payload["status"] == "running"
    assert payload["worker_id"]
    assert payload["parent_process_id"] == os.getpid()
    assert payload["process_id"]
    assert payload["thread_name"].startswith("price-monitoring-fetch-")
    assert payload["heartbeat_at"]
    assert payload["stale"] is False
    assert payload["stale_after_minutes"] == 30
    assert wait_for_worker_idle()


def test_stale_detection_uses_configured_threshold_and_safe_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_run(run_dir)
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).replace(microsecond=0).isoformat()
    _write_execution_metadata(run_dir, "old-runner", status="running", queued_at=old, started_at=old, heartbeat_at=old)
    client = TestClient(create_app())

    monkeypatch.setenv("ECOMMERCE_FETCH_STALE_AFTER_MINUTES", "5")
    stale_payload = client.get("/api/price-monitoring/runs/run-1/fetch/old-runner").json()
    assert stale_payload["stale"] is True
    assert stale_payload["stale_after_minutes"] == 5

    fresh = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    _write_execution_metadata(run_dir, "fresh-runner", status="running", queued_at=fresh, started_at=fresh, heartbeat_at=fresh)
    fresh_payload = client.get("/api/price-monitoring/runs/run-1/fetch/fresh-runner").json()
    assert fresh_payload["stale"] is True

    monkeypatch.setattr(fetch_execution, "_ACTIVE_EXECUTIONS", {"fresh-runner": object()})
    owned_fresh_payload = client.get("/api/price-monitoring/runs/run-1/fetch/fresh-runner").json()
    assert owned_fresh_payload["stale"] is False

    monkeypatch.setenv("ECOMMERCE_FETCH_STALE_AFTER_MINUTES", "bad")
    assert client.get("/api/price-monitoring/runs/run-1/fetch/fresh-runner").json()["stale_after_minutes"] == 30
    _write_execution_metadata(run_dir, "done", status="succeeded", queued_at=fresh, completed_at=fresh, heartbeat_at=old)
    assert client.get("/api/price-monitoring/runs/run-1/fetch/done").json()["stale"] is False


def test_cancel_stale_running_execution_without_worker_marks_cancelled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_run(run_dir)
    old = (datetime.now(timezone.utc) - timedelta(minutes=60)).replace(microsecond=0).isoformat()
    _write_execution_metadata(run_dir, "stale-runner", status="running", queued_at=old, started_at=old, heartbeat_at=old)
    client = TestClient(create_app())

    cancelled = client.post("/api/price-monitoring/runs/run-1/fetch/stale-runner/cancel").json()
    lines = client.get("/api/price-monitoring/runs/run-1/fetch/stale-runner/logs").json()["lines"]

    assert cancelled["status"] == "cancelled"
    assert cancelled["cancelled_at"]
    assert any("stale running execution" in line for line in lines)


def test_repeated_cancel_on_terminal_execution_is_idempotent_without_extra_logs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_run(_run_dir(tmp_path))
    original_ensure_worker = fetch_execution._ensure_worker_locked
    monkeypatch.setattr(fetch_execution, "_ensure_worker_locked", lambda: None)
    client = TestClient(create_app())
    execution = client.post("/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}).json()
    first = client.post(f"/api/price-monitoring/runs/run-1/fetch/{execution['execution_id']}/cancel").json()
    first_lines = client.get(f"/api/price-monitoring/runs/run-1/fetch/{execution['execution_id']}/logs").json()["lines"]
    second = client.post(f"/api/price-monitoring/runs/run-1/fetch/{execution['execution_id']}/cancel").json()
    second_lines = client.get(f"/api/price-monitoring/runs/run-1/fetch/{execution['execution_id']}/logs").json()["lines"]

    assert first["status"] == "cancelled"
    assert second["status"] == "cancelled"
    assert second_lines == first_lines
    monkeypatch.setattr(fetch_execution, "_ensure_worker_locked", original_ensure_worker)


def test_execution_listing_returns_sorted_items_with_stale_and_queue_position(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_run(run_dir)
    older = "2026-04-29T10:00:00+00:00"
    newer = "2026-04-29T11:00:00+00:00"
    _write_execution_metadata(run_dir, "older", status="succeeded", queued_at=older, completed_at=older)
    _write_execution_metadata(run_dir, "newer", status="queued", queued_at=newer)
    monkeypatch.setattr(fetch_execution, "_QUEUE", _queue_with("newer", run_dir))
    client = TestClient(create_app())

    payload = client.get("/api/price-monitoring/runs/run-1/fetch/executions").json()

    assert payload["count"] == 2
    assert [item["execution_id"] for item in payload["items"]] == ["newer", "older"]
    assert payload["items"][0]["queue_position"] == 1
    assert payload["items"][0]["stale"] is False
    assert payload["items"][1]["queue_position"] is None


def test_execution_listing_empty_history_returns_empty_list(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_run(_run_dir(tmp_path))

    payload = TestClient(create_app()).get("/api/price-monitoring/runs/run-1/fetch/executions").json()

    assert payload == {"run_id": "run-1", "items": [], "count": 0}


def test_legacy_fetch_result_statuses_map_to_execution_statuses(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_run(run_dir)
    _write_legacy_fetch_result(run_dir, "fetch_completed")
    client = TestClient(create_app())

    assert client.get("/api/price-monitoring/runs/run-1/fetch").json()["status"] == "succeeded"
    _write_legacy_fetch_result(run_dir, "fetch_failed")
    assert client.get("/api/price-monitoring/runs/run-1/fetch").json()["status"] == "failed"


def test_old_execution_metadata_loads_with_new_artifact_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_run(run_dir)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    _write_execution_metadata(run_dir, "old-json", status="succeeded", queued_at=now, completed_at=now)

    payload = TestClient(create_app()).get("/api/price-monitoring/runs/run-1/fetch/old-json").json()
    legacy = fetch_execution.source_url_fetch_result_to_execution_payload(_legacy_fetch_result_object(run_dir))

    assert payload["killed_reason"] is None
    assert payload["artifacts_are_diagnostic"] is False
    assert payload["artifact_warning"] is None
    assert legacy["killed_reason"] is None
    assert legacy["artifacts_are_diagnostic"] is False
    assert legacy["artifact_warning"] is None


def test_specific_execution_and_logs_endpoints_return_lines(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_run(_run_dir(tmp_path))
    _use_fake_child(monkeypatch, tmp_path, mode="success")
    client = TestClient(create_app())
    execution = client.post("/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}).json()
    assert wait_for_worker_idle()

    specific = client.get(f"/api/price-monitoring/runs/run-1/fetch/{execution['execution_id']}").json()
    latest_logs = client.get("/api/price-monitoring/runs/run-1/fetch/logs").json()
    specific_logs = client.get(f"/api/price-monitoring/runs/run-1/fetch/{execution['execution_id']}/logs").json()

    assert specific["execution_id"] == execution["execution_id"]
    assert latest_logs["execution_id"] == execution["execution_id"]
    assert any("Started subprocess fetch execution" in line for line in specific_logs["lines"])
    assert any("[stdout] fake child stdout" in line for line in specific_logs["lines"])
    assert any("[stderr] fake child stderr" in line for line in specific_logs["lines"])


def test_run_listing_latest_fetch_uses_execution_metadata(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    Base.metadata.create_all(get_engine(database_url))
    run_dir = _run_dir(tmp_path)
    _write_run(run_dir)
    _use_fake_child(monkeypatch, tmp_path, mode="success")
    client = TestClient(create_app())
    execution = client.post("/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}).json()
    assert wait_for_worker_idle()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with session_scope(database_url) as session:
        session.add(
            MonitoringRun(
                run_id="run-1",
                source="skroutz",
                status="selection_created",
                trigger_type="manual",
                output_dir=str(run_dir),
                input_csv_path=str(run_dir / "input.csv"),
                selection_summary_path=str(run_dir / "selection_summary.json"),
                selected_count=1,
                skipped_count=0,
                created_at=now,
                updated_at=now,
            )
        )

    list_payload = client.get("/api/price-monitoring/runs").json()["items"][0]["latest_fetch"]
    detail_payload = client.get("/api/price-monitoring/runs/run-1").json()["latest_fetch"]

    assert list_payload["execution_id"] == execution["execution_id"]
    assert list_payload["status"] == "succeeded"
    assert detail_payload["execution_id"] == execution["execution_id"]
    assert detail_payload["status"] == "succeeded"


def test_late_child_save_cannot_overwrite_killed_execution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = _run_dir(tmp_path)
    _write_run(run_dir)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    _write_execution_metadata(run_dir, "exec-1", status="killed", queued_at=now, completed_at=now)
    execution = fetch_execution.load_fetch_execution(run_dir, "exec-1")
    execution.status = "succeeded"
    execution.completed_at = now

    fetch_execution.save_fetch_execution(execution)
    payload = TestClient(create_app()).get("/api/price-monitoring/runs/run-1/fetch/exec-1").json()

    assert payload["status"] == "killed"


def test_dev_start_prints_urls_and_runs_backend_only(monkeypatch, capsys) -> None:
    run_args: dict[str, object] = {}
    monkeypatch.delenv("ECOMMERCE_DATABASE_URL", raising=False)
    monkeypatch.setattr(dev_start, "is_database_configured", lambda: False)
    monkeypatch.setattr(dev_start.uvicorn, "run", lambda app, **kwargs: run_args.update({"app": app, **kwargs}))

    dev_start.main(["--host", "127.0.0.2", "--port", "8123", "--reload"])
    output = capsys.readouterr().out

    assert run_args == {
        "app": "ecommerce.api.app:app",
        "host": "127.0.0.2",
        "port": 8123,
        "reload": True,
    }
    assert "API URL: http://127.0.0.2:8123" in output
    assert "Health URL: http://127.0.0.2:8123/api/health" in output
    assert "Docs URL: http://127.0.0.2:8123/docs" in output
    assert "Price Monitoring DB status URL: http://127.0.0.2:8123/api/price-monitoring/db/status" in output
    assert "ECOMMERCE_DATABASE_URL is not set" in output


def _run_dir(tmp_path: Path) -> Path:
    return tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"


def _run_dir_named(tmp_path: Path, run_id: str) -> Path:
    return tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / run_id


def _write_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "input.csv").write_text(
        "model,mpn,name,price\n005606,MPN-1,Product One,123.45\n",
        encoding="utf-8",
    )
    (run_dir / "selection_summary.json").write_text(
        json.dumps({"run_id": run_dir.name, "source": "skroutz"}),
        encoding="utf-8",
    )


def _write_execution_metadata(
    run_dir: Path,
    execution_id: str,
    *,
    status: str,
    queued_at: str,
    started_at: str | None = None,
    completed_at: str | None = None,
    heartbeat_at: str | None = None,
    catalog_url: str | None = None,
) -> None:
    execution_dir = run_dir / "fetch_executions"
    execution_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "execution_id": execution_id,
        "execution_type": "fetch",
        "run_id": run_dir.name,
        "status": status,
        "source": "skroutz",
        "catalog_url": catalog_url,
        "queued_at": queued_at,
        "started_at": started_at,
        "completed_at": completed_at,
        "cancelled_at": None,
        "cancel_reason": "",
        "input_csv_path": str(run_dir / "input.csv"),
        "enriched_csv_path": "",
        "fetch_summary_path": "",
        "fetch_result_path": str(run_dir / "fetch_result.json"),
        "execution_path": str(execution_dir / f"{execution_id}.json"),
        "log_path": str(execution_dir / f"{execution_id}.log"),
        "warnings": [],
        "error": "",
        "observation_count": 0,
        "replaced_observation_count": 0,
        "catalog_snapshot_count": None,
        "matched_observation_count": 0,
        "unmatched_observation_count": 0,
        "was_refetch": False,
        "fetch_attempt": 1,
        "persistence_status": "not_configured",
        "persistence_warnings": [],
        "alert_evaluation_status": "not_configured",
        "alert_event_count": 0,
        "alert_duplicate_count": 0,
        "alert_warnings": [],
        "worker_id": "old-worker" if status == "running" else None,
        "parent_process_id": None,
        "process_id": 12345 if status == "running" else None,
        "process_group_id": None,
        "thread_name": "old-thread" if status == "running" else None,
        "heartbeat_at": heartbeat_at,
        "command": [],
        "exit_code": None,
        "termination_mode": None,
        "terminate_sent_at": None,
        "kill_sent_at": None,
        "killed_at": None,
        "stdout_log_path": "",
        "stderr_log_path": "",
    }
    (execution_dir / f"{execution_id}.json").write_text(json.dumps(payload), encoding="utf-8")
    (execution_dir / f"{execution_id}.log").write_text("seed log\n", encoding="utf-8")
    (run_dir / "fetch_execution.json").write_text(json.dumps(payload), encoding="utf-8")


def _queue_with(execution_id: str, run_dir: Path):
    return fetch_execution.deque(
        [
            fetch_execution._FetchExecutionJob(
                run_dir=run_dir,
                execution_id=execution_id,
                source="skroutz",
                catalog_url=None,
                execution_type="fetch",
            )
        ]
    )


def _use_fake_child(monkeypatch, tmp_path: Path, *, mode: str, sleep_seconds: float = 0.0) -> None:
    script = tmp_path / f"fake_child_{mode}_{str(sleep_seconds).replace('.', '_')}.py"
    script.write_text(
        """
import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--run-id", required=True)
parser.add_argument("--execution-id", required=True)
parser.add_argument("--execution-type", required=True)
args = parser.parse_args()

mode = __MODE__
sleep_seconds = __SLEEP_SECONDS__
run_dir = Path("output") / "ecommerce" / "monitoring" / "runs" / args.run_id
execution_path = run_dir / "fetch_executions" / f"{args.execution_id}.json"
alias_path = run_dir / "fetch_execution.json"

def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def load():
    return json.loads(execution_path.read_text(encoding="utf-8"))

def save(payload):
    text = json.dumps(payload, indent=2) + "\\n"
    execution_path.write_text(text, encoding="utf-8")
    alias_path.write_text(text, encoding="utf-8")

print("fake child stdout")
print("fake child stderr", file=sys.stderr)
payload = load()
payload["heartbeat_at"] = now()
save(payload)

if mode == "sleep":
    time.sleep(sleep_seconds)
    payload = load()
    if payload.get("status") in {"cancelled", "killed"}:
        sys.exit(0)

if mode == "exit_only":
    sys.exit(3)

if mode == "ignore":
    signal.signal(signal.SIGTERM, lambda *_args: None)
    end = time.time() + sleep_seconds
    while time.time() < end:
        time.sleep(0.1)
    payload = load()
    if payload.get("status") in {"cancelled", "killed"}:
        sys.exit(0)

payload = load()
payload["heartbeat_at"] = now()
if mode == "fail":
    payload["status"] = "failed"
    payload["completed_at"] = now()
    payload["error"] = "Child failed intentionally."
    payload["exit_code"] = 1
    save(payload)
    sys.exit(1)

fetch_result_path = run_dir / "fetch_result.json"
enriched_path = run_dir / "input_skroutz_enriched.csv"
summary_path = run_dir / "input_summary.json"
enriched_path.write_text("model,mpn,price,skroutz_price\\n005606,MPN-1,123.45,119.90\\n", encoding="utf-8")
summary_path.write_text("{\\"operation\\":\\"fetch\\"}\\n", encoding="utf-8")
fetch_result_path.write_text(json.dumps({
    "run_id": args.run_id,
    "source": "skroutz",
    "status": "fetch_completed",
    "started_at": payload.get("started_at") or now(),
    "completed_at": now(),
    "input_csv_path": str(run_dir / "input.csv"),
    "enriched_csv_path": str(enriched_path),
    "fetch_summary_path": str(summary_path),
    "fetch_result_path": str(fetch_result_path),
    "stdout": "",
    "warnings": [],
    "error": ""
}, indent=2), encoding="utf-8")
payload.update({
    "status": "succeeded",
    "completed_at": now(),
    "enriched_csv_path": str(enriched_path),
    "fetch_summary_path": str(summary_path),
    "fetch_result_path": str(fetch_result_path),
    "persistence_status": "not_configured",
    "alert_evaluation_status": "not_configured",
    "exit_code": 0,
    "error": "",
})
save(payload)
sys.exit(0)
""".replace("__MODE__", repr(mode)).replace("__SLEEP_SECONDS__", repr(float(sleep_seconds))),
        encoding="utf-8",
    )

    def command(run_id: str, execution_id: str, execution_type: str) -> list[str]:
        return [
            sys.executable,
            str(script),
            "--run-id",
            run_id,
            "--execution-id",
            execution_id,
            "--execution-type",
            execution_type,
        ]

    monkeypatch.setattr(fetch_execution, "build_execution_command", command)


def _wait_for_status(client: TestClient, run_id: str, status: str, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if client.get(f"/api/price-monitoring/runs/{run_id}/fetch").json().get("status") == status:
            return True
        time.sleep(0.02)
    return False


def _wait_for_active_process(execution_id: str, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        metadata = fetch_execution._ACTIVE_EXECUTIONS.get(execution_id)
        if metadata is not None and metadata.process is not None and metadata.process.poll() is None:
            return True
        time.sleep(0.02)
    return False


class _FakeTimeoutProcess:
    def __init__(self, *, pid: int) -> None:
        self.pid = pid
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        if not self.killed:
            raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)
        return -9

    def kill(self) -> None:
        self.killed = True


def _route_fetch_success(
    run_dir: Path,
    source: str | None = None,
    catalog_url: str | None = None,
    write_result: bool = True,
):
    del catalog_url
    run_dir = Path(run_dir)
    source = source or "skroutz"
    source_capture_result_path = run_dir / "source_url_capture_result.json"
    source_capture_result = SourceUrlCaptureRunResult(
        status="completed",
        used_source_urls=True,
        source=source,
        vendor=source,
        selected_catalog_product_count=1,
        selected_source_url_count=1,
        selected_product_source_count=1,
        succeeded_count=1,
        failed_count=0,
        warnings=[],
        items=[{"product_source_id": 1, "status": "success"}],
        source_urls=[{"source_name": source, "status": "active"}],
        result_path=source_capture_result_path,
        run_id="vendor-capture-route",
        observation_batch_id="vendor-capture-route",
    )
    source_capture_result_path.write_text(json.dumps(source_capture_result.to_dict()), encoding="utf-8")
    result = PriceMonitoringFetchResult(
        run_id=run_dir.name,
        source=source,
        status="fetch_completed",
        started_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        completed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        input_csv_path=run_dir / "input.csv",
        enriched_csv_path=None,
        fetch_summary_path=None,
        fetch_result_path=run_dir / "fetch_result.json",
        stdout="",
        warnings=[],
        error="",
        source_filter=source,
        fetch_input_mode="source_urls",
        source_url_capture_used=True,
        source_url_capture_status="completed",
        source_url_capture_selected_count=1,
        source_url_capture_succeeded_count=1,
        source_url_capture_failed_count=0,
        source_url_capture_result_path=source_capture_result_path,
        source_url_capture_warnings=[],
        source_url_capture_run_id="vendor-capture-route",
        observation_batch_id="vendor-capture-route",
    )
    if write_result:
        from ecommerce.price_monitoring.fetch_run import write_price_monitoring_fetch_result

        write_price_monitoring_fetch_result(result.fetch_result_path, result)
    return result


def _write_legacy_fetch_result(run_dir: Path, status: str) -> None:
    fetch_result_path = run_dir / "fetch_result.json"
    fetch_result_path.write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "status": status,
                "source": "skroutz",
                "started_at": "2026-04-29T12:01:00+00:00",
                "completed_at": "2026-04-29T12:02:00+00:00",
                "input_csv_path": str(run_dir / "input.csv"),
                "enriched_csv_path": str(run_dir / "input_skroutz_enriched.csv"),
                "fetch_summary_path": str(run_dir / "input_summary.json"),
                "fetch_result_path": str(fetch_result_path),
                "warnings": [],
                "error": "failed" if status == "fetch_failed" else "",
            }
        ),
        encoding="utf-8",
    )


def _legacy_fetch_result_object(run_dir: Path) -> PriceMonitoringFetchResult:
    return PriceMonitoringFetchResult(
        run_id=run_dir.name,
        source="skroutz",
        status="fetch_completed",
        started_at="2026-04-29T12:01:00+00:00",
        completed_at="2026-04-29T12:02:00+00:00",
        input_csv_path=run_dir / "input.csv",
        enriched_csv_path=run_dir / "input_skroutz_enriched.csv",
        fetch_summary_path=run_dir / "input_summary.json",
        fetch_result_path=run_dir / "fetch_result.json",
        stdout="",
        warnings=[],
        error="",
    )
