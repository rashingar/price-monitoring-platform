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
from ecommerce.db.session import get_engine, session_scope  # noqa: E402


NOW = datetime(2026, 5, 12, 8, tzinfo=timezone.utc)


def _client(tmp_path: Path, monkeypatch) -> tuple[TestClient, str]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'vendor-sources-coverage.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    Base.metadata.create_all(get_engine(database_url))
    return TestClient(create_app()), database_url


def _catalog_product(session, *, model: str, active: bool = True) -> CatalogProductRow:
    row = CatalogProductRow(
        catalog_source="sourceCata",
        model=model,
        mpn=f"MPN-{model}",
        name=f"Product {model}",
        category="",
        raw_category="",
        manufacturer="Brand",
        active=active,
        imported_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(row)
    session.flush()
    return row


def _source_url(
    session,
    product: CatalogProductRow,
    *,
    source_name: str,
    status: str = "active",
    url_type: str = "manual",
) -> SourceUrl:
    url = f"https://www.{source_name}.gr/p/{product.model}"
    row = SourceUrl(
        catalog_product_id=product.id,
        catalog_source=product.catalog_source,
        model=product.model,
        mpn=product.mpn,
        manufacturer=product.manufacturer,
        source_name=source_name,
        source_domain=f"www.{source_name}.gr",
        url=url,
        url_normalized=url,
        status=status,
        url_type=url_type,
        trust_level=url_type,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(row)
    session.flush()
    return row


def test_vendor_source_url_summary_reports_coverage_and_grouped_counters(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        first = _catalog_product(session, model="005606")
        second = _catalog_product(session, model="123456")
        third = _catalog_product(session, model="999999")
        inactive = _catalog_product(session, model="OLD", active=False)
        _source_url(session, first, source_name="bestprice", status="active", url_type="manual")
        _source_url(session, first, source_name="skroutz", status="needs_review", url_type="imported")
        _source_url(session, second, source_name="bestprice", status="disabled", url_type="imported")
        _source_url(session, inactive, source_name="bestprice", status="active", url_type="manual")

    response = client.get("/api/vendor-sources/source-urls/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["catalog_product_count"] == 3
    assert payload["source_url_count"] == 3
    assert payload["products_with_active_source_urls"] == 1
    assert payload["products_without_active_source_urls"] == 2
    assert payload["coverage_percent"] == 33.33
    assert payload["by_status"]["active"] == 1
    assert payload["by_status"]["needs_review"] == 1
    assert payload["by_status"]["disabled"] == 1
    assert payload["by_source_name"] == {"bestprice": 2, "skroutz": 1}
    assert payload["by_url_type"]["manual"] == 1
    assert payload["by_url_type"]["imported"] == 2
    assert payload["missing_source_url_models"] == [second.model, third.model]


def test_vendor_source_url_summary_filters_by_source_name(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        first = _catalog_product(session, model="005606")
        second = _catalog_product(session, model="123456")
        third = _catalog_product(session, model="999999")
        _source_url(session, first, source_name="bestprice", status="active", url_type="manual")
        _source_url(session, first, source_name="skroutz", status="active", url_type="manual")
        _source_url(session, second, source_name="bestprice", status="disabled", url_type="imported")

    response = client.get("/api/vendor-sources/source-urls/summary?source_name=bestprice")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_name"] == "bestprice"
    assert payload["catalog_product_count"] == 3
    assert payload["source_url_count"] == 2
    assert payload["products_with_active_source_urls"] == 1
    assert payload["products_without_active_source_urls"] == 2
    assert payload["coverage_percent"] == 33.33
    assert payload["by_status"]["active"] == 1
    assert payload["by_status"]["disabled"] == 1
    assert payload["by_source_name"] == {"bestprice": 2}
    assert payload["missing_source_url_models"] == [second.model, third.model]
