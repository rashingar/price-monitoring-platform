from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models.base import Base  # noqa: E402
from ecommerce.db.models.catalog import CatalogProductRow  # noqa: E402
from ecommerce.db.models.products import SourceCaptureSnapshot  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.db.repositories.source_urls import (
    create_or_update_imported_source_url,
)  # noqa: E402
from ecommerce.source_capture.skroutz_network_diagnostic import (  # noqa: E402
    BLOCKED_OR_CHALLENGE,
    NON_JSON_XHR,
    POSSIBLE_PRODUCT_OR_OFFER_DATA,
    POSSIBLE_RECOMMENDATIONS,
    POSSIBLE_REVIEWS_OR_RATING_DATA,
    PRIMARY_CANDIDATE_PRODUCT_OFFERS,
    SECONDARY_CANDIDATE_SHOP_DETAILS,
    SkroutzNetworkCapturedResponse,
    SkroutzNetworkDiagnosticReport,
    classify_skroutz_network_endpoint,
    derived_skroutz_endpoint_urls,
    extract_skroutz_product_id,
    sanitize_diagnostic_url,
)
from ecommerce.vendor_sources import (
    skroutz_network_diagnostics as diagnostic_service,
)  # noqa: E402

NOW = datetime(2026, 5, 7, 12, tzinfo=timezone.utc)


def _database_url(tmp_path: Path) -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'skroutz-diagnostic.db'}"
    Base.metadata.create_all(get_engine(database_url))
    return database_url


