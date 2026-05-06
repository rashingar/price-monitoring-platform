import sys
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models import Base, CatalogProductRow, MonitoringRun, PriceObservation, SourceUrl  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402


NOW = datetime(2026, 4, 29, 12, tzinfo=timezone.utc)


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"


def _client(tmp_path: Path, monkeypatch) -> tuple[TestClient, str]:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    Base.metadata.create_all(get_engine(database_url))
    return TestClient(create_app()), database_url


def _catalog_product(session, *, model: str, mpn: str = "MPN-1", active: bool = True) -> CatalogProductRow:
    row = CatalogProductRow(
        catalog_source="sourceCata",
        model=model,
        mpn=mpn,
        name=f"Product {model}",
        category="Family",
        raw_category="Family",
        manufacturer="Brand",
        active=active,
        imported_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(row)
    session.flush()
    return row


def _run(session, *, run_id: str = "run-1", source: str = "skroutz", enriched_csv_path: str | None = None) -> MonitoringRun:
    run = MonitoringRun(
        run_id=run_id,
        source=source,
        status="fetch_completed",
        enriched_csv_path=enriched_csv_path,
        created_at=NOW,
        started_at=NOW,
        completed_at=NOW,
        updated_at=NOW,
    )
    session.add(run)
    session.flush()
    return run


def _observation(
    session,
    run: MonitoringRun,
    *,
    url: str,
    model: str,
    mpn: str = "MPN-1",
) -> PriceObservation:
    observation = PriceObservation(
        monitoring_run_id=run.id,
        run_id=run.run_id,
        catalog_source="sourceCata",
        source=run.source,
        model=model,
        mpn=mpn,
        competitor_price=Decimal("119.90"),
        currency="EUR",
        product_url=url,
        match_status="matched",
        observed_at=NOW,
        created_at=NOW,
    )
    session.add(observation)
    session.flush()
    return observation


def _source_url(
    session,
    product: CatalogProductRow,
    *,
    url: str,
    status: str = "active",
    url_type: str = "manual",
    source_name: str = "skroutz",
) -> SourceUrl:
    row = SourceUrl(
        catalog_product_id=product.id,
        catalog_source=product.catalog_source,
        model=product.model,
        mpn=product.mpn,
        manufacturer=product.manufacturer,
        source_name=source_name,
        source_domain="www.skroutz.gr" if "skroutz" in url else "www.bestprice.gr",
        url=url,
        url_normalized=url,
        status=status,
        url_type=url_type,
        trust_level=url_type,
        added_by="tester" if url_type == "manual" else None,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(row)
    session.flush()
    return row


def test_source_url_summary_counts_coverage_and_groups(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        first = _catalog_product(session, model="005606")
        second = _catalog_product(session, model="123456", mpn="MPN-2")
        third = _catalog_product(session, model="999999", mpn="MPN-3")
        inactive = _catalog_product(session, model="OLD", active=False)
        _source_url(session, first, url="https://www.skroutz.gr/s/1", status="active", url_type="manual")
        _source_url(session, first, url="https://www.bestprice.gr/item/1", status="needs_review", url_type="imported", source_name="bestprice")
        _source_url(session, second, url="https://www.skroutz.gr/s/2", status="disabled", url_type="imported")
        _source_url(session, inactive, url="https://www.skroutz.gr/s/old", status="active", url_type="imported")

    response = client.get("/api/catalog/source-urls/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["catalog_product_count"] == 3
    assert payload["products_with_active_source_urls"] == 1
    assert payload["products_without_active_source_urls"] == 2
    assert payload["coverage_percent"] == 33.33
    assert payload["source_url_count"] == 3
    assert payload["by_status"]["active"] == 1
    assert payload["by_status"]["needs_review"] == 1
    assert payload["by_status"]["disabled"] == 1
    assert payload["by_source_name"]["skroutz"] == 2
    assert payload["by_source_name"]["bestprice"] == 1
    assert payload["by_url_type"]["manual"] == 1
    assert payload["by_url_type"]["imported"] == 2
    assert third.id > 0


def test_preview_returns_report_without_writes(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        _catalog_product(session, model="005606")
        run = _run(session)
        _observation(session, run, url="https://www.skroutz.gr/s/1", model="005606")

    response = client.post("/api/catalog/source-urls/import/preview", json={"report_items_limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "preview"
    assert payload["applied"] is False
    assert payload["summary"]["candidates_found"] == 1
    assert payload["summary"]["would_import_count"] == 1
    assert payload["summary"]["imported_count"] == 0
    assert payload["sources"]["observations"]["processed"] == 1
    assert payload["items"][0]["action"] == "would_import"
    with session_scope(database_url) as session:
        assert session.query(SourceUrl).count() == 0


def test_apply_writes_rows_and_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        _catalog_product(session, model="005606")
        run = _run(session)
        _observation(session, run, url="https://www.skroutz.gr/s/1", model="005606")

    first = client.post("/api/catalog/source-urls/import/apply", json={})
    second = client.post("/api/catalog/source-urls/import/apply", json={})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["summary"]["imported_count"] == 1
    assert first.json()["items"][0]["source_url_id"] is not None
    assert second.json()["summary"]["duplicate_count"] == 1
    with session_scope(database_url) as session:
        assert session.query(SourceUrl).count() == 1


def test_product_factory_handoff_preview_and_apply(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ECOMMERCE_FILE_ROOTS", str(tmp_path / "work"))
    client, database_url = _client(tmp_path, monkeypatch)
    handoff_path = tmp_path / "work" / "005606" / "integrations" / "ecommerce_source_handoff.json"
    handoff_path.parent.mkdir(parents=True)
    with session_scope(database_url) as session:
        product = _catalog_product(session, model="005606")
        handoff_path.write_text(
            json.dumps(
                {
                    "schema_version": "v1",
                    "catalog_source": "sourceCata",
                    "product": {"catalog_product_id": product.id, "model": "005606", "mpn": "MPN-1"},
                    "sources": [
                        {
                            "source_name": "skroutz",
                            "url": "https://www.skroutz.gr/s/1?utm_campaign=x",
                            "confidence": 0.95,
                            "evidence": {"identity": "exact"},
                            "price_evidence": {"price": "119.90", "observed_at": "2026-04-29T12:00:00Z"},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    preview = client.post("/api/catalog/source-urls/import/product-factory/preview", json={"file": str(handoff_path)})
    apply = client.post("/api/catalog/source-urls/import/product-factory/apply", json={"file": str(handoff_path)})

    assert preview.status_code == 200
    assert apply.status_code == 200
    assert preview.json()["summary"]["would_import_count"] == 1
    assert preview.json()["sources"]["product_factory_handoff"]["candidates"] == 1
    assert apply.json()["summary"]["imported_count"] == 1
    assert apply.json()["items"][0]["action"] == "imported"
    with session_scope(database_url) as session:
        row = session.query(SourceUrl).one()
        assert row.url_normalized == "https://www.skroutz.gr/s/1"


def test_product_factory_handoff_import_rejects_paths_outside_allowed_roots(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ECOMMERCE_FILE_ROOTS", str(tmp_path / "allowed"))
    client, _database_url = _client(tmp_path, monkeypatch)
    outside_path = tmp_path / "outside" / "ecommerce_source_handoff.json"
    outside_path.parent.mkdir(parents=True)
    outside_path.write_text("{}", encoding="utf-8")

    response = client.post("/api/catalog/source-urls/import/product-factory/preview", json={"file": str(outside_path)})
    traversal = client.post(
        "/api/catalog/source-urls/import/product-factory/preview",
        json={"file": str(tmp_path / "allowed" / ".." / "ecommerce_source_handoff.json")},
    )

    assert response.status_code == 400
    assert "allowed artifact roots or configured file roots" in response.json()["detail"]
    assert traversal.status_code == 400
    assert "path traversal" in traversal.json()["detail"]


def test_preview_and_apply_preserve_manual_and_disabled_urls(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session, model="005606")
        manual = _source_url(session, product, url="https://www.skroutz.gr/s/manual", status="active", url_type="manual")
        disabled = _source_url(session, product, url="https://www.skroutz.gr/s/disabled", status="disabled", url_type="imported")
        run = _run(session)
        _observation(session, run, url=manual.url, model="005606")
        _observation(session, run, url=disabled.url, model="005606")

    preview = client.post("/api/catalog/source-urls/import/preview", json={})
    apply = client.post("/api/catalog/source-urls/import/apply", json={})

    assert preview.status_code == 200
    assert apply.status_code == 200
    with session_scope(database_url) as session:
        rows = {row.url: row for row in session.query(SourceUrl).all()}
        assert rows[manual.url].url_type == "manual"
        assert rows[manual.url].trust_level == "manual"
        assert rows[manual.url].added_by == "tester"
        assert rows[disabled.url].status == "disabled"


def test_import_report_item_truncation_keeps_full_counters(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        run = _run(session)
        for index in range(3):
            model = f"MODEL-{index}"
            _catalog_product(session, model=model, mpn=f"MPN-{index}")
            _observation(session, run, url=f"https://www.skroutz.gr/s/{index}", model=model, mpn=f"MPN-{index}")

    response = client.post("/api/catalog/source-urls/import/preview", json={"report_items_limit": 2})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["candidates_found"] == 3
    assert payload["summary"]["would_import_count"] == 3
    assert len(payload["items"]) == 2
    assert payload["truncated"] is True


def test_import_invalid_options_return_400(tmp_path: Path, monkeypatch) -> None:
    client, _database_url = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/catalog/source-urls/import/preview",
        json={"include_observations": False, "include_artifacts": False},
    )

    assert response.status_code == 400


def test_import_routes_return_catalog_db_required_without_database(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, "")
    client = TestClient(create_app())

    responses = [
        client.get("/api/catalog/source-urls/summary"),
        client.post("/api/catalog/source-urls/import/preview", json={}),
        client.post("/api/catalog/source-urls/import/apply", json={}),
    ]

    assert {response.status_code for response in responses} == {503}
    assert all(response.json()["detail"]["code"] == "catalog_database_required" for response in responses)


def test_import_options_note_describes_db_backed_capture() -> None:
    response = TestClient(create_app()).get("/api/catalog/source-urls/import/options")

    assert response.status_code == 200
    notes = response.json()["notes"]
    assert "Monitoring fetch behavior does not use stored source URLs yet." not in notes
    assert "Stored source URLs can be captured through DB-backed Vendor Sources capture." in notes


def test_openapi_includes_source_url_import_endpoints() -> None:
    paths = create_app().openapi()["paths"]

    assert "/api/catalog/source-urls/summary" in paths
    assert "/api/catalog/source-urls/import/preview" in paths
    assert "/api/catalog/source-urls/import/apply" in paths
    assert "/api/catalog/source-urls/import/product-factory/preview" in paths
    assert "/api/catalog/source-urls/import/product-factory/apply" in paths
    assert "/api/catalog/source-urls/import/options" in paths
