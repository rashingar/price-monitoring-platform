import json
import os
from pathlib import Path

import pytest

from product_factory.services import ServiceError, ServiceErrorCode
from product_factory.services.llm_config import load_openai_llm_config
from product_factory.services.llm_stage_execution import (
    INTRO_TEXT_WORD_COUNT_ERROR,
    IntroTextRetryExhaustedError,
    execute_split_llm_stage,
    run_intro_text_with_retry,
)


def _build_intro(words: int) -> str:
    return " ".join(["λέξη"] * words)


def _write_task_manifest(llm_dir: Path) -> Path:
    llm_dir.mkdir(parents=True, exist_ok=True)
    task_manifest_path = llm_dir / "task_manifest.json"
    task_manifest_path.write_text(
        json.dumps(
            {
                "primary_outputs": {
                    "tasks": {
                        "intro_text": {
                            "context_path": str(llm_dir / "intro_text.context.json"),
                            "prompt_path": str(llm_dir / "intro_text.prompt.txt"),
                            "expected_output_path": str(
                                llm_dir / "intro_text.output.txt"
                            ),
                        },
                        "seo_meta": {
                            "context_path": str(llm_dir / "seo_meta.context.json"),
                            "prompt_path": str(llm_dir / "seo_meta.prompt.txt"),
                            "expected_output_path": str(
                                llm_dir / "seo_meta.output.json"
                            ),
                        },
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (llm_dir / "intro_text.context.json").write_text("{}", encoding="utf-8")
    (llm_dir / "intro_text.prompt.txt").write_text("intro prompt", encoding="utf-8")
    (llm_dir / "seo_meta.context.json").write_text("{}", encoding="utf-8")
    (llm_dir / "seo_meta.prompt.txt").write_text("seo prompt", encoding="utf-8")
    return task_manifest_path


def test_load_openai_llm_config_reads_env_file_without_secret_defaults(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "OPENAI_API_KEY='test-key'\nOPENAI_MODEL=\"gpt-test\"\nOPENAI_REASONING_EFFORT=low\n",
        encoding="utf-8",
    )

    config = load_openai_llm_config(env={}, env_file=env_file)

    assert config.api_key == "test-key"
    assert config.model == "gpt-test"
    assert config.reasoning_effort == "low"


def test_load_openai_llm_config_treats_none_reasoning_effort_as_unset(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "OPENAI_API_KEY='test-key'\nOPENAI_MODEL=\"gpt-test\"\nOPENAI_REASONING_EFFORT=none\n",
        encoding="utf-8",
    )

    config = load_openai_llm_config(env={}, env_file=env_file)

    assert config.reasoning_effort is None


def test_load_openai_llm_config_requires_key_and_model(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text("OPENAI_MODEL=gpt-test\n", encoding="utf-8")

    with pytest.raises(ServiceError) as excinfo:
        load_openai_llm_config(env={}, env_file=env_file)

    assert excinfo.value.code == ServiceErrorCode.UNEXPECTED_FAILURE.value
    assert "Missing OPENAI_API_KEY" in excinfo.value.message

    with pytest.raises(ServiceError) as model_excinfo:
        load_openai_llm_config(
            env={"OPENAI_API_KEY": "test-key"}, env_file=tmp_path / "missing.env"
        )

    assert model_excinfo.value.code == ServiceErrorCode.UNEXPECTED_FAILURE.value
    assert "Missing OPENAI_MODEL" in model_excinfo.value.message


def test_execute_split_llm_stage_uses_openai_responses_when_outputs_are_missing(
    tmp_path: Path, monkeypatch
) -> None:
    import product_factory.services.llm_stage_execution as llm_stage_execution
    from product_factory.services.llm_config import OpenAILLMConfig

    llm_dir = tmp_path / "work" / "233541" / "llm"
    task_manifest_path = _write_task_manifest(llm_dir)
    calls: list[dict[str, str]] = []
    valid_seo = {
        "product": {
            "meta_description": "Valid generated meta description.",
            "meta_keywords": ["LG", "Example"],
        }
    }

    class FakeResponse:
        def __init__(self, output_text: str) -> None:
            self.output_text = output_text

    class FakeResponses:
        def create(self, **kwargs) -> FakeResponse:
            calls.append(kwargs)
            input = kwargs["input"]
            if "seo prompt" in input:
                return FakeResponse(json.dumps(valid_seo, ensure_ascii=False))
            return FakeResponse(_build_intro(100))

    class FakeClient:
        responses = FakeResponses()

    monkeypatch.setattr(
        llm_stage_execution,
        "load_openai_llm_config",
        lambda: OpenAILLMConfig(
            api_key="test-key", model="gpt-test", reasoning_effort="low"
        ),
    )
    monkeypatch.setattr(
        llm_stage_execution, "_build_openai_client", lambda *, api_key: FakeClient()
    )

    result = execute_split_llm_stage(
        llm_dir=llm_dir, task_manifest_path=task_manifest_path
    )

    assert [call["model"] for call in calls] == ["gpt-test", "gpt-test"]
    assert calls[0]["input"] == "seo prompt"
    assert calls[1]["input"] == "intro prompt"
    assert calls[0]["reasoning"] == {"effort": "low"}
    assert calls[1]["reasoning"] == {"effort": "low"}
    assert result.intro_text == _build_intro(100)
    assert (
        result.seo_meta_payload["product"]["meta_description"]
        == valid_seo["product"]["meta_description"]
    )
    assert (
        result.seo_meta_payload["product"]["meta_keywords"]
        == valid_seo["product"]["meta_keywords"]
    )
    assert (llm_dir / "intro_text.output.txt").read_text(
        encoding="utf-8"
    ) == _build_intro(100)
    assert (
        json.loads((llm_dir / "seo_meta.output.json").read_text(encoding="utf-8"))
        == valid_seo
    )


def test_execute_split_llm_stage_accepts_valid_intro_on_first_attempt(
    tmp_path: Path,
) -> None:
    llm_dir = tmp_path / "work" / "233541" / "llm"
    task_manifest_path = _write_task_manifest(llm_dir)
    calls = {"seo": 0, "intro": 0}

    def resolve_seo_meta(**_kwargs):
        calls["seo"] += 1
        return {
            "product": {
                "meta_description": "Περιγραφή προϊόντος.",
                "meta_keywords": ["LG", "GSGV80PYLL"],
            }
        }

    def resolve_intro_text(**_kwargs):
        calls["intro"] += 1
        return _build_intro(100)

    result = execute_split_llm_stage(
        llm_dir=llm_dir,
        task_manifest_path=task_manifest_path,
        resolve_intro_text_fn=resolve_intro_text,
        resolve_seo_meta_fn=resolve_seo_meta,
    )

    assert calls == {"seo": 1, "intro": 1}
    assert len(result.intro_text.split()) == 100
    assert result.llm_product["meta_description"] == "Περιγραφή προϊόντος."
    assert result.artifact_paths["intro_text_output_path"].read_text(
        encoding="utf-8"
    ) == _build_intro(100)
    trace = json.loads(
        result.artifact_paths["intro_text_trace_path"].read_text(encoding="utf-8")
    )
    assert trace == [
        {
            "attempt": 1,
            "word_count": 100,
            "error_codes": [],
            "status": "success",
            "reason": "intro validated successfully",
            "output_path": str(result.artifact_paths["intro_text_output_path"]),
        }
    ]


def test_run_intro_text_with_retry_retries_word_count_failures_only(
    tmp_path: Path,
) -> None:
    llm_dir = tmp_path / "work" / "233541" / "llm"
    _write_task_manifest(llm_dir)
    attempts: list[int] = []

    def resolve_intro_text(**kwargs):
        attempts.append(kwargs["attempt"])
        return _build_intro(59 if kwargs["attempt"] == 1 else 80)

    result = run_intro_text_with_retry(
        intro_text_context_path=llm_dir / "intro_text.context.json",
        intro_text_prompt_path=llm_dir / "intro_text.prompt.txt",
        intro_text_output_path=llm_dir / "intro_text.output.txt",
        resolve_intro_text_fn=resolve_intro_text,
    )

    assert attempts == [1, 2]
    assert len(result.split()) == 80
    assert (llm_dir / "intro_text.output.txt").read_text(
        encoding="utf-8"
    ) == _build_intro(80)
    trace = json.loads(
        (llm_dir / "intro_text.retry_trace.json").read_text(encoding="utf-8")
    )
    assert [item["status"] for item in trace] == ["retry", "success"]
    assert [item["word_count"] for item in trace] == [59, 80]


def test_run_intro_text_with_retry_accepts_113_words_immediately(
    tmp_path: Path,
) -> None:
    llm_dir = tmp_path / "work" / "233541" / "llm"
    _write_task_manifest(llm_dir)
    attempts: list[int] = []

    def resolve_intro_text(**kwargs):
        attempts.append(kwargs["attempt"])
        return _build_intro(113)

    result = run_intro_text_with_retry(
        intro_text_context_path=llm_dir / "intro_text.context.json",
        intro_text_prompt_path=llm_dir / "intro_text.prompt.txt",
        intro_text_output_path=llm_dir / "intro_text.output.txt",
        resolve_intro_text_fn=resolve_intro_text,
    )

    assert attempts == [1]
    assert len(result.split()) == 113


def test_run_intro_text_with_retry_counts_visible_words_with_strong_tags(
    tmp_path: Path,
) -> None:
    llm_dir = tmp_path / "work" / "233541" / "llm"
    _write_task_manifest(llm_dir)
    intro = "<strong>λέξη λέξη</strong> " + " ".join(["λέξη"] * 78)

    result = run_intro_text_with_retry(
        intro_text_context_path=llm_dir / "intro_text.context.json",
        intro_text_prompt_path=llm_dir / "intro_text.prompt.txt",
        intro_text_output_path=llm_dir / "intro_text.output.txt",
        resolve_intro_text_fn=lambda **_kwargs: intro,
    )

    assert result == intro
    trace = json.loads(
        (llm_dir / "intro_text.retry_trace.json").read_text(encoding="utf-8")
    )
    assert trace[0]["word_count"] == 80


def test_run_intro_text_with_retry_stops_after_three_invalid_attempts(
    tmp_path: Path,
) -> None:
    llm_dir = tmp_path / "work" / "233541" / "llm"
    _write_task_manifest(llm_dir)
    attempts: list[int] = []

    def resolve_intro_text(**kwargs):
        attempts.append(kwargs["attempt"])
        return _build_intro(59)

    with pytest.raises(IntroTextRetryExhaustedError) as excinfo:
        run_intro_text_with_retry(
            intro_text_context_path=llm_dir / "intro_text.context.json",
            intro_text_prompt_path=llm_dir / "intro_text.prompt.txt",
            intro_text_output_path=llm_dir / "intro_text.output.txt",
            resolve_intro_text_fn=resolve_intro_text,
        )

    assert attempts == [1, 2, 3]
    assert excinfo.value.code == ServiceErrorCode.VALIDATION_FAILURE.value
    assert excinfo.value.failure.stage == "intro_text"
    assert excinfo.value.failure.code == INTRO_TEXT_WORD_COUNT_ERROR
    assert excinfo.value.failure.attempts == 3
    assert excinfo.value.details["stage"] == "intro_text"
    assert excinfo.value.details["error_code"] == INTRO_TEXT_WORD_COUNT_ERROR
    assert excinfo.value.details["attempt_count"] == 3
    assert excinfo.value.details["reason"] == "word count 59 is outside 60-180"
    assert excinfo.value.trace_path == llm_dir / "intro_text.retry_trace.json"
    assert [item.status for item in excinfo.value.attempt_trace] == [
        "retry",
        "retry",
        "failed",
    ]
    assert "stage=intro_text" in excinfo.value.message
    assert "error_code=llm_intro_text_word_count_invalid" in excinfo.value.message
    trace = json.loads(
        (llm_dir / "intro_text.retry_trace.json").read_text(encoding="utf-8")
    )
    assert [item["attempt"] for item in trace] == [1, 2, 3]
    assert [item["status"] for item in trace] == ["retry", "retry", "failed"]


def test_run_intro_text_with_retry_retries_intro_markup_failures(
    tmp_path: Path,
) -> None:
    llm_dir = tmp_path / "work" / "233541" / "llm"
    _write_task_manifest(llm_dir)
    attempts: list[int] = []
    valid_intro = _build_intro(120)

    def resolve_intro_text(**kwargs):
        attempts.append(kwargs["attempt"])
        if kwargs["attempt"] == 1:
            return f"<em>{valid_intro}</em>"
        return valid_intro

    result = run_intro_text_with_retry(
        intro_text_context_path=llm_dir / "intro_text.context.json",
        intro_text_prompt_path=llm_dir / "intro_text.prompt.txt",
        intro_text_output_path=llm_dir / "intro_text.output.txt",
        resolve_intro_text_fn=resolve_intro_text,
    )

    assert result == valid_intro
    assert attempts == [1, 2]
    trace = json.loads(
        (llm_dir / "intro_text.retry_trace.json").read_text(encoding="utf-8")
    )
    assert [item["status"] for item in trace] == ["retry", "success"]
    assert "llm_intro_text_html_invalid" in trace[0]["error_codes"]


def test_execute_split_llm_stage_keeps_seo_meta_single_pass_during_intro_retries(
    tmp_path: Path,
) -> None:
    llm_dir = tmp_path / "work" / "233541" / "llm"
    task_manifest_path = _write_task_manifest(llm_dir)
    calls = {"seo": 0, "intro": 0}

    def resolve_seo_meta(**_kwargs):
        calls["seo"] += 1
        return {
            "product": {
                "meta_description": "Περιγραφή προϊόντος.",
                "meta_keywords": ["Samsung", "WW90DB7U94GBU3"],
            }
        }

    def resolve_intro_text(**kwargs):
        calls["intro"] += 1
        return _build_intro(59 if kwargs["attempt"] == 1 else 80)

    result = execute_split_llm_stage(
        llm_dir=llm_dir,
        task_manifest_path=task_manifest_path,
        resolve_intro_text_fn=resolve_intro_text,
        resolve_seo_meta_fn=resolve_seo_meta,
    )

    assert calls == {"seo": 1, "intro": 2}
    assert result.llm_product["meta_keywords"] == ["Samsung", "WW90DB7U94GBU3"]


def test_execute_split_llm_stage_preserves_existing_seo_meta_across_intro_exhaustion(
    tmp_path: Path,
) -> None:
    llm_dir = tmp_path / "work" / "233541" / "llm"
    task_manifest_path = _write_task_manifest(llm_dir)
    existing_seo_text = '{\n  "product": {\n    "meta_description": "Υπάρχουσα περιγραφή.",\n    "meta_keywords": [\n      "LG",\n      "Example"\n    ]\n  }\n}\n'
    (llm_dir / "seo_meta.output.json").write_text(existing_seo_text, encoding="utf-8")

    def resolve_intro_text(**kwargs):
        return _build_intro(59)

    with pytest.raises(IntroTextRetryExhaustedError) as excinfo:
        execute_split_llm_stage(
            llm_dir=llm_dir,
            task_manifest_path=task_manifest_path,
            resolve_intro_text_fn=resolve_intro_text,
        )

    assert excinfo.value.failure.stage == "intro_text"
    assert excinfo.value.failure.code == INTRO_TEXT_WORD_COUNT_ERROR
    assert excinfo.value.failure.attempts == 3
    assert (llm_dir / "seo_meta.output.json").read_text(
        encoding="utf-8"
    ) == existing_seo_text
    trace = json.loads(
        (llm_dir / "intro_text.retry_trace.json").read_text(encoding="utf-8")
    )
    assert [item["status"] for item in trace] == ["retry", "retry", "failed"]


def test_execute_split_llm_stage_uses_existing_valid_outputs_without_extra_regeneration(
    tmp_path: Path,
) -> None:
    llm_dir = tmp_path / "work" / "233541" / "llm"
    task_manifest_path = _write_task_manifest(llm_dir)
    valid_intro = _build_intro(100)
    valid_seo = {
        "product": {
            "meta_description": "Υπάρχουσα έγκυρη περιγραφή.",
            "meta_keywords": ["LG", "Example"],
        }
    }
    (llm_dir / "intro_text.output.txt").write_text(valid_intro, encoding="utf-8")
    (llm_dir / "seo_meta.output.json").write_text(
        json.dumps(valid_seo, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    result = execute_split_llm_stage(
        llm_dir=llm_dir,
        task_manifest_path=task_manifest_path,
    )

    assert result.intro_text == valid_intro
    assert (
        result.seo_meta_payload["product"]["meta_description"]
        == "Υπάρχουσα έγκυρη περιγραφή."
    )
    assert (llm_dir / "intro_text.output.txt").read_text(
        encoding="utf-8"
    ) == valid_intro


def test_execute_split_llm_stage_rejects_existing_corrupted_intro_output(
    tmp_path: Path,
) -> None:
    llm_dir = tmp_path / "work" / "233541" / "llm"
    task_manifest_path = _write_task_manifest(llm_dir)
    valid_seo = {
        "product": {
            "meta_description": "Valid generated meta description.",
            "meta_keywords": ["LG", "Example"],
        }
    }
    (llm_dir / "intro_text.output.txt").write_text(
        " ".join(["Καλημέρα???"] * 100), encoding="utf-8"
    )
    (llm_dir / "seo_meta.output.json").write_text(
        json.dumps(valid_seo, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with pytest.raises(ServiceError) as excinfo:
        execute_split_llm_stage(
            llm_dir=llm_dir,
            task_manifest_path=task_manifest_path,
        )

    assert excinfo.value.code == ServiceErrorCode.VALIDATION_FAILURE.value
    assert excinfo.value.details["stage"] == "intro_text"
    assert "llm_intro_text_encoding_invalid" in excinfo.value.details["error_codes"]


def test_execute_split_llm_stage_rejects_existing_corrupted_seo_output(
    tmp_path: Path,
) -> None:
    llm_dir = tmp_path / "work" / "233541" / "llm"
    task_manifest_path = _write_task_manifest(llm_dir)
    (llm_dir / "intro_text.output.txt").write_text(_build_intro(100), encoding="utf-8")
    (llm_dir / "seo_meta.output.json").write_text(
        json.dumps(
            {
                "product": {
                    "meta_description": "Κακή περιγραφή???",
                    "meta_keywords": ["LG", "Example"],
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ServiceError) as excinfo:
        execute_split_llm_stage(
            llm_dir=llm_dir,
            task_manifest_path=task_manifest_path,
        )

    assert excinfo.value.code == ServiceErrorCode.VALIDATION_FAILURE.value
    assert excinfo.value.details["stage"] == "seo_meta"
    assert (
        "llm_seo_meta_description_encoding_invalid"
        in excinfo.value.details["error_codes"]
    )


def test_execute_split_llm_stage_rewrites_existing_bom_outputs_as_utf8(
    tmp_path: Path,
) -> None:
    llm_dir = tmp_path / "work" / "233541" / "llm"
    task_manifest_path = _write_task_manifest(llm_dir)
    valid_intro = _build_intro(100)
    valid_seo = {
        "product": {
            "meta_description": "Valid generated meta description.",
            "meta_keywords": ["LG", "Example"],
        }
    }
    intro_path = llm_dir / "intro_text.output.txt"
    seo_path = llm_dir / "seo_meta.output.json"
    intro_path.write_bytes(b"\xef\xbb\xbf" + valid_intro.encode("utf-8"))
    seo_path.write_bytes(
        b"\xef\xbb\xbf"
        + json.dumps(valid_seo, ensure_ascii=False, indent=2).encode("utf-8")
    )

    result = execute_split_llm_stage(
        llm_dir=llm_dir,
        task_manifest_path=task_manifest_path,
    )

    assert result.intro_text == valid_intro
    assert (
        result.seo_meta_payload["product"]["meta_description"]
        == valid_seo["product"]["meta_description"]
    )
    assert (
        result.seo_meta_payload["product"]["meta_keywords"]
        == valid_seo["product"]["meta_keywords"]
    )
    assert not intro_path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert not seo_path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert intro_path.read_text(encoding="utf-8") == valid_intro
    assert json.loads(seo_path.read_text(encoding="utf-8")) == valid_seo


def test_run_intro_text_with_retry_writes_output_atomically(
    tmp_path: Path, monkeypatch
) -> None:
    import product_factory.services.llm_stage_execution as llm_stage_execution

    llm_dir = tmp_path / "work" / "233541" / "llm"
    _write_task_manifest(llm_dir)
    replace_calls: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def tracking_replace(src, dst):
        replace_calls.append((Path(src), Path(dst)))
        return real_replace(src, dst)

    def resolve_intro_text(**kwargs):
        return _build_intro(59 if kwargs["attempt"] == 1 else 80)

    monkeypatch.setattr(llm_stage_execution.os, "replace", tracking_replace)

    result = run_intro_text_with_retry(
        intro_text_context_path=llm_dir / "intro_text.context.json",
        intro_text_prompt_path=llm_dir / "intro_text.prompt.txt",
        intro_text_output_path=llm_dir / "intro_text.output.txt",
        resolve_intro_text_fn=resolve_intro_text,
    )

    assert len(result.split()) == 80
    assert any(dst == llm_dir / "intro_text.output.txt" for _, dst in replace_calls)
    assert not list(llm_dir.glob("intro_text.output.txt.*.tmp"))
