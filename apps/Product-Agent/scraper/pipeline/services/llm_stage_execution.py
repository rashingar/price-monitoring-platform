from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from ..llm_contract import (
    INTRO_MAX_WORDS,
    INTRO_MIN_WORDS,
    count_plain_text_words,
    validate_intro_text_output,
    validate_seo_meta_output,
)
from ..utils import read_json
from .errors import ServiceError, ServiceErrorCode
from .llm_config import load_openai_llm_config

INTRO_TEXT_STAGE = "intro_text"
SEO_META_STAGE = "seo_meta"
INTRO_TEXT_WORD_COUNT_ERROR = "llm_intro_text_word_count_invalid"
MAX_INTRO_ATTEMPTS = 3
LLM_OUTPUT_ENCODING = "utf-8"
UTF8_BOM = b"\xef\xbb\xbf"


@dataclass(slots=True)
class IntroTextAttemptTrace:
    attempt: int
    word_count: int
    error_codes: list[str]
    status: str
    reason: str
    output_path: Path


@dataclass(slots=True)
class IntroTextRetryFailure:
    stage: str
    code: str
    attempts: int
    reason: str
    output_path: Path
    trace_path: Path
    attempt_trace: list[IntroTextAttemptTrace]


class IntroTextRetryExhaustedError(ServiceError):
    def __init__(self, failure: IntroTextRetryFailure) -> None:
        super().__init__(
            ServiceErrorCode.VALIDATION_FAILURE.value,
            (
                f"LLM stage validation failed: stage={failure.stage}; error_code={failure.code}; "
                f"attempt_count={failure.attempts}; reason={failure.reason}"
            ),
            details={
                "stage": failure.stage,
                "error_code": failure.code,
                "attempt_count": failure.attempts,
                "reason": failure.reason,
                "output_path": str(failure.output_path),
                "trace_path": str(failure.trace_path),
                "attempt_trace": [
                    {
                        "attempt": item.attempt,
                        "word_count": item.word_count,
                        "error_codes": list(item.error_codes),
                        "status": item.status,
                        "reason": item.reason,
                        "output_path": str(item.output_path),
                    }
                    for item in failure.attempt_trace
                ],
            },
        )
        self.failure = failure
        self.stage = failure.stage
        self.stage_code = failure.code
        self.attempts = failure.attempts
        self.trace_path = failure.trace_path
        self.attempt_trace = list(failure.attempt_trace)


@dataclass(slots=True)
class SplitLLMTaskPaths:
    intro_text_context_path: Path
    intro_text_prompt_path: Path
    intro_text_output_path: Path
    intro_text_trace_path: Path
    seo_meta_context_path: Path
    seo_meta_prompt_path: Path
    seo_meta_output_path: Path


@dataclass(slots=True)
class SplitLLMStageResult:
    intro_text: str
    seo_meta_payload: dict[str, Any]
    task_paths: SplitLLMTaskPaths

    @property
    def llm_product(self) -> dict[str, Any]:
        return dict(self.seo_meta_payload.get("product", {}))

    @property
    def artifact_paths(self) -> dict[str, Path]:
        return {
            "intro_text_output_path": self.task_paths.intro_text_output_path,
            "intro_text_trace_path": self.task_paths.intro_text_trace_path,
            "seo_meta_output_path": self.task_paths.seo_meta_output_path,
        }


IntroTextResolver = Callable[..., str]
SeoMetaResolver = Callable[..., dict[str, Any]]


