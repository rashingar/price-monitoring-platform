import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api import routes_price_monitoring  # noqa: E402
from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.catalog_db import ingest_source_catalog  # noqa: E402
from ecommerce.catalog.source_catalog import SOURCE_CATA_ENV_VAR  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models.base import Base  # noqa: E402
from ecommerce.db.models.catalog import CatalogProductRow  # noqa: E402
from ecommerce.db.models.source_urls import SourceUrl  # noqa: E402
from ecommerce.db.models.price_monitoring import MonitoringRun  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.ignore.product_ignore import PRICE_IGNORE_ENV_VAR  # noqa: E402

RAW_COOKWARE = (
    "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ:::"
    "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Σκεύη Μαγειρικής:::"
    "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Σκεύη Μαγειρικής///Γάστρες"
)
RAW_PANS = (
    "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ:::"
    "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Σκεύη Μαγειρικής:::"
    "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Σκεύη Μαγειρικής///Τηγάνια"
)
RAW_APPLIANCES = "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ:::ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ///Απορροφητήρες"
NOW = datetime(2026, 4, 29, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _allow_monitoring_api_without_real_db(monkeypatch):
    monkeypatch.setattr(
        routes_price_monitoring,
        "require_database_ready_for_price_monitoring",
        lambda: None,
    )


def _write_catalog(path: Path) -> None:
    path.write_text(
        "model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n"
        f"005606,MPN-1,Eligible Bosch,{RAW_COOKWARE},Bosch,123.45,3,1,1,1\n"
        f"123456,MPN-2,BestPrice Only,{RAW_APPLIANCES},Miele,50.00,1,1,1,0\n"
        f"222222,MPN-3,Skroutz Only,{RAW_PANS},Bosch,75.00,1,1,0,1\n"
        "333333,MPN-4,Ignored Product,Cat A,Bosch,80.00,1,1,1,1\n"
        "233374-233203,MPN-5,Bundle Product,Cat A,Bosch,90.00,1,1,1,1\n"
        "444444,,Missing MPN,Cat A,Bosch,100.00,1,1,1,1\n"
        "555555,MPN-6,Inactive Product,Cat A,Bosch,110.00,1,0,1,1\n"
        "666666,MPN-7,Zero Price,Cat A,Bosch,0,1,1,1,1\n"
        "777777,MPN-8,Excluded Product,Cat A,Bosch,60.00,1,1,1,1\n",
        encoding="utf-8-sig",
    )


def _write_ignore(path: Path) -> None:
    path.write_text(
        "model,name,manufacturer,mpn,reason,ignored_at,notes\n"
        "333333,Ignored Product,Bosch,MPN-4,manual,2026-04-28T12:30:00+00:00,\n",
        encoding="utf-8-sig",
    )


def _client(
    tmp_path: Path, monkeypatch, *, ignored: bool = True, seed_source_urls: bool = True
) -> TestClient:
    catalog_path = tmp_path / "sourceCata.csv"
    ignore_path = tmp_path / "price_ignore.csv"
    _write_catalog(catalog_path)
    if ignored:
        _write_ignore(ignore_path)
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    monkeypatch.setenv(SOURCE_CATA_ENV_VAR, str(catalog_path))
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(ignore_path))
    monkeypatch.chdir(tmp_path)
    Base.metadata.create_all(get_engine(database_url))
    with session_scope(database_url) as session:
        ingest_source_catalog(session, source_cata_path=catalog_path)
    if seed_source_urls:
        _seed_default_active_source_urls(database_url)
    return TestClient(create_app())


def _setup_empty_db(tmp_path: Path, monkeypatch) -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    Base.metadata.create_all(get_engine(database_url))
    return database_url


def _database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"


def _catalog_products_by_model(database_url: str) -> dict[str, CatalogProductRow]:
    with session_scope(database_url) as session:
        return {row.model: row for row in session.query(CatalogProductRow).all()}


def _add_source_url(
    database_url: str,
    product: CatalogProductRow,
    *,
    source_name: str,
    status: str,
    url: str,
) -> None:
    source_domain = {
        "bestprice": "www.bestprice.gr",
        "skroutz": "www.skroutz.gr",
        "electronet": "www.electronet.gr",
    }.get(source_name, f"www.{source_name}.gr")
    with session_scope(database_url) as session:
        session.add(
            SourceUrl(
                catalog_product_id=product.id,
                catalog_source=product.catalog_source,
                model=product.model,
                mpn=product.mpn,
                manufacturer=product.manufacturer,
                source_name=source_name,
                source_domain=source_domain,
                url=url,
                url_normalized=url,
                status=status,
                url_type="manual",
                trust_level="manual",
                created_at=NOW,
                updated_at=NOW,
            )
        )


