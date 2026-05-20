import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api import routes_price_monitoring  # noqa: E402
from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.db.repositories.alerts import (  # noqa: E402
    acknowledge_alert_event,
    create_alert_rule,
    evaluate_alert_rules_for_run,
    list_alert_events,
    resolve_alert_event,
)
from ecommerce.db.models.base import Base  # noqa: E402
from ecommerce.db.models.catalog import CatalogProductRow  # noqa: E402
from ecommerce.db.models.products import Product  # noqa: E402
from ecommerce.db.models.price_monitoring import (
    MonitoringRun,
    PriceObservation,
)  # noqa: E402
from ecommerce.db.models.alerts import AlertEvent, AlertRule  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.price_monitoring.fetch_execution import (
    wait_for_worker_idle,
)  # noqa: E402
from test_price_monitoring_execution_utils import (
    install_fake_execution_child,
)  # noqa: E402


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"


def _create_schema(database_url: str) -> None:
    Base.metadata.create_all(get_engine(database_url))


def _seed_run(session, *, run_id: str = "run-1") -> tuple[MonitoringRun, Product]:
    now = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)
    run = MonitoringRun(
        run_id=run_id,
        source="skroutz",
        status="fetch_completed",
        created_at=now,
        updated_at=now,
    )
    product = Product(
        catalog_source="sourceCata",
        model="005606",
        mpn="MPN-1",
        name="Product One",
        created_at=now,
        updated_at=now,
    )
    session.add_all([run, product])
    _seed_active_catalog(session, now=now)
    session.flush()
    return run, product


def _seed_active_catalog(session, *, now: datetime | None = None) -> None:
    timestamp = now or datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)
    if (
        session.query(CatalogProductRow)
        .filter(
            CatalogProductRow.catalog_source == "sourceCata",
            CatalogProductRow.model == "005606",
        )
        .first()
    ):
        return
    session.add(
        CatalogProductRow(
            catalog_source="sourceCata",
            model="005606",
            mpn="MPN-1",
            name="Product One",
            category="Family:::Family///Category:::Family///Category///Sub",
            raw_category="Family:::Family///Category:::Family///Category///Sub",
            family="Family",
            category_name="Category",
            sub_category="Sub",
            category_levels=["Family", "Category", "Sub"],
            manufacturer="Brand",
            price=Decimal("100.00"),
            quantity=1,
            status=1,
            bestprice_status=1,
            skroutz_status=1,
            is_atomic_model=True,
            automation_eligible=True,
            active=True,
            imported_at=timestamp,
            raw_catalog_row={"model": "005606"},
            warnings=[],
            created_at=timestamp,
            updated_at=timestamp,
        )
    )


def _add_observation(
    session,
    run: MonitoringRun,
    product: Product | None,
    *,
    model: str | None = "005606",
    mpn: str | None = "MPN-1",
    competitor_price: Decimal | None = Decimal("94.00"),
    own_price: Decimal | None = Decimal("100.00"),
    source: str = "skroutz",
) -> PriceObservation:
    now = datetime(2026, 4, 29, 12, 1, tzinfo=timezone.utc)
    delta = (
        own_price - competitor_price
        if own_price is not None and competitor_price is not None
        else None
    )
    observation = PriceObservation(
        monitoring_run_id=run.id,
        product_id=product.id if product is not None else None,
        run_id=run.run_id,
        catalog_source="sourceCata",
        source=source,
        model=model,
        mpn=mpn,
        product_name="Product One",
        competitor_name="Shop",
        competitor_price=competitor_price,
        currency="EUR",
        own_price=own_price,
        price_delta=delta,
        price_delta_percent=(
            (delta / own_price) * Decimal("100")
            if delta is not None and own_price
            else None
        ),
        raw_observation={"model": model, "price": str(own_price or "")},
        matched_by="model" if product is not None else None,
        match_status="matched" if product is not None else "unmatched",
        observed_at=now,
        created_at=now,
    )
    session.add(observation)
    session.flush()
    return observation


def test_alert_metadata_and_migration_create_tables(
    tmp_path: Path, monkeypatch
) -> None:
    assert {"alert_rules", "alert_events"}.issubset(Base.metadata.tables)
    assert AlertRule.__table__.c.rule_type.nullable is False
    assert AlertEvent.__table__.c.dedupe_key.nullable is False
    assert any(
        index.name == "uq_alert_events_dedupe_key" and index.unique
        for index in AlertEvent.__table__.indexes
    )

    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    inspector = inspect(get_engine(database_url))

    assert {"alert_rules", "alert_events"}.issubset(inspector.get_table_names())
    event_indexes = {
        item["name"]: item for item in inspector.get_indexes("alert_events")
    }
    assert bool(event_indexes["uq_alert_events_dedupe_key"]["unique"]) is True


