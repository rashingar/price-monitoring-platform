"""Price Monitoring run folder and input CSV creation."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ecommerce.artifacts import artifact_link_payload
from ecommerce.db.session import session_scope
from ecommerce.price_monitoring.selection import (
    PriceMonitoringSelectionRequest,
    PriceMonitoringSelectionResult,
    SelectedPriceMonitoringProduct,
    select_price_monitoring_products,
)
from ecommerce.price_monitoring.source_url_coverage import (
    attach_source_url_coverage,
    compute_source_url_coverage,
    require_active_source_url_coverage,
)

PRICE_MONITORING_RUNS_DIR = Path("output") / "ecommerce" / "monitoring" / "runs"
INPUT_COLUMNS = ["model", "mpn", "name", "price"]
SUMMARY_FILENAME = "selection_summary.json"
FETCH_RESULT_FILENAME = "fetch_result.json"
FETCH_EXECUTION_FILENAME = "fetch_execution.json"


class InvalidPriceMonitoringRunIdError(ValueError):
    """Raised when a Price Monitoring run id is malformed or unsafe."""


@dataclass(frozen=True)
class PriceMonitoringRunRecord:
    run_id: str
    status: str
    source: str
    output_dir: Path
    input_csv_path: Path
    selection_summary_path: Path
    selection_result: PriceMonitoringSelectionResult
    created_at: str


def create_price_monitoring_run(
    request: PriceMonitoringSelectionRequest,
    runs_dir: Path = PRICE_MONITORING_RUNS_DIR,
    selection_result: PriceMonitoringSelectionResult | None = None,
) -> PriceMonitoringRunRecord:
    selection_result = selection_result or select_price_monitoring_products(request)
    if selection_result.source_url_coverage is None:
        with session_scope() as session:
            coverage = compute_source_url_coverage(
                session, selection_result.items, selection_result.source
            )
        selection_result = require_active_source_url_coverage(
            selection_result, coverage
        )
    if selection_result.selected_count == 0:
        raise ValueError("No eligible products selected.")

    run_id = _make_run_id()
    created_at = _now_iso()
    output_dir = runs_dir / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    input_csv_path = output_dir / "input.csv"
    selection_summary_path = output_dir / SUMMARY_FILENAME

    write_ecommerce_input_csv(input_csv_path, selection_result.items)
    summary = _selection_summary(run_id, created_at, selection_result, input_csv_path)
    with selection_summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return PriceMonitoringRunRecord(
        run_id=run_id,
        status="selection_created",
        source=selection_result.source,
        output_dir=output_dir,
        input_csv_path=input_csv_path,
        selection_summary_path=selection_summary_path,
        selection_result=selection_result,
        created_at=created_at,
    )


def write_ecommerce_input_csv(
    path: Path, products: list[SelectedPriceMonitoringProduct]
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INPUT_COLUMNS)
        writer.writeheader()
        for product in products:
            writer.writerow(
                {
                    "model": product.model,
                    "mpn": product.mpn,
                    "name": product.name,
                    "price": _price_text(product.price),
                }
            )
    return path


def run_record_to_response(record: PriceMonitoringRunRecord) -> dict:
    selected_items = [item.to_dict() for item in record.selection_result.items]
    skipped_items = [item.to_dict() for item in record.selection_result.skipped]
    return {
        "run_id": record.run_id,
        "status": record.status,
        "source": record.source,
        "source_name": record.source,
        "source_filter": record.selection_result.source_filter,
        "created_at": record.created_at,
        "output_dir": str(record.output_dir),
        "input_csv_path": str(record.input_csv_path),
        "selection_summary_path": str(record.selection_summary_path),
        "artifacts": [
            artifact_link_payload(record.input_csv_path),
            artifact_link_payload(record.selection_summary_path),
        ],
        "selected_count": record.selection_result.selected_count,
        "skipped_count": record.selection_result.skipped_count,
        "skipped_by_reason": record.selection_result.skipped_by_reason,
        "source_url_required": record.selection_result.source_url_required,
        "source_url_coverage": (
            record.selection_result.source_url_coverage.to_dict()
            if record.selection_result.source_url_coverage is not None
            else None
        ),
        "selected_models": [item.model for item in record.selection_result.items],
        "skipped_models": [item.to_dict() for item in record.selection_result.skipped],
        "latest_fetch": None,
        "items": selected_items,
        "skipped": skipped_items,
        "selected_items": selected_items,
        "skipped_items": skipped_items,
    }


def selection_preview_to_response(
    selection_result: PriceMonitoringSelectionResult,
) -> dict:
    selected_items = [item.to_dict() for item in selection_result.items]
    skipped_items = [item.to_dict() for item in selection_result.skipped]
    return {
        "source": selection_result.source,
        "source_name": selection_result.source,
        "source_filter": selection_result.source_filter,
        "selected_count": selection_result.selected_count,
        "skipped_count": selection_result.skipped_count,
        "skipped_by_reason": selection_result.skipped_by_reason,
        "source_url_required": selection_result.source_url_required,
        "source_url_coverage": (
            selection_result.source_url_coverage.to_dict()
            if selection_result.source_url_coverage is not None
            else None
        ),
        "items": selected_items,
        "skipped": skipped_items,
        "selected_items": selected_items,
        "skipped_items": skipped_items,
    }


def list_price_monitoring_runs(
    runs_dir: Path = PRICE_MONITORING_RUNS_DIR,
) -> list[dict]:
    runs_dir = Path(runs_dir)
    if not runs_dir.exists():
        return []

    items = []
    for child in runs_dir.iterdir():
        if not child.is_dir():
            continue
        try:
            items.append(price_monitoring_run_to_api_dict(child, runs_dir))
        except InvalidPriceMonitoringRunIdError:
            continue

    items.sort(
        key=lambda item: (str(item.get("created_at", "")), str(item.get("run_id", ""))),
        reverse=True,
    )
    return items


def load_price_monitoring_run(
    run_id: str, runs_dir: Path = PRICE_MONITORING_RUNS_DIR
) -> dict:
    run_dir = resolve_price_monitoring_run_dir(run_id, runs_dir)
    if not run_dir.exists():
        raise FileNotFoundError(f"Price monitoring run folder not found: {run_dir}")
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Price monitoring run folder not found: {run_dir}")
    return price_monitoring_run_to_api_dict(run_dir, runs_dir)


def resolve_price_monitoring_run_dir(
    run_id: str,
    runs_dir: Path = PRICE_MONITORING_RUNS_DIR,
) -> Path:
    safe_run_id = validate_price_monitoring_run_id(run_id)
    root_path = Path(runs_dir)
    run_dir = root_path / safe_run_id
    root = _resolve_path(root_path)
    resolved_run_dir = _resolve_path(run_dir)
    if not _same_or_child(resolved_run_dir, root):
        raise InvalidPriceMonitoringRunIdError("Invalid run_id.")
    return run_dir


def validate_price_monitoring_run_id(run_id: str) -> str:
    value = str(run_id or "").strip()
    if not value or value in {".", ".."}:
        raise InvalidPriceMonitoringRunIdError("Invalid run_id.")
    if "/" in value or "\\" in value:
        raise InvalidPriceMonitoringRunIdError("Invalid run_id.")

    path = Path(value)
    if len(path.parts) != 1 or any(part == ".." for part in path.parts):
        raise InvalidPriceMonitoringRunIdError("Invalid run_id.")
    return value


def price_monitoring_run_to_api_dict(
    run_dir: Path,
    runs_dir: Path = PRICE_MONITORING_RUNS_DIR,
) -> dict:
    run_dir = Path(run_dir)
    safe_run_id = validate_price_monitoring_run_id(run_dir.name)
    root = _resolve_path(Path(runs_dir))
    resolved_run_dir = _resolve_path(run_dir)
    if not _same_or_child(resolved_run_dir, root):
        raise InvalidPriceMonitoringRunIdError("Invalid run_id.")

    selection_summary_path = run_dir / SUMMARY_FILENAME
    input_csv_path = run_dir / "input.csv"
    summary = _read_json_object(selection_summary_path)
    latest_fetch = _latest_fetch_payload(run_dir)

    selected_models = _string_list(summary.get("selected_models"))
    skipped_models = _list_value(summary.get("skipped_models"))
    selected_count = _int_value(summary.get("selected_count"), len(selected_models))
    skipped_count = _int_value(summary.get("skipped_count"), len(skipped_models))

    return {
        "run_id": str(summary.get("run_id") or safe_run_id),
        "status": str(summary.get("status") or "selection_created"),
        "source": str(
            summary.get("source") or (latest_fetch or {}).get("source") or ""
        ),
        "source_name": str(
            summary.get("source_name")
            or summary.get("source")
            or (latest_fetch or {}).get("source")
            or ""
        ),
        "source_filter": summary.get("source_filter"),
        "created_at": str(
            summary.get("created_at") or _created_at_from_run_dir(run_dir)
        ),
        "output_dir": str(run_dir),
        "input_csv_path": str(summary.get("input_csv_path") or input_csv_path),
        "selection_summary_path": str(selection_summary_path),
        "selected_count": selected_count,
        "skipped_count": skipped_count,
        "skipped_by_reason": _dict_value(summary.get("skipped_by_reason")),
        "selected_models": selected_models,
        "skipped_models": skipped_models,
        "latest_fetch": latest_fetch,
        "artifacts": _run_artifacts(run_dir),
    }


def _selection_summary(
    run_id: str,
    created_at: str,
    selection_result: PriceMonitoringSelectionResult,
    input_csv_path: Path,
) -> dict:
    selected_items = [item.to_dict() for item in selection_result.items]
    return {
        "run_id": run_id,
        "source": selection_result.source,
        "source_name": selection_result.source,
        "source_filter": selection_result.source_filter,
        "created_at": created_at,
        "filters": selection_result.filters.to_dict(),
        "selected_count": selection_result.selected_count,
        "skipped_count": selection_result.skipped_count,
        "skipped_by_reason": selection_result.skipped_by_reason,
        "source_url_required": selection_result.source_url_required,
        "source_url_coverage": (
            selection_result.source_url_coverage.to_dict()
            if selection_result.source_url_coverage is not None
            else None
        ),
        "input_csv_path": str(input_csv_path),
        "selected_models": [item.model for item in selection_result.items],
        "selected_items": selected_items,
        "items": selected_items,
        "skipped_models": [asdict(item) for item in selection_result.skipped],
    }


def _latest_fetch_payload(run_dir: Path) -> dict | None:
    execution_path = run_dir / FETCH_EXECUTION_FILENAME
    execution_payload = _read_json_object(execution_path)
    if execution_payload:
        return {
            "execution_id": str(execution_payload.get("execution_id") or ""),
            "execution_type": str(execution_payload.get("execution_type") or "fetch"),
            "status": _normalize_fetch_status(
                str(execution_payload.get("status") or "")
            ),
            "source": str(execution_payload.get("source") or ""),
            "queued_at": str(execution_payload.get("queued_at") or ""),
            "started_at": str(execution_payload.get("started_at") or ""),
            "completed_at": str(execution_payload.get("completed_at") or ""),
            "cancelled_at": str(execution_payload.get("cancelled_at") or ""),
            "enriched_csv_path": str(execution_payload.get("enriched_csv_path") or ""),
            "fetch_summary_path": str(
                execution_payload.get("fetch_summary_path") or ""
            ),
            "fetch_result_path": str(
                execution_payload.get("fetch_result_path")
                or run_dir / FETCH_RESULT_FILENAME
            ),
            "error": str(execution_payload.get("error") or ""),
            "fetch_input_mode": str(
                execution_payload.get("fetch_input_mode") or "source_urls"
            ),
            "source_url_capture_used": bool(
                execution_payload.get("source_url_capture_used", False)
            ),
            "source_url_capture_status": str(
                execution_payload.get("source_url_capture_status") or "not_run"
            ),
            "source_url_capture_selected_count": _int_value(
                execution_payload.get("source_url_capture_selected_count"), 0
            ),
            "source_url_capture_succeeded_count": _int_value(
                execution_payload.get("source_url_capture_succeeded_count"), 0
            ),
            "source_url_capture_failed_count": _int_value(
                execution_payload.get("source_url_capture_failed_count"), 0
            ),
            "source_url_capture_result_path": str(
                execution_payload.get("source_url_capture_result_path") or ""
            ),
            "source_url_capture_warnings": _list_value(
                execution_payload.get("source_url_capture_warnings")
            ),
            "source_url_capture_run_id": str(
                execution_payload.get("source_url_capture_run_id") or ""
            ),
            "observation_batch_id": str(
                execution_payload.get("observation_batch_id") or ""
            ),
            "worker_id": str(execution_payload.get("worker_id") or ""),
            "process_id": execution_payload.get("process_id"),
            "thread_name": str(execution_payload.get("thread_name") or ""),
            "heartbeat_at": str(execution_payload.get("heartbeat_at") or ""),
            "exit_code": execution_payload.get("exit_code"),
            "termination_mode": str(execution_payload.get("termination_mode") or ""),
            "terminate_sent_at": str(execution_payload.get("terminate_sent_at") or ""),
            "kill_sent_at": str(execution_payload.get("kill_sent_at") or ""),
            "killed_at": str(execution_payload.get("killed_at") or ""),
        }

    result_path = run_dir / FETCH_RESULT_FILENAME
    payload = _read_json_object(result_path)
    if not payload:
        return None
    return {
        "execution_id": "",
        "status": _normalize_fetch_status(str(payload.get("status") or "")),
        "source": str(payload.get("source") or ""),
        "queued_at": str(payload.get("started_at") or ""),
        "started_at": str(payload.get("started_at") or ""),
        "completed_at": str(payload.get("completed_at") or ""),
        "cancelled_at": "",
        "enriched_csv_path": str(payload.get("enriched_csv_path") or ""),
        "fetch_summary_path": str(payload.get("fetch_summary_path") or ""),
        "fetch_result_path": str(payload.get("fetch_result_path") or result_path),
        "error": str(payload.get("error") or ""),
        "fetch_input_mode": str(payload.get("fetch_input_mode") or "source_urls"),
        "source_url_capture_used": bool(payload.get("source_url_capture_used", False)),
        "source_url_capture_status": str(
            payload.get("source_url_capture_status") or "not_run"
        ),
        "source_url_capture_selected_count": _int_value(
            payload.get("source_url_capture_selected_count"), 0
        ),
        "source_url_capture_succeeded_count": _int_value(
            payload.get("source_url_capture_succeeded_count"), 0
        ),
        "source_url_capture_failed_count": _int_value(
            payload.get("source_url_capture_failed_count"), 0
        ),
        "source_url_capture_result_path": str(
            payload.get("source_url_capture_result_path") or ""
        ),
        "source_url_capture_warnings": _list_value(
            payload.get("source_url_capture_warnings")
        ),
        "source_url_capture_run_id": str(
            payload.get("source_url_capture_run_id") or ""
        ),
        "observation_batch_id": str(payload.get("observation_batch_id") or ""),
    }


def _run_artifacts(run_dir: Path) -> list[dict]:
    artifacts = []
    if not run_dir.exists():
        return artifacts
    for child in sorted(run_dir.iterdir(), key=lambda path: path.name.casefold()):
        if child.is_file():
            artifacts.append(artifact_link_payload(child))
    return artifacts


def _read_json_object(path: Path) -> dict:
    if not path.exists() or not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _created_at_from_run_dir(run_dir: Path) -> str:
    parsed = _created_at_from_run_id(run_dir.name)
    if parsed:
        return parsed
    try:
        timestamp = run_dir.stat().st_mtime
    except OSError:
        timestamp = 0
    return (
        datetime.fromtimestamp(timestamp, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )


def _created_at_from_run_id(run_id: str) -> str:
    prefix = run_id[:15]
    try:
        parsed = datetime.strptime(prefix, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return ""
    return parsed.replace(microsecond=0).isoformat()


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _list_value(value: object) -> list:
    return value if isinstance(value, list) else []


def _dict_value(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _int_value(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _normalize_fetch_status(status: str) -> str:
    if status == "fetch_completed":
        return "succeeded"
    if status == "fetch_failed":
        return "failed"
    return status


def _resolve_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _same_or_child(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _make_run_id() -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _price_text(price: float) -> str:
    return f"{price:.2f}"
