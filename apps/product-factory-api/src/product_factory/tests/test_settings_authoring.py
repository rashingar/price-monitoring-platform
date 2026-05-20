from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from product_factory import repo_paths
from product_factory.llm_contract import (
    INTRO_MAX_WORDS,
    INTRO_MIN_WORDS,
    build_intro_text_context,
    validate_intro_text_output,
)
from product_factory.models import (
    CLIInput,
    ParsedProduct,
    SourceProductData,
    TaxonomyResolution,
)
from product_factory.services.authoring_service import (
    PreparedAuthoringArtifactsNotFoundError,
    get_authoring_status,
    run_intro_text_authoring,
    run_seo_meta_authoring,
)
from product_factory.services.llm_stage_execution import (
    SplitLLMStageResult,
    SplitLLMTaskPaths,
)
from product_factory.services.render_execution import (
    _build_llm_validation_backstop_errors,
)
from product_factory.services.settings_service import (
    IntroTextPolicy,
    ProductFactorySettingsError,
    get_intro_text_policy,
    load_product_factory_settings,
)
from product_factory.utils import write_json

MODEL = "999001"


def _build_intro(words: int) -> str:
    return " ".join(["λέξη"] * words)


@pytest.fixture()
def isolated_repo(tmp_path: Path, monkeypatch):
    settings_path = (
        tmp_path / "resources" / "settings" / "product_factory_settings.json"
    )
    monkeypatch.setattr(repo_paths, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(repo_paths, "RESOURCES_DIR", tmp_path / "resources")
    monkeypatch.setattr(repo_paths, "SETTINGS_DIR", tmp_path / "resources" / "settings")
    monkeypatch.setattr(repo_paths, "PRODUCT_FACTORY_SETTINGS_PATH", settings_path)
    return tmp_path


def _write_settings(
    path: Path,
    *,
    min_words=80,
    max_words=180,
    max_attempts=3,
    max_emphasized_words_percent=35,
    max_chars=260,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        path,
        {
            "schema_version": 1,
            "authoring": {
                "intro_text": {
                    "default": {
                        "min_words": min_words,
                        "max_words": max_words,
                        "max_attempts": max_attempts,
                        "max_emphasized_words_percent": max_emphasized_words_percent,
                    },
                    "by_source": {"electronet": {"default": {"min_words": 90}}},
                    "by_category": {"cat-1": {"default": {"max_words": 120}}},
                },
                "seo_meta": {
                    "default": {"meta_description_max_chars": max_chars},
                    "by_source": {},
                    "by_category": {},
                },
            },
        },
    )


def _write_prepared_authoring_artifacts(repo_root: Path, model: str = MODEL) -> Path:
    model_root = repo_root / "work" / model
    scrape_dir = model_root / "scrape"
    llm_dir = model_root / "llm"
    scrape_dir.mkdir(parents=True)
    llm_dir.mkdir(parents=True)
    write_json(
        scrape_dir / f"{model}.source.json",
        {"source_name": "electronet", "brand": "LG", "name": "Example"},
    )
    write_json(
        scrape_dir / f"{model}.normalized.json",
        {
            "taxonomy": {"category_id": "cat-1", "leaf_category": "Ψυγεία"},
            "schema_match": {"schema_id": "schema-1"},
            "input": {
                "model": model,
                "url": "https://example.test",
                "photos": 1,
                "sections": 0,
            },
        },
    )
    write_json(
        llm_dir / "task_manifest.json",
        {
            "primary_outputs": {
                "tasks": {
                    "intro_text": {
                        "context_path": str(llm_dir / "intro_text.context.json"),
                        "prompt_path": str(llm_dir / "intro_text.prompt.txt"),
                        "expected_output_path": str(llm_dir / "intro_text.output.txt"),
                    },
                    "seo_meta": {
                        "context_path": str(llm_dir / "seo_meta.context.json"),
                        "prompt_path": str(llm_dir / "seo_meta.prompt.txt"),
                        "expected_output_path": str(llm_dir / "seo_meta.output.json"),
                    },
                }
            }
        },
    )
    write_json(llm_dir / "intro_text.context.json", {})
    (llm_dir / "intro_text.prompt.txt").write_text("intro prompt", encoding="utf-8")
    write_json(llm_dir / "seo_meta.context.json", {})
    (llm_dir / "seo_meta.prompt.txt").write_text("seo prompt", encoding="utf-8")
    return model_root


def test_missing_settings_file_loads_defaults(isolated_repo: Path) -> None:
    settings = load_product_factory_settings()

    assert settings.intro_text_default.min_words == INTRO_MIN_WORDS
    assert settings.intro_text_default.max_words == INTRO_MAX_WORDS
    assert settings.intro_text_default.max_attempts == 3
    assert settings.intro_text_default.max_emphasized_words_percent == 35


def test_existing_settings_file_loads_valid_values(isolated_repo: Path) -> None:
    _write_settings(
        repo_paths.PRODUCT_FACTORY_SETTINGS_PATH,
        min_words=60,
        max_words=140,
        max_attempts=5,
        max_emphasized_words_percent=45,
    )

    policy = get_intro_text_policy()

    assert policy == IntroTextPolicy(
        min_words=60,
        max_words=140,
        max_attempts=5,
        max_emphasized_words_percent=45,
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"min_words": 0}, "min_words"),
        ({"max_words": 0}, "max_words"),
        ({"min_words": 120, "max_words": 100}, "greater than or equal"),
        ({"max_words": 501}, "less than or equal to 500"),
        ({"max_attempts": 0}, "between 1 and 10"),
        ({"max_attempts": 11}, "between 1 and 10"),
        ({"max_emphasized_words_percent": -1}, "between 0 and 100"),
        ({"max_emphasized_words_percent": 101}, "between 0 and 100"),
    ],
)
def test_invalid_settings_are_rejected(
    isolated_repo: Path, overrides: dict[str, int], message: str
) -> None:
    values = {"min_words": 80, "max_words": 180, "max_attempts": 3, **overrides}
    _write_settings(repo_paths.PRODUCT_FACTORY_SETTINGS_PATH, **values)

    with pytest.raises(ProductFactorySettingsError, match=message):
        load_product_factory_settings()


