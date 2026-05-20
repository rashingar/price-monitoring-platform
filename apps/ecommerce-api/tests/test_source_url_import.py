import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models.base import Base  # noqa: E402
from ecommerce.db.models.catalog import CatalogProductRow  # noqa: E402
from ecommerce.db.models.source_urls import SourceUrl  # noqa: E402
from ecommerce.db.models.products import Product  # noqa: E402
from ecommerce.db.models.price_monitoring import (
    MonitoringRun,
    PriceObservation,
)  # noqa: E402
from ecommerce.db.repositories.source_urls import source_url_summary  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.jobs.import_source_urls import main as import_job_main  # noqa: E402
from ecommerce.source_url_import import import_source_urls  # noqa: E402

NOW = datetime(2026, 4, 29, 12, tzinfo=timezone.utc)


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"


def _create_schema(database_url: str) -> None:
    Base.metadata.create_all(get_engine(database_url))


def _catalog_product(
    session,
    *,
    model: str,
    mpn: str = "MPN-1",
    catalog_source: str = "sourceCata",
    active: bool = True,
) -> CatalogProductRow:
    row = CatalogProductRow(
        catalog_source=catalog_source,
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


def _run(
    session,
    *,
    run_id: str = "run-1",
    source: str = "skroutz",
    enriched_csv_path: str | None = None,
) -> MonitoringRun:
    row = MonitoringRun(
        run_id=run_id,
        source=source,
        status="fetch_completed",
        enriched_csv_path=enriched_csv_path,
        created_at=NOW,
        started_at=NOW,
        completed_at=NOW,
        updated_at=NOW,
    )
    session.add(row)
    session.flush()
    return row


def _observation_product(
    session, *, model: str | None, mpn: str | None = None
) -> Product:
    product = Product(
        catalog_source="sourceCata",
        model=model,
        mpn=mpn,
        active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(product)
    session.flush()
    return product


def _observation(
    session,
    run: MonitoringRun,
    *,
    url: str | None,
    model: str | None = "005606",
    mpn: str | None = "MPN-1",
    product_id: int | None = None,
    match_status: str = "matched",
    competitor_price: Decimal | None = Decimal("119.90"),
    source: str = "skroutz",
) -> PriceObservation:
    row = PriceObservation(
        monitoring_run_id=run.id,
        product_id=product_id,
        run_id=run.run_id,
        catalog_source="sourceCata",
        source=source,
        model=model,
        mpn=mpn,
        competitor_price=competitor_price,
        currency="EUR",
        product_url=url,
        match_status=match_status,
        observed_at=NOW,
        created_at=NOW,
    )
    session.add(row)
    session.flush()
    return row


def _source_url(
    session,
    product: CatalogProductRow,
    *,
    url: str,
    status: str = "active",
    url_type: str = "imported",
    source_name: str = "skroutz",
) -> SourceUrl:
    row = SourceUrl(
        catalog_product_id=product.id,
        catalog_source=product.catalog_source,
        model=product.model,
        mpn=product.mpn,
        manufacturer=product.manufacturer,
        source_name=source_name,
        source_domain=(
            "www.skroutz.gr" if source_name == "skroutz" else "www.bestprice.gr"
        ),
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


def test_source_url_summary_repository_counts_active_catalog_products_and_groups(
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        first = _catalog_product(session, model="005606")
        second = _catalog_product(session, model="123456", mpn="MPN-2")
        _catalog_product(session, model="999999", mpn="MPN-3")
        inactive = _catalog_product(session, model="OLD", active=False)
        foreign = _catalog_product(session, model="FOREIGN", catalog_source="other")
        _source_url(
            session,
            first,
            url="https://www.skroutz.gr/s/1",
            status="active",
            url_type="manual",
        )
        _source_url(
            session,
            first,
            url="https://www.bestprice.gr/item/1",
            status="needs_review",
            url_type="imported",
            source_name="bestprice",
        )
        _source_url(
            session,
            second,
            url="https://www.skroutz.gr/s/2",
            status="disabled",
            url_type="discovered",
        )
        _source_url(
            session, inactive, url="https://www.skroutz.gr/s/old", status="active"
        )
        _source_url(
            session, foreign, url="https://www.skroutz.gr/s/foreign", status="active"
        )

        summary = source_url_summary(session, "sourceCata")

    assert summary["catalog_source"] == "sourceCata"
    assert summary["catalog_product_count"] == 3
    assert summary["products_with_active_source_urls"] == 1
    assert summary["products_without_active_source_urls"] == 2
    assert summary["coverage_percent"] == 33.33
    assert summary["source_url_count"] == 3
    assert summary["by_status"] == {
        "active": 1,
        "broken": 0,
        "disabled": 1,
        "needs_review": 1,
        "redirected": 0,
    }
    assert summary["by_source_name"] == {"bestprice": 1, "skroutz": 2}
    assert summary["by_url_type"] == {"discovered": 1, "imported": 1, "manual": 1}
    assert summary["updated_at"] == NOW.isoformat()


def test_db_observation_exact_model_imports_active_and_is_idempotent(
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        product = _catalog_product(session, model="005606")
        run = _run(session)
        _observation(session, run, url="https://www.skroutz.gr/s/1#top", model="005606")

        result = import_source_urls(session, apply=True, include_artifacts=False)
        second = import_source_urls(session, apply=True, include_artifacts=False)
        rows = session.query(SourceUrl).all()

    assert result.counters["imported_count"] == 1
    assert second.counters["duplicate_count"] == 1
    assert len(rows) == 1
    assert rows[0].catalog_product_id == product.id
    assert rows[0].status == "active"
    assert rows[0].url_type == "imported"
    assert rows[0].last_success_at.replace(tzinfo=timezone.utc) == NOW
    assert rows[0].url_normalized == "https://www.skroutz.gr/s/1"


def test_db_observation_product_id_unique_mpn_imports_active(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        product = _catalog_product(session, model="CAT-1", mpn="MPN-ONLY")
        observation_product = _observation_product(session, model=None, mpn="MPN-ONLY")
        run = _run(session)
        _observation(
            session,
            run,
            url="https://www.bestprice.gr/item/1",
            model=None,
            mpn=None,
            product_id=observation_product.id,
        )

        result = import_source_urls(session, apply=True, include_artifacts=False)
        row = session.query(SourceUrl).one()

    assert result.counters["imported_count"] == 1
    assert row.catalog_product_id == product.id
    assert row.status == "active"


def test_db_observation_skips_unmatched_invalid_and_missing_identity(
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        _catalog_product(session, model="005606")
        run = _run(session)
        _observation(session, run, url="ftp://example.test/p", model="005606")
        _observation(
            session,
            run,
            url="https://example.test/no-id",
            model=None,
            mpn=None,
            match_status="unmatched",
        )

        result = import_source_urls(session, apply=True, include_artifacts=False)

    assert result.counters["invalid_url_count"] == 1
    assert result.counters["unresolved_identity_count"] == 1
    assert result.counters["skipped_count"] == 2


def test_enriched_csv_exact_model_active_mpn_needs_review_aliases_and_idempotent(
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    csv_path = tmp_path / "input_skroutz_enriched.csv"
    csv_path.write_text(
        "model,mpn,skroutz_price,skroutz_url\n"
        "005606,MPN-1,119.90,https://www.skroutz.gr/s/1\n"
        ",MPN-2,10.00,https://www.bestprice.gr/item/2\n",
        encoding="utf-8-sig",
    )
    with session_scope(database_url) as session:
        _catalog_product(session, model="005606", mpn="MPN-1")
        _catalog_product(session, model="123456", mpn="MPN-2")
        _run(session, source="skroutz", enriched_csv_path=str(csv_path))

        result = import_source_urls(session, apply=True, include_observations=False)
        second = import_source_urls(session, apply=True, include_observations=False)
        rows = sorted(session.query(SourceUrl).all(), key=lambda item: item.model)

    assert result.counters["imported_count"] == 2
    assert result.counters["active_count"] == 1
    assert result.counters["needs_review_count"] == 1
    assert second.counters["duplicate_count"] == 2
    assert [row.status for row in rows] == ["active", "needs_review"]


def test_enriched_csv_bestprice_alias_invalid_url_and_ambiguous_mpn_are_skipped(
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    csv_path = tmp_path / "input_bestprice_enriched.csv"
    csv_path.write_text(
        "mpn,bestprice_price,bestprice_url\n"
        "DUP,9.90,https://www.bestprice.gr/item/dup\n"
        "OK,8.90,notaurl\n",
        encoding="utf-8-sig",
    )
    with session_scope(database_url) as session:
        _catalog_product(session, model="A", mpn="DUP")
        _catalog_product(session, model="B", mpn="DUP")
        _catalog_product(session, model="C", mpn="OK")
        _run(session, source="bestprice", enriched_csv_path=str(csv_path))

        result = import_source_urls(session, apply=True, include_observations=False)

    assert result.counters["ambiguous_identity_count"] == 1
    assert result.counters["invalid_url_count"] == 1
    assert result.counters["imported_count"] == 0


def test_import_preserves_manual_disabled_and_reactivates_broken_only_with_success(
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        product = _catalog_product(session, model="005606")
        manual = SourceUrl(
            catalog_product_id=product.id,
            catalog_source=product.catalog_source,
            model=product.model,
            mpn=product.mpn,
            manufacturer=product.manufacturer,
            source_name="skroutz",
            source_domain="www.skroutz.gr",
            url="https://www.skroutz.gr/s/manual",
            url_normalized="https://www.skroutz.gr/s/manual",
            status="active",
            url_type="manual",
            trust_level="manual",
            added_by="tester",
            created_at=NOW,
            updated_at=NOW,
        )
        disabled = SourceUrl(
            catalog_product_id=product.id,
            catalog_source=product.catalog_source,
            model=product.model,
            mpn=product.mpn,
            manufacturer=product.manufacturer,
            source_name="skroutz",
            source_domain="www.skroutz.gr",
            url="https://www.skroutz.gr/s/disabled",
            url_normalized="https://www.skroutz.gr/s/disabled",
            status="disabled",
            url_type="imported",
            trust_level="imported",
            created_at=NOW,
            updated_at=NOW,
        )
        broken = SourceUrl(
            catalog_product_id=product.id,
            catalog_source=product.catalog_source,
            model=product.model,
            mpn=product.mpn,
            manufacturer=product.manufacturer,
            source_name="skroutz",
            source_domain="www.skroutz.gr",
            url="https://www.skroutz.gr/s/broken",
            url_normalized="https://www.skroutz.gr/s/broken",
            status="broken",
            url_type="imported",
            trust_level="imported",
            created_at=NOW,
            updated_at=NOW,
        )
        session.add_all([manual, disabled, broken])
        run = _run(session)
        _observation(session, run, url=manual.url, model="005606")
        _observation(session, run, url=disabled.url, model="005606")
        _observation(
            session,
            run,
            url=broken.url,
            model="005606",
            competitor_price=Decimal("119.90"),
        )

        import_source_urls(session, apply=True, include_artifacts=False)
        session.refresh(manual)
        session.refresh(disabled)
        session.refresh(broken)

    assert manual.url_type == "manual"
    assert manual.trust_level == "manual"
    assert manual.added_by == "tester"
    assert disabled.status == "disabled"
    assert broken.status == "active"


def test_cli_default_dry_run_and_apply_json(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        _catalog_product(session, model="005606")
        run = _run(session)
        _observation(session, run, url="https://www.skroutz.gr/s/1", model="005606")

    assert import_job_main(["--json"]) == 0
    dry_payload = json.loads(capsys.readouterr().out)
    with session_scope(database_url) as session:
        assert session.query(SourceUrl).count() == 0

    assert dry_payload["imported_count"] == 1
    assert dry_payload["candidates_found"] == 1

    assert import_job_main(["--apply", "--json"]) == 0
    apply_payload = json.loads(capsys.readouterr().out)
    with session_scope(database_url) as session:
        assert session.query(SourceUrl).count() == 1

    assert apply_payload["imported_count"] == 1
    assert "price_observations" in apply_payload["sources_processed"]
