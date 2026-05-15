"""OpenCart catalog export and Ecommerce catalog ingestion orchestration."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ecommerce.catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.catalog_update.cleanup import purge_excluded_catalog_state
from ecommerce.catalog_update.config import load_catalog_update_config
from ecommerce.catalog_update.exclusions import (
    filter_source_catalog_exclusions,
    load_excluded_models as _load_excluded_models,
    normalize_downloaded_csv,
)
from ecommerce.catalog_update.exporter import export_catalog_csv
from ecommerce.catalog_update.migration import run_alembic_upgrade
from ecommerce.catalog_update.paths import catalog_update_output_dir, display_path, repo_root
from ecommerce.catalog_update.progress import (
    CATALOG_UPDATE_HEARTBEAT_INTERVAL_SECONDS,
    CatalogUpdateJobProgressReporter,
    CatalogUpdateProgressCallback,
    CatalogUpdateStepTracker,
)
from ecommerce.catalog_update.redaction import redact_opencart_sensitive_data
from ecommerce.catalog_update.types import (
    CatalogUpdateConfig,
    CatalogUpdateError,
    ExcludedModels,
)
from ecommerce.jobs.ingest_catalog import ingest_catalog_file


def run_catalog_update(
    job_id: str,
    *,
    config: CatalogUpdateConfig | None = None,
    progress_callback: CatalogUpdateProgressCallback | None = None,
) -> dict[str, Any]:
    steps = CatalogUpdateStepTracker(progress_callback=progress_callback)
    try:
        selected_config = config or load_catalog_update_config()
    except CatalogUpdateError as exc:
        raise CatalogUpdateError(_message_with_step(str(exc), steps.current_step)) from exc
    steps.mark(
        "config_loaded",
        details={
            "export_profile": selected_config.export_profile,
            "timeout_seconds": selected_config.timeout_seconds,
            "headed": selected_config.headed,
        },
    )
    output_dir = catalog_update_output_dir(job_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    steps.mark("alembic_upgrade", progress_step="alembic_upgrade_started")
    try:
        migration = run_alembic_upgrade()
    except CatalogUpdateError as exc:
        raise CatalogUpdateError(_message_with_step(str(exc), steps.current_step)) from exc
    steps.emit_progress("alembic_upgrade_completed", details={"status": migration.get("status")})

    export = export_catalog_csv(selected_config, output_dir, job_id=job_id, step_tracker=steps)
    try:
        normalized_csv_path = normalize_downloaded_csv(export.downloaded_path, output_dir)
    except CatalogUpdateError as exc:
        raise CatalogUpdateError(_message_with_step(str(exc), steps.current_step)) from exc
    steps.mark("filter_exclusions", progress_step="exclusion_filtering_started")
    try:
        exclusions = load_excluded_models()
        filter_result = filter_source_catalog_exclusions(normalized_csv_path, output_dir, exclusions)
    except CatalogUpdateError as exc:
        raise CatalogUpdateError(_message_with_step(str(exc), steps.current_step)) from exc
    steps.emit_progress(
        "exclusion_filtering_completed",
        details={
            "excluded_model_count": filter_result.excluded_model_count,
            "input_row_count": filter_result.input_row_count,
            "removed_row_count": filter_result.removed_row_count,
            "output_row_count": filter_result.output_row_count,
        },
    )
    steps.mark("ingest_catalog", progress_step="ingest_started")
    try:
        ingest = run_catalog_ingest(filter_result.filtered_csv_path)
    except Exception as exc:
        raise CatalogUpdateError(_message_with_step(str(exc) or exc.__class__.__name__, steps.current_step)) from exc
    steps.emit_progress("ingest_completed", details={"imported": ingest.get("imported")})
    steps.mark("purge_exclusions", progress_step="exclusion_purge_started")
    try:
        cleanup = purge_excluded_catalog_state(
            exclusions.models,
            catalog_source=str(ingest.get("catalog_source") or DEFAULT_CATALOG_SOURCE),
        )
    except CatalogUpdateError as exc:
        raise CatalogUpdateError(_message_with_step(str(exc), steps.current_step)) from exc
    steps.emit_progress("exclusion_purge_completed", details=cleanup.to_payload())

    return {
        "job_id": job_id,
        "artifact_dir": display_path(output_dir),
        "download_dir": display_path(output_dir),
        "export_profile": selected_config.export_profile,
        "downloaded_csv_path": display_path(export.downloaded_path),
        "normalized_csv_path": display_path(normalized_csv_path),
        "imported_csv_path": display_path(filter_result.filtered_csv_path),
        "downloaded_filename": export.downloaded_path.name,
        "downloaded_file_size": export.downloaded_size,
        "migration": migration,
        "ingest": ingest,
        "exclusions": {
            **filter_result.to_payload(),
            **cleanup.to_payload(),
        },
    }


def run_catalog_update_durable_job(
    job_id: str,
    *,
    config: CatalogUpdateConfig | None = None,
    heartbeat_interval_seconds: float = CATALOG_UPDATE_HEARTBEAT_INTERVAL_SECONDS,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    with CatalogUpdateJobProgressReporter(job_id, heartbeat_interval_seconds=heartbeat_interval_seconds, now=now) as progress:
        return run_catalog_update(job_id, config=config, progress_callback=progress.report)


def run_catalog_ingest(source_cata_path: Path) -> dict[str, Any]:
    return ingest_catalog_file(source_cata_path=source_cata_path).to_dict()


def load_excluded_models(path: Path | None = None) -> ExcludedModels:
    return _load_excluded_models(path, repo_root_func=repo_root)


def _message_with_step(message: str, step: str) -> str:
    safe_message = redact_opencart_sensitive_data(message)
    if "Step:" in safe_message or " at step " in safe_message:
        return safe_message
    return f"{safe_message} Step: {step}."
