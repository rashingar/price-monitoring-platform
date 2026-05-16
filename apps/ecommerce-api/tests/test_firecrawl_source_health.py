import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models import Base  # noqa: E402
from ecommerce.db.models.catalog import CatalogProductRow  # noqa: E402
from ecommerce.db.models.source_urls import SourceUrl  # noqa: E402
from ecommerce.db.models.products import ProductSource  # noqa: E402
from ecommerce.db.repositories.source_urls import create_or_update_imported_source_url  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.source_capture.firecrawl_health import (  # noqa: E402
    firecrawl_health_reason,
    firecrawl_source_review_failure_threshold,
)
from ecommerce.source_capture.scheduled import capture_due_product_sources  # noqa: E402
from ecommerce.source_capture.types import CaptureResult, CaptureSnapshotPayload  # noqa: E402
from ecommerce.vendor_sources.capture import recapture_product_source  # noqa: E402
from ecommerce.vendor_sources.coverage import source_health_items  # noqa: E402

NOW = datetime(2026, 5, 16, tzinfo=timezone.utc)


def _database_url(tmp_path: Path) -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'firecrawl-health.db'}"
    Base.metadata.create_all(get_engine(database_url))
    return database_url


def _catalog_product(session, *, model: str) -> CatalogProductRow:
    row = CatalogProductRow(
        catalog_source="sourceCata",
        model=model,
        mpn=f"MPN-{model}",
        name="Source Product",
        category="",
        raw_category="",
        manufacturer="Brand",
        imported_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(row)
    session.flush()
    return row


def _add_source(session, *, model: str, vendor: str = "skroutz", status: str = "active") -> ProductSource:
    product = _catalog_product(session, model=model)
    url = {
        "skroutz": f"https://www.skroutz.gr/s/{model}/product.html",
        "bestprice": f"https://www.bestprice.gr/item/{model}/product.html",
        "electronet": f"https://www.electronet.gr/p/{model}",
    }[vendor]
    create_or_update_imported_source_url(
        session,
        catalog_product_id=product.id,
        url=url,
        source_name=vendor,
        trust_level="high_confidence",
        status=status,
    )
    return session.query(ProductSource).order_by(ProductSource.id.desc()).first()


def _firecrawl_failure(reason_code: str):
    def fake_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
        del url
        return CaptureResult(
            vendor_slug=vendor_slug or "skroutz",
            status="failed",
            snapshot=CaptureSnapshotPayload(
                capture_strategy="skroutz_firecrawl",
                page_url="https://www.skroutz.gr/s/1/product.html",
                response_status=403 if reason_code == "FIRECRAWL_API_FAILED" else None,
                data_quality_flags=[reason_code],
                error_code=reason_code,
                error_message="blocked" if reason_code == "FIRECRAWL_API_FAILED" else "parse failed",
                captured_at=NOW,
                fetched_at=NOW,
                parsed_at=NOW,
            ),
            error_code=reason_code,
            error_message="blocked" if reason_code == "FIRECRAWL_API_FAILED" else "parse failed",
        )

    return fake_capture


def _bestprice_failure(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
    del url
    return CaptureResult(
        vendor_slug=vendor_slug or "bestprice",
        status="failed",
        snapshot=CaptureSnapshotPayload(
            capture_strategy="bestprice_httpx_html",
            page_url="https://www.bestprice.gr/item/1/product.html",
            data_quality_flags=["FIRECRAWL_PARSE_FAILED", "firecrawl_parse_failed"],
            error_code="FIRECRAWL_PARSE_FAILED",
            error_message="parse failed",
            captured_at=NOW,
            fetched_at=NOW,
            parsed_at=NOW,
        ),
        error_code="FIRECRAWL_PARSE_FAILED",
        error_message="parse failed",
    )


def test_firecrawl_threshold_config(monkeypatch) -> None:
    monkeypatch.delenv("ECOMMERCE_FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD", raising=False)
    assert firecrawl_source_review_failure_threshold() == 2
    monkeypatch.setenv("ECOMMERCE_FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD", "4")
    assert firecrawl_source_review_failure_threshold() == 4
    monkeypatch.setenv("ECOMMERCE_FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD", "bad")
    assert firecrawl_source_review_failure_threshold() == 2
    monkeypatch.setenv("ECOMMERCE_FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD", "0")
    assert firecrawl_source_review_failure_threshold() == 1


def test_source_health_maps_firecrawl_failure_reason(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    with session_scope(database_url) as session:
        _add_source(session, model="SK-REASON")
        capture_due_product_sources(session, capture_fn=_firecrawl_failure("FIRECRAWL_PARSE_FAILED"))
        payload = source_health_items(session, vendor="skroutz")

    assert payload["items"][0]["last_error_code"] == "FIRECRAWL_PARSE_FAILED"
    assert payload["items"][0]["health_reason"] == "firecrawl_parse_failed"
    assert firecrawl_health_reason(capture_strategy="skroutz_firecrawl", error_code="FIRECRAWL_TIMEOUT") == "firecrawl_timeout"


def test_repeated_firecrawl_blocked_moves_skroutz_source_url_to_needs_review(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ECOMMERCE_FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD", "2")
    database_url = _database_url(tmp_path)
    with session_scope(database_url) as session:
        _add_source(session, model="SK-BLOCKED")
        capture_due_product_sources(session, capture_fn=_firecrawl_failure("FIRECRAWL_API_FAILED"))
        assert session.query(SourceUrl).one().status == "active"
        capture_due_product_sources(session, capture_fn=_firecrawl_failure("FIRECRAWL_API_FAILED"))
        source_url = session.query(SourceUrl).one()

    assert source_url.status == "needs_review"
    assert "firecrawl_blocked" in source_url.notes


def test_repeated_firecrawl_parse_failed_moves_skroutz_source_url_to_needs_review(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ECOMMERCE_FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD", "2")
    database_url = _database_url(tmp_path)
    with session_scope(database_url) as session:
        _add_source(session, model="SK-PARSE")
        capture_due_product_sources(session, capture_fn=_firecrawl_failure("FIRECRAWL_PARSE_FAILED"))
        capture_due_product_sources(session, capture_fn=_firecrawl_failure("FIRECRAWL_PARSE_FAILED"))
        source_url = session.query(SourceUrl).one()

    assert source_url.status == "needs_review"
    assert "firecrawl_parse_failed" in source_url.notes


def test_threshold_one_escalates_after_one_matching_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ECOMMERCE_FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD", "1")
    database_url = _database_url(tmp_path)
    with session_scope(database_url) as session:
        _add_source(session, model="SK-ONE")
        capture_due_product_sources(session, capture_fn=_firecrawl_failure("FIRECRAWL_PARSE_FAILED"))
        source_url = session.query(SourceUrl).one()

    assert source_url.status == "needs_review"


def test_one_off_firecrawl_failure_does_not_escalate_when_threshold_two(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ECOMMERCE_FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD", "2")
    database_url = _database_url(tmp_path)
    with session_scope(database_url) as session:
        _add_source(session, model="SK-ONCE")
        capture_due_product_sources(session, capture_fn=_firecrawl_failure("FIRECRAWL_PARSE_FAILED"))
        source_url = session.query(SourceUrl).one()

    assert source_url.status == "active"


def test_bestprice_is_not_escalated_by_firecrawl_like_flags(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ECOMMERCE_FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD", "1")
    database_url = _database_url(tmp_path)
    with session_scope(database_url) as session:
        _add_source(session, model="BP-ONE", vendor="bestprice")
        capture_due_product_sources(session, vendor_slug="bestprice", capture_fn=_bestprice_failure)
        source_url = session.query(SourceUrl).one()

    assert source_url.status == "active"


def test_manual_recapture_can_trigger_firecrawl_escalation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ECOMMERCE_FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD", "1")
    database_url = _database_url(tmp_path)
    with session_scope(database_url) as session:
        source = _add_source(session, model="SK-MANUAL")
        source_id = source.id
        response = recapture_product_source(
            session,
            product_source_id=source_id,
            capture_fn=_firecrawl_failure("FIRECRAWL_PARSE_FAILED"),
            runs_dir=tmp_path / "runs",
        )
        source_url = session.query(SourceUrl).one()

    assert response["product_source_id"] == source_id
    assert response["health_reason"] == "firecrawl_parse_failed"
    assert source_url.status == "needs_review"


def test_manual_recapture_route_captures_exactly_one_and_forces_not_due(tmp_path: Path, monkeypatch) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    captured_urls: list[str] = []

    def successful_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
        captured_urls.append(url)
        return CaptureResult(
            vendor_slug=vendor_slug or "electronet",
            status="success",
            snapshot=CaptureSnapshotPayload(
                capture_strategy="electronet_httpx_html",
                page_url=url,
                captured_at=NOW,
                fetched_at=NOW,
                parsed_at=NOW,
            ),
        )

    with session_scope(database_url) as session:
        first = _add_source(session, model="EL-ONE", vendor="electronet")
        _add_source(session, model="EL-TWO", vendor="electronet")
        first.last_success_at = NOW
        session.flush()
        first_id = first.id

    monkeypatch.setattr("ecommerce.vendor_sources.capture_service.capture_source_url", successful_capture)
    response = TestClient(create_app()).post(f"/api/vendor-sources/source-health/{first_id}/recapture")

    assert response.status_code == 200
    assert response.json()["product_source_id"] == first_id
    assert response.json()["status"] == "success"
    assert captured_urls == ["https://www.electronet.gr/p/EL-ONE"]


def test_manual_recapture_route_rejects_missing_and_inactive_sources(tmp_path: Path, monkeypatch) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    with session_scope(database_url) as session:
        inactive = _add_source(session, model="EL-INACTIVE", vendor="electronet")
        inactive.active = False
        session.flush()
        inactive_id = inactive.id

    client = TestClient(create_app())
    assert client.post("/api/vendor-sources/source-health/999999/recapture").status_code == 404
    assert client.post(f"/api/vendor-sources/source-health/{inactive_id}/recapture").status_code == 404
