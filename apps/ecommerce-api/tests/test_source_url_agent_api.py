import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models import Base  # noqa: E402
from ecommerce.db.models.catalog import CatalogProductRow  # noqa: E402
from ecommerce.db.models.source_urls import SourceUrl, SourceUrlCandidate  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402


NOW = datetime(2026, 5, 3, 12, tzinfo=timezone.utc)


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"


def _client(tmp_path: Path, monkeypatch) -> tuple[TestClient, str]:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    Base.metadata.create_all(get_engine(database_url))
    return TestClient(create_app()), database_url


def _catalog_product(session, *, model: str = "005606", mpn: str = "MR25GB") -> CatalogProductRow:
    row = CatalogProductRow(
        catalog_source="sourceCata",
        model=model,
        mpn=mpn,
        name=f"Product {model}",
        category="TV Control",
        raw_category="TV Control",
        manufacturer="LG",
        status=1,
        active=True,
        imported_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(row)
    session.flush()
    return row


def _candidate(
    session,
    product: CatalogProductRow,
    *,
    run_id: str = "run-1",
    source_name: str = "bestprice",
    status: str = "needs_review",
    match_status: str = "needs_review",
    confidence_score: Decimal = Decimal("0.6000"),
    model: str | None = None,
    url: str = "https://www.bestprice.gr/item/1/lg-remote.html",
) -> SourceUrlCandidate:
    row = SourceUrlCandidate(
        run_id=run_id,
        catalog_product_id=product.id,
        catalog_source=product.catalog_source,
        model=model or product.model,
        mpn=product.mpn,
        manufacturer=product.manufacturer,
        product_name=product.name,
        category=product.category,
        own_price=Decimal("19.00"),
        source_name=source_name,
        source_domain="www.bestprice.gr",
        source_type="marketplace",
        expected_listing="listed",
        candidate_url=url,
        canonical_url=url,
        candidate_title="LG Remote",
        candidate_price=Decimal("18.50"),
        match_status=match_status,
        confidence_score=confidence_score,
        match_method="exact_mpn_and_brand",
        evidence_json={"mpn": {"found": True, "fragment": product.mpn}},
        competing_candidates_count=1,
        searched_queries_json=["LG MR25GB"],
        status=status,
        notes="initial note",
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(row)
    session.flush()
    return row


def _source_url(session, product: CatalogProductRow, *, url: str) -> SourceUrl:
    row = SourceUrl(
        catalog_product_id=product.id,
        catalog_source=product.catalog_source,
        model=product.model,
        mpn=product.mpn,
        manufacturer=product.manufacturer,
        source_name="bestprice",
        source_domain="www.bestprice.gr",
        url=url,
        url_normalized=url,
        status="needs_review",
        url_type="discovered",
        trust_level="manual",
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(row)
    session.flush()
    return row


def test_vendor_sources_api_returns_discovery_and_capture_capabilities() -> None:
    response = TestClient(create_app()).get("/api/vendor-sources/sources")

    assert response.status_code == 200
    items = {item["source_name"]: item for item in response.json()["items"]}
    assert items["electronet"]["source_type"] == "direct_vendor"
    assert items["electronet"]["discovery_enabled"] is True
    assert items["electronet"]["capture_implemented"] is True
    assert items["electronet"]["capture_enabled"] is True
    assert items["skroutz"]["source_type"] == "marketplace"
    assert items["skroutz"]["capture_implemented"] is True
    assert items["bestprice"]["discovery_enabled"] is True
    assert items["bestprice"]["capture_implemented"] is True
    for source_name in ("plaisio", "public", "kotsovolos"):
        assert items[source_name]["source_type"] == "direct_vendor"
        assert items[source_name]["discovery_enabled"] is True
        assert items[source_name]["capture_implemented"] is False
        assert "discovery-only" in items[source_name]["notes"]

def test_source_url_agent_run_api_rejects_missing_database(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(DATABASE_URL_ENV_VAR, raising=False)
    client = TestClient(create_app())

    response = client.post("/api/source-url-agent/runs", json={"source": "bestprice", "mode": "catalog"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "source_url_agent_database_required"

def test_get_source_url_agent_candidates_returns_persisted_candidates(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)

    response = client.get("/api/source-url-agent/candidates?status=needs_review&limit=50&offset=0")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 50
    assert payload["offset"] == 0
    assert payload["items"][0]["id"] == candidate.id
    assert payload["items"][0]["evidence_json"]["mpn"]["found"] is True


def test_source_url_agent_canonical_namespace_returns_candidates_and_sources(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)

    candidates_response = client.get("/api/source-url-agent/candidates?status=needs_review")
    sources_response = client.get("/api/source-url-agent/sources")

    assert candidates_response.status_code == 200
    assert candidates_response.json()["items"][0]["id"] == candidate.id
    assert sources_response.status_code == 200
    assert {item["source_name"] for item in sources_response.json()["items"]} >= {"bestprice", "skroutz", "electronet"}


def test_get_source_url_agent_candidates_filters(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        first_product = _catalog_product(session, model="ABC-1", mpn="MPN-A")
        second_product = _catalog_product(session, model="XYZ-2", mpn="MPN-B")
        wanted = _candidate(
            session,
            first_product,
            run_id="run-filter",
            source_name="BestPrice",
            confidence_score=Decimal("0.7500"),
            model="ABC-1",
        )
        _candidate(
            session,
            second_product,
            run_id="run-other",
            source_name="skroutz",
            confidence_score=Decimal("0.4000"),
            model="XYZ-2",
            status="rejected",
        )

    response = client.get(
        "/api/source-url-agent/candidates",
        params={
            "status": "needs_review",
            "source_name": "best",
            "run_id": "run-filter",
            "model": "abc",
            "catalog_product_id": str(first_product.id),
            "min_confidence": "0.7",
            "max_confidence": "0.8",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == wanted.id


def test_get_source_url_agent_candidates_returns_empty_for_no_matches(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        _candidate(session, product)

    response = client.get("/api/source-url-agent/candidates", params={"status": "accepted"})

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


def test_get_source_url_agent_candidate_returns_review_panel_payload(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)

    response = client.get(f"/api/source-url-agent/candidates/{candidate.id}")
    missing = client.get("/api/source-url-agent/candidates/999")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == candidate.id
    assert "drawer" not in payload
    assert payload["review_panel"]["mode"] == "inline_row"
    assert payload["review_panel"]["open_on"] == "row_single_click"
    assert payload["review_panel"]["review_endpoint"] == f"/api/source-url-agent/candidates/{candidate.id}/review"
    assert [action["decision"] for action in payload["review_panel"]["review_actions"]] == [
        "accept",
        "replace_url",
        "reject",
    ]
    assert missing.status_code == 404


def test_patch_accept_updates_candidate_and_creates_source_url(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)

    response = client.patch(
        f"/api/source-url-agent/candidates/{candidate.id}/review",
        json={"decision": "accept", "review_notes": "approved", "reviewed_by": "tester"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["reviewed_by"] == "tester"
    assert payload["source_url"]["action"] == "created"
    with session_scope(database_url) as session:
        stored = session.query(SourceUrl).one()
        candidate_row = session.get(SourceUrlCandidate, candidate.id)
        assert stored.url == candidate.candidate_url
        assert stored.status == "active"
        assert stored.url_type == "discovered"
        assert stored.trust_level == "manual"
        assert candidate_row.status == "accepted"


def test_patch_reject_updates_candidate_without_source_url(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)

    response = client.patch(f"/api/source-url-agent/candidates/{candidate.id}/review", json={"decision": "reject"})

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    with session_scope(database_url) as session:
        assert session.query(SourceUrl).count() == 0


def test_patch_removed_review_decisions_fail_validation(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)

    not_found = client.patch(f"/api/source-url-agent/candidates/{candidate.id}/review", json={"decision": "not_found"})
    needs_manual_review = client.patch(
        f"/api/source-url-agent/candidates/{candidate.id}/review",
        json={"decision": "needs_manual_review"},
    )

    assert not_found.status_code == 422
    assert needs_manual_review.status_code == 422
    with session_scope(database_url) as session:
        candidate_row = session.get(SourceUrlCandidate, candidate.id)
        assert candidate_row.status == "needs_review"
        assert session.query(SourceUrl).count() == 0


def test_patch_replace_url_requires_reviewed_url_and_promotes_reviewed_url(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)

    missing = client.patch(
        f"/api/source-url-agent/candidates/{candidate.id}/review",
        json={"decision": "replace_url"},
    )
    reviewed_url = "https://www.bestprice.gr/item/2/replacement.html"
    replaced = client.patch(
        f"/api/source-url-agent/candidates/{candidate.id}/review",
        json={"decision": "replace_url", "reviewed_url": reviewed_url},
    )

    assert missing.status_code == 400
    assert missing.json()["detail"] == "reviewed_url is required for replace_url."
    assert replaced.status_code == 200
    assert replaced.json()["status"] == "accepted"
    with session_scope(database_url) as session:
        stored = session.query(SourceUrl).one()
        assert stored.url == reviewed_url


def test_duplicate_promotion_does_not_create_duplicate_source_url(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        existing = _source_url(session, product, url="https://www.bestprice.gr/item/1/lg-remote.html")
        candidate = _candidate(session, product, url=existing.url)

    response = client.patch(f"/api/source-url-agent/candidates/{candidate.id}/review", json={"decision": "accept"})

    assert response.status_code == 200
    assert response.json()["source_url"]["source_url_id"] == existing.id
    with session_scope(database_url) as session:
        assert session.query(SourceUrl).count() == 1


def test_source_url_agent_candidate_routes_return_404_and_validation_errors(tmp_path: Path, monkeypatch) -> None:
    client, _database_url = _client(tmp_path, monkeypatch)

    missing = client.patch("/api/source-url-agent/candidates/999/review", json={"decision": "reject"})
    invalid_decision = client.patch("/api/source-url-agent/candidates/999/review", json={"decision": "bad"})
    invalid_product_id = client.get("/api/source-url-agent/candidates", params={"catalog_product_id": "bad"})

    assert missing.status_code == 404
    assert missing.json()["detail"] == "Source URL candidate not found."
    assert invalid_decision.status_code == 422
    assert invalid_product_id.status_code == 400
    assert invalid_product_id.json()["detail"] == "catalog_product_id must be an integer."


def test_openapi_includes_source_url_agent_candidate_endpoints() -> None:
    paths = create_app().openapi()["paths"]

    assert "/api/vendor-sources/agent/runs" not in paths
    assert "/api/vendor-sources/agent/runs/{run_id}" not in paths
    assert "/api/vendor-sources/agent/runs/{run_id}/artifacts" not in paths
    assert "/api/vendor-sources/candidates" not in paths
    assert "/api/vendor-sources/candidates/{candidate_id}" not in paths
    assert "/api/vendor-sources/candidates/{candidate_id}/review" not in paths
    assert "/api/source-url-agent/runs" in paths
    assert "/api/source-url-agent/runs/{run_id}" in paths
    assert "/api/source-url-agent/runs/{run_id}/artifacts" in paths
    assert "/api/source-url-agent/candidates" in paths
    assert "/api/source-url-agent/candidates/review-layout" not in paths
    assert "/api/source-url-agent/candidates/review-layout/reset" not in paths
    assert "/api/source-url-agent/candidates/{candidate_id}/review" in paths
    assert "/api/vendor-sources/sources" in paths
    assert "/api/source-url-agent/sources" in paths
    assert "/api/source-url-agent/runs" in paths
    assert "/api/source-url-agent/runs/sync" in paths
    assert "/api/source-url-agent/runs/{run_id}" in paths
    assert "/api/source-url-agent/runs/{run_id}/artifacts" in paths
    assert "/api/source-url-agent/candidates" in paths
    assert "/api/source-url-agent/candidates/{candidate_id}" in paths
    assert "/api/source-url-agent/candidates/{candidate_id}/review" in paths
    assert "/api/vendor-sources/captures/runs" in paths
    assert "/api/vendor-sources/captures/runs/{run_id}" in paths
    assert "/api/vendor-sources/captures/runs/{run_id}/artifacts" in paths


def test_price_monitoring_exposes_no_marketplace_source_enum() -> None:
    import ecommerce.price_monitoring.selection as selection

    assert not hasattr(selection, "PriceMonitoringSource")
    assert not hasattr(selection, "MarketplaceMonitoringSource")
