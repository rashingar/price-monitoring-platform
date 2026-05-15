import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.catalog_db import ingest_source_catalog  # noqa: E402
from ecommerce.catalog.source_catalog import SOURCE_CATA_ENV_VAR  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models import Base  # noqa: E402
from ecommerce.db.models.products import ProductSource, SourceCaptureSnapshot  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.db.repositories.source_urls import create_or_update_imported_source_url, create_or_update_manual_source_url  # noqa: E402
from ecommerce.ignore.product_ignore import PRICE_IGNORE_ENV_VAR  # noqa: E402

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
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    monkeypatch.setenv(SOURCE_CATA_ENV_VAR, str(catalog_path))
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(tmp_path / "missing-price-ignore.csv"))
    Base.metadata.create_all(get_engine(database_url))
    with session_scope(database_url) as session:
        ingest_source_catalog(session, source_cata_path=catalog_path)
    return TestClient(create_app())


def _client_with_db_catalog_file(tmp_path: Path, monkeypatch, catalog_path: Path, ignore_path: Path | None = None) -> TestClient:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
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
    assert "debug" not in payload
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


def test_catalog_products_sort_by_and_sort_dir(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)

    by_price_desc = client.get(
        "/api/catalog/products",
        params={"sort_by": "price", "sort_dir": "desc"},
    ).json()
    by_name_asc = client.get(
        "/api/catalog/products",
        params={"sort_by": "name", "sort_dir": "asc"},
    ).json()

    assert [item["model"] for item in by_price_desc["items"]] == ["005606", "233374-233203", "ABC123", "123456"]
    assert [item["model"] for item in by_name_asc["items"]] == ["233374-233203", "ABC123", "005606", "123456"]


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


def test_catalog_products_has_quantity_filter_requires_active_positive_quantity(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)

    payload = client.get("/api/catalog/products", params={"has_quantity": "true"}).json()

    assert payload["filtered_total"] == 2
    assert {item["model"] for item in payload["items"]} == {"005606", "233374-233203"}
    assert "ABC123" not in {item["model"] for item in payload["items"]}
    assert "123456" not in {item["model"] for item in payload["items"]}
    assert all(item["status"] == 1 and item["quantity"] > 0 for item in payload["items"])


