import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.api import routes_price_monitoring, routes_vendor_sources  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models import Base, CatalogProductRow, OfferObservation, PriceObservation, ProductSource, SourceCaptureSnapshot, SourceUrl, Vendor  # noqa: E402
from ecommerce.db.product_source_repository import create_product_from_source_urls  # noqa: E402
from ecommerce.db.source_url_repository import create_or_update_imported_source_url  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.price_monitoring.fetch_run import run_price_monitoring_fetch  # noqa: E402
from ecommerce.price_monitoring.selection import SelectedPriceMonitoringProduct  # noqa: E402
from ecommerce.vendor_sources.capture import SourceUrlCaptureRunResult, capture_selected_source_urls  # noqa: E402
from ecommerce.price_monitoring.source_url_coverage import compute_source_url_coverage  # noqa: E402
from ecommerce.source_capture.scheduled import capture_due_product_sources  # noqa: E402
from ecommerce.source_capture.canonicalize_url import canonical_url_hash, canonicalize_url  # noqa: E402
from ecommerce.source_capture.detect_vendor import detect_vendor_slug  # noqa: E402
from ecommerce.source_capture.parsing import parse_electronet_html, parse_skroutz_offers, parse_skroutz_price_summary  # noqa: E402
from ecommerce.source_capture.sanitize import sanitize_headers, sanitize_json  # noqa: E402
from ecommerce.source_capture.scoring import score_response_candidate  # noqa: E402
from ecommerce.source_capture.skroutz_xhr import (  # noqa: E402
    BLOCKED_OR_CAPTCHA,
    FILTER_PRODUCTS_ACTION,
    NO_CANDIDATE_XHR_FOUND,
    NO_SHOP_TRIGGER,
    TIMEOUT,
    XHR_PARSE_FAILED,
    capture_skroutz_xhr,
)
from ecommerce.source_capture.types import (  # noqa: E402
    CaptureResult,
    CaptureSnapshotPayload,
    ParsedOfferObservation,
    ParsedPriceObservation,
    ResponseCandidate,
)


def _database_url(tmp_path: Path) -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'capture.db'}"
    Base.metadata.create_all(get_engine(database_url))
    return database_url


