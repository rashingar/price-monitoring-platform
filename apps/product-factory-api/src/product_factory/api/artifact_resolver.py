from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from product_factory.jobs.models import JobRecord, JobType

from ..repo_paths import REPO_ROOT, category_filter_review_path


@dataclass(frozen=True, slots=True)
class ResolvedArtifact:
    name: str
    path: str
    kind: str | None = None
    content_type: str | None = None
    content: str | None = None


def resolve_job_artifacts(
    record: JobRecord,
    *,
    repo_root: Path = REPO_ROOT,
) -> list[ResolvedArtifact]:
    paths = _existing_expected_paths(record, repo_root=repo_root)
    paths.update(record.artifacts)
    return [
        _resolved_artifact(name, path) for name, path in sorted(paths.items()) if path
    ]


def _existing_expected_paths(record: JobRecord, *, repo_root: Path) -> dict[str, str]:
    if not record.model:
        return {}
    paths = _expected_paths(record.job_type, record.model, repo_root=repo_root)
    return {name: str(path) for name, path in paths.items() if path.exists()}


def _expected_paths(
    job_type: JobType, model: str, *, repo_root: Path
) -> dict[str, Path]:
    model_root = repo_root / "work" / model
    scrape_dir = model_root / "scrape"
    llm_dir = model_root / "llm"
    candidate_dir = model_root / "candidate"
    products_csv = repo_root / "products" / f"{model}.csv"
    review_path = category_filter_review_path(model, repo_root=repo_root)

    prepare_paths = {
        "model_root": model_root,
        "scrape_dir": scrape_dir,
        "llm_dir": llm_dir,
        "raw_html_path": scrape_dir / f"{model}.raw.html",
        "source_json_path": scrape_dir / f"{model}.source.json",
        "scrape_normalized_json_path": scrape_dir / f"{model}.normalized.json",
        "source_report_json_path": scrape_dir / f"{model}.report.json",
        "llm_task_manifest_path": llm_dir / "task_manifest.json",
        "intro_text_context_path": llm_dir / "intro_text.context.json",
        "intro_text_prompt_path": llm_dir / "intro_text.prompt.txt",
        "intro_text_output_path": llm_dir / "intro_text.output.txt",
        "intro_text_trace_path": llm_dir / "intro_text.retry_trace.json",
        "intro_text_preview_path": llm_dir / "intro_text.preview.html",
        "seo_meta_context_path": llm_dir / "seo_meta.context.json",
        "seo_meta_prompt_path": llm_dir / "seo_meta.prompt.txt",
        "seo_meta_output_path": llm_dir / "seo_meta.output.json",
        "seo_meta_preview_path": llm_dir / "seo_meta.preview.json",
        "category_filter_review_path": review_path,
        "metadata_path": model_root / "prepare.run.json",
    }
    if job_type in {JobType.PREPARE, JobType.FULL_PIPELINE}:
        if job_type == JobType.FULL_PIPELINE:
            return {
                **prepare_paths,
                "candidate_dir": candidate_dir,
                "candidate_csv_path": candidate_dir / f"{model}.csv",
                "published_csv_path": products_csv,
                "candidate_normalized_json_path": candidate_dir
                / f"{model}.normalized.json",
                "validation_report_path": candidate_dir / f"{model}.validation.json",
                "description_html_path": candidate_dir / "description.html",
                "characteristics_html_path": candidate_dir / "characteristics.html",
                "render_metadata_path": model_root / "render.run.json",
                "publish_metadata_path": model_root / "publish.run.json",
                "upload_report_path": model_root / "upload.opencart.json",
                "import_report_path": model_root / "import.opencart.json",
            }
        return prepare_paths
    if job_type == JobType.AUTHORING_INTRO:
        return {
            "model_root": model_root,
            "llm_dir": llm_dir,
            "llm_task_manifest_path": llm_dir / "task_manifest.json",
            "intro_text_context_path": llm_dir / "intro_text.context.json",
            "intro_text_prompt_path": llm_dir / "intro_text.prompt.txt",
            "intro_text_output_path": llm_dir / "intro_text.output.txt",
            "intro_text_trace_path": llm_dir / "intro_text.retry_trace.json",
            "intro_text_preview_path": llm_dir / "intro_text.preview.html",
        }
    if job_type == JobType.AUTHORING_SEO:
        return {
            "model_root": model_root,
            "llm_dir": llm_dir,
            "llm_task_manifest_path": llm_dir / "task_manifest.json",
            "seo_meta_context_path": llm_dir / "seo_meta.context.json",
            "seo_meta_prompt_path": llm_dir / "seo_meta.prompt.txt",
            "seo_meta_output_path": llm_dir / "seo_meta.output.json",
            "seo_meta_preview_path": llm_dir / "seo_meta.preview.json",
        }
    if job_type == JobType.RENDER:
        return {
            "model_root": model_root,
            "scrape_dir": scrape_dir,
            "llm_dir": llm_dir,
            "candidate_dir": candidate_dir,
            "source_json_path": scrape_dir / f"{model}.source.json",
            "scrape_normalized_json_path": scrape_dir / f"{model}.normalized.json",
            "llm_task_manifest_path": llm_dir / "task_manifest.json",
            "intro_text_output_path": llm_dir / "intro_text.output.txt",
            "intro_text_trace_path": llm_dir / "intro_text.retry_trace.json",
            "seo_meta_output_path": llm_dir / "seo_meta.output.json",
            "candidate_csv_path": candidate_dir / f"{model}.csv",
            "published_csv_path": products_csv,
            "candidate_normalized_json_path": candidate_dir
            / f"{model}.normalized.json",
            "validation_report_path": candidate_dir / f"{model}.validation.json",
            "description_html_path": candidate_dir / "description.html",
            "characteristics_html_path": candidate_dir / "characteristics.html",
            "category_filter_review_path": review_path,
            "metadata_path": model_root / "render.run.json",
        }
    return {
        "model_root": model_root,
        "published_csv_path": products_csv,
        "category_filter_review_path": review_path,
        "metadata_path": model_root / "publish.run.json",
        "upload_report_path": model_root / "upload.opencart.json",
        "import_report_path": model_root / "import.opencart.json",
    }


def _artifact_kind(path: Path) -> str | None:
    if path.is_dir():
        return "directory"
    if path.is_file():
        if path.name.endswith(".preview.html"):
            return "text_preview"
        if path.name.endswith(".preview.json"):
            return "json_preview"
        return "file"
    return None


def _resolved_artifact(name: str, path: str) -> ResolvedArtifact:
    resolved_path = Path(path)
    kind = _artifact_kind(resolved_path)
    content_type, content = _preview_content(resolved_path, kind)
    return ResolvedArtifact(
        name=name,
        path=path,
        kind=kind,
        content_type=content_type,
        content=content,
    )


def _preview_content(path: Path, kind: str | None) -> tuple[str | None, str | None]:
    if kind not in {"text_preview", "json_preview"} or not path.is_file():
        return None, None
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None, None
    if len(content) > 20_000:
        content = content[:20_000] + "\n...[truncated]"
    if kind == "json_preview":
        try:
            content = json.dumps(json.loads(content), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass
        return "application/json", content
    return "text/html", content
