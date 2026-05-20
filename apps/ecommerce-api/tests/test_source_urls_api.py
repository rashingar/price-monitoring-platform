import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api import routes_source_urls  # noqa: E402
from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.catalog.source_catalog import SOURCE_CATA_ENV_VAR  # noqa: E402
from ecommerce.catalog_db import ingest_source_catalog  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models.base import Base  # noqa: E402
from ecommerce.db.models.source_urls import SourceUrl  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.ignore.product_ignore import PRICE_IGNORE_ENV_VAR  # noqa: E402
from ecommerce.source_urls import SourceUrlValidationResult  # noqa: E402


def _write_catalog(path: Path) -> None:
    path.write_text(
        "model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n"
        "005606,MPN-1,Product One,Family,Brand A,123.45,1,1,1,1\n"
        "123456,MPN-2,Product Two,Family,Brand B,99.00,1,1,0,1\n",
        encoding="utf-8-sig",
    )


def _client_with_catalog(tmp_path: Path, monkeypatch) -> tuple[TestClient, str]:
    catalog_path = tmp_path / "sourceCata.csv"
    _write_catalog(catalog_path)
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    monkeypatch.setenv(SOURCE_CATA_ENV_VAR, str(catalog_path))
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(tmp_path / "missing-price-ignore.csv"))
    Base.metadata.create_all(get_engine(database_url))
    with session_scope(database_url) as session:
        ingest_source_catalog(session, source_cata_path=catalog_path)
    return TestClient(create_app()), database_url


def _catalog_product_ids(client: TestClient) -> list[int]:
    response = client.get("/api/catalog/products")
    assert response.status_code == 200
    return [int(item["catalog_product_id"]) for item in response.json()["items"]]


def _post_source_url(
    client: TestClient, catalog_product_id: int, url: str, **payload
) -> dict:
    response = client.post(
        f"/api/catalog/products/{catalog_product_id}/source-urls",
        json={"url": url, **payload},
    )
    assert response.status_code == 200
    return response.json()


def test_catalog_products_include_catalog_product_id(
    tmp_path: Path, monkeypatch
) -> None:
    client, _database_url = _client_with_catalog(tmp_path, monkeypatch)

    response = client.get("/api/catalog/products")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert isinstance(item["catalog_product_id"], int)
    assert item["catalog_product_id"] > 0


def test_post_manual_url_creates_active_url_and_infers_known_source(
    tmp_path: Path, monkeypatch
) -> None:
    client, _database_url = _client_with_catalog(tmp_path, monkeypatch)
    product_id = _catalog_product_ids(client)[0]

    item = _post_source_url(
        client, product_id, " HTTPS://WWW.Skroutz.GR/s/123?sku=ABC#details "
    )

    assert item["catalog_product_id"] == product_id
    assert item["status"] == "active"
    assert item["url_type"] == "manual"
    assert item["trust_level"] == "manual"
    assert item["source_domain"] == "www.skroutz.gr"
    assert item["source_name"] == "skroutz"
    assert item["url_normalized"] == "https://www.skroutz.gr/s/123?sku=ABC"
    assert item["failure_count"] == 0


def test_unknown_domain_is_accepted_as_unknown(tmp_path: Path, monkeypatch) -> None:
    client, _database_url = _client_with_catalog(tmp_path, monkeypatch)
    product_id = _catalog_product_ids(client)[0]

    item = _post_source_url(client, product_id, "https://shop.example.test/products/1")

    assert item["source_domain"] == "shop.example.test"
    assert item["source_name"] == "unknown"
    assert item["status"] == "active"


def test_duplicate_normalized_url_for_same_product_returns_existing_row(
    tmp_path: Path, monkeypatch
) -> None:
    client, database_url = _client_with_catalog(tmp_path, monkeypatch)
    product_id = _catalog_product_ids(client)[0]

    first = _post_source_url(
        client, product_id, "https://www.bestprice.gr/item/1#top", notes="first"
    )
    second = _post_source_url(
        client, product_id, "HTTPS://www.bestprice.gr/item/1", notes="second"
    )

    assert second["id"] == first["id"]
    assert second["notes"] == "second"
    with session_scope(database_url) as session:
        assert session.query(SourceUrl).count() == 1


def test_same_url_can_exist_for_different_catalog_products(
    tmp_path: Path, monkeypatch
) -> None:
    client, database_url = _client_with_catalog(tmp_path, monkeypatch)
    first_product_id, second_product_id = _catalog_product_ids(client)

    first = _post_source_url(
        client, first_product_id, "https://www.public.gr/product/1"
    )
    second = _post_source_url(
        client, second_product_id, "https://www.public.gr/product/1"
    )

    assert first["id"] != second["id"]
    with session_scope(database_url) as session:
        assert session.query(SourceUrl).count() == 2


