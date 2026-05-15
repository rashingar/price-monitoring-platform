from __future__ import annotations

import os
import re
from pathlib import Path

from .repo_paths import REPO_ROOT

ENV_FILENAME = ".env"
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_local_env_if_present() -> dict[str, object]:
    monorepo_root = _monorepo_root()
    root_env = monorepo_root / ENV_FILENAME
    app_env = REPO_ROOT / ENV_FILENAME
    keys_loaded: list[str] = []
    keys_skipped_existing: list[str] = []
    keys_skipped_deprecated_duplicate: list[str] = []
    warnings: list[str] = []
    status: dict[str, object] = {
        "root_path": str(root_env) if root_env.is_file() else None,
        "deprecated_app_path": str(app_env) if app_env.is_file() else None,
        "keys_loaded": keys_loaded,
        "keys_skipped_existing": keys_skipped_existing,
        "keys_skipped_deprecated_duplicate": keys_skipped_deprecated_duplicate,
        "warnings": warnings,
    }

    root_keys: set[str] = set()
    if root_env.is_file():
        for key, value in _parse_env_file(root_env):
            root_keys.add(key)
            if key in os.environ:
                keys_skipped_existing.append(key)
                continue
            os.environ[key] = value
            keys_loaded.append(key)

    if app_env.is_file() and app_env != root_env:
        warnings.append(
            "Deprecated app-local .env detected. Move values to repo-root .env; "
            "OS env vars still override both, and repo-root .env is preferred."
        )
        for key, value in _parse_env_file(app_env):
            if key in root_keys:
                keys_skipped_deprecated_duplicate.append(key)
                continue
            if key in os.environ:
                keys_skipped_existing.append(key)
                continue
            os.environ[key] = value
            keys_loaded.append(key)

    return status


def _monorepo_root() -> Path:
    for directory in (REPO_ROOT, *REPO_ROOT.parents):
        if (directory / "AGENTS.md").is_file() and (directory / "apps").is_dir():
            return directory
        if (directory / ".git").exists():
            return directory
    return REPO_ROOT


def _parse_env_file(path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return entries
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        raw_key, raw_value = line.split("=", 1)
        key = raw_key.strip()
        if not _ENV_KEY_RE.fullmatch(key):
            continue
        entries.append((key, _strip_optional_quotes(raw_value.strip())))
    return entries


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
