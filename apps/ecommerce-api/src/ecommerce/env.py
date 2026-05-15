"""Local development environment loading."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TypedDict

ENV_FILENAME = ".env"
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class LocalEnvLoadStatus(TypedDict):
    loaded: bool
    path: str | None
    root_path: str | None
    deprecated_app_path: str | None
    deprecated_app_env_detected: bool
    keys_loaded: list[str]
    keys_loaded_from_root: list[str]
    keys_loaded_from_deprecated_app: list[str]
    keys_skipped_existing: list[str]
    keys_skipped_deprecated_duplicate: list[str]
    warnings: list[str]


def load_local_env_if_present() -> LocalEnvLoadStatus:
    """Load local .env values without overriding OS environment.

    Repo-root .env is preferred. App-local .env files are deprecated and are
    loaded only as a compatibility fallback for keys not set by the OS or the
    repo-root .env.
    """

    repo_root = _find_repo_root()
    root_env_path = repo_root / ENV_FILENAME if repo_root is not None else _find_local_env()
    if root_env_path is not None and not root_env_path.is_file():
        root_env_path = None
    deprecated_app_env_path = _find_deprecated_app_env(repo_root, root_env_path)
    status: LocalEnvLoadStatus = {
        "loaded": False,
        "path": (
            str(root_env_path or deprecated_app_env_path)
            if (root_env_path or deprecated_app_env_path)
            else None
        ),
        "root_path": str(root_env_path) if root_env_path else None,
        "deprecated_app_path": str(deprecated_app_env_path) if deprecated_app_env_path else None,
        "deprecated_app_env_detected": deprecated_app_env_path is not None,
        "keys_loaded": [],
        "keys_loaded_from_root": [],
        "keys_loaded_from_deprecated_app": [],
        "keys_skipped_existing": [],
        "keys_skipped_deprecated_duplicate": [],
        "warnings": [],
    }
    if root_env_path is None and deprecated_app_env_path is None:
        return status

    root_keys: set[str] = set()
    if root_env_path is not None:
        for key, value in _parse_env_file(root_env_path):
            root_keys.add(key)
            if key in os.environ:
                status["keys_skipped_existing"].append(key)
                continue
            os.environ[key] = value
            status["keys_loaded"].append(key)
            status["keys_loaded_from_root"].append(key)

    if deprecated_app_env_path is not None:
        status["warnings"].append(
            "Deprecated app-local .env detected. Move values to repo-root .env; "
            "OS env vars still override both, and repo-root .env is preferred."
        )
        for key, value in _parse_env_file(deprecated_app_env_path):
            if key in root_keys:
                status["keys_skipped_deprecated_duplicate"].append(key)
                continue
            if key in os.environ:
                status["keys_skipped_existing"].append(key)
                continue
            os.environ[key] = value
            status["keys_loaded"].append(key)
            status["keys_loaded_from_deprecated_app"].append(key)

    status["loaded"] = True
    return status


def describe_local_env_warnings(status: LocalEnvLoadStatus) -> list[str]:
    """Return safe, key-only warning lines for local env diagnostics."""

    lines = list(status.get("warnings", []))
    duplicate_keys = sorted(set(status.get("keys_skipped_deprecated_duplicate", [])))
    if duplicate_keys:
        lines.append(
            "Deprecated app-local .env duplicate keys skipped because repo-root .env is preferred: "
            + ", ".join(duplicate_keys)
        )
    return lines


def _find_repo_root() -> Path | None:
    current = Path.cwd().resolve(strict=False)
    for directory in (current, *current.parents):
        if (directory / ".git").exists():
            return directory
        if (directory / "AGENTS.md").is_file() and (directory / "apps").is_dir():
            return directory
    env_path = _find_local_env()
    return env_path.parent if env_path is not None else None


def _find_deprecated_app_env(repo_root: Path | None, root_env_path: Path | None) -> Path | None:
    current = Path.cwd().resolve(strict=False)
    for directory in (current, *current.parents):
        if repo_root is not None and directory == repo_root:
            break
        candidate = directory / ENV_FILENAME
        if candidate.is_file() and candidate != root_env_path:
            return candidate
    return None


def _find_local_env() -> Path | None:
    current = Path.cwd().resolve(strict=False)
    for directory in (current, *current.parents):
        candidate = directory / ENV_FILENAME
        if candidate.is_file():
            return candidate
    return None


def _parse_env_file(path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return entries

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        raw_key, raw_value = stripped.split("=", 1)
        key = raw_key.strip()
        if not key or not _ENV_KEY_RE.fullmatch(key):
            continue
        entries.append((key, _strip_optional_quotes(raw_value.strip())))
    return entries


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
