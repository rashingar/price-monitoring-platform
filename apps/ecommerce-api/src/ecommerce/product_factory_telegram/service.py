"""Telegram Product Factory intake orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .client import ProductFactoryClientError, ProductFactoryJob
from .config import ProductFactoryTelegramConfig
from .parser import ProductFactoryCommandParseError, parse_product_factory_command
from .warehouse import WarehouseCatalogError, WarehouseProduct, lookup_warehouse_product


FULL_GALLERY_PHOTOS = 20
DEFAULT_SECTIONS = 20


class TelegramMessenger(Protocol):
    def send_message(self, chat_id: str, text: str) -> None: ...


class ProductFactoryStarter(Protocol):
    def start_full_pipeline(self, payload: dict[str, Any]) -> ProductFactoryJob: ...


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


def extract_telegram_identity(update: dict[str, Any]) -> TelegramIdentity:
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
) -> TelegramIntakeResult:
    message = _message_payload(update)
    chat_id = _id_text(_nested(message, "chat", "id"))
    text = _message_text(message)
    if not chat_id or not text:
        return TelegramIntakeResult(status="ignored", message="No text command found.")

    sent_messages: list[str] = []

    def send(text_value: str) -> None:
        telegram_client.send_message(chat_id, text_value)
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
        reply = (
            "Automatic source resolution is not implemented yet; no Product Factory job was started. "
            "Send the model with an absolute http/https product URL."
        )
        send(reply)
        return TelegramIntakeResult(status="source_resolution_not_implemented", message=reply, sent_messages=sent_messages)

    source_reply = (
        "Selected scrape source: Manual URL\n"
        f"URL: {command.manual_url}\n"
        "Confidence: manual override"
    )
    send(source_reply)

    payload = _product_factory_payload(
        command_model=command.model,
        product=product,
        source_url=command.manual_url,
        bestprice_enabled=command.bestprice_enabled,
        skroutz_enabled=command.skroutz_enabled,
        boxnow_enabled=command.boxnow_enabled,
        telegram_chat_id=chat_id,
    )
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

    summary_reply = (
        f"Product Factory job started\n"
        f"model: {command.model}\n"
        f"product name: {product.name}\n"
        f"job_id: {job.job_id}\n"
        f"BestPrice: {_yes_no(command.bestprice_enabled)}\n"
        f"Skroutz: {_yes_no(command.skroutz_enabled)}\n"
        f"BoxNow: {_yes_no(command.boxnow_enabled)}"
    )
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
) -> dict[str, Any]:
    source_resolution: dict[str, Any] = {
        "method": "manual_url",
        "manual_override": True,
    }
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
