"""OpenCart catalog export and Ecommerce catalog ingestion orchestration."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urlparse, urlunparse

from ecommerce.catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.config import get_database_url, sanitize_database_error
from ecommerce.env import load_local_env_if_present
from ecommerce.jobs.ingest_catalog import ingest_catalog_file

CATALOG_UPDATE_JOB_TYPE = "catalog_update_from_opencart"
DEFAULT_EXPORT_PROFILE = DEFAULT_CATALOG_SOURCE
DEFAULT_EXPORT_TIMEOUT_SECONDS = 900
CSV_PRODUCT_EXPORT_ROUTE = "extension/ka_extensions/csv_product_export/ka_product_export"
REDACTED_VALUE = "[redacted]"
CATALOG_UPDATE_STEPS = (
    "config_loaded",
    "alembic_upgrade",
    "playwright_start",
    "login",
    "open_csv_product_export",
    "load_profile",
    "step_2_next",
    "wait_for_download",
    "save_download",
    "ingest_catalog",
)
SENSITIVE_QUERY_KEYS = {
    "access_token",
    "auth",
    "authorization",
    "cookie",
    "key",
    "password",
    "pass",
    "passwd",
    "pwd",
    "refresh_token",
    "secret",
    "session",
    "sessionid",
    "sid",
    "token",
    "user",
    "username",
    "user_token",
}


class CatalogUpdateError(RuntimeError):
    """Raised when the catalog update workflow cannot complete."""


class CatalogUpdateConfigError(CatalogUpdateError):
    """Raised when required OpenCart export configuration is missing."""


@dataclass
class CatalogUpdateStepTracker:
    current_step: str = "config_loaded"

    def mark(self, step: str) -> None:
        if step not in CATALOG_UPDATE_STEPS:
            raise ValueError(f"Unsupported catalog update step: {step}")
        self.current_step = step


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

    @property
    def admin_index_url(self) -> str:
        return build_admin_index(self.store_base, self.admin_path)

    def safe_payload(self) -> dict[str, Any]:
        return {
            "admin_url": self.admin_url,
            "admin_index_url": self.admin_index_url,
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
    steps = CatalogUpdateStepTracker()
    steps.mark("config_loaded")
    try:
        selected_config = config or load_catalog_update_config()
    except CatalogUpdateError as exc:
        raise CatalogUpdateError(_message_with_step(str(exc), steps.current_step)) from exc
    output_dir = catalog_update_output_dir(job_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    steps.mark("alembic_upgrade")
    try:
        migration = run_alembic_upgrade()
    except CatalogUpdateError as exc:
        raise CatalogUpdateError(_message_with_step(str(exc), steps.current_step)) from exc

    export = export_catalog_csv(selected_config, output_dir, job_id=job_id, step_tracker=steps)
    try:
        normalized_csv_path = normalize_downloaded_csv(export.downloaded_path, output_dir)
    except CatalogUpdateError as exc:
        raise CatalogUpdateError(_message_with_step(str(exc), steps.current_step)) from exc
    steps.mark("ingest_catalog")
    try:
        ingest = run_catalog_ingest(normalized_csv_path)
    except Exception as exc:
        raise CatalogUpdateError(_message_with_step(str(exc) or exc.__class__.__name__, steps.current_step)) from exc

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


def export_catalog_csv(
    config: CatalogUpdateConfig,
    output_dir: Path,
    *,
    job_id: str | None = None,
    step_tracker: CatalogUpdateStepTracker | None = None,
) -> CatalogExportResult:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise CatalogUpdateError("OpenCart export failed: Playwright is not installed.") from exc

    timeout_ms = int(config.timeout_seconds * 1000)
    selected_job_id = job_id or output_dir.name
    steps = step_tracker or CatalogUpdateStepTracker()
    browser = None
    context = None
    page = None
    try:
        steps.mark("playwright_start")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not config.headed)
            try:
                context = browser.new_context(accept_downloads=True)
                page = context.new_page()
                page.set_default_timeout(timeout_ms)
                steps.mark("login")
                _login_to_opencart(page, config, timeout_ms)
                steps.mark("open_csv_product_export")
                _open_csv_product_export(page, config, timeout_ms)
                steps.mark("load_profile")
                _load_export_profile(page, config.export_profile)
                steps.mark("step_2_next")
                _advance_export_step_two(page)
                steps.mark("wait_for_download")
                downloaded_path = _download_export(page, output_dir, timeout_ms, step_tracker=steps)
                return CatalogExportResult(
                    downloaded_path=downloaded_path,
                    downloaded_size=downloaded_path.stat().st_size,
                )
            except PlaywrightTimeoutError as exc:
                diagnostics_dir = _capture_export_failure_diagnostics(
                    job_id=selected_job_id,
                    output_dir=output_dir,
                    config=config,
                    step=steps.current_step,
                    page=page,
                    error=exc,
                )
                raise CatalogUpdateError(
                    _format_export_failure("export timeout.", step=steps.current_step, diagnostics_dir=diagnostics_dir, config=config)
                ) from exc
            except CatalogUpdateError as exc:
                diagnostics_dir = _capture_export_failure_diagnostics(
                    job_id=selected_job_id,
                    output_dir=output_dir,
                    config=config,
                    step=steps.current_step,
                    page=page,
                    error=exc,
                )
                raise CatalogUpdateError(
                    _format_export_failure(str(exc), step=steps.current_step, diagnostics_dir=diagnostics_dir, config=config)
                ) from exc
            except Exception as exc:
                diagnostics_dir = _capture_export_failure_diagnostics(
                    job_id=selected_job_id,
                    output_dir=output_dir,
                    config=config,
                    step=steps.current_step,
                    page=page,
                    error=exc,
                )
                raise CatalogUpdateError(
                    _format_export_failure(exc.__class__.__name__, step=steps.current_step, diagnostics_dir=diagnostics_dir, config=config)
                ) from exc
            finally:
                try:
                    if context is not None:
                        context.close()
                finally:
                    browser.close()
    except CatalogUpdateError:
        raise
    except Exception as exc:
        diagnostics_dir = _capture_export_failure_diagnostics(
            job_id=selected_job_id,
            output_dir=output_dir,
            config=config,
            step=steps.current_step,
            page=page,
            error=exc,
        )
        raise CatalogUpdateError(
            _format_export_failure(exc.__class__.__name__, step=steps.current_step, diagnostics_dir=diagnostics_dir, config=config)
        ) from exc


def normalize_downloaded_csv(downloaded_path: Path, output_dir: Path) -> Path:
    if not downloaded_path.exists():
        raise CatalogUpdateError("OpenCart export failed: downloaded CSV is missing.")
    final_path = output_dir / f"{DEFAULT_EXPORT_PROFILE}.csv"
    if downloaded_path.resolve(strict=False) != final_path.resolve(strict=False):
        shutil.copy2(downloaded_path, final_path)
    return final_path


def run_catalog_ingest(source_cata_path: Path) -> dict[str, Any]:
    return ingest_catalog_file(source_cata_path=source_cata_path).to_dict()


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


def _login_to_opencart(page: Any, config: CatalogUpdateConfig, timeout_ms: int) -> None:
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


def _append_session_token(target_url: str, current_url: str) -> str:
    user_token = parse_qs(urlparse(current_url).query).get("user_token", [None])[0]
    if not user_token:
        return target_url

    separator = "&" if urlparse(target_url).query else "?"
    return f"{target_url}{separator}user_token={quote(user_token, safe='')}"


def _open_csv_product_export(page: Any, config: CatalogUpdateConfig, timeout_ms: int) -> None:
    export_url = _append_session_token(
        f"{config.admin_index_url}?route={CSV_PRODUCT_EXPORT_ROUTE}",
        page.url,
    )
    page.goto(export_url, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_load_state("networkidle", timeout=timeout_ms)
    page.locator('select[name="profile_id"]').wait_for(state="visible", timeout=timeout_ms)


def _navigate_to_csv_product_export(page: Any) -> None:
    for label in ("System", "Σύστημα"):
        if _try_click_text(page, label):
            break
    if not _try_click_text(page, "CSV Product Export"):
        raise CatalogUpdateError("OpenCart export failed: CSV Product Export menu item not found.")
    _wait_for_text(page, ("STEP 1", "Step 1", "ΒΗΜΑ 1"))


def _load_export_profile(page: Any, export_profile: str) -> None:
    select_locator = page.locator('select[name="profile_id"]').first
    select_locator.wait_for(state="visible")
    try:
        select_locator.select_option(label=export_profile)
    except Exception:
        select_locator.select_option(export_profile)
    page.locator('input[value="Load"], button:has-text("Load")').first.click()
    _click_first_locator(
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
    _wait_for_text(page, ("STEP 2", "Step 2", "ΒΗΜΑ 2"))


def _advance_export_step_two(page: Any) -> None:
    _click_first_locator(
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
    _wait_for_text(page, ("STEP 3", "Step 3", "ΒΗΜΑ 3"))


def _download_export(
    page: Any,
    output_dir: Path,
    timeout_ms: int,
    *,
    step_tracker: CatalogUpdateStepTracker | None = None,
) -> Path:
    download_control = _download_locator(page, timeout_ms)
    with page.expect_download() as download_info:
        download_control.click()
    download = download_info.value
    filename = _safe_filename(download.suggested_filename or f"{DEFAULT_EXPORT_PROFILE}.csv")
    downloaded_path = output_dir / filename
    if step_tracker is not None:
        step_tracker.mark("save_download")
    download.save_as(downloaded_path)
    if not downloaded_path.exists():
        raise CatalogUpdateError("OpenCart export failed: download missing after save.")
    return downloaded_path


def _download_locator(page: Any, timeout_ms: int) -> Any:
    pattern = re.compile(r"download", re.IGNORECASE)
    deadline = time.monotonic() + max(1, timeout_ms / 1000)
    while time.monotonic() < deadline:
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


def _fill_first(page: Any, selectors: tuple[str, ...], value: str) -> None:
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count() > 0:
            locator.fill(value)
            return
    raise CatalogUpdateError(f"OpenCart login failed: field not found for selectors {', '.join(selectors)}.")


def _click_by_role_or_text(page: Any, labels: tuple[str, ...], *, roles: tuple[str, ...]) -> None:
    for role in roles:
        for label in labels:
            locator = page.get_by_role(role, name=re.compile(re.escape(label), re.IGNORECASE))
            if locator.count() > 0:
                locator.first.click()
                return
    for label in labels:
        if _try_click_text(page, label):
            return
    raise CatalogUpdateError(f"OpenCart export failed: control not found: {labels[0]}.")


def _try_click_text(page: Any, label: str) -> bool:
    locator = page.get_by_text(re.compile(re.escape(label), re.IGNORECASE)).first
    if locator.count() <= 0:
        return False
    locator.click()
    return True


def _wait_for_text(page: Any, labels: tuple[str, ...]) -> None:
    pattern = re.compile("|".join(re.escape(label) for label in labels), re.IGNORECASE)
    page.get_by_text(pattern).first.wait_for(state="visible")


def _click_first_locator(page: Any, selectors: tuple[str, ...], error_message: str) -> None:
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count() > 0:
            locator.first.click()
            return
    raise CatalogUpdateError(error_message)


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


def redact_opencart_url(value: object, config: CatalogUpdateConfig | None = None) -> str:
    text = str(value or "")
    if not text:
        return ""
    try:
        parsed = urlparse(text)
    except ValueError:
        return redact_opencart_sensitive_data(text, config)
    if not parsed.scheme or not parsed.netloc:
        return redact_opencart_sensitive_data(text, config)

    query_items = [
        (key, REDACTED_VALUE if _is_sensitive_query_key(key) else redact_opencart_sensitive_data(value, config))
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return redact_opencart_sensitive_data(urlunparse(parsed._replace(query=urlencode(query_items))), config)


def redact_opencart_sensitive_data(value: object, config: CatalogUpdateConfig | None = None) -> str:
    text = str(value or "")
    if not text:
        return ""
    sensitive_values = {
        os.environ.get("OPENCART_ADMIN_PASS", ""),
        os.environ.get("OPENCART_ADMIN_USER", ""),
    }
    if config is not None:
        sensitive_values.update({config.admin_pass, config.admin_user})
    for secret in sorted((item for item in sensitive_values if item), key=len, reverse=True):
        text = text.replace(secret, REDACTED_VALUE)
    text = re.sub(
        r"(?i)\b(user_token|access_token|refresh_token|token|password|passwd|pwd|pass|cookie|secret|authorization)=([^&\s]+)",
        lambda match: f"{match.group(1)}={REDACTED_VALUE}",
        text,
    )
    return text


def _capture_export_failure_diagnostics(
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
                _redact_visible_credentials(page)
                page.screenshot(path=str(screenshot_path), full_page=True)
                screenshot_saved = screenshot_path.exists()
            except Exception as screenshot_exc:
                screenshot_error = redact_opencart_sensitive_data(str(screenshot_exc) or screenshot_exc.__class__.__name__, config)

        context_path = diagnostics_dir / "failure_context.json"
        context: dict[str, Any] = {
            "job_id": job_id,
            "step": step,
            "current_url": redact_opencart_url(getattr(page, "url", ""), config) if page is not None else None,
            "export_profile": redact_opencart_sensitive_data(config.export_profile, config),
            "timeout_seconds": config.timeout_seconds,
            "headed": config.headed,
            "error_class": error.__class__.__name__,
            "sanitized_error_message": redact_opencart_sensitive_data(str(error) or error.__class__.__name__, config),
            "timestamp": _now_iso(),
        }
        if screenshot_saved:
            context["screenshot_path"] = _display_path(screenshot_path)
        if screenshot_error:
            context["screenshot_error"] = screenshot_error
        context_path.write_text(json.dumps(context, indent=2, sort_keys=True), encoding="utf-8")
        return diagnostics_dir
    except Exception:
        return None


def _redact_visible_credentials(page: Any) -> None:
    for selector, value in (('input[name="password"]', ""), ('input[name="username"]', REDACTED_VALUE)):
        try:
            locator = page.locator(selector).first
            locator.fill(value)
        except Exception:
            pass


def _format_export_failure(
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
        base = f"{base} Diagnostics saved to {_display_path(diagnostics_dir)}."
    return base


def _message_with_step(message: str, step: str) -> str:
    safe_message = redact_opencart_sensitive_data(message)
    if "Step:" in safe_message or " at step " in safe_message:
        return safe_message
    return f"{safe_message} Step: {step}."


def _is_sensitive_query_key(key: str) -> bool:
    normalized = key.strip().casefold()
    return normalized in SENSITIVE_QUERY_KEYS or any(part in normalized for part in ("token", "password", "cookie", "secret"))


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


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