def run_intro_text_with_retry(
    *,
    intro_text_context_path: Path,
    intro_text_prompt_path: Path,
    intro_text_output_path: Path,
    resolve_intro_text_fn: IntroTextResolver | None = None,
    max_attempts: int = MAX_INTRO_ATTEMPTS,
    intro_policy: Any | None = None,
    force_refresh: bool = False,
) -> str:
    intro_word_min = _policy_int(intro_policy, "min_words", INTRO_MIN_WORDS)
    intro_word_max = _policy_int(intro_policy, "max_words", INTRO_MAX_WORDS)
    resolved_max_attempts = _policy_int(intro_policy, "max_attempts", max_attempts)
    resolver = resolve_intro_text_fn
    trace_path = intro_text_output_path.with_name("intro_text.retry_trace.json")
    attempt_trace: list[IntroTextAttemptTrace] = []
    for attempt in range(1, resolved_max_attempts + 1):
        if resolver is None:
            intro_payload = _resolve_intro_text_output(
                intro_text_context_path=intro_text_context_path,
                intro_text_prompt_path=intro_text_prompt_path,
                intro_text_output_path=intro_text_output_path,
                attempt=attempt,
                intro_word_min=intro_word_min,
                intro_word_max=intro_word_max,
                force_refresh=force_refresh,
            )
        else:
            intro_payload = resolver(
                intro_text_context_path=intro_text_context_path,
                intro_text_prompt_path=intro_text_prompt_path,
                intro_text_output_path=intro_text_output_path,
                attempt=attempt,
            )
        if not isinstance(intro_payload, str):
            failure_reason = "resolver returned a non-string intro payload"
            attempt_trace.append(
                IntroTextAttemptTrace(
                    attempt=attempt,
                    word_count=0,
                    error_codes=["llm_intro_text_invalid"],
                    status="failed",
                    reason=failure_reason,
                    output_path=intro_text_output_path,
                )
            )
            _write_intro_trace(trace_path, attempt_trace)
            raise _build_stage_validation_error(
                stage=INTRO_TEXT_STAGE,
                error_codes=["llm_intro_text_invalid"],
                attempt=attempt,
                reason=failure_reason,
                output_path=intro_text_output_path,
                trace_path=trace_path,
                attempt_trace=attempt_trace,
            )
        _persist_text_if_needed(
            intro_text_output_path,
            intro_payload,
            force_write=force_refresh or attempt > 1 or not intro_text_output_path.exists(),
        )
        normalized_intro, intro_errors = validate_intro_text_output(
            intro_payload,
            intro_word_min=intro_word_min,
            intro_word_max=intro_word_max,
        )
        word_count = count_plain_text_words(normalized_intro)
        if not intro_errors:
            attempt_trace.append(
                IntroTextAttemptTrace(
                    attempt=attempt,
                    word_count=word_count,
                    error_codes=[],
                    status="success",
                    reason="intro validated successfully",
                    output_path=intro_text_output_path,
                )
            )
            _write_intro_trace(trace_path, attempt_trace)
            return normalized_intro
        if any(error != INTRO_TEXT_WORD_COUNT_ERROR for error in intro_errors):
            failure_reason = "intro validation failed with a non-retryable error"
            attempt_trace.append(
                IntroTextAttemptTrace(
                    attempt=attempt,
                    word_count=word_count,
                    error_codes=list(intro_errors),
                    status="failed",
                    reason=failure_reason,
                    output_path=intro_text_output_path,
                )
            )
            _write_intro_trace(trace_path, attempt_trace)
            raise _build_stage_validation_error(
                stage=INTRO_TEXT_STAGE,
                error_codes=intro_errors,
                attempt=attempt,
                reason=failure_reason,
                output_path=intro_text_output_path,
                trace_path=trace_path,
                attempt_trace=attempt_trace,
            )
        failure_reason = _build_intro_word_count_reason(
            normalized_intro,
            intro_word_min=intro_word_min,
            intro_word_max=intro_word_max,
        )
        if attempt >= resolved_max_attempts:
            attempt_trace.append(
                IntroTextAttemptTrace(
                    attempt=attempt,
                    word_count=word_count,
                    error_codes=list(intro_errors),
                    status="failed",
                    reason=failure_reason,
                    output_path=intro_text_output_path,
                )
            )
            _write_intro_trace(trace_path, attempt_trace)
            raise IntroTextRetryExhaustedError(
                IntroTextRetryFailure(
                    stage=INTRO_TEXT_STAGE,
                    code=INTRO_TEXT_WORD_COUNT_ERROR,
                    attempts=attempt,
                    reason=failure_reason,
                    output_path=intro_text_output_path,
                    trace_path=trace_path,
                    attempt_trace=list(attempt_trace),
                )
            )
        attempt_trace.append(
            IntroTextAttemptTrace(
                attempt=attempt,
                word_count=word_count,
                error_codes=list(intro_errors),
                status="retry",
                reason=failure_reason,
                output_path=intro_text_output_path,
            )
        )
        _write_intro_trace(trace_path, attempt_trace)
    raise IntroTextRetryExhaustedError(
        IntroTextRetryFailure(
            stage=INTRO_TEXT_STAGE,
            code=INTRO_TEXT_WORD_COUNT_ERROR,
            attempts=resolved_max_attempts,
            reason="intro retry loop exited unexpectedly",
            output_path=intro_text_output_path,
            trace_path=trace_path,
            attempt_trace=list(attempt_trace),
        )
    )


