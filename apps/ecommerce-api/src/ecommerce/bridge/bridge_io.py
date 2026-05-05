"""Bridge IO helpers for run folder and artifact discovery."""

from __future__ import annotations

import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple
import logging

LOGGER = logging.getLogger("ecommerce.bridge.io")


def prepare_run(base_out: Path) -> Tuple[Path, Path]:
    """Create a timestamped run directory and return ``(run_dir, log_path)``."""
    timestamp = datetime.now().strftime("run-%Y%m%d-%H%M%S")
    run_dir = base_out / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "bridge.log"
    return run_dir, log_path


def mirror_latest(run_dir: Path, latest_dir: Path) -> None:
    """Replace the latest directory with the contents of the current run."""
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    latest_dir.mkdir(parents=True, exist_ok=True)
    for file in run_dir.glob("*.*"):
        shutil.copy2(file, latest_dir / file.name)


def archive_old_runs(base_out: Path, keep_days: int = 7) -> None:
    """Zip runs older than ``keep_days`` and remove the original folders."""
    cutoff = datetime.now() - timedelta(days=keep_days)
    for folder in base_out.iterdir():
        if not folder.is_dir() or folder.name == "latest":
            continue
        try:
            ts = datetime.strptime(folder.name, "run-%Y%m%d-%H%M%S")
        except ValueError:
            continue
        if ts < cutoff:
            archive_path = base_out / f"{folder.name}.zip"
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file in folder.rglob("*"):
                    if file.is_file():
                        zf.write(file, arcname=file.relative_to(folder))
            shutil.rmtree(folder)
            LOGGER.info("Archived %s", folder)


def find_latest(latest_dir: Path, prefix: str) -> Optional[Path]:
    """Find the most recent CSV in ``latest_dir`` starting with ``prefix``."""
    if not latest_dir.exists():
        return None
    candidates = [p for p in latest_dir.glob(f"{prefix}*.csv") if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)
