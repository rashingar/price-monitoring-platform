"""Telegram Product Factory intake orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
import secrets
import threading
from typing import Any, Protocol

from .audit import append_event, latest_enqueued_job_for_model
from .client import ProductFactoryClientError, ProductFactoryJob
from .config import ProductFactoryTelegramConfig
from .parser import ProductFactoryCommand, ProductFactoryCommandParseError, parse_product_factory_command
from .source_resolution import (
    SourceResolutionCandidate,
    SourceResolutionConfigError,
    SourceResolutionError,
    SourceResolutionResult,
    resolver_from_config_path,
)
from .warehouse import WarehouseCatalogError, WarehouseProduct, lookup_warehouse_product


FULL_GALLERY_PHOTOS = 20
DEFAULT_SECTIONS = 20


class TelegramMessenger(Protocol):
    def send_message(self, chat_id: str, text: str, *, reply_markup: dict[str, Any] | None = None) -> None: ...


class ProductFactoryStarter(Protocol):
    def start_full_pipeline(self, payload: dict[str, Any]) -> ProductFactoryJob: ...
    def get_job(self, job_id: str) -> ProductFactoryJob: ...
    def list_jobs_by_model(self, model: str) -> list[ProductFactoryJob]: ...


class SourceResolver(Protocol):
    def resolve(self, *, product: WarehouseProduct) -> SourceResolutionResult: ...


@dataclass(frozen=True)
class TelegramIdentity:
    chat_id: str | None
    user_id: str | None


@dataclass(frozen=True)
class TelegramIntakeResult:
    status: str
    message: str
    job_id: str | None = None
    product_factory_payload: dict[str, Any] | None = None
    sent_messages: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PendingSourceChoice:
    choice_id: str
    chat_id: str
    user_id: str
    model: str
    command: ProductFactoryCommand
    product: WarehouseProduct
    candidates: tuple[SourceResolutionCandidate, ...]
    preferred_sources: list[str]
    created_at: datetime
    expires_at: datetime

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


class PendingSourceChoiceStore:
    def __init__(self) -> None:
        self._choices: dict[str, PendingSourceChoice] = {}
        self._lock = threading.Lock()

    def create(
        self,
        *,
        chat_id: str,
        user_id: str,
        command: ProductFactoryCommand,
        product: WarehouseProduct,
        result: SourceResolutionResult,
        now: datetime,
    ) -> PendingSourceChoice:
        choice_id = secrets.token_urlsafe(8)
        choice = PendingSourceChoice(
            choice_id=choice_id,
            chat_id=chat_id,
            user_id=user_id,
            model=command.model,
            command=command,
            product=product,
            candidates=result.candidates,
            preferred_sources=result.config.preferred_source_names,
            created_at=now,
            expires_at=now + result.config.pending_choice_ttl,
        )
        with self._lock:
            self._choices[choice_id] = choice
        return choice

    def get(self, choice_id: str) -> PendingSourceChoice | None:
        with self._lock:
            return self._choices.get(choice_id)

    def delete(self, choice_id: str) -> None:
        with self._lock:
            self._choices.pop(choice_id, None)


DEFAULT_PENDING_SOURCE_CHOICES = PendingSourceChoiceStore()
_MODEL_RE = re.compile(r"^\d{6}$")
_PFSTATUS_USAGE = "Usage examples:\n/pfstatus <job_id>\n/pfstatus job_id: <job_id>\n/pfstatus job: <job_id>"
_STATUS_MODEL_USAGE = "Usage example:\nstatus 012345"


@dataclass(frozen=True)
class StatusCommand:
    kind: str
    job_id: str | None = None
    model: str | None = None


class StatusCommandParseError(ValueError):
    pass


def extract_telegram_identity(update: dict[str, Any]) -> TelegramIdentity:
    callback = _callback_query_payload(update)
    if callback:
        return TelegramIdentity(
            chat_id=_id_text(_nested(callback, "message", "chat", "id")),
            user_id=_id_text(_nested(callback, "from", "id")),
        )
    message = _message_payload(update)
    return TelegramIdentity(
        chat_id=_id_text(_nested(message, "chat", "id")),
        user_id=_id_text(_nested(message, "from", "id")),
    )


def is_authorized_telegram_identity(identity: TelegramIdentity, config: ProductFactoryTelegramConfig) -> bool:
    if not config.allowed_chat_ids and not config.allowed_user_ids:
        return False
    if config.allowed_chat_ids and identity.chat_id not in config.allowed_chat_ids:
        return False
    if config.allowed_user_ids and identity.user_id not in config.allowed_user_ids:
        return False
    return True


def process_telegram_product_factory_update(
    update: dict[str, Any],
    *,
    config: ProductFactoryTelegramConfig,
    telegram_client: TelegramMessenger,
    product_factory_client: ProductFactoryStarter,
    source_resolver: SourceResolver | None = None,
    pending_choices: PendingSourceChoiceStore = DEFAULT_PENDING_SOURCE_CHOICES,
) -> TelegramIntakeResult:
    callback = _callback_query_payload(update)
    if callback:
        return _process_source_choice_callback(
            callback,
            audit_log_path=config.audit_log_path,
            telegram_client=telegram_client,
            product_factory_client=product_factory_client,
            pending_choices=pending_choices,
        )

    message = _message_payload(update)
    chat_id = _id_text(_nested(message, "chat", "id"))
    user_id = _id_text(_nested(message, "from", "id")) or ""
    text = _message_text(message)
    if not chat_id or not text:
        return TelegramIntakeResult(status="ignored", message="No text command found.")

    sent_messages: list[str] = []

    def send(text_value: str, *, reply_markup: dict[str, Any] | None = None) -> None:
        telegram_client.send_message(chat_id, text_value, reply_markup=reply_markup)
        sent_messages.append(text_value)

    try:
        status_command = _parse_status_command(text)
    except StatusCommandParseError as exc:
        reply = str(exc)
        send(reply)
        _audit_event(
            config.audit_log_path,
            event_type="product_factory_status_failed",
            chat_id=chat_id,
            user_id=user_id,
            status="invalid_command",
            message=reply,
        )
        return TelegramIntakeResult(status="status_command_error", message=reply, sent_messages=sent_messages)
    if status_command is not None:
        _audit_event(
            config.audit_log_path,
            event_type="telegram_command_received",
            chat_id=chat_id,
            user_id=user_id,
            model=status_command.model,
            job_id=status_command.job_id,
            status="received",
            metadata={"command": status_command.kind},
        )
        return _process_status_command(
            status_command,
            chat_id=chat_id,
            user_id=user_id,
            audit_log_path=config.audit_log_path,
            product_factory_client=product_factory_client,
            send=send,
            sent_messages=sent_messages,
        )

    try:
        command = parse_product_factory_command(text)
    except ProductFactoryCommandParseError as exc:
        reply = f"Product Factory command error: {exc}"
        send(reply)
        return TelegramIntakeResult(status="command_error", message=reply, sent_messages=sent_messages)
    _audit_command_received(
        audit_log_path=config.audit_log_path,
        chat_id=chat_id,
        user_id=user_id,
        command=command,
    )

    try:
        product = lookup_warehouse_product(
            path=config.warehouse_catalog_path,
            model=command.model,
            model_column=config.warehouse_catalog_model_column,
            name_column=config.warehouse_catalog_name_column,
            encoding=config.warehouse_catalog_encoding,
        )
    except WarehouseCatalogError as exc:
        reply = f"ERP warehouse catalog error: {exc.message}"
        send(reply)
        _audit_event(
            config.audit_log_path,
            event_type="warehouse_lookup_failed",
            chat_id=chat_id,
            user_id=user_id,
            model=command.model,
            status=exc.code,
            message=exc.message,
        )
        return TelegramIntakeResult(status=exc.code, message=reply, sent_messages=sent_messages)
    _audit_product_event(
        config.audit_log_path,
        event_type="warehouse_lookup_succeeded",
        chat_id=chat_id,
        user_id=user_id,
        command=command,
        product=product,
        status="succeeded",
    )

    if command.manual_url is None:
        resolver = source_resolver
        if resolver is None:
            try:
                resolver = resolver_from_config_path(config.source_resolution_config_path)
            except SourceResolutionConfigError as exc:
                reply = f"Source resolution config error: {exc}"
                send(reply)
                _audit_product_event(
                    config.audit_log_path,
                    event_type="source_resolution_failed",
                    chat_id=chat_id,
                    user_id=user_id,
                    command=command,
                    product=product,
                    status="source_resolution_config_error",
                    message=str(exc),
                )
                return TelegramIntakeResult(status="source_resolution_config_error", message=reply, sent_messages=sent_messages)
        try:
            resolution = resolver.resolve(product=product)
        except (SourceResolutionConfigError, SourceResolutionError) as exc:
            reply = f"Source resolution error: {exc}"
            send(reply)
            _audit_product_event(
                config.audit_log_path,
                event_type="source_resolution_failed",
                chat_id=chat_id,
                user_id=user_id,
                command=command,
                product=product,
                status="source_resolution_error",
                message=str(exc),
            )
            return TelegramIntakeResult(status="source_resolution_error", message=reply, sent_messages=sent_messages)

        if resolution.selected is not None and resolution.selected.confidence >= resolution.config.minimum_confidence:
            selected = resolution.selected
            source_reply = _resolved_source_message(
                model=command.model,
                product=product,
                candidate=selected,
            )
            send(source_reply)
            _audit_candidate_event(
                config.audit_log_path,
                event_type="source_auto_selected",
                chat_id=chat_id,
                user_id=user_id,
                command=command,
                product=product,
                candidate=selected,
                selection_method=resolution.method,
                status="selected",
            )
            payload = _product_factory_payload(
                command_model=command.model,
                product=product,
                source_url=selected.url,
                bestprice_enabled=command.bestprice_enabled,
                skroutz_enabled=command.skroutz_enabled,
                boxnow_enabled=command.boxnow_enabled,
                telegram_chat_id=chat_id,
                source_resolution=resolution.metadata_for(selected),
            )
            return _enqueue_and_report(
                payload=payload,
                command=command,
                product=product,
                product_factory_client=product_factory_client,
                send=send,
                sent_messages=sent_messages,
                audit_log_path=config.audit_log_path,
                chat_id=chat_id,
                user_id=user_id,
                selected_source=selected.source_name,
                selected_url=selected.url,
                selected_title=selected.title,
                confidence=selected.confidence,
                selection_method=resolution.method,
            )

        if resolution.candidates:
            choice = pending_choices.create(
                chat_id=chat_id,
                user_id=user_id,
                command=command,
                product=product,
                result=resolution,
                now=datetime.now(timezone.utc),
            )
            reply = _suggestions_message(command.model, product, choice.candidates)
            send(reply, reply_markup=_source_choice_reply_markup(choice))
            _audit_product_event(
                config.audit_log_path,
                event_type="source_suggestions_sent",
                chat_id=chat_id,
                user_id=user_id,
                command=command,
                product=product,
                status="suggestions_sent",
                selection_method=resolution.method,
                metadata={
                    "choice_id": choice.choice_id,
                    "candidate_count": len(choice.candidates),
                    "candidates": [_candidate_metadata(candidate) for candidate in choice.candidates],
                    "expires_at": choice.expires_at.isoformat(),
                },
            )
            return TelegramIntakeResult(status="source_resolution_suggestions", message=reply, sent_messages=sent_messages)

        reply = (
            "No confident scrape source was found\n"
            f"model: {command.model}\n"
            f"product name: {product.name}\n"
            "Send the command again with a manual URL override."
        )
        send(reply)
        _audit_product_event(
            config.audit_log_path,
            event_type="source_resolution_no_usable_source",
            chat_id=chat_id,
            user_id=user_id,
            command=command,
            product=product,
            status="source_resolution_no_usable_source",
            message="No confident scrape source was found.",
            selection_method=resolution.method,
        )
        return TelegramIntakeResult(status="source_resolution_no_usable_source", message=reply, sent_messages=sent_messages)

    source_reply = _manual_source_message(command.manual_url)
    send(source_reply)
    _audit_product_event(
        config.audit_log_path,
        event_type="manual_url_selected",
        chat_id=chat_id,
        user_id=user_id,
        command=command,
        product=product,
        selected_source="Manual URL",
        selected_url=command.manual_url,
        confidence="manual override",
        selection_method="manual_url",
        status="selected",
    )

    payload = _product_factory_payload(
        command_model=command.model,
        product=product,
        source_url=command.manual_url,
        bestprice_enabled=command.bestprice_enabled,
        skroutz_enabled=command.skroutz_enabled,
        boxnow_enabled=command.boxnow_enabled,
        telegram_chat_id=chat_id,
        source_resolution=_manual_source_resolution(product=product, url=command.manual_url),
    )
    return _enqueue_and_report(
        payload=payload,
        command=command,
        product=product,
        product_factory_client=product_factory_client,
        send=send,
        sent_messages=sent_messages,
        audit_log_path=config.audit_log_path,
        chat_id=chat_id,
        user_id=user_id,
        selected_source="Manual URL",
        selected_url=command.manual_url,
        confidence="manual override",
        selection_method="manual_url",
    )


def _process_source_choice_callback(
    callback: dict[str, Any],
    *,
    audit_log_path: str,
    telegram_client: TelegramMessenger,
    product_factory_client: ProductFactoryStarter,
    pending_choices: PendingSourceChoiceStore,
) -> TelegramIntakeResult:
    chat_id = _id_text(_nested(callback, "message", "chat", "id"))
    user_id = _id_text(_nested(callback, "from", "id"))
    data = str(callback.get("data") or "").strip()
    if not chat_id:
        return TelegramIntakeResult(status="ignored", message="No callback chat found.")

    sent_messages: list[str] = []

    def send(text_value: str, *, reply_markup: dict[str, Any] | None = None) -> None:
        telegram_client.send_message(chat_id, text_value, reply_markup=reply_markup)
        sent_messages.append(text_value)

    parsed = _parse_source_choice_callback_data(data)
    if parsed is None:
        return TelegramIntakeResult(status="ignored", message="Unsupported callback data.")

    choice_id, action = parsed
    choice = pending_choices.get(choice_id)
    if choice is None:
        reply = "Source choice expired or is no longer available. Send the command again."
        send(reply)
        _audit_event(
            audit_log_path,
            event_type="source_choice_expired",
            chat_id=chat_id,
            user_id=user_id,
            status="source_choice_expired",
            message=reply,
            metadata={"choice_id": choice_id},
        )
        return TelegramIntakeResult(status="source_choice_expired", message=reply, sent_messages=sent_messages)
    if choice.chat_id != chat_id or choice.user_id != (user_id or ""):
        reply = "This source choice belongs to another chat or user."
        send(reply)
        return TelegramIntakeResult(status="source_choice_forbidden", message=reply, sent_messages=sent_messages)
    if choice.is_expired(datetime.now(timezone.utc)):
        pending_choices.delete(choice_id)
        reply = "Source choice expired. Send the command again."
        send(reply)
        _audit_product_event(
            audit_log_path,
            event_type="source_choice_expired",
            chat_id=chat_id,
            user_id=user_id,
            command=choice.command,
            product=choice.product,
            status="source_choice_expired",
            message=reply,
            metadata={"choice_id": choice_id},
        )
        return TelegramIntakeResult(status="source_choice_expired", message=reply, sent_messages=sent_messages)
    if action == "cancel":
        pending_choices.delete(choice_id)
        reply = "Source selection cancelled."
        send(reply)
        _audit_product_event(
            audit_log_path,
            event_type="source_suggestion_cancelled",
            chat_id=chat_id,
            user_id=user_id,
            command=choice.command,
            product=choice.product,
            status="source_choice_cancelled",
            message=reply,
            metadata={"choice_id": choice_id},
        )
        return TelegramIntakeResult(status="source_choice_cancelled", message=reply, sent_messages=sent_messages)

    try:
        selected = choice.candidates[int(action) - 1]
    except (ValueError, IndexError):
        reply = "Selected source choice is invalid. Send the command again."
        send(reply)
        return TelegramIntakeResult(status="source_choice_invalid", message=reply, sent_messages=sent_messages)

    send(_selected_choice_message(selected))
    _audit_candidate_event(
        audit_log_path,
        event_type="source_suggestion_selected",
        chat_id=chat_id,
        user_id=user_id,
        command=choice.command,
        product=choice.product,
        candidate=selected,
        selection_method="telegram_callback",
        status="selected",
        metadata={"choice_id": choice_id, "candidate_index": int(action)},
    )
    payload = _product_factory_payload(
        command_model=choice.command.model,
        product=choice.product,
        source_url=selected.url,
        bestprice_enabled=choice.command.bestprice_enabled,
        skroutz_enabled=choice.command.skroutz_enabled,
        boxnow_enabled=choice.command.boxnow_enabled,
        telegram_chat_id=chat_id,
        source_resolution=_candidate_source_resolution(
            candidate=selected,
            candidate_count=len(choice.candidates),
            preferred_sources=choice.preferred_sources,
        ),
    )
    result = _enqueue_and_report(
        payload=payload,
        command=choice.command,
        product=choice.product,
        product_factory_client=product_factory_client,
        send=send,
        sent_messages=sent_messages,
        audit_log_path=audit_log_path,
        chat_id=chat_id,
        user_id=user_id,
        selected_source=selected.source_name,
        selected_url=selected.url,
        selected_title=selected.title,
        confidence=selected.confidence,
        selection_method="telegram_callback",
    )
    if result.status == "queued":
        pending_choices.delete(choice_id)
    return result


def _enqueue_and_report(
    *,
    payload: dict[str, Any],
    command: ProductFactoryCommand,
    product: WarehouseProduct,
    product_factory_client: ProductFactoryStarter,
    send: Any,
    sent_messages: list[str],
    audit_log_path: str,
    chat_id: str,
    user_id: str | None,
    selected_source: str | None = None,
    selected_url: str | None = None,
    selected_title: str | None = None,
    confidence: int | str | None = None,
    selection_method: str | None = None,
) -> TelegramIntakeResult:
    try:
        job = product_factory_client.start_full_pipeline(payload)
    except ProductFactoryClientError as exc:
        reply = f"Product Factory error: {exc}"
        send(reply)
        _audit_product_event(
            audit_log_path,
            event_type="product_factory_enqueue_failed",
            chat_id=chat_id,
            user_id=user_id,
            command=command,
            product=product,
            selected_source=selected_source,
            selected_url=selected_url,
            selected_title=selected_title,
            confidence=confidence,
            selection_method=selection_method,
            status="failed",
            message=str(exc),
        )
        return TelegramIntakeResult(
            status="product_factory_error",
            message=reply,
            product_factory_payload=payload,
            sent_messages=sent_messages,
        )

    summary_reply = _job_started_message(command=command, product=product, job=job)
    send(summary_reply)
    _audit_product_event(
        audit_log_path,
        event_type="product_factory_enqueue_succeeded",
        chat_id=chat_id,
        user_id=user_id,
        command=command,
        product=product,
        selected_source=selected_source,
        selected_url=selected_url,
        selected_title=selected_title,
        confidence=confidence,
        selection_method=selection_method,
        job_id=job.job_id,
        status=job.status or "queued",
        message=job.message,
    )
    return TelegramIntakeResult(
        status="queued",
        message=summary_reply,
        job_id=job.job_id,
        product_factory_payload=payload,
        sent_messages=sent_messages,
    )


def _process_status_command(
    command: StatusCommand,
    *,
    chat_id: str,
    user_id: str,
    audit_log_path: str,
    product_factory_client: ProductFactoryStarter,
    send: Any,
    sent_messages: list[str],
) -> TelegramIntakeResult:
    try:
        if command.kind == "pfstatus":
            job_id = command.job_id or ""
            job = product_factory_client.get_job(job_id)
            reply = _job_status_message(job)
            send(reply)
            _audit_event(
                audit_log_path,
                event_type="product_factory_status_requested",
                chat_id=chat_id,
                user_id=user_id,
                model=job.model or None,
                job_id=job.job_id,
                status=job.status,
                message=job.message,
                metadata={"command": "pfstatus"},
            )
            return TelegramIntakeResult(
                status="status_reported",
                message=reply,
                job_id=job.job_id,
                sent_messages=sent_messages,
            )

        model = command.model or ""
        audit_job_id = latest_enqueued_job_for_model(audit_log_path, model)
        if audit_job_id:
            job = product_factory_client.get_job(audit_job_id)
        else:
            jobs = product_factory_client.list_jobs_by_model(model)
            if not jobs:
                reply = f"No Product Factory job found for model {model}."
                send(reply)
                _audit_event(
                    audit_log_path,
                    event_type="product_factory_status_requested",
                    chat_id=chat_id,
                    user_id=user_id,
                    model=model,
                    status="not_found",
                    message=reply,
                    metadata={"command": "status"},
                )
                return TelegramIntakeResult(status="status_not_found", message=reply, sent_messages=sent_messages)
            job = jobs[0]

        reply = _job_status_message(job)
        send(reply)
        _audit_event(
            audit_log_path,
            event_type="product_factory_status_requested",
            chat_id=chat_id,
            user_id=user_id,
            model=model,
            job_id=job.job_id,
            status=job.status,
            message=job.message,
            metadata={"command": "status", "source": "audit" if audit_job_id else "by_model"},
        )
        return TelegramIntakeResult(
            status="status_reported",
            message=reply,
            job_id=job.job_id,
            sent_messages=sent_messages,
        )
    except ProductFactoryClientError as exc:
        reply = f"Product Factory status error: {exc}"
        send(reply)
        _audit_event(
            audit_log_path,
            event_type="product_factory_status_failed",
            chat_id=chat_id,
            user_id=user_id,
            model=command.model,
            job_id=command.job_id,
            status="failed",
            message=str(exc),
            metadata={"command": command.kind},
        )
        return TelegramIntakeResult(status="status_error", message=reply, sent_messages=sent_messages)


def _parse_status_command(text: str) -> StatusCommand | None:
    tokens = str(text or "").split(maxsplit=1)
    if not tokens:
        return None
    command = tokens[0].casefold()
    rest = tokens[1].strip() if len(tokens) > 1 else ""
    if command == "/pfstatus" or command.startswith("/pfstatus@"):
        job_id = _parse_pfstatus_job_id(rest)
        if job_id is None:
            raise StatusCommandParseError(f"Invalid /pfstatus command.\n{_PFSTATUS_USAGE}")
        return StatusCommand(kind="pfstatus", job_id=job_id)
    if command == "status":
        model_tokens = rest.split()
        if len(model_tokens) != 1 or not _MODEL_RE.fullmatch(model_tokens[0]):
            raise StatusCommandParseError(f"Invalid status command.\n{_STATUS_MODEL_USAGE}")
        return StatusCommand(kind="status", model=model_tokens[0])
    return None


def _parse_pfstatus_job_id(rest: str) -> str | None:
    if not rest:
        return None
    raw_tokens = rest.split()
    if len(raw_tokens) == 1 and ":" not in raw_tokens[0]:
        return raw_tokens[0]
    match = re.fullmatch(r"(?i)job(?:_id)?\s*:\s*(\S+)", rest)
    if match:
        return match.group(1)
    return None


def _job_status_message(job: ProductFactoryJob) -> str:
    return "\n".join(
        [
            "Product Factory status",
            f"job_id: {job.job_id}",
            f"type: {job.job_type or '-'}",
            f"model: {job.model or '-'}",
            f"status: {job.status or '-'}",
            f"message: {job.message or '-'}",
            f"error: {job.error or '-'}",
            f"updated_at: {job.updated_at or '-'}",
        ]
    )


def _audit_command_received(
    *,
    audit_log_path: str,
    chat_id: str,
    user_id: str,
    command: ProductFactoryCommand,
) -> None:
    _audit_product_event(
        audit_log_path,
        event_type="telegram_command_received",
        chat_id=chat_id,
        user_id=user_id,
        command=command,
        product=None,
        status="received",
    )


def _audit_product_event(
    audit_log_path: str,
    *,
    event_type: str,
    chat_id: str | None,
    user_id: str | None,
    command: ProductFactoryCommand,
    product: WarehouseProduct | None,
    selected_source: str | None = None,
    selected_url: str | None = None,
    selected_title: str | None = None,
    confidence: int | str | None = None,
    selection_method: str | None = None,
    job_id: str | None = None,
    status: str | None = None,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    _audit_event(
        audit_log_path,
        event_type=event_type,
        chat_id=chat_id,
        user_id=user_id,
        model=command.model,
        product_name=product.name if product else None,
        bestprice_enabled=command.bestprice_enabled,
        skroutz_enabled=command.skroutz_enabled,
        boxnow_enabled=command.boxnow_enabled,
        selected_source=selected_source,
        selected_url=selected_url,
        selected_title=selected_title,
        confidence=confidence,
        selection_method=selection_method,
        job_id=job_id,
        status=status,
        message=message,
        metadata=metadata,
    )


def _audit_candidate_event(
    audit_log_path: str,
    *,
    event_type: str,
    chat_id: str | None,
    user_id: str | None,
    command: ProductFactoryCommand,
    product: WarehouseProduct,
    candidate: SourceResolutionCandidate,
    selection_method: str,
    status: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    _audit_product_event(
        audit_log_path,
        event_type=event_type,
        chat_id=chat_id,
        user_id=user_id,
        command=command,
        product=product,
        selected_source=candidate.source_name,
        selected_url=candidate.url,
        selected_title=candidate.title,
        confidence=candidate.confidence,
        selection_method=selection_method,
        status=status,
        metadata=metadata,
    )


def _audit_event(audit_log_path: str, **kwargs: Any) -> None:
    append_event(path=audit_log_path, **kwargs)


def _candidate_metadata(candidate: SourceResolutionCandidate) -> dict[str, Any]:
    return {
        "source_name": candidate.source_name,
        "url": candidate.url,
        "title": candidate.title,
        "confidence": candidate.confidence,
    }


def _product_factory_payload(
    *,
    command_model: str,
    product: WarehouseProduct,
    source_url: str,
    bestprice_enabled: bool,
    skroutz_enabled: bool,
    boxnow_enabled: bool,
    telegram_chat_id: str,
    source_resolution: dict[str, Any],
) -> dict[str, Any]:
    source_resolution = dict(source_resolution)
    if product.metadata:
        source_resolution["warehouse_metadata"] = dict(product.metadata)
    return {
        "model": command_model,
        "product_name": product.name,
        "source_url": source_url,
        "bestprice_enabled": bestprice_enabled,
        "skroutz_enabled": skroutz_enabled,
        "boxnow_enabled": boxnow_enabled,
        "photos": FULL_GALLERY_PHOTOS,
        "sections": DEFAULT_SECTIONS,
        "trigger_source": "telegram",
        "telegram_chat_id": telegram_chat_id,
        "source_resolution": source_resolution,
    }


def _manual_source_resolution(*, product: WarehouseProduct, url: str) -> dict[str, Any]:
    del product
    return {
        "method": "manual_url",
        "manual_override": True,
        "selected_source": "Manual URL",
        "selected_url": url,
        "confidence": "manual override",
    }


def _candidate_source_resolution(
    *,
    candidate: SourceResolutionCandidate,
    candidate_count: int,
    preferred_sources: list[str],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "method": "brave_weighted",
        "selected_source": candidate.source_name,
        "selected_url": candidate.url,
        "confidence": candidate.confidence,
        "candidate_count": candidate_count,
        "preferred_sources": preferred_sources,
    }
    if candidate.title:
        payload["selected_title"] = candidate.title
    return payload


def _manual_source_message(url: str) -> str:
    return (
        "Selected scrape source: Manual URL\n"
        f"URL: {url}\n"
        "Confidence: manual override"
    )


def _resolved_source_message(*, model: str, product: WarehouseProduct, candidate: SourceResolutionCandidate) -> str:
    lines = [
        "Resolved Product Factory source",
        f"model: {model}",
        f"product name: {product.name}",
        f"selected source: {candidate.source_name}",
    ]
    if candidate.title:
        lines.append(f"page title: {candidate.title}")
    lines.extend(
        [
            f"URL: {candidate.url}",
            f"confidence: {candidate.confidence}",
        ]
    )
    return "\n".join(lines)


def _selected_choice_message(candidate: SourceResolutionCandidate) -> str:
    lines = [
        "Selected scrape source",
        f"source: {candidate.source_name}",
    ]
    if candidate.title:
        lines.append(f"page title: {candidate.title}")
    lines.extend(
        [
            f"URL: {candidate.url}",
            f"confidence: {candidate.confidence}",
        ]
    )
    return "\n".join(lines)


def _suggestions_message(model: str, product: WarehouseProduct, candidates: tuple[SourceResolutionCandidate, ...]) -> str:
    lines = [
        "Choose a scrape source",
        f"model: {model}",
        f"product name: {product.name}",
    ]
    for index, candidate in enumerate(candidates, start=1):
        lines.extend(
            [
                f"{index}. {candidate.source_name}",
                f"title: {candidate.title or '-'}",
                f"URL: {candidate.url}",
                f"confidence: {candidate.confidence}",
            ]
        )
    return "\n".join(lines)


def _source_choice_reply_markup(choice: PendingSourceChoice) -> dict[str, Any]:
    buttons = [
        {"text": f"Use {index}", "callback_data": f"pfsrc:{choice.choice_id}:{index}"}
        for index, _candidate in enumerate(choice.candidates, start=1)
    ]
    return {
        "inline_keyboard": [
            buttons,
            [{"text": "Cancel", "callback_data": f"pfsrc:{choice.choice_id}:cancel"}],
        ]
    }


def _job_started_message(*, command: ProductFactoryCommand, product: WarehouseProduct, job: ProductFactoryJob) -> str:
    return (
        f"Product Factory job started\n"
        f"model: {command.model}\n"
        f"product name: {product.name}\n"
        f"job_id: {job.job_id}\n"
        f"BestPrice: {_yes_no(command.bestprice_enabled)}\n"
        f"Skroutz: {_yes_no(command.skroutz_enabled)}\n"
        f"BoxNow: {_yes_no(command.boxnow_enabled)}"
    )


def _parse_source_choice_callback_data(data: str) -> tuple[str, str] | None:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "pfsrc":
        return None
    choice_id = parts[1].strip()
    action = parts[2].strip().casefold()
    if not choice_id or (action != "cancel" and not action.isdigit()):
        return None
    return choice_id, action


def _callback_query_payload(update: dict[str, Any]) -> dict[str, Any]:
    value = update.get("callback_query")
    return value if isinstance(value, dict) else {}


def _message_payload(update: dict[str, Any]) -> dict[str, Any]:
    for key in ("message", "edited_message"):
        value = update.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _message_text(message: dict[str, Any]) -> str:
    value = message.get("text")
    return str(value).strip() if value is not None else ""


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _id_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
