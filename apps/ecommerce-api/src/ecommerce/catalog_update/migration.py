"""Database migration step for catalog updates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from ecommerce.catalog_update.paths import display_path, ecommerce_app_root
from ecommerce.catalog_update.redaction import sanitize_output
from ecommerce.catalog_update.types import CatalogUpdateError
from ecommerce.db.config import get_database_url


def run_alembic_upgrade() -> dict[str, Any]:
    command = [sys.executable, "-m", "alembic", "upgrade", "head"]
    app_root = ecommerce_app_root()
    database_url = get_database_url()
    try:
        completed = subprocess.run(
            command,
            cwd=app_root,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = sanitize_output(f"{exc.stdout or ''}\n{exc.stderr or ''}", database_url)
        raise CatalogUpdateError(f"Migration failed: alembic upgrade head timed out. {output}".strip()) from exc
    except Exception as exc:
        raise CatalogUpdateError(f"Migration failed: {exc.__class__.__name__}") from exc

    stdout = sanitize_output(completed.stdout, database_url)
    stderr = sanitize_output(completed.stderr, database_url)
    payload = {
        "status": "succeeded" if completed.returncode == 0 else "failed",
        "command": [Path(sys.executable).name, "-m", "alembic", "upgrade", "head"],
        "cwd": display_path(app_root),
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }
    if completed.returncode != 0:
        raise CatalogUpdateError(f"Migration failed: {stderr or stdout or 'alembic upgrade head failed'}")
    return payload
