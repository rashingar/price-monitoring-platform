"""High-level OpenCart catalog export flow."""

from __future__ import annotations

from pathlib import Path

from ecommerce.catalog_update import browser_steps
from ecommerce.catalog_update.diagnostics import (
    capture_export_failure_diagnostics,
    format_export_failure,
)
from ecommerce.catalog_update.progress import CatalogUpdateStepTracker
from ecommerce.catalog_update.types import (
    CatalogExportResult,
    CatalogUpdateConfig,
    CatalogUpdateError,
)


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
        raise CatalogUpdateError(
            "OpenCart export failed: Playwright is not installed."
        ) from exc

    timeout_ms = int(config.timeout_seconds * 1000)
    selected_job_id = job_id or output_dir.name
    steps = step_tracker or CatalogUpdateStepTracker()
    browser = None
    context = None
    page = None
    try:
        steps.mark("playwright_start", progress_step="playwright_started")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not config.headed)
            try:
                context = browser.new_context(accept_downloads=True)
                page = context.new_page()
                page.set_default_timeout(timeout_ms)
                steps.mark("login", progress_step="login_started")
                browser_steps.login_to_opencart(page, config, timeout_ms)
                steps.emit_progress("login_completed")
                steps.mark("open_csv_product_export")
                browser_steps.open_csv_product_export(page, config, timeout_ms)
                steps.emit_progress("export_page_opened")
                steps.mark("load_profile")
                browser_steps.load_export_profile(page, config.export_profile)
                steps.emit_progress(
                    "profile_loaded", details={"export_profile": config.export_profile}
                )
                steps.mark("step_2_next")
                browser_steps.advance_export_step_two(page)
                steps.emit_progress("export_step_advanced")
                steps.mark("wait_for_download", progress_step="download_waiting")
                downloaded_path = browser_steps.download_export(
                    page, output_dir, timeout_ms, step_tracker=steps
                )
                return CatalogExportResult(
                    downloaded_path=downloaded_path,
                    downloaded_size=downloaded_path.stat().st_size,
                )
            except PlaywrightTimeoutError as exc:
                diagnostics_dir = capture_export_failure_diagnostics(
                    job_id=selected_job_id,
                    output_dir=output_dir,
                    config=config,
                    step=steps.current_step,
                    page=page,
                    error=exc,
                )
                raise CatalogUpdateError(
                    format_export_failure(
                        "export timeout.",
                        step=steps.current_step,
                        diagnostics_dir=diagnostics_dir,
                        config=config,
                    )
                ) from exc
            except CatalogUpdateError as exc:
                diagnostics_dir = capture_export_failure_diagnostics(
                    job_id=selected_job_id,
                    output_dir=output_dir,
                    config=config,
                    step=steps.current_step,
                    page=page,
                    error=exc,
                )
                raise CatalogUpdateError(
                    format_export_failure(
                        str(exc),
                        step=steps.current_step,
                        diagnostics_dir=diagnostics_dir,
                        config=config,
                    )
                ) from exc
            except Exception as exc:
                diagnostics_dir = capture_export_failure_diagnostics(
                    job_id=selected_job_id,
                    output_dir=output_dir,
                    config=config,
                    step=steps.current_step,
                    page=page,
                    error=exc,
                )
                raise CatalogUpdateError(
                    format_export_failure(
                        exc.__class__.__name__,
                        step=steps.current_step,
                        diagnostics_dir=diagnostics_dir,
                        config=config,
                    )
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
        diagnostics_dir = capture_export_failure_diagnostics(
            job_id=selected_job_id,
            output_dir=output_dir,
            config=config,
            step=steps.current_step,
            page=page,
            error=exc,
        )
        raise CatalogUpdateError(
            format_export_failure(
                exc.__class__.__name__,
                step=steps.current_step,
                diagnostics_dir=diagnostics_dir,
                config=config,
            )
        ) from exc
