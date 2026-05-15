"""Catalog exclusion file loading and sourceCata filtering."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path
from typing import Callable

from ecommerce.catalog_update.config import env_text
from ecommerce.catalog_update.paths import repo_root
from ecommerce.catalog_update.types import (
    DEFAULT_EXCLUDED_MODELS_RELATIVE_PATH,
    DEFAULT_EXPORT_PROFILE,
    EXCLUDED_MODELS_ENV_VAR,
    CatalogExclusionFilterResult,
    CatalogUpdateError,
    ExcludedModels,
)
from ecommerce.env import load_local_env_if_present


def normalize_downloaded_csv(downloaded_path: Path, output_dir: Path) -> Path:
    if not downloaded_path.exists():
        raise CatalogUpdateError("OpenCart export failed: downloaded CSV is missing.")
    final_path = output_dir / f"{DEFAULT_EXPORT_PROFILE}.csv"
    if downloaded_path.resolve(strict=False) != final_path.resolve(strict=False):
        shutil.copy2(downloaded_path, final_path)
    return final_path


def load_excluded_models(path: Path | None = None, *, repo_root_func: Callable[[], Path] = repo_root) -> ExcludedModels:
    load_local_env_if_present()
    explicit_value = env_text(EXCLUDED_MODELS_ENV_VAR)
    explicit_path = explicit_value is not None
    resolved_path = Path(explicit_value).expanduser() if explicit_value else (repo_root_func() / DEFAULT_EXCLUDED_MODELS_RELATIVE_PATH)
    if path is not None:
        resolved_path = path.expanduser()
        explicit_path = True
    resolved_path = resolved_path.resolve(strict=False)
    if not resolved_path.exists():
        if explicit_path:
            raise CatalogUpdateError(f"Catalog exclusion file not found: {resolved_path}")
        return ExcludedModels(path=resolved_path, found=False, explicit_path=False, models=frozenset())

    try:
        with resolved_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
    except OSError as exc:
        raise CatalogUpdateError(f"Catalog exclusion file could not be read: {resolved_path}") from exc

    return ExcludedModels(
        path=resolved_path,
        found=True,
        explicit_path=explicit_path,
        models=frozenset(excluded_models_from_rows(rows, resolved_path)),
    )


def filter_source_catalog_exclusions(
    source_cata_path: Path,
    output_dir: Path,
    exclusions: ExcludedModels,
) -> CatalogExclusionFilterResult:
    filtered_path = output_dir / "sourceCata.filtered.csv"
    try:
        with source_cata_path.open("r", encoding="utf-8-sig", newline="") as input_handle:
            reader = csv.DictReader(input_handle)
            fieldnames = list(reader.fieldnames or [])
            if "model" not in fieldnames:
                raise CatalogUpdateError("Catalog update exclusion filtering failed: sourceCata.csv is missing required model column.")
            rows = list(reader)
    except OSError as exc:
        raise CatalogUpdateError(f"Catalog update exclusion filtering failed: could not read {source_cata_path}") from exc

    kept_rows: list[dict[str, str]] = []
    removed_row_count = 0
    for row in rows:
        model = str(row.get("model") or "").strip()
        if model and model in exclusions.models:
            removed_row_count += 1
            continue
        kept_rows.append(row)

    try:
        with filtered_path.open("w", encoding="utf-8", newline="") as output_handle:
            writer = csv.DictWriter(output_handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(kept_rows)
    except OSError as exc:
        raise CatalogUpdateError(f"Catalog update exclusion filtering failed: could not write {filtered_path}") from exc

    return CatalogExclusionFilterResult(
        exclusion_file_path=exclusions.path,
        exclusion_file_found=exclusions.found,
        excluded_model_count=exclusions.count,
        input_row_count=len(rows),
        removed_row_count=removed_row_count,
        output_row_count=len(kept_rows),
        filtered_csv_path=filtered_path,
    )


def excluded_models_from_rows(rows: list[list[str]], path: Path) -> set[str]:
    non_empty_rows = [row for row in rows if any(str(cell).strip() for cell in row)]
    if not non_empty_rows:
        return set()

    first_row = [str(cell).strip() for cell in non_empty_rows[0]]
    normalized_header = [cell.casefold() for cell in first_row]
    if "model" in normalized_header:
        model_index = normalized_header.index("model")
        return {
            str(row[model_index]).strip()
            for row in non_empty_rows[1:]
            if model_index < len(row) and str(row[model_index]).strip()
        }

    max_columns = max(len(row) for row in non_empty_rows)
    if max_columns == 1:
        return {str(row[0]).strip() for row in non_empty_rows if row and str(row[0]).strip()}

    raise CatalogUpdateError(f"Catalog exclusion file must contain a model header or a single model column: {path}")
