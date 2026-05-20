from __future__ import annotations

from pathlib import Path

from ..repo_paths import category_filter_review_path
from .errors import ServiceError, ServiceErrorCode, service_error_from_exception
from .metadata import MetadataWriteError
from .render_execution import execute_render_workflow
from .models import RenderRequest, RunArtifacts, RunMetadata, RunType, ServiceResult


def _existing_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    return path if path.exists() else None


def _missing_artifact_message(
    operation: str, missing_artifacts: dict[str, Path]
) -> str:
    joined = ", ".join(f"{name}={path}" for name, path in missing_artifacts.items())
    return f"{operation.capitalize()} completed but required artifacts are missing: {joined}"


def _service_error_from_render_metadata_failure(
    error: MetadataWriteError,
) -> ServiceError:
    payload = error.payload
    code = payload.run.error_code or ServiceErrorCode.UNEXPECTED_FAILURE.value
    message = payload.run.error_detail or str(error)
    return ServiceError(
        code,
        message,
        cause=error,
        details={
            "metadata_path": str(error.metadata_path),
            "metadata_run_type": payload.run.run_type.value,
            "metadata_run_status": payload.run.status.value,
            "metadata_write_failure": str(error),
        },
    )


def _build_render_service_result(
    request: RenderRequest,
    *,
    run_status,
    warnings: list[str],
    error_code: str | None,
    error_detail: str | None,
    artifacts: RunArtifacts,
    details: dict[str, str | int | float | bool | None],
) -> ServiceResult:
    return ServiceResult(
        run=RunMetadata(
            model=request.model,
            run_type=RunType.RENDER,
            status=run_status,
            warnings=warnings,
            error_code=error_code,
            error_detail=error_detail,
        ),
        artifacts=artifacts,
        details=details,
    )


def _degraded_render_result_from_metadata_error(
    request: RenderRequest,
    error: MetadataWriteError,
) -> ServiceResult:
    payload = error.payload
    warnings = list(payload.run.warnings)
    warnings.append(str(error))
    return _build_render_service_result(
        request,
        run_status=payload.run.status,
        warnings=warnings,
        error_code=payload.run.error_code or ServiceErrorCode.UNEXPECTED_FAILURE.value,
        error_detail=payload.run.error_detail or str(error),
        artifacts=RunArtifacts(
            model_root=_existing_path(payload.artifacts.model_root),
            scrape_dir=_existing_path(payload.artifacts.scrape_dir),
            candidate_dir=_existing_path(payload.artifacts.candidate_dir),
            llm_dir=_existing_path(payload.artifacts.llm_dir),
            source_json_path=_existing_path(payload.artifacts.source_json_path),
            scrape_normalized_json_path=_existing_path(
                payload.artifacts.scrape_normalized_json_path
            ),
            llm_task_manifest_path=_existing_path(
                payload.artifacts.llm_task_manifest_path
            ),
            intro_text_output_path=_existing_path(
                payload.artifacts.intro_text_output_path
            ),
            seo_meta_output_path=_existing_path(payload.artifacts.seo_meta_output_path),
            candidate_csv_path=_existing_path(payload.artifacts.candidate_csv_path),
            published_csv_path=_existing_path(payload.artifacts.published_csv_path),
            candidate_normalized_json_path=_existing_path(
                payload.artifacts.candidate_normalized_json_path
            ),
            validation_report_path=_existing_path(
                payload.artifacts.validation_report_path
            ),
            description_html_path=_existing_path(
                payload.artifacts.description_html_path
            ),
            characteristics_html_path=_existing_path(
                payload.artifacts.characteristics_html_path
            ),
            category_filter_review_path=_existing_path(
                payload.artifacts.category_filter_review_path
            ),
            metadata_path=None,
        ),
        details={
            "validation_ok": bool(payload.details.get("validation_ok", False)),
            "published": bool(payload.details.get("published", False)),
        },
    )


