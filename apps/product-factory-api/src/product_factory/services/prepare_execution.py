from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Callable

from ..llm_contract import (
    build_intro_text_context,
    build_seo_meta_context,
    build_task_manifest,
)
from ..models import CLIInput
from ..prepare_stage import execute_prepare_stage
from ..repo_paths import INTRO_TEXT_PROMPT_PATH, REPO_ROOT, SEO_META_PROMPT_PATH
from ..utils import ensure_directory, utcnow_iso, write_json, write_text
from .execution_models import PreparedProductContext, PrepareExecutionResult, PrepareExecutionScrapeResult
from .errors import service_error_from_exception
from .metadata import maybe_write_run_metadata
from .models import RunArtifacts, RunStatus, RunType
from .settings_service import get_intro_text_policy

WORK_ROOT = REPO_ROOT / "work"
BLOCKED_BY_CHALLENGE = "blocked_by_challenge"


def _path_or_none(value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    return Path(value)


def execute_prepare_workflow(
    cli: CLIInput,
    *,
    work_root: Path = WORK_ROOT,
    execute_prepare_stage_fn: Callable[..., Mapping[str, object]] = execute_prepare_stage,
) -> PrepareExecutionResult:
    requested_at = utcnow_iso()
    started_at = requested_at
    model_root = ensure_directory(work_root / cli.model)
    scrape_dir = ensure_directory(model_root / "scrape")
    llm_dir = ensure_directory(model_root / "llm")
    prepared_context = PreparedProductContext.from_model(cli.model, model_root=model_root)
    task_manifest_path = prepared_context.task_manifest_path
    intro_text_context_path = prepared_context.intro_text_context_path
    intro_text_prompt_path = prepared_context.intro_text_prompt_path
    intro_text_output_path = prepared_context.intro_text_output_path
    seo_meta_context_path = prepared_context.seo_meta_context_path
    seo_meta_prompt_path = prepared_context.seo_meta_prompt_path
    seo_meta_output_path = prepared_context.seo_meta_output_path
    scrape_cli = CLIInput(**{**cli.to_dict(), "out": str(scrape_dir)})
    try:
        stage_result = execute_prepare_stage_fn(scrape_cli, model_dir=scrape_dir)
        prepared_context = PreparedProductContext.from_prepare_stage_result(
            cli=scrape_cli,
            model_root=model_root,
            scrape_dir=scrape_dir,
            llm_dir=llm_dir,
            stage_result=stage_result,
        )
        if _blocked_reason_from_stage_result(stage_result) == BLOCKED_BY_CHALLENGE:
            task_manifest = build_task_manifest(
                llm_dir=str(llm_dir),
                intro_text_context_path=str(intro_text_context_path),
                intro_text_prompt_path=str(intro_text_prompt_path),
                intro_text_output_path=str(intro_text_output_path),
                seo_meta_context_path=str(seo_meta_context_path),
                seo_meta_prompt_path=str(seo_meta_prompt_path),
                seo_meta_output_path=str(seo_meta_output_path),
            )
            task_manifest["prepare_mode"] = "blocked_snapshot"
            blocked_context = _build_blocked_llm_context(scrape_cli, stage_result)
            write_json(intro_text_context_path, {**blocked_context, "task": "intro_text"})
            write_text(intro_text_prompt_path, _blocked_prompt("intro_text"))
            write_json(seo_meta_context_path, {**blocked_context, "task": "seo_meta"})
            write_text(seo_meta_prompt_path, _blocked_prompt("seo_meta"))
            write_json(task_manifest_path, task_manifest)
            finished_at = utcnow_iso()
            metadata_path = maybe_write_run_metadata(
                model=cli.model,
                run_type=RunType.PREPARE,
                status=RunStatus.COMPLETED,
                model_root=model_root,
                artifacts=RunArtifacts(
                    model_root=model_root,
                    scrape_dir=scrape_dir,
                    llm_dir=llm_dir,
                    raw_html_path=_path_or_none(stage_result.get("raw_html_path")),
                    source_json_path=_path_or_none(stage_result.get("source_json_path")),
                    scrape_normalized_json_path=_path_or_none(stage_result.get("normalized_json_path")),
                    source_report_json_path=_path_or_none(stage_result.get("report_json_path")),
                    llm_task_manifest_path=task_manifest_path,
                    intro_text_context_path=intro_text_context_path,
                    intro_text_prompt_path=intro_text_prompt_path,
                    intro_text_output_path=intro_text_output_path,
                    seo_meta_context_path=seo_meta_context_path,
                    seo_meta_prompt_path=seo_meta_prompt_path,
                    seo_meta_output_path=seo_meta_output_path,
                ),
                requested_at=requested_at,
                started_at=started_at,
                finished_at=finished_at,
                warnings=PrepareExecutionScrapeResult.from_mapping(stage_result).report_warnings,
                details={
                    "source": str(stage_result.get("source", "")),
                    "llm_prepare_mode": "blocked_snapshot",
                    "llm_primary_outputs_dir": str(llm_dir),
                    "blocked_reason": BLOCKED_BY_CHALLENGE,
                },
            )
            return PrepareExecutionResult(
                model_root=model_root,
                scrape_dir=scrape_dir,
                llm_dir=llm_dir,
                task_manifest_path=task_manifest_path,
                intro_text_context_path=intro_text_context_path,
                intro_text_prompt_path=intro_text_prompt_path,
                intro_text_output_path=intro_text_output_path,
                seo_meta_context_path=seo_meta_context_path,
                seo_meta_prompt_path=seo_meta_prompt_path,
                seo_meta_output_path=seo_meta_output_path,
                run_status=RunStatus.COMPLETED,
                metadata_path=metadata_path,
                scrape_result=PrepareExecutionScrapeResult.from_mapping(stage_result),
            )
        deterministic_product = prepared_context.deterministic_product
        parsed = prepared_context.require_parsed()
        taxonomy = prepared_context.require_taxonomy()
        intro_policy = get_intro_text_policy(
            source=str(stage_result.get("source", "")),
            category_id=str(getattr(taxonomy, "category_id", "") or ""),
            taxonomy_path=str(getattr(taxonomy, "taxonomy_path", "") or ""),
        )
        intro_text_context = build_intro_text_context(
            cli=scrape_cli,
            parsed=parsed,
            taxonomy=taxonomy,
            deterministic_product=deterministic_product,
            intro_policy=intro_policy,
        )
        seo_meta_context = build_seo_meta_context(
            cli=scrape_cli,
            parsed=parsed,
            taxonomy=taxonomy,
            deterministic_product=deterministic_product,
        )
        intro_text_prompt = INTRO_TEXT_PROMPT_PATH.read_text(encoding="utf-8").replace(
            "{{LLM_CONTEXT_JSON}}",
            json.dumps(intro_text_context, ensure_ascii=False, indent=2),
        )
        seo_meta_prompt = SEO_META_PROMPT_PATH.read_text(encoding="utf-8").replace(
            "{{LLM_CONTEXT_JSON}}",
            json.dumps(seo_meta_context, ensure_ascii=False, indent=2),
        )
        task_manifest = build_task_manifest(
            llm_dir=str(llm_dir),
            intro_text_context_path=str(intro_text_context_path),
            intro_text_prompt_path=str(intro_text_prompt_path),
            intro_text_output_path=str(intro_text_output_path),
            seo_meta_context_path=str(seo_meta_context_path),
            seo_meta_prompt_path=str(seo_meta_prompt_path),
            seo_meta_output_path=str(seo_meta_output_path),
        )
        write_json(intro_text_context_path, intro_text_context)
        write_text(intro_text_prompt_path, intro_text_prompt)
        write_json(seo_meta_context_path, seo_meta_context)
        write_text(seo_meta_prompt_path, seo_meta_prompt)
        write_json(task_manifest_path, task_manifest)
        finished_at = utcnow_iso()
        metadata_path = maybe_write_run_metadata(
            model=cli.model,
            run_type=RunType.PREPARE,
            status=RunStatus.COMPLETED,
            model_root=model_root,
            artifacts=RunArtifacts(
                model_root=model_root,
                scrape_dir=scrape_dir,
                llm_dir=llm_dir,
                raw_html_path=_path_or_none(stage_result.get("raw_html_path")),
                source_json_path=_path_or_none(stage_result.get("source_json_path")),
                scrape_normalized_json_path=_path_or_none(stage_result.get("normalized_json_path")),
                source_report_json_path=_path_or_none(stage_result.get("report_json_path")),
                llm_task_manifest_path=task_manifest_path,
                intro_text_context_path=intro_text_context_path,
                intro_text_prompt_path=intro_text_prompt_path,
                intro_text_output_path=intro_text_output_path,
                seo_meta_context_path=seo_meta_context_path,
                seo_meta_prompt_path=seo_meta_prompt_path,
                seo_meta_output_path=seo_meta_output_path,
            ),
            requested_at=requested_at,
            started_at=started_at,
            finished_at=finished_at,
            warnings=PrepareExecutionScrapeResult.from_mapping(stage_result).report_warnings,
            details={
                "source": str(stage_result.get("source", "")),
                "llm_prepare_mode": "split_tasks",
                "llm_primary_outputs_dir": str(llm_dir),
            },
        )
        return PrepareExecutionResult(
            model_root=model_root,
            scrape_dir=scrape_dir,
            llm_dir=llm_dir,
            task_manifest_path=task_manifest_path,
            intro_text_context_path=intro_text_context_path,
            intro_text_prompt_path=intro_text_prompt_path,
            intro_text_output_path=intro_text_output_path,
            seo_meta_context_path=seo_meta_context_path,
            seo_meta_prompt_path=seo_meta_prompt_path,
            seo_meta_output_path=seo_meta_output_path,
            run_status=RunStatus.COMPLETED,
            metadata_path=metadata_path,
            scrape_result=PrepareExecutionScrapeResult.from_mapping(stage_result),
        )
    except Exception as exc:
        finished_at = utcnow_iso()
        service_error = service_error_from_exception(exc, operation="prepare")
        maybe_write_run_metadata(
            model=cli.model,
            run_type=RunType.PREPARE,
            status=RunStatus.FAILED,
            model_root=model_root,
            artifacts=RunArtifacts(
                model_root=model_root,
                scrape_dir=scrape_dir,
                llm_dir=llm_dir,
                raw_html_path=scrape_dir / f"{cli.model}.raw.html",
                source_json_path=scrape_dir / f"{cli.model}.source.json",
                scrape_normalized_json_path=scrape_dir / f"{cli.model}.normalized.json",
                source_report_json_path=scrape_dir / f"{cli.model}.report.json",
                llm_task_manifest_path=task_manifest_path,
                intro_text_context_path=intro_text_context_path,
                intro_text_prompt_path=intro_text_prompt_path,
                intro_text_output_path=intro_text_output_path,
                seo_meta_context_path=seo_meta_context_path,
                seo_meta_prompt_path=seo_meta_prompt_path,
                seo_meta_output_path=seo_meta_output_path,
            ),
            requested_at=requested_at,
            started_at=started_at,
            finished_at=finished_at,
            error_code=service_error.code,
            error_detail=service_error.message,
        )
        raise


def _blocked_reason_from_stage_result(stage_result: Mapping[str, object]) -> str:
    reason = str(stage_result.get("blocked_reason", "") or "")
    if reason:
        return reason
    parsed = stage_result.get("parsed")
    source = getattr(parsed, "source", None)
    return str(getattr(source, "page_type", "") or "")


def _build_blocked_llm_context(cli: CLIInput, stage_result: Mapping[str, object]) -> dict[str, object]:
    report = stage_result.get("report")
    report_payload = report if isinstance(report, Mapping) else {}
    blocked_snapshot = report_payload.get("blocked_snapshot")
    return {
        "input": {
            "model": cli.model,
            "url": cli.url,
        },
        "blocked_snapshot": blocked_snapshot if isinstance(blocked_snapshot, Mapping) else {"reason": BLOCKED_BY_CHALLENGE},
        "writer_rules": {
            "llm_owned_fields": [],
            "blocked": True,
            "reason": BLOCKED_BY_CHALLENGE,
        },
    }


def _blocked_prompt(task: str) -> str:
    return (
        f"{task} is blocked because the Skroutz source snapshot returned a bot challenge. "
        "Do not author product content until a valid product snapshot is available."
    )
