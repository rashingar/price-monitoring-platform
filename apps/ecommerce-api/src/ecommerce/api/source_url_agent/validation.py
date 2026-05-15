"""Validation helpers for Source URL Agent API routes."""

from __future__ import annotations

import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import HTTPException

from ecommerce.db.policy import catalog_database_unavailable_detail, collect_catalog_database_readiness, require_database_ready_for_catalog
from ecommerce.source_url_agent.sources import SOURCE_CHOICES, load_source_registry

from .schemas import DEFAULT_API_MAX_PRODUCTS_PER_BATCH, MAX_API_SOURCE_URL_AGENT_LIMIT, SourceUrlAgentRunRequest

_FACADE_MODULE = "ecommerce.api.routes_source_url_agent"


def default_api_max_products_per_batch() -> int:
    facade = sys.modules.get(_FACADE_MODULE)
    if facade is not None and hasattr(facade, "DEFAULT_API_MAX_PRODUCTS_PER_BATCH"):
        return int(getattr(facade, "DEFAULT_API_MAX_PRODUCTS_PER_BATCH"))
    return DEFAULT_API_MAX_PRODUCTS_PER_BATCH


def validate_source_choice(value: str) -> None:
    source = value.strip().lower()
    if source not in SOURCE_CHOICES:
        raise HTTPException(status_code=400, detail=f"source must be one of: {', '.join(SOURCE_CHOICES)}.")
    try:
        load_source_registry().selected(source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def api_run_limit(request: SourceUrlAgentRunRequest) -> int:
    default_batch = default_api_max_products_per_batch()
    limit = request.limit if request.limit is not None else default_batch
    max_batch = request.max_products_per_batch or default_batch
    return min(int(limit), int(max_batch), MAX_API_SOURCE_URL_AGENT_LIMIT)


def selected_models(values: list[str]) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        selected.append(text)
        seen.add(text)
    return selected


def source_url_agent_input_path(request: SourceUrlAgentRunRequest) -> Path | None:
    if request.mode != "csv":
        return None
    raw_path = optional_text(request.input_path)
    if raw_path is None:
        raise HTTPException(status_code=400, detail="input_path is required for csv mode.")
    path = Path(raw_path)
    if contains_parent_reference(path):
        raise HTTPException(status_code=400, detail="input_path must not contain path traversal.")
    resolved = path.expanduser().resolve(strict=False)
    cwd = Path.cwd().resolve(strict=False)
    if not same_or_child(resolved, cwd):
        raise HTTPException(status_code=400, detail="input_path must be inside the application working directory.")
    return resolved


def require_source_url_agent_run_database_ready() -> None:
    readiness = collect_catalog_database_readiness()
    dialect = str(readiness.get("dialect") or "").lower()
    if bool(readiness.get("ready_for_catalog", False)) and dialect == "postgresql":
        return
    detail = catalog_database_unavailable_detail(readiness)
    detail.update(
        {
            "message": "PostgreSQL is required for Source URL Agent runs.",
            "code": "source_url_agent_database_required",
            "dialect": dialect or None,
            "ready_for_source_url_agent_runs": False,
        }
    )
    raise HTTPException(status_code=503, detail=detail)


def require_catalog_database_ready() -> None:
    require_database_ready_for_catalog()


def optional_decimal(value: str | None, field_name: str) -> Decimal | None:
    text = optional_text(value)
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a number.") from None


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def like_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def contains_parent_reference(path: Path) -> bool:
    return any(part == ".." for part in path.parts)


def same_or_child(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return path == parent
