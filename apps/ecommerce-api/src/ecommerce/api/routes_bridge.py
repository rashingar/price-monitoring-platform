"""Bridge API routes."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ecommerce.artifacts import artifact_link_payload
from ecommerce.bridge import DEFAULT_STOCK_CSV_PATH, run_bridge_from_balance_csv

router = APIRouter(prefix="/api/bridge", tags=["bridge"])


class BridgeRunRequest(BaseModel):
    opencart_export_path: str = Field(..., min_length=1)
    stock_csv_path: str | None = None
    output_dir: str | None = None


def _make_run_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"


@router.post("/run")
def run_bridge(request: BridgeRunRequest) -> dict:
    stock_csv_path = Path(request.stock_csv_path) if request.stock_csv_path else DEFAULT_STOCK_CSV_PATH
    opencart_export_path = Path(request.opencart_export_path)
    run_id = _make_run_id()
    output_dir = Path(request.output_dir) if request.output_dir else Path("output") / "ecommerce" / "bridge" / "runs" / run_id

    if not stock_csv_path.exists():
        raise HTTPException(status_code=404, detail=f"Stock CSV not found: {stock_csv_path}")
    if not opencart_export_path.exists():
        raise HTTPException(status_code=404, detail=f"OpenCart export not found: {opencart_export_path}")

    try:
        result = run_bridge_from_balance_csv(
            stock_csv_path=stock_csv_path,
            opencart_csv_path=opencart_export_path,
            output_dir=output_dir,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Bridge execution failed.") from exc

    return {
        "run_id": run_id,
        "status": "completed",
        "stock_csv_path": str(stock_csv_path),
        "opencart_export_path": str(opencart_export_path),
        "output_dir": str(result.run_dir),
        "artifacts": [artifact_link_payload(artifact.path) for artifact in result.artifacts],
        "summary": {
            "updated_count": result.summary.updated_count,
            "unknown_count": result.summary.unknown_count,
            "codes_not_in_entersoft_count": result.summary.codes_not_in_entersoft_count,
            "invalid_or_composite_models_ignored": result.summary.invalid_or_composite_models_ignored,
        },
    }
