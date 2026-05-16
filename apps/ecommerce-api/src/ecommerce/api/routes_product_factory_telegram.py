"""Telegram webhook for Product Factory intake."""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from ecommerce.product_factory_telegram.client import ProductFactoryClient, TelegramBotClient, TelegramDeliveryError
from ecommerce.product_factory_telegram.config import ProductFactoryTelegramConfig, product_factory_telegram_config_from_env
from ecommerce.product_factory_telegram.service import (
    DEFAULT_PENDING_SOURCE_CHOICES,
    extract_telegram_identity,
    is_authorized_telegram_identity,
    process_telegram_product_factory_update,
)

router = APIRouter(prefix="/api/product-factory/telegram", tags=["product-factory-telegram"])


class ProductFactoryTelegramWebhookResponse(BaseModel):
    status: str
    message: str
    job_id: str | None = None


@router.post("/webhook", response_model=ProductFactoryTelegramWebhookResponse)
def product_factory_telegram_webhook(
    update: dict[str, Any],
    x_telegram_bot_api_secret_token: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> ProductFactoryTelegramWebhookResponse:
    config = product_factory_telegram_config_from_env()
    _validate_webhook_security(update, x_telegram_bot_api_secret_token, config)

    try:
        result = process_telegram_product_factory_update(
            update,
            config=config,
            telegram_client=_telegram_client(config),
            product_factory_client=_product_factory_client(config),
            pending_choices=DEFAULT_PENDING_SOURCE_CHOICES,
        )
    except TelegramDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "Telegram message delivery failed.", "code": "telegram_delivery_failed"},
        ) from exc

    return ProductFactoryTelegramWebhookResponse(
        status=result.status,
        message=result.message,
        job_id=result.job_id,
    )


def _validate_webhook_security(
    update: dict[str, Any],
    secret_header: str | None,
    config: ProductFactoryTelegramConfig,
) -> None:
    if not config.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": "Telegram Product Factory intake is disabled.", "code": "telegram_intake_disabled"},
        )
    if not config.webhook_secret or not secret_header or not hmac.compare_digest(secret_header, config.webhook_secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    identity = extract_telegram_identity(update)
    if not is_authorized_telegram_identity(identity, config):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _telegram_client(config: ProductFactoryTelegramConfig) -> TelegramBotClient:
    return TelegramBotClient(config.bot_token)


def _product_factory_client(config: ProductFactoryTelegramConfig) -> ProductFactoryClient:
    return ProductFactoryClient(config.product_factory_api_base_url)
