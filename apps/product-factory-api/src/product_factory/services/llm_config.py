from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ..repo_paths import REPO_ROOT
from .errors import ServiceError, ServiceErrorCode


@dataclass(frozen=True, slots=True)
class OpenAILLMConfig:
    api_key: str
    model: str
    reasoning_effort: str | None = None


def load_openai_llm_config(
    *,
    env: Mapping[str, str] | None = None,
    env_file: Path | None = None,
) -> OpenAILLMConfig:
    source_env = os.environ if env is None else env
    file_values = (
        _read_env_file(env_file) if env_file is not None else _read_default_env_files()
    )
    api_key = str(
        source_env.get("OPENAI_API_KEY") or file_values.get("OPENAI_API_KEY") or ""
    ).strip()
    model = str(
        source_env.get("OPENAI_MODEL") or file_values.get("OPENAI_MODEL") or ""
    ).strip()
    reasoning_effort = _normalize_reasoning_effort(
        source_env.get("OPENAI_REASONING_EFFORT")
        or file_values.get("OPENAI_REASONING_EFFORT")
        or ""
    )
    if not api_key:
        raise ServiceError(
            ServiceErrorCode.UNEXPECTED_FAILURE.value,
            "Missing OPENAI_API_KEY. Set it in the environment or repo-root .env.",
        )
    if not model:
        raise ServiceError(
            ServiceErrorCode.UNEXPECTED_FAILURE.value,
            "Missing OPENAI_MODEL. Set it in the environment or repo-root .env.",
        )
    return OpenAILLMConfig(
        api_key=api_key,
        model=model,
        reasoning_effort=reasoning_effort,
    )


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, value = line.split("=", 1)
        key = key.strip()
        if key in {"OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_REASONING_EFFORT"}:
            values[key] = _strip_env_value(value.strip())
    return values


def _read_default_env_files() -> dict[str, str]:
    values = _read_env_file(_monorepo_root() / ".env")
    legacy_values = _read_env_file(REPO_ROOT / ".secrets" / ".env.local")
    for key, value in legacy_values.items():
        values.setdefault(key, value)
    return values


def _monorepo_root() -> Path:
    for directory in (REPO_ROOT, *REPO_ROOT.parents):
        if (directory / "AGENTS.md").is_file() and (directory / "apps").is_dir():
            return directory
        if (directory / ".git").exists():
            return directory
    return REPO_ROOT


def _strip_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _normalize_reasoning_effort(value: object) -> str | None:
    normalized = str(value or "").strip()
    if normalized.lower() in {"", "none"}:
        return None
    return normalized
