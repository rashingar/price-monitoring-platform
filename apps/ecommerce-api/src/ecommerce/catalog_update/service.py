"""OpenCart catalog export and Ecommerce catalog ingestion orchestration."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ecommerce.catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.config import get_database_url, sanitize_database_error
from ecommerce.env import load_local_env_if_present
from ecommerce.jobs.ingest_catalog import ingest_catalog_file

CATALOG_UPDATE_JOB_TYPE = "catalog_update_from_opencart"
DEFAULT_EXPORT_PROFILE = DEFAULT_CATALOG_SOURCE
DEFAULT_EXPORT_TIMEOUT_SECONDS = 900


class CatalogUpdateError(RuntimeError):
    """Raised when the catalog update workflow cannot complete."""


class CatalogUpdateConfigError(CatalogUpdateError):
    """Raised when required OpenCart export configuration is missing."""


@dataclass(frozen=True)
class CatalogUpdateConfig:
    store_base: str
    admin_path: str
    admin_user: str
    admin_pass: str
    export_profile: str = DEFAULT_EXPORT_PROFILE
    timeout_seconds: int = DEFAULT_EXPORT_TIMEOUT_SECONDS
    headed: bool = False

    @property
    def admin_url(self) -> str:
        base = self.store_base.rstrip("/")
        path = self.admin_path.strip("/")
        return f"{base}/{path}" if path else base

    def safe_payload(self) -> dict[str, Any]:
        return {
            "admin_url": self.admin_url,
            "export_profile": self.export_profile,
            "timeout_seconds": self.timeout_seconds,
            "headed": self.headed,
        }


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
        if not _env_text(name)
    ]
    if missing:
        raise CatalogUpdateConfigError(f"Missing OpenCart export env config: {', '.join(missing)}")

    return CatalogUpdateConfig(
        store_base=_env_text("OPENCART_STORE_BASE") or "",
        admin_path=_env_text("OPENCART_ADMIN_PATH") or "",
        admin_user=_env_text("OPENCART_ADMIN_USER") or "",
        admin_pass=_env_text("OPENCART_ADMIN_PASS") or "",
        export_profile=_env_text("OPENCART_EXPORT_PROFILE") or DEFAULT_EXPORT_PROFILE,
        timeout_seconds=_env_int("OPENCART_EXPORT_TIMEOUT_SECONDS", DEFAULT_EXPORT_TIMEOUT_SECONDS),
        headed=_env_bool("OPENCART_EXPORT_HEADED", False),
    )


def run_catalog_update(job_id: str, *, config: CatalogUpdateConfig | None = None) -> dict[str, Any]:
    selected_config = config or load_catalog_update_config()
    output_dir = catalog_update_output_dir(job_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    migration = run_alembic_upgrade()
    export = export_catalog_csv(selected_config, output_dir)
    normalized_csv_path = normalize_downloaded_csv(export.downloaded_path, output_dir)
    ingest = run_catalog_ingest(normalized_csv_path)

    return {
        "job_id": job_id,
        "artifact_dir": _display_path(output_dir),
        "download_dir": _display_path(output_dir),
        "export_profile": selected_config.export_profile,
        "downloaded_csv_path": _display_path(export.downloaded_path),
        "imported_csv_path": _display_path(normalized_csv_path),
        "downloaded_filename": export.downloaded_path.name,
        "downloaded_file_size": export.downloaded_size,
        "migration": migration,
        "ingest": ingest,
    }


@dataclass(frozen=True)
class CatalogExportResult:
    downloaded_path: Path
    downloaded_size: int


def catalog_update_output_dir(job_id: str) -> Path:
    return repo_root() / "output" / "catalog_updates" / _safe_path_segment(job_id)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def ecommerce_app_root() -> Path:
    return Path(__file__).resolve().parents[3]


def run_alembic_upgrade() -> dict[str, Any]:
    command = [sys.executable, "-m", "alembic", "upgrade", "head"]
    app_root = ecommerce_app_root()
    database_url = get_database_url()
    try:
        completed = subprocess.run(
            command,
            cwd=app_root,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = _sanitize_output(f"{exc.stdout or ''}\n{exc.stderr or ''}", database_url)
        raise CatalogUpdateError(f"Migration failed: alembic upgrade head timed out. {output}".strip()) from exc
    except Exception as exc:
        raise CatalogUpdateError(f"Migration failed: {exc.__class__.__name__}") from exc

    stdout = _sanitize_output(completed.stdout, database_url)
    stderr = _sanitize_output(completed.stderr, database_url)
    payload = {
        "status": "succeeded" if completed.returncode == 0 else "failed",
        "command": [Path(sys.executable).name, "-m", "alembic", "upgrade", "head"],
        "cwd": _display_path(app_root),
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }
    if completed.returncode != 0:
        raise CatalogUpdateError(f"Migration failed: {stderr or stdout or 'alembic upgrade head failed'}")
    return payload


def export_catalog_csv(config: CatalogUpdateConfig, output_dir: Path) -> CatalogExportResult:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise CatalogUpdateError("OpenCart export failed: Playwright is not installed.") from exc

    timeout_ms = int(config.timeout_seconds * 1000)
    browser = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not config.headed)
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            page.set_default_timeout(timeout_ms)
            _login_to_opencart(page, config)
            _navigate_to_csv_product_export(page)
            _load_export_profile(page, config.export_profile)
            _advance_export_step_two(page)
            downloaded_path = _download_export(page, output_dir)
            return CatalogExportResult(
                downloaded_path=downloaded_path,
                downloaded_size=downloaded_path.stat().st_size,
            )
    except PlaywrightTimeoutError as exc:
        raise CatalogUpdateError("OpenCart export failed: export timeout.") from exc
    except CatalogUpdateError:
        raise
    except Exception as exc:
        raise CatalogUpdateError(f"OpenCart export failed: {exc.__class__.__name__}") from exc
    finally:
        if browser is not None:
            browser.close()


def normalize_downloaded_csv(downloaded_path: Path, output_dir: Path) -> Path:
    if not downloaded_path.exists():
        raise CatalogUpdateError("OpenCart export failed: downloaded CSV is missing.")
    final_path = output_dir / f"{DEFAULT_EXPORT_PROFILE}.csv"
    if downloaded_path.resolve(strict=False) != final_path.resolve(strict=False):
        shutil.copy2(downloaded_path, final_path)
    return final_path


def run_catalog_ingest(source_cata_path: Path) -> dict[str, Any]:
    return ingest_catalog_file(source_cata_path=source_cata_path).to_dict()


def _login_to_opencart(page: Any, config: CatalogUpdateConfig) -> None:
    page.goto(config.admin_url, wait_until="domcontentloaded")
    _fill_first(page, ("input[name='username']", "input[name='user']", "#input-username", "input[type='text']"), config.admin_user)
    _fill_first(page, ("input[name='password']", "#input-password", "input[type='password']"), config.admin_pass)
    _click_by_role_or_text(page, ("Login", "Σύνδεση", "Είσοδος"), roles=("button",))
    page.wait_for_load_state("networkidle")


def _navigate_to_csv_product_export(page: Any) -> None:
    for label in ("System", "Σύστημα"):
        if _try_click_text(page, label):
            break
    if not _try_click_text(page, "CSV Product Export"):
        raise CatalogUpdateError("OpenCart export failed: CSV Product Export menu item not found.")
    _wait_for_text(page, ("STEP 1", "Step 1", "ΒΗΜΑ 1"))


def _load_export_profile(page: Any, export_profile: str) -> None:
    select_locator = page.locator("select").filter(has_text=export_profile).first()
    select_locator.wait_for(state="visible")
    try:
        select_locator.select_option(label=export_profile)
    except Exception:
        select_locator.select_option(export_profile)
    _click_by_role_or_text(page, ("Load", "Φόρτωση"), roles=("button", "link"))
    _wait_for_text(page, ("success", "loaded", "επιτυχ", "φορτώθηκε"))
    _click_by_role_or_text(page, ("Next", "Επόμενο"), roles=("button", "link"))
    _wait_for_text(page, ("STEP 2", "Step 2", "ΒΗΜΑ 2"))


def _advance_export_step_two(page: Any) -> None:
    _click_by_role_or_text(page, ("Next", "Επόμενο"), roles=("button", "link"))
    _wait_for_text(page, ("STEP 3", "Step 3", "ΒΗΜΑ 3"))


def _download_export(page: Any, output_dir: Path) -> Path:
    download_control = _download_locator(page)
    download_control.wait_for(state="visible")
    with page.expect_download() as download_info:
        download_control.click()
    download = download_info.value
    filename = _safe_filename(download.suggested_filename or f"{DEFAULT_EXPORT_PROFILE}.csv")
    downloaded_path = output_dir / filename
    download.save_as(downloaded_path)
    if not downloaded_path.exists():
        raise CatalogUpdateError("OpenCart export failed: download missing after save.")
    return downloaded_path


def _download_locator(page: Any) -> Any:
    pattern = re.compile(r"download|λήψη|κατέβασ", re.IGNORECASE)
    candidates = (
        page.get_by_role("link", name=pattern),
        page.get_by_role("button", name=pattern),
        page.locator("a").filter(has_text=pattern),
        page.locator("button").filter(has_text=pattern),
    )
    for locator in candidates:
        if locator.count() > 0:
            return locator.first()
    raise CatalogUpdateError("OpenCart export failed: download link not found.")


def _fill_first(page: Any, selectors: tuple[str, ...], value: str) -> None:
    for selector in selectors:
        locator = page.locator(selector).first()
        if locator.count() > 0:
            locator.fill(value)
            return
    raise CatalogUpdateError(f"OpenCart login failed: field not found for selectors {', '.join(selectors)}.")


def _click_by_role_or_text(page: Any, labels: tuple[str, ...], *, roles: tuple[str, ...]) -> None:
    for role in roles:
        for label in labels:
            locator = page.get_by_role(role, name=re.compile(re.escape(label), re.IGNORECASE))
            if locator.count() > 0:
                locator.first().click()
                return
    for label in labels:
        if _try_click_text(page, label):
            return
    raise CatalogUpdateError(f"OpenCart export failed: control not found: {labels[0]}.")


def _try_click_text(page: Any, label: str) -> bool:
    locator = page.get_by_text(re.compile(re.escape(label), re.IGNORECASE)).first()
    if locator.count() <= 0:
        return False
    locator.click()
    return True


def _wait_for_text(page: Any, labels: tuple[str, ...]) -> None:
    pattern = re.compile("|".join(re.escape(label) for label in labels), re.IGNORECASE)
    page.get_by_text(pattern).first().wait_for(state="visible")


def _env_text(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    text = value.strip()
    return text or None


def _env_int(name: str, default: int) -> int:
    value = _env_text(name)
    if value is None:
        return default
    try:
        return max(1, int(value))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = _env_text(name)
    if value is None:
        return default
    return value.casefold() in {"1", "true", "yes", "on", "headed"}


def _sanitize_output(value: object, database_url: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return sanitize_database_error(text, database_url)[:4000]


def _safe_path_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value or "job")


def _safe_filename(value: str) -> str:
    name = Path(value).name.strip()
    return _safe_path_segment(name) or f"{DEFAULT_EXPORT_PROFILE}.csv"


def _display_path(path: Path) -> str:
    resolved = path.expanduser().resolve(strict=False)
    try:
        return str(resolved.relative_to(repo_root().resolve(strict=False)))
    except ValueError:
        return str(resolved)
