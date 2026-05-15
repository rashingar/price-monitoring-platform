"""Path helpers for catalog update artifacts."""

from __future__ import annotations

import re
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def ecommerce_app_root() -> Path:
    return Path(__file__).resolve().parents[3]


def catalog_update_output_dir(job_id: str) -> Path:
    return repo_root() / "output" / "catalog_updates" / safe_path_segment(job_id)


def safe_path_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value or "job")


def safe_filename(value: str, *, default: str = "sourceCata.csv") -> str:
    name = Path(value).name.strip()
    return safe_path_segment(name) or default


def display_path(path: Path) -> str:
    resolved = path.expanduser().resolve(strict=False)
    try:
        return str(resolved.relative_to(repo_root().resolve(strict=False)))
    except ValueError:
        return str(resolved)