def render_product(request: RenderRequest) -> ServiceResult:
    try:
        result = execute_render_workflow(request.model)
    except MetadataWriteError as exc:
        if (
            exc.payload.run.status.value == "completed"
            or exc.payload.run.error_code == ServiceErrorCode.VALIDATION_FAILURE.value
        ):
            return _degraded_render_result_from_metadata_error(request, exc)
        raise _service_error_from_render_metadata_failure(exc) from exc
    except Exception as exc:
        raise service_error_from_exception(exc, operation="render") from exc

    candidate_dir = result.candidate_dir
    model_root = result.model_root
    scrape_dir = result.scrape_dir
    validation_report = result.validation_report
    validation_ok = validation_report.ok
    run_warnings = list(validation_report.warnings)
    error_code = None if validation_ok else ServiceErrorCode.VALIDATION_FAILURE.value
    error_detail = None if validation_ok else "Candidate validation failed"
    source_json_path = scrape_dir / f"{request.model}.source.json"
    scrape_normalized_json_path = scrape_dir / f"{request.model}.normalized.json"
    llm_task_manifest_path = result.llm_dir / "task_manifest.json"
    intro_text_output_path = result.llm_dir / "intro_text.output.txt"
    seo_meta_output_path = result.llm_dir / "seo_meta.output.json"
    candidate_normalized_json_path = candidate_dir / f"{request.model}.normalized.json"
    review_path = category_filter_review_path(
        request.model, repo_root=model_root.parent.parent
    )
    required_artifacts = {
        "candidate_dir": candidate_dir,
        "candidate_csv_path": result.candidate_csv_path,
        "validation_report_path": result.validation_report_path,
        "description_html_path": result.description_path,
        "characteristics_html_path": result.characteristics_path,
    }
    if validation_ok and result.published_csv_path is not None:
        required_artifacts["published_csv_path"] = result.published_csv_path
    missing_required_artifacts = {
        name: path for name, path in required_artifacts.items() if not path.exists()
    }
    if missing_required_artifacts:
        raise ServiceError(
            ServiceErrorCode.MISSING_ARTIFACT.value,
            _missing_artifact_message("render", missing_required_artifacts),
            details={
                "missing_artifacts": {
                    name: str(path) for name, path in missing_required_artifacts.items()
                }
            },
        )

    metadata_path = _existing_path(result.metadata_path)
    if metadata_path is None:
        metadata_warning = (
            f"Render metadata artifact is missing: {result.metadata_path}"
        )
        run_warnings.append(metadata_warning)
        if error_code is None:
            error_code = ServiceErrorCode.MISSING_ARTIFACT.value
            error_detail = metadata_warning

    return _build_render_service_result(
        request,
        run_status=result.run_status,
        warnings=run_warnings,
        error_code=error_code,
        error_detail=error_detail,
        artifacts=RunArtifacts(
            model_root=_existing_path(model_root),
            scrape_dir=_existing_path(scrape_dir),
            candidate_dir=_existing_path(candidate_dir),
            llm_dir=_existing_path(result.llm_dir),
            source_json_path=_existing_path(source_json_path),
            scrape_normalized_json_path=_existing_path(scrape_normalized_json_path),
            llm_task_manifest_path=_existing_path(llm_task_manifest_path),
            intro_text_output_path=_existing_path(intro_text_output_path),
            seo_meta_output_path=_existing_path(seo_meta_output_path),
            candidate_csv_path=_existing_path(result.candidate_csv_path),
            published_csv_path=_existing_path(result.published_csv_path),
            candidate_normalized_json_path=_existing_path(
                candidate_normalized_json_path
            ),
            validation_report_path=_existing_path(result.validation_report_path),
            description_html_path=_existing_path(result.description_path),
            characteristics_html_path=_existing_path(result.characteristics_path),
            category_filter_review_path=_existing_path(review_path),
            metadata_path=metadata_path,
        ),
        details={
            "validation_ok": validation_ok,
            "published": _existing_path(result.published_csv_path) is not None,
        },
    )