def test_settings_api_get_and_patch_preserves_override_keys(
    isolated_repo: Path,
) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    _write_settings(repo_paths.PRODUCT_FACTORY_SETTINGS_PATH)
    client = fastapi_testclient.TestClient(create_app())

    get_response = client.get("/api/settings")
    patch_response = client.patch(
        "/api/settings",
        json={
            "authoring": {
                "intro_text": {
                    "default": {
                        "min_words": 70,
                        "max_words": 150,
                        "max_emphasized_words_percent": 40,
                    }
                }
            }
        },
    )

    assert get_response.status_code == 200
    assert patch_response.status_code == 200
    body = patch_response.json()
    assert body["authoring"]["intro_text"]["default"]["min_words"] == 70
    assert body["authoring"]["intro_text"]["default"]["max_words"] == 150
    assert (
        body["authoring"]["intro_text"]["default"]["max_emphasized_words_percent"] == 40
    )
    assert "by_source" in body["authoring"]["intro_text"]
    assert "by_category" in body["authoring"]["intro_text"]


def test_build_intro_text_context_uses_configured_word_range() -> None:
    context = build_intro_text_context(
        cli=CLIInput(model="1", url="https://example.test"),
        parsed=ParsedProduct(source=SourceProductData(name="Product")),
        taxonomy=TaxonomyResolution(leaf_category="Category"),
        deterministic_product={},
        intro_policy=IntroTextPolicy(
            min_words=40, max_words=90, max_attempts=2, max_emphasized_words_percent=45
        ),
    )

    assert context["writer_rules"]["word_count_range"] == {"min": 40, "max": 90}
    assert (
        context["writer_rules"]["emphasis_policy"]["max_emphasized_word_ratio"] == 0.45
    )


def test_validate_intro_text_output_uses_configured_range_and_defaults_remain() -> None:
    _, configured_errors = validate_intro_text_output(
        _build_intro(50), intro_word_min=40, intro_word_max=90
    )
    _, default_errors = validate_intro_text_output(_build_intro(INTRO_MIN_WORDS))

    assert configured_errors == []
    assert default_errors == []


def test_render_llm_backstop_uses_configured_intro_range(tmp_path: Path) -> None:
    task_paths = SplitLLMTaskPaths(
        intro_text_context_path=tmp_path / "intro_text.context.json",
        intro_text_prompt_path=tmp_path / "intro_text.prompt.txt",
        intro_text_output_path=tmp_path / "intro_text.output.txt",
        intro_text_trace_path=tmp_path / "intro_text.retry_trace.json",
        seo_meta_context_path=tmp_path / "seo_meta.context.json",
        seo_meta_prompt_path=tmp_path / "seo_meta.prompt.txt",
        seo_meta_output_path=tmp_path / "seo_meta.output.json",
    )
    result = SplitLLMStageResult(
        intro_text=_build_intro(50),
        seo_meta_payload={
            "product": {
                "meta_description": "Έγκυρη περιγραφή προϊόντος.",
                "meta_keywords": ["LG", "Example"],
            }
        },
        task_paths=task_paths,
    )

    assert (
        _build_llm_validation_backstop_errors(
            result,
            intro_policy=IntroTextPolicy(min_words=40, max_words=90, max_attempts=2),
        )
        == []
    )


def test_get_authoring_status_requires_prepared_artifacts(isolated_repo: Path) -> None:
    with pytest.raises(
        PreparedAuthoringArtifactsNotFoundError, match="Run prepare first"
    ):
        get_authoring_status(MODEL)


