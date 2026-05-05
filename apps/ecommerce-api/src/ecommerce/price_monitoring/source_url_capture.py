"""Compatibility shim for Vendor Sources source URL capture.

Source URL capture is owned by :mod:`ecommerce.vendor_sources.capture`.
This module remains temporarily so older Price Monitoring imports keep working.
"""

from __future__ import annotations

from ecommerce.vendor_sources.capture import (  # noqa: F401
    SOURCE_URL_CAPTURE_RESULT_FILENAME,
    VENDOR_SOURCE_CAPTURE_RESULT_FILENAME,
    VENDOR_SOURCE_CAPTURE_RUNS_DIR,
    SourceUrlCaptureRunResult,
    capture_due_vendor_sources,
    capture_selected_source_urls,
    capture_selected_source_urls_for_run,
    get_vendor_source_capture_run,
    list_vendor_source_capture_runs,
    run_vendor_source_capture,
    vendor_source_capture_run_to_dict,
)
