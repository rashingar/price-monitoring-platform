from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from product_factory.jobs.models import JobRecord, JobStatus, JobType
from product_factory.status_fields import (
    DEFAULT_BESTPRICE_STATUS,
    DEFAULT_BOXNOW_STATUS,
    DEFAULT_SKR_OUTZ_STATUS,
    status_or_default,
)

from ..source_detection import validate_url_scope
from .artifact_resolver import ResolvedArtifact

DEFAULT_FULL_PIPELINE_PHOTOS = 100
DEFAULT_FULL_PIPELINE_SECTIONS = 20
DEFAULT_FULL_PIPELINE_GALLERY_MODE = "all"


class HealthResponse(BaseModel):
    status: str = "ok"


class PrepareJobRequest(BaseModel):
    model: str
    url: str
    photos: int = 1
    sections: int = 0
    bestprice_status: int = DEFAULT_BESTPRICE_STATUS
    skroutz_status: int = DEFAULT_SKR_OUTZ_STATUS
    boxnow: int = DEFAULT_BOXNOW_STATUS
    price: str | float | int = 0
    gallery_url: str | None = None
    characteristics_url: str | None = None
    second_opencart_image_index: int | None = Field(default=None, ge=1)
    gallery_mode: Literal["all"] | None = None

    @field_validator("bestprice_status", "skroutz_status", "boxnow", mode="before")
    @classmethod
    def _normalize_status_fields(cls, value: object, info: object) -> object:
        field_name = getattr(info, "field_name", "status")
        default = {
            "bestprice_status": DEFAULT_BESTPRICE_STATUS,
            "skroutz_status": DEFAULT_SKR_OUTZ_STATUS,
            "boxnow": DEFAULT_BOXNOW_STATUS,
        }[field_name]
        return status_or_default(value, default=default, field_name=field_name)

    @field_validator("gallery_url", "characteristics_url", mode="before")
    @classmethod
    def _normalize_optional_url(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed or None
        return value

    @field_validator("gallery_url", "characteristics_url")
    @classmethod
    def _optional_url_must_be_absolute(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = urlsplit(value)
        if not parts.scheme or not parts.netloc:
            raise ValueError("URL override must be an absolute URL")
        return value


class RenderJobRequest(BaseModel):
    model: str


class PublishJobRequest(BaseModel):
    model: str
    current_job_product_file: str | None = None


class AuthoringIntroJobRequest(BaseModel):
    model: str
    retry: bool = False

    @field_validator("model")
    @classmethod
    def _model_not_empty(cls, value: str) -> str:
        value = str(value or "").strip()
        if not value:
            raise ValueError("model must not be empty")
        return value


class AuthoringSeoJobRequest(BaseModel):
    model: str
    retry: bool = False

    @field_validator("model")
    @classmethod
    def _model_not_empty(cls, value: str) -> str:
        value = str(value or "").strip()
        if not value:
            raise ValueError("model must not be empty")
        return value


class FullPipelineJobRequest(BaseModel):
    model: str
    product_name: str | None = None
    source_url: str
    bestprice_status: int = DEFAULT_BESTPRICE_STATUS
    skroutz_status: int = DEFAULT_SKR_OUTZ_STATUS
    boxnow: int = DEFAULT_BOXNOW_STATUS
    price: str | float | int = 0
    photos: int = Field(default=DEFAULT_FULL_PIPELINE_PHOTOS, ge=0)
    sections: int = Field(default=DEFAULT_FULL_PIPELINE_SECTIONS, ge=0)
    gallery_url: str | None = None
    characteristics_url: str | None = None
    second_opencart_image_index: int | None = Field(default=None, ge=1)
    gallery_mode: Literal["all"] | None = DEFAULT_FULL_PIPELINE_GALLERY_MODE
    skip_publish: bool = False
    trigger_source: str | None = None
    telegram_chat_id: str | None = None
    source_resolution: dict[str, Any] | None = None

    @field_validator("model")
    @classmethod
    def _model_not_empty(cls, value: str) -> str:
        value = str(value or "").strip()
        if not value:
            raise ValueError("model must not be empty")
        return value

    @field_validator(
        "product_name", "trigger_source", "telegram_chat_id", mode="before"
    )
    @classmethod
    def _normalize_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed or None
        return value

    @field_validator("source_url", mode="before")
    @classmethod
    def _normalize_source_url(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("gallery_url", "characteristics_url", mode="before")
    @classmethod
    def _normalize_optional_url(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed or None
        return value

    @field_validator("gallery_url", "characteristics_url")
    @classmethod
    def _optional_url_must_be_absolute(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("URL override must be an absolute HTTP(S) URL")
        return value

    @field_validator("source_url")
    @classmethod
    def _source_url_must_be_supported(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        try:
            _source, scope_ok, _reason = validate_url_scope(value)
        except ValueError as exc:
            raise ValueError(
                "source_url must be a supported Product Factory source URL"
            ) from exc
        if not scope_ok:
            raise ValueError(
                "source_url must be a supported Product Factory source URL"
            )
        return value

    @field_validator("bestprice_status", "skroutz_status", "boxnow", mode="before")
    @classmethod
    def _normalize_full_pipeline_status_fields(
        cls, value: object, info: object
    ) -> object:
        field_name = getattr(info, "field_name", "status")
        default = {
            "bestprice_status": DEFAULT_BESTPRICE_STATUS,
            "skroutz_status": DEFAULT_SKR_OUTZ_STATUS,
            "boxnow": DEFAULT_BOXNOW_STATUS,
        }[field_name]
        return status_or_default(value, default=default, field_name=field_name)


class StopJobRequest(BaseModel):
    reason: str | None = None


class JobResponse(BaseModel):
    job_id: str
    job_type: JobType
    status: JobStatus
    model: str
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    message: str | None = None
    error: str | None = None
    error_code: str | None = None

    @classmethod
    def from_record(cls, record: JobRecord) -> JobResponse:
        return cls(
            job_id=record.job_id,
            job_type=record.job_type,
            status=record.status,
            model=record.model,
            created_at=record.created_at,
            updated_at=record.updated_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            message=record.message,
            error=record.error,
            error_code=record.error_code,
        )


class JobListResponse(BaseModel):
    jobs: list[JobResponse] = Field(default_factory=list)


class JobLogsResponse(BaseModel):
    job_id: str
    lines: list[str] = Field(default_factory=list)


class JobArtifact(BaseModel):
    name: str
    path: str
    kind: str | None = None
    content_type: str | None = None
    content: str | None = None


class JobArtifactsResponse(BaseModel):
    job_id: str
    artifacts: list[JobArtifact] = Field(default_factory=list)

    @classmethod
    def from_artifacts(
        cls, job_id: str, artifacts: list[ResolvedArtifact]
    ) -> JobArtifactsResponse:
        return cls(
            job_id=job_id,
            artifacts=[
                JobArtifact(
                    name=artifact.name,
                    path=artifact.path,
                    kind=artifact.kind,
                    content_type=artifact.content_type,
                    content=artifact.content,
                )
                for artifact in artifacts
            ],
        )


class ErrorResponse(BaseModel):
    detail: str


class SettingsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int
    authoring: dict[str, Any]


class SettingsPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authoring: dict[str, Any] = Field(default_factory=dict)


class AuthoringTaskStatus(BaseModel):
    status: str
    output_path: str
    trace_path: str | None = None
    word_count: int | None = None
    min_words: int | None = None
    max_words: int | None = None
    max_attempts: int | None = None
    errors: list[str] = Field(default_factory=list)
    emphasis_warning_codes: list[str] = Field(default_factory=list)
    lint_trace_path: str | None = None
    lint_warning_codes: list[str] = Field(default_factory=list)
    lint_warnings: list[dict[str, str]] = Field(default_factory=list)
    strong_span_count: int | None = None
    emphasized_word_count: int | None = None
    visible_word_count: int | None = None
    emphasized_word_ratio: float | None = None
    updated_at: str | None = None


class AuthoringStatusResponse(BaseModel):
    model: str
    llm_dir: str
    intro_text: AuthoringTaskStatus
    seo_meta: AuthoringTaskStatus
    ready_for_render: bool
    render_block_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FilterReviewValue(BaseModel):
    value_id: str
    value: str
    status: str


class FilterReviewGroup(BaseModel):
    group_id: str
    group_name: str
    required: bool
    status: str
    allowed_values: list[FilterReviewValue] = Field(default_factory=list)
    resolved_value: str = ""
    reviewed_value: str = ""
    effective_value: str = ""
    effective_value_id: str | None = None
    value_status: str | None = None
    source: str = ""
    missing_required: bool = False
    outside_allowed: bool = False
    deprecated_value: bool = False
    inactive_group: bool = False
    emitted_if_rendered: bool = False


class FilterReviewResponse(BaseModel):
    model: str
    category_id: str
    taxonomy_path: str
    filter_category_found: bool
    approved: bool
    approved_at: str | None = None
    render_blocked: bool
    render_block_reasons: list[str] = Field(default_factory=list)
    missing_required_groups: list[FilterReviewGroup] = Field(default_factory=list)
    groups: list[FilterReviewGroup] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    review_artifact_path: str


class FilterReviewValueUpdate(BaseModel):
    group_id: str | None = None
    group_name: str
    value: str
    value_id: str | None = None
    add_to_global: bool = True

    @field_validator("group_name", "value")
    @classmethod
    def _not_empty(cls, value: str) -> str:
        if not str(value or "").strip():
            raise ValueError("must not be empty")
        return str(value).strip()


class FilterReviewNewGroup(BaseModel):
    group_name: str
    value: str
    required: bool = True
    status: str = "active"
    value_status: str = "active"

    @field_validator("group_name", "value")
    @classmethod
    def _not_empty(cls, value: str) -> str:
        if not str(value or "").strip():
            raise ValueError("must not be empty")
        return str(value).strip()

    @field_validator("status", "value_status")
    @classmethod
    def _valid_status(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if normalized not in {"active", "inactive", "deprecated"}:
            raise ValueError("status must be one of active/inactive/deprecated")
        return normalized


class FilterReviewGroupUpdate(BaseModel):
    group_id: str | None = None
    group_name: str
    required: StrictBool | None = None
    status: str | None = None

    @field_validator("group_name")
    @classmethod
    def _not_empty(cls, value: str) -> str:
        if not str(value or "").strip():
            raise ValueError("must not be empty")
        return str(value).strip()

    @field_validator("status")
    @classmethod
    def _valid_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value or "").strip()
        if normalized not in {"active", "inactive", "deprecated"}:
            raise ValueError("status must be one of active/inactive/deprecated")
        return normalized


class FilterReviewUpdateRequest(BaseModel):
    values: list[FilterReviewValueUpdate] = Field(default_factory=list)
    group_updates: list[FilterReviewGroupUpdate] = Field(default_factory=list)
    new_groups: list[FilterReviewNewGroup] = Field(default_factory=list)
    add_new_values_globally: bool = True


FilterSource = Literal["base", "manual", "merged"]
FilterStatus = Literal["active", "inactive", "deprecated"]


class FilterValueResponse(BaseModel):
    value_id: str
    value: str
    status: FilterStatus
    source: FilterSource


class FilterGroupResponse(BaseModel):
    group_id: str
    name: str
    required: bool
    status: FilterStatus
    source: FilterSource
    values: list[FilterValueResponse] = Field(default_factory=list)


class FilterCategoryListItem(BaseModel):
    category_id: str
    path: str
    parent_category: str
    leaf_category: str
    sub_category: str
    key: str
    group_count: int
    active_group_count: int
    required_group_count: int
    inactive_group_count: int
    deprecated_group_count: int
    source: FilterSource


class FilterCategoriesResponse(BaseModel):
    categories: list[FilterCategoryListItem] = Field(default_factory=list)


class FilterCategoryResponse(BaseModel):
    category_id: str
    path: str
    parent_category: str
    leaf_category: str
    sub_category: str
    revision: str | None = None
    groups: list[FilterGroupResponse] = Field(default_factory=list)


class FilterStatusResponse(BaseModel):
    filter_map_base_path: str
    filter_map_manual_overrides_path: str
    filter_map_path: str
    sync_report_path: str
    valid_statuses: list[str] = Field(default_factory=list)
    revision: str | None = None


class FilterBackupItem(BaseModel):
    backup_name: str
    created_at: str
    revision: str
    size_bytes: int


class FilterBackupsResponse(BaseModel):
    items: list[FilterBackupItem] = Field(default_factory=list)


class RestoreFilterBackupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backup_name: str | None = None


class FilterBackupRestoreResponse(BaseModel):
    status: str
    restored_backup_name: str
    revision: str
    filter_map_path: str
    manual_overrides_path: str
    sync_report_path: str


class AddFilterGroupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    required: StrictBool = True
    status: FilterStatus = "active"
    expected_revision: str | None = None

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, value: str) -> str:
        value = str(value or "").strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


class UpdateFilterGroupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    required: StrictBool | None = None
    status: FilterStatus | None = None
    expected_revision: str | None = None

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value or "").strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


class AddFilterValueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    status: FilterStatus = "active"
    expected_revision: str | None = None

    @field_validator("value")
    @classmethod
    def _value_not_empty(cls, value: str) -> str:
        value = str(value or "").strip()
        if not value:
            raise ValueError("value must not be empty")
        return value


class UpdateFilterValueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | None = None
    status: FilterStatus | None = None
    expected_revision: str | None = None

    @field_validator("value")
    @classmethod
    def _value_not_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value or "").strip()
        if not value:
            raise ValueError("value must not be empty")
        return value


class FilterSyncResponse(BaseModel):
    status: str
    filter_map_path: str
    sync_report_path: str
    revision: str | None = None
    category_count: int
    group_count: int
    value_count: int
    warning_count: int
    overridden_group_count: int
    overridden_value_count: int


class FilterSyncReportResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    mode: str = ""
    warnings: list[Any] = Field(default_factory=list)
    overridden_groups: list[Any] = Field(default_factory=list)
    overridden_values: list[Any] = Field(default_factory=list)
