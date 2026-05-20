"""Shared durable job progress payload and persistence helpers."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from ecommerce.db.repositories.jobs import record_progress
from ecommerce.db.session import session_scope

JobProgressDetailsSanitizer = Callable[[dict[str, Any] | None], dict[str, Any]]

__all__ = [
    "JobProgressCompletedStep",
    "JobProgressDetailsSanitizer",
    "JobProgressReporter",
    "JobProgressState",
    "JobProgressStepDefinition",
    "elapsed_seconds",
    "now_utc",
]


@dataclass(frozen=True)
class JobProgressStepDefinition:
    id: str
    label: str


@dataclass(frozen=True)
class JobProgressCompletedStep:
    step: str
    label: str
    started_at: str
    completed_at: str
    elapsed_seconds: float
    warnings: tuple[Any, ...] = ()
    errors: tuple[Any, ...] = ()
    details: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "step": self.step,
            "label": self.label,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": self.elapsed_seconds,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }
        if self.details:
            payload["details"] = dict(self.details)
        return payload


@dataclass
class JobProgressState:
    step_definitions: dict[str, str]
    current_step: str
    details_sanitizer: JobProgressDetailsSanitizer | None = None
    started_at: datetime | None = None
    current_step_started_at: datetime | None = None
    completed_steps: list[JobProgressCompletedStep] = field(default_factory=list)
    current_warnings: list[Any] = field(default_factory=list)
    current_errors: list[Any] = field(default_factory=list)
    current_details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        step_definitions: tuple[JobProgressStepDefinition, ...],
        initial_step: str,
        details_sanitizer: JobProgressDetailsSanitizer | None = None,
    ) -> "JobProgressState":
        labels = {definition.id: definition.label for definition in step_definitions}
        return cls(
            step_definitions=labels,
            current_step=initial_step,
            details_sanitizer=details_sanitizer,
        )

    def start(self, timestamp: datetime) -> None:
        self.started_at = timestamp
        self.current_step_started_at = timestamp

    def advance_to(self, step: str, timestamp: datetime) -> None:
        if self.current_step == step:
            return
        if self.current_step_started_at is not None:
            self.completed_steps.append(
                JobProgressCompletedStep(
                    step=self.current_step,
                    label=self.label_for(self.current_step),
                    started_at=self.current_step_started_at.isoformat(),
                    completed_at=timestamp.isoformat(),
                    elapsed_seconds=elapsed_seconds(
                        self.current_step_started_at, timestamp
                    ),
                    warnings=tuple(self.current_warnings),
                    errors=tuple(self.current_errors),
                    details=(
                        dict(self.current_details) if self.current_details else None
                    ),
                )
            )
        self.current_step = step
        self.current_step_started_at = timestamp
        self.current_warnings = []
        self.current_errors = []
        self.current_details = {}

    def add_details(self, details: dict[str, Any] | None) -> None:
        safe_details = self.sanitize_details(details)
        if safe_details:
            self.current_details.update(safe_details)

    def add_warning(
        self, warning: object, details: dict[str, Any] | None = None
    ) -> None:
        self.current_warnings.append(self.sanitize_notice(warning, details=details))

    def add_error(self, error: object, details: dict[str, Any] | None = None) -> None:
        self.current_errors.append(self.sanitize_notice(error, details=details))

    def payload(
        self, timestamp: datetime, *, details: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.add_details(details)
        started_at = self.started_at or timestamp
        step_started_at = self.current_step_started_at or timestamp
        payload: dict[str, Any] = {
            "current_step": self.current_step,
            "current_step_label": self.label_for(self.current_step),
            "step_started_at": step_started_at.isoformat(),
            "last_progress_at": timestamp.isoformat(),
            "elapsed_seconds": elapsed_seconds(started_at, timestamp),
            "current_step_elapsed_seconds": elapsed_seconds(step_started_at, timestamp),
            "steps_completed": len(self.completed_steps),
            "completed_steps": [step.to_payload() for step in self.completed_steps],
            "warnings": list(self.current_warnings),
            "errors": list(self.current_errors),
        }
        if self.current_details:
            payload["details"] = dict(self.current_details)
        return payload

    def label_for(self, step: str) -> str:
        return self.step_definitions.get(step, step)

    def sanitize_details(self, details: dict[str, Any] | None) -> dict[str, Any]:
        if not details:
            return {}
        if self.details_sanitizer is not None:
            return _json_safe_dict(self.details_sanitizer(details))
        return _json_safe_dict(details)

    def sanitize_notice(
        self, message: object, *, details: dict[str, Any] | None = None
    ) -> Any:
        safe_message = self.sanitize_details({"message": message}).get("message")
        if safe_message is None:
            safe_message = _json_safe_value(message)
        if details:
            safe_details = self.sanitize_details(details)
            if safe_details:
                return {"message": safe_message, "details": safe_details}
        return safe_message


class JobProgressReporter:
    def __init__(
        self,
        job_id: str,
        *,
        step_definitions: tuple[JobProgressStepDefinition, ...],
        initial_step: str,
        heartbeat_interval_seconds: float,
        details_sanitizer: JobProgressDetailsSanitizer | None = None,
        now: Callable[[], datetime] | None = None,
        heartbeat_thread_name: str | None = None,
    ) -> None:
        self._job_id = job_id
        self._heartbeat_interval_seconds = max(1.0, float(heartbeat_interval_seconds))
        self._state = JobProgressState.create(
            step_definitions=step_definitions,
            initial_step=initial_step,
            details_sanitizer=details_sanitizer,
        )
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._now = now or now_utc
        self._heartbeat_thread_name = (
            heartbeat_thread_name or f"job-progress-heartbeat-{job_id}"
        )

    def __enter__(self) -> "JobProgressReporter":
        timestamp = self._now()
        with self._lock:
            self._state.start(timestamp)
        self.report(self._state.current_step)
        self._thread = threading.Thread(
            target=self._heartbeat_loop, name=self._heartbeat_thread_name, daemon=True
        )
        self._thread.start()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def report(
        self,
        step: str,
        details: dict[str, Any] | None = None,
        *,
        warnings: list[object] | tuple[object, ...] | None = None,
        errors: list[object] | tuple[object, ...] | None = None,
    ) -> None:
        timestamp = self._now()
        with self._lock:
            self._state.advance_to(step, timestamp)
            for warning in warnings or ():
                self._state.add_warning(warning)
            for error in errors or ():
                self._state.add_error(error)
            progress = self._state.payload(timestamp, details=details)
        self._record(progress, timestamp)

    def add_warning(
        self, warning: object, details: dict[str, Any] | None = None
    ) -> None:
        timestamp = self._now()
        with self._lock:
            self._state.add_warning(warning, details=details)
            progress = self._state.payload(timestamp)
        self._record(progress, timestamp)

    def add_error(self, error: object, details: dict[str, Any] | None = None) -> None:
        timestamp = self._now()
        with self._lock:
            self._state.add_error(error, details=details)
            progress = self._state.payload(timestamp)
        self._record(progress, timestamp)

    def current_payload(self) -> dict[str, Any]:
        timestamp = self._now()
        with self._lock:
            return self._state.payload(timestamp)

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(self._heartbeat_interval_seconds):
            timestamp = self._now()
            with self._lock:
                progress = self._state.payload(timestamp)
            self._record(progress, timestamp)

    def _record(self, progress: dict[str, Any], timestamp: datetime) -> None:
        try:
            with session_scope() as session:
                record_progress(
                    session, self._job_id, progress=progress, progress_at=timestamp
                )
        except Exception:
            return


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def elapsed_seconds(started_at: datetime, ended_at: datetime) -> float:
    return max(0.0, round((ended_at - started_at).total_seconds(), 3))


def _json_safe_dict(value: dict[str, Any]) -> dict[str, Any]:
    safe_value = _json_safe_value(value)
    return safe_value if isinstance(safe_value, dict) else {}


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe_value(item) for item in value]
    return str(value)
