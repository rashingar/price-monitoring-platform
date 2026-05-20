"""Environment-backed config for Telegram Product Factory intake."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .audit import DEFAULT_AUDIT_LOG_PATH


@dataclass(frozen=True)
class ProductFactoryTelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    webhook_secret: str = ""
    allowed_chat_ids: set[str] = field(default_factory=set)
    allowed_user_ids: set[str] = field(default_factory=set)
    warehouse_catalog_path: str = ""
    warehouse_catalog_model_column: str = "model"
    warehouse_catalog_name_column: str = "name"
    warehouse_catalog_encoding: str = "utf-8-sig"
    product_factory_api_base_url: str = "http://127.0.0.1:8000"
    source_resolution_config_path: str = ""
    audit_log_path: str = DEFAULT_AUDIT_LOG_PATH


def product_factory_telegram_config_from_env() -> ProductFactoryTelegramConfig:
    return ProductFactoryTelegramConfig(
        enabled=_env_bool("PRODUCT_FACTORY_TELEGRAM_ENABLED", default=False),
        bot_token=_env_text("PRODUCT_FACTORY_TELEGRAM_BOT_TOKEN"),
        webhook_secret=_env_text("PRODUCT_FACTORY_TELEGRAM_WEBHOOK_SECRET"),
        allowed_chat_ids=_env_id_set("PRODUCT_FACTORY_TELEGRAM_ALLOWED_CHAT_IDS"),
        allowed_user_ids=_env_id_set("PRODUCT_FACTORY_TELEGRAM_ALLOWED_USER_IDS"),
        warehouse_catalog_path=_env_text("PRODUCT_FACTORY_WAREHOUSE_CATALOG_PATH"),
        warehouse_catalog_model_column=_env_text(
            "PRODUCT_FACTORY_WAREHOUSE_CATALOG_MODEL_COLUMN"
        )
        or "model",
        warehouse_catalog_name_column=_env_text(
            "PRODUCT_FACTORY_WAREHOUSE_CATALOG_NAME_COLUMN"
        )
        or "name",
        warehouse_catalog_encoding=_env_text(
            "PRODUCT_FACTORY_WAREHOUSE_CATALOG_ENCODING"
        )
        or "utf-8-sig",
        product_factory_api_base_url=_env_text("PRODUCT_FACTORY_API_BASE_URL")
        or "http://127.0.0.1:8000",
        source_resolution_config_path=_env_text(
            "PRODUCT_FACTORY_SOURCE_RESOLUTION_CONFIG_PATH"
        ),
        audit_log_path=_env_text("PRODUCT_FACTORY_TELEGRAM_AUDIT_LOG_PATH")
        or DEFAULT_AUDIT_LOG_PATH,
    )


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_text(name: str) -> str:
    return os.getenv(name, "").strip()


def _env_id_set(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {item.strip() for item in raw.replace(";", ",").split(",") if item.strip()}
