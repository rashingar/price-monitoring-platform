import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models import Base, CatalogProductRow, OfferObservation, PriceObservation, ProductSource, SourceCaptureSnapshot, SourceUrl, Vendor  # noqa: E402
from ecommerce.db.product_source_repository import create_product_from_source_urls  # noqa: E402
from ecommerce.db.source_url_repository import create_or_update_imported_source_url  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.price_monitoring.selection import SelectedPriceMonitoringProduct  # noqa: E402
from ecommerce.price_monitoring.source_url_coverage import compute_source_url_coverage  # noqa: E402
from ecommerce.source_capture.canonicalize_url import canonical_url_hash, canonicalize_url  # noqa: E402
from ecommerce.source_capture.detect_vendor import detect_vendor_slug  # noqa: E402
from ecommerce.source_capture.scheduled import capture_due_product_sources  # noqa: E402
from ecommerce.source_capture.types import CaptureResult, CaptureSnapshotPayload, ParsedOfferObservation, ParsedPriceObservation  # noqa: E402
from ecommerce.vendor_sources.capture import capture_selected_source_urls  # noqa: E402


NOW = datetime(2026, 5, 3, tzinfo=timezone.utc)


def _database_url(tmp_path: Path) -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'capture-contract.db'}"
    Base.metadata.create_all(get_engine(database_url))
    return database_url


