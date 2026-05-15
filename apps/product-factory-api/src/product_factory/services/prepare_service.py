from __future__ import annotations

from pathlib import Path

from ..models import CLIInput
from .errors import ServiceError, ServiceErrorCode, service_error_from_exception
from .metadata import MetadataWriteError
from .prepare_execution import WORK_ROOT, execute_prepare_workflow
from .models import PrepareRequest, RunArtifacts, RunMetadata, RunStatus, RunType, ServiceResult


def _existing_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    return path if path.exists() else None


def _missing_artifact_message(operation: str, missing_artifacts: dict[str, Path]) -> str:
    joined = ", ".join(f"{name}={path}" for name, path in missing_artifacts.items())
    return f"{operation.capitalize()} completed but required artifacts are missing: {joined}"


def _service_error_from_prepare_metadata_failure(error: MetadataWriteError) -> ServiceError:
    payload = error.payload
    return ServiceError(
        payload.run.error_code or ServiceErrorCode.UNEXPECTED_FAILURE.value,
        payload.run.error_detail or str(error),
        cause=error,
        details={
            "metadata_path": str(error.metadata_path),
            "metadata_run_type": payload.run.run_type.value,
            "metadata_run_status": payload.run.status.value,
            "metadata_write_failure": str(error),
        },
    )


def _build_prepare_service_result(
    *,
    request: PrepareRequest,
    run_status: RunStatus,
    warnings: list[str],
    error_code: str | None,
    error_detail: str | None,
    artifacts: RunArtifacts,
    details: dict[str, str | int | float | bool | None],
) -> ServiceResult:
    return ServiceResult(
        run=RunMetadata(
            model=request.model,
            run_type=RunType.PREPARE,
            status=run_status,
            warnings=warnings,
            error_code=error_code,
            error_detail=error_detail,
        ),
        artifacts=artifacts,
        details=details,
    )


def _degraded_prepare_result_from_metadata_error(
    request: PrepareRequest,
    error: MetadataWriteError,
) -> ServiceResult:
    payload = error.payload
    warnings = list(payload.run.warnings)
    warnings.append(str(error))
    return _build_prepare_service_result(
        request=request,
        run_status=payload.run.status,
        warnings=warnings,
        error_code=ServiceErrorCode.UNEXPECTED_FAILURE.value if payload.run.status == RunStatus.COMPLETED else payload.run.error_code,
        error_detail=str(error) if payload.run.status == RunStatus.COMPLETED else payload.run.error_detail,
        artifacts=RunArtifacts(
            model_root=_existing_path(payload.artifacts.model_root),
            scrape_dir=_existing_path(payload.artifacts.scrape_dir),
            llm_dir=_existing_path(payload.artifacts.llm_dir),
            raw_html_path=_existing_path(payload.artifacts.raw_html_path),
            source_json_path=_existing_path(payload.artifacts.source_json_path),
            scrape_normalized_json_path=_existing_path(payload.artifacts.scrape_normalized_json_path),
            source_report_json_path=_existing_path(payload.artifacts.source_report_json_path),
            llm_task_manifest_path=_existing_path(payload.artifacts.llm_task_manifest_path),
            intro_text_context_path=_existing_path(payload.artifacts.intro_text_context_path),
            intro_text_prompt_path=_existing_path(payload.artifacts.intro_text_prompt_path),
            intro_text_output_path=payload.artifacts.intro_text_output_path,
            seo_meta_context_path=_existing_path(payload.artifacts.seo_meta_context_path),
            seo_meta_prompt_path=_existing_path(payload.artifacts.seo_meta_prompt_path),
            seo_meta_output_path=payload.artifacts.seo_meta_output_path,
            metadata_path=None,
        ),
        details={
            "source": str(payload.details.get("source", "") or ""),
            "product_name": str(payload.details.get("product_name", "") or ""),
            "product_code": str(payload.details.get("product_code", "") or ""),
            "brand": str(payload.details.get("brand", "") or ""),
            "taxonomy_path": str(payload.details.get("taxonomy_path", "") or ""),
            "matched_schema_id": str(payload.details.get("matched_schema_id", "") or ""),
            "schema_score": float(payload.details.get("schema_score", 0.0) or 0.0),
            "warnings_count": int(payload.details.get("warnings_count", len(payload.run.warnings)) or 0),
            "llm_prepare_mode": str(payload.details.get("llm_prepare_mode", "split_tasks") or "split_tasks"),
        },
    )