def test_catalog_products_source_url_filter(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    with session_scope(database_url) as session:
        product_id = client.get(
            "/api/catalog/products",
            params={"q": "Vacuum Two"},
        ).json()["items"][0]["catalog_product_id"]
        create_or_update_manual_source_url(
            session,
            product_id,
            {"url": "https://www.skroutz.gr/s/123/vacuum-two.html"},
        )

    with_source_url = client.get("/api/catalog/products", params={"has_source_url": "true"}).json()
    without_source_url = client.get("/api/catalog/products", params={"has_source_url": "false"}).json()
    with_skroutz_source_url = client.get(
        "/api/catalog/products",
        params={"has_source_url": "true", "source_name": "SKROUTZ"},
    ).json()
    without_bestprice_source_url = client.get(
        "/api/catalog/products",
        params={"has_source_url": "false", "source_name": "bestprice"},
    ).json()

    assert [item["model"] for item in with_source_url["items"]] == ["123456"]
    assert {item["model"] for item in without_source_url["items"]} == {"005606", "233374-233203", "ABC123"}
    assert [item["model"] for item in with_skroutz_source_url["items"]] == ["123456"]
    assert {item["model"] for item in without_bestprice_source_url["items"]} == {
        "005606",
        "123456",
        "233374-233203",
        "ABC123",
    }


def test_catalog_products_include_source_url_eligibility_coverage(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    with session_scope(database_url) as session:
        vacuum_one_id = client.get(
            "/api/catalog/products",
            params={"q": "Vacuum One"},
        ).json()["items"][0]["catalog_product_id"]
        vacuum_two_id = client.get(
            "/api/catalog/products",
            params={"q": "Vacuum Two"},
        ).json()["items"][0]["catalog_product_id"]
        create_or_update_imported_source_url(
            session,
            catalog_product_id=vacuum_one_id,
            url="https://www.bestprice.gr/item/456/vacuum-one.html",
            source_name="bestprice",
            status="needs_review",
        )
        create_or_update_imported_source_url(
            session,
            catalog_product_id=vacuum_one_id,
            url="https://www.bestprice.gr/item/456/vacuum-one-disabled.html",
            source_name="bestprice",
            status="disabled",
        )
        create_or_update_imported_source_url(
            session,
            catalog_product_id=vacuum_one_id,
            url="https://www.bestprice.gr/item/456/vacuum-one-broken.html",
            source_name="bestprice",
            status="broken",
        )
        create_or_update_imported_source_url(
            session,
            catalog_product_id=vacuum_one_id,
            url="https://www.bestprice.gr/item/456/vacuum-one-redirected.html",
            source_name="bestprice",
            status="redirected",
        )
        create_or_update_manual_source_url(
            session,
            vacuum_two_id,
            {"url": "https://www.bestprice.gr/item/123/vacuum-two.html", "source_name": "bestprice"},
        )

    payload = client.get(
        "/api/catalog/products",
        params={"marketplace": "bestprice", "source_name": "bestprice", "atomic_only": "true"},
    ).json()

    by_model = {item["model"]: item for item in payload["items"]}
    assert by_model["005606"]["source_url_coverage"]["has_active_source_url"] is False
    assert by_model["005606"]["source_url_coverage"]["needs_review_source_url_count"] == 1
    assert by_model["005606"]["source_url_coverage"]["disabled_source_url_count"] == 1
    assert by_model["005606"]["source_url_coverage"]["broken_source_url_count"] == 1
    assert by_model["005606"]["source_url_coverage"]["redirected_source_url_count"] == 1
    assert by_model["005606"]["source_url_coverage"]["status_counts"] == {
        "active": 0,
        "needs_review": 1,
        "broken": 1,
        "disabled": 1,
        "redirected": 1,
    }
    assert by_model["123456"]["source_url_coverage"]["has_active_source_url"] is True
    assert by_model["123456"]["source_url_coverage"]["active_source_url_count"] == 1

    with_active_source_url = client.get(
        "/api/catalog/products",
        params={"has_source_url": "true", "source_name": "BestPrice"},
    ).json()
    assert [item["model"] for item in with_active_source_url["items"]] == ["123456"]


def test_catalog_product_detail_returns_product_and_empty_source_urls(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)
    product_id = client.get(
        "/api/catalog/products",
        params={"q": "Vacuum One"},
    ).json()["items"][0]["catalog_product_id"]

    response = client.get(f"/api/catalog/products/{product_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["product"]["catalog_product_id"] == product_id
    assert payload["product"]["model"] == "005606"
    assert payload["product"]["mpn"] == "MPN-1"
    assert payload["product"]["manufacturer"] == "Bosch"
    assert payload["product"]["category_levels"] == [
        "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        "Σκεύη Μαγειρικής",
        "Γάστρες",
    ]
    assert payload["source_urls"] == []
    assert payload["source_url_summary"] == {
        "total_count": 0,
        "by_status": {},
        "by_source": {},
        "by_type": {},
    }


def test_catalog_product_detail_missing_product_returns_404(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)

    response = client.get("/api/catalog/products/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Catalog product not found."


def test_catalog_product_detail_returns_source_url_lifecycle_rows(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    product_id = client.get(
        "/api/catalog/products",
        params={"q": "Vacuum One"},
    ).json()["items"][0]["catalog_product_id"]
    statuses = ["active", "needs_review", "broken", "disabled", "redirected"]

    with session_scope(database_url) as session:
        create_or_update_manual_source_url(
            session,
            product_id,
            {"url": "https://www.skroutz.gr/s/123/vacuum-one.html", "source_name": "skroutz"},
        )
        for status in statuses[1:]:
            create_or_update_imported_source_url(
                session,
                catalog_product_id=product_id,
                url=f"https://www.bestprice.gr/item/456/vacuum-one-{status}.html",
                source_name="bestprice",
                status=status,
                last_error="provider returned token=live-secret and password=hidden" if status == "broken" else None,
            )

    payload = client.get(f"/api/catalog/products/{product_id}").json()

    rows_by_status = {item["status"]: item for item in payload["source_urls"]}
    assert set(rows_by_status) == set(statuses)
    assert payload["source_url_summary"]["total_count"] == 5
    assert payload["source_url_summary"]["by_status"] == {status: 1 for status in statuses}
    assert payload["source_url_summary"]["by_source"] == {"bestprice": 4, "skroutz": 1}
    assert rows_by_status["active"]["source_url_id"] == rows_by_status["active"]["id"]
    assert rows_by_status["active"]["url_type"] == "manual"
    assert rows_by_status["needs_review"]["trust_level"] == "imported"
    assert "live-secret" not in rows_by_status["broken"]["last_error"]
    assert "hidden" not in rows_by_status["broken"]["last_error"]
    assert "<redacted>" in rows_by_status["broken"]["last_error"]


def test_catalog_product_detail_includes_capture_fetch_fields_when_stored(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    product_id = client.get(
        "/api/catalog/products",
        params={"q": "Vacuum Two"},
    ).json()["items"][0]["catalog_product_id"]
    captured_at = datetime(2026, 5, 2, 8, 5, tzinfo=timezone.utc)
    fetched_at = datetime(2026, 5, 2, 8, 4, tzinfo=timezone.utc)

    with session_scope(database_url) as session:
        create_or_update_manual_source_url(
            session,
            product_id,
            {"url": "https://www.skroutz.gr/s/123/vacuum-two.html", "source_name": "skroutz"},
        )
        product_source = session.query(ProductSource).one()
        product_source.last_fetch_status = "success"
        product_source.last_capture_strategy = "scheduled-test"
        product_source.last_success_at = captured_at
        snapshot = SourceCaptureSnapshot(
            product_id=product_source.product_id,
            product_source_id=product_source.id,
            vendor_id=product_source.vendor_id,
            capture_strategy="scheduled-test",
            page_url=product_source.canonical_url,
            artifact_ref="source-captures/9001/full-snapshot.json",
            captured_at=captured_at,
            fetched_at=fetched_at,
            created_at=captured_at,
        )
        session.add(snapshot)

    payload = client.get(f"/api/catalog/products/{product_id}").json()
    row = payload["source_urls"][0]
    assert row["product_source_id"] == product_source.id
    assert row["capture_status"] == "success"
    assert row["last_fetch_status"] == "success"
    assert row["last_capture_status"] == "success"
    assert row["last_capture_strategy"] == "scheduled-test"
    assert row["last_capture_at"] == "2026-05-02T08:05:00+00:00"
    assert row["last_fetched_at"] == "2026-05-02T08:04:00+00:00"
    assert row["source_capture_snapshot_id"] is not None
    assert row["last_capture_snapshot_id"] == row["source_capture_snapshot_id"]
    assert row["artifact_ref"]["path"] == "source-captures/9001/full-snapshot.json"
    assert row["full_snapshot_ref"]["path"] == "source-captures/9001/full-snapshot.json"


def test_catalog_product_detail_excludes_price_monitoring_history(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)
    product_id = client.get(
        "/api/catalog/products",
        params={"q": "Vacuum One"},
    ).json()["items"][0]["catalog_product_id"]

    payload = client.get(f"/api/catalog/products/{product_id}").json()

    serialized = str(payload)
    assert "price_observations" not in payload
    assert "price_listings" not in payload
    assert "monitoring_runs" not in payload
    assert "monitoring_history" not in payload
    assert "PriceObservation" not in serialized


def test_catalog_products_debug_metadata_is_opt_in(tmp_path: Path, monkeypatch) -> None:
    client = _client_with_catalog(tmp_path, monkeypatch)

    default_payload = client.get("/api/catalog/products").json()
    debug_payload = client.get(
        "/api/catalog/products",
        params={"debug": "true", "q": "vacuum", "sort_by": "name", "sort_dir": "desc", "page": 1, "page_size": 1},
    ).json()

    assert "debug" not in default_payload
    assert debug_payload["debug"]["query_mode"] == "database"
    assert isinstance(debug_payload["debug"]["elapsed_ms"], (int, float))
    assert debug_payload["debug"]["filters_applied"] == ["q", "ignored"]
    assert debug_payload["debug"]["sort_by"] == "name"
    assert debug_payload["debug"]["sort_dir"] == "desc"
    assert debug_payload["debug"]["page"] == 1
    assert debug_payload["debug"]["page_size"] == 1


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
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
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
