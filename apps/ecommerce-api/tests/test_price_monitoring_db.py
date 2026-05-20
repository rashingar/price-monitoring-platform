import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api import routes_price_monitoring  # noqa: E402
from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.catalog_db import ingest_source_catalog  # noqa: E402
from ecommerce.catalog.source_catalog import SOURCE_CATA_ENV_VAR  # noqa: E402
from ecommerce.db.config import sanitize_database_error  # noqa: E402
from ecommerce.db.diagnostics import get_alembic_head_revision  # noqa: E402
from ecommerce.db.models.base import Base  # noqa: E402
from ecommerce.db.models.catalog import CatalogProductRow  # noqa: E402
from ecommerce.db.models.source_urls import SourceUrl  # noqa: E402
from ecommerce.db.models.products import Product, SourceCaptureSnapshot  # noqa: E402
from ecommerce.db.models.price_monitoring import (
    CatalogSnapshot,
    MonitoringRun,
    OfferObservation,
    PriceObservation,
    PriceObservationListing,
)  # noqa: E402
from ecommerce.db.repositories.products import (
    upsert_product_from_catalog_row,
)  # noqa: E402
from ecommerce.db.repositories.price_monitoring import (
    catalog_snapshot_to_dict,
    list_price_observations,
    monitoring_run_to_dict,
    persist_monitoring_run_creation,
    replace_price_observations,
)  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.jobs.run_price_monitoring_now import main as run_job_main  # noqa: E402
from ecommerce.jobs.check_db_setup import main as check_db_setup_main  # noqa: E402
from ecommerce.price_monitoring.fetch_execution import (
    wait_for_worker_idle,
)  # noqa: E402
from ecommerce.price_monitoring.observations import (
    ParsedPriceObservation,
    parse_price_observations_csv,
)  # noqa: E402
from ecommerce.price_monitoring.runs import PriceMonitoringRunRecord  # noqa: E402
from ecommerce.price_monitoring.selection import (  # noqa: E402
    PriceMonitoringFilters,
    PriceMonitoringSelectionResult,
    SelectedPriceMonitoringProduct,
)
from test_price_monitoring_execution_utils import (
    install_fake_execution_child,
)  # noqa: E402


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"


def _create_schema(database_url: str) -> None:
    Base.metadata.create_all(get_engine(database_url))


def _stamp_alembic_head(database_url: str) -> None:
    head = get_alembic_head_revision()
    assert head is not None
    engine = get_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "create table if not exists alembic_version (version_num varchar(32) not null)"
            )
        )
        connection.execute(text("delete from alembic_version"))
        connection.execute(
            text("insert into alembic_version (version_num) values (:head)"),
            {"head": head},
        )


def _selected_product() -> SelectedPriceMonitoringProduct:
    return SelectedPriceMonitoringProduct(
        model="005606",
        mpn="MPN-1",
        name="Product One",
        manufacturer="Bosch",
        category="Family:::Family///Category:::Family///Category///Sub",
        raw_category="Family:::Family///Category:::Family///Category///Sub",
        family="Family",
        category_name="Category",
        sub_category="Sub",
        category_levels=["Family", "Category", "Sub"],
        price=123.45,
        source="skroutz",
    )


def _run_record(tmp_path: Path) -> PriceMonitoringRunRecord:
    product = _selected_product()
    selection = PriceMonitoringSelectionResult(
        source="skroutz",
        source_filter="skroutz",
        filters=PriceMonitoringFilters(),
        items=[product],
        skipped=[],
    )
    output_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    output_dir.mkdir(parents=True, exist_ok=True)
    input_csv_path = output_dir / "input.csv"
    input_csv_path.write_text(
        "model,mpn,name,price\n005606,MPN-1,Product One,123.45\n", encoding="utf-8"
    )
    selection_summary_path = output_dir / "selection_summary.json"
    selection_summary_path.write_text("{}", encoding="utf-8")
    return PriceMonitoringRunRecord(
        run_id="run-1",
        status="selection_created",
        source="skroutz",
        output_dir=output_dir,
        input_csv_path=input_csv_path,
        selection_summary_path=selection_summary_path,
        selection_result=selection,
        created_at="2026-04-29T12:00:00+00:00",
    )


def _write_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "input.csv").write_text(
        "model,mpn,name,price\n005606,MPN-1,Product One,123.45\n",
        encoding="utf-8",
    )
    (run_dir / "selection_summary.json").write_text(
        json.dumps({"run_id": run_dir.name, "source": "skroutz"}),
        encoding="utf-8",
    )


