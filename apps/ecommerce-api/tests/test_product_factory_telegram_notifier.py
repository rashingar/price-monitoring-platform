from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from ecommerce.product_factory_telegram import audit
from ecommerce.product_factory_telegram.client import (
    ProductFactoryClientError,
    ProductFactoryJob,
    TelegramDeliveryError,
)
from ecommerce.product_factory_telegram.config import ProductFactoryTelegramConfig
from ecommerce.product_factory_telegram.notifier import (
    POLL_FAILED_EVENT,
    main,
    run_once,
    terminal_notification_candidates,
)


def test_finds_enqueued_telegram_jobs_from_audit_log(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    audit.append_event(
        path=path,
        event_type="product_factory_enqueue_succeeded",
        chat_id="-100",
        user_id="123",
        model="012345",
        job_id="job-1",
    )

    candidates = terminal_notification_candidates(str(path))

    assert len(candidates) == 1
    assert candidates[0].job_id == "job-1"
    assert candidates[0].chat_id == "-100"
    assert candidates[0].model == "012345"
    assert candidates[0].user_id == "123"


@pytest.mark.parametrize(
    "event_type",
    [
        "product_factory_terminal_notification_sent",
        "product_factory_terminal_notification_failed",
    ],
)
def test_ignores_jobs_already_notified(event_type: str, tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    audit.append_event(
        path=path,
        event_type="product_factory_enqueue_succeeded",
        chat_id="-100",
        model="012345",
        job_id="job-1",
    )
    audit.append_event(
        path=path,
        event_type=event_type,
        chat_id="-100",
        model="012345",
        job_id="job-1",
    )
    product_factory = FakeProductFactoryClient()
    telegram = FakeTelegramClient()

    summary = run_once(
        config=_config(path),
        product_factory_client=product_factory,
        telegram_client=telegram,
        output=lambda _line: None,
    )

    assert summary.checked == 0
    assert product_factory.get_job_calls == []
    assert telegram.messages == []


def test_ignores_non_terminal_jobs(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    audit.append_event(
        path=path,
        event_type="product_factory_enqueue_succeeded",
        chat_id="-100",
        model="012345",
        job_id="job-1",
    )
    product_factory = FakeProductFactoryClient(
        {
            "job-1": ProductFactoryJob(
                job_id="job-1",
                status="running",
                raw={"job_id": "job-1"},
                model="012345",
            )
        }
    )
    telegram = FakeTelegramClient()

    summary = run_once(
        config=_config(path),
        product_factory_client=product_factory,
        telegram_client=telegram,
        output=lambda _line: None,
    )

    assert summary.non_terminal == 1
    assert telegram.messages == []
    assert "product_factory_terminal_notification_sent" not in _event_types(path)


@pytest.mark.parametrize("status", ["succeeded", "cancelled", "killed"])
def test_sends_notification_for_terminal_statuses(status: str, tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    audit.append_event(
        path=path,
        event_type="product_factory_enqueue_succeeded",
        chat_id="-100",
        model="012345",
        job_id="job-1",
    )
    product_factory = FakeProductFactoryClient(
        {
            "job-1": ProductFactoryJob(
                job_id="job-1",
                status=status,
                raw={"job_id": "job-1"},
                model="012345",
                message="Finished.",
            )
        }
    )
    telegram = FakeTelegramClient()

    summary = run_once(
        config=_config(path),
        product_factory_client=product_factory,
        telegram_client=telegram,
        output=lambda _line: None,
    )

    assert summary.sent == 1
    assert telegram.messages == [
        {
            "chat_id": "-100",
            "text": (
                "Product Factory job finished\n"
                "model: 012345\n"
                "job_id: job-1\n"
                f"status: {status}\n"
                "message: Finished."
            ),
            "reply_markup": None,
        }
    ]


def test_sends_notification_for_failed_with_message_error_and_error_code(
    tmp_path: Path,
) -> None:
    path = tmp_path / "audit.jsonl"
    audit.append_event(
        path=path,
        event_type="product_factory_enqueue_succeeded",
        chat_id="-100",
        model="012345",
        selected_url="https://example.com/product",
        selected_title="Source title",
        confidence=98,
        job_id="job-1",
    )
    product_factory = FakeProductFactoryClient(
        {
            "job-1": ProductFactoryJob(
                job_id="job-1",
                status="failed",
                raw={"job_id": "job-1"},
                model="012345",
                message="Render failed.",
                error="Missing image.",
                error_code="render_error",
            )
        }
    )
    telegram = FakeTelegramClient()

    run_once(
        config=_config(path),
        product_factory_client=product_factory,
        telegram_client=telegram,
        output=lambda _line: None,
    )

    text = telegram.messages[0]["text"]
    assert "model: 012345" in text
    assert "job_id: job-1" in text
    assert "status: failed" in text
    assert "message: Render failed." in text
    assert "error: Missing image." in text
    assert "error_code: render_error" in text


def test_does_not_fetch_logs_or_include_source_selection_fields(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    audit.append_event(
        path=path,
        event_type="product_factory_enqueue_succeeded",
        chat_id="-100",
        model="012345",
        selected_url="https://example.com/product",
        selected_title="Source title",
        confidence=98,
        job_id="job-1",
    )
    product_factory = FakeProductFactoryClient(
        {
            "job-1": ProductFactoryJob(
                job_id="job-1",
                status="succeeded",
                raw={"job_id": "job-1"},
                model="012345",
            )
        }
    )
    telegram = FakeTelegramClient()

    run_once(
        config=_config(path),
        product_factory_client=product_factory,
        telegram_client=telegram,
        output=lambda _line: None,
    )

    text = telegram.messages[0]["text"]
    assert product_factory.log_fetches == 0
    assert "https://example.com/product" not in text
    assert "Source title" not in text
    assert "confidence" not in text


def test_writes_sent_audit_event_after_successful_delivery(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    audit.append_event(
        path=path,
        event_type="product_factory_enqueue_succeeded",
        chat_id="-100",
        model="012345",
        job_id="job-1",
    )
    product_factory = FakeProductFactoryClient(
        {
            "job-1": ProductFactoryJob(
                job_id="job-1",
                status="failed",
                raw={"job_id": "job-1"},
                model="012345",
                message="Done.",
                error="Problem.",
                error_code="problem",
            )
        }
    )

    run_once(
        config=_config(path),
        product_factory_client=product_factory,
        telegram_client=FakeTelegramClient(),
        output=lambda _line: None,
    )

    event = _events(path)[-1]
    assert event["event_type"] == "product_factory_terminal_notification_sent"
    assert event["job_id"] == "job-1"
    assert event["status"] == "failed"
    assert event["message"] == "Done."
    assert event["metadata"]["error"] == "Problem."
    assert event["metadata"]["error_code"] == "problem"


def test_writes_failed_audit_event_after_delivery_failure(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    audit.append_event(
        path=path,
        event_type="product_factory_enqueue_succeeded",
        chat_id="-100",
        model="012345",
        job_id="job-1",
    )
    product_factory = FakeProductFactoryClient(
        {
            "job-1": ProductFactoryJob(
                job_id="job-1",
                status="succeeded",
                raw={"job_id": "job-1"},
                model="012345",
            )
        }
    )

    summary = run_once(
        config=_config(path),
        product_factory_client=product_factory,
        telegram_client=FakeTelegramClient(fail=True),
        output=lambda _line: None,
    )

    event = _events(path)[-1]
    assert summary.delivery_failed == 1
    assert event["event_type"] == "product_factory_terminal_notification_failed"
    assert event["job_id"] == "job-1"
    assert event["status"] == "succeeded"
    assert event["message"] == "Telegram message delivery failed."
    assert event["metadata"]["delivery_error"] == "Telegram message delivery failed."


def test_does_not_send_duplicate_notifications_on_second_pass(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    audit.append_event(
        path=path,
        event_type="product_factory_enqueue_succeeded",
        chat_id="-100",
        model="012345",
        job_id="job-1",
    )
    product_factory = FakeProductFactoryClient(
        {
            "job-1": ProductFactoryJob(
                job_id="job-1",
                status="succeeded",
                raw={"job_id": "job-1"},
                model="012345",
            )
        }
    )
    telegram = FakeTelegramClient()
    config = _config(path)

    run_once(
        config=config,
        product_factory_client=product_factory,
        telegram_client=telegram,
        output=lambda _line: None,
    )
    run_once(
        config=config,
        product_factory_client=product_factory,
        telegram_client=telegram,
        output=lambda _line: None,
    )

    assert len(telegram.messages) == 1
    assert product_factory.get_job_calls == ["job-1"]


def test_once_runs_one_pass_and_exits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[int] = []

    def fake_run_once(**kwargs: Any) -> Any:
        calls.append(kwargs["limit"])
        return object()

    assert main(["--once", "--limit", "7"], run_once_func=fake_run_once) == 0
    assert calls == [7]


def test_polling_errors_for_one_job_do_not_stop_other_jobs(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    audit.append_event(
        path=path,
        event_type="product_factory_enqueue_succeeded",
        chat_id="-100",
        model="012345",
        job_id="job-bad",
    )
    audit.append_event(
        path=path,
        event_type="product_factory_enqueue_succeeded",
        chat_id="-200",
        model="999999",
        job_id="job-good",
    )
    product_factory = FakeProductFactoryClient(
        {
            "job-good": ProductFactoryJob(
                job_id="job-good",
                status="succeeded",
                raw={"job_id": "job-good"},
                model="999999",
            )
        },
        fail_job_ids={"job-bad"},
    )
    telegram = FakeTelegramClient()

    summary = run_once(
        config=_config(path),
        product_factory_client=product_factory,
        telegram_client=telegram,
        output=lambda _line: None,
    )

    assert summary.poll_failed == 1
    assert summary.sent == 1
    assert product_factory.get_job_calls == ["job-bad", "job-good"]
    assert telegram.messages[0]["chat_id"] == "-200"
    assert POLL_FAILED_EVENT in _event_types(path)
    assert "product_factory_terminal_notification_sent" in _event_types(path)


class FakeTelegramClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[dict[str, Any]] = []

    def send_message(
        self, chat_id: str, text: str, *, reply_markup: dict[str, Any] | None = None
    ) -> None:
        if self.fail:
            raise TelegramDeliveryError("Telegram message delivery failed.")
        self.messages.append(
            {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        )


class FakeProductFactoryClient:
    def __init__(
        self,
        jobs: dict[str, ProductFactoryJob] | None = None,
        *,
        fail_job_ids: set[str] | None = None,
    ) -> None:
        self.jobs = jobs or {}
        self.fail_job_ids = fail_job_ids or set()
        self.get_job_calls: list[str] = []
        self.log_fetches = 0

    def get_job(self, job_id: str) -> ProductFactoryJob:
        self.get_job_calls.append(job_id)
        if job_id in self.fail_job_ids:
            raise ProductFactoryClientError(
                "Product Factory API is unavailable; job status could not be fetched."
            )
        return self.jobs[job_id]

    def get_job_logs(self, job_id: str) -> list[str]:
        del job_id
        self.log_fetches += 1
        return ["unexpected log line"]


def _config(path: Path) -> ProductFactoryTelegramConfig:
    return replace(
        ProductFactoryTelegramConfig(), audit_log_path=str(path), bot_token="token"
    )


def _events(path: Path) -> list[dict[str, Any]]:
    return list(audit.iter_events(path))


def _event_types(path: Path) -> list[str]:
    return [event["event_type"] for event in _events(path)]
