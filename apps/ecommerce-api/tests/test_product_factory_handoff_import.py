import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models import Base  # noqa: E402
from ecommerce.db.models.catalog import CatalogProductRow  # noqa: E402
from ecommerce.db.models.source_urls import SourceUrl  # noqa: E402
from ecommerce.db.models.products import ProductSource, SourceCaptureSnapshot  # noqa: E402
from ecommerce.db.models.price_monitoring import PriceObservation  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.jobs.import_product_factory_handoff import main as handoff_job_main  # noqa: E402
from ecommerce.product_factory_handoff import import_product_factory_handoff, parse_product_factory_handoff  # noqa: E402


NOW = datetime(2026, 5, 4, 12, tzinfo=timezone.utc)
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "product_factory" / "ecommerce_source_handoff.json"


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'handoff.db'}"


def _create_schema(database_url: str) -> None:
    Base.metadata.create_all(get_engine(database_url))


def _catalog_product(
    session,
    *,
    model: str = "HANDOFF-1",
    mpn: str = "MPN-HANDOFF-1",
    active: bool = True,
) -> CatalogProductRow:
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


def _write_handoff(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "work" / str(payload.get("product", {}).get("model") or "HANDOFF-1") / "integrations"
    path.mkdir(parents=True, exist_ok=True)
    handoff_path = path / "ecommerce_source_handoff.json"
    handoff_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return handoff_path


def _fixture_payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parse_product_factory_handoff_fixture_schema_v1() -> None:
    handoff = parse_product_factory_handoff(FIXTURE)

    assert handoff.identity.model == "HANDOFF-1"
    assert handoff.identity.mpn == "MPN-HANDOFF-1"
    assert handoff.sources[0].url == "https://www.electronet.gr/product/handoff-1?utm_source=agent"
    assert handoff.sources[0].price.price == Decimal("699.00")


def test_apply_imports_active_source_url_product_source_snapshot_and_price(tmp_path: Path, monkeypatch) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    monkeypatch.setenv("ECOMMERCE_SOURCE_CAPTURE_ARTIFACT_DIR", str(tmp_path / "capture-artifacts"))

    with session_scope(database_url) as session:
        product = _catalog_product(session)
        payload = _fixture_payload()
        payload["product"]["catalog_product_id"] = product.id
        handoff_path = _write_handoff(tmp_path, payload)

        result = import_product_factory_handoff(session, file_path=handoff_path, apply=True)
        second = import_product_factory_handoff(session, file_path=handoff_path, apply=True)

        source_url = session.query(SourceUrl).one()
        product_source = session.query(ProductSource).one()
        snapshot = session.query(SourceCaptureSnapshot).one()
        observation = session.query(PriceObservation).one()

    assert result.counters["imported_count"] == 1
    assert result.counters["snapshot_count"] == 1
    assert result.counters["price_observation_count"] == 1
    assert second.counters["duplicate_count"] == 1
    assert second.counters["duplicate_snapshot_count"] == 1
    assert source_url.catalog_product_id == product.id
    assert source_url.status == "active"
    assert source_url.trust_level == "high_confidence"
    assert source_url.url_normalized == "https://www.electronet.gr/product/handoff-1"
    assert product_source.canonical_url == "https://www.electronet.gr/product/handoff-1"
    assert snapshot.capture_strategy == "product_factory_handoff_electronet"
    assert snapshot.raw_html_ref is not None
    assert observation.competitor_price == Decimal("699.00")
    assert observation.timestamp_source == "product_factory_handoff.observed_at"


def test_dry_run_reports_without_writes(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        _catalog_product(session)
        handoff_path = _write_handoff(tmp_path, _fixture_payload())

        result = import_product_factory_handoff(session, file_path=handoff_path, apply=False)

        assert result.counters["imported_count"] == 1
        assert result.counters["would_import_snapshot_count"] == 1
        assert session.query(SourceUrl).count() == 0
        assert session.query(ProductSource).count() == 0
        assert session.query(SourceCaptureSnapshot).count() == 0


def test_mpn_resolution_imports_needs_review_without_product_source(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    payload = _fixture_payload()
    payload["product"].pop("model")
    payload["sources"][0]["confidence"] = 0.99
    handoff_path = _write_handoff(tmp_path, payload)

    with session_scope(database_url) as session:
        _catalog_product(session, model="CAT-MODEL", mpn="MPN-HANDOFF-1")

        result = import_product_factory_handoff(session, file_path=handoff_path, apply=True)
        row = session.query(SourceUrl).one()

        assert result.counters["needs_review_count"] == 1
        assert row.status == "needs_review"
        assert session.query(ProductSource).count() == 0
        assert session.query(PriceObservation).count() == 0


def test_ambiguous_identity_and_invalid_url_do_not_write(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    payload = _fixture_payload()
    payload["product"].pop("model")
    payload["sources"][0]["url"] = "ftp://example.test/not-supported"
    handoff_path = _write_handoff(tmp_path, payload)

    with session_scope(database_url) as session:
        _catalog_product(session, model="A", mpn="MPN-HANDOFF-1")
        _catalog_product(session, model="B", mpn="MPN-HANDOFF-1")

        ambiguous = import_product_factory_handoff(session, file_path=handoff_path, apply=True)
        assert ambiguous.counters["ambiguous_identity_count"] == 1
        assert session.query(SourceUrl).count() == 0

    payload["product"]["model"] = "A"
    handoff_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with session_scope(database_url) as session:
        invalid = import_product_factory_handoff(session, file_path=handoff_path, apply=True)

        assert invalid.counters["invalid_url_count"] == 1
        assert session.query(SourceUrl).count() == 0


def test_cli_dry_run_and_apply_json(tmp_path: Path, monkeypatch, capsys) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        _catalog_product(session)
    handoff_path = _write_handoff(tmp_path, _fixture_payload())

    assert handoff_job_main(["--file", str(handoff_path), "--dry-run", "--json"]) == 0
    dry_payload = json.loads(capsys.readouterr().out)
    assert dry_payload["counters"]["imported_count"] == 1
    with session_scope(database_url) as session:
        assert session.query(SourceUrl).count() == 0

    assert handoff_job_main(["--file", str(handoff_path), "--apply", "--json"]) == 0
    apply_payload = json.loads(capsys.readouterr().out)
    assert apply_payload["counters"]["imported_count"] == 1
    with session_scope(database_url) as session:
        assert session.query(SourceUrl).count() == 1
