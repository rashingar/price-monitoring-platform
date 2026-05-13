"""Artifact evidence helpers for DB-backed Price Monitoring runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ecommerce.artifacts import artifact_link_payload, is_artifact_path_allowed


RUN_ARTIFACT_PATH_FIELDS = (
    "input_csv_path",
    "selection_summary_path",
    "fetch_result_path",
    "enriched_csv_path",
    "fetch_summary_path",
)


@dataclass(frozen=True)
class RunArtifactEvidence:
    artifacts: list[dict[str, Any]]
    warnings: list[str]


def build_run_artifact_evidence(run_payload: dict[str, object]) -> RunArtifactEvidence:
    """Attach artifact links for DB-referenced paths without reading artifact state as truth."""

    artifacts: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()

    for field in RUN_ARTIFACT_PATH_FIELDS:
        path = _optional_path(run_payload.get(field))
        if path is None:
            continue
        if not path.exists() or not path.is_file():
            warnings.append(f"Referenced artifact is missing: {field}={path}")
            continue
        _append_artifact(artifacts, seen, path)

    output_dir = _optional_path(run_payload.get("output_dir"))
    if output_dir is None:
        return RunArtifactEvidence(artifacts=artifacts, warnings=warnings)
    if not output_dir.exists():
        warnings.append(f"Run artifact directory is missing: {output_dir}")
        return RunArtifactEvidence(artifacts=artifacts, warnings=warnings)
    if not output_dir.is_dir():
        warnings.append(f"Run artifact path is not a directory: {output_dir}")
        return RunArtifactEvidence(artifacts=artifacts, warnings=warnings)
    if not is_artifact_path_allowed(output_dir):
        warnings.append(f"Run artifact directory is outside allowed artifact roots: {output_dir}")
        return RunArtifactEvidence(artifacts=artifacts, warnings=warnings)

    for child in sorted(output_dir.iterdir(), key=lambda item: item.name.casefold()):
        if child.is_file():
            _append_artifact(artifacts, seen, child)
    return RunArtifactEvidence(artifacts=artifacts, warnings=warnings)


def _append_artifact(artifacts: list[dict[str, Any]], seen: set[str], path: Path) -> None:
    key = str(path.expanduser().resolve(strict=False)).casefold()
    if key in seen:
        return
    seen.add(key)
    artifacts.append(artifact_link_payload(path))


def _optional_path(value: object) -> Path | None:
    text = str(value or "").strip()
    return Path(text) if text else None
