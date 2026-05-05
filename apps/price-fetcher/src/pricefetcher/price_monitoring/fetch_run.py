"""Execute live fetch for an existing Price Monitoring run folder."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pricefetcher.vendor_sources.capture import (
    SourceUrlCaptureRunResult,
    capture_selected_source_urls_for_run,
)

FETCH_RESULT_FILENAME = "fetch_result.json"

SourceCaptureRunner = Callable[..., Any]


class PriceMonitoringFetchError(RuntimeError):
    """Raised when live fetch execution fails for a Price Monitoring run."""

    def __init__(self, message: str, result: "PriceMonitoringFetchResult | None" = None) -> None:
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class PriceMonitoringFetchResult:
    run_id: str
    source: str
    status: str
    started_at: str
    completed_at: str
    input_csv_path: Path
    enriched_csv_path: Path | None
    fetch_summary_path: Path | None
    fetch_result_path: Path
    stdout: str
    warnings: list[str]
    error: str
    source_filter: str | None = None
    fetch_input_mode: str = "source_urls"
    legacy_marketplace_fetch_used: bool = False
    source_url_capture_used: bool = False
    source_url_capture_status: str = "not_run"
    source_url_capture_selected_count: int = 0
    source_url_capture_succeeded_count: int = 0
    source_url_capture_failed_count: int = 0
    source_url_capture_result_path: Path | None = None
    source_url_capture_warnings: list[str] | None = None
    source_url_capture_run_id: str = ""
    observation_batch_id: str = ""

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["input_csv_path"] = str(self.input_csv_path)
        payload["enriched_csv_path"] = str(self.enriched_csv_path) if self.enriched_csv_path is not None else ""
        payload["fetch_summary_path"] = str(self.fetch_summary_path) if self.fetch_summary_path is not None else ""
        payload["fetch_result_path"] = str(self.fetch_result_path)
        payload["source_url_capture_result_path"] = (
            str(self.source_url_capture_result_path) if self.source_url_capture_result_path is not None else ""
        )
        payload["source_url_capture_warnings"] = list(self.source_url_capture_warnings or [])
        return payload


def run_price_monitoring_fetch(
    run_dir: Path,
    source: str | None = None,
    catalog_url: str | None = None,
    *,
    source_capture_fn: SourceCaptureRunner | None = None,
    write_result: bool = True,
) -> PriceMonitoringFetchResult:
    """Run Vendor Sources capture for an existing Price Monitoring run."""

    run_dir = Path(run_dir)
    if not run_dir.exists():
        raise FileNotFoundError(f"Price monitoring run folder not found: {run_dir}")

    input_csv_path = run_dir / "input.csv"
    if not input_csv_path.exists():
        raise FileNotFoundError(f"Price monitoring input.csv not found: {input_csv_path}")

    resolved_source = resolve_price_monitoring_fetch_source(run_dir, source)
    fetch_result_path = run_dir / FETCH_RESULT_FILENAME
    started_at = _now_iso()
    del catalog_url
    source_capture_result = _run_source_url_capture(
        run_dir,
        resolved_source,
        source_capture_fn=source_capture_fn,
        write_result=True,
    )
    source_capture_warnings = list(source_capture_result.warnings)
    if source_capture_result.selected_source_url_count <= 0:
        completed_at = _now_iso()
        error = (
            "missing_active_source_url: add active source URLs in Vendor Sources "
            "before running Price Monitoring fetch."
        )
        result = PriceMonitoringFetchResult(
            run_id=run_dir.name,
            source=resolved_source,
            status="fetch_failed",
            started_at=started_at,
            completed_at=completed_at,
            input_csv_path=input_csv_path,
            enriched_csv_path=None,
            fetch_summary_path=None,
            fetch_result_path=fetch_result_path,
            stdout="",
            warnings=source_capture_warnings,
            error=error,
            source_filter=_source_filter(resolved_source),
            **_source_capture_result_fields(source_capture_result),
        )
        if write_result:
            write_price_monitoring_fetch_result(fetch_result_path, result)
        raise PriceMonitoringFetchError(error, result=result)

    completed_at = _now_iso()
    result = PriceMonitoringFetchResult(
        run_id=run_dir.name,
        source=resolved_source,
        status="fetch_completed",
        started_at=started_at,
        completed_at=completed_at,
        input_csv_path=input_csv_path,
        enriched_csv_path=None,
        fetch_summary_path=None,
        fetch_result_path=fetch_result_path,
        stdout="",
        warnings=source_capture_warnings,
        error="",
        source_filter=_source_filter(resolved_source),
        **_source_capture_result_fields(source_capture_result),
    )
    if write_result:
        write_price_monitoring_fetch_result(fetch_result_path, result)
    return result


def load_price_monitoring_fetch_result(run_dir: Path) -> PriceMonitoringFetchResult:
    run_dir = Path(run_dir)
    result_path = run_dir / FETCH_RESULT_FILENAME
    if not result_path.exists():
        raise FileNotFoundError(f"Price monitoring fetch result not found: {result_path}")

    with result_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return PriceMonitoringFetchResult(
        run_id=str(payload.get("run_id", run_dir.name)),
        source=str(payload.get("source", "")),
        status=str(payload.get("status", "")),
        started_at=str(payload.get("started_at", "")),
        completed_at=str(payload.get("completed_at", "")),
        input_csv_path=Path(str(payload.get("input_csv_path", run_dir / "input.csv"))),
        enriched_csv_path=_path_or_none(payload.get("enriched_csv_path")),
        fetch_summary_path=_path_or_none(payload.get("fetch_summary_path")),
        fetch_result_path=Path(str(payload.get("fetch_result_path", result_path))),
        stdout=str(payload.get("stdout", "")),
        warnings=[str(item) for item in payload.get("warnings", [])],
        error=str(payload.get("error", "")),
        source_filter=_source_filter(str(payload.get("source_filter") or payload.get("source") or "")),
        fetch_input_mode=str(payload.get("fetch_input_mode") or "source_urls"),
        legacy_marketplace_fetch_used=bool(payload.get("legacy_marketplace_fetch_used", False)),
        source_url_capture_used=bool(payload.get("source_url_capture_used", False)),
        source_url_capture_status=str(payload.get("source_url_capture_status") or "not_run"),
        source_url_capture_selected_count=_int_value(payload.get("source_url_capture_selected_count")),
        source_url_capture_succeeded_count=_int_value(payload.get("source_url_capture_succeeded_count")),
        source_url_capture_failed_count=_int_value(payload.get("source_url_capture_failed_count")),
        source_url_capture_result_path=_path_or_none(payload.get("source_url_capture_result_path")),
        source_url_capture_warnings=[str(item) for item in _list_value(payload.get("source_url_capture_warnings"))],
        source_url_capture_run_id=str(payload.get("source_url_capture_run_id") or ""),
        observation_batch_id=str(payload.get("observation_batch_id") or payload.get("source_url_capture_observation_batch_id") or ""),
    )


def resolve_price_monitoring_fetch_source(run_dir: Path, explicit_source: str | None) -> str:
    source = _optional_text(explicit_source)
    if source:
        return _validate_source(source)

    summary_path = run_dir / "selection_summary.json"
    if not summary_path.exists():
        raise ValueError("Price Monitoring requires one source/vendor in selection_summary.json before fetch.")

    try:
        with summary_path.open("r", encoding="utf-8-sig") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError("selection_summary.json is malformed JSON") from exc

    return _validate_source(str(payload.get("source_filter") or payload.get("source_name") or payload.get("source") or ""))


def _validate_source(source: str) -> str:
    normalized = _optional_text(source).lower()
    if not normalized or normalized == "all":
        raise ValueError("Price Monitoring requires exactly one source/vendor; source=all is not allowed.")
    return normalized


def write_price_monitoring_fetch_result(path: Path, result: PriceMonitoringFetchResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        f.write("\n")
    _replace_with_retry(tmp_path, path)


def _safe_error_message(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return "Price monitoring fetch failed."
    return message.splitlines()[0][:500]


def _optional_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _path_or_none(value: object) -> Path | None:
    text = _optional_text(value)
    return Path(text) if text else None


def _run_source_url_capture(
    run_dir: Path,
    source: str,
    *,
    source_capture_fn: SourceCaptureRunner | None,
    write_result: bool,
) -> SourceUrlCaptureRunResult:
    capture_source = _source_filter(source) or ""
    try:
        return capture_selected_source_urls_for_run(
            run_dir,
            capture_source,
            capture_fn=source_capture_fn,
            write_result=write_result,
        )
    except Exception as exc:
        from pricefetcher.vendor_sources.capture import SourceUrlCaptureRunResult

        warning = f"Source URL capture failed: {_safe_error_message(exc)}"
        return SourceUrlCaptureRunResult(
            status="failed",
            used_source_urls=False,
            source=capture_source,
            selected_catalog_product_count=0,
            selected_source_url_count=0,
            selected_product_source_count=0,
            succeeded_count=0,
            failed_count=0,
            warnings=[warning],
            items=[],
            source_urls=[],
            result_path=run_dir / "source_url_capture_result.json",
        )


def _source_capture_result_fields(result: SourceUrlCaptureRunResult) -> dict[str, object]:
    return {
        "fetch_input_mode": "source_urls",
        "legacy_marketplace_fetch_used": False,
        "source_url_capture_used": result.selected_source_url_count > 0,
        "source_url_capture_status": result.status,
        "source_url_capture_selected_count": result.selected_source_url_count,
        "source_url_capture_succeeded_count": result.succeeded_count,
        "source_url_capture_failed_count": result.failed_count,
        "source_url_capture_result_path": result.result_path,
        "source_url_capture_warnings": list(result.warnings),
        "source_url_capture_run_id": result.run_id,
        "observation_batch_id": result.observation_batch_id,
    }


def _source_filter(source: str | None) -> str | None:
    text = _optional_text(source).lower()
    if not text or text == "all":
        raise ValueError("Price Monitoring requires exactly one source/vendor; source=all is not allowed.")
    return text


def _list_value(value: object) -> list:
    return value if isinstance(value, list) else []


def _int_value(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _replace_with_retry(source: Path, target: Path) -> None:
    for attempt in range(5):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.02)
