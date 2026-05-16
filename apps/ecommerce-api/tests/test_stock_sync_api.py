from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from ecommerce.api import routes_stock_sync
from ecommerce.api.app import create_app


def _client(monkeypatch, tmp_path: Path, *, enabled: bool = False) -> TestClient:
    monkeypatch.setenv("ECOMMERCE_STOCK_SYNC_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("ECOMMERCE_STOCK_SYNC_SERVER", "ERPSERVER")
    monkeypatch.setenv("ECOMMERCE_STOCK_SYNC_TASK_REVIEW", "OpenCartStockSync-ReviewOnly")
    monkeypatch.setenv("ECOMMERCE_STOCK_SYNC_TASK_DRY_RUN", "OpenCartStockSync-DryRunImport")
    monkeypatch.setenv("ECOMMERCE_STOCK_SYNC_TASK_IMPORT", "OpenCartStockSync-RunImport")
    monkeypatch.setenv("ECOMMERCE_STOCK_SYNC_LATEST_REVIEW_PATH", str(tmp_path / "missing-review.json"))
    monkeypatch.setattr(routes_stock_sync.shutil, "which", lambda name: "schtasks.exe" if name == "schtasks" else None)
    return TestClient(create_app())


def test_readiness_reports_disabled_without_touching_schtasks(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path, enabled=False)

    response = client.get("/api/stock-sync/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is False
    assert payload["server"] == "ERPSERVER"
    assert payload["tasks"] == {
        "review": "OpenCartStockSync-ReviewOnly",
        "dry_run": "OpenCartStockSync-DryRunImport",
        "import": "OpenCartStockSync-RunImport",
    }
    assert payload["latest_review_exists"] is False
    assert payload["latest_review_readable"] is False
    assert payload["schtasks_available"] is True


def test_run_rejects_when_disabled(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path, enabled=False)

    response = client.post("/api/stock-sync/runs", json={"mode": "review"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "stock_sync_disabled"


def test_review_mode_maps_to_review_task(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):  # noqa: ANN001, ANN003
        calls.append(list(args))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="SUCCESS", stderr="")

    monkeypatch.setattr(routes_stock_sync.subprocess, "run", fake_run)
    client = _client(monkeypatch, tmp_path, enabled=True)

    response = client.post("/api/stock-sync/runs", json={"mode": "review"})

    assert response.status_code == 200
    assert calls == [["schtasks", "/Run", "/S", "ERPSERVER", "/TN", "OpenCartStockSync-ReviewOnly"]]
    assert response.json()["task_name"] == "OpenCartStockSync-ReviewOnly"
    assert response.json()["message"] == "Scheduled task triggered. Check email for the final report."


def test_dry_run_mode_maps_to_dry_run_task(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):  # noqa: ANN001, ANN003
        calls.append(list(args))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(routes_stock_sync.subprocess, "run", fake_run)
    client = _client(monkeypatch, tmp_path, enabled=True)

    response = client.post("/api/stock-sync/runs", json={"mode": "dry_run"})

    assert response.status_code == 200
    assert calls == [["schtasks", "/Run", "/S", "ERPSERVER", "/TN", "OpenCartStockSync-DryRunImport"]]
    assert response.json()["task_name"] == "OpenCartStockSync-DryRunImport"


def test_import_mode_requires_confirmation(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path, enabled=True)

    rejected = client.post("/api/stock-sync/runs", json={"mode": "import"})

    assert rejected.status_code == 400
    assert rejected.json()["detail"]["code"] == "stock_sync_import_confirmation_required"

    calls: list[list[str]] = []

    def fake_run(args, **kwargs):  # noqa: ANN001, ANN003
        calls.append(list(args))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(routes_stock_sync.subprocess, "run", fake_run)

    accepted = client.post(
        "/api/stock-sync/runs",
        json={"mode": "import", "confirmation": "RUN IMPORT"},
    )

    assert accepted.status_code == 200
    assert calls == [["schtasks", "/Run", "/S", "ERPSERVER", "/TN", "OpenCartStockSync-RunImport"]]


def test_unknown_mode_is_rejected(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path, enabled=True)

    response = client.post("/api/stock-sync/runs", json={"mode": "custom"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "stock_sync_unknown_mode"


def test_latest_handles_missing_review(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path, enabled=False)

    response = client.get("/api/stock-sync/latest")

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["message"] == "Latest stock sync review is not available yet."


def test_latest_parses_valid_review(monkeypatch, tmp_path: Path) -> None:
    review_path = tmp_path / "review.json"
    review_path.write_text(
        json.dumps(
            {
                "status": "reviewed",
                "ok_to_upload": True,
                "run_id": "stock-sync-20260516",
                "run_dir": r"\\ERPSERVER\C$\OpenCartStockSync\runs\stock-sync-20260516",
                "created_at": "2026-05-16T10:00:00Z",
                "counts": {
                    "output_rows": 120,
                    "disabled_count": 8,
                    "price_zero_forced_disabled_count": 2,
                },
                "safety": {
                    "warnings": ["Manual review recommended."],
                    "hard_failures": [],
                },
                "orchestrator": {"host": "ERPSERVER"},
            }
        ),
        encoding="utf-8",
    )
    client = _client(monkeypatch, tmp_path, enabled=False)
    monkeypatch.setenv("ECOMMERCE_STOCK_SYNC_LATEST_REVIEW_PATH", str(review_path))

    response = client.get("/api/stock-sync/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["status"] == "reviewed"
    assert payload["ok_to_upload"] is True
    assert payload["run_id"] == "stock-sync-20260516"
    assert payload["counts"]["output_rows"] == 120
    assert payload["warnings"] == ["Manual review recommended."]
    assert payload["hard_failures"] == []
    assert payload["orchestrator"] == {"host": "ERPSERVER"}