def _write_fetch_result(run_dir: Path) -> None:
    fetch_result_path = run_dir / "fetch_result.json"
    enriched_csv_path = run_dir / "input_skroutz_enriched.csv"
    summary_path = run_dir / "input_summary.json"
    enriched_csv_path.write_text(
        "model,mpn,price,skroutz_price,skroutz_url,observed_at\n"
        "005606,MPN-1,123.45,119.90,https://example.test/p,2026-04-28T12:00:00+00:00\n",
        encoding="utf-8-sig",
    )
    summary_path.write_text('{"operation":"fetch"}\n', encoding="utf-8")
    fetch_result_path.write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "source": "skroutz",
                "status": "fetch_completed",
                "started_at": "2026-04-28T12:00:00+00:00",
                "completed_at": "2026-04-28T12:00:01+00:00",
                "input_csv_path": str(run_dir / "input.csv"),
                "enriched_csv_path": str(enriched_csv_path),
                "fetch_summary_path": str(summary_path),
                "fetch_result_path": str(fetch_result_path),
                "stdout": "",
                "warnings": [],
                "error": "",
            }
        ),
        encoding="utf-8",
    )


def _write_catalog(path: Path) -> None:
    path.write_text(
        "model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n"
        "005606,MPN-1,Product One,Family,Brand A,123.45,1,1,1,1\n",
        encoding="utf-8-sig",
    )


def _ingest_test_catalog(database_url: str, path: Path) -> None:
    with session_scope(database_url) as session:
        ingest_source_catalog(session, source_cata_path=path)
        product = (
            session.query(CatalogProductRow)
            .filter(CatalogProductRow.model == "005606")
            .one()
        )
        session.add(
            SourceUrl(
                catalog_product_id=product.id,
                catalog_source=product.catalog_source,
                model=product.model,
                mpn=product.mpn,
                manufacturer=product.manufacturer,
                source_name="skroutz",
                source_domain="www.skroutz.gr",
                url="https://www.skroutz.gr/s/005606-active",
                url_normalized="https://www.skroutz.gr/s/005606-active",
                status="active",
                url_type="manual",
                trust_level="manual",
                created_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
                updated_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
            )
        )


