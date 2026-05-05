"""Safe artifact root and preview helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from ecommerce.env import load_local_env_if_present

ARTIFACT_ROOTS_ENV_VAR = "ECOMMERCE_ARTIFACT_ROOTS"
DEFAULT_ARTIFACT_ROOTS = (
    Path("output") / "ecommerce" / "bridge" / "runs",
    Path("output") / "ecommerce" / "monitoring" / "runs",
    Path("output") / "ecommerce" / "source-url-agent" / "runs",
    Path("output") / "vendor_sources" / "captures" / "runs",
)
RUN_TYPE_ROOTS = {
    "bridge": DEFAULT_ARTIFACT_ROOTS[0],
    "price_monitoring": DEFAULT_ARTIFACT_ROOTS[1],
    "source_url_agent": DEFAULT_ARTIFACT_ROOTS[2],
    "vendor_sources": DEFAULT_ARTIFACT_ROOTS[3],
}
RUN_TYPE_PATH_SEGMENTS = {
    "bridge": "bridge",
    "price_monitoring": "monitoring",
    "source_url_agent": "source-url-agent",
    "vendor_sources": "vendor_sources",
}
TEXT_ARTIFACT_EXTENSIONS = {".csv", ".json", ".txt", ".log"}


class ArtifactPathError(ValueError):
    """Raised when an artifact path request is malformed."""


class ArtifactPathForbiddenError(PermissionError):
    """Raised when an artifact path is outside configured roots."""


class UnsupportedArtifactExtensionError(ValueError):
    """Raised when a preview is requested for an unsupported file type."""


@dataclass(frozen=True)
class ArtifactItem:
    name: str
    path: Path
    extension: str
    size_bytes: int
    modified_at: str

    def to_api_dict(self) -> dict:
        payload = artifact_link_payload(self.path)
        payload.update(
            {
                "extension": self.extension,
                "size_bytes": self.size_bytes,
                "modified_at": self.modified_at,
            }
        )
        return payload


@dataclass(frozen=True)
class ArtifactListResult:
    run_id: str
    run_type: str
    run_dir: Path
    items: list[ArtifactItem]


@dataclass(frozen=True)
class ArtifactTextResult:
    path: Path
    filename: str
    extension: str
    content: str
    truncated: bool
    size_bytes: int
    modified_at: str


def get_artifact_roots() -> list[Path]:
    load_local_env_if_present()
    roots = list(DEFAULT_ARTIFACT_ROOTS)
    configured = os.environ.get(ARTIFACT_ROOTS_ENV_VAR)
    if configured:
        roots.extend(Path(part.strip()) for part in configured.split(";") if part.strip())
    return _dedupe_paths(roots)


def get_artifact_root_entries() -> list[dict]:
    load_local_env_if_present()
    entries = [_root_entry(root, "default", is_default=True, is_configured=False) for root in DEFAULT_ARTIFACT_ROOTS]
    configured = os.environ.get(ARTIFACT_ROOTS_ENV_VAR)
    if configured:
        entries.extend(
            _root_entry(Path(part.strip()), ARTIFACT_ROOTS_ENV_VAR, is_default=False, is_configured=True)
            for part in configured.split(";")
            if part.strip()
        )
    return _dedupe_root_entries(entries)


def resolve_artifact_path(path: str | Path) -> Path:
    requested = Path(path)
    if _contains_parent_reference(requested):
        raise ArtifactPathError("Path traversal is not allowed.")
    resolved = _resolve_path(requested)
    if not is_artifact_path_allowed(resolved):
        raise ArtifactPathForbiddenError(f"Path is outside allowed artifact roots: {_display_path(resolved)}")
    return resolved


def is_artifact_path_allowed(path: Path) -> bool:
    resolved = _resolve_path(path)
    return any(_same_or_child(resolved, _resolve_path(root)) for root in get_artifact_roots())


def list_run_artifacts(run_type: str, run_id: str) -> ArtifactListResult:
    normalized_run_type = _normalize_run_type(run_type)
    safe_run_id = _validate_run_id(run_id)
    candidates = [_resolve_path(root / safe_run_id) for root in _run_roots(normalized_run_type)]
    run_dir = next((candidate for candidate in candidates if candidate.exists()), candidates[0])

    if not is_artifact_path_allowed(run_dir):
        raise ArtifactPathForbiddenError("Run folder is outside allowed artifact roots.")
    if not run_dir.exists():
        raise FileNotFoundError(f"Run folder not found: {_display_path(run_dir)}")
    if not run_dir.is_dir():
        raise ArtifactPathError(f"Run path is not a directory: {_display_path(run_dir)}")

    items = []
    for child in run_dir.iterdir():
        if not child.is_file():
            continue
        items.append(_artifact_item(child))
    items.sort(key=lambda item: item.name.casefold())
    return ArtifactListResult(
        run_id=safe_run_id,
        run_type="price-monitoring" if normalized_run_type == "price_monitoring" else normalized_run_type,
        run_dir=run_dir,
        items=items,
    )


def read_text_artifact(path: Path, max_bytes: int = 1048576) -> ArtifactTextResult:
    if max_bytes < 1:
        raise ArtifactPathError("max_bytes must be greater than 0.")

    resolved = resolve_artifact_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"Artifact not found: {_display_path(resolved)}")
    if not resolved.is_file():
        raise ArtifactPathError(f"Path is not a file: {_display_path(resolved)}")
    extension = resolved.suffix.lower()
    if extension not in TEXT_ARTIFACT_EXTENSIONS:
        raise UnsupportedArtifactExtensionError("Unsupported preview extension.")

    stat = resolved.stat()
    with resolved.open("rb") as f:
        content_bytes = f.read(max_bytes + 1)
    truncated = len(content_bytes) > max_bytes
    if truncated:
        content_bytes = content_bytes[:max_bytes]
    try:
        content = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = content_bytes.decode("utf-8", errors="replace")

    return ArtifactTextResult(
        path=resolved,
        filename=resolved.name,
        extension=extension,
        content=content,
        truncated=truncated,
        size_bytes=stat.st_size,
        modified_at=_modified_at(stat.st_mtime),
    )


def artifact_link_payload(path: Path, include_forbidden_links: bool = False) -> dict:
    display_path = _display_path(Path(path))
    encoded_path = quote(display_path, safe="")
    is_allowed = is_artifact_path_allowed(Path(path))
    can_access = is_allowed or include_forbidden_links
    return {
        "name": Path(path).name,
        "path": display_path,
        "download_url": f"/api/artifacts/download?path={encoded_path}" if can_access else "",
        "read_url": f"/api/artifacts/read?path={encoded_path}" if can_access else "",
        "is_allowed": is_allowed,
        "can_read": is_allowed,
        "can_download": is_allowed,
        "warning": "" if is_allowed else "outside_configured_artifact_roots",
    }


def _artifact_item(path: Path) -> ArtifactItem:
    stat = path.stat()
    return ArtifactItem(
        name=path.name,
        path=path,
        extension=path.suffix.lower(),
        size_bytes=stat.st_size,
        modified_at=_modified_at(stat.st_mtime),
    )


def _normalize_run_type(run_type: str) -> str:
    normalized = run_type.strip().lower().replace("-", "_")
    if normalized not in RUN_TYPE_ROOTS:
        raise ArtifactPathError("run_type must be one of: bridge, price_monitoring, source_url_agent, vendor_sources")
    return normalized


def _validate_run_id(run_id: str) -> str:
    value = run_id.strip()
    parts = Path(value).parts
    if not value or len(parts) != 1 or value in {".", ".."} or _contains_parent_reference(Path(value)):
        raise ArtifactPathError("Invalid run_id.")
    return value


def _run_roots(run_type: str) -> list[Path]:
    load_local_env_if_present()
    default_root = RUN_TYPE_ROOTS[run_type]
    roots = [default_root]
    configured = os.environ.get(ARTIFACT_ROOTS_ENV_VAR)
    if configured:
        expected_parent = RUN_TYPE_PATH_SEGMENTS[run_type]
        env_roots = [Path(part.strip()) for part in configured.split(";") if part.strip()]
        matching_env_roots = [
            root
            for root in env_roots
            if root.name == "runs" and root.parent.name.lower() == expected_parent
        ]
        roots.extend(matching_env_roots or env_roots)
    return _dedupe_paths(roots)


def _dedupe_paths(paths: list[Path] | tuple[Path, ...]) -> list[Path]:
    seen: set[str] = set()
    result = []
    for path in paths:
        key = str(_resolve_path(path)).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


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


def _resolve_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _same_or_child(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _contains_parent_reference(path: Path) -> bool:
    return any(part == ".." for part in path.parts)


def _display_path(path: Path) -> str:
    resolved = _resolve_path(path)
    try:
        return str(resolved.relative_to(Path.cwd().resolve(strict=False)))
    except ValueError:
        return str(resolved)


def _modified_at(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).replace(microsecond=0).isoformat()
