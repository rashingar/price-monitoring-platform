"""Failure diagnostics for OpenCart export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ecommerce.catalog_update.paths import display_path
from ecommerce.catalog_update.redaction import (
    REDACTED_VALUE,
    redact_opencart_sensitive_data,
    redact_opencart_url,
)
from ecommerce.catalog_update.types import CatalogUpdateConfig


def capture_export_failure_diagnostics(
    *,
    job_id: str,
    output_dir: Path,
    config: CatalogUpdateConfig,
    step: str,
    page: Any | None,
    error: BaseException,
) -> Path | None:
    try:
        diagnostics_dir = output_dir / "diagnostics"
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = diagnostics_dir / "failure.png"
        screenshot_saved = False
        screenshot_error: str | None = None
        if page is not None:
            try:
                redact_visible_credentials(page)
                page.screenshot(path=str(screenshot_path), full_page=True)
                screenshot_saved = screenshot_path.exists()
            except Exception as screenshot_exc:
                screenshot_error = redact_opencart_sensitive_data(
                    str(screenshot_exc) or screenshot_exc.__class__.__name__, config
                )

        context_path = diagnostics_dir / "failure_context.json"
        context: dict[str, Any] = {
            "job_id": job_id,
            "step": step,
            "current_url": (
                redact_opencart_url(getattr(page, "url", ""), config)
                if page is not None
                else None
            ),
            "export_profile": redact_opencart_sensitive_data(
                config.export_profile, config
            ),
            "timeout_seconds": config.timeout_seconds,
            "headed": config.headed,
            "error_class": error.__class__.__name__,
            "sanitized_error_message": redact_opencart_sensitive_data(
                str(error) or error.__class__.__name__, config
            ),
            "timestamp": now_iso(),
        }
        if screenshot_saved:
            context["screenshot_path"] = display_path(screenshot_path)
        if screenshot_error:
            context["screenshot_error"] = screenshot_error
        context_path.write_text(
            json.dumps(context, indent=2, sort_keys=True), encoding="utf-8"
        )
        return diagnostics_dir
    except Exception:
        return None


def redact_visible_credentials(page: Any) -> None:
    for selector, value in (
        ('input[name="password"]', ""),
        ('input[name="username"]', REDACTED_VALUE),
    ):
        try:
            locator = page.locator(selector).first
            locator.fill(value)
        except Exception:
            pass


def format_export_failure(
    message: str,
    *,
    step: str,
    diagnostics_dir: Path | None,
    config: CatalogUpdateConfig,
) -> str:
    safe_message = redact_opencart_sensitive_data(message, config)
    if safe_message.startswith("OpenCart export failed"):
        base = f"{safe_message} Step: {step}."
    else:
        base = f"OpenCart export failed at step {step}: {safe_message}"
    if diagnostics_dir is not None:
        base = f"{base} Diagnostics saved to {display_path(diagnostics_dir)}."
    return base


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
