from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..repo_paths import REPO_ROOT
from ..utils import utcnow_iso
from .metadata import maybe_write_run_metadata
from .models import RunArtifacts, RunStatus, RunType

WORK_ROOT = REPO_ROOT / "work"
PRODUCTS_ROOT = REPO_ROOT / "products"
OPENCART_PUBLISH_ENTRYPOINT = Path("tools") / "run_opencart_pipeline.sh"
OPENCART_UPLOAD_REPORT_NAME = "upload.opencart.json"
OPENCART_IMPORT_REPORT_NAME = "import.opencart.json"
PUBLISH_STAGE_EXIT_CODES = {
    11: "preflight",
    12: "image_upload",
    13: "csv_import",
}
WSL_LAUNCH_MARKERS = (
    "Bash/Service/CreateInstance",
    "Wsl/Service/CreateInstance",
    "CreateInstance/0xd0000022",
)


def _report_paths(repo_root: Path, model: str) -> tuple[Path, Path]:
    model_root = repo_root / "work" / model
    return (
        model_root / OPENCART_UPLOAD_REPORT_NAME,
        model_root / OPENCART_IMPORT_REPORT_NAME,
    )


def _summarize_command_output(stdout: str, stderr: str) -> str:
    lines = [line.strip() for line in [*stdout.splitlines(), *stderr.splitlines()] if line.strip()]
    if not lines:
        return ""
    return " | ".join(lines[-3:])


def _classify_bash_probe_failure(stdout: str, stderr: str) -> str | None:
    summary = _summarize_command_output(stdout, stderr)
    if not summary:
        return None
    if any(marker in summary for marker in WSL_LAUNCH_MARKERS):
        return "bash_or_wsl_startup_failure"
    lowered = summary.lower()
    if "access is denied" in lowered:
        return "bash_access_denied"
    if "cannot find" in lowered or "not recognized" in lowered:
        return "bash_not_available"
    return None