def _catalog_product(session, *, model: str, mpn: str = "MPN-SRC-1", now: datetime = NOW) -> CatalogProductRow:
    row = CatalogProductRow(
        catalog_source="sourceCata",
        model=model,
        mpn=mpn,
        name="Source Product",
        category="",
        raw_category="",
        manufacturer="Brand",
        imported_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    return row


def test_vendor_detection_includes_active_and_scaffolded_vendors() -> None:
    assert detect_vendor_slug("https://www.electronet.gr/product/1") == "electronet"
    assert detect_vendor_slug("https://www.skroutz.gr/s/1") == "skroutz"
    assert detect_vendor_slug("https://www.plaisio.gr/product/1") == "plaisio"
    assert detect_vendor_slug("https://www.public.gr/product/1") == "public"
    assert detect_vendor_slug("https://www.kotsovolos.gr/product/1") == "kotsovolos"


def test_canonicalization_strips_tracking_and_hash_is_stable() -> None:
    first = canonicalize_url("HTTPS://WWW.Electronet.GR/p/1/?utm_source=x&sku=123&fbclid=y#reviews")
    second = canonicalize_url("https://www.electronet.gr/p/1?sku=123")

    assert first == "https://www.electronet.gr/p/1?sku=123"
    assert second == first
    assert canonical_url_hash(first) == canonical_url_hash(second)


def test_product_source_creation_deduplicates_and_seeds_vendor(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    with session_scope(database_url) as session:
        first = create_product_from_source_urls(
            session,
            model="LG OLED55C31LA",
            source_urls=["https://www.electronet.gr/p/1?utm_campaign=x"],
            capture=False,
        )
        second = create_product_from_source_urls(
            session,
            model="LG OLED55C31LA",
            source_urls=["https://www.electronet.gr/p/1"],
            capture=False,
        )

        assert first.product.id == second.product.id
        assert session.query(ProductSource).count() == 1
        source = session.query(ProductSource).one()
        assert source.vendor_id == session.query(Vendor).filter_by(slug="electronet").one().id
        assert source.first_seen_at is not None
        assert source.last_seen_at is not None


def test_active_catalog_source_url_creates_product_source_for_scheduled_capture(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)

    with session_scope(database_url) as session:
        catalog_product = _catalog_product(session, model="SRC-1")
        create_or_update_imported_source_url(
            session,
            catalog_product_id=catalog_product.id,
            url="https://www.skroutz.gr/s/123/source-product.html",
            source_name="skroutz",
            trust_level="high_confidence",
            status="active",
        )
        assert session.query(ProductSource).count() == 1

    captured_urls: list[str] = []

    def fake_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
        captured_urls.append(url)
        return CaptureResult(
            vendor_slug=vendor_slug or "skroutz",
            status="success",
            snapshot=CaptureSnapshotPayload(capture_strategy="source-url-sync-test", page_url=url, captured_at=NOW, fetched_at=NOW, parsed_at=NOW),
            offer_observations=(ParsedOfferObservation(seller_name="Store A", price=Decimal("199.99")),),
        )

    with session_scope(database_url) as session:
        summary = capture_due_product_sources(session, capture_fn=fake_capture)

        assert summary.selected_count == 1
        assert summary.succeeded_count == 1
        assert captured_urls == ["https://www.skroutz.gr/s/123/source-product.html"]
        assert session.query(OfferObservation).count() == 1


def test_monitoring_source_url_capture_uses_active_source_urls_and_mirrors_product_sources(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)

    with session_scope(database_url) as session:
        catalog_product = _catalog_product(session, model="RUN-SRC-1", mpn="MPN-RUN-SRC-1")
        create_or_update_imported_source_url(
            session,
            catalog_product_id=catalog_product.id,
            url="https://www.skroutz.gr/s/777/run-source.html",
            source_name="skroutz",
            trust_level="high_confidence",
            status="active",
        )

        captured_urls: list[str] = []

        def fake_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
            captured_urls.append(url)
            return CaptureResult(
                vendor_slug=vendor_slug or "skroutz",
                status="success",
                snapshot=CaptureSnapshotPayload(capture_strategy="monitoring-source-url-test", page_url=url, captured_at=NOW, fetched_at=NOW, parsed_at=NOW),
                offer_observations=(ParsedOfferObservation(seller_name="Store A", price=Decimal("99.90")),),
            )

        result = capture_selected_source_urls(
            session,
            run_id="run-1",
            source="skroutz",
            catalog_product_ids=[catalog_product.id],
            capture_fn=fake_capture,
        )

        assert result.used_source_urls is True
        assert result.selected_source_url_count == 1
        assert result.succeeded_count == 1
        assert captured_urls == ["https://www.skroutz.gr/s/777/run-source.html"]
        assert session.query(ProductSource).count() == 1
        assert session.query(OfferObservation).count() == 1


def test_monitoring_source_url_capture_excludes_non_active_statuses(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)

    with session_scope(database_url) as session:
        catalog_product = _catalog_product(session, model="RUN-SRC-2", mpn="MPN-RUN-SRC-2")
        for status, suffix in [
            ("active", "active"),
            ("broken", "broken"),
            ("disabled", "disabled"),
            ("needs_review", "review"),
            ("redirected", "redirected"),
        ]:
            create_or_update_imported_source_url(
                session,
                catalog_product_id=catalog_product.id,
                url=f"https://www.skroutz.gr/s/778/{suffix}.html",
                source_name="skroutz",
                trust_level="high_confidence",
                status=status,
            )

        captured_urls: list[str] = []

        def fake_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
            captured_urls.append(url)
            return CaptureResult(
                vendor_slug=vendor_slug or "skroutz",
                status="success",
                snapshot=CaptureSnapshotPayload(capture_strategy="status-filter-test", page_url=url, captured_at=NOW, fetched_at=NOW, parsed_at=NOW),
            )

        result = capture_selected_source_urls(
            session,
            run_id="run-1",
            source="skroutz",
            catalog_product_ids=[catalog_product.id],
            capture_fn=fake_capture,
        )

        assert result.selected_source_url_count == 1
        assert captured_urls == ["https://www.skroutz.gr/s/778/active.html"]
        assert session.query(ProductSource).count() == 1


def test_monitoring_source_url_capture_success_appends_price_observation(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)

    with session_scope(database_url) as session:
        catalog_product = _catalog_product(session, model="RUN-SRC-3", mpn="MPN-RUN-SRC-3")
        create_or_update_imported_source_url(
            session,
            catalog_product_id=catalog_product.id,
            url="https://www.electronet.gr/p/run-price",
            source_name="electronet",
            trust_level="high_confidence",
            status="active",
        )

        def fake_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
            return CaptureResult(
                vendor_slug=vendor_slug or "electronet",
                status="success",
                snapshot=CaptureSnapshotPayload(capture_strategy="price-test", page_url=url, captured_at=NOW, fetched_at=NOW, parsed_at=NOW),
                price_observations=(ParsedPriceObservation(price=Decimal("149.90"), availability="available"),),
            )

        result = capture_selected_source_urls(
            session,
            run_id="run-1",
            source="electronet",
            catalog_product_ids=[catalog_product.id],
            capture_fn=fake_capture,
        )

        assert result.succeeded_count == 1
        observed = session.query(PriceObservation).one()
        assert observed.competitor_price == Decimal("149.90")
        assert observed.product_source_id == session.query(ProductSource).one().id


def test_monitoring_source_url_capture_failure_updates_health_without_deleting_records(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)

    with session_scope(database_url) as session:
        catalog_product = _catalog_product(session, model="RUN-SRC-4", mpn="MPN-RUN-SRC-4")
        create_or_update_imported_source_url(
            session,
            catalog_product_id=catalog_product.id,
            url="https://www.skroutz.gr/s/779/failing.html",
            source_name="skroutz",
            trust_level="high_confidence",
            status="active",
        )

        def failing_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
            return CaptureResult(
                vendor_slug=vendor_slug or "skroutz",
                status="failed",
                snapshot=CaptureSnapshotPayload(
                    capture_strategy="failure-test",
                    page_url=url,
                    error_code="VENDOR_BLOCKED",
                    error_message="blocked",
                    data_quality_flags=["VENDOR_BLOCKED"],
                    captured_at=NOW,
                    fetched_at=NOW,
                    parsed_at=NOW,
                ),
                error_code="VENDOR_BLOCKED",
                error_message="blocked",
            )

        result = capture_selected_source_urls(
            session,
            run_id="run-1",
            source="skroutz",
            catalog_product_ids=[catalog_product.id],
            capture_fn=failing_capture,
        )

        assert result.failed_count == 1
        assert session.query(SourceUrl).count() == 1
        assert session.query(ProductSource).count() == 1
        source = session.query(ProductSource).one()
        assert source.last_error_code == "VENDOR_BLOCKED"
        assert source.consecutive_failures == 1
        assert session.query(SourceCaptureSnapshot).count() == 1


def test_product_source_creation_mirrors_to_source_url_coverage(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)

    with session_scope(database_url) as session:
        catalog_product = _catalog_product(session, model="SRC-2", mpn="MPN-SRC-2")
        create_product_from_source_urls(
            session,
            model="SRC-2",
            source_urls=["https://www.skroutz.gr/s/456/product-source.html?utm_source=x"],
            capture=False,
        )

        source_url = session.query(SourceUrl).one()
        coverage = compute_source_url_coverage(
            session,
            [
                SelectedPriceMonitoringProduct(
                    model="SRC-2",
                    mpn="MPN-SRC-2",
                    name="Source Product",
                    manufacturer="Brand",
                    category="",
                    raw_category="",
                    family="",
                    category_name="",
                    sub_category="",
                    category_levels=[],
                    price=100.0,
                    source="skroutz",
                    catalog_product_id=catalog_product.id,
                )
            ],
            "skroutz",
        )

    assert source_url.status == "active"
    assert source_url.trust_level == "product_source"
    assert coverage.summary.products_with_active_source_urls == 1
    assert coverage.item_coverage[0].active_source_urls[0]["url_normalized"] == "https://www.skroutz.gr/s/456/product-source.html"


def test_initial_capture_failure_preserves_product_and_source_health(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)

    def failing_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
        return CaptureResult(
            vendor_slug=vendor_slug or "skroutz",
            status="failed",
            snapshot=CaptureSnapshotPayload(
                capture_strategy="test",
                page_url=url,
                data_quality_flags=["NO_CANDIDATE_XHR_FOUND"],
                error_code="NO_CANDIDATE_XHR_FOUND",
                error_message="no xhr",
                captured_at=NOW,
                fetched_at=NOW,
                parsed_at=NOW,
            ),
            error_code="NO_CANDIDATE_XHR_FOUND",
            error_message="no xhr",
        )

    with session_scope(database_url) as session:
        result = create_product_from_source_urls(
            session,
            model="ABC-1",
            source_urls=["https://www.skroutz.gr/s/1"],
            capture_fn=failing_capture,
        )

        assert result.product.id is not None
        assert result.source_results[0]["capture_status"] == "failed"
        assert session.query(ProductSource).count() == 1
        source = session.query(ProductSource).one()
        assert source.last_error_code == "NO_CANDIDATE_XHR_FOUND"
        assert source.consecutive_failures == 1
        assert session.query(SourceCaptureSnapshot).count() == 1


def test_price_observations_are_append_only_for_repeated_capture(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    prices = [Decimal("199.99"), Decimal("189.99")]

    def price_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
        price = prices.pop(0)
        return CaptureResult(
            vendor_slug=vendor_slug or "electronet",
            status="success",
            snapshot=CaptureSnapshotPayload(capture_strategy="test", page_url=url, content_hash=str(price), captured_at=NOW, fetched_at=NOW, parsed_at=NOW),
            price_observations=(ParsedPriceObservation(price=price, availability="available"),),
        )

    with session_scope(database_url) as session:
        create_product_from_source_urls(
            session,
            model="ABC-2",
            source_urls=["https://www.electronet.gr/p/2"],
            capture_fn=price_capture,
        )
        create_product_from_source_urls(
            session,
            model="ABC-2",
            source_urls=["https://www.electronet.gr/p/2"],
            capture_fn=price_capture,
        )

        observed = session.query(PriceObservation).order_by(PriceObservation.id.asc()).all()
        assert [item.competitor_price for item in observed] == [Decimal("199.99"), Decimal("189.99")]
        assert session.query(SourceCaptureSnapshot).count() == 2


def test_offer_observations_persist_for_aggregator_capture(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)

    def offer_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
        return CaptureResult(
            vendor_slug=vendor_slug or "skroutz",
            status="success",
            snapshot=CaptureSnapshotPayload(capture_strategy="test", page_url=url, captured_at=NOW, fetched_at=NOW, parsed_at=NOW),
            offer_observations=(ParsedOfferObservation(seller_name="Store A", price=Decimal("199.99")),),
        )

    with session_scope(database_url) as session:
        create_product_from_source_urls(
            session,
            model="ABC-3",
            source_urls=["https://www.skroutz.gr/s/3"],
            capture_fn=offer_capture,
        )

        assert session.query(OfferObservation).count() == 1
        assert session.query(OfferObservation).one().seller_name == "Store A"


def test_products_from_source_api_stores_source_without_capture(tmp_path: Path, monkeypatch) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)

    response = TestClient(create_app()).post(
        "/api/products/from-source",
        json={"model": "LG OLED55C31LA", "source_urls": ["https://www.electronet.gr/p/1?utm_source=x"], "capture": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["product"]["model"] == "LG OLED55C31LA"
    assert payload["sources"][0]["capture_status"] == "skipped"
    assert payload["sources"][0]["canonical_url"] == "https://www.electronet.gr/p/1"
