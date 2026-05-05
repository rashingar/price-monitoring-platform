import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pricefetcher.api.app import create_app  # noqa: E402
from pricefetcher.catalog_db import ingest_source_catalog  # noqa: E402
from pricefetcher.catalog.source_catalog import SOURCE_CATA_ENV_VAR  # noqa: E402
from pricefetcher.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from pricefetcher.db.models import Base  # noqa: E402
from pricefetcher.db.session import get_engine, session_scope  # noqa: E402
from pricefetcher.ignore.product_ignore import PRICE_IGNORE_ENV_VAR  # noqa: E402

RAW_COOKWARE = (
    "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ:::"
    "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Σκεύη Μαγειρικής:::"
    "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Σκεύη Μαγειρικής///Γάστρες"
)
RAW_APPLIANCES = "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ:::ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ///Απορροφητήρες"
RAW_PLAIN = "Plain Value"


def _write_api_catalog(path: Path) -> None:
    path.write_text(
        "model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n"
        f"005606,MPN-1,Vacuum One,{RAW_COOKWARE},Bosch,123.45,3,1,1,0\n"
        f"123456,MPN-2,Vacuum Two,{RAW_APPLIANCES},Miele,0,0,1,1,1\n"
        f"233374-233203,,Bundle,{RAW_COOKWARE},Bosch,50.00,2,1,0,0\n"
        f"ABC123,MPN-4,Inactive,{RAW_PLAIN},Philips,12.00,7,0,0,1\n",
        encoding="utf-8-sig",
    )


def _client_with_catalog(tmp_path: Path, monkeypatch) -> TestClient:
    catalog_path = tmp_path / "sourceCata.csv"
    _write_api_catalog(catalog_path)
    database_url = f"sqlite+pysqlite:///{tmp_path / 'pricefetcher.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    monkeypatch.setenv(SOURCE_CATA_ENV_VAR, str(catalog_path))
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(tmp_path / "missing-price-ignore.csv"))
    Base.metadata.create_all(get_engine(database_url))
    with session_scope(database_url) as session:
        ingest_source_catalog(session, source_cata_path=catalog_path)
    return TestClient(create_app())


def _client_with_db_catalog_file(tmp_path: Path, monkeypatch, catalog_path: Path, ignore_path: Path | None = None) -> TestClient:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'pricefetcher.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    monkeypatch.setenv(SOURCE_CATA_ENV_VAR, str(catalog_path))
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(ignore_path or tmp_path / "missing-price-ignore.csv"))
    Base.metadata.create_all(get_engine(database_url))
    with session_scope(database_url) as session:
        ingest_source_catalog(session, source_cata_path=catalog_path)
    return TestClient(create_app())


def test_catalog_products_pagination(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)

    response = client.get("/api/catalog/products", params={"page": 2, "page_size": 2})

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 2
    assert payload["page_size"] == 2
    assert payload["total"] == 4
    assert payload["filtered_total"] == 4
    assert [item["model"] for item in payload["items"]] == ["233374-233203", "ABC123"]
    assert "ignored" in payload["items"][0]
    assert isinstance(payload["items"][0]["catalog_product_id"], int)


def test_catalog_products_category_filter(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)

    response = client.get("/api/catalog/products", params={"category": RAW_COOKWARE})

    assert response.status_code == 200
    payload = response.json()
    assert payload["filtered_total"] == 2
    assert {item["model"] for item in payload["items"]} == {"005606", "233374-233203"}


def test_catalog_product_response_includes_parsed_category_fields(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)

    response = client.get("/api/catalog/products", params={"category": RAW_COOKWARE, "page_size": 1})

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["category"] == RAW_COOKWARE
    assert item["raw_category"] == RAW_COOKWARE
    assert item["family"] == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"
    assert item["category_name"] == "Σκεύη Μαγειρικής"
    assert item["sub_category"] == "Γάστρες"
    assert item["category_levels"] == ["ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ", "Σκεύη Μαγειρικής", "Γάστρες"]


