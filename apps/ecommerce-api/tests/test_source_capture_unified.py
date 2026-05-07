import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models import Base, CatalogProductRow, PriceObservation, ProductSource, SourceCaptureSnapshot  # noqa: E402
from ecommerce.db.product_source_repository import create_product_from_source_urls  # noqa: E402
from ecommerce.db.source_url_repository import create_or_update_imported_source_url  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.price_monitoring.fetch_run import run_price_monitoring_fetch  # noqa: E402
from ecommerce.source_capture.scheduled import capture_due_product_sources  # noqa: E402
from ecommerce.source_capture.types import CaptureResult, CaptureSnapshotPayload, ParsedOfferObservation, ParsedPriceObservation  # noqa: E402


NOW = datetime(2026, 5, 3, tzinfo=timezone.utc)


def _database_url(tmp_path: Path) -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'capture-runtime.db'}"
    Base.metadata.create_all(get_engine(database_url))
    return database_url


def _catalog_product(session, *, model: str, mpn: str) -> CatalogProductRow:
    row = CatalogProductRow(
        catalog_source="sourceCata",
        model=model,
        mpn=mpn,
        name="Source Product",
        category="",
        raw_category="",
        manufacturer="Brand",
        imported_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(row)
    session.flush()
    return row


def test_raw_capture_text_is_preserved_as_full_artifact(tmp_path: Path, monkeypatch) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_SOURCE_CAPTURE_ARTIFACT_DIR", str(tmp_path / "capture-artifacts"))
    raw_html = "<html>" + ("x" * 150_000) + "</html>"

    def raw_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
        return CaptureResult(
            vendor_slug=vendor_slug or "electronet",
            status="success",
            snapshot=CaptureSnapshotPayload(
                capture_strategy="raw-artifact-test",
                page_url=url,
                raw_html=raw_html,
                captured_at=NOW,
                fetched_at=NOW,
                parsed_at=NOW,
            ),
        )

    with session_scope(database_url) as session:
        create_product_from_source_urls(
            session,
            model="RAW-1",
            source_urls=["https://www.electronet.gr/p/raw"],
            capture_fn=raw_capture,
        )
        snapshot = session.query(SourceCaptureSnapshot).one()

    assert snapshot.raw_html_ref is not None
    assert len(snapshot.raw_html_ref) < 300
    assert Path(snapshot.raw_html_ref).read_text(encoding="utf-8") == raw_html


def test_scheduled_capture_refreshes_due_product_sources(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)

    with session_scope(database_url) as session:
        create_product_from_source_urls(
            session,
            model="SCHEDULED-1",
            source_urls=["https://www.electronet.gr/p/1"],
            capture=False,
        )

    def fake_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
        return CaptureResult(
            vendor_slug=vendor_slug or "electronet",
            status="success",
            snapshot=CaptureSnapshotPayload(capture_strategy="scheduled-test", page_url=url, captured_at=NOW, fetched_at=NOW, parsed_at=NOW),
            price_observations=(ParsedPriceObservation(price=Decimal("299.00"), availability="available"),),
        )

    with session_scope(database_url) as session:
        summary = capture_due_product_sources(session, refresh_after_minutes=360, capture_fn=fake_capture)

        assert summary.selected_count == 1
        assert summary.succeeded_count == 1
        assert summary.failed_count == 0
        assert session.query(PriceObservation).count() == 1
        source = session.query(ProductSource).one()
        assert source.last_fetch_status == "success"
        assert source.last_capture_strategy == "scheduled-test"


def test_price_monitoring_fetch_result_reports_source_url_capture_usage(tmp_path: Path, monkeypatch) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    (run_dir / "input.csv").write_text("model,mpn,name,price\nRUN-SRC-5,MPN-RUN-SRC-5,Source Product,100.00\n", encoding="utf-8")

    with session_scope(database_url) as session:
        catalog_product = _catalog_product(session, model="RUN-SRC-5", mpn="MPN-RUN-SRC-5")
        catalog_product_id = catalog_product.id
        create_or_update_imported_source_url(
            session,
            catalog_product_id=catalog_product_id,
            url="https://www.skroutz.gr/s/780/result-fields.html",
            source_name="skroutz",
            trust_level="high_confidence",
            status="active",
        )
    (run_dir / "selection_summary.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "source": "skroutz",
                "selected_items": [{"model": "RUN-SRC-5", "catalog_product_id": catalog_product_id}],
            }
        ),
        encoding="utf-8",
    )

    def fake_capture(url: str, *, vendor_slug: str | None = None) -> CaptureResult:
        return CaptureResult(
            vendor_slug=vendor_slug or "skroutz",
            status="success",
            snapshot=CaptureSnapshotPayload(capture_strategy="fetch-result-test", page_url=url, captured_at=NOW, fetched_at=NOW, parsed_at=NOW),
            offer_observations=(ParsedOfferObservation(seller_name="Store A", price=Decimal("88.00")),),
        )

    result = run_price_monitoring_fetch(
        run_dir,
        source="skroutz",
        source_capture_fn=fake_capture,
    )

    assert result.fetch_input_mode == "source_urls"
    assert result.source_url_capture_used is True
    assert result.source_url_capture_status == "completed"
    assert result.source_url_capture_selected_count == 1
    assert result.source_url_capture_succeeded_count == 1
    assert result.source_url_capture_result_path == run_dir / "source_url_capture_result.json"
    payload = json.loads((run_dir / "fetch_result.json").read_text(encoding="utf-8"))
    assert payload["source_url_capture_used"] is True
    assert payload["fetch_input_mode"] == "source_urls"
