import json
import sys
from datetime import timezone
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pricefetcher.db.models import Base, PriceObservation, ProductSource, SourceCaptureSnapshot  # noqa: E402
from pricefetcher.db.session import get_engine, session_scope  # noqa: E402
from pricefetcher.source_capture.product_agent_import import import_product_agent_artifacts  # noqa: E402


def _database_url(tmp_path: Path) -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'product-agent-import.db'}"
    Base.metadata.create_all(get_engine(database_url))
    return database_url


def _write_product_agent_artifact(
    root: Path,
    *,
    model: str = "000001",
    url: str = "https://www.electronet.gr/product/example",
    source: str = "electronet",
    price_value: object = 699.0,
    price_text: str = "699,00 €",
    confidence: float = 0.99,
    scope_ok: bool = True,
    scraped_at: str = "2026-04-03T17:43:54+00:00",
) -> Path:
    scrape_dir = root / model / "scrape"
    scrape_dir.mkdir(parents=True)
    raw_html_path = scrape_dir / f"{model}.raw.html"
    raw_html_path.write_text(f"<html><title>{model}</title><span>{price_text}</span></html>", encoding="utf-8")
    source_payload = {
        "source_name": source,
        "page_type": "product",
        "url": url,
        "canonical_url": url,
        "brand": "Brand",
        "name": f"Product {model}",
        "price_text": price_text,
        "price_value": price_value,
        "delivery_text": "Διαθέσιμο",
        "raw_html_path": str(raw_html_path),
        "scraped_at": scraped_at,
        "mpn": "MPN-1",
    }
    report_payload = {
        "input": {"model": model, "url": url},
        "source": source,
        "fetch_mode": "httpx",
        "source_resolution": {"requested_url": url, "resolved_url": url},
        "url_scope_validation": {"ok": scope_ok, "reason": "test"},
        "critical_extractors": {"price": "dom:.price"},
        "field_diagnostics": {
            "price": {
                "confidence": confidence,
                "selected_strategy": "dom:.price",
                "value_present": True,
            }
        },
        "missing_fields": [],
        "critical_missing": [],
        "warnings": [],
    }
    source_path = scrape_dir / f"{model}.source.json"
    source_path.write_text(json.dumps(source_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (scrape_dir / f"{model}.report.json").write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return source_path


def test_product_agent_artifact_import_preserves_raw_snapshot_and_reliable_price(tmp_path: Path, monkeypatch) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv("PRICEFETCHER_SOURCE_CAPTURE_ARTIFACT_DIR", str(tmp_path / "capture-artifacts"))
    root = tmp_path / "product-agent-work"
    _write_product_agent_artifact(root)

    with session_scope(database_url) as session:
        result = import_product_agent_artifacts(session, artifact_root=root, apply=True)

        assert result.counters["artifacts_discovered"] == 1
        assert result.counters["imported_snapshot_count"] == 1
        assert result.counters["price_observation_count"] == 1
        source = session.query(ProductSource).one()
        snapshot = session.query(SourceCaptureSnapshot).one()
        observation = session.query(PriceObservation).one()

        assert source.canonical_url == "https://www.electronet.gr/product/example"
        assert source.last_fetch_status == "success"
        assert snapshot.raw_html_ref is not None
        assert Path(snapshot.raw_html_ref).read_text(encoding="utf-8").startswith("<html>")
        assert len(str(snapshot.raw_html_ref)) < 300
        assert snapshot.response_body_json["source"]["price_value"] == 699.0
        assert snapshot.imported_at is not None
        assert observation.competitor_price == Decimal("699.00")
        assert observation.timestamp_source == "product_agent.source.scraped_at"
        assert observation.timestamp_quality == "exact"
        assert observation.observed_at.replace(tzinfo=timezone.utc).isoformat() == "2026-04-03T17:43:54+00:00"


def test_product_agent_artifact_import_keeps_unreliable_price_out_of_observations(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    root = tmp_path / "product-agent-work"
    _write_product_agent_artifact(root, model="000002", confidence=0.3)

    with session_scope(database_url) as session:
        result = import_product_agent_artifacts(session, artifact_root=root, apply=True)

        assert result.counters["imported_snapshot_count"] == 1
        assert result.counters["unreliable_price_count"] == 1
        assert session.query(SourceCaptureSnapshot).count() == 1
        assert session.query(PriceObservation).count() == 0
        snapshot = session.query(SourceCaptureSnapshot).one()
        assert "PRICE_CONFIDENCE_LOW" in snapshot.data_quality_flags
        assert "PRICE_UNRELIABLE" in snapshot.data_quality_flags


def test_product_agent_artifact_import_is_idempotent_by_artifact_and_content_hash(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    root = tmp_path / "product-agent-work"
    _write_product_agent_artifact(root, model="000003")

    with session_scope(database_url) as session:
        first = import_product_agent_artifacts(session, artifact_root=root, apply=True)
        second = import_product_agent_artifacts(session, artifact_root=root, apply=True)

        assert first.counters["imported_snapshot_count"] == 1
        assert second.counters["duplicate_snapshot_count"] == 1
        assert session.query(SourceCaptureSnapshot).count() == 1
        assert session.query(PriceObservation).count() == 1


def test_product_agent_artifact_import_dry_run_does_not_write_rows(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    root = tmp_path / "product-agent-work"
    _write_product_agent_artifact(root, model="000004")

    with session_scope(database_url) as session:
        result = import_product_agent_artifacts(session, artifact_root=root, apply=False)

        assert result.counters["would_import_snapshot_count"] == 1
        assert result.counters["would_import_price_observation_count"] == 1
        assert session.query(ProductSource).count() == 0
        assert session.query(SourceCaptureSnapshot).count() == 0
        assert session.query(PriceObservation).count() == 0
