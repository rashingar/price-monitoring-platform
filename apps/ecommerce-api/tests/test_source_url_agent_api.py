import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api import routes_source_url_agent  # noqa: E402
from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models import Base, CatalogProductRow, SourceUrl, SourceUrlCandidate, SourceUrlDiscoveryRun, UiViewPreference  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.source_url_agent.evidence import PageEvidence  # noqa: E402
from ecommerce.source_url_agent.search import SourceSearchResult  # noqa: E402


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


def _allow_source_url_agent_run_database(monkeypatch) -> None:
    monkeypatch.setattr(routes_source_url_agent, "_require_source_url_agent_run_database_ready", lambda: None)


def _fake_resolver(product, source) -> SourceSearchResult:
    url = f"https://{source.source_domain}/item/{product.model}/lg-remote.html"
    evidence = PageEvidence(
        requested_url=url,
        final_url=url,
        canonical_url=url,
        title=f"{product.manufacturer} {product.mpn} remote control",
        body_text_sample=f"{product.manufacturer} {product.mpn}",
        candidate_price=Decimal("18.50"),
        exact_mpn_found=True,
        exact_mpn_fragment=product.mpn,
        exact_mpn_source="title",
        exact_model_found=False,
        exact_model_fragment="",
        exact_model_source="",
        brand_found=True,
        brand_fragment=product.manufacturer,
        category_compatible=True,
        category_fragment=product.category,
        title_similarity=0.95,
        title_matched_tokens=(product.manufacturer.lower(), product.mpn.lower()),
        price_compatible=None,
        jsonld_products=(),
    )
    return SourceSearchResult(evidence=[evidence], searched_queries=[f"{product.manufacturer} {product.mpn}"], searched_urls=[], errors=[])


def _run_api_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, str]:
    monkeypatch.chdir(tmp_path)
    _allow_source_url_agent_run_database(monkeypatch)
    monkeypatch.setattr(routes_source_url_agent, "SOURCE_URL_AGENT_API_RESOLVER", _fake_resolver)
    return _client(tmp_path, monkeypatch)