def prepare_product(request: PrepareRequest) -> ServiceResult:
    cli = CLIInput(
        model=request.model,
        url=request.url,
        photos=request.photos,
        sections=request.sections,
        skroutz_status=request.skroutz_status,
        boxnow=request.boxnow,
        price=request.price,
        gallery_url=request.gallery_url,
        characteristics_url=request.characteristics_url,
        second_opencart_image_index=request.second_opencart_image_index,
        out=str(WORK_ROOT / request.model / "scrape"),
    )
    try:
        result = execute_prepare_workflow(cli, work_root=WORK_ROOT)
    except MetadataWriteError as exc:
        if exc.payload.run.status == RunStatus.COMPLETED:
            return _degraded_prepare_result_from_metadata_error(request, exc)
        raise _service_error_from_prepare_metadata_failure(exc) from exc
    except Exception as exc:
        raise service_error_from_exception(exc, operation="prepare") from exc

    scrape_result = result.scrape_result
    parsed = scrape_result.parsed
    taxonomy = scrape_result.taxonomy
    schema_match = scrape_result.schema_match
    model_root = result.model_root
    scrape_dir = result.scrape_dir
    warnings = list(scrape_result.report_warnings)
    raw_html_path = scrape_dir / f"{request.model}.raw.html"
    source_json_path = scrape_dir / f"{request.model}.source.json"
    scrape_normalized_json_path = scrape_dir / f"{request.model}.normalized.json"
    source_report_json_path = scrape_dir / f"{request.model}.report.json"
    required_artifacts = {
        "scrape_dir": scrape_dir,
        "llm_dir": result.llm_dir,
        "source_json_path": source_json_path,
        "scrape_normalized_json_path": scrape_normalized_json_path,
        "source_report_json_path": source_report_json_path,
        "llm_task_manifest_path": result.task_manifest_path,
        "intro_text_context_path": result.intro_text_context_path,
        "intro_text_prompt_path": result.intro_text_prompt_path,
        "seo_meta_context_path": result.seo_meta_context_path,
        "seo_meta_prompt_path": result.seo_meta_prompt_path,
    }
    missing_required_artifacts = {
        name: path
        for name, path in required_artifacts.items()
        if not path.exists()
    }
    if missing_required_artifacts:
        raise ServiceError(
            ServiceErrorCode.MISSING_ARTIFACT.value,
            _missing_artifact_message("prepare", missing_required_artifacts),
            details={"missing_artifacts": {name: str(path) for name, path in missing_required_artifacts.items()}},
        )

    metadata_path = _existing_path(result.metadata_path)
    error_code = None
    error_detail = None
    if metadata_path is None:
        error_detail = f"Prepare metadata artifact is missing: {result.metadata_path}"
        warnings.append(error_detail)
        error_code = ServiceErrorCode.MISSING_ARTIFACT.value

    report_payload = scrape_result.payload.get("report", {})
    report = report_payload if isinstance(report_payload, dict) else {}
    gallery_settings_payload = report.get("gallery_settings", {})
    gallery_settings = gallery_settings_payload if isinstance(gallery_settings_payload, dict) else {}
    characteristics_settings_payload = report.get("characteristics_settings", {})
    characteristics_settings = characteristics_settings_payload if isinstance(characteristics_settings_payload, dict) else {}
    details = {
        "source": scrape_result.source,
        "product_name": str(getattr(getattr(parsed, "source", None), "name", "") or ""),
        "product_code": str(getattr(getattr(parsed, "source", None), "product_code", "") or ""),
        "brand": str(getattr(getattr(parsed, "source", None), "brand", "") or ""),
        "taxonomy_path": str(getattr(taxonomy, "taxonomy_path", "") or ""),
        "matched_schema_id": str(getattr(schema_match, "matched_schema_id", "") or ""),
        "schema_score": float(getattr(schema_match, "score", 0.0) or 0.0),
        "warnings_count": len(scrape_result.report_warnings),
        "llm_prepare_mode": "blocked_snapshot"
        if str(getattr(getattr(parsed, "source", None), "page_type", "") or "") == "blocked_by_challenge"
        else "split_tasks",
    }
    if gallery_settings:
        details.update(
            {
                "gallery_url_used": bool(gallery_settings.get("gallery_url_used", False)),
                "gallery_extraction_url": str(gallery_settings.get("gallery_extraction_url", "") or ""),
                "second_opencart_image_index": gallery_settings.get("second_opencart_image_index"),
                "second_opencart_image_override_applied": bool(
                    gallery_settings.get("second_opencart_image_override_applied", False)
                ),
            }
        )
    if characteristics_settings:
        details.update(
            {
                "characteristics_url_used": bool(characteristics_settings.get("characteristics_url_used", False)),
                "characteristics_extraction_url": str(
                    characteristics_settings.get("characteristics_extraction_url", "") or ""
                ),
            }
        )
    if details["llm_prepare_mode"] == "blocked_snapshot":
        details["blocked_reason"] = "blocked_by_challenge"

    return _build_prepare_service_result(
        request=request,
        run_status=result.run_status,
        warnings=warnings,
        error_code=error_code,
        error_detail=error_detail,
        artifacts=RunArtifacts(
            model_root=_existing_path(model_root),
            scrape_dir=_existing_path(scrape_dir),
            llm_dir=_existing_path(result.llm_dir),
            raw_html_path=_existing_path(raw_html_path),
            source_json_path=_existing_path(source_json_path),
            scrape_normalized_json_path=_existing_path(scrape_normalized_json_path),
            source_report_json_path=_existing_path(source_report_json_path),
            llm_task_manifest_path=_existing_path(result.task_manifest_path),
            intro_text_context_path=_existing_path(result.intro_text_context_path),
            intro_text_prompt_path=_existing_path(result.intro_text_prompt_path),
            intro_text_output_path=result.intro_text_output_path,
            seo_meta_context_path=_existing_path(result.seo_meta_context_path),
            seo_meta_prompt_path=_existing_path(result.seo_meta_prompt_path),
            seo_meta_output_path=result.seo_meta_output_path,
            metadata_path=metadata_path,
        ),
        details=details,
    )