def test_app_import_and_db_status_work_without_database_url(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ECOMMERCE_DATABASE_URL", raising=False)

    response = TestClient(create_app()).get("/api/price-monitoring/db/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is False
    assert payload["reachable"] is False
    assert payload["sanitized_database_url"] is None
    assert payload["price_monitoring_database_mode"] == "not_configured"
    assert payload["price_monitoring_database_required_future"] is True
    assert payload["catalog_requires_database"] is True
    assert payload["ready_for_catalog"] is False
    assert payload["price_monitoring_requires_database"] is True
    assert payload["ready_for_price_monitoring"] is False
    assert payload["non_db_workflows_available"] is True
    assert payload["error"] is None
    assert payload["required_tables_present"] is False
    assert payload["missing_tables"]
    assert "Set ECOMMERCE_DATABASE_URL." in payload["setup_hints"]
    assert "Restart ecommerce-api." in payload["setup_hints"]

    observations_response = TestClient(create_app()).get(
        "/api/price-monitoring/observations"
    )
    assert observations_response.status_code == 503
    assert (
        observations_response.json()["detail"]["code"]
        == "price_monitoring_database_required"
    )


def test_check_db_setup_exits_nonzero_without_database_url(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ECOMMERCE_DATABASE_URL", raising=False)

    assert check_db_setup_main([]) == 1
    output = capsys.readouterr().out
    assert "ECOMMERCE_DATABASE_URL configured: False" in output
    assert "Sanitized database URL: (not configured)" in output


def test_db_error_sanitization_removes_password(monkeypatch) -> None:
    raw_url = "postgresql+psycopg://ecommerce:super-secret@127.0.0.1:5432/ecommerce"
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", raw_url)

    message = sanitize_database_error(
        f"could not connect using {raw_url}; password=super-secret"
    )

    assert "super-secret" not in message
    assert "***" in message


def test_db_status_sanitizes_reachability_errors(monkeypatch) -> None:
    raw_url = "postgresql+psycopg://ecommerce:super-secret@127.0.0.1:5432/ecommerce"
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", raw_url)

    def broken_database_status():
        return {
            "configured": True,
            "reachable": False,
            "dialect": None,
            "sanitized_database_url": "postgresql+psycopg://ecommerce:***@127.0.0.1:5432/ecommerce",
            "alembic_current_revision": None,
            "alembic_head_revision": "20260429_0002",
            "alembic_up_to_date": None,
            "required_tables": {},
            "required_tables_present": False,
            "missing_tables": [],
            "row_counts": None,
            "price_monitoring_database_mode": "unreachable",
            "price_monitoring_database_required_future": True,
            "error": sanitize_database_error(f"could not connect using {raw_url}"),
            "setup_hints": [
                "Check that PostgreSQL is running and that ECOMMERCE_DATABASE_URL credentials are correct."
            ],
            "warnings": [],
        }

    monkeypatch.setattr(
        routes_price_monitoring,
        "collect_price_monitoring_database_readiness",
        broken_database_status,
    )

    response = TestClient(create_app()).get("/api/price-monitoring/db/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["reachable"] is False
    assert "super-secret" not in payload["sanitized_database_url"]
    assert "super-secret" not in payload["error"]
    assert "***" in payload["error"]
    assert any("PostgreSQL" in hint for hint in payload["setup_hints"])


def test_db_status_reports_migrated_empty_database_as_configured_empty(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    _create_schema(database_url)
    _stamp_alembic_head(database_url)

    response = TestClient(create_app()).get("/api/price-monitoring/db/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["reachable"] is True
    assert payload["dialect"] == "sqlite"
    assert payload["required_tables_present"] is True
    head_revision = get_alembic_head_revision()
    assert payload["alembic_current_revision"] == head_revision
    assert payload["alembic_head_revision"] == head_revision
    assert payload["alembic_up_to_date"] is True
    assert payload["price_monitoring_database_mode"] == "configured_empty"
    assert payload["ready_for_catalog"] is True
    assert payload["ready_for_price_monitoring"] is False
    assert payload["active_catalog_count"] == 0
    assert "active_catalog_empty" in payload["blocking_reasons"]
    assert all(count == 0 for count in payload["row_counts"].values())
    assert payload["missing_tables"] == []
    assert payload["setup_hints"] == []


def test_db_status_detects_missing_required_tables(tmp_path: Path, monkeypatch) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    engine = get_engine(database_url)
    Product.__table__.create(engine)
    _stamp_alembic_head(database_url)

    response = TestClient(create_app()).get("/api/price-monitoring/db/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["reachable"] is True
    assert payload["required_tables"]["products"] is True
    assert payload["required_tables"]["monitoring_runs"] is False
    assert payload["required_tables_present"] is False
    assert "monitoring_runs" in payload["missing_tables"]
    assert payload["row_counts"] is None
    assert payload["price_monitoring_database_mode"] == "incomplete"
    assert any("alembic upgrade head" in hint for hint in payload["setup_hints"])


def test_model_metadata_contains_price_monitoring_tables() -> None:
    assert {
        "catalog_products",
        "source_urls",
        "products",
        "monitoring_runs",
        "catalog_snapshots",
        "price_observations",
        "price_observation_listings",
    }.issubset(Base.metadata.tables)
    assert CatalogProductRow.__table__.c.model.nullable is False
    assert SourceUrl.__table__.c.catalog_product_id.nullable is False
    assert SourceUrl.__table__.c.failure_count.server_default is not None
    assert MonitoringRun.__table__.c.run_id.unique is None
    assert Product.__table__.c.catalog_source.nullable is False
    assert CatalogSnapshot.__table__.c.raw_catalog_row.type is not None
    assert PriceObservation.__table__.c.raw_observation.type is not None
    assert PriceObservation.__table__.c.product_id.nullable is True
    assert PriceObservationListing.__table__.c.price_observation_id.nullable is False
    assert PriceObservationListing.__table__.c.raw_listing.type is not None
    assert MonitoringRun.__table__.c.fetch_attempt.server_default is not None
    assert PriceObservation.__table__.c.match_status.server_default is not None


def test_alembic_configuration_has_price_monitoring_head_migration() -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()

    assert heads == [get_alembic_head_revision()]
    migration_text = (
        PROJECT_ROOT
        / "migrations"
        / "versions"
        / "20260429_0001_price_monitoring_persistence.py"
    ).read_text(encoding="utf-8")
    for table_name in (
        "products",
        "monitoring_runs",
        "catalog_snapshots",
        "price_observations",
    ):
        assert f'"{table_name}"' in migration_text
    assert "postgresql.JSONB" in migration_text
    assert "uq_products_catalog_source_model_present" in migration_text
    assert "ix_price_observations_match_status" in migration_text
    active_catalog_migration = (
        PROJECT_ROOT / "migrations" / "versions" / "20260429_0003_active_catalog.py"
    ).read_text(encoding="utf-8")
    assert '"catalog_products"' in active_catalog_migration
    assert "uq_catalog_products_catalog_source_model" in active_catalog_migration
    source_urls_migration = (
        PROJECT_ROOT / "migrations" / "versions" / "20260429_0004_source_urls.py"
    ).read_text(encoding="utf-8")
    assert '"source_urls"' in source_urls_migration
    assert "uq_source_urls_catalog_product_url_normalized" in source_urls_migration
    assert "catalog_products.id" in source_urls_migration
    unified_sources_migration = (
        PROJECT_ROOT
        / "migrations"
        / "versions"
        / "20260503_0005_unified_product_sources.py"
    ).read_text(encoding="utf-8")
    for table_name in (
        "vendors",
        "product_sources",
        "source_capture_snapshots",
        "offer_observations",
    ):
        assert f'"{table_name}"' in unified_sources_migration
    assert "uq_product_sources_product_canonical_url_hash" in unified_sources_migration
    source_url_agent_migration = (
        PROJECT_ROOT / "migrations" / "versions" / "20260503_0006_source_url_agent.py"
    ).read_text(encoding="utf-8")
    for table_name in ("source_url_discovery_runs", "source_url_candidates"):
        assert f'"{table_name}"' in source_url_agent_migration
    observation_batch_migration = (
        PROJECT_ROOT
        / "migrations"
        / "versions"
        / "20260505_0009_observation_batches.py"
    ).read_text(encoding="utf-8")
    assert "observation_batch_id" in observation_batch_migration
    listings_migration = (
        PROJECT_ROOT
        / "migrations"
        / "versions"
        / "20260513_0011_price_observation_listings.py"
    ).read_text(encoding="utf-8")
    assert '"price_observation_listings"' in listings_migration
    assert "ix_price_observation_listings_observation_rank" in listings_migration
    catalog_listing_migration = (
        PROJECT_ROOT
        / "migrations"
        / "versions"
        / "20260515_0013_catalog_listing_indexes.py"
    ).read_text(encoding="utf-8")
    assert "ix_source_urls_catalog_product_status_source" in catalog_listing_migration


def test_sqlite_metadata_schema_contains_expected_indexes(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    assert set(inspector.get_table_names()) >= {
        "catalog_products",
        "source_urls",
        "products",
        "monitoring_runs",
        "catalog_snapshots",
        "price_observations",
        "price_observation_listings",
    }
    catalog_indexes = {
        item["name"] for item in inspector.get_indexes("catalog_products")
    }
    source_url_indexes = {item["name"] for item in inspector.get_indexes("source_urls")}
    product_indexes = {item["name"] for item in inspector.get_indexes("products")}
    observation_indexes = {
        item["name"] for item in inspector.get_indexes("price_observations")
    }
    listing_indexes = {
        item["name"] for item in inspector.get_indexes("price_observation_listings")
    }
    offer_indexes = {
        item["name"] for item in inspector.get_indexes("offer_observations")
    }
    vendor_capture_indexes = {
        item["name"] for item in inspector.get_indexes("vendor_source_capture_runs")
    }
    assert "uq_catalog_products_catalog_source_model" in catalog_indexes
    assert "ix_source_urls_catalog_product_id" in source_url_indexes
    assert "ix_source_urls_status" in source_url_indexes
    assert "ix_source_urls_catalog_product_status_source" in source_url_indexes
    assert "uq_products_catalog_source_model_present" in product_indexes
    assert "ix_price_observations_match_status" in observation_indexes
    assert "ix_price_observations_observation_batch_id" in observation_indexes
    assert "ix_price_observation_listings_observation_rank" in listing_indexes
    assert "ix_price_observation_listings_run_product_price" in listing_indexes
    assert "ix_offer_observations_observation_batch_id" in offer_indexes
    assert (
        "ix_vendor_source_capture_runs_observation_batch_id" in vendor_capture_indexes
    )


def test_repository_serializes_decimal_and_datetime_safely(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        run = persist_monitoring_run_creation(session, _run_record(tmp_path))
        session.flush()
        run_payload = monitoring_run_to_dict(run)
        snapshot_payload = catalog_snapshot_to_dict(run.catalog_snapshots[0])

    assert run_payload["created_at"] == "2026-04-29T12:00:00+00:00"
    assert snapshot_payload["own_price"] == 123.45
    assert snapshot_payload["raw_catalog_row"]["model"] == "005606"


def test_run_creation_api_persists_monitoring_run_and_catalog_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    _create_schema(database_url)
    catalog_path = tmp_path / "sourceCata.csv"
    _write_catalog(catalog_path)
    _ingest_test_catalog(database_url, catalog_path)
    monkeypatch.setenv(SOURCE_CATA_ENV_VAR, str(catalog_path))
    monkeypatch.chdir(tmp_path)

    response = TestClient(create_app()).post(
        "/api/price-monitoring/runs",
        json={"source": "skroutz", "selected_models": ["005606"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["input_csv_path"]
    assert Path(payload["input_csv_path"]).exists()
    with session_scope(database_url) as session:
        run = (
            session.query(MonitoringRun)
            .filter(MonitoringRun.run_id == payload["run_id"])
            .one()
        )
        snapshots = (
            session.query(CatalogSnapshot)
            .filter(CatalogSnapshot.run_id == payload["run_id"])
            .all()
        )
        products = session.query(Product).all()

    assert run.source == "skroutz"
    assert run.status == "selection_created"
    assert run.trigger_type == "manual"
    assert run.selected_count == 1
    assert run.skipped_count == 0
    assert len(snapshots) == 1
    assert snapshots[0].product_id == products[0].id
    assert products[0].catalog_source == "sourceCata"


def test_run_creation_api_reports_db_persistence_failure(
    tmp_path: Path, monkeypatch
) -> None:
    catalog_path = tmp_path / "sourceCata.csv"
    _write_catalog(catalog_path)
    monkeypatch.setenv(SOURCE_CATA_ENV_VAR, str(catalog_path))
    monkeypatch.setenv(
        "ECOMMERCE_DATABASE_URL",
        "postgresql+psycopg://user:secret-password@localhost/db",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        routes_price_monitoring,
        "require_database_ready_for_price_monitoring",
        lambda: None,
    )
    monkeypatch.setattr(
        routes_price_monitoring,
        "create_price_monitoring_run",
        lambda request: _run_record(tmp_path),
    )

    def broken_persistence(record, *, trigger_type: str = "manual"):
        raise RuntimeError("connection failed for password secret-password")

    monkeypatch.setattr(
        routes_price_monitoring,
        "persist_run_creation_if_configured",
        broken_persistence,
    )

    response = TestClient(create_app()).post(
        "/api/price-monitoring/runs",
        json={"source": "skroutz", "selected_models": ["005606"]},
    )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "DB persistence failed" in detail
    assert "secret-password" not in detail


def test_observation_parser_handles_source_specific_and_generic_columns(
    tmp_path: Path,
) -> None:
    source_specific = tmp_path / "skroutz.csv"
    source_specific.write_text(
        "model,mpn,name,price,skroutz_price,skroutz_url,observed_at\n"
        "005606,MPN-1,Product One,123.45,119.90,https://skroutz.test/p,2026-04-28 12:00:00\n",
        encoding="utf-8",
    )
    generic = tmp_path / "generic.csv"
    generic.write_text(
        "model;mpn;product_name;competitor_price;store;product_url;current_price\n"
        "123456;MPN-2;Product Two;88,50;Store A;https://example.test/p;90,00\n",
        encoding="utf-8",
    )

    parsed_source = parse_price_observations_csv(
        source_specific, run_id="run-1", source="skroutz"
    )
    parsed_generic = parse_price_observations_csv(
        generic, run_id="run-2", source="bestprice"
    )

    assert parsed_source.observations[0].competitor_price == Decimal("119.90")
    assert parsed_source.observations[0].own_price == Decimal("123.45")
    assert parsed_generic.observations[0].competitor_name == "Store A"
    assert parsed_generic.observations[0].competitor_price == Decimal("88.50")
    assert parsed_generic.observations[0].own_price == Decimal("90.00")
    assert parsed_generic.observations[0].raw_observation["store"] == "Store A"


def test_observation_parser_handles_alias_columns_and_skips_rows_without_model_or_mpn(
    tmp_path: Path,
) -> None:
    path = tmp_path / "alias.csv"
    path.write_text(
        "Product Model,Manufacturer-Part-Number,Title,Internal Price,Fetched Price,Shop,Source URL\n"
        "555555,MPN-5,Alias Product,50.00,45.25,Shop A,https://example.test/a\n"
        ",,,,,Shop B,https://example.test/b\n",
        encoding="utf-8",
    )

    parsed = parse_price_observations_csv(path, run_id="run-1", source="bestprice")

    assert len(parsed.observations) == 1
    observation = parsed.observations[0]
    assert observation.model == "555555"
    assert observation.mpn == "MPN-5"
    assert observation.product_name == "Alias Product"
    assert observation.own_price == Decimal("50.00")
    assert observation.competitor_price == Decimal("45.25")
    assert observation.competitor_name == "Shop A"
    assert observation.product_url == "https://example.test/a"
    assert parsed.warnings


def test_observation_parser_keeps_mpn_only_identity_and_warns_on_bad_price(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mpn_only.csv"
    path.write_text(
        "Manufacturer Part Number,Product Name,Catalog Price,Price Found\n"
        "MPN-ONLY,MPN Only Product,10.00,not-a-price\n",
        encoding="utf-8",
    )

    parsed = parse_price_observations_csv(path, run_id="run-1", source="skroutz")

    assert len(parsed.observations) == 1
    assert parsed.observations[0].model is None
    assert parsed.observations[0].mpn == "MPN-ONLY"
    assert parsed.observations[0].competitor_price is None
    assert any("malformed competitor_price" in warning for warning in parsed.warnings)


def test_product_upsert_uses_catalog_source_and_model_boundary(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        first = upsert_product_from_catalog_row(
            session,
            {"model": "005606", "mpn": "MPN-1", "name": "One"},
            catalog_source="sourceA",
        )
        second = upsert_product_from_catalog_row(
            session,
            {"model": "005606", "mpn": "MPN-2", "name": "Two"},
            catalog_source="sourceB",
        )
        updated = upsert_product_from_catalog_row(
            session,
            {"model": "005606", "mpn": "MPN-3", "name": "Updated"},
            catalog_source="sourceA",
        )
        session.flush()

        assert first is not None
        assert second is not None
        assert updated is not None
        assert first.id == updated.id
        assert second.id != first.id
        assert session.query(Product).count() == 2
        assert updated.name == "Updated"


def test_product_upsert_falls_back_to_catalog_source_and_mpn(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        first = upsert_product_from_catalog_row(
            session, {"mpn": "MPN-ONLY", "name": "One"}, catalog_source="sourceA"
        )
        updated = upsert_product_from_catalog_row(
            session, {"mpn": "MPN-ONLY", "name": "Updated"}, catalog_source="sourceA"
        )
        other_source = upsert_product_from_catalog_row(
            session, {"mpn": "MPN-ONLY", "name": "Other"}, catalog_source="sourceB"
        )
        session.flush()

        assert first is not None
        assert updated is not None
        assert other_source is not None
        assert first.id == updated.id
        assert other_source.id != first.id
        assert updated.model is None
        assert updated.name == "Updated"


def test_catalog_snapshot_writer_stores_selected_fields_and_raw_payload(
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)

    with session_scope(database_url) as session:
        run = persist_monitoring_run_creation(session, _run_record(tmp_path))
        session.flush()
        snapshot = run.catalog_snapshots[0]

    assert snapshot.model == "005606"
    assert snapshot.product_id is not None
    assert snapshot.catalog_source == "sourceCata"
    assert snapshot.manufacturer == "Bosch"
    assert snapshot.family == "Family"
    assert snapshot.raw_catalog_row["category_levels"] == ["Family", "Category", "Sub"]


def test_unresolved_product_id_is_allowed_for_observations_and_included_by_default(
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)

    with session_scope(database_url) as session:
        run = persist_monitoring_run_creation(session, _run_record(tmp_path))
        replacement = replace_price_observations(
            session,
            run,
            [
                ParsedPriceObservation(
                    run_id="run-1",
                    catalog_source="sourceCata",
                    source="skroutz",
                    model="UNKNOWN",
                    mpn=None,
                    product_name="Unknown",
                    competitor_name="Shop",
                    competitor_price=Decimal("10.00"),
                    currency="EUR",
                    availability=None,
                    product_url=None,
                    own_price=None,
                    price_delta=None,
                    price_delta_percent=None,
                    raw_observation={"model": "UNKNOWN"},
                    observed_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
                )
            ],
        )
        session.flush()
        items, count = list_price_observations(session, run_id="run-1")
        matched_only, matched_count = list_price_observations(
            session, run_id="run-1", include_unmatched=False
        )

    assert replacement.unmatched_observation_count == 1
    assert count == 1
    assert items[0]["product_id"] is None
    assert items[0]["match_status"] == "unmatched"
    assert items[0]["is_matched"] is False
    assert matched_count == 0
    assert matched_only == []


def test_fetch_response_includes_observation_count_when_db_configured(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    _create_schema(database_url)
    catalog_path = tmp_path / "sourceCata.csv"
    _write_catalog(catalog_path)
    _ingest_test_catalog(database_url, catalog_path)
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)

    install_fake_execution_child(monkeypatch, tmp_path, mode="success", persist=True)

    client = TestClient(create_app())
    response = client.post(
        "/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}
    )

    assert response.status_code == 202
    assert wait_for_worker_idle()
    payload = client.get("/api/price-monitoring/runs/run-1/fetch").json()
    assert payload["observation_count"] == 1
    assert payload["replaced_observation_count"] == 0
    assert payload["catalog_snapshot_count"] == 1
    assert payload["matched_observation_count"] == 1
    assert payload["unmatched_observation_count"] == 0
    assert payload["was_refetch"] is False
    assert payload["fetch_attempt"] == 1
    assert payload["persistence_status"] == "persisted"
    assert payload["persistence_warnings"] == []
    with session_scope(database_url) as session:
        count = session.query(PriceObservation).count()
    assert count == 1


def test_get_fetch_result_reports_missing_when_db_rows_do_not_exist(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    _create_schema(database_url)
    catalog_path = tmp_path / "sourceCata.csv"
    _write_catalog(catalog_path)
    _ingest_test_catalog(database_url, catalog_path)
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)
    _write_fetch_result(run_dir)

    response = TestClient(create_app()).get("/api/price-monitoring/runs/run-1/fetch")

    assert response.status_code == 200
    payload = response.json()
    assert payload["persistence_status"] == "missing"
    assert any(
        "database rows were not found" in warning
        for warning in payload["persistence_warnings"]
    )


def test_get_fetch_result_reports_persisted_when_db_rows_exist(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    _create_schema(database_url)
    catalog_path = tmp_path / "sourceCata.csv"
    _write_catalog(catalog_path)
    _ingest_test_catalog(database_url, catalog_path)
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)
    _write_fetch_result(run_dir)
    with session_scope(database_url) as session:
        run = persist_monitoring_run_creation(session, _run_record(tmp_path))
        replace_price_observations(
            session,
            run,
            [
                ParsedPriceObservation(
                    run_id="run-1",
                    catalog_source="sourceCata",
                    source="skroutz",
                    model="005606",
                    mpn="MPN-1",
                    product_name="Product One",
                    competitor_name="Shop",
                    competitor_price=Decimal("119.90"),
                    currency="EUR",
                    availability=None,
                    product_url="https://example.test/p",
                    own_price=Decimal("123.45"),
                    price_delta=Decimal("3.55"),
                    price_delta_percent=None,
                    raw_observation={"model": "005606"},
                    observed_at=datetime(2026, 4, 28, 12, tzinfo=timezone.utc),
                )
            ],
        )

    response = TestClient(create_app()).get("/api/price-monitoring/runs/run-1/fetch")

    assert response.status_code == 200
    payload = response.json()
    assert payload["persistence_status"] == "persisted"
    assert payload["persistence_warnings"] == []


def test_backfill_listings_endpoint_performs_explicit_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    monkeypatch.setattr(
        routes_price_monitoring,
        "require_database_ready_for_price_monitoring",
        lambda: None,
    )
    _create_schema(database_url)
    now = datetime(2026, 4, 29, 12, tzinfo=timezone.utc)
    with session_scope(database_url) as session:
        product = Product(
            catalog_source="sourceCata",
            model="005606",
            mpn="MPN-1",
            name="Product One",
            current_price=Decimal("123.45"),
            created_at=now,
            updated_at=now,
        )
        session.add(product)
        session.flush()
        run = MonitoringRun(
            run_id="run-1",
            source="skroutz",
            status="fetch_completed",
            trigger_type="manual",
            selected_count=1,
            skipped_count=0,
            created_at=now,
            updated_at=now,
        )
        session.add(run)
        session.flush()
        snapshot = SourceCaptureSnapshot(
            product_id=product.id,
            capture_strategy="test",
            page_url="https://skroutz.test/product",
            captured_at=now,
            created_at=now,
        )
        session.add(snapshot)
        session.flush()
        observation = PriceObservation(
            monitoring_run_id=run.id,
            product_id=product.id,
            source_capture_snapshot_id=snapshot.id,
            run_id="run-1",
            catalog_source="sourceCata",
            source="skroutz",
            model="005606",
            mpn="MPN-1",
            product_name="Product One",
            competitor_name="Collapsed Primary",
            competitor_price=Decimal("999.00"),
            own_price=Decimal("123.45"),
            currency="EUR",
            product_url="https://skroutz.test/product",
            raw_observation={},
            matched_by="model",
            match_status="matched",
            observed_at=now,
            created_at=now,
        )
        session.add(observation)
        session.add(
            OfferObservation(
                product_id=product.id,
                source_capture_snapshot_id=snapshot.id,
                observation_batch_id="batch-1",
                seller_name="Store A",
                seller_url="https://seller.test/a",
                price=Decimal("118.50"),
                currency="EUR",
                raw_observation={"rank": 1},
                observed_at=now,
                created_at=now,
            )
        )

    response = TestClient(create_app()).post(
        "/api/price-monitoring/runs/run-1/backfill-listings"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["inserted_count"] == 1
    assert payload["listing_count"] == 1
    with session_scope(database_url) as session:
        listings = session.query(PriceObservationListing).all()
    assert len(listings) == 1
    assert listings[0].seller_name == "Store A"
    assert listings[0].price == Decimal("118.50")


def test_run_detail_includes_db_status_without_breaking_file_first_response(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    _create_schema(database_url)
    catalog_path = tmp_path / "sourceCata.csv"
    _write_catalog(catalog_path)
    _ingest_test_catalog(database_url, catalog_path)
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)

    response = TestClient(create_app()).get("/api/price-monitoring/runs/run-1")

    assert response.status_code == 404
    assert "DB-backed price monitoring run not found" in response.json()["detail"]


def test_run_detail_includes_db_persistence_counts(tmp_path: Path, monkeypatch) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    _create_schema(database_url)
    catalog_path = tmp_path / "sourceCata.csv"
    _write_catalog(catalog_path)
    _ingest_test_catalog(database_url, catalog_path)
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)
    with session_scope(database_url) as session:
        run = persist_monitoring_run_creation(session, _run_record(tmp_path))
        replace_price_observations(
            session,
            run,
            [
                ParsedPriceObservation(
                    run_id="run-1",
                    catalog_source="sourceCata",
                    source="skroutz",
                    model="005606",
                    mpn="MPN-1",
                    product_name="Product One",
                    competitor_name="Shop",
                    competitor_price=Decimal("119.90"),
                    currency="EUR",
                    availability=None,
                    product_url=None,
                    own_price=Decimal("123.45"),
                    price_delta=Decimal("3.55"),
                    price_delta_percent=None,
                    raw_observation={"model": "005606"},
                    observed_at=datetime(2026, 4, 28, 12, tzinfo=timezone.utc),
                )
            ],
        )

    response = TestClient(create_app()).get("/api/price-monitoring/runs/run-1")

    assert response.status_code == 200
    db = response.json()["db"]
    assert db["configured"] is True
    assert db["reachable"] is True
    assert db["monitoring_run_exists"] is True
    assert db["observation_count"] == 1
    assert db["matched_observation_count"] == 1
    assert db["unmatched_observation_count"] == 0
    assert db["alert_event_count"] == 0
    assert db["persistence_status"] == "persisted"


def test_refetch_appends_observations_for_same_run_id_while_latest_query_matches_previous_behavior(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    _create_schema(database_url)
    catalog_path = tmp_path / "sourceCata.csv"
    _write_catalog(catalog_path)
    _ingest_test_catalog(database_url, catalog_path)
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)

    install_fake_execution_child(
        monkeypatch, tmp_path, mode="success", persist=True, prices=["119.90", "111.11"]
    )
    client = TestClient(create_app())

    assert (
        client.post(
            "/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}
        ).status_code
        == 202
    )
    assert wait_for_worker_idle()
    second_response = client.post(
        "/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}
    )
    assert second_response.status_code == 202
    assert wait_for_worker_idle()
    second_payload = client.get("/api/price-monitoring/runs/run-1/fetch").json()
    assert second_payload["replaced_observation_count"] == 1
    assert second_payload["was_refetch"] is True
    assert second_payload["fetch_attempt"] == 2

    with session_scope(database_url) as session:
        items, count = list_price_observations(session, run_id="run-1")
        stored_count = session.query(PriceObservation).count()
        run = session.query(MonitoringRun).filter(MonitoringRun.run_id == "run-1").one()
    assert count == 1
    assert stored_count == 2
    assert items[0]["competitor_price"] == 111.11
    assert items[0]["raw_observation"]["persistence"]["fetch_attempt"] == 2
    assert items[0]["raw_observation"]["persistence"]["was_refetch"] is True
    assert run.fetch_attempt == 2
    assert run.last_was_refetch is True


def test_observation_api_serializes_decimal_datetime_and_raw_json(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    _create_schema(database_url)
    catalog_path = tmp_path / "sourceCata.csv"
    _write_catalog(catalog_path)
    _ingest_test_catalog(database_url, catalog_path)
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)

    install_fake_execution_child(monkeypatch, tmp_path, mode="success", persist=True)
    client = TestClient(create_app())
    fetch_response = client.post(
        "/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}
    )
    assert fetch_response.status_code == 202
    assert wait_for_worker_idle()

    observations = client.get("/api/price-monitoring/observations").json()
    item = observations["items"][0]
    assert observations["count"] == 1
    assert item["competitor_price"] == 119.9
    assert item["observed_at"] == "2026-04-28T12:00:00+00:00"
    assert item["raw_observation"]["source"] == "fake_source_url_capture"
    assert item["catalog_source"] == "sourceCata"
    assert item["matched_by"] == "model"
    assert item["match_status"] == "matched"
    assert item["is_matched"] is True

    filtered = client.get(
        "/api/price-monitoring/observations",
        params={
            "catalog_source": "sourceCata",
            "match_status": "matched",
            "limit": 1,
            "offset": 0,
        },
    ).json()
    assert filtered["count"] == 1
    assert filtered["limit"] == 1

    run_observations = client.get(
        "/api/price-monitoring/runs/run-1/observations"
    ).json()
    assert run_observations["run_id"] == "run-1"
    assert run_observations["count"] == 1
    assert run_observations["matched_count"] == 1
    assert run_observations["unmatched_count"] == 0

    snapshot = client.get("/api/price-monitoring/runs/run-1/catalog-snapshot").json()
    assert snapshot["run_id"] == "run-1"
    assert snapshot["count"] == 1
    assert snapshot["items"][0]["raw_catalog_row"]["model"] == "005606"
    product_id = snapshot["items"][0]["product_id"]
    assert product_id is not None

    product_history = client.get(
        f"/api/price-monitoring/products/{product_id}/price-history"
    ).json()
    assert product_history["product_id"] == product_id
    assert product_history["count"] == 1
    ambiguous_product_history = client.get(
        "/api/price-monitoring/products/005606/price-history"
    )
    assert ambiguous_product_history.status_code == 400
    assert "by-model" in ambiguous_product_history.json()["detail"]

    history = client.get(
        "/api/price-monitoring/products/by-model/005606/price-history"
    ).json()
    assert history["model"] == "005606"
    assert history["count"] == 1


def test_job_script_missing_run_id_exits_nonzero() -> None:
    assert run_job_main(["--source", "skroutz"]) != 0
