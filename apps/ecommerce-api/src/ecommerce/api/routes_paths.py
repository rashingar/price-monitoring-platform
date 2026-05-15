"""Local path root diagnostics for browser UI clients."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter

from ecommerce.artifacts import ARTIFACT_ROOTS_ENV_VAR, get_artifact_root_entries
from ecommerce.db.config import DATABASE_URL_ENV_VAR, is_database_configured
from ecommerce.env import describe_local_env_warnings, load_local_env_if_present
from ecommerce.file_editor import FILE_ROOTS_ENV_VAR, get_file_root_entries
from ecommerce.io.paths import DEFAULT_OUTPUT_DIR, DEFAULT_RUNTIME_CONFIG_PATH, load_runtime_config

router = APIRouter(prefix="/api/paths", tags=["paths"])


@router.get("/roots")
def get_path_roots() -> dict:
    env_status = load_local_env_if_present()
    return {
        "artifact_roots": get_artifact_root_entries(),
        "file_roots": get_file_root_entries(),
        "output_roots": _output_root_entries(),
        "env": {
            ARTIFACT_ROOTS_ENV_VAR: _env_status(ARTIFACT_ROOTS_ENV_VAR),
            FILE_ROOTS_ENV_VAR: _env_status(FILE_ROOTS_ENV_VAR),
            DATABASE_URL_ENV_VAR: "configured" if is_database_configured() else "not_configured",
        },
        "env_readiness": _env_readiness(),
        "local_env": {
            "root_env_loaded": env_status["root_path"] is not None,
            "deprecated_app_env_detected": env_status["deprecated_app_env_detected"],
            "keys_loaded": sorted(set(env_status["keys_loaded"])),
            "keys_skipped_existing": sorted(set(env_status["keys_skipped_existing"])),
            "keys_skipped_deprecated_duplicate": sorted(
                set(env_status["keys_skipped_deprecated_duplicate"])
            ),
            "warnings": describe_local_env_warnings(env_status),
        },
        "path_separator": ";",
        "platform": "Windows-compatible",
    }


def _output_root_entries() -> list[dict]:
    entries = [_root_entry(Path(DEFAULT_OUTPUT_DIR), "default", is_default=True, is_configured=False)]
    runtime_config = load_runtime_config()
    runtime_output = Path(runtime_config.output_dir)
    if _resolve_path(runtime_output) != _resolve_path(Path(DEFAULT_OUTPUT_DIR)):
        entries.append(
            _root_entry(
                runtime_output,
                str(DEFAULT_RUNTIME_CONFIG_PATH),
                is_default=False,
                is_configured=DEFAULT_RUNTIME_CONFIG_PATH.exists(),
            )
        )
    return _dedupe_root_entries(entries)


def _env_status(name: str) -> str:
    return "configured" if os.environ.get(name) is not None else "not_configured"


def _env_readiness() -> list[dict]:
    groups = [
        ("Database", [DATABASE_URL_ENV_VAR]),
        (
            "OpenCart",
            ["OPENCART_STORE_BASE", "OPENCART_ADMIN_PATH", "OPENCART_ADMIN_USER", "OPENCART_ADMIN_PASS"],
        ),
        ("Brave Search", ["BRAVE_SEARCH_API_KEY"]),
        ("File roots", [ARTIFACT_ROOTS_ENV_VAR, FILE_ROOTS_ENV_VAR]),
        ("Product Factory", ["ECOMMERCE_API_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"]),
    ]
    return [_env_group_status(name, keys) for name, keys in groups]


def _env_group_status(name: str, keys: list[str]) -> dict:
    missing = [key for key in keys if not str(os.environ.get(key) or "").strip()]
    configured = [key for key in keys if key not in missing]
    return {
        "name": name,
        "status": "configured" if not missing else "missing",
        "configured_keys": configured,
        "missing_keys": missing,
    }


def _root_entry(path: Path, source: str, *, is_default: bool, is_configured: bool) -> dict:
    resolved = _resolve_path(path)
    return {
        "path": str(resolved),
        "source": source,
        "exists": resolved.exists(),
        "is_default": is_default,
        "is_configured": is_configured,
    }


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


def _resolve_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)