def _shell_path_from_repo(path: Path, *, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return str(path)


def _preflight_publish_environment(
    *,
    model: str,
    script_path: Path,
    published_csv_path: Path,
    work_root: Path,
    repo_root: Path,
) -> tuple[str | None, str | None, str | None]:
    if not script_path.exists():
        return "preflight", f"OpenCart publish failed during preflight: shell entrypoint not found at {script_path}", None
    if not published_csv_path.exists():
        return "preflight", f"OpenCart publish failed during preflight: missing published CSV: {published_csv_path}", None

    main_image_path = work_root / model / "scrape" / "gallery" / f"{model}-1.jpg"
    if not main_image_path.exists():
        return "preflight", f"OpenCart publish failed during preflight: missing gallery image: {main_image_path}", None

    bash_path = shutil.which("bash")
    if not bash_path:
        return "preflight", "OpenCart publish failed during preflight: bash executable not found on PATH", None

    try:
        completed = subprocess.run(
            [bash_path, "--version"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return "preflight", f"OpenCart publish failed during preflight: {exc}", None

    if completed.returncode == 0:
        return None, None, bash_path

    summary = _summarize_command_output(completed.stdout, completed.stderr)
    failure_class = _classify_bash_probe_failure(completed.stdout, completed.stderr)
    message = "OpenCart publish failed during preflight: bash launcher probe failed"
    if failure_class:
        message = f"{message} ({failure_class})"
    message = f"{message}: exit={completed.returncode}"
    if summary:
        message = f"{message}: {summary}"
    return "preflight", message, bash_path


def execute_publish_workflow(
    model: str,
    *,
    current_job_product_file: Path | None = None,
    repo_root: Path = REPO_ROOT,
    work_root: Path = WORK_ROOT,
    products_root: Path = PRODUCTS_ROOT,
) -> dict[str, Any]:
    model_root = work_root / model
    requested_at = utcnow_iso()
    started_at = requested_at
    finished_at = requested_at
    published_csv_path = current_job_product_file or (products_root / f"{model}.csv")
    upload_report_path, import_report_path = _report_paths(repo_root, model)
    artifacts = RunArtifacts(
        model_root=model_root,
        published_csv_path=published_csv_path,
    )

    maybe_write_run_metadata(
        model=model,
        run_type=RunType.PUBLISH,
        status=RunStatus.RUNNING,
        model_root=model_root,
        artifacts=artifacts,
        requested_at=requested_at,
        started_at=started_at,
        finished_at=started_at,
        details={
            "publish_attempted": True,
            "publish_status": "attempted",
            "publish_stage": "-",
            "publish_message": "OpenCart publish phase started.",
            "upload_report_path": str(upload_report_path),
            "import_report_path": str(import_report_path),
        },
    )

    script_path = repo_root / OPENCART_PUBLISH_ENTRYPOINT
    publish_status = "failed"
    publish_stage = "preflight"
    publish_message: str | None = None
    run_status = RunStatus.FAILED

    try:
        preflight_stage, preflight_message, bash_path = _preflight_publish_environment(
            model=model,
            script_path=script_path,
            published_csv_path=published_csv_path,
            work_root=work_root,
            repo_root=repo_root,
        )
        if preflight_message is not None:
            publish_stage = str(preflight_stage or "preflight")
            publish_message = preflight_message
        else:
            env = os.environ.copy()
            env["CURRENT_JOB_PRODUCT_FILE"] = _shell_path_from_repo(
                published_csv_path,
                repo_root=repo_root,
            )
            completed = subprocess.run(
                [
                    str(bash_path),
                    _shell_path_from_repo(script_path, repo_root=repo_root),
                    model,
                ],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.stdout:
                print(completed.stdout.rstrip())
            if completed.stderr:
                print(completed.stderr.rstrip(), file=sys.stderr)

            if completed.returncode == 0:
                missing_reports = [
                    str(path)
                    for path in (upload_report_path, import_report_path)
                    if not path.exists()
                ]
                publish_stage = "csv_import"
                if missing_reports:
                    publish_status = "warning"
                    publish_message = (
                        "OpenCart publish completed but expected report files are missing: "
                        + ", ".join(missing_reports)
                    )
                else:
                    publish_status = "success"
                    publish_message = "OpenCart publish completed successfully."
                run_status = RunStatus.COMPLETED
            else:
                launcher_failure = _classify_bash_probe_failure(completed.stdout, completed.stderr)
                publish_stage = "preflight" if launcher_failure else PUBLISH_STAGE_EXIT_CODES.get(completed.returncode, "unknown")
                summary = _summarize_command_output(completed.stdout, completed.stderr)
                publish_message = f"OpenCart publish failed during {publish_stage}: exit={completed.returncode}"
                if launcher_failure:
                    publish_message = f"{publish_message} ({launcher_failure})"
                if summary:
                    publish_message = f"{publish_message}: {summary}"
    except FileNotFoundError as exc:
        publish_message = f"OpenCart publish failed during preflight: {exc}"
    except Exception as exc:
        publish_stage = "unknown"
        publish_message = f"OpenCart publish failed during unknown: {exc}"

    finished_at = utcnow_iso()
    warnings: list[str] = []
    if publish_status in {"warning", "failed"} and publish_message:
        warnings.append(publish_message)
    metadata_path = maybe_write_run_metadata(
        model=model,
        run_type=RunType.PUBLISH,
        status=run_status,
        model_root=model_root,
        artifacts=artifacts,
        requested_at=requested_at,
        started_at=started_at,
        finished_at=finished_at,
        warnings=warnings,
        error_detail=publish_message if publish_status == "failed" else None,
        details={
            "publish_attempted": True,
            "publish_status": publish_status,
            "publish_stage": publish_stage,
            "publish_message": publish_message,
            "upload_report_path": str(upload_report_path),
            "import_report_path": str(import_report_path),
        },
    )
    return {
        "run_status": run_status.value,
        "metadata_path": metadata_path,
        "published_csv_path": published_csv_path,
        "publish_attempted": True,
        "publish_status": publish_status,
        "publish_stage": publish_stage,
        "publish_message": publish_message,
        "upload_report_path": upload_report_path,
        "import_report_path": import_report_path,
    }
