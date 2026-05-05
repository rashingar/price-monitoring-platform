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
    keys_loaded: list[str]
    keys_skipped_existing: list[str]


def load_local_env_if_present() -> LocalEnvLoadStatus:
    """Load the nearest parent .env file without overriding OS environment."""

    env_path = _find_local_env()
    status: LocalEnvLoadStatus = {
        "loaded": False,
        "path": str(env_path) if env_path else None,
        "keys_loaded": [],
        "keys_skipped_existing": [],
    }
    if env_path is None:
        return status

    for key, value in _parse_env_file(env_path):
        if key in os.environ:
            status["keys_skipped_existing"].append(key)
            continue
        os.environ[key] = value
        status["keys_loaded"].append(key)

    status["loaded"] = True
    return status


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