def _catalog_product(session, *, model: str = "005606") -> CatalogProductRow:
    row = CatalogProductRow(
        catalog_source="sourceCata",
        model=model,
        mpn="MD-20L",
        name="Midea Product",
        category="",
        raw_category="",
        manufacturer="Midea",
        imported_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(row)
    session.flush()
    return row


def test_skroutz_product_id_extraction_and_derived_endpoints() -> None:
    url = "https://www.skroutz.gr/s/65005733/xiaomi-poco.html?utm=1"

    assert extract_skroutz_product_id(url) == "65005733"
    assert extract_skroutz_product_id("https://www.skroutz.gr/c/40/phones.html") is None
    assert derived_skroutz_endpoint_urls(url) == {
        "filter_products": "https://www.skroutz.gr/s/65005733/filter_products.json",
        "shops_details": "https://www.skroutz.gr/s/65005733/shops_details.json",
    }


def test_skroutz_endpoint_classification_cases() -> None:
    assert (
        classify_skroutz_network_endpoint(
            "https://www.skroutz.gr/s/1/filter_products.json", {}, "{}"
        )
        == PRIMARY_CANDIDATE_PRODUCT_OFFERS
    )
    assert (
        classify_skroutz_network_endpoint(
            "https://www.skroutz.gr/s/1/shops_details.json", {}, "{}"
        )
        == SECONDARY_CANDIDATE_SHOP_DETAILS
    )
    assert (
        classify_skroutz_network_endpoint(
            "https://www.skroutz.gr/api/data", {"product_cards": [{"price": 1}]}, "{}"
        )
        == PRIMARY_CANDIDATE_PRODUCT_OFFERS
    )
    assert (
        classify_skroutz_network_endpoint(
            "https://www.skroutz.gr/api/data", {"offers": [{"seller": "shop"}]}, "{}"
        )
        == POSSIBLE_PRODUCT_OR_OFFER_DATA
    )
    assert (
        classify_skroutz_network_endpoint(
            "https://www.skroutz.gr/api/reviews", {"ratings": []}, "{}"
        )
        == POSSIBLE_REVIEWS_OR_RATING_DATA
    )
    assert (
        classify_skroutz_network_endpoint(
            "https://www.skroutz.gr/api/recommendations", {"similar_products": []}, "{}"
        )
        == POSSIBLE_RECOMMENDATIONS
    )
    assert (
        classify_skroutz_network_endpoint(
            "https://www.skroutz.gr/challenge", None, "<html>captcha challenge</html>"
        )
        == BLOCKED_OR_CHALLENGE
    )
    assert (
        classify_skroutz_network_endpoint(
            "https://www.skroutz.gr/api/data", None, "not json"
        )
        == NON_JSON_XHR
    )


def test_skroutz_diagnostic_url_sanitizes_sensitive_query_params() -> None:
    url = "https://www.skroutz.gr/api/offers?token=abc&session=secret&page=2&signature=sig"

    assert (
        sanitize_diagnostic_url(url)
        == "https://www.skroutz.gr/api/offers?token=%5BREDACTED%5D&session=%5BREDACTED%5D&page=2&signature=%5BREDACTED%5D"
    )


def test_skroutz_network_diagnostic_api_rejects_non_skroutz_source_url(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        source_url = create_or_update_imported_source_url(
            session,
            catalog_product_id=product.id,
            url="https://www.electronet.gr/product/midea-md-20l",
            source_name="electronet",
            status="active",
        ).row
        assert source_url is not None
        source_url_id = source_url.id

    client = TestClient(create_app())
    response = client.post(
        f"/api/vendor-sources/source-urls/{source_url_id}/diagnostics/skroutz-network",
        json={},
    )

    assert response.status_code == 400
    assert "only available for Skroutz" in response.json()["detail"]


def test_skroutz_network_diagnostic_api_persists_and_fetches_latest_report(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        source_url = create_or_update_imported_source_url(
            session,
            catalog_product_id=product.id,
            url="https://www.skroutz.gr/s/65005733/xiaomi.html",
            source_name="skroutz",
            status="active",
            trust_level="high_confidence",
        ).row
        assert source_url is not None
        source_url_id = source_url.id

    def fake_runner(
        source_url: str, *, headed: bool = False, timeout_seconds: int = 60
    ) -> SkroutzNetworkDiagnosticReport:
        del headed, timeout_seconds
        derived = derived_skroutz_endpoint_urls(source_url)
        return SkroutzNetworkDiagnosticReport(
            source_url=source_url,
            status="success",
            started_at=NOW.isoformat(),
            completed_at=NOW.isoformat(),
            timeout_seconds=60,
            headed=False,
            derived_endpoints=derived,
            captured_responses=[
                SkroutzNetworkCapturedResponse(
                    method="GET",
                    url=derived["filter_products"],
                    status=200,
                    resource_type="xhr",
                    content_type="application/json",
                    body_size=120,
                    parsed_json_valid=True,
                    json_summary={
                        "top_level_type": "object",
                        "top_level_keys": ["product_cards"],
                        "top_level_key_count": 1,
                        "has_product_cards": True,
                        "product_cards_count": 1,
                    },
                    classification=PRIMARY_CANDIDATE_PRODUCT_OFFERS,
                    matched_derived_endpoint="filter_products",
                    body_sample='{"product_cards":[{"price":10}]}',
                )
            ],
            observed_filter_products_url=True,
            observed_shops_details_url=False,
            exact_match_count=1,
            product_data_candidate_url=derived["filter_products"],
            product_data_candidate_reason="PRIMARY_CANDIDATE_PRODUCT_OFFERS: exact derived filter_products endpoint observed",
            classifications_summary={PRIMARY_CANDIDATE_PRODUCT_OFFERS: 1},
        )

    monkeypatch.setattr(
        diagnostic_service, "run_skroutz_network_diagnostic", fake_runner
    )

    client = TestClient(create_app())
    response = client.post(
        f"/api/vendor-sources/source-urls/{source_url_id}/diagnostics/skroutz-network",
        json={"headed": False, "timeout_seconds": 60},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["captured_response_count"] == 1
    assert payload["observed_filter_products_url"] is True
    assert payload["observed_shops_details_url"] is False
    assert (
        payload["best_product_data_endpoint"]
        == "https://www.skroutz.gr/s/65005733/filter_products.json"
    )
    assert payload["diagnostic_report_id"] is not None

    latest = client.get(
        f"/api/vendor-sources/source-urls/{source_url_id}/diagnostics/skroutz-network/latest"
    )
    assert latest.status_code == 200
    latest_payload = latest.json()
    assert latest_payload["summary"]["captured_response_count"] == 1
    assert (
        latest_payload["captured_responses"][0]["classification"]
        == PRIMARY_CANDIDATE_PRODUCT_OFFERS
    )
    assert latest_payload["captured_responses"][0]["body_sample"].startswith("{")

    with session_scope(database_url) as session:
        snapshot = session.query(SourceCaptureSnapshot).one()
        assert snapshot.capture_strategy == "skroutz_browser_network_diagnostic"
        assert snapshot.response_body_json["observed_filter_products_url"] is True
