"""JSON writing helpers for summary artifacts."""

from __future__ import annotations

import json
from pathlib import Path


def write_json(path: Path, payload: dict[str, object], encoding: str) -> None:
    with path.open("w", encoding=encoding) as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
        handle.write("\n")