def test_catalog_products_hierarchy_filters(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)

    by_family = client.get("/api/catalog/products", params={"family": "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"}).json()
    by_category = client.get(
        "/api/catalog/products",
        params={"family": "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ", "category_name": "Σκεύη Μαγειρικής"},
    ).json()
    by_sub_category = client.get(
        "/api/catalog/products",
        params={
            "family": "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
            "category_name": "Σκεύη Μαγειρικής",
            "sub_category": "Γάστρες",
        },
    ).json()

    assert {item["model"] for item in by_family["items"]} == {"005606", "233374-233203"}
    assert {item["model"] for item in by_category["items"]} == {"005606", "233374-233203"}
    assert {item["model"] for item in by_sub_category["items"]} == {"005606", "233374-233203"}


def test_catalog_products_raw_and_hierarchy_filters_combine(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)

    matched = client.get(
        "/api/catalog/products",
        params={"category": RAW_COOKWARE, "family": "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"},
    ).json()
    mismatched = client.get(
        "/api/catalog/products",
        params={"category": RAW_COOKWARE, "family": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ"},
    ).json()
    empty_ignored = client.get(
        "/api/catalog/products",
        params={"family": "   ", "category_name": ""},
    ).json()

    assert matched["filtered_total"] == 2
    assert mismatched["filtered_total"] == 0
    assert empty_ignored["filtered_total"] == 4


def test_catalog_products_manufacturer_filter(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)

    response = client.get("/api/catalog/products", params={"manufacturer": "Miele"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["filtered_total"] == 1
    assert payload["items"][0]["model"] == "123456"


def test_catalog_products_marketplace_filter(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)

    bestprice = client.get("/api/catalog/products", params={"marketplace": "bestprice"}).json()
    skroutz = client.get("/api/catalog/products", params={"marketplace": "skroutz"}).json()
    both = client.get("/api/catalog/products", params={"marketplace": "both"}).json()
    none = client.get("/api/catalog/products", params={"marketplace": "none"}).json()

    assert {item["model"] for item in bestprice["items"]} == {"005606", "123456"}
    assert {item["model"] for item in skroutz["items"]} == {"123456", "ABC123"}
    assert [item["model"] for item in both["items"]] == ["123456"]
    assert [item["model"] for item in none["items"]] == ["233374-233203"]


def test_catalog_products_search_mpn_atomic_and_automation_filters(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)

    searched = client.get("/api/catalog/products", params={"q": "vacuum"}).json()
    has_mpn = client.get("/api/catalog/products", params={"has_mpn": "false"}).json()
    atomic = client.get("/api/catalog/products", params={"atomic_only": "true"}).json()
    eligible = client.get("/api/catalog/products", params={"automation_eligible_only": "true"}).json()

    assert {item["model"] for item in searched["items"]} == {"005606", "123456"}
    assert [item["model"] for item in has_mpn["items"]] == ["233374-233203"]
    assert {item["model"] for item in atomic["items"]} == {"005606", "123456"}
    assert [item["model"] for item in eligible["items"]] == ["005606"]


def test_catalog_categories(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)

    response = client.get("/api/catalog/categories")

    assert response.status_code == 200
    items = response.json()["items"]
    cookware = next(item for item in items if item["category"] == RAW_COOKWARE)
    assert cookware == {
        "category": RAW_COOKWARE,
        "raw_category": RAW_COOKWARE,
        "family": "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        "category_name": "Σκεύη Μαγειρικής",
        "sub_category": "Γάστρες",
        "category_levels": ["ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ", "Σκεύη Μαγειρικής", "Γάστρες"],
        "count": 2,
    }
    assert {item["category"]: item["count"] for item in items} == {
        RAW_COOKWARE: 2,
        RAW_APPLIANCES: 1,
        RAW_PLAIN: 1,
    }


def test_catalog_category_hierarchy(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)

    response = client.get("/api/catalog/category-hierarchy")

    assert response.status_code == 200
    items = response.json()["items"]
    cookware_family = next(item for item in items if item["family"] == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ")
    cookware_category = cookware_family["categories"][0]
    cookware_sub_category = cookware_category["sub_categories"][0]
    assert cookware_family["count"] == 2
    assert cookware_category["category_name"] == "Σκεύη Μαγειρικής"
    assert cookware_category["count"] == 2
    assert cookware_sub_category == {
        "sub_category": "Γάστρες",
        "count": 2,
        "raw_categories": [RAW_COOKWARE],
    }


def test_catalog_brands(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)

    response = client.get("/api/catalog/brands")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"manufacturer": "Bosch", "count": 2},
            {"manufacturer": "Miele", "count": 1},
            {"manufacturer": "Philips", "count": 1},
        ]
    }


def test_catalog_summary(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)

    response = client.get("/api/catalog/summary")

    assert response.status_code == 200
    assert response.json() == {
        "total_products": 4,
        "active_products": 3,
        "atomic_products": 2,
        "composite_or_invalid_models": 2,
        "bestprice_products": 2,
        "skroutz_products": 2,
        "missing_mpn": 1,
        "category_count": 3,
        "family_count": 3,
        "category_name_count": 2,
        "sub_category_count": 1,
        "manufacturer_count": 3,
    }


def test_catalog_missing_file_returns_404(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, "")

    response = TestClient(create_app()).get("/api/catalog/summary")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "catalog_database_required"


def test_catalog_missing_columns_returns_400(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'pricefetcher.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    Base.metadata.create_all(get_engine(database_url))

    response = TestClient(create_app()).get("/api/catalog/summary")

    assert response.status_code == 200
    assert response.json()["total_products"] == 0
    assert "Active catalog is empty" in response.json()["warning"]


def test_catalog_products_exclude_ignored_by_default(tmp_path: Path, monkeypatch) -> None:
    catalog_path = tmp_path / "sourceCata.csv"
    ignore_path = tmp_path / "price_ignore.csv"
    _write_api_catalog(catalog_path)
    ignore_path.write_text(
        "model,name,manufacturer,mpn,reason,ignored_at,notes\n"
        "005606,Vacuum One,Bosch,MPN-1,manual,2026-04-28T12:30:00+00:00,\n",
        encoding="utf-8-sig",
    )
    monkeypatch.setenv(SOURCE_CATA_ENV_VAR, str(catalog_path))
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(ignore_path))

    payload = _client_with_db_catalog_file(tmp_path, monkeypatch, catalog_path, ignore_path).get("/api/catalog/products").json()

    assert payload["filtered_total"] == 3
    assert "005606" not in {item["model"] for item in payload["items"]}


def test_catalog_products_ignored_include_and_only_filters(tmp_path: Path, monkeypatch) -> None:
    catalog_path = tmp_path / "sourceCata.csv"
    ignore_path = tmp_path / "price_ignore.csv"
    _write_api_catalog(catalog_path)
    ignore_path.write_text(
        "model,name,manufacturer,mpn,reason,ignored_at,notes\n"
        "005606,Vacuum One,Bosch,MPN-1,manual,2026-04-28T12:30:00+00:00,\n",
        encoding="utf-8-sig",
    )
    client = _client_with_db_catalog_file(tmp_path, monkeypatch, catalog_path, ignore_path)

    included = client.get("/api/catalog/products", params={"ignored": "include"}).json()
    only = client.get("/api/catalog/products", params={"ignored": "only"}).json()

    included_item = next(item for item in included["items"] if item["model"] == "005606")
    assert included["filtered_total"] == 4
    assert included_item["ignored"] is True
    assert included_item["automation_eligible"] is False
    assert only["filtered_total"] == 1
    assert only["items"][0]["model"] == "005606"


def test_catalog_automation_eligible_is_false_when_mpn_empty(tmp_path: Path, monkeypatch) -> None:
    catalog_path = tmp_path / "sourceCata.csv"
    catalog_path.write_text(
        "model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n"
        "005606,,Missing MPN,Cat A,Bosch,123.45,3,1,1,0\n",
        encoding="utf-8-sig",
    )

    payload = _client_with_db_catalog_file(tmp_path, monkeypatch, catalog_path).get("/api/catalog/products").json()

    assert payload["items"][0]["automation_eligible"] is False
