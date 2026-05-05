from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .utils import ensure_directory, write_json, write_text


@dataclass(slots=True)
class PrepareScrapePersistenceInput:
    model: str
    scrape_dir: Path
    raw_html: str
    source_payload: Mapping[str, Any]
    normalized_payload: Mapping[str, Any]
    report_payload: Mapping[str, Any]
    bescos_raw_payload: Mapping[str, Any] | None = None

    @property
    def raw_html_path(self) -> Path:
        return Path(self.scrape_dir) / f"{self.model}.raw.html"

    @property
    def source_json_path(self) -> Path:
        return Path(self.scrape_dir) / f"{self.model}.source.json"

    @property
    def normalized_json_path(self) -> Path:
        return Path(self.scrape_dir) / f"{self.model}.normalized.json"

    @property
    def report_json_path(self) -> Path:
        return Path(self.scrape_dir) / f"{self.model}.report.json"

    @property
    def bescos_raw_path(self) -> Path:
        return Path(self.scrape_dir) / "bescos_raw.json"


@dataclass(slots=True)
class PrepareScrapePersistenceResult:
    scrape_dir: Path
    raw_html_path: Path
    source_json_path: Path
    normalized_json_path: Path
    report_json_path: Path
    bescos_raw_path: Path


def persist_prepare_scrape_artifacts(
    persistence_input: PrepareScrapePersistenceInput,
) -> PrepareScrapePersistenceResult:
    scrape_dir = ensure_directory(persistence_input.scrape_dir)
    raw_html_path = persistence_input.raw_html_path
    source_json_path = persistence_input.source_json_path
    normalized_json_path = persistence_input.normalized_json_path
    report_json_path = persistence_input.report_json_path
    bescos_raw_path = persistence_input.bescos_raw_path

    if bescos_raw_path.exists():
        bescos_raw_path.unlink()

    write_text(raw_html_path, persistence_input.raw_html)
    write_json(source_json_path, persistence_input.source_payload)
    write_json(normalized_json_path, persistence_input.normalized_payload)
    write_json(report_json_path, persistence_input.report_payload)

    if persistence_input.bescos_raw_payload is not None:
        write_json(bescos_raw_path, persistence_input.bescos_raw_payload)

    return PrepareScrapePersistenceResult(
        scrape_dir=scrape_dir,
        raw_html_path=raw_html_path,
        source_json_path=source_json_path,
        normalized_json_path=normalized_json_path,
        report_json_path=report_json_path,
        bescos_raw_path=bescos_raw_path,
    )
