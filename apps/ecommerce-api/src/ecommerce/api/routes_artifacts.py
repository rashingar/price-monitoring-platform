"""Safe generated artifact access API routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ecommerce.artifacts import (
    ArtifactPathError,
    ArtifactPathForbiddenError,
    UnsupportedArtifactExtensionError,
    get_artifact_roots,
    list_run_artifacts,
    read_text_artifact,
    resolve_artifact_path,
)

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


@router.get("/roots")
def get_roots() -> dict:
    return {"roots": [{"path": str(root), "exists": root.exists()} for root in get_artifact_roots()]}


@router.get("/price-monitoring/runs/{run_id}")
def get_price_monitoring_run_artifacts(run_id: str) -> dict:
    return _run_artifacts_response("price_monitoring", run_id)


@router.get("/read")
def read_artifact(path: str | None = Query(None), max_bytes: int = Query(1048576)) -> dict:
    try:
        result = read_text_artifact(Path(_required_path(path)), max_bytes=max_bytes)
    except ArtifactPathForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except UnsupportedArtifactExtensionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ArtifactPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Artifact read failed.") from exc

    return {
        "path": _display_path(result.path),
        "filename": result.filename,
        "extension": result.extension,
        "content": result.content,
        "truncated": result.truncated,
        "size_bytes": result.size_bytes,
        "modified_at": result.modified_at,
    }


@router.get("/download")
def download_artifact(path: str | None = Query(None)) -> FileResponse:
    try:
        resolved = resolve_artifact_path(_required_path(path))
        if not resolved.exists():
            raise FileNotFoundError(f"Artifact not found: {_display_path(resolved)}")
        if not resolved.is_file():
            raise ArtifactPathError(f"Path is not a file: {_display_path(resolved)}")
    except ArtifactPathForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ArtifactPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Artifact download failed.") from exc
    return FileResponse(resolved, filename=resolved.name)


def _run_artifacts_response(run_type: str, run_id: str) -> dict:
    try:
        result = list_run_artifacts(run_type, run_id)
    except ArtifactPathForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ArtifactPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Artifact listing failed.") from exc
    return {
        "run_id": result.run_id,
        "run_type": result.run_type,
        "run_dir": _display_path(result.run_dir),
        "items": [item.to_api_dict() for item in result.items],
    }


def _required_path(path: str | None) -> str:
    if path is None or not path.strip():
        raise ArtifactPathError("path is required.")
    return path


def _display_path(path: Path) -> str:
    resolved = path.expanduser().resolve(strict=False)
    try:
        return str(resolved.relative_to(Path.cwd().resolve(strict=False)))
    except ValueError:
        return str(resolved)
