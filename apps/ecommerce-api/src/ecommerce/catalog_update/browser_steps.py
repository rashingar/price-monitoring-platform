"""Low-level Playwright interactions for the OpenCart CSV export."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from ecommerce.catalog_update.progress import (
    CATALOG_UPDATE_HEARTBEAT_INTERVAL_SECONDS,
    CatalogUpdateStepTracker,
)
from ecommerce.catalog_update.paths import safe_filename
from ecommerce.catalog_update.types import (
    DEFAULT_EXPORT_PROFILE,
    CatalogUpdateConfig,
    CatalogUpdateError,
)

CSV_PRODUCT_EXPORT_ROUTE = (
    "extension/ka_extensions/csv_product_export/ka_product_export"
)


def login_to_opencart(page: Any, config: CatalogUpdateConfig, timeout_ms: int) -> None:
    login_url = f"{config.admin_index_url}?route=common/login"
    page.goto(login_url, wait_until="domcontentloaded", timeout=timeout_ms)

    user = page.locator('input[name="username"]')
    password = page.locator('input[name="password"]')
    user.wait_for(state="visible", timeout=timeout_ms)
    user.fill(config.admin_user)
    password.fill(config.admin_pass)

    page.locator('button[type="submit"], input[type="submit"]').first.click()
    page.wait_for_load_state("networkidle", timeout=timeout_ms)

    if "route=common/login" in page.url:
        raise CatalogUpdateError("OpenCart login failed: still on login route.")


def append_session_token(target_url: str, current_url: str) -> str:
    user_token = parse_qs(urlparse(current_url).query).get("user_token", [None])[0]
    if not user_token:
        return target_url

    separator = "&" if urlparse(target_url).query else "?"
    return f"{target_url}{separator}user_token={quote(user_token, safe='')}"


def open_csv_product_export(
    page: Any, config: CatalogUpdateConfig, timeout_ms: int
) -> None:
    export_url = append_session_token(
        f"{config.admin_index_url}?route={CSV_PRODUCT_EXPORT_ROUTE}",
        page.url,
    )
    page.goto(export_url, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_load_state("networkidle", timeout=timeout_ms)
    page.locator('select[name="profile_id"]').wait_for(
        state="visible", timeout=timeout_ms
    )


def navigate_to_csv_product_export(page: Any) -> None:
    for label in ("System", "Σύστημα"):
        if try_click_text(page, label):
            break
    if not try_click_text(page, "CSV Product Export"):
        raise CatalogUpdateError(
            "OpenCart export failed: CSV Product Export menu item not found."
        )
    wait_for_text(page, ("STEP 1", "Step 1", "ΒΗΜΑ 1"))


def load_export_profile(page: Any, export_profile: str) -> None:
    select_locator = page.locator('select[name="profile_id"]').first
    select_locator.wait_for(state="visible")
    try:
        select_locator.select_option(label=export_profile)
    except Exception:
        select_locator.select_option(export_profile)
    page.locator('input[value="Load"], button:has-text("Load")').first.click()
    click_first_locator(
        page,
        (
            'button[form="form-step1"]:has-text("Next")',
            'button[type="submit"][form="form-step1"]',
            'input[type="submit"][value="Next"]',
            'button:has-text("Next")',
            'a:has-text("Next")',
        ),
        "OpenCart export failed: Step 1 Next button not found.",
    )
    page.wait_for_load_state("networkidle")
    wait_for_text(page, ("STEP 2", "Step 2", "ΒΗΜΑ 2"))


def advance_export_step_two(page: Any) -> None:
    click_first_locator(
        page,
        (
            'button[form="form-step2"]:has-text("Next")',
            'button[type="submit"][form="form-step2"]',
            'input[type="submit"][value="Next"]',
            'button:has-text("Next")',
            'a:has-text("Next")',
        ),
        "OpenCart export failed: Step 2 Next button not found.",
    )
    page.wait_for_load_state("networkidle")
    wait_for_text(page, ("STEP 3", "Step 3", "ΒΗΜΑ 3"))


def download_export(
    page: Any,
    output_dir: Path,
    timeout_ms: int,
    *,
    step_tracker: CatalogUpdateStepTracker | None = None,
) -> Path:
    download_control = download_locator(page, timeout_ms, step_tracker=step_tracker)
    with page.expect_download() as download_info:
        download_control.click()
    download = download_info.value
    filename = safe_filename(
        download.suggested_filename or f"{DEFAULT_EXPORT_PROFILE}.csv",
        default=f"{DEFAULT_EXPORT_PROFILE}.csv",
    )
    downloaded_path = output_dir / filename
    if step_tracker is not None:
        step_tracker.mark("save_download")
    download.save_as(downloaded_path)
    if not downloaded_path.exists():
        raise CatalogUpdateError("OpenCart export failed: download missing after save.")
    if step_tracker is not None:
        step_tracker.emit_progress(
            "download_saved",
            details={
                "downloaded_filename": downloaded_path.name,
                "downloaded_file_size": downloaded_path.stat().st_size,
            },
        )
    return downloaded_path


def download_locator(
    page: Any, timeout_ms: int, *, step_tracker: CatalogUpdateStepTracker | None = None
) -> Any:
    pattern = re.compile(r"download", re.IGNORECASE)
    deadline = time.monotonic() + max(1, timeout_ms / 1000)
    next_heartbeat = time.monotonic()
    while time.monotonic() < deadline:
        if step_tracker is not None and time.monotonic() >= next_heartbeat:
            step_tracker.mark("wait_for_download")
            next_heartbeat = (
                time.monotonic() + CATALOG_UPDATE_HEARTBEAT_INTERVAL_SECONDS
            )
        candidates = (
            page.get_by_role("link", name=pattern),
            page.get_by_role("button", name=pattern),
            page.locator("a").filter(has_text=pattern),
            page.locator("button").filter(has_text=pattern),
        )
        for locator in candidates:
            first = locator.first
            try:
                first.wait_for(state="visible", timeout=500)
                return first
            except Exception:
                pass
        time.sleep(1)
    raise CatalogUpdateError("OpenCart export failed: download link not found.")


def fill_first(page: Any, selectors: tuple[str, ...], value: str) -> None:
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count() > 0:
            locator.fill(value)
            return
    raise CatalogUpdateError(
        f"OpenCart login failed: field not found for selectors {', '.join(selectors)}."
    )


def click_by_role_or_text(
    page: Any, labels: tuple[str, ...], *, roles: tuple[str, ...]
) -> None:
    for role in roles:
        for label in labels:
            locator = page.get_by_role(
                role, name=re.compile(re.escape(label), re.IGNORECASE)
            )
            if locator.count() > 0:
                locator.first.click()
                return
    for label in labels:
        if try_click_text(page, label):
            return
    raise CatalogUpdateError(f"OpenCart export failed: control not found: {labels[0]}.")


def try_click_text(page: Any, label: str) -> bool:
    locator = page.get_by_text(re.compile(re.escape(label), re.IGNORECASE)).first
    if locator.count() <= 0:
        return False
    locator.click()
    return True


def wait_for_text(page: Any, labels: tuple[str, ...]) -> None:
    pattern = re.compile("|".join(re.escape(label) for label in labels), re.IGNORECASE)
    page.get_by_text(pattern).first.wait_for(state="visible")


def click_first_locator(
    page: Any, selectors: tuple[str, ...], error_message: str
) -> None:
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count() > 0:
            locator.first.click()
            return
    raise CatalogUpdateError(error_message)
