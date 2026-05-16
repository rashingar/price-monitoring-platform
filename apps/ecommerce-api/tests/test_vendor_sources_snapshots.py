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
from ecommerce.db.models import Base  # noqa: E402
from ecommerce.db.models.catalog import CatalogProductRow  # noqa: E402
from ecommerce.db.models.products import ProductSource  # noqa: E402
from ecommerce.db.models.price_monitoring import PriceObservation  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.db.repositories.source_urls import create_or_update_imported_source_url  # noqa: E402
from ecommerce.source_capture.types import CaptureResult, CaptureSnapshotPayload, ParsedPriceObservation  # noqa: E402
from ecommerce.vendor_sources.capture import SourceUrlCaptureRunResult, capture_selected_source_urls  # noqa: E402


NOW = datetime(2026, 5, 5, 12, tzinfo=timezone.utc)


def _snapshot(fixtures_root: Path, *parts: str) -> dict:
    return json.loads((fixtures_root / "golden_snapshots" / Path(*parts)).read_text(encoding="utf-8"))


def _database_url(tmp_path: Path) -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'vendor-sources-snapshot.db'}"
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


def _selection_snapshot(result: SourceUrlCaptureRunResult, captured_urls: list[str]) -> dict:
    return {
        "status": result.status,
        "used_source_urls": result.used_source_urls,
        "source": result.source,
        "vendor": result.vendor,
        "selected_catalog_product_count": result.selected_catalog_product_count,
        "selected_source_url_count": result.selected_source_url_count,
        "selected_product_source_count": result.selected_product_source_count,
        "succeeded_count": result.succeeded_count,
        "failed_count": result.failed_count,
        "warnings": result.warnings,
        "captured_urls": captured_urls,
        "source_urls": [
            {
                "source_name": item["source_name"],
                "status": item["status"],
                "url_normalized": item["url_normalized"],
            }
            for item in result.source_urls
        ],
    }


def test_vendor_source_selection_snapshot(fixtures_root: Path, tmp_path: Path) -> None:
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

        assert session.query(PriceObservation).count() == 1

    assert _selection_snapshot(result, captured_urls) == _snapshot(fixtures_root, "vendor_sources", "selection", "selection.expected.json")


def test_vendor_source_status_filtering_snapshot(fixtures_root: Path, tmp_path: Path) -> None:
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

    assert _selection_snapshot(result, captured_urls) == _snapshot(fixtures_root, "vendor_sources", "selection", "status_filtering.expected.json")


def test_vendor_source_run_result_serialization_snapshot(fixtures_root: Path) -> None:
    result = SourceUrlCaptureRunResult(
        status="completed_with_partial_failures",
        used_source_urls=True,
        source="electronet",
        vendor="electronet",
        run_id="vendor-capture-1",
        observation_batch_id="vendor-capture-1",
        source_filter="electronet",
        selected_catalog_product_count=2,
        selected_source_url_count=2,
        selected_product_source_count=2,
        succeeded_count=1,
        failed_count=1,
        warnings=["one source failed"],
        items=[
            {"product_source_id": 1, "vendor": "electronet", "status": "success"},
            {"product_source_id": 2, "vendor": "electronet", "status": "failed", "error_code": "timeout"},
        ],
        source_urls=[
            {"id": 1, "source_name": "electronet", "status": "active", "url_normalized": "https://www.electronet.gr/p/1"},
            {"id": 2, "source_name": "electronet", "status": "active", "url_normalized": "https://www.electronet.gr/p/2"},
        ],
        result_path=Path("vendor_source_capture_result.json"),
    )

    payload = result.to_dict()
    actual = {
        key: payload[key]
        for key in [
            "status",
            "used_source_urls",
            "source",
            "vendor",
            "run_id",
            "observation_batch_id",
            "source_filter",
            "selected_catalog_product_count",
            "selected_source_url_count",
            "selected_product_source_count",
            "succeeded_count",
            "failed_count",
            "warnings",
            "items",
            "source_urls",
        ]
    }
    actual["result_file_name"] = Path(payload["result_path"]).name

    assert actual == _snapshot(fixtures_root, "vendor_sources", "run_result", "serialization.expected.json")


def test_vendor_source_capture_api_response_snapshot(fixtures_root: Path, tmp_path: Path, monkeypatch) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    monkeypatch.setattr(routes_vendor_sources, "_require_vendor_sources_database_ready", lambda: None)
    capture_kwargs: dict[str, object] = {}

    def fake_run_vendor_source_capture(*_args: object, **kwargs: object) -> SourceUrlCaptureRunResult:
        capture_kwargs.update(kwargs)
        return SourceUrlCaptureRunResult(
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
        )

    monkeypatch.setattr(
        routes_vendor_sources,
        "run_vendor_source_capture",
        fake_run_vendor_source_capture,
    )

    response = TestClient(create_app()).post(
        "/api/vendor-sources/captures/runs",
        json={"source_name": "electronet", "limit": 1, "include_not_due": True},
    )

    assert response.status_code == 200
    assert capture_kwargs["source_name"] == "electronet"
    assert capture_kwargs["vendor_slug"] is None
    payload = response.json()
    actual = {
        key: payload[key]
        for key in [
            "status",
            "used_source_urls",
            "source",
            "vendor",
            "selected_catalog_product_count",
            "selected_source_url_count",
            "selected_product_source_count",
            "selected_count",
            "succeeded_count",
            "failed_count",
            "warnings",
            "items",
            "run_id",
            "observation_batch_id",
        ]
    }

    assert actual == _snapshot(fixtures_root, "vendor_sources", "api_response", "capture_run.expected.json")
