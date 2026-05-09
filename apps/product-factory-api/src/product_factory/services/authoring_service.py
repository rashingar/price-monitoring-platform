from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import repo_paths
from ..intro_text_markup import summarize_intro_text_emphasis
from ..llm_contract import count_plain_text_words, validate_intro_text_output, validate_seo_meta_output
from ..utils import read_json
from .errors import ServiceError, ServiceErrorCode
from .execution_models import PreparedProductContext
from .llm_stage_execution import (
    IntroTextResolver,
    SeoMetaResolver,
    run_intro_text_with_retry,
    run_seo_meta_once,
)
from .settings_service import IntroTextPolicy, get_intro_text_policy


class PreparedAuthoringArtifactsNotFoundError(RuntimeError):
    pass


@dataclass(slots=True)
class IntroTextTaskStatus:
    status: str
    output_path: str
    trace_path: str
    word_count: int | None
    min_words: int
    max_words: int
    max_attempts: int
    errors: list[str] = field(default_factory=list)
    emphasis_warning_codes: list[str] = field(default_factory=list)
    strong_span_count: int | None = None
    emphasized_word_count: int | None = None
    visible_word_count: int | None = None
    emphasized_word_ratio: float | None = None
    updated_at: str | None = None


@dataclass(slots=True)
class SeoMetaTaskStatus:
    status: str
    output_path: str
    errors: list[str] = field(default_factory=list)
    updated_at: str | None = None


@dataclass(slots=True)
class AuthoringStatus:
    model: str
    llm_dir: str
    intro_text: IntroTextTaskStatus
    seo_meta: SeoMetaTaskStatus
    ready_for_render: bool
    render_block_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def get_authoring_status(model: str) -> AuthoringStatus:
    context = _load_prepared_authoring_context(model)
    return _build_authoring_status(context)


def run_intro_text_authoring(
    model: str,
    retry: bool = False,
    *,
    resolve_intro_text_fn: IntroTextResolver | None = None,
) -> AuthoringStatus:
    context = _load_prepared_authoring_context(model)
    policy = _intro_policy_for_context(context)
    run_intro_text_with_retry(
        intro_text_context_path=context.intro_text_context_path,
        intro_text_prompt_path=context.intro_text_prompt_path,
        intro_text_output_path=context.intro_text_output_path,
        resolve_intro_text_fn=resolve_intro_text_fn,
        intro_policy=policy,
        max_attempts=policy.max_attempts,
        force_refresh=retry,
    )
    return _build_authoring_status(context)


def run_seo_meta_authoring(
    model: str,
    retry: bool = False,
    *,
    resolve_seo_meta_fn: SeoMetaResolver | None = None,
) -> AuthoringStatus:
    context = _load_prepared_authoring_context(model)
    run_seo_meta_once(
        seo_meta_context_path=context.seo_meta_context_path,
        seo_meta_prompt_path=context.seo_meta_prompt_path,
        seo_meta_output_path=context.seo_meta_output_path,
        resolve_seo_meta_fn=resolve_seo_meta_fn,
        force_refresh=retry,
    )
    return _build_authoring_status(context)


def _load_prepared_authoring_context(model: str) -> PreparedProductContext:
    model_root = repo_paths.model_root_path(model)
    context = PreparedProductContext.from_model(model, model_root=model_root)
    required_paths = {
        "source_json_path": context.source_json_path,
        "scrape_normalized_json_path": context.scrape_normalized_json_path,
        "task_manifest_path": context.task_manifest_path,
        "intro_text_context_path": context.intro_text_context_path,
        "intro_text_prompt_path": context.intro_text_prompt_path,
        "seo_meta_context_path": context.seo_meta_context_path,
        "seo_meta_prompt_path": context.seo_meta_prompt_path,
    }
    missing = {name: path for name, path in required_paths.items() if not path.exists()}
    if missing:
        raise PreparedAuthoringArtifactsNotFoundError(
            f"Prepared authoring artifacts not found for model {model}. Run prepare first."
        )
    return context


def _build_authoring_status(context: PreparedProductContext) -> AuthoringStatus:
    intro_status = _intro_text_status(context)
    seo_status = _seo_meta_status(context)
    render_block_reasons: list[str] = []
    if intro_status.status != "valid":
        render_block_reasons.append(f"intro_text_{intro_status.status}")
    if seo_status.status != "valid":
        render_block_reasons.append(f"seo_meta_{seo_status.status}")
    return AuthoringStatus(
        model=context.model,
        llm_dir=str(context.llm_dir),
        intro_text=intro_status,
        seo_meta=seo_status,
        ready_for_render=not render_block_reasons,
        render_block_reasons=render_block_reasons,
        warnings=[],
    )