def execute_split_llm_stage(
    *,
    llm_dir: Path,
    task_manifest_path: Path,
    resolve_intro_text_fn: IntroTextResolver | None = None,
    resolve_seo_meta_fn: SeoMetaResolver | None = None,
    intro_policy: Any | None = None,
) -> SplitLLMStageResult:
    task_paths = _resolve_split_llm_task_paths(llm_dir=llm_dir, task_manifest_path=task_manifest_path)
    seo_resolver = resolve_seo_meta_fn or _resolve_seo_meta_output
    seo_meta_payload = seo_resolver(
        seo_meta_context_path=task_paths.seo_meta_context_path,
        seo_meta_prompt_path=task_paths.seo_meta_prompt_path,
        seo_meta_output_path=task_paths.seo_meta_output_path,
    )
    if not isinstance(seo_meta_payload, dict):
        raise _build_stage_validation_error(
            stage=SEO_META_STAGE,
            error_codes=["llm_seo_meta_not_object"],
            attempt=1,
            reason="resolver returned a non-object seo_meta payload",
            output_path=task_paths.seo_meta_output_path,
        )
    _persist_json_if_needed(task_paths.seo_meta_output_path, seo_meta_payload)
    normalized_seo, seo_errors = validate_seo_meta_output(seo_meta_payload)
    if seo_errors:
        raise _build_stage_validation_error(
            stage=SEO_META_STAGE,
            error_codes=seo_errors,
            attempt=1,
            reason="seo_meta validation failed before intro execution",
            output_path=task_paths.seo_meta_output_path,
        )
    intro_text = run_intro_text_with_retry(
        intro_text_context_path=task_paths.intro_text_context_path,
        intro_text_prompt_path=task_paths.intro_text_prompt_path,
        intro_text_output_path=task_paths.intro_text_output_path,
        resolve_intro_text_fn=resolve_intro_text_fn,
        max_attempts=MAX_INTRO_ATTEMPTS,
        intro_policy=intro_policy,
    )
    return SplitLLMStageResult(
        intro_text=intro_text,
        seo_meta_payload=normalized_seo,
        task_paths=task_paths,
    )


def _resolve_split_llm_task_paths(*, llm_dir: Path, task_manifest_path: Path) -> SplitLLMTaskPaths:
    manifest = read_json(task_manifest_path) if task_manifest_path.exists() else {}
    tasks = manifest.get("primary_outputs", {}).get("tasks", {}) if isinstance(manifest, dict) else {}
    intro_task = tasks.get(INTRO_TEXT_STAGE, {}) if isinstance(tasks, dict) else {}
    seo_task = tasks.get(SEO_META_STAGE, {}) if isinstance(tasks, dict) else {}
    intro_text_output_path = Path(intro_task.get("expected_output_path", llm_dir / "intro_text.output.txt"))
    return SplitLLMTaskPaths(
        intro_text_context_path=Path(intro_task.get("context_path", llm_dir / "intro_text.context.json")),
        intro_text_prompt_path=Path(intro_task.get("prompt_path", llm_dir / "intro_text.prompt.txt")),
        intro_text_output_path=intro_text_output_path,
        intro_text_trace_path=intro_text_output_path.with_name("intro_text.retry_trace.json"),
        seo_meta_context_path=Path(seo_task.get("context_path", llm_dir / "seo_meta.context.json")),
        seo_meta_prompt_path=Path(seo_task.get("prompt_path", llm_dir / "seo_meta.prompt.txt")),
        seo_meta_output_path=Path(seo_task.get("expected_output_path", llm_dir / "seo_meta.output.json")),
    )


