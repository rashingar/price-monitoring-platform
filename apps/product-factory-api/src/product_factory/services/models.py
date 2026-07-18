from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ..status_fields import (
    DEFAULT_BESTPRICE_STATUS,
    DEFAULT_BOXNOW_STATUS,
    DEFAULT_SKR_OUTZ_STATUS,
)


class RunType(str, Enum):
    PREPARE = "prepare"
    RENDER = "render"
    PUBLISH = "publish"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class PrepareRequest:
    model: str
    url: str
    photos: int = 1
    sections: int = 0
    bestprice_status: int = DEFAULT_BESTPRICE_STATUS
    skroutz_status: int = DEFAULT_SKR_OUTZ_STATUS
    boxnow: int = DEFAULT_BOXNOW_STATUS
    price: str | float | int = 0
    manual_mpn: str | None = None
    gallery_url: str | None = None
    characteristics_url: str | None = None
    second_opencart_image_index: int | None = None
    gallery_mode: str | None = None


@dataclass(slots=True)
class RenderRequest:
    model: str


@dataclass(slots=True)
class PublishRequest:
    model: str
    current_job_product_file: Path | None = None


@dataclass(slots=True)
class RunArtifacts:
    model_root: Path | None = None
    scrape_dir: Path | None = None
    llm_dir: Path | None = None
    candidate_dir: Path | None = None
    raw_html_path: Path | None = None
    source_json_path: Path | None = None
    scrape_normalized_json_path: Path | None = None
    source_report_json_path: Path | None = None
    llm_task_manifest_path: Path | None = None
    intro_text_context_path: Path | None = None
    intro_text_prompt_path: Path | None = None
    intro_text_output_path: Path | None = None
    seo_meta_context_path: Path | None = None
    seo_meta_prompt_path: Path | None = None
    seo_meta_output_path: Path | None = None
    candidate_csv_path: Path | None = None
    published_csv_path: Path | None = None
    candidate_normalized_json_path: Path | None = None
    validation_report_path: Path | None = None
    description_html_path: Path | None = None
    characteristics_html_path: Path | None = None
    category_filter_review_path: Path | None = None
    metadata_path: Path | None = None


@dataclass(slots=True)
class RunMetadata:
    model: str
    run_type: RunType
    status: RunStatus = RunStatus.QUEUED
    schema_version: str = "1.0"
    run_id: str = ""
    requested_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error_code: str | None = None
    error_detail: str | None = None


@dataclass(slots=True)
class ServiceResult:
    run: RunMetadata
    artifacts: RunArtifacts = field(default_factory=RunArtifacts)
    details: dict[str, Any] = field(default_factory=dict)