def _seed_default_active_source_urls(database_url: str) -> None:
    products = _catalog_products_by_model(database_url)
    for model, source_name in [
        ("005606", "skroutz"),
        ("005606", "bestprice"),
        ("123456", "bestprice"),
        ("222222", "skroutz"),
        ("333333", "skroutz"),
        ("333333", "bestprice"),
    ]:
        _add_source_url(
            database_url,
            products[model],
            source_name=source_name,
            status="active",
            url=f"https://www.{source_name}.gr/item/{model}",
        )


def _insert_db_run(
    database_url: str,
    run_dir: Path,
    *,
    source: str = "bestprice",
    status: str = "selection_created",
    created_at: str = "2026-04-29T12:00:00+00:00",
    selected_count: int = 0,
    skipped_count: int = 0,
    fetch_result_path: str | None = None,
    enriched_csv_path: str | None = None,
    fetch_summary_path: str | None = None,
) -> None:
    from datetime import datetime

    parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    with session_scope(database_url) as session:
        session.add(
            MonitoringRun(
                run_id=run_dir.name,
                source=source,
                status=status,
                trigger_type="manual",
                output_dir=str(run_dir),
                input_csv_path=str(run_dir / "input.csv"),
                selection_summary_path=str(run_dir / "selection_summary.json"),
                fetch_result_path=fetch_result_path,
                enriched_csv_path=enriched_csv_path,
                fetch_summary_path=fetch_summary_path,
                selected_count=selected_count,
                skipped_count=skipped_count,
                created_at=parsed_created_at,
                updated_at=parsed_created_at,
                started_at=parsed_created_at if fetch_result_path else None,
                completed_at=parsed_created_at if fetch_result_path else None,
            )
        )


def _write_run_metadata(
    run_dir: Path,
    *,
    source: str = "bestprice",
    created_at: str = "2026-04-29T12:00:00+00:00",
    selected_models: list[str] | None = None,
) -> None:
    selected_models = selected_models or []
    run_dir.mkdir(parents=True, exist_ok=True)
    input_csv_path = run_dir / "input.csv"
    selection_summary_path = run_dir / "selection_summary.json"
    input_csv_path.write_text("model,mpn,name,price\n", encoding="utf-8")
    selection_summary_path.write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "status": "selection_created",
                "source": source,
                "created_at": created_at,
                "input_csv_path": str(input_csv_path),
                "selected_count": len(selected_models),
                "skipped_count": 0,
                "skipped_by_reason": {},
                "selected_models": selected_models,
                "skipped_models": [],
            }
        ),
        encoding="utf-8",
    )