def _resolve_intro_text_output(
    *,
    intro_text_context_path: Path,
    intro_text_prompt_path: Path,
    intro_text_output_path: Path,
    attempt: int,
    intro_word_min: int = INTRO_MIN_WORDS,
    intro_word_max: int = INTRO_MAX_WORDS,
    force_refresh: bool = False,
) -> str:
    del intro_text_context_path
    if intro_text_output_path.exists() and attempt == 1 and not force_refresh:
        return _read_llm_output_text(intro_text_output_path)
    if not intro_text_prompt_path.exists():
        raise FileNotFoundError(f"Missing intro_text prompt artifact: {intro_text_prompt_path}")
    return _request_openai_text(
        prompt_path=intro_text_prompt_path,
        retry_note=_intro_retry_note(attempt, intro_word_min=intro_word_min, intro_word_max=intro_word_max),
    )


def _resolve_seo_meta_output(
    *,
    seo_meta_context_path: Path,
    seo_meta_prompt_path: Path,
    seo_meta_output_path: Path,
    force_refresh: bool = False,
) -> dict[str, Any]:
    del seo_meta_context_path
    if seo_meta_output_path.exists() and not force_refresh:
        payload = json.loads(_read_llm_output_text(seo_meta_output_path))
    else:
        if not seo_meta_prompt_path.exists():
            raise FileNotFoundError(f"Missing seo_meta prompt artifact: {seo_meta_prompt_path}")
        payload = json.loads(_request_openai_text(prompt_path=seo_meta_prompt_path))
    if not isinstance(payload, dict):
        raise ServiceError(
            ServiceErrorCode.VALIDATION_FAILURE.value,
            "Invalid seo_meta payload type.",
            details={
                "stage": SEO_META_STAGE,
                "error_codes": ["llm_seo_meta_not_object"],
                "attempt_count": 1,
                "output_path": str(seo_meta_output_path),
            },
        )
    return payload