def test_alert_rule_validation_accepts_supported_targets(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        _, product = _seed_run(session)
        for payload in (
            {"rule_type": "other", "product_id": product.id},
            {"rule_type": "competitor_below_own_price"},
            {
                "rule_type": "competitor_below_own_price",
                "product_id": product.id,
                "threshold_amount": "-1",
            },
        ):
            try:
                create_alert_rule(session, payload)
            except ValueError:
                pass
            else:
                raise AssertionError("invalid rule payload was accepted")

        product_rule = create_alert_rule(
            session,
            {"rule_type": "competitor_below_own_price", "product_id": product.id},
        )
        model_rule = create_alert_rule(
            session,
            {
                "rule_type": "competitor_below_own_price",
                "catalog_source": "sourceCata",
                "model": "005606",
            },
        )
        mpn_rule = create_alert_rule(
            session,
            {
                "rule_type": "competitor_below_own_price",
                "catalog_source": "sourceCata",
                "mpn": "MPN-1",
            },
        )

    assert product_rule.product_id == product.id
    assert model_rule.model == "005606"
    assert mpn_rule.mpn == "MPN-1"


def test_alert_evaluation_thresholds_matching_and_dedupe(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        run, product = _seed_run(session)
        _add_observation(
            session,
            run,
            product,
            competitor_price=Decimal("94.00"),
            own_price=Decimal("100.00"),
        )
        _add_observation(
            session,
            run,
            product,
            competitor_price=Decimal("101.00"),
            own_price=Decimal("100.00"),
        )
        _add_observation(
            session, run, product, competitor_price=None, own_price=Decimal("100.00")
        )
        create_alert_rule(
            session,
            {"rule_type": "competitor_below_own_price", "product_id": product.id},
        )
        create_alert_rule(
            session,
            {
                "rule_type": "competitor_below_own_price",
                "product_id": product.id,
                "threshold_amount": "5.00",
            },
        )
        create_alert_rule(
            session,
            {
                "rule_type": "competitor_below_own_price",
                "product_id": product.id,
                "threshold_percent": "5.0",
            },
        )
        create_alert_rule(
            session,
            {
                "rule_type": "competitor_below_own_price",
                "product_id": product.id,
                "threshold_amount": "7.00",
                "threshold_percent": "5.0",
            },
        )

        first = evaluate_alert_rules_for_run(session, "run-1")
        second = evaluate_alert_rules_for_run(session, "run-1")
        event_count = session.query(AlertEvent).count()

    assert first.created_event_count == 3
    assert first.skipped_count >= 5
    assert second.created_event_count == 0
    assert second.duplicate_event_count == 3
    assert event_count == 3


def test_alert_evaluation_fallback_targets_and_product_id_preference(
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        run, product = _seed_run(session)
        other = Product(
            catalog_source="sourceCata",
            model="OTHER",
            mpn="MPN-2",
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
        session.add(other)
        session.flush()
        _add_observation(session, run, product, model="DIFFERENT", mpn="MPN-1")
        _add_observation(session, run, other, model="005606", mpn="MPN-2")
        _add_observation(session, run, None, model="FALLBACK", mpn="MPN-3")
        _add_observation(session, run, None, model=None, mpn="MPN-ONLY")
        preferred = create_alert_rule(
            session,
            {
                "rule_type": "competitor_below_own_price",
                "product_id": product.id,
                "catalog_source": "sourceCata",
                "model": "005606",
            },
        )
        model_rule = create_alert_rule(
            session,
            {
                "rule_type": "competitor_below_own_price",
                "catalog_source": "sourceCata",
                "model": "FALLBACK",
            },
        )
        mpn_rule = create_alert_rule(
            session,
            {
                "rule_type": "competitor_below_own_price",
                "catalog_source": "sourceCata",
                "mpn": "MPN-ONLY",
            },
        )

        result = evaluate_alert_rules_for_run(session, "run-1")
        dedupe_keys = {event.dedupe_key for event in session.query(AlertEvent).all()}

    assert result.created_event_count == 3
    assert any(
        f"alert_rule:{preferred.id}" in key and f"product:{product.id}" in key
        for key in dedupe_keys
    )
    assert any(
        f"alert_rule:{model_rule.id}" in key
        and "catalog_model:sourceCata:FALLBACK" in key
        for key in dedupe_keys
    )
    assert any(
        f"alert_rule:{mpn_rule.id}" in key and "catalog_mpn:sourceCata:MPN-ONLY" in key
        for key in dedupe_keys
    )


def test_alert_event_state_transitions_and_filters(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        run, product = _seed_run(session)
        _add_observation(session, run, product)
        create_alert_rule(
            session,
            {"rule_type": "competitor_below_own_price", "product_id": product.id},
        )
        evaluate_alert_rules_for_run(session, "run-1")
        event = session.query(AlertEvent).one()
        acknowledged = acknowledge_alert_event(session, event.id, "user-a")
        assert acknowledged is not None
        resolved = resolve_alert_event(session, event.id, "user-r")
        assert resolved is not None
        resolved_items, resolved_count = list_alert_events(session, status="resolved")
        open_items, open_count = list_alert_events(session, status="open")
        acknowledged_items, acknowledged_count = list_alert_events(
            session, status="acknowledged"
        )

    assert resolved.status == "resolved"
    assert resolved.acknowledged_at is not None
    assert resolved.resolved_at is not None
    assert resolved_items[0]["status"] == "resolved"
    assert resolved_count == 1
    assert open_items == []
    assert open_count == 0
    assert acknowledged_items == []
    assert acknowledged_count == 0


def test_direct_vendor_observation_can_trigger_alert(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        run, product = _seed_run(session, run_id="electronet-run")
        run.source = "electronet"
        _add_observation(session, run, product, source="electronet")
        create_alert_rule(
            session,
            {"rule_type": "competitor_below_own_price", "product_id": product.id},
        )

        result = evaluate_alert_rules_for_run(session, "electronet-run")
        event = session.query(AlertEvent).one()

    assert result.created_event_count == 1
    assert event.source == "electronet"


def test_alert_api_crud_events_and_not_configured(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ECOMMERCE_DATABASE_URL", raising=False)
    not_configured = TestClient(create_app()).get("/api/price-monitoring/alerts/rules")
    assert not_configured.status_code == 503
    assert (
        not_configured.json()["detail"]["code"] == "price_monitoring_database_required"
    )

    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        run, product = _seed_run(session)
        _add_observation(session, run, product)

    client = TestClient(create_app())
    create_response = client.post(
        "/api/price-monitoring/alerts/rules",
        json={
            "rule_type": "competitor_below_own_price",
            "product_id": product.id,
            "threshold_amount": "1.00",
        },
    )
    assert create_response.status_code == 200
    rule = create_response.json()
    assert client.get("/api/price-monitoring/alerts/rules").json()["count"] == 1
    assert (
        client.get(f"/api/price-monitoring/alerts/rules/{rule['id']}").json()["id"]
        == rule["id"]
    )
    patch = client.patch(
        f"/api/price-monitoring/alerts/rules/{rule['id']}", json={"name": "Below own"}
    ).json()
    assert patch["name"] == "Below own"

    evaluate = client.post("/api/price-monitoring/alerts/evaluate/run-1").json()
    assert evaluate["status"] == "evaluated"
    assert evaluate["created_event_count"] == 1
    events = client.get("/api/price-monitoring/alerts/events").json()
    assert events["count"] == 1
    event_id = events["items"][0]["id"]
    assert (
        client.post(
            f"/api/price-monitoring/alerts/events/{event_id}/acknowledge",
            json={"acknowledged_by": "u"},
        ).json()["status"]
        == "acknowledged"
    )
    assert (
        client.post(
            f"/api/price-monitoring/alerts/events/{event_id}/resolve",
            json={"resolved_by": "u"},
        ).json()["status"]
        == "resolved"
    )
    assert (
        client.post(
            f"/api/price-monitoring/alerts/rules/{rule['id']}/deactivate"
        ).json()["active"]
        is False
    )


def test_fetch_integration_evaluates_active_alert_rules(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    _create_schema(database_url)
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)
    with session_scope(database_url) as session:
        run, product = _seed_run(session)
        create_alert_rule(
            session,
            {"rule_type": "competitor_below_own_price", "product_id": product.id},
        )

    install_fake_execution_child(monkeypatch, tmp_path, mode="success", persist=True)
    client = TestClient(create_app())

    assert (
        client.post(
            "/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}
        ).status_code
        == 202
    )
    assert wait_for_worker_idle()
    first = client.get("/api/price-monitoring/runs/run-1/fetch").json()
    assert (
        client.post(
            "/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}
        ).status_code
        == 202
    )
    assert wait_for_worker_idle()
    second = client.get("/api/price-monitoring/runs/run-1/fetch").json()

    assert first["persistence_status"] == "persisted"
    assert first["alert_evaluation_status"] == "evaluated"
    assert first["alert_event_count"] == 1
    assert second["alert_event_count"] == 0
    assert second["alert_duplicate_count"] == 1
    with session_scope(database_url) as session:
        assert session.query(AlertEvent).count() == 1


def test_fetch_integration_skips_when_no_active_rules(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    _create_schema(database_url)
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)
    with session_scope(database_url) as session:
        _seed_active_catalog(session)

    install_fake_execution_child(monkeypatch, tmp_path, mode="success", persist=True)
    client = TestClient(create_app())
    assert (
        client.post(
            "/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}
        ).status_code
        == 202
    )
    assert wait_for_worker_idle()
    payload = client.get("/api/price-monitoring/runs/run-1/fetch").json()

    assert payload["persistence_status"] == "persisted"
    assert payload["alert_evaluation_status"] == "skipped"
    assert payload["alert_event_count"] == 0


def _write_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "input.csv").write_text(
        "model,mpn,name,price\n005606,MPN-1,Product One,100.00\n", encoding="utf-8"
    )
    (run_dir / "selection_summary.json").write_text(
        json.dumps({"run_id": run_dir.name, "source": "skroutz"}), encoding="utf-8"
    )