def test_get_authoring_status_reports_missing_and_valid_outputs(
    isolated_repo: Path,
) -> None:
    model_root = _write_prepared_authoring_artifacts(isolated_repo)
    status = get_authoring_status(MODEL)

    assert status.intro_text.status == "missing"
    assert status.seo_meta.status == "missing"
    assert status.ready_for_render is False

    (model_root / "llm" / "intro_text.output.txt").write_text(
        _build_intro(100), encoding="utf-8"
    )
    write_json(
        model_root / "llm" / "seo_meta.output.json",
        {
            "product": {
                "meta_description": "Έγκυρη περιγραφή προϊόντος.",
                "meta_keywords": ["LG", "Example"],
            }
        },
    )
    status = get_authoring_status(MODEL)

    assert status.intro_text.status == "valid"
    assert status.intro_text.word_count == 100
    assert status.intro_text.visible_word_count == 100
    assert status.intro_text.emphasis_warning_codes == [
        "llm_intro_text_emphasis_missing"
    ]
    assert status.intro_text.strong_span_count == 0
    assert status.seo_meta.status == "valid"
    assert status.ready_for_render is True


def test_get_authoring_status_reports_invalid_outputs(isolated_repo: Path) -> None:
    model_root = _write_prepared_authoring_artifacts(isolated_repo)
    (model_root / "llm" / "intro_text.output.txt").write_text(
        _build_intro(10), encoding="utf-8"
    )
    write_json(
        model_root / "llm" / "seo_meta.output.json",
        {"product": {"meta_description": "bad", "meta_keywords": "csv"}},
    )

    status = get_authoring_status(MODEL)

    assert status.intro_text.status == "invalid"
    assert "llm_intro_text_word_count_invalid" in status.intro_text.errors
    assert status.seo_meta.status == "invalid"
    assert "llm_seo_meta_keywords_invalid" in status.seo_meta.errors


def test_intro_authoring_retry_rewrites_only_intro_and_uses_configured_policy(
    isolated_repo: Path,
) -> None:
    _write_settings(
        repo_paths.PRODUCT_FACTORY_SETTINGS_PATH,
        min_words=5,
        max_words=6,
        max_attempts=2,
    )
    model_root = _write_prepared_authoring_artifacts(isolated_repo)
    llm_dir = model_root / "llm"
    (llm_dir / "intro_text.output.txt").write_text(_build_intro(5), encoding="utf-8")
    write_json(
        llm_dir / "seo_meta.output.json",
        {"product": {"meta_description": "Έγκυρη περιγραφή.", "meta_keywords": ["LG"]}},
    )
    seo_before = (llm_dir / "seo_meta.output.json").read_text(encoding="utf-8")
    time.sleep(0.01)

    status = run_intro_text_authoring(
        MODEL,
        retry=True,
        resolve_intro_text_fn=lambda **kwargs: _build_intro(6),
    )

    assert status.intro_text.status == "valid"
    assert status.intro_text.min_words == 5
    assert status.intro_text.max_words == 6
    assert status.intro_text.max_attempts == 2
    assert (llm_dir / "intro_text.output.txt").read_text(
        encoding="utf-8"
    ) == _build_intro(6)
    assert (llm_dir / "seo_meta.output.json").read_text(encoding="utf-8") == seo_before


def test_seo_authoring_retry_rewrites_only_seo(isolated_repo: Path) -> None:
    model_root = _write_prepared_authoring_artifacts(isolated_repo)
    llm_dir = model_root / "llm"
    intro = _build_intro(100)
    (llm_dir / "intro_text.output.txt").write_text(intro, encoding="utf-8")
    write_json(
        llm_dir / "seo_meta.output.json",
        {"product": {"meta_description": "Old.", "meta_keywords": ["Old"]}},
    )

    status = run_seo_meta_authoring(
        MODEL,
        retry=True,
        resolve_seo_meta_fn=lambda **kwargs: {
            "product": {
                "meta_description": "Νέα έγκυρη περιγραφή προϊόντος.",
                "meta_keywords": ["LG", "New"],
            }
        },
    )

    assert status.seo_meta.status == "valid"
    assert (llm_dir / "intro_text.output.txt").read_text(encoding="utf-8") == intro
    assert json.loads((llm_dir / "seo_meta.output.json").read_text(encoding="utf-8"))[
        "product"
    ]["meta_keywords"] == ["LG", "New"]


def test_authoring_api_routes_are_included_and_queue_jobs(isolated_repo: Path) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app
    from product_factory.jobs.runner import SequentialJobRunner
    from product_factory.jobs.store import JobStore

    _write_prepared_authoring_artifacts(isolated_repo)
    store = JobStore(isolated_repo / "jobs")
    runner = SequentialJobRunner(store, lambda record, log: None)
    client = fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    )

    try:
        assert client.get(f"/api/authoring/{MODEL}").status_code == 200
        assert client.post(f"/api/authoring/{MODEL}/intro-text").status_code == 202
        assert (
            client.post(f"/api/authoring/{MODEL}/intro-text/retry").status_code == 202
        )
        assert client.post(f"/api/authoring/{MODEL}/seo-meta").status_code == 202
        assert client.post(f"/api/authoring/{MODEL}/seo-meta/retry").status_code == 202
        assert client.get("/api/authoring/missing").status_code == 404
    finally:
        runner.stop()
