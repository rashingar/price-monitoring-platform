import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api import routes_vendor_sources  # noqa: E402
from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models import Base, CatalogProductRow, PriceObservation, ProductSource, VendorSourceCaptureRun  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.db.source_url_repository import create_or_update_imported_source_url  # noqa: E402
from ecommerce.source_capture.types import CaptureResult, CaptureSnapshotPayload, ParsedPriceObservation  # noqa: E402
from ecommerce.vendor_sources.capture import (  # noqa: E402
    SourceUrlCaptureRunResult,
    capture_selected_source_urls,
    capture_selected_source_urls_for_run,
    run_vendor_source_capture,
)


NOW = datetime(2026, 5, 5, 12, tzinfo=timezone.utc)


def _database_url(tmp_path: Path) -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'vendor-sources.db'}"
    Base.metadata.create_all(get_engine(database_url))
    return database_url


def _catalog_product(session, *, model: str) -> CatalogProductRow:
    row = CatalogProductRow(
        catalog_source="sourceCata",
        model=model,
        mpn=f"MPN-{model}",
        name="Electronet Product",
        category="",
        raw_category="",
        manufacturer="LG",
        imported_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(row)
    session.flush()
    return row


def _fake_electronet_capture(captured_urls: list[str]):
    def fake_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
        captured_urls.append(url)
        return CaptureResult(
            vendor_slug=vendor_slug or "electronet",
            status="success",
            snapshot=CaptureSnapshotPayload(
                capture_strategy="vendor-sources-electronet-test",
                page_url=url,
                captured_at=NOW,
                fetched_at=NOW,
                parsed_at=NOW,
            ),
            price_observations=(ParsedPriceObservation(price=Decimal("499.90"), availability="available"),),
        )

    return fake_capture


def test_vendor_sources_capture_selects_electronet_active_urls(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    captured_urls: list[str] = []

    with session_scope(database_url) as session:
        product = _catalog_product(session, model="EL-ACTIVE")
        create_or_update_imported_source_url(
            session,
            catalog_product_id=product.id,
            url="https://www.electronet.gr/p/el-active",
            source_name="electronet",
            trust_level="high_confidence",
            status="active",
        )

        result = capture_selected_source_urls(
            session,
            run_id="vendor-run-1",
            source="electronet",
            catalog_product_ids=[product.id],
            capture_fn=_fake_electronet_capture(captured_urls),
        )

        assert result.status == "completed"
        assert result.used_source_urls is True
        assert result.source == "electronet"
        assert result.vendor == "electronet"
        assert result.selected_catalog_product_count == 1
        assert result.selected_source_url_count == 1
        assert result.selected_product_source_count == 1
        assert result.succeeded_count == 1
        assert captured_urls == ["https://www.electronet.gr/p/el-active"]
        assert session.query(PriceObservation).count() == 1


def test_vendor_sources_capture_excludes_ineligible_source_urls_and_disabled_product_sources(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    captured_urls: list[str] = []

    with session_scope(database_url) as session:
        active_product = _catalog_product(session, model="EL-ELIGIBLE")
        disabled_product_source_product = _catalog_product(session, model="EL-PS-DISABLED")
        for status in ["active", "broken", "disabled", "needs_review", "redirected"]:
            create_or_update_imported_source_url(
                session,
                catalog_product_id=active_product.id,
                url=f"https://www.electronet.gr/p/{status}",
                source_name="electronet",
                trust_level="high_confidence",
                status=status,
            )
        create_or_update_imported_source_url(
            session,
            catalog_product_id=disabled_product_source_product.id,
            url="https://www.electronet.gr/p/product-source-disabled",
            source_name="electronet",
            trust_level="high_confidence",
            status="active",
        )
        disabled_source = (
            session.query(ProductSource)
            .filter(ProductSource.source_url == "https://www.electronet.gr/p/product-source-disabled")
            .one()
        )
        disabled_source.active = False
        session.flush()

        result = capture_selected_source_urls(
            session,
            run_id="vendor-run-2",
            source="electronet",
            catalog_product_ids=[active_product.id, disabled_product_source_product.id],
            capture_fn=_fake_electronet_capture(captured_urls),
        )

        assert result.selected_source_url_count == 1
        assert result.selected_product_source_count == 1
        assert result.succeeded_count == 1
        assert captured_urls == ["https://www.electronet.gr/p/active"]


def test_vendor_sources_capture_for_run_writes_result_counts_without_live_http(tmp_path: Path, monkeypatch) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    run_dir = tmp_path / "run-electronet"
    run_dir.mkdir()
    (run_dir / "selection_summary.json").write_text(
        json.dumps({"selected_items": [{"catalog_product_id": 1}], "source": "electronet"}),
        encoding="utf-8",
    )
    captured_urls: list[str] = []

    with session_scope(database_url) as session:
        product = _catalog_product(session, model="EL-WRITE")
        assert product.id == 1
        create_or_update_imported_source_url(
            session,
            catalog_product_id=product.id,
            url="https://www.electronet.gr/p/write-result",
            source_name="electronet",
            trust_level="high_confidence",
            status="active",
        )

    result = capture_selected_source_urls_for_run(
        run_dir,
        "electronet",
        capture_fn=_fake_electronet_capture(captured_urls),
    )

    payload = json.loads((run_dir / "source_url_capture_result.json").read_text(encoding="utf-8"))
    assert result.succeeded_count == 1
    assert captured_urls == ["https://www.electronet.gr/p/write-result"]
    assert payload["status"] == "completed"
    assert payload["source"] == "electronet"
    assert payload["vendor"] == "electronet"
    assert payload["used_source_urls"] is True
    assert payload["selected_catalog_product_count"] == 1
    assert payload["selected_source_url_count"] == 1
    assert payload["selected_product_source_count"] == 1
    assert payload["succeeded_count"] == 1
    assert payload["failed_count"] == 0
    assert payload["result_path"].endswith("source_url_capture_result.json")
    assert payload["run_id"] == result.run_id
    assert payload["observation_batch_id"] == result.run_id
    with session_scope(database_url) as session:
        row = session.query(VendorSourceCaptureRun).filter_by(run_id=result.run_id).one()
        observation = session.query(PriceObservation).one()
        assert row.observation_batch_id == result.run_id
        assert observation.run_id == run_dir.name
        assert observation.observation_batch_id == result.run_id


def test_vendor_sources_capture_api_returns_required_payload(monkeypatch) -> None:
    monkeypatch.setattr(routes_vendor_sources, "_require_vendor_sources_database_ready", lambda: None)
    monkeypatch.setattr(
        routes_vendor_sources,
        "run_vendor_source_capture",
        lambda *_args, **_kwargs: SourceUrlCaptureRunResult(
            status="completed",
            used_source_urls=True,
            source="electronet",
            vendor="electronet",
            run_id="vendor-capture-1",
            observation_batch_id="vendor-capture-1",
            source_filter="electronet",
            selected_catalog_product_count=1,
            selected_source_url_count=1,
            selected_product_source_count=1,
            succeeded_count=1,
            failed_count=0,
            warnings=[],
            items=[{"product_source_id": 1, "vendor": "electronet", "status": "success"}],
            source_urls=[{"id": 1, "source_name": "electronet", "status": "active"}],
            result_path=None,
        ),
    )

    response = TestClient(create_app()).post(
        "/api/vendor-sources/captures/runs",
        json={"vendor": "electronet", "limit": 1, "include_not_due": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["used_source_urls"] is True
    assert payload["source"] == "electronet"
    assert payload["vendor"] == "electronet"
    assert payload["selected_catalog_product_count"] == 1
    assert payload["selected_source_url_count"] == 1
    assert payload["selected_product_source_count"] == 1
    assert payload["succeeded_count"] == 1
    assert payload["failed_count"] == 0
    assert payload["warnings"] == []
    assert payload["items"][0]["status"] == "success"
    assert payload["run_id"] == "vendor-capture-1"
    assert payload["observation_batch_id"] == "vendor-capture-1"

    compatibility = TestClient(create_app()).post(
        "/api/vendor-sources/captures/run",
        json={"vendor": "electronet", "limit": 1, "include_not_due": True},
    )

    assert compatibility.status_code == 200
    assert compatibility.json()["deprecated"] is True
    assert compatibility.json()["replacement_endpoint"] == "/api/vendor-sources/captures/runs"


def test_vendor_sources_capture_api_requires_source_unless_admin_diagnostic(monkeypatch) -> None:
    monkeypatch.setattr(routes_vendor_sources, "_require_vendor_sources_database_ready", lambda: None)

    def fake_run(*_args, **kwargs):
        if not kwargs.get("admin_all_sources"):
            raise ValueError("Vendor Sources capture requires one source/vendor unless admin_all_sources=true for diagnostic all-source capture.")
        return SourceUrlCaptureRunResult(
            status="dry_run",
            used_source_urls=False,
            source="",
            vendor=None,
            run_id="vendor-capture-admin",
            observation_batch_id="vendor-capture-admin",
            source_filter=None,
            selected_catalog_product_count=0,
            selected_source_url_count=0,
            selected_product_source_count=0,
            succeeded_count=0,
            failed_count=0,
            warnings=[],
            items=[],
            source_urls=[],
            result_path=None,
        )

    monkeypatch.setattr(routes_vendor_sources, "run_vendor_source_capture", fake_run)
    client = TestClient(create_app())

    missing = client.post("/api/vendor-sources/captures/runs", json={"dry_run": True})
    admin = client.post("/api/vendor-sources/captures/runs", json={"dry_run": True, "admin_all_sources": True})

    assert missing.status_code == 400
    assert "admin_all_sources=true" in missing.json()["detail"]
    assert admin.status_code == 200
    assert admin.json()["observation_batch_id"] == "vendor-capture-admin"


def test_vendor_sources_capture_run_history_row_is_created(tmp_path: Path, monkeypatch) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    monkeypatch.setattr(routes_vendor_sources, "_require_vendor_sources_database_ready", lambda: None)
    captured_urls: list[str] = []
    run_id = ""

    with session_scope(database_url) as session:
        product = _catalog_product(session, model="EL-HISTORY")
        create_or_update_imported_source_url(
            session,
            catalog_product_id=product.id,
            url="https://www.electronet.gr/p/history",
            source_name="electronet",
            trust_level="high_confidence",
            status="active",
        )

        result = run_vendor_source_capture(
            session,
            vendor_slug="electronet",
            include_not_due=True,
            capture_fn=_fake_electronet_capture(captured_urls),
            runs_dir=tmp_path / "vendor-captures",
        )

        row = session.query(VendorSourceCaptureRun).filter_by(run_id=result.run_id).one()
        run_id = result.run_id
        assert row.status == "completed"
        assert row.observation_batch_id == result.run_id
        assert row.source_filter == "electronet"
        assert row.selected_source_url_count == 1
        assert row.selected_product_source_count == 1
        assert row.succeeded_count == 1
        assert row.result_path and row.result_path.endswith("vendor_source_capture_result.json")
        assert captured_urls == ["https://www.electronet.gr/p/history"]
        observation = session.query(PriceObservation).one()
        assert observation.observation_batch_id == result.run_id

    client = TestClient(create_app())
    history = client.get("/api/vendor-sources/captures/runs")
    detail = client.get(f"/api/vendor-sources/captures/runs/{run_id}")
    artifacts = client.get(f"/api/vendor-sources/captures/runs/{run_id}/artifacts")

    assert history.status_code == 200
    assert history.json()["items"][0]["run_id"] == run_id
    assert history.json()["items"][0]["observation_batch_id"] == run_id
    assert detail.status_code == 200
    assert detail.json()["run_id"] == run_id
    assert detail.json()["observation_batch_id"] == run_id
    assert artifacts.status_code == 200
    assert artifacts.json()["items"][0]["name"] == "vendor_source_capture_result.json"


def test_vendor_sources_capture_run_requires_admin_flag_for_all_active_sources(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    captured_urls: list[str] = []

    with session_scope(database_url) as session:
        electronet_product = _catalog_product(session, model="EL-ALL")
        skroutz_product = _catalog_product(session, model="SK-ALL")
        create_or_update_imported_source_url(
            session,
            catalog_product_id=electronet_product.id,
            url="https://www.electronet.gr/p/all",
            source_name="electronet",
            trust_level="high_confidence",
            status="active",
        )
        create_or_update_imported_source_url(
            session,
            catalog_product_id=skroutz_product.id,
            url="https://www.skroutz.gr/s/1/all.html",
            source_name="skroutz",
            trust_level="high_confidence",
            status="active",
        )

        try:
            run_vendor_source_capture(
                session,
                include_not_due=True,
                capture_fn=_fake_electronet_capture(captured_urls),
                runs_dir=tmp_path / "vendor-captures",
            )
        except ValueError as exc:
            assert "admin_all_sources=true" in str(exc)
        else:
            raise AssertionError("all-source capture should require admin_all_sources=true")

        result = run_vendor_source_capture(
            session,
            include_not_due=True,
            admin_all_sources=True,
            capture_fn=_fake_electronet_capture(captured_urls),
            runs_dir=tmp_path / "vendor-captures",
        )

        assert result.source_filter is None
        assert result.observation_batch_id == result.run_id
        assert result.selected_source_url_count == 2
        assert result.selected_product_source_count == 2
        assert sorted(captured_urls) == ["https://www.electronet.gr/p/all", "https://www.skroutz.gr/s/1/all.html"]


def test_vendor_sources_capture_run_source_filter_only_selects_requested_source(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    captured_urls: list[str] = []

    with session_scope(database_url) as session:
        electronet_product = _catalog_product(session, model="EL-FILTER")
        skroutz_product = _catalog_product(session, model="SK-FILTER")
        create_or_update_imported_source_url(
            session,
            catalog_product_id=electronet_product.id,
            url="https://www.electronet.gr/p/filter",
            source_name="electronet",
            trust_level="high_confidence",
            status="active",
        )
        create_or_update_imported_source_url(
            session,
            catalog_product_id=skroutz_product.id,
            url="https://www.skroutz.gr/s/1/filter.html",
            source_name="skroutz",
            trust_level="high_confidence",
            status="active",
        )

        result = run_vendor_source_capture(
            session,
            source_name="electronet",
            include_not_due=True,
            capture_fn=_fake_electronet_capture(captured_urls),
            runs_dir=tmp_path / "vendor-captures",
        )

        assert result.source_filter == "electronet"
        assert result.selected_source_url_count == 1
        assert result.selected_product_source_count == 1
        assert captured_urls == ["https://www.electronet.gr/p/filter"]


def test_vendor_sources_capture_run_excludes_ineligible_source_url_statuses(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    captured_urls: list[str] = []

    with session_scope(database_url) as session:
        product = _catalog_product(session, model="EL-STATUS")
        for status in ["active", "broken", "disabled", "needs_review", "redirected"]:
            create_or_update_imported_source_url(
                session,
                catalog_product_id=product.id,
                url=f"https://www.electronet.gr/p/run-{status}",
                source_name="electronet",
                trust_level="high_confidence",
                status=status,
            )

        result = run_vendor_source_capture(
            session,
            source_name="electronet",
            include_not_due=True,
            capture_fn=_fake_electronet_capture(captured_urls),
            runs_dir=tmp_path / "vendor-captures",
        )

        assert result.selected_source_url_count == 1
        assert result.selected_product_source_count == 1
        assert captured_urls == ["https://www.electronet.gr/p/run-active"]


def test_legacy_price_monitoring_source_url_capture_import_still_works() -> None:
    from ecommerce.price_monitoring import source_url_capture

    assert source_url_capture.run_vendor_source_capture is run_vendor_source_capture