def run_seo_meta_once(
    *,
    seo_meta_context_path: Path,
    seo_meta_prompt_path: Path,
    seo_meta_output_path: Path,
    resolve_seo_meta_fn: SeoMetaResolver | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    if resolve_seo_meta_fn is None:
        seo_meta_payload = _resolve_seo_meta_output(
            seo_meta_context_path=seo_meta_context_path,
            seo_meta_prompt_path=seo_meta_prompt_path,
            seo_meta_output_path=seo_meta_output_path,
            force_refresh=force_refresh,
        )
    else:
        seo_meta_payload = resolve_seo_meta_fn(
            seo_meta_context_path=seo_meta_context_path,
            seo_meta_prompt_path=seo_meta_prompt_path,
            seo_meta_output_path=seo_meta_output_path,
        )
    if not isinstance(seo_meta_payload, dict):
        raise _build_stage_validation_error(
            stage=SEO_META_STAGE,
            error_codes=["llm_seo_meta_not_object"],
            attempt=1,
            reason="resolver returned a non-object seo_meta payload",
            output_path=seo_meta_output_path,
        )
    _persist_json_if_needed(seo_meta_output_path, seo_meta_payload, force_write=force_refresh)
    normalized_seo, seo_errors = validate_seo_meta_output(seo_meta_payload)
    if seo_errors:
        raise _build_stage_validation_error(
            stage=SEO_META_STAGE,
            error_codes=seo_errors,
            attempt=1,
            reason="seo_meta validation failed",
            output_path=seo_meta_output_path,
        )
    return normalized_seo


def _request_openai_text(*, prompt_path: Path, retry_note: str = "") -> str:
    prompt = prompt_path.read_text(encoding="utf-8")
    if retry_note:
        prompt = f"{prompt}\n\n{retry_note}"
    config = load_openai_llm_config()
    client = _build_openai_client(api_key=config.api_key)
    request_payload: dict[str, Any] = {
        "model": config.model,
        "input": prompt,
    }
    if config.reasoning_effort:
        request_payload["reasoning"] = {"effort": config.reasoning_effort}
    response = client.responses.create(**request_payload)
    output_text = getattr(response, "output_text", "")
    if not isinstance(output_text, str) or not output_text.strip():
        raise ServiceError(
            ServiceErrorCode.UNEXPECTED_FAILURE.value,
            "OpenAI Responses API returned empty output text.",
        )
    return output_text.strip()


def _build_openai_client(*, api_key: str):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ServiceError(
            ServiceErrorCode.UNEXPECTED_FAILURE.value,
            "OpenAI Python SDK is not installed. Install dependencies from requirements.txt.",
            cause=exc,
        ) from exc
    return OpenAI(api_key=api_key)


def _intro_retry_note(
    attempt: int,
    *,
    intro_word_min: int = INTRO_MIN_WORDS,
    intro_word_max: int = INTRO_MAX_WORDS,
) -> str:
    if attempt <= 1:
        return ""
    return (
        "Previous intro_text output failed validation for word count. "
        f"Regenerate attempt {attempt} so the final Greek paragraph is {intro_word_min}-{intro_word_max} visible words. "
        "<strong> tags do not count as words."
    )


def _persist_text_if_needed(path: Path, value: str, *, force_write: bool = False) -> None:
    has_bom = _has_utf8_bom(path) if path.exists() else False
    current = _read_llm_output_text(path) if path.exists() else None
    if force_write or has_bom or current != value:
        _write_text_atomic(path, value)


def _persist_json_if_needed(path: Path, payload: Mapping[str, Any], *, force_write: bool = False) -> None:
    has_bom = _has_utf8_bom(path) if path.exists() else False
    current = json.loads(_read_llm_output_text(path)) if path.exists() else None
    if force_write or has_bom or current != dict(payload):
        _write_json_atomic(path, dict(payload))


def _write_intro_trace(path: Path, attempt_trace: list[IntroTextAttemptTrace]) -> None:
    _write_json_atomic(
        path,
        [
            {
                "attempt": item.attempt,
                "word_count": item.word_count,
                "error_codes": list(item.error_codes),
                "status": item.status,
                "reason": item.reason,
                "output_path": str(item.output_path),
            }
            for item in attempt_trace
        ],
    )


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _write_temp_file(path=path, payload=value)
    try:
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _write_temp_file(
        path=path,
        payload=json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
    try:
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _write_temp_file(*, path: Path, payload: str) -> Path:
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding=LLM_OUTPUT_ENCODING,
            dir=path.parent,
            delete=False,
            prefix=f"{path.name}.",
            suffix=".tmp",
        ) as handle:
            handle.write(payload)
            temp_path = Path(handle.name)
        return temp_path
    except Exception:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise


def _read_llm_output_text(path: Path) -> str:
    text = path.read_text(encoding=LLM_OUTPUT_ENCODING)
    return text[1:] if text.startswith("\ufeff") else text


def _has_utf8_bom(path: Path) -> bool:
    return path.read_bytes().startswith(UTF8_BOM)


def _build_intro_word_count_reason(
    intro_text: str,
    *,
    intro_word_min: int = INTRO_MIN_WORDS,
    intro_word_max: int = INTRO_MAX_WORDS,
) -> str:
    word_count = count_plain_text_words(intro_text)
    return f"word count {word_count} is outside {intro_word_min}-{intro_word_max}"


def _policy_int(policy: Any | None, field_name: str, default: int) -> int:
    if policy is None:
        return default
    if isinstance(policy, Mapping):
        value = policy.get(field_name, default)
    else:
        value = getattr(policy, field_name, default)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _build_stage_validation_error(
    *,
    stage: str,
    error_codes: list[str],
    attempt: int,
    reason: str,
    output_path: Path,
    trace_path: Path | None = None,
    attempt_trace: list[IntroTextAttemptTrace] | None = None,
) -> ServiceError:
    primary_error_code = error_codes[0] if len(error_codes) == 1 else error_codes
    return ServiceError(
        ServiceErrorCode.VALIDATION_FAILURE.value,
        (
            f"LLM stage validation failed: stage={stage}; error_code={primary_error_code}; "
            f"attempt_count={attempt}; reason={reason}"
        ),
        details={
            "stage": stage,
            "error_code": primary_error_code,
            "error_codes": list(error_codes),
            "attempt_count": attempt,
            "reason": reason,
            "output_path": str(output_path),
            "trace_path": str(trace_path) if trace_path is not None else None,
            "attempt_trace": [
                {
                    "attempt": item.attempt,
                    "word_count": item.word_count,
                    "error_codes": list(item.error_codes),
                    "status": item.status,
                    "reason": item.reason,
                    "output_path": str(item.output_path),
                }
                for item in (attempt_trace or [])
            ],
        },
    )
