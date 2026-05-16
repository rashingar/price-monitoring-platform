"""Poll Product Factory jobs and notify Telegram when they finish."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import time
from typing import Any, Protocol

from ecommerce.env import load_local_env_if_present

from .audit import append_event, iter_events
from .client import ProductFactoryClient, ProductFactoryJob, TelegramBotClient
from .config import ProductFactoryTelegramConfig, product_factory_telegram_config_from_env


TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled", "killed"})
TERMINAL_NOTIFICATION_EVENTS = frozenset(
    {
        "product_factory_terminal_notification_sent",
        "product_factory_terminal_notification_failed",
    }
)
POLL_FAILED_EVENT = "product_factory_terminal_notification_poll_failed"


class ProductFactoryStatusClient(Protocol):
    def get_job(self, job_id: str) -> ProductFactoryJob: ...


class TelegramMessageClient(Protocol):
    def send_message(self, chat_id: str, text: str, *, reply_markup: dict[str, Any] | None = None) -> None: ...


@dataclass(frozen=True)
class NotificationCandidate:
    job_id: str
    chat_id: str
    model: str
    user_id: str | None = None


@dataclass
class NotifierPassSummary:
    candidates: int = 0
    checked: int = 0
    non_terminal: int = 0
    sent: int = 0
    delivery_failed: int = 0
    poll_failed: int = 0
    skipped: int = 0


def terminal_notification_candidates(
    audit_log_path: str,
    *,
    limit: int = 50,
) -> list[NotificationCandidate]:
    """Return unnotified Telegram-started Product Factory jobs from the audit log."""

    notified_job_ids: set[str] = set()
    candidates_by_job_id: dict[str, NotificationCandidate] = {}

    for event in iter_events(audit_log_path):
        event_type = str(event.get("event_type") or "")
        job_id = str(event.get("job_id") or "").strip()
        if not job_id:
            continue
        if event_type in TERMINAL_NOTIFICATION_EVENTS:
            notified_job_ids.add(job_id)
            candidates_by_job_id.pop(job_id, None)
            continue
        if event_type != "product_factory_enqueue_succeeded" or job_id in notified_job_ids:
            continue

        chat_id = str(event.get("chat_id") or "").strip()
        if not chat_id:
            continue
        candidates_by_job_id[job_id] = NotificationCandidate(
            job_id=job_id,
            chat_id=chat_id,
            model=str(event.get("model") or "").strip(),
            user_id=_optional_text(event.get("user_id")),
        )

    return list(candidates_by_job_id.values())[: max(0, limit)]


def run_once(
    *,
    config: ProductFactoryTelegramConfig | None = None,
    product_factory_client: ProductFactoryStatusClient | None = None,
    telegram_client: TelegramMessageClient | None = None,
    limit: int = 50,
    output: Callable[[str], None] = print,
) -> NotifierPassSummary:
    config = config or product_factory_telegram_config_from_env()
    product_factory_client = product_factory_client or ProductFactoryClient(config.product_factory_api_base_url)
    telegram_client = telegram_client or TelegramBotClient(config.bot_token)
    candidates = terminal_notification_candidates(config.audit_log_path, limit=limit)
    summary = NotifierPassSummary(candidates=len(candidates))

    for candidate in candidates:
        summary.checked += 1
        try:
            job = product_factory_client.get_job(candidate.job_id)
        except Exception as exc:  # keep one bad job from blocking the pass
            summary.poll_failed += 1
            _append_poll_failed(config.audit_log_path, candidate, exc)
            continue

        status = _normalize_status(job.status)
        if status not in TERMINAL_STATUSES:
            summary.non_terminal += 1
            continue

        message = terminal_notification_message(job, fallback_model=candidate.model)
        try:
            telegram_client.send_message(candidate.chat_id, message)
        except Exception as exc:  # delivery errors are audited and the pass continues
            summary.delivery_failed += 1
            _append_delivery_failed(config.audit_log_path, candidate, job, exc)
            continue

        summary.sent += 1
        append_event(
            path=config.audit_log_path,
            event_type="product_factory_terminal_notification_sent",
            chat_id=candidate.chat_id,
            user_id=candidate.user_id,
            model=_job_model(job, candidate.model),
            job_id=job.job_id,
            status=status,
            message=job.message,
            metadata=_job_terminal_metadata(job),
        )

    summary.skipped = summary.candidates - summary.checked
    output(_summary_line(summary))
    return summary


def terminal_notification_message(job: ProductFactoryJob, *, fallback_model: str = "") -> str:
    lines = [
        "Product Factory job finished",
        f"model: {_job_model(job, fallback_model) or '-'}",
        f"job_id: {job.job_id}",
        f"status: {_normalize_status(job.status) or '-'}",
    ]
    if job.message:
        lines.append(f"message: {job.message}")
    if job.error:
        lines.append(f"error: {job.error}")
    if job.error_code:
        lines.append(f"error_code: {job.error_code}")
    return "\n".join(lines)


def main(
    argv: Sequence[str] | None = None,
    *,
    run_once_func: Callable[..., NotifierPassSummary] = run_once,
) -> int:
    load_local_env_if_present()
    parser = _build_parser()
    args = parser.parse_args(argv)
    limit = max(1, int(args.limit))

    if args.once:
        run_once_func(limit=limit)
        return 0

    poll_seconds = int(args.poll_seconds)
    try:
        while True:
            run_once_func(limit=limit)
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        print("notifier stopped")
        return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Notify Telegram when Telegram-started Product Factory jobs finish.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="Run one polling pass and exit.")
    mode.add_argument("--poll-seconds", type=_positive_int, help="Run continuously, sleeping N seconds between passes.")
    parser.add_argument("--limit", type=_positive_int, default=50, help="Maximum jobs to check per pass.")
    return parser


def _append_poll_failed(audit_log_path: str, candidate: NotificationCandidate, exc: Exception) -> None:
    append_event(
        path=audit_log_path,
        event_type=POLL_FAILED_EVENT,
        chat_id=candidate.chat_id,
        user_id=candidate.user_id,
        model=candidate.model,
        job_id=candidate.job_id,
        status="failed",
        message=str(exc),
        metadata={"error": str(exc)},
    )


def _append_delivery_failed(
    audit_log_path: str,
    candidate: NotificationCandidate,
    job: ProductFactoryJob,
    exc: Exception,
) -> None:
    append_event(
        path=audit_log_path,
        event_type="product_factory_terminal_notification_failed",
        chat_id=candidate.chat_id,
        user_id=candidate.user_id,
        model=_job_model(job, candidate.model),
        job_id=job.job_id,
        status=_normalize_status(job.status),
        message=str(exc),
        metadata={**_job_terminal_metadata(job), "delivery_error": str(exc)},
    )


def _job_terminal_metadata(job: ProductFactoryJob) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if job.message:
        metadata["job_message"] = job.message
    if job.error:
        metadata["error"] = job.error
    if job.error_code:
        metadata["error_code"] = job.error_code
    return metadata


def _summary_line(summary: NotifierPassSummary) -> str:
    return (
        "notifier pass: "
        f"candidates={summary.candidates} checked={summary.checked} "
        f"non_terminal={summary.non_terminal} sent={summary.sent} "
        f"delivery_failed={summary.delivery_failed} poll_failed={summary.poll_failed}"
    )


def _job_model(job: ProductFactoryJob, fallback_model: str) -> str:
    return str(job.model or fallback_model or "").strip()


def _normalize_status(status: str) -> str:
    return str(status or "").strip().lower()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
