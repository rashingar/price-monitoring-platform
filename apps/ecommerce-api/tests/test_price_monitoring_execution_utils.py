from __future__ import annotations

import sys
from pathlib import Path

from ecommerce.price_monitoring import fetch_execution


def install_fake_execution_child(
    monkeypatch,
    tmp_path: Path,
    *,
    mode: str = "success",
    persist: bool = False,
    prices: list[str] | None = None,
) -> None:
    prices_path = tmp_path / "fake_child_prices.txt"
    prices_path.write_text("\n".join(prices or ["119.90"]) + "\n", encoding="utf-8")
    script = tmp_path / f"fake_price_monitoring_child_{mode}_{int(persist)}.py"
    script.write_text(
        """
import argparse
import json
import sys
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path

from ecommerce.db.models import PriceObservation, Product
from ecommerce.db.session import session_scope
from ecommerce.price_monitoring.fetch_execution import evaluate_alerts_after_persistence
from ecommerce.price_monitoring.fetch_run import load_price_monitoring_fetch_result
from ecommerce.price_monitoring.persistence import persist_fetch_result_if_configured

parser = argparse.ArgumentParser()
parser.add_argument("--run-id", required=True)
parser.add_argument("--execution-id", required=True)
parser.add_argument("--execution-type", required=True)
args = parser.parse_args()

mode = __MODE__
persist = __PERSIST__
prices_path = Path(__PRICES_PATH__)
run_dir = Path("output") / "ecommerce" / "monitoring" / "runs" / args.run_id
execution_path = run_dir / "fetch_executions" / f"{args.execution_id}.json"
alias_path = run_dir / "fetch_execution.json"

def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def load():
    return json.loads(execution_path.read_text(encoding="utf-8"))

def save(payload):
    text = json.dumps(payload, indent=2) + "\\n"
    execution_path.write_text(text, encoding="utf-8")
    alias_path.write_text(text, encoding="utf-8")

def next_price():
    values = [line.strip() for line in prices_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    value = values[0] if values else "119.90"
    prices_path.write_text("\\n".join(values[1:] or [value]) + "\\n", encoding="utf-8")
    return value

payload = load()
payload["heartbeat_at"] = now()
save(payload)
print("fake child stdout")
print("fake child stderr", file=sys.stderr)

if mode == "fail":
    payload.update({"status": "failed", "completed_at": now(), "error": "Fetch command failed", "exit_code": 1})
    save(payload)
    sys.exit(1)

competitor_price = next_price()
fetch_result_path = run_dir / "fetch_result.json"
source_capture_result_path = run_dir / "source_url_capture_result.json"
source_capture_result_path.write_text(json.dumps({
    "status": "completed",
    "used_source_urls": True,
    "source": "skroutz",
    "vendor": "skroutz",
    "selected_catalog_product_count": 1,
    "selected_source_url_count": 1,
    "selected_product_source_count": 1,
    "succeeded_count": 1,
    "failed_count": 0,
    "warnings": [],
    "items": [{"product_source_id": 1, "status": "success"}],
    "source_urls": [{"source_name": "skroutz", "status": "active", "url": "https://example.test/p"}],
    "result_path": str(source_capture_result_path),
    "artifact_path": str(source_capture_result_path)
}, indent=2), encoding="utf-8")
fetch_result_path.write_text(json.dumps({
    "run_id": args.run_id,
    "source": "skroutz",
    "source_filter": "skroutz",
    "status": "fetch_completed",
    "started_at": payload.get("started_at") or now(),
    "completed_at": now(),
    "input_csv_path": str(run_dir / "input.csv"),
    "enriched_csv_path": "",
    "fetch_summary_path": "",
    "fetch_result_path": str(fetch_result_path),
    "stdout": "",
    "warnings": [],
    "error": "",
    "fetch_input_mode": "source_urls",
    "legacy_marketplace_fetch_used": False,
    "source_url_capture_used": True,
    "source_url_capture_status": "completed",
    "source_url_capture_selected_count": 1,
    "source_url_capture_succeeded_count": 1,
    "source_url_capture_failed_count": 0,
    "source_url_capture_result_path": str(source_capture_result_path),
    "source_url_capture_warnings": []
}, indent=2), encoding="utf-8")

payload.update({
    "status": "succeeded",
    "completed_at": now(),
    "enriched_csv_path": "",
    "fetch_summary_path": "",
    "fetch_result_path": str(fetch_result_path),
    "fetch_input_mode": "source_urls",
    "legacy_marketplace_fetch_used": False,
    "source_url_capture_used": True,
    "source_url_capture_status": "completed",
    "source_url_capture_selected_count": 1,
    "source_url_capture_succeeded_count": 1,
    "source_url_capture_failed_count": 0,
    "source_url_capture_result_path": str(source_capture_result_path),
    "source_url_capture_warnings": [],
    "persistence_status": "not_configured",
    "persistence_warnings": [],
    "alert_evaluation_status": "not_configured",
    "alert_event_count": 0,
    "alert_duplicate_count": 0,
    "alert_warnings": [],
    "exit_code": 0,
    "error": "",
})

if persist:
    with session_scope() as session:
        product = session.query(Product).filter(Product.catalog_source == "sourceCata", Product.model == "005606").first()
        session.add(PriceObservation(
            run_id=args.run_id,
            catalog_source="sourceCata",
            source="skroutz",
            product_id=product.id if product is not None else None,
            model="005606",
            mpn="MPN-1",
            product_name="Product One",
            competitor_name="",
            competitor_price=Decimal(str(competitor_price)),
            currency="EUR",
            own_price=Decimal("123.45"),
            price_delta=Decimal("123.45") - Decimal(str(competitor_price)),
            raw_observation={"source": "fake_source_url_capture"},
            matched_by="model",
            match_status="matched",
            observed_at=datetime(2026, 4, 28, 12, tzinfo=timezone.utc),
            created_at=datetime.now(timezone.utc).replace(microsecond=0),
        ))
    result = load_price_monitoring_fetch_result(run_dir)
    persistence = persist_fetch_result_if_configured(result, trigger_type="manual")
    alert_status, alert_count, duplicate_count, alert_warnings = evaluate_alerts_after_persistence(
        result.run_id,
        persistence_status=persistence.persistence_status,
    )
    payload.update({
        "observation_count": persistence.observation_count,
        "replaced_observation_count": persistence.replaced_observation_count,
        "catalog_snapshot_count": persistence.catalog_snapshot_count,
        "matched_observation_count": persistence.matched_observation_count,
        "unmatched_observation_count": persistence.unmatched_observation_count,
        "was_refetch": persistence.was_refetch,
        "fetch_attempt": persistence.fetch_attempt,
        "persistence_status": persistence.persistence_status,
        "persistence_warnings": persistence.warnings,
        "alert_evaluation_status": alert_status,
        "alert_event_count": alert_count,
        "alert_duplicate_count": duplicate_count,
        "alert_warnings": alert_warnings,
    })

save(payload)
sys.exit(0)
""".replace("__MODE__", repr(mode))
        .replace("__PERSIST__", repr(bool(persist)))
        .replace("__PRICES_PATH__", repr(str(prices_path))),
        encoding="utf-8",
    )

    def command(run_id: str, execution_id: str, execution_type: str) -> list[str]:
        return [
            sys.executable,
            str(script),
            "--run-id",
            run_id,
            "--execution-id",
            execution_id,
            "--execution-type",
            execution_type,
        ]

    monkeypatch.setattr(fetch_execution, "build_execution_command", command)
