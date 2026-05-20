"""Artifact listing helpers for Source URL Agent API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ecommerce.artifacts import (
    ArtifactPathError,
    ArtifactPathForbiddenError,
    list_run_artifacts,
)


def source_url_agent_artifact_listing(run_id: str) -> dict[str, Any]:
    try:
        result = list_run_artifacts("source_url_agent", run_id)
    except ArtifactPathForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ArtifactPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Source URL Agent artifact listing failed."
        ) from exc
    return {
        "run_id": result.run_id,
        "run_type": result.run_type,
        "run_dir": display_path(result.run_dir),
        "items": [item.to_api_dict() for item in result.items],
    }


def source_url_agent_artifact_items(run_id: str) -> list[dict[str, Any]]:
    try:
        return source_url_agent_artifact_listing(run_id)["items"]
    except HTTPException as exc:
        if exc.status_code == 404:
            return []
        raise


def display_path(path: Path) -> str:
    resolved = path.expanduser().resolve(strict=False)
    try:
        return str(resolved.relative_to(Path.cwd().resolve(strict=False)))
    except ValueError:
        return str(resolved)