def _intro_text_status(context: PreparedProductContext) -> IntroTextTaskStatus:
    policy = _intro_policy_for_context(context)
    trace_path = context.intro_text_output_path.with_name("intro_text.retry_trace.json")
    if not context.intro_text_output_path.exists():
        return IntroTextTaskStatus(
            status="missing",
            output_path=str(context.intro_text_output_path),
            trace_path=str(trace_path),
            word_count=None,
            min_words=policy.min_words,
            max_words=policy.max_words,
            max_attempts=policy.max_attempts,
            errors=[],
            emphasis_warning_codes=[],
            strong_span_count=None,
            emphasized_word_count=None,
            visible_word_count=None,
            emphasized_word_ratio=None,
            updated_at=None,
        )
    diagnostics: dict[str, object] = {}
    try:
        raw_text = _read_text_no_bom(context.intro_text_output_path)
        normalized, errors = validate_intro_text_output(
            raw_text,
            intro_word_min=policy.min_words,
            intro_word_max=policy.max_words,
            intro_max_emphasized_word_ratio=policy.max_emphasized_word_ratio,
        )
        diagnostics = summarize_intro_text_emphasis(
            raw_text,
            max_emphasized_word_ratio=policy.max_emphasized_word_ratio,
        )
        word_count = count_plain_text_words(normalized)
    except Exception as exc:
        errors = [f"llm_intro_text_read_error:{exc}"]
        word_count = None
    return IntroTextTaskStatus(
        status="valid" if not errors else "invalid",
        output_path=str(context.intro_text_output_path),
        trace_path=str(trace_path),
        word_count=word_count,
        min_words=policy.min_words,
        max_words=policy.max_words,
        max_attempts=policy.max_attempts,
        errors=list(errors),
        emphasis_warning_codes=list(diagnostics.get("emphasis_warning_codes", [])),
        strong_span_count=_optional_int(diagnostics.get("strong_span_count")),
        emphasized_word_count=_optional_int(diagnostics.get("emphasized_word_count")),
        visible_word_count=_optional_int(diagnostics.get("visible_word_count")),
        emphasized_word_ratio=_optional_float(diagnostics.get("emphasized_word_ratio")),
        updated_at=_updated_at(context.intro_text_output_path),
    )


def _seo_meta_status(context: PreparedProductContext) -> SeoMetaTaskStatus:
    if not context.seo_meta_output_path.exists():
        return SeoMetaTaskStatus(
            status="missing",
            output_path=str(context.seo_meta_output_path),
            errors=[],
            updated_at=None,
        )
    try:
        payload = json.loads(_read_text_no_bom(context.seo_meta_output_path))
        _, errors = validate_seo_meta_output(payload)
    except Exception as exc:
        errors = [f"llm_seo_meta_read_error:{exc}"]
    return SeoMetaTaskStatus(
        status="valid" if not errors else "invalid",
        output_path=str(context.seo_meta_output_path),
        errors=list(errors),
        updated_at=_updated_at(context.seo_meta_output_path),
    )


def _intro_policy_for_context(context: PreparedProductContext) -> IntroTextPolicy:
    source = ""
    category_id = ""
    taxonomy_path = ""
    try:
        source_payload = read_json(context.source_json_path)
        source = str(source_payload.get("source_name", "") or "")
    except Exception:
        pass
    try:
        normalized = read_json(context.scrape_normalized_json_path)
        taxonomy = normalized.get("taxonomy", {})
        if isinstance(taxonomy, dict):
            category_id = str(taxonomy.get("category_id", "") or "")
            taxonomy_path = str(taxonomy.get("taxonomy_path", "") or taxonomy.get("path", "") or "")
    except Exception:
        pass
    return get_intro_text_policy(source=source, category_id=category_id, taxonomy_path=taxonomy_path)


def _read_text_no_bom(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return text[1:] if text.startswith("\ufeff") else text


def _updated_at(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, (float, int)) and not isinstance(value, bool) else None


def authoring_service_error_from_exception(exc: Exception) -> ServiceError:
    if isinstance(exc, ServiceError):
        return exc
    if isinstance(exc, PreparedAuthoringArtifactsNotFoundError):
        return ServiceError(ServiceErrorCode.MISSING_ARTIFACT.value, str(exc), cause=exc)
    return ServiceError(ServiceErrorCode.UNEXPECTED_FAILURE.value, str(exc), cause=exc)
