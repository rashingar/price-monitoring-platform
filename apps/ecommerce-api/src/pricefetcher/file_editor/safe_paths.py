"""Safe root handling for local file editor operations."""

from __future__ import annotations

import os
from pathlib import Path

from pricefetcher.env import load_local_env_if_present

FILE_ROOTS_ENV_VAR = "PRICEFETCHER_FILE_ROOTS"
DEFAULT_FILE_ROOTS = (
    Path(r"C:\Users\user\Downloads"),
    Path(r"C:\Exports"),
    Path("output"),
)


class UnsafePathError(PermissionError):
    """Raised when a requested path is outside the configured safe roots."""


def get_allowed_roots() -> list[Path]:
    load_local_env_if_present()
    configured = os.environ.get(FILE_ROOTS_ENV_VAR)
    if configured is not None:
        roots = [Path(part.strip()) for part in configured.split(";") if part.strip()]
    else:
        roots = list(DEFAULT_FILE_ROOTS)
    return [_resolve_path(root) for root in roots]


def get_file_root_entries() -> list[dict]:
    load_local_env_if_present()
    configured = os.environ.get(FILE_ROOTS_ENV_VAR)
    if configured is not None:
        entries = [
            _root_entry(Path(part.strip()), FILE_ROOTS_ENV_VAR, is_default=False, is_configured=True)
            for part in configured.split(";")
            if part.strip()
        ]
    else:
        entries = [_root_entry(root, "default", is_default=True, is_configured=False) for root in DEFAULT_FILE_ROOTS]
    return _dedupe_root_entries(entries)


def resolve_safe_path(path: str | Path) -> Path:
    resolved = _resolve_path(Path(path))
    roots = get_allowed_roots()
    if not is_path_allowed(resolved, roots):
        raise UnsafePathError(f"Path is outside allowed roots: {resolved}")
    return resolved


def is_path_allowed(path: Path, roots: list[Path]) -> bool:
    resolved = _resolve_path(path)
    for root in roots:
        resolved_root = _resolve_path(root)
        if _same_or_child(resolved, resolved_root):
            return True
    return False


def _resolve_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _same_or_child(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _dedupe_root_entries(entries: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result = []
    for entry in entries:
        key = str(entry["path"]).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result


def _root_entry(path: Path, source: str, *, is_default: bool, is_configured: bool) -> dict:
    resolved = _resolve_path(path)
    return {
        "path": str(resolved),
        "source": source,
        "exists": resolved.exists(),
        "is_default": is_default,
        "is_configured": is_configured,
    }
