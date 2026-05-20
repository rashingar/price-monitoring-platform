from __future__ import annotations

from pydantic import BaseModel

from product_factory.api.schemas import (
    AuthoringStatusResponse,
    FilterCategoriesResponse,
    FilterCategoryResponse,
    FilterGroupResponse,
    FilterReviewResponse,
    FilterSyncResponse,
    JobArtifactsResponse,
    JobListResponse,
    JobLogsResponse,
    JobResponse,
    SettingsResponse,
)


def _properties(model: type[BaseModel]) -> set[str]:
    return set(model.model_json_schema()["properties"])


def test_job_response_public_fields_are_stable() -> None:
    assert {
        "job_id",
        "job_type",
        "status",
        "model",
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
        "message",
        "error",
        "error_code",
    }.issubset(_properties(JobResponse))


def test_job_collection_logs_and_artifacts_public_fields_are_stable() -> None:
    assert {"jobs"}.issubset(_properties(JobListResponse))
    assert {"job_id", "lines"}.issubset(_properties(JobLogsResponse))
    assert {"job_id", "artifacts"}.issubset(_properties(JobArtifactsResponse))


def test_filter_public_fields_are_stable() -> None:
    assert {"categories"}.issubset(_properties(FilterCategoriesResponse))
    assert {"category_id", "path", "groups"}.issubset(
        _properties(FilterCategoryResponse)
    )
    assert {"group_id", "name", "required", "status", "source", "values"}.issubset(
        _properties(FilterGroupResponse)
    )
    assert {
        "status",
        "filter_map_path",
        "sync_report_path",
        "category_count",
        "group_count",
        "value_count",
        "warning_count",
        "overridden_group_count",
        "overridden_value_count",
    }.issubset(_properties(FilterSyncResponse))


def test_filter_review_public_fields_are_stable() -> None:
    assert {
        "model",
        "category_id",
        "groups",
        "approved",
        "render_blocked",
        "review_artifact_path",
    }.issubset(_properties(FilterReviewResponse))


def test_authoring_and_settings_public_fields_are_stable() -> None:
    assert {
        "model",
        "llm_dir",
        "intro_text",
        "seo_meta",
        "ready_for_render",
    }.issubset(_properties(AuthoringStatusResponse))
    assert {"schema_version", "authoring"}.issubset(_properties(SettingsResponse))
