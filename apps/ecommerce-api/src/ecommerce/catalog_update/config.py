"""Catalog update configuration loading and validation."""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

from ecommerce.catalog_update.types import (
    DEFAULT_EXPORT_PROFILE,
    DEFAULT_EXPORT_TIMEOUT_SECONDS,
    CatalogUpdateConfig,
    CatalogUpdateConfigError,
)
from ecommerce.env import load_local_env_if_present


def load_catalog_update_config() -> CatalogUpdateConfig:
    load_local_env_if_present()
    missing = [
        name
        for name in (
            "OPENCART_STORE_BASE",
            "OPENCART_ADMIN_PATH",
            "OPENCART_ADMIN_USER",
            "OPENCART_ADMIN_PASS",
        )
        if not env_text(name)
    ]
    if missing:
        raise CatalogUpdateConfigError(f"Missing OpenCart export env config: {', '.join(missing)}")

    return CatalogUpdateConfig(
        store_base=env_text("OPENCART_STORE_BASE") or "",
        admin_path=env_text("OPENCART_ADMIN_PATH") or "",
        admin_user=env_text("OPENCART_ADMIN_USER") or "",
        admin_pass=env_text("OPENCART_ADMIN_PASS") or "",
        export_profile=env_text("OPENCART_EXPORT_PROFILE") or DEFAULT_EXPORT_PROFILE,
        timeout_seconds=env_int("OPENCART_EXPORT_TIMEOUT_SECONDS", DEFAULT_EXPORT_TIMEOUT_SECONDS),
        headed=env_bool("OPENCART_EXPORT_HEADED", False),
    )


def normalize_admin_path(admin_path: str) -> str:
    value = (admin_path or "").strip().replace("\\", "/")
    if not value:
        return "/index.php"
    if re.match(r"^[A-Za-z]:/", value):
        parts = [part for part in value.split("/") if part]
        if len(parts) >= 2 and parts[-1].lower() == "index.php":
            return "/" + "/".join(parts[-2:])
    if "://" in value:
        return urlparse(value).path or "/index.php"
    return value if value.startswith("/") else f"/{value}"


def build_admin_index(store_base: str, admin_path: str) -> str:
    normalized_admin_path = normalize_admin_path(admin_path)
    return f"{store_base.rstrip('/')}/{normalized_admin_path.lstrip('/')}"


def env_text(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    text = value.strip()
    return text or None


def env_int(name: str, default: int) -> int:
    value = env_text(name)
    if value is None:
        return default
    try:
        return max(1, int(value))
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    value = env_text(name)
    if value is None:
        return default
    return value.casefold() in {"1", "true", "yes", "on", "headed"}