def _catalog_product(
    session,
    *,
    model: str,
    mpn: str,
    now: datetime,
) -> CatalogProductRow:
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
    now = datetime(2026, 5, 3, tzinfo=timezone.utc)

    with session_scope(database_url) as session:
        catalog_product = _catalog_product(session, model="SRC-1", mpn="MPN-SRC-1", now=now)
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
            snapshot=CaptureSnapshotPayload(
                capture_strategy="source-url-sync-test",
                page_url=url,
                captured_at=now,
                fetched_at=now,
                parsed_at=now,
            ),
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
    now = datetime(2026, 5, 3, tzinfo=timezone.utc)

    with session_scope(database_url) as session:
        catalog_product = _catalog_product(session, model="RUN-SRC-1", mpn="MPN-RUN-SRC-1", now=now)
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
                snapshot=CaptureSnapshotPayload(
                    capture_strategy="monitoring-source-url-test",
                    page_url=url,
                    captured_at=now,
                    fetched_at=now,
                    parsed_at=now,
                ),
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
    now = datetime(2026, 5, 3, tzinfo=timezone.utc)

    with session_scope(database_url) as session:
        catalog_product = _catalog_product(session, model="RUN-SRC-2", mpn="MPN-RUN-SRC-2", now=now)
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
                snapshot=CaptureSnapshotPayload(capture_strategy="status-filter-test", page_url=url, captured_at=now, fetched_at=now, parsed_at=now),
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
    now = datetime(2026, 5, 3, tzinfo=timezone.utc)

    with session_scope(database_url) as session:
        catalog_product = _catalog_product(session, model="RUN-SRC-3", mpn="MPN-RUN-SRC-3", now=now)
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
                snapshot=CaptureSnapshotPayload(capture_strategy="price-test", page_url=url, captured_at=now, fetched_at=now, parsed_at=now),
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
    now = datetime(2026, 5, 3, tzinfo=timezone.utc)

    with session_scope(database_url) as session:
        catalog_product = _catalog_product(session, model="RUN-SRC-4", mpn="MPN-RUN-SRC-4", now=now)
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
                    captured_at=now,
                    fetched_at=now,
                    parsed_at=now,
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
    now = datetime(2026, 5, 3, tzinfo=timezone.utc)

    with session_scope(database_url) as session:
        catalog_product = _catalog_product(session, model="SRC-2", mpn="MPN-SRC-2", now=now)
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
        now = datetime.now(timezone.utc).replace(microsecond=0)
        return CaptureResult(
            vendor_slug=vendor_slug or "skroutz",
            status="failed",
            snapshot=CaptureSnapshotPayload(
                capture_strategy="test",
                page_url=url,
                data_quality_flags=["NO_CANDIDATE_XHR_FOUND"],
                error_code="NO_CANDIDATE_XHR_FOUND",
                error_message="no xhr",
                captured_at=now,
                fetched_at=now,
                parsed_at=now,
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
        now = datetime.now(timezone.utc).replace(microsecond=0)
        price = prices.pop(0)
        return CaptureResult(
            vendor_slug=vendor_slug or "electronet",
            status="success",
            snapshot=CaptureSnapshotPayload(
                capture_strategy="test",
                page_url=url,
                content_hash=str(price),
                captured_at=now,
                fetched_at=now,
                parsed_at=now,
            ),
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


def test_skroutz_candidate_scoring_prefers_offer_payload() -> None:
    analytics = score_response_candidate(
        ResponseCandidate(url="https://analytics.example/collect", body_text="ok", content_type="text/plain")
    )
    offers = score_response_candidate(
        ResponseCandidate(
            url="https://www.skroutz.gr/products/1/offers",
            content_type="application/json",
            body_text='{"shop_name":"Store A","price":199.99,"availability":"available","shipping_cost":3}',
            occurred_after_trigger=True,
        )
    )

    assert offers.score > analytics.score
    assert "seller/shop fields" in "; ".join(offers.reasons)


def test_skroutz_candidate_scoring_penalizes_widgets_and_promotions() -> None:
    widget = score_response_candidate(
        ResponseCandidate(
            url="https://ekr.zdassets.com/compose/support-widget",
            content_type="application/json",
            body_text='{"products":[{"name":"web_widget"}]}',
        )
    )
    promotion = score_response_candidate(
        ResponseCandidate(
            url="https://www.skroutz.gr/s/1/placements?type=featured_cross_sell",
            body_text="<html><title>Just a moment...</title></html>",
            status=403,
            occurred_after_trigger=True,
        )
    )
    offers = score_response_candidate(
        ResponseCandidate(
            url="https://www.skroutz.gr/s/1/service_filtered_offerings.json",
            content_type="application/json",
            body_text='{"shop_name":"Store A","price":199.99}',
            occurred_after_trigger=True,
        )
    )
    filter_products = score_response_candidate(
        ResponseCandidate(
            url="https://www.skroutz.gr/s/1/filter_products.json",
            content_type="application/json",
            body_text='{"price_min":"199.99"}',
        )
    )

    assert offers.score > widget.score
    assert offers.score > promotion.score
    assert filter_products.score > widget.score
    assert "skroutz filter products endpoint" in "; ".join(filter_products.reasons)


def test_skroutz_xhr_capture_persists_best_candidate_and_parses_offers() -> None:
    payload = {
        "shops": [
            {"shop_name": "Store A", "price": "199,99", "availability": "available", "shipping_cost": "3.00"},
            {"seller": {"name": "Store B"}, "pricing": {"final_price": "205.00"}, "delivery": {"text": "1-3 days"}},
        ]
    }
    page = _FakePage(
        has_trigger=True,
        responses=[
            _FakeResponse(
                "https://www.skroutz.gr/s/1/service_filtered_offerings.json",
                json.dumps(payload),
                resource_type="fetch",
            )
        ],
    )

    result = capture_skroutz_xhr(
        "https://www.skroutz.gr/s/1/product.html",
        timeout_seconds=5,
        sync_playwright_factory=lambda: _FakePlaywright(page),
    )

    assert result.status == "success"
    assert result.snapshot.request_url == "https://www.skroutz.gr/s/1/service_filtered_offerings.json"
    assert result.snapshot.request_method == "GET"
    assert result.snapshot.response_status == 200
    assert result.snapshot.response_content_type == "application/json"
    assert result.snapshot.response_body_json == payload
    assert result.snapshot.network_event_type == "fetch"
    assert result.snapshot.trigger_action == "#offerings button[data-controller*='shops-entrypoint']"
    assert page.waited_selectors[0] == "#offerings button[data-controller*='shops-entrypoint']"
    assert page.waited_timeouts[0] == 3000
    assert page.clicked_selectors == ["#offerings button[data-controller*='shops-entrypoint']"]
    assert result.snapshot.candidate_score is not None and result.snapshot.candidate_score > 0
    assert len(result.offer_observations) == 2
    assert result.offer_observations[0].seller_name == "Store A"
    assert result.offer_observations[0].price == Decimal("199.99")


def test_skroutz_xhr_capture_returns_no_shop_trigger_without_live_browser() -> None:
    page = _FakePage(has_trigger=False)

    result = capture_skroutz_xhr(
        "https://www.skroutz.gr/s/2/product.html",
        timeout_seconds=5,
        sync_playwright_factory=lambda: _FakePlaywright(page),
    )

    assert result.status == "failed"
    assert result.error_code == NO_SHOP_TRIGGER
    assert NO_SHOP_TRIGGER in result.snapshot.data_quality_flags
    assert NO_CANDIDATE_XHR_FOUND in result.snapshot.data_quality_flags
    assert result.snapshot.raw_html is not None


def test_skroutz_xhr_capture_uses_filter_products_price_summary_without_shop_trigger() -> None:
    page = _FakePage(
        has_trigger=False,
        filter_products_payload={"price_min": "187,50", "availability": "available"},
    )

    result = capture_skroutz_xhr(
        "https://www.skroutz.gr/s/8/product.html",
        timeout_seconds=5,
        sync_playwright_factory=lambda: _FakePlaywright(page),
    )

    assert result.status == "success"
    assert result.snapshot.request_url == "https://www.skroutz.gr/s/8/filter_products.json"
    assert result.snapshot.parser_version == "skroutz_filter_products_v1"
    assert result.snapshot.trigger_action == FILTER_PRODUCTS_ACTION
    assert NO_SHOP_TRIGGER in result.snapshot.data_quality_flags
    assert len(result.price_observations) == 1
    assert result.price_observations[0].price == Decimal("187.50")
    assert result.offer_observations == ()


def test_skroutz_xhr_capture_returns_no_candidate_after_trigger() -> None:
    page = _FakePage(has_trigger=True)

    result = capture_skroutz_xhr(
        "https://www.skroutz.gr/s/3/product.html",
        timeout_seconds=5,
        sync_playwright_factory=lambda: _FakePlaywright(page),
    )

    assert result.status == "failed"
    assert result.error_code == NO_CANDIDATE_XHR_FOUND
    assert result.snapshot.trigger_action == "#offerings button[data-controller*='shops-entrypoint']"


def test_skroutz_xhr_capture_returns_parse_failed_for_unparseable_candidate() -> None:
    page = _FakePage(
        has_trigger=True,
        responses=[
            _FakeResponse(
                "https://www.skroutz.gr/s/4/service_filtered_offerings.json",
                '{"price":199.99,"availability":"available","shipping_cost":3}',
            )
        ],
    )

    result = capture_skroutz_xhr(
        "https://www.skroutz.gr/s/4/product.html",
        timeout_seconds=5,
        sync_playwright_factory=lambda: _FakePlaywright(page),
    )

    assert result.status == "failed"
    assert result.error_code == XHR_PARSE_FAILED
    assert result.snapshot.request_url == "https://www.skroutz.gr/s/4/service_filtered_offerings.json"
    assert result.snapshot.response_body_json == {"price": 199.99, "availability": "available", "shipping_cost": 3}
    assert XHR_PARSE_FAILED in result.snapshot.data_quality_flags


def test_skroutz_xhr_capture_flags_blocked_candidate() -> None:
    page = _FakePage(
        has_trigger=True,
        responses=[
            _FakeResponse(
                "https://www.skroutz.gr/s/5/service_filtered_offerings.json",
                "<html><title>Just a moment...</title><p>Cloudflare captcha challenge</p></html>",
                status=403,
                content_type="text/html",
            )
        ],
    )

    result = capture_skroutz_xhr(
        "https://www.skroutz.gr/s/5/product.html",
        timeout_seconds=5,
        sync_playwright_factory=lambda: _FakePlaywright(page),
    )

    assert result.status == "failed"
    assert result.error_code == BLOCKED_OR_CAPTCHA
    assert result.snapshot.response_status == 403
    assert result.snapshot.response_body_text is not None


def test_skroutz_xhr_capture_returns_timeout_code() -> None:
    page = _FakePage(has_trigger=True, goto_error=_FakeTimeout("timed out"))

    result = capture_skroutz_xhr(
        "https://www.skroutz.gr/s/6/product.html",
        timeout_seconds=5,
        sync_playwright_factory=lambda: _FakePlaywright(page),
        timeout_error_cls=_FakeTimeout,
    )

    assert result.status == "failed"
    assert result.error_code == TIMEOUT
    assert TIMEOUT in result.snapshot.data_quality_flags


def test_skroutz_xhr_capture_falls_back_to_visible_dom_offers() -> None:
    page = _FakePage(
        has_trigger=True,
        html="""
        <html><body>
          <div class="shop-card"><h3>DOM Store</h3><span>188,40 €</span><p>Διαθέσιμο</p><p>Μεταφορικά 4,00 €</p></div>
        </body></html>
        """,
    )

    result = capture_skroutz_xhr(
        "https://www.skroutz.gr/s/7/product.html",
        timeout_seconds=5,
        sync_playwright_factory=lambda: _FakePlaywright(page),
    )

    assert result.status == "success"
    assert result.snapshot.capture_strategy == "skroutz_playwright_dom_fallback"
    assert "dom_fallback" in result.snapshot.data_quality_flags
    assert len(result.offer_observations) == 1
    assert result.offer_observations[0].seller_name == "DOM Store"
    assert result.offer_observations[0].price == Decimal("188.40")


def test_electronet_parser_extracts_price_and_flags_missing_price() -> None:
    parsed, flags = parse_electronet_html(
        '<html><title>TV</title><meta property="product:price:amount" content="499.90"><span>Διαθεσιμότητα</span><b>Άμεσα διαθέσιμο</b></html>',
        page_url="https://www.electronet.gr/p/1",
    )
    missing, missing_flags = parse_electronet_html("<html><title>TV</title></html>", page_url="https://www.electronet.gr/p/1")

    assert parsed.price == Decimal("499.90")
    assert "PRICE_MISSING" not in flags
    assert missing.price is None
    assert "PRICE_MISSING" in missing_flags


def test_electronet_parser_extracts_json_ld_product_offer() -> None:
    parsed, flags = parse_electronet_html(
        """
        <html><head>
        <script type="application/ld+json">
        {"@type":"Product","name":"LG OLED","offers":{"price":"849.90","availability":"https://schema.org/InStock"}}
        </script>
        </head></html>
        """,
        page_url="https://www.electronet.gr/p/structured",
    )

    assert parsed.price == Decimal("849.90")
    assert parsed.product_name == "LG OLED"
    assert parsed.availability == "https://schema.org/InStock"
    assert flags == []


def test_skroutz_parser_extracts_multiple_offers() -> None:
    offers, flags = parse_skroutz_offers(
        {
            "shops": [
                {"shop_name": "Store A", "price": "199,99", "availability": "available", "shipping_cost": "3.00"},
                {"seller": {"name": "Store B"}, "final_price": 205},
            ]
        }
    )

    assert flags == []
    assert len(offers) == 2
    assert offers[0].seller_name == "Store A"
    assert offers[0].price == Decimal("199.99")


def test_skroutz_parser_extracts_filter_products_price_min() -> None:
    observation, flags = parse_skroutz_price_summary(
        {"price_min": "187,50", "availability": "available"},
        page_url="https://www.skroutz.gr/s/8/product.html",
    )

    assert flags == []
    assert observation is not None
    assert observation.price == Decimal("187.50")
    assert observation.availability == "available"
    assert observation.raw_observation["source"] == "filter_products"


def test_skroutz_parser_extracts_nested_shop_and_pricing_payload() -> None:
    offers, flags = parse_skroutz_offers(
        {
            "cards": [
                {
                    "shop": {"name": "Nested Store", "url": "https://seller.example.test"},
                    "pricing": {"final_price": "321.50"},
                    "delivery": {"shipping_cost": "4.90", "text": "1-3 days"},
                    "availability_text": "in stock",
                }
            ]
        }
    )

    assert flags == []
    assert len(offers) == 1
    assert offers[0].seller_name == "Nested Store"
    assert offers[0].price == Decimal("321.50")
    assert offers[0].shipping_cost == Decimal("4.90")
    assert offers[0].delivery_text == "1-3 days"


def test_offer_observations_persist_for_aggregator_capture(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)

    def offer_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        return CaptureResult(
            vendor_slug=vendor_slug or "skroutz",
            status="success",
            snapshot=CaptureSnapshotPayload(capture_strategy="test", page_url=url, captured_at=now, fetched_at=now, parsed_at=now),
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


def test_raw_snapshot_sanitization_helpers_remove_sensitive_metadata() -> None:
    assert sanitize_headers({"Cookie": "secret", "Authorization": "Bearer x", "Content-Type": "application/json"}) == {
        "Content-Type": "application/json"
    }
    assert sanitize_json({"token": "secret", "payload": {"csrf": "secret", "price": 10}}) == {"payload": {"price": 10}}


def test_raw_capture_text_is_preserved_as_full_artifact(tmp_path: Path, monkeypatch) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_SOURCE_CAPTURE_ARTIFACT_DIR", str(tmp_path / "capture-artifacts"))
    raw_html = "<html>" + ("x" * 150_000) + "</html>"

    def raw_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        return CaptureResult(
            vendor_slug=vendor_slug or "electronet",
            status="success",
            snapshot=CaptureSnapshotPayload(
                capture_strategy="raw-artifact-test",
                page_url=url,
                raw_html=raw_html,
                captured_at=now,
                fetched_at=now,
                parsed_at=now,
            ),
        )

    with session_scope(database_url) as session:
        create_product_from_source_urls(
            session,
            model="RAW-1",
            source_urls=["https://www.electronet.gr/p/raw"],
            capture_fn=raw_capture,
        )
        snapshot = session.query(SourceCaptureSnapshot).one()

    assert snapshot.raw_html_ref is not None
    assert len(snapshot.raw_html_ref) < 300
    assert Path(snapshot.raw_html_ref).read_text(encoding="utf-8") == raw_html


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


def test_scheduled_capture_refreshes_due_product_sources(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)

    with session_scope(database_url) as session:
        create_product_from_source_urls(
            session,
            model="SCHEDULED-1",
            source_urls=["https://www.electronet.gr/p/1"],
            capture=False,
        )

    def fake_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        return CaptureResult(
            vendor_slug=vendor_slug or "electronet",
            status="success",
            snapshot=CaptureSnapshotPayload(capture_strategy="scheduled-test", page_url=url, captured_at=now, fetched_at=now, parsed_at=now),
            price_observations=(ParsedPriceObservation(price=Decimal("299.00"), availability="available"),),
        )

    with session_scope(database_url) as session:
        summary = capture_due_product_sources(session, refresh_after_minutes=360, capture_fn=fake_capture)

        assert summary.selected_count == 1
        assert summary.succeeded_count == 1
        assert summary.failed_count == 0
        assert session.query(PriceObservation).count() == 1
        source = session.query(ProductSource).one()
        assert source.last_fetch_status == "success"
        assert source.last_capture_strategy == "scheduled-test"


def test_source_capture_run_api_returns_summary(tmp_path: Path, monkeypatch) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    monkeypatch.setattr(routes_price_monitoring, "_require_price_monitoring_database_ready", lambda: None)
    monkeypatch.setattr(routes_vendor_sources, "_require_vendor_sources_database_ready", lambda: None)
    monkeypatch.setattr(
        routes_price_monitoring,
        "run_vendor_source_capture",
        lambda *_args, **_kwargs: SourceUrlCaptureRunResult(
            status="completed_with_partial_failures",
            used_source_urls=True,
            source="electronet",
            vendor="electronet",
            run_id="capture-run-1",
            observation_batch_id="capture-run-1",
            source_filter="electronet",
            selected_catalog_product_count=2,
            selected_source_url_count=2,
            selected_product_source_count=2,
            succeeded_count=1,
            failed_count=1,
            warnings=[],
            items=[{"product_source_id": 1, "status": "success"}, {"product_source_id": 2, "status": "failed"}],
            source_urls=[],
            result_path=None,
        ),
    )
    monkeypatch.setattr(
        routes_vendor_sources,
        "run_vendor_source_capture",
        lambda *_args, **_kwargs: SourceUrlCaptureRunResult(
            status="completed_with_partial_failures",
            used_source_urls=True,
            source="electronet",
            vendor="electronet",
            run_id="capture-run-1",
            observation_batch_id="capture-run-1",
            source_filter="electronet",
            selected_catalog_product_count=2,
            selected_source_url_count=2,
            selected_product_source_count=2,
            succeeded_count=1,
            failed_count=1,
            warnings=[],
            items=[{"product_source_id": 1, "status": "success"}, {"product_source_id": 2, "status": "failed"}],
            source_urls=[],
            result_path=None,
        ),
    )

    response = TestClient(create_app()).post(
        "/api/vendor-sources/captures/runs",
        json={"vendor": "electronet", "limit": 2, "refresh_after_minutes": 0},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "electronet"
    assert payload["vendor"] == "electronet"
    assert payload["selected_count"] == 2
    assert payload["selected_source_url_count"] == 2
    assert payload["selected_product_source_count"] == 2
    assert payload["succeeded_count"] == 1
    assert payload["failed_count"] == 1

    compatibility_response = TestClient(create_app()).post(
        "/api/price-monitoring/source-captures/run",
        json={"vendor": "electronet", "limit": 2, "refresh_after_minutes": 0},
    )

    assert compatibility_response.status_code == 200
    assert compatibility_response.json()["replacement_endpoint"] == "/api/vendor-sources/captures/runs"


def test_price_monitoring_fetch_result_reports_source_url_capture_usage(tmp_path: Path, monkeypatch) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    now = datetime(2026, 5, 3, tzinfo=timezone.utc)
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    (run_dir / "input.csv").write_text("model,mpn,name,price\nRUN-SRC-5,MPN-RUN-SRC-5,Source Product,100.00\n", encoding="utf-8")

    with session_scope(database_url) as session:
        catalog_product = _catalog_product(session, model="RUN-SRC-5", mpn="MPN-RUN-SRC-5", now=now)
        catalog_product_id = catalog_product.id
        create_or_update_imported_source_url(
            session,
            catalog_product_id=catalog_product_id,
            url="https://www.skroutz.gr/s/780/result-fields.html",
            source_name="skroutz",
            trust_level="high_confidence",
            status="active",
        )
    (run_dir / "selection_summary.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "source": "skroutz",
                "selected_items": [{"model": "RUN-SRC-5", "catalog_product_id": catalog_product_id}],
            }
        ),
        encoding="utf-8",
    )

    def fake_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
        return CaptureResult(
            vendor_slug=vendor_slug or "skroutz",
            status="success",
            snapshot=CaptureSnapshotPayload(capture_strategy="fetch-result-test", page_url=url, captured_at=now, fetched_at=now, parsed_at=now),
            offer_observations=(ParsedOfferObservation(seller_name="Store A", price=Decimal("88.00")),),
        )

    result = run_price_monitoring_fetch(
        run_dir,
        source="skroutz",
        source_capture_fn=fake_capture,
    )

    assert result.fetch_input_mode == "source_urls"
    assert result.legacy_marketplace_fetch_used is False
    assert result.source_url_capture_used is True
    assert result.source_url_capture_status == "completed"
    assert result.source_url_capture_selected_count == 1
    assert result.source_url_capture_succeeded_count == 1
    assert result.source_url_capture_result_path == run_dir / "source_url_capture_result.json"
    payload = json.loads((run_dir / "fetch_result.json").read_text(encoding="utf-8"))
    assert payload["source_url_capture_used"] is True
    assert payload["fetch_input_mode"] == "source_urls"
    assert payload["legacy_marketplace_fetch_used"] is False


class _FakeTimeout(TimeoutError):
    pass


class _FakeRequest:
    def __init__(self, *, resource_type: str = "fetch", method: str = "GET") -> None:
        self.resource_type = resource_type
        self.method = method


class _FakeResponse:
    def __init__(
        self,
        url: str,
        body: str,
        *,
        status: int = 200,
        content_type: str = "application/json",
        resource_type: str = "xhr",
        method: str = "GET",
    ) -> None:
        self.url = url
        self.status = status
        self.headers = {"content-type": content_type}
        self.request = _FakeRequest(resource_type=resource_type, method=method)
        self._body = body

    def text(self) -> str:
        return self._body


class _FakeLocator:
    def __init__(self, page: "_FakePage", selector: str) -> None:
        self._page = page
        self._selector = selector

    @property
    def first(self) -> "_FakeLocator":
        return self

    def count(self) -> int:
        if "Accept" in self._selector or "OK" in self._selector or "Αποδοχή" in self._selector or "Συμφωνώ" in self._selector:
            return 0
        trigger_selectors = {
            "#offerings button[data-controller*='shops-entrypoint']",
            "#offerings .js-shops-entrypoint-wrapper button",
            "button[data-controller='sku-page--offerings--shops-entrypoint']",
            "button[data-controller*='sku-page--offerings--shops-entrypoint']",
            "button[data-action*='stats#incrementCounterDeviceSuffix']",
            "button.alternative-option-wrapper.btn-reset:has-text('καταστήματα')",
            "text=Δες τα καταστήματα",
        }
        return 1 if self._page.has_trigger and self._selector in trigger_selectors else 0

    def is_visible(self, timeout: int | None = None) -> bool:
        del timeout
        return self.count() > 0

    def click(self, timeout: int | None = None) -> None:
        del timeout
        self._page.clicked_selectors.append(self._selector)
        self._page.emit_trigger_responses()

    def scroll_into_view_if_needed(self, timeout: int | None = None) -> None:
        del timeout
        self._page.scrolled_selectors.append(self._selector)


class _FakePage:
    def __init__(
        self,
        *,
        has_trigger: bool,
        responses: list[_FakeResponse] | None = None,
        html: str = "<html><body><button>Δες τα καταστήματα</button></body></html>",
        goto_error: BaseException | None = None,
        filter_products_payload: dict | None = None,
    ) -> None:
        self.has_trigger = has_trigger
        self.responses = responses or []
        self.html = html
        self.goto_error = goto_error
        self.filter_products_payload = filter_products_payload
        self.url = "https://www.skroutz.gr/s/final-product.html"
        self.handlers: dict[str, list] = {}
        self.clicked_selectors: list[str] = []
        self.scrolled_selectors: list[str] = []
        self.waited_selectors: list[str] = []
        self.waited_timeouts: list[int] = []
        self.evaluate_calls: list[dict] = []

    def on(self, event: str, handler) -> None:
        self.handlers.setdefault(event, []).append(handler)

    def goto(self, url: str, *, wait_until: str, timeout: int) -> _FakeResponse:
        del wait_until, timeout
        self.url = url
        if self.goto_error is not None:
            raise self.goto_error
        return _FakeResponse(url, "<html></html>", resource_type="document", content_type="text/html")

    def wait_for_load_state(self, state: str, *, timeout: int) -> None:
        del state, timeout

    def wait_for_timeout(self, timeout: int) -> None:
        self.waited_timeouts.append(timeout)

    def wait_for_selector(self, selector: str, *, state: str, timeout: int):
        del state, timeout
        self.waited_selectors.append(selector)
        locator = _FakeLocator(self, selector)
        if locator.count() <= 0:
            raise _FakeTimeout("selector not visible")
        return locator

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(self, selector)

    def content(self) -> str:
        return self.html

    def evaluate(self, script: str, arg: dict):
        del script
        self.evaluate_calls.append(arg)
        if self.filter_products_payload is None:
            raise _FakeTimeout("filter_products unavailable")
        return {
            "url": arg["url"],
            "status": 200,
            "contentType": "application/json",
            "text": json.dumps(self.filter_products_payload),
        }

    def emit_trigger_responses(self) -> None:
        for response in self.responses:
            for handler in self.handlers.get("response", []):
                handler(response)


class _FakeBrowser:
    def __init__(self, page: _FakePage) -> None:
        self._page = page
        self.closed = False

    def new_page(self, **kwargs) -> _FakePage:
        del kwargs
        return self._page

    def close(self) -> None:
        self.closed = True


class _FakeChromium:
    def __init__(self, page: _FakePage) -> None:
        self._page = page

    def launch(self, *, headless: bool) -> _FakeBrowser:
        del headless
        return _FakeBrowser(self._page)


class _FakePlaywright:
    def __init__(self, page: _FakePage) -> None:
        self.chromium = _FakeChromium(page)

    def __enter__(self) -> "_FakePlaywright":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback
