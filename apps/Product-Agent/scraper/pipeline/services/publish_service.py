from __future__ import annotations

from pathlib import Path

from ..repo_paths import REPO_ROOT
from .errors import ServiceErrorCode
from .models import PublishRequest, RunArtifacts, RunMetadata, RunStatus, RunType, ServiceResult
from .publish_execution import OPENCART_IMPORT_REPORT_NAME, OPENCART_UPLOAD_REPORT_NAME, execute_publish_workflow


def _report_paths(model: str, *, repo_root: Path = REPO_ROOT) -> tuple[str, str]:
    model_root = repo_root / "work" / model
    return (
        str(model_root / OPENCART_UPLOAD_REPORT_NAME),
        str(model_root / OPENCART_IMPORT_REPORT_NAME),
    )


def build_publish_phase_details(
    model: str,
    publish_result: ServiceResult | None = None,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, str | int | float | bool | None]:
    upload_report_path, import_report_path = _report_paths(model, repo_root=repo_root)
    if publish_result is None:
        return {
            "publish_attempted": False,
            "publish_status": "not_attempted",
            "publish_stage": "-",
            "publish_message": f"Publish skipped because render did not publish products/{model}.csv.",
            "upload_report_path": upload_report_path,
            "import_report_path": import_report_path,
            "publish_metadata_path": None,
        }
    return {
        "publish_attempted": bool(publish_result.details.get("publish_attempted", True)),
        "publish_status": str(publish_result.details.get("publish_status", "failed")),
        "publish_stage": str(publish_result.details.get("publish_stage", "unknown")),
        "publish_message": (
            str(publish_result.details.get("publish_message"))
            if publish_result.details.get("publish_message") is not None
            else None
        ),
        "upload_report_path": str(publish_result.details.get("upload_report_path") or upload_report_path),
        "import_report_path": str(publish_result.details.get("import_report_path") or import_report_path),
        "publish_metadata_path": str(publish_result.artifacts.metadata_path) if publish_result.artifacts.metadata_path else None,
    }


def publish_product(request: PublishRequest) -> ServiceResult:
    result = execute_publish_workflow(
        request.model,
        current_job_product_file=request.current_job_product_file,
    )
    publish_status = str(result.get("publish_status", "failed"))
    publish_message = str(result["publish_message"]) if result.get("publish_message") else None
    warnings: list[str] = []
    if publish_status in {"warning", "failed"} and publish_message:
        warnings.append(publish_message)
    return ServiceResult(
        run=RunMetadata(
            model=request.model,
            run_type=RunType.PUBLISH,
            status=RunStatus(result["run_status"]),
            warnings=warnings,
            error_code=ServiceErrorCode.PUBLISH_FAILURE.value if publish_status == "failed" else None,
            error_detail=publish_message if publish_status == "failed" else None,
        ),
        artifacts=RunArtifacts(
            model_root=Path(result["metadata_path"]).parent if result.get("metadata_path") else None,
            published_csv_path=Path(result["published_csv_path"]) if result.get("published_csv_path") else None,
            metadata_path=Path(result["metadata_path"]) if result.get("metadata_path") else None,
        ),
        details={
            "publish_attempted": bool(result.get("publish_attempted", True)),
            "publish_status": publish_status,
            "publish_stage": str(result.get("publish_stage", "unknown")),
            "publish_message": publish_message,
            "upload_report_path": str(result["upload_report_path"]) if result.get("upload_report_path") else None,
            "import_report_path": str(result["import_report_path"]) if result.get("import_report_path") else None,
        },
    )
