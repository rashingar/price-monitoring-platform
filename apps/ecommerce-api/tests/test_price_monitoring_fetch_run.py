import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api import routes_price_monitoring  # noqa: E402
from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.price_monitoring import fetch_run as fetch_run_module  # noqa: E402
from ecommerce.price_monitoring.fetch_run import (  # noqa: E402
    PriceMonitoringFetchError,
    run_price_monitoring_fetch,
)
from ecommerce.vendor_sources.capture import SourceUrlCaptureRunResult  # noqa: E402
from ecommerce.price_monitoring.fetch_execution import wait_for_worker_idle  # noqa: E402
from test_price_monitoring_execution_utils import install_fake_execution_child  # noqa: E402


@pytest.fixture(autouse=True)
def _allow_monitoring_api_without_real_db(monkeypatch):
    monkeypatch.setattr(routes_price_monitoring, "require_database_ready_for_price_monitoring", lambda: None)


def _write_run(run_dir: Path, *, source: str = "skroutz", input_csv: bool = True) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    if input_csv:
        (run_dir / "input.csv").write_text(
            "model,mpn,name,price\n"
            "005606,MPN-1,Product One,123.45\n",
            encoding="utf-8",
        )
    (run_dir / "selection_summary.json").write_text(
        json.dumps({"run_id": run_dir.name, "source": source}),
        encoding="utf-8",
    )


def _fake_source_capture_result(run_dir: Path, source: str = "skroutz") -> SourceUrlCaptureRunResult:
    return SourceUrlCaptureRunResult(
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
        source_urls=[{"id": 1, "status": "active", "source_name": source}],
        result_path=run_dir / "source_url_capture_result.json",
        run_id="vendor-capture-1",
        observation_batch_id="vendor-capture-1",
    )


def _install_fake_source_capture(monkeypatch) -> dict[str, str]:
    captured: dict[str, str] = {}

    def fake_capture(run_dir: Path, source: str, **_kwargs) -> SourceUrlCaptureRunResult:
        captured["source"] = source
        result = _fake_source_capture_result(Path(run_dir), source)
        result.result_path.write_text(json.dumps(result.to_dict()), encoding="utf-8")
        return result

    monkeypatch.setattr("ecommerce.price_monitoring.fetch_run.capture_selected_source_urls_for_run", fake_capture)
    return captured


def _install_missing_source_capture(monkeypatch) -> None:
    def fake_capture(run_dir: Path, source: str, **_kwargs) -> SourceUrlCaptureRunResult:
        return SourceUrlCaptureRunResult(
            status="no_active_source_urls",
            used_source_urls=False,
            source=source,
            vendor=source,
            selected_catalog_product_count=1,
            selected_source_url_count=0,
            selected_product_source_count=0,
            succeeded_count=0,
            failed_count=0,
            warnings=["No active source URLs exist."],
            items=[],
            source_urls=[],
            result_path=Path(run_dir) / "source_url_capture_result.json",
            run_id="vendor-capture-missing",
            observation_batch_id="vendor-capture-missing",
        )

    monkeypatch.setattr("ecommerce.price_monitoring.fetch_run.capture_selected_source_urls_for_run", fake_capture)