def test_preview_by_explicit_selected_models(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/price-monitoring/selection/preview",
        json={"source": "skroutz", "selected_models": ["005606", "333333"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_count"] == 1
    assert payload["items"][0]["model"] == "005606"
    assert payload["selected_items"] == payload["items"]
    assert payload["skipped"] == [{"model": "333333", "reasons": ["ignored"]}]
    assert payload["skipped_items"] == payload["skipped"]
    assert payload["skipped_by_reason"] == {"ignored": 1}


def test_preview_route_delegates_and_preserves_response_shape(monkeypatch) -> None:
    def fake_preview(selection_request, *, session_scope_fn):
        assert selection_request.source == "skroutz"
        return {
            "source": "skroutz",
            "source_filter": "skroutz",
            "selected_count": 1,
            "skipped_count": 0,
            "items": [{"model": "005606"}],
            "selected_items": [{"model": "005606"}],
            "skipped": [],
            "skipped_items": [],
            "skipped_by_reason": {},
            "source_url_required": True,
        }

    monkeypatch.setattr(
        routes_price_monitoring.monitoring_service,
        "preview_selection_response",
        fake_preview,
    )

    response = TestClient(create_app()).post(
        "/api/price-monitoring/selection/preview",
        json={"source": "skroutz", "selected_models": ["005606"]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "source": "skroutz",
        "source_filter": "skroutz",
        "selected_count": 1,
        "skipped_count": 0,
        "items": [{"model": "005606"}],
        "selected_items": [{"model": "005606"}],
        "skipped": [],
        "skipped_items": [],
        "skipped_by_reason": {},
        "source_url_required": True,
    }


def test_preview_selected_items_include_hierarchy_fields(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/price-monitoring/selection/preview",
        json={"source": "skroutz", "selected_models": ["005606"]},
    )

    assert response.status_code == 200
    item = response.json()["selected_items"][0]
    assert item["raw_category"] == RAW_COOKWARE
    assert item["category_levels"]
    assert item["family"] == item["category_levels"][0]
    assert item["category_name"] == item["category_levels"][1]
    assert item["sub_category"] == item["category_levels"][2]


def test_preview_includes_source_specific_source_url_coverage(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch, seed_source_urls=False)
    database_url = _database_url(tmp_path)
    products = _catalog_products_by_model(database_url)
    _add_source_url(
        database_url,
        products["005606"],
        source_name="skroutz",
        status="active",
        url="https://www.skroutz.gr/s/005606-active",
    )
    _add_source_url(
        database_url,
        products["005606"],
        source_name="skroutz",
        status="needs_review",
        url="https://www.skroutz.gr/s/005606-review",
    )
    _add_source_url(
        database_url,
        products["005606"],
        source_name="bestprice",
        status="active",
        url="https://www.bestprice.gr/item/005606",
    )
    _add_source_url(
        database_url,
        products["222222"],
        source_name="skroutz",
        status="broken",
        url="https://www.skroutz.gr/s/222222-broken",
    )
    _add_source_url(
        database_url,
        products["222222"],
        source_name="skroutz",
        status="disabled",
        url="https://www.skroutz.gr/s/222222-disabled",
    )
    _add_source_url(
        database_url,
        products["222222"],
        source_name="skroutz",
        status="redirected",
        url="https://www.skroutz.gr/s/222222-redirected",
    )

    response = client.post(
        "/api/price-monitoring/selection/preview",
        json={"source": "skroutz", "selected_models": ["005606", "222222", "777777"]},
    )

    assert response.status_code == 200
    payload = response.json()
    coverage = payload["source_url_coverage"]
    assert coverage["source"] == "skroutz"
    assert coverage["selected_count"] == 3
    assert coverage["products_with_active_source_urls"] == 1
    assert coverage["products_without_active_source_urls"] == 2
    assert coverage["coverage_percent"] == 33.33
    assert coverage["active_source_url_count"] == 1
    assert coverage["needs_review_source_url_count"] == 1
    assert coverage["broken_source_url_count"] == 1
    assert coverage["disabled_source_url_count"] == 1
    assert coverage["redirected_source_url_count"] == 1
    assert coverage["missing_source_url_models"] == ["222222", "777777"]
    assert coverage["missing_source_url_catalog_product_ids"] == [
        products["222222"].id,
        products["777777"].id,
    ]
    assert "not eligible for Price Monitoring" in coverage["warning"]
    assert "Vendor Sources" in coverage["warning"]
    assert payload["source_url_required"] is True
    assert payload["selected_count"] == 1
    assert payload["skipped_by_reason"]["missing_active_source_url"] == 2

    items = {item["model"]: item for item in payload["items"]}
    assert items["005606"]["catalog_product_id"] == products["005606"].id
    first_coverage = items["005606"]["source_url_coverage"]
    assert first_coverage["has_active_source_url"] is True
    assert first_coverage["active_source_url_count"] == 1
    assert first_coverage["status_counts"]["active"] == 1
    assert first_coverage["status_counts"]["needs_review"] == 1
    assert len(first_coverage["active_source_urls"]) == 1
    assert first_coverage["active_source_urls"][0]["source_name"] == "skroutz"

    assert [item["model"] for item in payload["skipped_items"]] == ["222222", "777777"]
    assert payload["skipped_items"][0]["reasons"] == ["missing_active_source_url"]


def test_preview_source_url_coverage_is_source_specific_for_bestprice(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch, seed_source_urls=False)
    database_url = _database_url(tmp_path)
    products = _catalog_products_by_model(database_url)
    _add_source_url(
        database_url,
        products["005606"],
        source_name="bestprice",
        status="active",
        url="https://www.bestprice.gr/item/005606",
    )
    _add_source_url(
        database_url,
        products["123456"],
        source_name="skroutz",
        status="active",
        url="https://www.skroutz.gr/s/123456",
    )

    response = client.post(
        "/api/price-monitoring/selection/preview",
        json={"source": "bestprice", "selected_models": ["005606", "123456"]},
    )

    assert response.status_code == 200
    payload = response.json()
    coverage = payload["source_url_coverage"]
    assert coverage["source"] == "bestprice"
    assert coverage["products_with_active_source_urls"] == 1
    assert coverage["products_without_active_source_urls"] == 1
    assert coverage["coverage_percent"] == 50.0
    assert coverage["missing_source_url_models"] == ["123456"]
    assert payload["selected_count"] == 1
    assert payload["skipped_by_reason"]["missing_active_source_url"] == 1
    items = {item["model"]: item for item in payload["items"]}
    assert items["005606"]["source_url_coverage"]["has_active_source_url"] is True
    assert "123456" not in items


def test_preview_requires_source_vendor(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/price-monitoring/selection/preview",
        json={"selected_models": ["005606"]},
    )

    assert response.status_code == 400
    assert "requires exactly one source/vendor" in response.json()["detail"]


def test_preview_rejects_all_source(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/price-monitoring/selection/preview",
        json={"source": "all", "selected_models": ["005606"]},
    )

    assert response.status_code == 400
    assert "requires exactly one source/vendor" in response.json()["detail"]


def test_preview_accepts_electronet_when_active_source_url_exists(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch, seed_source_urls=False)
    database_url = _database_url(tmp_path)
    products = _catalog_products_by_model(database_url)
    _add_source_url(
        database_url,
        products["123456"],
        source_name="electronet",
        status="active",
        url="https://www.electronet.gr/p/123456",
    )

    response = client.post(
        "/api/price-monitoring/selection/preview",
        json={"source": "electronet", "selected_models": ["123456"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "electronet"
    assert payload["source_filter"] == "electronet"
    assert payload["selected_count"] == 1
    assert payload["items"][0]["model"] == "123456"
    assert (
        payload["items"][0]["source_url_coverage"]["active_source_urls"][0][
            "source_name"
        ]
        == "electronet"
    )


def test_preview_default_all_excludes_ineligible_source_url_statuses(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch, seed_source_urls=False)
    database_url = _database_url(tmp_path)
    products = _catalog_products_by_model(database_url)
    for status in ["broken", "disabled", "needs_review", "redirected"]:
        _add_source_url(
            database_url,
            products["005606"],
            source_name="electronet",
            status=status,
            url=f"https://www.electronet.gr/p/{status}",
        )

    response = client.post(
        "/api/price-monitoring/selection/preview",
        json={"source": "electronet", "selected_models": ["005606"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_count"] == 0
    assert payload["skipped_by_reason"] == {"missing_active_source_url": 1}
    assert payload["source_url_coverage"]["active_source_url_count"] == 0
    assert payload["source_url_coverage"]["broken_source_url_count"] == 1
    assert payload["source_url_coverage"]["disabled_source_url_count"] == 1
    assert payload["source_url_coverage"]["needs_review_source_url_count"] == 1
    assert payload["source_url_coverage"]["redirected_source_url_count"] == 1


def test_run_list_returns_items_newest_first(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    database_url = _setup_empty_db(tmp_path, monkeypatch)
    runs_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs"
    old_run = runs_dir / "20260429-110000-oldrun"
    new_run = runs_dir / "20260429-120000-newrun"
    _write_run_metadata(
        old_run, created_at="2026-04-29T11:00:00+00:00", selected_models=["111111"]
    )
    _write_run_metadata(
        new_run, created_at="2026-04-29T12:00:00+00:00", selected_models=["222222"]
    )
    _insert_db_run(
        database_url, old_run, created_at="2026-04-29T11:00:00+00:00", selected_count=1
    )
    _insert_db_run(
        database_url, new_run, created_at="2026-04-29T12:00:00+00:00", selected_count=1
    )

    response = TestClient(create_app()).get("/api/price-monitoring/runs")

    assert response.status_code == 200
    payload = response.json()
    assert [item["run_id"] for item in payload["items"]] == [new_run.name, old_run.name]
    assert payload["items"][0]["selected_count"] == 1
    assert payload["items"][0]["latest_fetch"] is None


def test_old_file_only_run_is_ignored_by_db_backed_listing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _setup_empty_db(tmp_path, monkeypatch)
    _write_run_metadata(
        tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "legacy-file-only"
    )

    response = TestClient(create_app()).get("/api/price-monitoring/runs")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_run_detail_returns_one_run_with_latest_fetch(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    database_url = _setup_empty_db(tmp_path, monkeypatch)
    run_dir = (
        tmp_path
        / "output"
        / "ecommerce"
        / "monitoring"
        / "runs"
        / "20260429-120000-abcd1234"
    )
    _write_run_metadata(run_dir, selected_models=["005606"])
    fetch_result_path = run_dir / "fetch_result.json"
    _insert_db_run(
        database_url,
        run_dir,
        status="fetch_completed",
        selected_count=1,
        fetch_result_path=str(fetch_result_path),
        enriched_csv_path=str(run_dir / "input_bestprice_enriched.csv"),
        fetch_summary_path=str(run_dir / "input_summary.json"),
    )
    fetch_result_path.write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "status": "fetch_completed",
                "source": "bestprice",
                "started_at": "2026-04-29T12:01:00+00:00",
                "completed_at": "2026-04-29T12:02:00+00:00",
                "enriched_csv_path": str(run_dir / "input_bestprice_enriched.csv"),
                "fetch_summary_path": str(run_dir / "input_summary.json"),
                "fetch_result_path": str(fetch_result_path),
            }
        ),
        encoding="utf-8",
    )

    response = TestClient(create_app()).get(
        f"/api/price-monitoring/runs/{run_dir.name}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == run_dir.name
    assert payload["status"] == "fetch_completed"
    assert payload["source"] == "bestprice"
    assert payload["selected_count"] == 1
    assert payload["latest_fetch"]["status"] == "succeeded"
    assert payload["latest_fetch"]["fetch_result_path"] == str(fetch_result_path)


def test_run_detail_uses_db_when_artifact_directory_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    database_url = _setup_empty_db(tmp_path, monkeypatch)
    run_dir = (
        tmp_path
        / "output"
        / "ecommerce"
        / "monitoring"
        / "runs"
        / "20260429-130000-dbonly"
    )
    _insert_db_run(
        database_url,
        run_dir,
        source="skroutz",
        status="fetch_failed",
        selected_count=7,
        skipped_count=2,
    )

    response = TestClient(create_app()).get(
        f"/api/price-monitoring/runs/{run_dir.name}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == run_dir.name
    assert payload["status"] == "fetch_failed"
    assert payload["source"] == "skroutz"
    assert payload["selected_count"] == 7
    assert payload["skipped_count"] == 2
    assert payload["artifacts"] == []
    assert any(
        "Run artifact directory is missing" in warning
        for warning in payload["artifact_warnings"]
    )


def test_run_detail_attaches_existing_artifacts_as_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    database_url = _setup_empty_db(tmp_path, monkeypatch)
    run_dir = (
        tmp_path
        / "output"
        / "ecommerce"
        / "monitoring"
        / "runs"
        / "20260429-140000-artifacts"
    )
    _write_run_metadata(run_dir, selected_models=["005606"])
    extra_path = run_dir / "operator-note.txt"
    extra_path.write_text("kept for inspection\n", encoding="utf-8")
    _insert_db_run(database_url, run_dir, selected_count=1)

    response = TestClient(create_app()).get(
        f"/api/price-monitoring/runs/{run_dir.name}"
    )

    assert response.status_code == 200
    payload = response.json()
    artifact_names = {item["name"] for item in payload["artifacts"]}
    assert {"input.csv", "selection_summary.json", "operator-note.txt"}.issubset(
        artifact_names
    )
    assert all(item["is_allowed"] is True for item in payload["artifacts"])
    assert payload["artifact_warnings"] == []


def test_run_detail_db_fields_win_over_stale_artifact_content(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    database_url = _setup_empty_db(tmp_path, monkeypatch)
    run_dir = (
        tmp_path
        / "output"
        / "ecommerce"
        / "monitoring"
        / "runs"
        / "20260429-150000-stale"
    )
    _write_run_metadata(
        run_dir,
        source="stale-source",
        created_at="2020-01-01T00:00:00+00:00",
        selected_models=["111111", "222222"],
    )
    _insert_db_run(
        database_url,
        run_dir,
        source="db-source",
        status="fetch_completed",
        created_at="2026-04-29T15:00:00+00:00",
        selected_count=9,
        skipped_count=3,
    )

    response = TestClient(create_app()).get(
        f"/api/price-monitoring/runs/{run_dir.name}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "db-source"
    assert payload["status"] == "fetch_completed"
    assert payload["created_at"] == "2026-04-29T15:00:00+00:00"
    assert payload["selected_count"] == 9
    assert payload["skipped_count"] == 3
    assert payload["selected_models"] == []


def test_run_detail_missing_run_returns_404(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _setup_empty_db(tmp_path, monkeypatch)

    response = TestClient(create_app()).get("/api/price-monitoring/runs/missing")

    assert response.status_code == 404
    assert "DB-backed price monitoring run not found" in response.json()["detail"]


def test_run_detail_malformed_run_id_returns_400(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    response = TestClient(create_app()).get("/api/price-monitoring/runs/%2E%2E")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid run_id."


def test_preview_by_category_filter(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/price-monitoring/selection/preview",
        json={"source": "skroutz", "filters": {"category": RAW_APPLIANCES}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_count"] == 0
    assert payload["skipped"] == [
        {"model": "123456", "reasons": ["missing_active_source_url"]}
    ]


def test_preview_by_hierarchy_family_filter(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/price-monitoring/selection/preview",
        json={"source": "skroutz", "filters": {"family": "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["model"] for item in payload["items"]] == ["005606", "222222"]


def test_preview_by_hierarchy_family_and_category_name(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/price-monitoring/selection/preview",
        json={
            "source": "skroutz",
            "filters": {
                "family": "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
                "category_name": "Σκεύη Μαγειρικής",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["model"] for item in payload["items"]] == ["005606", "222222"]


def test_preview_by_full_hierarchy_filter(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/price-monitoring/selection/preview",
        json={
            "source": "skroutz",
            "filters": {
                "family": "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
                "category_name": "Σκεύη Μαγειρικής",
                "sub_category": "Γάστρες",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["model"] for item in payload["items"]] == ["005606"]


def test_preview_by_manufacturer_filter(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/price-monitoring/selection/preview",
        json={"source": "bestprice", "filters": {"manufacturer": "Miele"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_count"] == 1
    assert payload["items"][0]["model"] == "123456"


def test_source_filter_for_skroutz_and_bestprice(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    skroutz = client.post(
        "/api/price-monitoring/selection/preview",
        json={"source": "skroutz", "selected_models": ["123456", "222222"]},
    ).json()
    bestprice = client.post(
        "/api/price-monitoring/selection/preview",
        json={"source": "bestprice", "selected_models": ["123456", "222222"]},
    ).json()

    assert [item["model"] for item in skroutz["items"]] == ["222222"]
    assert skroutz["skipped"] == [
        {"model": "123456", "reasons": ["missing_active_source_url"]}
    ]
    assert [item["model"] for item in bestprice["items"]] == ["123456"]
    assert bestprice["skipped"] == [
        {"model": "222222", "reasons": ["missing_active_source_url"]}
    ]


def test_electronet_active_url_does_not_make_product_eligible_for_skroutz(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch, seed_source_urls=False)
    database_url = _database_url(tmp_path)
    products = _catalog_products_by_model(database_url)
    _add_source_url(
        database_url,
        products["123456"],
        source_name="electronet",
        status="active",
        url="https://www.electronet.gr/p/123456",
    )

    electronet = client.post(
        "/api/price-monitoring/selection/preview",
        json={"source": "electronet", "selected_models": ["123456"]},
    ).json()
    skroutz = client.post(
        "/api/price-monitoring/selection/preview",
        json={"source": "skroutz", "selected_models": ["123456"]},
    ).json()

    assert [item["model"] for item in electronet["items"]] == ["123456"]
    assert skroutz["selected_count"] == 0
    assert skroutz["skipped"] == [
        {"model": "123456", "reasons": ["missing_active_source_url"]}
    ]


def test_include_ignored_true_allows_otherwise_eligible_product(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/price-monitoring/selection/preview",
        json={
            "source": "skroutz",
            "selected_models": ["333333"],
            "include_ignored": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_count"] == 1
    assert payload["items"][0]["model"] == "333333"


def test_composite_missing_mpn_inactive_and_price_exclusions(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch, ignored=False)

    response = client.post(
        "/api/price-monitoring/selection/preview",
        json={
            "source": "skroutz",
            "selected_models": ["233374-233203", "444444", "555555", "666666"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_count"] == 0
    assert payload["skipped"] == [
        {"model": "233374-233203", "reasons": ["non_atomic_model"]},
        {"model": "444444", "reasons": ["missing_mpn"]},
        {"model": "555555", "reasons": ["inactive"]},
        {"model": "666666", "reasons": ["missing_or_invalid_price"]},
    ]


def test_excluded_models_removes_product(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/price-monitoring/selection/preview",
        json={
            "source": "skroutz",
            "selected_models": ["005606", "777777"],
            "excluded_models": ["777777"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["model"] for item in payload["items"]] == ["005606"]
    assert payload["skipped"] == [
        {"model": "777777", "reasons": ["explicitly_excluded"]}
    ]


def test_run_creation_writes_input_csv_and_selection_summary(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch, seed_source_urls=False)
    database_url = _database_url(tmp_path)
    products = _catalog_products_by_model(database_url)
    _add_source_url(
        database_url,
        products["005606"],
        source_name="skroutz",
        status="active",
        url="https://www.skroutz.gr/s/005606-active",
    )
    _add_source_url(
        database_url,
        products["222222"],
        source_name="skroutz",
        status="broken",
        url="https://www.skroutz.gr/s/222222-broken",
    )

    response = client.post(
        "/api/price-monitoring/runs",
        json={"source": "skroutz", "selected_models": ["005606", "222222"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "selection_created"
    assert payload["source_url_required"] is True
    assert payload["selected_count"] == 1
    assert payload["skipped_by_reason"]["missing_active_source_url"] == 1
    assert payload["source_url_coverage"]["products_with_active_source_urls"] == 1
    assert payload["source_url_coverage"]["products_without_active_source_urls"] == 1
    assert payload["source_url_coverage"]["missing_source_url_models"] == ["222222"]
    assert payload["items"][0]["catalog_product_id"] == products["005606"].id
    assert payload["items"][0]["source_url_coverage"]["has_active_source_url"] is True

    input_csv_path = Path(payload["input_csv_path"])
    summary_path = Path(payload["selection_summary_path"])
    assert input_csv_path.exists()
    assert summary_path.exists()

    with input_csv_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys()) == ["model", "mpn", "name", "price"]
    assert rows == [
        {
            "model": "005606",
            "mpn": "MPN-1",
            "name": "Eligible Bosch",
            "price": "123.45",
        },
    ]

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["run_id"] == payload["run_id"]
    assert summary["source"] == "skroutz"
    assert summary["selected_models"] == ["005606"]
    assert summary["skipped_by_reason"]["missing_active_source_url"] == 1
    assert summary["source_url_required"] is True
    assert summary["input_csv_path"] == payload["input_csv_path"]
    assert summary["source_url_coverage"] == payload["source_url_coverage"]
    assert (
        summary["selected_items"][0]["source_url_coverage"]["has_active_source_url"]
        is True
    )


def test_run_creation_preserves_hierarchy_filters_in_selection_summary(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/price-monitoring/runs",
        json={
            "source": "skroutz",
            "filters": {
                "family": "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
                "category_name": "Σκεύη Μαγειρικής",
                "sub_category": "Γάστρες",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    summary = json.loads(
        Path(payload["selection_summary_path"]).read_text(encoding="utf-8")
    )
    assert summary["selected_models"] == ["005606"]
    assert summary["filters"]["family"] == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"
    assert summary["filters"]["category_name"] == "Σκεύη Μαγειρικής"
    assert summary["filters"]["sub_category"] == "Γάστρες"
    assert summary["filters"]["category"] is None


def test_run_creation_fails_when_all_selected_products_lack_active_source_urls(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/price-monitoring/runs",
        json={"source": "skroutz", "selected_models": ["777777"]},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["message"] == "No eligible products selected."
    assert detail["selected_count"] == 0
    assert detail["source_url_required"] is True
    assert detail["skipped_by_reason"] == {"missing_active_source_url": 1}
    assert detail["source"] == "skroutz"
    assert detail["source_filter"] == "skroutz"
    assert "Vendor Sources" in detail["operator_message"]


def test_run_creation_fails_with_400_when_selected_count_is_zero(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/price-monitoring/runs",
        json={"source": "skroutz", "selected_models": ["333333"]},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["message"] == "No eligible products selected."
    assert detail["selected_count"] == 0
    assert detail["skipped_by_reason"] == {"ignored": 1}
