"""Payload models for Vendor Sources capture workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

SOURCE_URL_CAPTURE_RESULT_FILENAME = "source_url_capture_result.json"
VENDOR_SOURCE_CAPTURE_RESULT_FILENAME = "vendor_source_capture_result.json"
VENDOR_SOURCE_CAPTURE_RUNS_DIR = Path("output") / "vendor_sources" / "captures" / "runs"


@dataclass(frozen=True)
class SourceUrlCaptureRunResult:
    status: str
    used_source_urls: bool
    source: str
    selected_catalog_product_count: int
    selected_source_url_count: int
    selected_product_source_count: int
    succeeded_count: int
    failed_count: int
    warnings: list[str]
    items: list[dict[str, Any]]
    source_urls: list[dict[str, Any]]
    result_path: Path | None
    vendor: str | None = None
    run_id: str = ""
    observation_batch_id: str = ""
    source_filter: str | None = None
    catalog_source: str | None = None
    skipped_count: int = 0
    artifact_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["result_path"] = str(self.result_path) if self.result_path is not None else ""
        payload["artifact_path"] = payload["result_path"]
        return json_safe_value(payload)


def json_safe_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe_value(item) for item in value]
    return value
