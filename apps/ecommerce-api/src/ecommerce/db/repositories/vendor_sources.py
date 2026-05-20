"""Vendor Sources capture run repository helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecommerce.db.models.vendor_sources import VendorSourceCaptureRun
from ecommerce.vendor_sources.payloads import SourceUrlCaptureRunResult, json_safe_value


def create_vendor_source_capture_run_row(
    session: Session,
    *,
    run_id: str,
    observation_batch_id: str,
    status: str,
    source_filter: str | None,
    catalog_source: str | None,
    filters: dict[str, Any],
    result_path: Path,
) -> VendorSourceCaptureRun:
    now = now_utc()
    row = VendorSourceCaptureRun(
        run_id=run_id,
        observation_batch_id=observation_batch_id,
        status=status,
        source_filter=source_filter,
        catalog_source=catalog_source,
        warnings_json=[],
        filters_json=json_safe_value(filters),
        artifact_refs_json=[],
        result_path=str(result_path),
        started_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    return row


def mark_vendor_source_capture_run_failed(
    row: VendorSourceCaptureRun,
    *,
    error: Exception,
    result_path: Path | None = None,
) -> None:
    now = now_utc()
    row.status = "failed"
    row.failed_count = int(row.failed_count or 0)
    row.warnings_json = list(row.warnings_json or []) + [_short_error(error)]
    if result_path is not None:
        row.result_path = str(result_path)
        refs = list(row.artifact_refs_json or [])
        if str(result_path) not in refs:
            refs.append(str(result_path))
        row.artifact_refs_json = refs
    row.completed_at = now
    row.updated_at = now


def update_vendor_source_capture_run(
    row: VendorSourceCaptureRun, result: SourceUrlCaptureRunResult
) -> None:
    now = now_utc()
    row.status = result.status
    row.observation_batch_id = (
        result.observation_batch_id or row.observation_batch_id or result.run_id
    )
    row.source_filter = result.source_filter
    row.catalog_source = result.catalog_source
    row.selected_catalog_product_count = result.selected_catalog_product_count
    row.selected_source_url_count = result.selected_source_url_count
    row.selected_product_source_count = result.selected_product_source_count
    row.succeeded_count = result.succeeded_count
    row.failed_count = result.failed_count
    row.skipped_count = result.skipped_count
    row.warnings_json = list(result.warnings)
    row.artifact_refs_json = list(result.artifact_refs)
    row.result_path = (
        str(result.result_path) if result.result_path is not None else None
    )
    row.completed_at = now
    row.updated_at = now


def list_vendor_source_capture_runs(
    session: Session,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 500))
    safe_offset = max(0, int(offset))
    rows = session.execute(
        select(VendorSourceCaptureRun)
        .order_by(
            VendorSourceCaptureRun.created_at.desc(), VendorSourceCaptureRun.id.desc()
        )
        .offset(safe_offset)
        .limit(safe_limit)
    ).scalars()
    return [vendor_source_capture_run_to_dict(row) for row in rows]


def get_vendor_source_capture_run(
    session: Session, run_id: str
) -> VendorSourceCaptureRun | None:
    return session.execute(
        select(VendorSourceCaptureRun).where(VendorSourceCaptureRun.run_id == run_id)
    ).scalar_one_or_none()


def vendor_source_capture_run_to_dict(row: VendorSourceCaptureRun) -> dict[str, Any]:
    return json_safe_value(
        {
            "id": row.id,
            "run_id": row.run_id,
            "observation_batch_id": row.observation_batch_id,
            "status": row.status,
            "source_filter": row.source_filter,
            "catalog_source": row.catalog_source,
            "selected_catalog_product_count": row.selected_catalog_product_count,
            "selected_source_url_count": row.selected_source_url_count,
            "selected_product_source_count": row.selected_product_source_count,
            "succeeded_count": row.succeeded_count,
            "failed_count": row.failed_count,
            "skipped_count": row.skipped_count,
            "warnings": row.warnings_json or [],
            "filters": row.filters_json or {},
            "artifact_refs": row.artifact_refs_json or [],
            "result_path": row.result_path or "",
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


def make_vendor_capture_run_id() -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _short_error(error: Exception, *, limit: int = 500) -> str:
    text = " ".join(str(error).split()) or error.__class__.__name__
    return text if len(text) <= limit else f"{text[: limit - 3]}..."
