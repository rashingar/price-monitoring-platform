"""Telegram Product Factory intake orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import secrets
import threading
from typing import Any, Protocol

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
        command = parse_product_factory_command(text)
    except ProductFactoryCommandParseError as exc:
        reply = f"Product Factory command error: {exc}"
        send(reply)
        return TelegramIntakeResult(status="command_error", message=reply, sent_messages=sent_messages)

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
        return TelegramIntakeResult(status=exc.code, message=reply, sent_messages=sent_messages)

    if command.manual_url is None:
        resolver = source_resolver
        if resolver is None:
            try:
                resolver = resolver_from_config_path(config.source_resolution_config_path)
            except SourceResolutionConfigError as exc:
                reply = f"Source resolution config error: {exc}"
                send(reply)
                return TelegramIntakeResult(status="source_resolution_config_error", message=reply, sent_messages=sent_messages)
        try:
            resolution = resolver.resolve(product=product)
        except (SourceResolutionConfigError, SourceResolutionError) as exc:
            reply = f"Source resolution error: {exc}"
            send(reply)
            return TelegramIntakeResult(status="source_resolution_error", message=reply, sent_messages=sent_messages)

        if resolution.selected is not None and resolution.selected.confidence >= resolution.config.minimum_confidence:
            selected = resolution.selected
            source_reply = _resolved_source_message(
                model=command.model,
                product=product,
                candidate=selected,
            )
            send(source_reply)
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
            return TelegramIntakeResult(status="source_resolution_suggestions", message=reply, sent_messages=sent_messages)

        reply = (
            "No confident scrape source was found\n"
            f"model: {command.model}\n"
            f"product name: {product.name}\n"
            "Send the command again with a manual URL override."
        )
        send(reply)
        return TelegramIntakeResult(status="source_resolution_no_usable_source", message=reply, sent_messages=sent_messages)

    source_reply = _manual_source_message(command.manual_url)
    send(source_reply)

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
    )


def _process_source_choice_callback(
    callback: dict[str, Any],
    *,
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
        return TelegramIntakeResult(status="source_choice_expired", message=reply, sent_messages=sent_messages)
    if choice.chat_id != chat_id or choice.user_id != (user_id or ""):
        reply = "This source choice belongs to another chat or user."
        send(reply)
        return TelegramIntakeResult(status="source_choice_forbidden", message=reply, sent_messages=sent_messages)
    if choice.is_expired(datetime.now(timezone.utc)):
        pending_choices.delete(choice_id)
        reply = "Source choice expired. Send the command again."
        send(reply)
        return TelegramIntakeResult(status="source_choice_expired", message=reply, sent_messages=sent_messages)
    if action == "cancel":
        pending_choices.delete(choice_id)
        reply = "Source selection cancelled."
        send(reply)
        return TelegramIntakeResult(status="source_choice_cancelled", message=reply, sent_messages=sent_messages)

    try:
        selected = choice.candidates[int(action) - 1]
    except (ValueError, IndexError):
        reply = "Selected source choice is invalid. Send the command again."
        send(reply)
        return TelegramIntakeResult(status="source_choice_invalid", message=reply, sent_messages=sent_messages)

    send(_selected_choice_message(selected))
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
) -> TelegramIntakeResult:
    try:
        job = product_factory_client.start_full_pipeline(payload)
    except ProductFactoryClientError as exc:
        reply = f"Product Factory error: {exc}"
        send(reply)
        return TelegramIntakeResult(
            status="product_factory_error",
            message=reply,
            product_factory_payload=payload,
            sent_messages=sent_messages,
        )

    summary_reply = _job_started_message(command=command, product=product, job=job)
    send(summary_reply)
    return TelegramIntakeResult(
        status="queued",
        message=summary_reply,
        job_id=job.job_id,
        product_factory_payload=payload,
        sent_messages=sent_messages,
    )


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