def test_get_lists_source_urls_for_catalog_product(tmp_path: Path, monkeypatch) -> None:
    client, _database_url = _client_with_catalog(tmp_path, monkeypatch)
    product_id = _catalog_product_ids(client)[0]
    created = _post_source_url(
        client, product_id, "https://www.kotsovolos.gr/product/1"
    )

    response = client.get(f"/api/catalog/products/{product_id}/source-urls")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [created["id"]]


def test_patch_can_disable_and_reactivate_url(tmp_path: Path, monkeypatch) -> None:
    client, _database_url = _client_with_catalog(tmp_path, monkeypatch)
    product_id = _catalog_product_ids(client)[0]
    created = _post_source_url(client, product_id, "https://www.plaisio.gr/product/1")

    disabled = client.patch(
        f"/api/catalog/source-urls/{created['id']}", json={"status": "disabled"}
    ).json()
    active = client.patch(
        f"/api/catalog/source-urls/{created['id']}", json={"status": "active"}
    ).json()

    assert disabled["status"] == "disabled"
    assert active["status"] == "active"


def test_invalid_url_shape_is_rejected(tmp_path: Path, monkeypatch) -> None:
    client, _database_url = _client_with_catalog(tmp_path, monkeypatch)
    product_id = _catalog_product_ids(client)[0]

    response = client.post(
        f"/api/catalog/products/{product_id}/source-urls",
        json={"url": "ftp://example.test/p"},
    )

    assert response.status_code == 400
    assert "http:// or https://" in response.json()["detail"]


def test_validation_does_not_block_activation(tmp_path: Path, monkeypatch) -> None:
    client, _database_url = _client_with_catalog(tmp_path, monkeypatch)
    product_id = _catalog_product_ids(client)[0]

    item = _post_source_url(client, product_id, "https://not-validated.example.test/p")

    assert item["status"] == "active"
    assert item["last_seen_at"] is None


def test_validation_success_updates_health_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    client, _database_url = _client_with_catalog(tmp_path, monkeypatch)
    product_id = _catalog_product_ids(client)[0]
    created = _post_source_url(client, product_id, "https://www.skroutz.gr/s/1")
    monkeypatch.setattr(
        routes_source_urls,
        "validate_source_url_reachability",
        lambda _url: SourceUrlValidationResult(
            status="success", message="ok", http_status_code=200
        ),
    )

    response = client.post(f"/api/catalog/source-urls/{created['id']}/validate")

    assert response.status_code == 200
    item = response.json()["item"]
    assert response.json()["validation"]["status"] == "success"
    assert item["status"] == "active"
    assert item["last_seen_at"] is not None
    assert item["last_success_at"] is not None
    assert item["last_error"] is None
    assert item["failure_count"] == 0


def test_validation_clear_failure_marks_broken_and_never_deletes_row(
    tmp_path: Path, monkeypatch
) -> None:
    client, database_url = _client_with_catalog(tmp_path, monkeypatch)
    product_id = _catalog_product_ids(client)[0]
    created = _post_source_url(client, product_id, "https://www.skroutz.gr/s/missing")
    monkeypatch.setattr(
        routes_source_urls,
        "validate_source_url_reachability",
        lambda _url: SourceUrlValidationResult(
            status="failed", message="URL returned HTTP 404.", http_status_code=404
        ),
    )

    first = client.post(f"/api/catalog/source-urls/{created['id']}/validate")
    second = client.post(f"/api/catalog/source-urls/{created['id']}/validate")

    assert first.status_code == 200
    assert second.status_code == 200
    item = second.json()["item"]
    assert item["status"] == "broken"
    assert item["failure_count"] == 2
    assert item["last_failed_at"] is not None
    assert item["last_error"] == "URL returned HTTP 404."
    with session_scope(database_url) as session:
        assert session.query(SourceUrl).count() == 1


def test_source_url_api_returns_503_when_catalog_db_missing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, "")
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(tmp_path / "missing-price-ignore.csv"))

    response = TestClient(create_app()).get("/api/catalog/products/1/source-urls")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "catalog_database_required"


def test_db_diagnostics_include_source_urls(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, "")

    response = TestClient(create_app()).get("/api/price-monitoring/db/status")

    assert response.status_code == 200
    payload = response.json()
    assert "source_urls" in payload["required_tables"]
    if not payload["required_tables"]["source_urls"]:
        assert "source_urls" in payload["missing_tables"]
