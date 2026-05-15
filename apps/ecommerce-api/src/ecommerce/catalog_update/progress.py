"""Catalog update workflow phases, progress events, and heartbeat reporting."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from ecommerce.catalog_update.redaction import sanitize_progress_details
from ecommerce.db.repositories.jobs import record_progress
from ecommerce.db.session import session_scope

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
    CatalogUpdateProgressEvent("config_loaded", "Config loaded", "config_loaded", "completed"),
    CatalogUpdateProgressEvent("alembic_upgrade_started", "Alembic upgrade started", "alembic_upgrade", "started"),
    CatalogUpdateProgressEvent("alembic_upgrade_completed", "Alembic upgrade completed", "alembic_upgrade", "completed"),
    CatalogUpdateProgressEvent("playwright_started", "Playwright started", "playwright_start", "started"),
    CatalogUpdateProgressEvent("login_started", "Login started", "login", "started"),
    CatalogUpdateProgressEvent("login_completed", "Login completed", "login", "completed"),
    CatalogUpdateProgressEvent("export_page_opened", "Export page opened", "open_csv_product_export", "completed"),
    CatalogUpdateProgressEvent("profile_loaded", "Profile loaded", "load_profile", "completed"),
    CatalogUpdateProgressEvent("export_step_advanced", "Export step advanced", "step_2_next", "completed"),
    CatalogUpdateProgressEvent("download_waiting", "Download waiting", "wait_for_download", "started"),
    CatalogUpdateProgressEvent("download_saved", "Download saved", "wait_for_download", "completed"),
    CatalogUpdateProgressEvent("exclusion_filtering_started", "Exclusion filtering started", "filter_exclusions", "started"),
    CatalogUpdateProgressEvent("exclusion_filtering_completed", "Exclusion filtering completed", "filter_exclusions", "completed"),
    CatalogUpdateProgressEvent("ingest_started", "Ingest started", "ingest_catalog", "started"),
    CatalogUpdateProgressEvent("ingest_completed", "Ingest completed", "ingest_catalog", "completed"),
    CatalogUpdateProgressEvent("exclusion_purge_started", "Exclusion purge started", "purge_exclusions", "started"),
    CatalogUpdateProgressEvent("exclusion_purge_completed", "Exclusion purge completed", "purge_exclusions", "completed"),
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
        selected_event_id = progress_event_id or (phase_id if phase_id in PROGRESS_EVENT_LABELS else None)
        if selected_event_id is not None:
            self.emit_progress_event(selected_event_id, details=details)

    def emit_progress_event(self, event_id: str, *, details: dict[str, Any] | None = None) -> None:
        if event_id not in PROGRESS_EVENT_LABELS:
            raise ValueError(f"Unsupported catalog update progress event: {event_id}")
        if self.progress_callback is not None:
            self.progress_callback(event_id, details)

    def mark(self, step: str, *, progress_step: str | None = None, details: dict[str, Any] | None = None) -> None:
        self.mark_workflow_phase(step, progress_event_id=progress_step, details=details)

    def emit_progress(self, progress_step: str, *, details: dict[str, Any] | None = None) -> None:
        self.emit_progress_event(progress_step, details=details)


@dataclass(frozen=True)
class CatalogUpdateCompletedStep:
    step: str
    label: str
    started_at: str
    completed_at: str
    elapsed_seconds: float


class CatalogUpdateJobProgressReporter:
    def __init__(
        self,
        job_id: str,
        *,
        heartbeat_interval_seconds: float = CATALOG_UPDATE_HEARTBEAT_INTERVAL_SECONDS,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._job_id = job_id
        self._heartbeat_interval_seconds = max(1.0, float(heartbeat_interval_seconds))
        self._current_step = "config_loaded"
        self._current_step_started_at: datetime | None = None
        self._started_at: datetime | None = None
        self._completed_steps: list[CatalogUpdateCompletedStep] = []
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._now = now or now_utc

    def __enter__(self) -> "CatalogUpdateJobProgressReporter":
        timestamp = self._now()
        with self._lock:
            self._started_at = timestamp
            self._current_step_started_at = timestamp
        self.report(self._current_step)
        self._thread = threading.Thread(target=self._heartbeat_loop, name=f"catalog-update-heartbeat-{self._job_id}", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def report(self, step: str, details: dict[str, Any] | None = None) -> None:
        timestamp = self._now()
        with self._lock:
            self._advance_step(step, timestamp)
            progress = self._progress_payload(timestamp, details=details)
        self._record(progress, timestamp)

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(self._heartbeat_interval_seconds):
            timestamp = self._now()
            with self._lock:
                progress = self._progress_payload(timestamp)
            self._record(progress, timestamp)

    def _advance_step(self, step: str, timestamp: datetime) -> None:
        if self._current_step == step:
            return
        if self._current_step_started_at is not None:
            self._completed_steps.append(
                CatalogUpdateCompletedStep(
                    step=self._current_step,
                    label=PROGRESS_EVENT_LABELS.get(self._current_step, self._current_step),
                    started_at=self._current_step_started_at.isoformat(),
                    completed_at=timestamp.isoformat(),
                    elapsed_seconds=elapsed_seconds(self._current_step_started_at, timestamp),
                )
            )
        self._current_step = step
        self._current_step_started_at = timestamp

    def _progress_payload(self, timestamp: datetime, *, details: dict[str, Any] | None = None) -> dict[str, Any]:
        started_at = self._started_at or timestamp
        step_started_at = self._current_step_started_at or timestamp
        payload: dict[str, Any] = {
            "current_step": self._current_step,
            "current_step_label": PROGRESS_EVENT_LABELS.get(self._current_step, self._current_step),
            "steps_completed": len(self._completed_steps),
            "step_started_at": step_started_at.isoformat(),
            "last_progress_at": timestamp.isoformat(),
            "elapsed_seconds": elapsed_seconds(started_at, timestamp),
            "current_step_elapsed_seconds": elapsed_seconds(step_started_at, timestamp),
            "completed_steps": [step.__dict__ for step in self._completed_steps],
        }
        safe_details = sanitize_progress_details(details)
        if safe_details:
            payload["details"] = safe_details
        return payload

    def _record(self, progress: dict[str, Any], timestamp: datetime) -> None:
        try:
            with session_scope() as session:
                record_progress(session, self._job_id, progress=progress, progress_at=timestamp)
        except Exception:
            return


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def elapsed_seconds(started_at: datetime, ended_at: datetime) -> float:
    return max(0.0, round((ended_at - started_at).total_seconds(), 3))