def test_source_url_agent_run_api_dry_run_from_catalog_persists_run_and_candidates(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _run_api_client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)

    response = client.post(
        "/api/vendor-sources/agent/runs",
        json={
            "source": "bestprice",
            "mode": "catalog",
            "catalog_product_id": product.id,
            "limit": 1,
            "dry_run": True,
            "max_products_per_batch": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"]
    assert payload["dry_run"] is True
    assert payload["summary"]["selected_count"] == 1
    assert payload["summary"]["matched_count"] == 1
    assert payload["summary"]["persisted_candidate_count"] == 1
    assert any(item["artifact_key"] == "source_url_run_summary" for item in payload["artifacts"])
    assert all(item["is_allowed"] for item in payload["artifacts"])
    with session_scope(database_url) as session:
        run = session.query(SourceUrlDiscoveryRun).one()
        candidate = session.query(SourceUrlCandidate).one()
        assert run.run_id == payload["run_id"]
        assert run.source_name == "bestprice"
        assert candidate.run_id == payload["run_id"]
        assert candidate.match_status == "matched"
    history = client.get("/api/vendor-sources/agent/runs")
    detail = client.get(f"/api/vendor-sources/agent/runs/{payload['run_id']}")
    assert history.status_code == 200
    assert history.json()["items"][0]["run_id"] == payload["run_id"]
    assert detail.status_code == 200
    assert detail.json()["run_id"] == payload["run_id"]
    assert detail.json()["artifacts"]


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
    assert items["bestprice"]["capture_implemented"] is False
    for source_name in ("plaisio", "public", "kotsovolos"):
        assert items[source_name]["source_type"] == "direct_vendor"
        assert items[source_name]["discovery_enabled"] is True
        assert items[source_name]["capture_implemented"] is False
        assert "discovery-only" in items[source_name]["notes"]


def test_vendor_sources_agent_run_namespace_delegates_to_source_url_agent(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _run_api_client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)

    response = client.post(
        "/api/vendor-sources/agent/runs",
        json={
            "source": "electronet",
            "mode": "catalog",
            "catalog_product_id": product.id,
            "limit": 1,
            "dry_run": True,
            "max_products_per_batch": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "electronet"
    history = client.get("/api/vendor-sources/agent/runs")
    assert history.status_code == 200
    assert history.json()["items"][0]["run_id"] == payload["run_id"]


def test_source_url_agent_run_api_rejects_missing_database(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(DATABASE_URL_ENV_VAR, raising=False)
    client = TestClient(create_app())

    response = client.post("/api/vendor-sources/agent/runs", json={"source": "bestprice", "mode": "catalog"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "source_url_agent_database_required"


def test_source_url_agent_run_api_enforces_bounded_default_limit(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _run_api_client(tmp_path, monkeypatch)
    monkeypatch.setattr(routes_source_url_agent, "DEFAULT_API_MAX_PRODUCTS_PER_BATCH", 2)
    with session_scope(database_url) as session:
        for index in range(4):
            _catalog_product(session, model=f"MODEL-{index}", mpn=f"MPN-{index}")

    response = client.post("/api/vendor-sources/agent/runs", json={"source": "bestprice", "mode": "catalog"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["selected_count"] == 2
    with session_scope(database_url) as session:
        assert session.query(SourceUrlCandidate).count() == 2


def test_source_url_agent_run_artifact_endpoint_returns_safe_metadata(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _run_api_client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)

    run_response = client.post(
        "/api/vendor-sources/agent/runs",
        json={"source": "bestprice", "mode": "catalog", "catalog_product_id": product.id, "limit": 1},
    )
    run_id = run_response.json()["run_id"]
    artifact_response = client.get(f"/api/vendor-sources/agent/runs/{run_id}/artifacts")

    assert artifact_response.status_code == 200
    payload = artifact_response.json()
    assert payload["run_id"] == run_id
    names = {item["name"] for item in payload["items"]}
    assert "source_url_run_summary.json" in names
    assert all(item["is_allowed"] for item in payload["items"])
    assert all(item["read_url"].startswith("/api/artifacts/read?path=") for item in payload["items"])


def test_get_source_url_agent_candidates_returns_persisted_candidates(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)

    response = client.get("/api/vendor-sources/candidates?status=needs_review&limit=50&offset=0")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 50
    assert payload["offset"] == 0
    assert payload["items"][0]["id"] == candidate.id
    assert payload["items"][0]["evidence_json"]["mpn"]["found"] is True


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
        "/api/vendor-sources/candidates",
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

    response = client.get("/api/vendor-sources/candidates", params={"status": "accepted"})

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


def test_source_url_candidate_review_layout_defaults_and_persistence(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)

    default_response = client.get("/api/vendor-sources/candidates/review-layout")

    assert default_response.status_code == 200
    default_payload = default_response.json()
    assert default_payload["view_key"] == "source_url_candidate_review"
    assert default_payload["settings_card"]["collapsible"] is True
    assert default_payload["settings_card"]["collapsed"] is True
    assert default_payload["actions"]["table_column_visible"] is False
    assert default_payload["action_panel"]["mode"] == "drawer"
    assert default_payload["action_panel"]["open_on"] == "row_single_click"
    assert "actions" not in [column["key"] for column in default_payload["columns"]]

    save_response = client.put(
        "/api/vendor-sources/candidates/review-layout",
        json={
            "user_key": "tester",
            "settings_card_collapsed": False,
            "action_panel_width_px": 520,
            "columns": [
                {"key": "candidate_url", "visible": True, "order": 5, "width_px": 360},
                {"key": "status", "visible": False, "order": 40, "width_px": 128},
            ],
        },
    )

    assert save_response.status_code == 200
    saved_payload = save_response.json()
    columns = {column["key"]: column for column in saved_payload["columns"]}
    assert saved_payload["user_key"] == "tester"
    assert saved_payload["settings_card"]["collapsed"] is False
    assert saved_payload["action_panel"]["width_px"] == 520
    assert columns["candidate_url"]["visible"] is True
    assert columns["candidate_url"]["order"] == 5
    assert columns["candidate_url"]["width_px"] == 360
    assert columns["status"]["visible"] is False

    persisted_response = client.get("/api/vendor-sources/candidates/review-layout", params={"user_key": "tester"})

    assert persisted_response.status_code == 200
    assert persisted_response.json()["columns"][0]["key"] == "candidate_url"
    with session_scope(database_url) as session:
        stored = session.query(UiViewPreference).one()
        assert stored.view_key == "source_url_candidate_review"
        assert stored.user_key == "tester"


def test_source_url_candidate_review_layout_validates_columns_and_resets(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)

    unknown = client.put(
        "/api/vendor-sources/candidates/review-layout",
        json={"columns": [{"key": "actions", "visible": True}]},
    )
    duplicate = client.put(
        "/api/vendor-sources/candidates/review-layout",
        json={"columns": [{"key": "status"}, {"key": "status"}]},
    )
    bad_width = client.put(
        "/api/vendor-sources/candidates/review-layout",
        json={"columns": [{"key": "status", "width_px": 20}]},
    )
    saved = client.put(
        "/api/vendor-sources/candidates/review-layout",
        json={"user_key": "tester", "columns": [{"key": "status", "visible": False}]},
    )
    reset = client.post("/api/vendor-sources/candidates/review-layout/reset", params={"user_key": "tester"})

    assert unknown.status_code == 400
    assert "Unknown" in unknown.json()["detail"]
    assert duplicate.status_code == 400
    assert bad_width.status_code == 400
    assert saved.status_code == 200
    assert reset.status_code == 200
    assert reset.json()["settings_card"]["collapsed"] is True
    with session_scope(database_url) as session:
        assert session.query(UiViewPreference).count() == 0


def test_get_source_url_agent_candidate_returns_drawer_payload(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)

    response = client.get(f"/api/vendor-sources/candidates/{candidate.id}")
    missing = client.get("/api/vendor-sources/candidates/999")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == candidate.id
    assert payload["drawer"]["open_on"] == "row_single_click"
    assert payload["drawer"]["review_endpoint"] == f"/api/vendor-sources/candidates/{candidate.id}/review"
    assert [action["decision"] for action in payload["drawer"]["review_actions"]] == [
        "accept",
        "replace_url",
        "reject",
        "not_found",
        "needs_manual_review",
    ]
    assert missing.status_code == 404


def test_patch_accept_updates_candidate_and_creates_source_url(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)

    response = client.patch(
        f"/api/vendor-sources/candidates/{candidate.id}/review",
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

    response = client.patch(f"/api/vendor-sources/candidates/{candidate.id}/review", json={"decision": "reject"})

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    with session_scope(database_url) as session:
        assert session.query(SourceUrl).count() == 0


def test_patch_not_found_updates_candidate_without_source_url(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)

    response = client.patch(f"/api/vendor-sources/candidates/{candidate.id}/review", json={"decision": "not_found"})

    assert response.status_code == 200
    assert response.json()["status"] == "not_found"
    with session_scope(database_url) as session:
        assert session.query(SourceUrl).count() == 0


def test_patch_needs_manual_review_keeps_candidate_in_review_without_source_url(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product, status="rejected")

    response = client.patch(
        f"/api/vendor-sources/candidates/{candidate.id}/review",
        json={"decision": "needs_manual_review"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "needs_review"
    with session_scope(database_url) as session:
        assert session.query(SourceUrl).count() == 0


def test_patch_replace_url_requires_reviewed_url_and_promotes_reviewed_url(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)

    missing = client.patch(
        f"/api/vendor-sources/candidates/{candidate.id}/review",
        json={"decision": "replace_url"},
    )
    reviewed_url = "https://www.bestprice.gr/item/2/replacement.html"
    replaced = client.patch(
        f"/api/vendor-sources/candidates/{candidate.id}/review",
        json={"decision": "replace_url", "reviewed_url": reviewed_url},
    )

    assert missing.status_code == 400
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

    response = client.patch(f"/api/vendor-sources/candidates/{candidate.id}/review", json={"decision": "accept"})

    assert response.status_code == 200
    assert response.json()["source_url"]["source_url_id"] == existing.id
    with session_scope(database_url) as session:
        assert session.query(SourceUrl).count() == 1


def test_source_url_agent_candidate_routes_return_404_and_validation_errors(tmp_path: Path, monkeypatch) -> None:
    client, _database_url = _client(tmp_path, monkeypatch)

    missing = client.patch("/api/vendor-sources/candidates/999/review", json={"decision": "reject"})
    invalid_decision = client.patch("/api/vendor-sources/candidates/999/review", json={"decision": "bad"})
    invalid_product_id = client.get("/api/vendor-sources/candidates", params={"catalog_product_id": "bad"})

    assert missing.status_code == 404
    assert invalid_decision.status_code == 422
    assert invalid_product_id.status_code == 400


def test_openapi_includes_source_url_agent_candidate_endpoints() -> None:
    paths = create_app().openapi()["paths"]

    assert "/api/vendor-sources/agent/runs" in paths
    assert "/api/vendor-sources/agent/runs/{run_id}" in paths
    assert "/api/vendor-sources/agent/runs/{run_id}/artifacts" in paths
    assert "/api/vendor-sources/candidates" in paths
    assert "/api/vendor-sources/candidates/{candidate_id}/review" in paths
    assert "/api/vendor-sources/sources" in paths
    assert "/api/vendor-sources/captures/runs" in paths
    assert "/api/vendor-sources/captures/runs/{run_id}" in paths
    assert "/api/vendor-sources/captures/runs/{run_id}/artifacts" in paths


def test_price_monitoring_exposes_no_marketplace_source_enum() -> None:
    import ecommerce.price_monitoring.selection as selection

    assert not hasattr(selection, "PriceMonitoringSource")
    assert not hasattr(selection, "MarketplaceMonitoringSource")
