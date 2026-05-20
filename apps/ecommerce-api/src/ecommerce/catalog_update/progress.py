"""Catalog update workflow phases, progress events, and heartbeat reporting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from ecommerce.catalog_update.redaction import sanitize_progress_details
from ecommerce.jobs.progress import (
    JobProgressCompletedStep,
    JobProgressReporter,
    JobProgressStepDefinition,
    elapsed_seconds,
    now_utc,
)

CATALOG_UPDATE_HEARTBEAT_INTERVAL_SECONDS = 30
CatalogUpdateProgressCallback = Callable[[str, dict[str, Any] | None], None]


@dataclass(frozen=True)
class CatalogUpdateWorkflowPhase:
    id: str
    label: str


@dataclass(frozen=True)
class CatalogUpdateProgressEvent:
    id: str
    label: str
    phase_id: str
    boundary: str


WORKFLOW_PHASES: tuple[CatalogUpdateWorkflowPhase, ...] = (
    CatalogUpdateWorkflowPhase("config_loaded", "Config loaded"),
    CatalogUpdateWorkflowPhase("alembic_upgrade", "Alembic upgrade"),
    CatalogUpdateWorkflowPhase("playwright_start", "Playwright start"),
    CatalogUpdateWorkflowPhase("login", "Login"),
    CatalogUpdateWorkflowPhase("open_csv_product_export", "Open CSV Product Export"),
    CatalogUpdateWorkflowPhase("load_profile", "Load export profile"),
    CatalogUpdateWorkflowPhase("step_2_next", "Advance export step"),
    CatalogUpdateWorkflowPhase("wait_for_download", "Wait for download"),
    CatalogUpdateWorkflowPhase("save_download", "Save download"),
    CatalogUpdateWorkflowPhase("filter_exclusions", "Filter exclusions"),
    CatalogUpdateWorkflowPhase("ingest_catalog", "Ingest catalog"),
    CatalogUpdateWorkflowPhase("purge_exclusions", "Purge exclusions"),
)
PROGRESS_EVENTS: tuple[CatalogUpdateProgressEvent, ...] = (
    CatalogUpdateProgressEvent(
        "config_loaded", "Config loaded", "config_loaded", "completed"
    ),
    CatalogUpdateProgressEvent(
        "alembic_upgrade_started",
        "Alembic upgrade started",
        "alembic_upgrade",
        "started",
    ),
    CatalogUpdateProgressEvent(
        "alembic_upgrade_completed",
        "Alembic upgrade completed",
        "alembic_upgrade",
        "completed",
    ),
    CatalogUpdateProgressEvent(
        "playwright_started", "Playwright started", "playwright_start", "started"
    ),
    CatalogUpdateProgressEvent("login_started", "Login started", "login", "started"),
    CatalogUpdateProgressEvent(
        "login_completed", "Login completed", "login", "completed"
    ),
    CatalogUpdateProgressEvent(
        "export_page_opened",
        "Export page opened",
        "open_csv_product_export",
        "completed",
    ),
    CatalogUpdateProgressEvent(
        "profile_loaded", "Profile loaded", "load_profile", "completed"
    ),
    CatalogUpdateProgressEvent(
        "export_step_advanced", "Export step advanced", "step_2_next", "completed"
    ),
    CatalogUpdateProgressEvent(
        "download_waiting", "Download waiting", "wait_for_download", "started"
    ),
    CatalogUpdateProgressEvent(
        "download_saved", "Download saved", "wait_for_download", "completed"
    ),
    CatalogUpdateProgressEvent(
        "exclusion_filtering_started",
        "Exclusion filtering started",
        "filter_exclusions",
        "started",
    ),
    CatalogUpdateProgressEvent(
        "exclusion_filtering_completed",
        "Exclusion filtering completed",
        "filter_exclusions",
        "completed",
    ),
    CatalogUpdateProgressEvent(
        "ingest_started", "Ingest started", "ingest_catalog", "started"
    ),
    CatalogUpdateProgressEvent(
        "ingest_completed", "Ingest completed", "ingest_catalog", "completed"
    ),
    CatalogUpdateProgressEvent(
        "exclusion_purge_started",
        "Exclusion purge started",
        "purge_exclusions",
        "started",
    ),
    CatalogUpdateProgressEvent(
        "exclusion_purge_completed",
        "Exclusion purge completed",
        "purge_exclusions",
        "completed",
    ),
)
WORKFLOW_PHASE_LABELS = {phase.id: phase.label for phase in WORKFLOW_PHASES}
PROGRESS_EVENT_LABELS = {event.id: event.label for event in PROGRESS_EVENTS}
PROGRESS_EVENT_PHASES = {event.id: event.phase_id for event in PROGRESS_EVENTS}
CATALOG_UPDATE_STEPS = tuple(WORKFLOW_PHASE_LABELS)
CATALOG_UPDATE_PROGRESS_STEPS = PROGRESS_EVENT_LABELS


@dataclass
class CatalogUpdateStepTracker:
    current_step: str = "config_loaded"
    progress_callback: CatalogUpdateProgressCallback | None = None

    def mark_workflow_phase(
        self,
        phase_id: str,
        *,
        progress_event_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if phase_id not in WORKFLOW_PHASE_LABELS:
            raise ValueError(f"Unsupported catalog update workflow phase: {phase_id}")
        self.current_step = phase_id
        selected_event_id = progress_event_id or (
            phase_id if phase_id in PROGRESS_EVENT_LABELS else None
        )
        if selected_event_id is not None:
            self.emit_progress_event(selected_event_id, details=details)

    def emit_progress_event(
        self, event_id: str, *, details: dict[str, Any] | None = None
    ) -> None:
        if event_id not in PROGRESS_EVENT_LABELS:
            raise ValueError(f"Unsupported catalog update progress event: {event_id}")
        if self.progress_callback is not None:
            self.progress_callback(event_id, details)

    def mark(
        self,
        step: str,
        *,
        progress_step: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.mark_workflow_phase(step, progress_event_id=progress_step, details=details)

    def emit_progress(
        self, progress_step: str, *, details: dict[str, Any] | None = None
    ) -> None:
        self.emit_progress_event(progress_step, details=details)


CatalogUpdateCompletedStep = JobProgressCompletedStep
CATALOG_UPDATE_PROGRESS_STEP_DEFINITIONS = tuple(
    JobProgressStepDefinition(event.id, event.label) for event in PROGRESS_EVENTS
)


class CatalogUpdateJobProgressReporter(JobProgressReporter):
    def __init__(
        self,
        job_id: str,
        *,
        heartbeat_interval_seconds: float = CATALOG_UPDATE_HEARTBEAT_INTERVAL_SECONDS,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(
            job_id,
            step_definitions=CATALOG_UPDATE_PROGRESS_STEP_DEFINITIONS,
            initial_step="config_loaded",
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            details_sanitizer=sanitize_progress_details,
            now=now,
            heartbeat_thread_name=f"catalog-update-heartbeat-{job_id}",
        )