def test_source_is_read_from_selection_summary_when_not_supplied(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run-1"
    _write_run(run_dir, source="bestprice")
    captured = _install_fake_source_capture(monkeypatch)

    result = run_price_monitoring_fetch(run_dir)

    assert captured["source"] == "bestprice"
    assert result.source == "bestprice"
    assert result.fetch_input_mode == "source_urls"


def test_explicit_source_overrides_selection_summary(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run-1"
    _write_run(run_dir, source="skroutz")
    captured = _install_fake_source_capture(monkeypatch)

    result = run_price_monitoring_fetch(run_dir, source="bestprice")

    assert captured["source"] == "bestprice"
    assert result.source == "bestprice"


def test_successful_fetch_writes_fetch_result_json_and_does_not_call_legacy_fetch(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run-1"
    _write_run(run_dir)
    _install_fake_source_capture(monkeypatch)

    result = run_price_monitoring_fetch(run_dir)

    fetch_result_path = run_dir / "fetch_result.json"
    assert result.status == "fetch_completed"
    assert result.enriched_csv_path is None
    assert result.fetch_summary_path is None
    assert result.fetch_input_mode == "source_urls"
    assert result.legacy_marketplace_fetch_used is False
    assert result.source_url_capture_used is True
    assert result.source_url_capture_run_id == "vendor-capture-1"
    assert result.observation_batch_id == "vendor-capture-1"
    assert fetch_result_path.exists()

    payload = json.loads(fetch_result_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-1"
    assert payload["source"] == "skroutz"
    assert payload["status"] == "fetch_completed"
    assert payload["fetch_input_mode"] == "source_urls"
    assert payload["legacy_marketplace_fetch_used"] is False
    assert payload["source_url_capture_run_id"] == "vendor-capture-1"
    assert payload["observation_batch_id"] == "vendor-capture-1"
    assert payload["error"] == ""


def test_price_monitoring_fetch_has_no_core_run_fetch_hook(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run-1"
    _write_run(run_dir)
    _install_fake_source_capture(monkeypatch)
    assert not hasattr(fetch_run_module, "run_fetch")

    result = run_price_monitoring_fetch(run_dir)

    assert result.status == "fetch_completed"
    assert result.fetch_input_mode == "source_urls"
    assert result.legacy_marketplace_fetch_used is False


def test_fetch_missing_active_source_url_error_points_to_vendor_sources(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run-1"
    _write_run(run_dir)
    _install_missing_source_capture(monkeypatch)

    with pytest.raises(PriceMonitoringFetchError) as exc_info:
        run_price_monitoring_fetch(run_dir)

    assert "missing_active_source_url" in str(exc_info.value)
    assert "Vendor Sources" in str(exc_info.value)
    assert exc_info.value.result is not None
    assert exc_info.value.result.legacy_marketplace_fetch_used is False


def test_missing_selection_summary_rejects_fetch_without_one_source(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    (run_dir / "input.csv").write_text("model,mpn,name,price\n005606,MPN-1,Product One,123.45\n", encoding="utf-8")
    _install_fake_source_capture(monkeypatch)

    with pytest.raises(ValueError) as exc_info:
        run_price_monitoring_fetch(run_dir)

    assert "requires one source/vendor" in str(exc_info.value)
    result = run_price_monitoring_fetch(run_dir, source="skroutz")
    assert result.source == "skroutz"


def test_fetch_rejects_all_source(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run-1"
    _write_run(run_dir, source="all")
    _install_fake_source_capture(monkeypatch)

    with pytest.raises(ValueError) as exc_info:
        run_price_monitoring_fetch(run_dir)

    assert "source=all is not allowed" in str(exc_info.value)


def test_api_missing_run_folder_returns_404(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    response = TestClient(create_app()).post(
        "/api/price-monitoring/runs/missing/fetch",
        json={"source": None, "catalog_url": None},
    )

    assert response.status_code == 404
    assert "run folder not found" in response.json()["detail"]


def test_api_missing_input_csv_returns_404(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir, input_csv=False)

    response = TestClient(create_app()).post(
        "/api/price-monitoring/runs/run-1/fetch",
        json={"source": None, "catalog_url": None},
    )

    assert response.status_code == 404
    assert "input.csv not found" in response.json()["detail"]


def test_api_accepts_arbitrary_source_filter(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)
    install_fake_execution_child(monkeypatch, tmp_path, mode="success")

    response = TestClient(create_app()).post(
        "/api/price-monitoring/runs/run-1/fetch",
        json={"source": "other", "catalog_url": None},
    )

    assert response.status_code == 202
    assert response.json()["source"] == "other"
    assert wait_for_worker_idle()


def test_api_fetch_failure_returns_clear_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)

    install_fake_execution_child(monkeypatch, tmp_path, mode="fail")

    response = TestClient(create_app()).post(
        "/api/price-monitoring/runs/run-1/fetch",
        json={"source": None, "catalog_url": None},
    )

    assert response.status_code == 202
    assert wait_for_worker_idle()
    payload = TestClient(create_app()).get("/api/price-monitoring/runs/run-1/fetch").json()
    assert payload["status"] == "failed"
    assert payload["error"] == "Fetch command failed"


def test_api_successful_fetch_returns_artifacts_and_get_reads_fetch_result(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)

    install_fake_execution_child(monkeypatch, tmp_path, mode="success")
    client = TestClient(create_app())

    post_response = client.post(
        "/api/price-monitoring/runs/run-1/fetch",
        json={"source": None, "catalog_url": None},
    )

    assert post_response.status_code == 202
    post_payload = post_response.json()
    assert post_payload["status"] in {"queued", "running", "succeeded"}
    assert post_payload["execution_id"]
    assert post_payload["source"] == "skroutz"
    assert wait_for_worker_idle()

    get_response = client.get("/api/price-monitoring/runs/run-1/fetch")
    assert get_response.status_code == 200
    get_payload = get_response.json()
    assert get_payload["status"] == "succeeded"
    assert get_payload["enriched_csv_path"] == ""
    assert get_payload["fetch_input_mode"] == "source_urls"
    assert get_payload["legacy_marketplace_fetch_used"] is False
    assert Path(get_payload["fetch_result_path"]).exists()
