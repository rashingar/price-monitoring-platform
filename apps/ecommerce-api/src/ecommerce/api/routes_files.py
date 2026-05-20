"""Safe local CSV file viewer/editor API routes."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ecommerce.file_editor import (
    InvalidCsvDelimiterError,
    UnsafePathError,
    get_allowed_roots,
    is_path_allowed,
    read_csv_file,
    resolve_safe_path,
    write_csv_copy,
    write_csv_file,
)

router = APIRouter(prefix="/api/files", tags=["files"])


class CsvReadRequest(BaseModel):
    path: str
    delimiter: str | None = None
    max_rows: int | None = None


class CsvSaveRequest(BaseModel):
    path: str
    columns: list[str]
    rows: list[dict[str, Any]]
    delimiter: str = ","


class CsvSaveCopyRequest(BaseModel):
    source_path: str
    target_path: str
    columns: list[str]
    rows: list[dict[str, Any]]
    delimiter: str = ","


@router.get("/roots")
def get_roots() -> dict:
    return {
        "roots": [
            {"path": str(root), "exists": root.exists()} for root in get_allowed_roots()
        ]
    }


@router.get("/list")
def list_files(
    root: str,
    relative_path: str = "",
    extensions: str = ".csv",
) -> dict:
    selected_root = _resolve_requested_root(root)
    directory = (selected_root / relative_path).resolve(strict=False)
    if not is_path_allowed(directory, [selected_root]):
        raise HTTPException(status_code=403, detail="Path is outside selected root.")
    if not directory.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {directory}")
    if not directory.is_dir():
        raise HTTPException(
            status_code=400, detail=f"Path is not a directory: {directory}"
        )

    allowed_extensions = _parse_extensions(extensions)
    items = []
    try:
        for child in directory.iterdir():
            if child.is_dir():
                items.append(_file_item(child, "directory"))
            elif child.is_file() and child.suffix.lower() in allowed_extensions:
                items.append(_file_item(child, "file"))
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail="Directory listing failed."
        ) from exc

    items.sort(key=lambda item: (item["type"] != "directory", item["name"].casefold()))
    return {"root": str(selected_root), "relative_path": relative_path, "items": items}


@router.post("/read")
def read_file(request: CsvReadRequest) -> dict:
    path = _safe_path_or_403(request.path)
    _require_csv_extension(path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Path is not a file: {path}")
    if request.max_rows is not None and request.max_rows < 0:
        raise HTTPException(
            status_code=400, detail="max_rows must be greater than or equal to 0"
        )

    try:
        result = read_csv_file(
            path, delimiter=request.delimiter, max_rows=request.max_rows
        )
    except InvalidCsvDelimiterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400, detail="CSV file must be UTF-8 encoded."
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="CSV read failed.") from exc

    metadata = _metadata(path)
    return {
        "path": str(path),
        "filename": path.name,
        "delimiter": result.delimiter,
        "encoding": result.encoding,
        "columns": result.columns,
        "rows": result.rows,
        "returned_rows": result.returned_rows,
        "total_rows": result.total_rows,
        "size_bytes": metadata["size_bytes"],
        "modified_at": metadata["modified_at"],
    }


@router.post("/save")
def save_file(request: CsvSaveRequest) -> dict:
    path = _safe_path_or_403(request.path)
    _require_csv_extension(path)
    _ensure_parent_allowed(path)
    return _write_response(path, request.columns, request.rows, request.delimiter)


@router.post("/save-copy")
def save_copy(request: CsvSaveCopyRequest) -> dict:
    source_path = _safe_path_or_403(request.source_path)
    target_path = _safe_path_or_403(request.target_path)
    _require_csv_extension(target_path)
    _ensure_parent_allowed(target_path)
    if not source_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Source file not found: {source_path}"
        )
    if not source_path.is_file():
        raise HTTPException(
            status_code=400, detail=f"Source path is not a file: {source_path}"
        )

    try:
        result = write_csv_copy(
            source_path, target_path, request.columns, request.rows, request.delimiter
        )
    except InvalidCsvDelimiterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="CSV write failed.") from exc
    return _write_payload(
        result.path, result.columns, result.written_rows, result.delimiter
    )


def _write_response(
    path: Path, columns: list[str], rows: list[dict[str, Any]], delimiter: str
) -> dict:
    try:
        result = write_csv_file(path, columns, rows, delimiter)
    except InvalidCsvDelimiterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="CSV write failed.") from exc
    return _write_payload(
        result.path, result.columns, result.written_rows, result.delimiter
    )


def _write_payload(
    path: Path, columns: list[str], written_rows: int, delimiter: str
) -> dict:
    metadata = _metadata(path)
    return {
        "path": str(path),
        "filename": path.name,
        "written_rows": written_rows,
        "columns": columns,
        "delimiter": delimiter,
        "size_bytes": metadata["size_bytes"],
        "modified_at": metadata["modified_at"],
    }


def _resolve_requested_root(root: str) -> Path:
    roots = get_allowed_roots()
    requested = Path(root).expanduser().resolve(strict=False)
    for allowed_root in roots:
        if requested == allowed_root or root == allowed_root.name:
            return allowed_root
    if is_path_allowed(requested, roots):
        return requested
    raise HTTPException(status_code=403, detail="Root is outside allowed roots.")


def _safe_path_or_403(path: str) -> Path:
    try:
        return resolve_safe_path(path)
    except UnsafePathError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _ensure_parent_allowed(path: Path) -> None:
    if not is_path_allowed(path.parent, get_allowed_roots()):
        raise HTTPException(
            status_code=403, detail="Target directory is outside allowed roots."
        )


def _require_csv_extension(path: Path) -> None:
    if path.suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")


def _parse_extensions(extensions: str) -> set[str]:
    parsed = set()
    for extension in extensions.split(","):
        value = extension.strip().lower()
        if not value:
            continue
        parsed.add(value if value.startswith(".") else f".{value}")
    return parsed or {".csv"}


def _file_item(path: Path, item_type: str) -> dict:
    metadata = _metadata(path)
    return {
        "name": path.name,
        "path": str(path),
        "type": item_type,
        "extension": path.suffix.lower() if item_type == "file" else "",
        "size_bytes": metadata["size_bytes"] if item_type == "file" else None,
        "modified_at": metadata["modified_at"],
    }


def _metadata(path: Path) -> dict:
    stat = path.stat()
    return {
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime)
        .replace(microsecond=0)
        .isoformat(),
    }
