import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.db.models import Base  # noqa: E402
from ecommerce.db.models.alerts import AlertRule  # noqa: E402
from ecommerce.db.models.catalog import CatalogProductRow  # noqa: E402
from ecommerce.db.models.jobs import EcommerceJob  # noqa: E402
from ecommerce.db.models.price_monitoring import MonitoringRun  # noqa: E402
from ecommerce.db.models.products import ProductSource  # noqa: E402
from ecommerce.db.models.source_urls import SourceUrl  # noqa: E402
from ecommerce.db.repositories import json_safe_value as compatibility_json_safe_value  # noqa: E402
from ecommerce.db.repositories.alerts import create_alert_rule  # noqa: E402
from ecommerce.db.repositories.capture_persistence import persist_capture_result  # noqa: E402,F401
from ecommerce.db.repositories.jobs import create_queued_job, get_job_by_id  # noqa: E402
from ecommerce.db.repositories.price_monitoring import get_monitoring_run, monitoring_run_to_dict  # noqa: E402
from ecommerce.db.repositories.products import product_source_to_dict  # noqa: E402
from ecommerce.db.repositories.source_convergence import sync_source_url_to_product_source  # noqa: E402
from ecommerce.db.repositories.source_urls import create_or_update_imported_source_url, get_active_catalog_product, source_url_to_dict  # noqa: E402
from ecommerce.db.repositories.vendor_sources import create_vendor_source_capture_run_row, vendor_source_capture_run_to_dict  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402


def _database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"


def _create_schema(database_url: str) -> None:
    Base.metadata.create_all(get_engine(database_url))


def _catalog_row(now: datetime) -> CatalogProductRow:
    return CatalogProductRow(
        catalog_source="sourceCata",
        model="005606",
        mpn="MPN-1",
        name="Product One",
        category="Kitchen",
        raw_category="Kitchen",
        manufacturer="Bosch",
        imported_at=now,
        created_at=now,
        updated_at=now,
    )


def test_repository_domain_imports_and_representative_behavior(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    _create_schema(database_url)
    now = datetime.now(timezone.utc).replace(microsecond=0)

    with session_scope(database_url) as session:
        catalog_row = _catalog_row(now)
        session.add(catalog_row)
        session.flush()

        assert get_active_catalog_product(session, catalog_row.id) is catalog_row
        upsert = create_or_update_imported_source_url(
            session,
            catalog_product_id=catalog_row.id,
            url="https://www.electronet.gr/product/example",
            status="active",
        )
        assert isinstance(upsert.row, SourceUrl)
        assert source_url_to_dict(upsert.row)["status"] == "active"

        product_source = sync_source_url_to_product_source(session, upsert.row)
        assert isinstance(product_source, ProductSource)
        assert product_source_to_dict(product_source)["active"] is True

        monitoring_run = MonitoringRun(
            run_id="run-1",
            source="source_urls",
            status="selection_created",
            created_at=now,
            updated_at=now,
        )
        session.add(monitoring_run)
        session.flush()
        assert get_monitoring_run(session, "run-1") is monitoring_run
        assert monitoring_run_to_dict(monitoring_run)["run_id"] == "run-1"

        alert_rule = create_alert_rule(session, {"product_id": product_source.product_id, "threshold_amount": "1"})
        assert isinstance(alert_rule, AlertRule)

        job = create_queued_job(session, job_type="diagnostic", payload={"ok": True}, job_id="job-1")
        assert isinstance(job, EcommerceJob)
        assert get_job_by_id(session, "job-1") is job

        run_row = create_vendor_source_capture_run_row(
            session,
            run_id="capture-1",
            observation_batch_id="batch-1",
            status="running",
            source_filter=None,
            catalog_source="sourceCata",
            filters={"limit": 1},
            result_path=tmp_path / "capture.json",
        )
        assert vendor_source_capture_run_to_dict(run_row)["run_id"] == "capture-1"

    assert compatibility_json_safe_value({"at": now}) == {"at": now.isoformat()}
