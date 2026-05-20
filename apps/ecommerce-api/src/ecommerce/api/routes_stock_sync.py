"""OpenCart stock sync scheduled-task trigger endpoints."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/stock-sync", tags=["stock-sync"])

DEFAULT_SERVER = "ERPSERVER"
DEFAULT_TASK_REVIEW = "OpenCartStockSync-ReviewOnly"
DEFAULT_TASK_DRY_RUN = "OpenCartStockSync-DryRunImport"
DEFAULT_TASK_IMPORT = "OpenCartStockSync-RunImport"
DEFAULT_LATEST_REVIEW_PATH = r"\\ERPSERVER\C$\OpenCartStockSync\runs\latest\review.json"
FINAL_REPORT_MESSAGE = "Scheduled task triggered. Check email for the final report."

MODE_TO_TASK_ENV = {
    "review": "ECOMMERCE_STOCK_SYNC_TASK_REVIEW",
    "dry_run": "ECOMMERCE_STOCK_SYNC_TASK_DRY_RUN",
    "import": "ECOMMERCE_STOCK_SYNC_TASK_IMPORT",
}

TASK_DEFAULTS = {
    "ECOMMERCE_STOCK_SYNC_TASK_REVIEW": DEFAULT_TASK_REVIEW,
    "ECOMMERCE_STOCK_SYNC_TASK_DRY_RUN": DEFAULT_TASK_DRY_RUN,
    "ECOMMERCE_STOCK_SYNC_TASK_IMPORT": DEFAULT_TASK_IMPORT,
}


class StockSyncRunRequest(BaseModel):
    mode: str = Field(description="One of review, dry_run, or import.")
    confirmation: str | None = None


class StockSyncRunResponse(BaseModel):
    mode: str
    task_name: str
    server: str
    triggered_at: datetime
    stdout: str | None = None
    stderr: str | None = None
    message: str


class StockSyncLatestResponse(BaseModel):
    available: bool
    message: str | None = None
    status: str | None = None
    ok_to_upload: bool | None = None
    run_id: str | None = None
    run_dir: str | None = None
    created_at: str | None = None
    counts: dict[str, Any] = Field(default_factory=dict)
    warnings: list[Any] = Field(default_factory=list)
    hard_failures: list[Any] = Field(default_factory=list)
    safety: dict[str, Any] | None = None
    orchestrator: dict[str, Any] | None = None


class StockSyncReadinessResponse(BaseModel):
    enabled: bool
    server: str
    tasks: dict[str, str]
    latest_review_path: str
    latest_review_exists: bool
    latest_review_readable: bool
    latest_review_error: str | None = None
    schtasks_available: bool


@router.post("/runs", response_model=StockSyncRunResponse)
def trigger_stock_sync_run(request: StockSyncRunRequest) -> StockSyncRunResponse:
    if not _enabled():
        raise HTTPException(
            status_code=503,
            detail={
                "message": "OpenCart Stock Sync API is disabled. Set ECOMMERCE_STOCK_SYNC_ENABLED=true to enable it.",
                "code": "stock_sync_disabled",
            },
        )

    mode = request.mode
    if mode not in MODE_TO_TASK_ENV:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Unknown stock sync mode.",
                "code": "stock_sync_unknown_mode",
            },
        )

    if mode == "import" and request.confirmation != "RUN IMPORT":
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Import mode requires confirmation exactly RUN IMPORT.",
                "code": "stock_sync_import_confirmation_required",
            },
        )

    if not _schtasks_available():
        raise HTTPException(
            status_code=503,
            detail={
                "message": "schtasks is not available on this machine.",
                "code": "stock_sync_schtasks_missing",
            },
        )

    server = _server()
    task_name = _task_name_for_mode(mode)
    command = ["schtasks", "/Run", "/S", server, "/TN", task_name]
    triggered_at = datetime.now(UTC)

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=504,
            detail={
                "message": "Timed out while triggering the OpenCart Stock Sync scheduled task.",
                "code": "stock_sync_trigger_timeout",
                "stdout": _clean_output(exc.stdout),
                "stderr": _clean_output(exc.stderr),
            },
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Failed to start schtasks for OpenCart Stock Sync.",
                "code": "stock_sync_trigger_unavailable",
                "error": exc.__class__.__name__,
            },
        ) from exc

    stdout = _clean_output(completed.stdout)
    stderr = _clean_output(completed.stderr)
    if completed.returncode != 0:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "OpenCart Stock Sync scheduled task trigger failed.",
                "code": "stock_sync_trigger_failed",
                "stdout": stdout,
                "stderr": stderr,
            },
        )

    return StockSyncRunResponse(
        mode=mode,
        task_name=task_name,
        server=server,
        triggered_at=triggered_at,
        stdout=stdout,
        stderr=stderr,
        message=FINAL_REPORT_MESSAGE,
    )


@router.get("/latest", response_model=StockSyncLatestResponse)
def get_latest_stock_sync() -> StockSyncLatestResponse:
    path = Path(_latest_review_path())
    try:
        if not path.exists() or not path.is_file():
            return StockSyncLatestResponse(
                available=False,
                message="Latest stock sync review is not available yet.",
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return StockSyncLatestResponse(
            available=False,
            message="Latest stock sync review is missing or inaccessible.",
        )

    if not isinstance(payload, dict):
        return StockSyncLatestResponse(
            available=False,
            message="Latest stock sync review has an unsupported shape.",
        )

    safety = _optional_dict(payload.get("safety"))
    warnings = _list_value(
        payload.get("warnings")
        if safety is None
        else safety.get("warnings", payload.get("warnings"))
    )
    hard_failures = _list_value(
        payload.get("hard_failures")
        if safety is None
        else safety.get("hard_failures", payload.get("hard_failures"))
    )

    return StockSyncLatestResponse(
        available=True,
        status=_optional_str(payload.get("status")),
        ok_to_upload=_optional_bool(payload.get("ok_to_upload")),
        run_id=_optional_str(payload.get("run_id")),
        run_dir=_optional_str(payload.get("run_dir")),
        created_at=_optional_str(payload.get("created_at")),
        counts=_dict_value(payload.get("counts")),
        warnings=warnings,
        hard_failures=hard_failures,
        safety=safety,
        orchestrator=_optional_dict(payload.get("orchestrator")),
    )


@router.get("/readiness", response_model=StockSyncReadinessResponse)
def get_stock_sync_readiness() -> StockSyncReadinessResponse:
    path = Path(_latest_review_path())
    exists = False
    readable = False
    error: str | None = None
    try:
        exists = path.exists() and path.is_file()
        if exists:
            with path.open("rb"):
                readable = True
    except OSError:
        error = "Latest stock sync review path is not currently readable."

    return StockSyncReadinessResponse(
        enabled=_enabled(),
        server=_server(),
        tasks={mode: _task_name_for_mode(mode) for mode in MODE_TO_TASK_ENV},
        latest_review_path=str(path),
        latest_review_exists=exists,
        latest_review_readable=readable,
        latest_review_error=error,
        schtasks_available=_schtasks_available(),
    )


def _enabled() -> bool:
    return os.getenv("ECOMMERCE_STOCK_SYNC_ENABLED", "false").strip().lower() == "true"


def _server() -> str:
    return (
        os.getenv("ECOMMERCE_STOCK_SYNC_SERVER", DEFAULT_SERVER).strip()
        or DEFAULT_SERVER
    )


def _task_name_for_mode(mode: str) -> str:
    env_key = MODE_TO_TASK_ENV[mode]
    return os.getenv(env_key, TASK_DEFAULTS[env_key]).strip() or TASK_DEFAULTS[env_key]


def _latest_review_path() -> str:
    return (
        os.getenv(
            "ECOMMERCE_STOCK_SYNC_LATEST_REVIEW_PATH", DEFAULT_LATEST_REVIEW_PATH
        ).strip()
        or DEFAULT_LATEST_REVIEW_PATH
    )


def _schtasks_available() -> bool:
    return shutil.which("schtasks") is not None


def _clean_output(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_str(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, int | float | bool):
        return str(value)
    return None


def _optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_dict(value: object) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _list_value(value: object) -> list[Any]:
    return value if isinstance(value, list) else []
