from pathlib import Path

import pytest

from product_factory.services import RunArtifacts, RunMetadata, RunStatus, RunType, ServiceResult
from product_factory.services import metadata as metadata_module
from product_factory.services.metadata import MetadataWriteError


def test_write_run_metadata_returns_metadata_path_and_serializes_payload(tmp_path: Path, monkeypatch) -> None:
    metadata_path = tmp_path / "work" / "233541" / "prepare.run.json"
    captured: dict[str, object] = {}

    def fake_write_json(path: Path, payload: object) -> None:
        captured["path"] = path
        captured["payload"] = payload

    monkeypatch.setattr(metadata_module, "write_json", fake_write_json)

    result = ServiceResult(
        run=RunMetadata(
            model="233541",
            run_type=RunType.PREPARE,
            status=RunStatus.COMPLETED,
            warnings=["prepare warning"],
        ),
        artifacts=RunArtifacts(
            model_root=tmp_path / "work" / "233541",
            scrape_dir=tmp_path / "work" / "233541" / "scrape",
            metadata_path=metadata_path,
        ),
        details={"llm_prepare_mode": "split_tasks"},
    )

    returned_path = metadata_module.write_run_metadata(result)

    assert returned_path == metadata_path
    assert captured["path"] == metadata_path
    assert captured["payload"] == {
        "run": {
            "model": "233541",
            "run_type": "prepare",
            "status": "completed",
            "schema_version": "1.0",
            "run_id": "",
            "requested_at": None,
            "started_at": None,
            "finished_at": None,
            "context": {},
            "warnings": ["prepare warning"],
            "error_code": None,
            "error_detail": None,
        },
        "artifacts": {
            "model_root": str(tmp_path / "work" / "233541"),
            "scrape_dir": str(tmp_path / "work" / "233541" / "scrape"),
            "llm_dir": None,
            "candidate_dir": None,
            "raw_html_path": None,
            "source_json_path": None,
            "scrape_normalized_json_path": None,
            "source_report_json_path": None,
            "llm_task_manifest_path": None,
            "intro_text_context_path": None,
            "intro_text_prompt_path": None,
            "intro_text_output_path": None,
            "seo_meta_context_path": None,
            "seo_meta_prompt_path": None,
            "seo_meta_output_path": None,
            "candidate_csv_path": None,
            "published_csv_path": None,
            "candidate_normalized_json_path": None,
            "validation_report_path": None,
            "description_html_path": None,
            "characteristics_html_path": None,
            "category_filter_review_path": None,
            "metadata_path": str(metadata_path),
        },
        "details": {
            "llm_prepare_mode": "split_tasks",
        },
    }


def test_write_run_metadata_requires_metadata_path(tmp_path: Path) -> None:
    result = ServiceResult(
        run=RunMetadata(model="233541", run_type=RunType.PREPARE),
        artifacts=RunArtifacts(model_root=tmp_path / "work" / "233541"),
    )

    with pytest.raises(ValueError) as excinfo:
        metadata_module.write_run_metadata(result)

    assert str(excinfo.value) == "Run metadata path is required"


def test_maybe_write_run_metadata_builds_service_result_payload_for_write(tmp_path: Path, monkeypatch) -> None:
    model_root = tmp_path / "work" / "233541"
    artifacts = RunArtifacts(model_root=model_root, scrape_dir=model_root / "scrape")
    captured: dict[str, object] = {}

    def fake_write_run_metadata(result: ServiceResult) -> Path:
        captured["result"] = result
        return result.artifacts.metadata_path

    monkeypatch.setattr(metadata_module, "write_run_metadata", fake_write_run_metadata)

    returned_path = metadata_module.maybe_write_run_metadata(
        model="233541",
        run_type=RunType.PREPARE,
        status=RunStatus.FAILED,
        model_root=model_root,
        artifacts=artifacts,
        requested_at="2026-03-31T10:00:00Z",
        started_at="2026-03-31T10:00:01Z",
        finished_at="2026-03-31T10:00:02Z",
        warnings=["metadata warning"],
        error_code="unexpected_failure",
        error_detail="prepare exploded",
        details={"llm_prepare_mode": "split_tasks"},
    )

    assert returned_path == model_root / "prepare.run.json"
    assert artifacts.metadata_path == model_root / "prepare.run.json"

    payload = captured["result"]
    assert isinstance(payload, ServiceResult)
    assert payload.run == RunMetadata(
        model="233541",
        run_type=RunType.PREPARE,
        status=RunStatus.FAILED,
        requested_at="2026-03-31T10:00:00Z",
        started_at="2026-03-31T10:00:01Z",
        finished_at="2026-03-31T10:00:02Z",
        warnings=["metadata warning"],
        error_code="unexpected_failure",
        error_detail="prepare exploded",
    )
    assert payload.artifacts is artifacts
    assert payload.details == {"llm_prepare_mode": "split_tasks"}


def test_maybe_write_run_metadata_raises_structured_write_failure(tmp_path: Path, monkeypatch) -> None:
    model_root = tmp_path / "work" / "233541"
    artifacts = RunArtifacts(model_root=model_root, scrape_dir=model_root / "scrape")

    def fake_write_run_metadata(_result: ServiceResult) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(metadata_module, "write_run_metadata", fake_write_run_metadata)

    with pytest.raises(MetadataWriteError) as excinfo:
        metadata_module.maybe_write_run_metadata(
            model="233541",
            run_type=RunType.RENDER,
            status=RunStatus.COMPLETED,
            model_root=model_root,
            artifacts=artifacts,
            requested_at="2026-03-31T10:00:00Z",
            started_at="2026-03-31T10:00:01Z",
            finished_at="2026-03-31T10:00:02Z",
            warnings=["render warning"],
            details={"validation_ok": True},
        )

    error = excinfo.value
    assert str(error) == f"Failed to write render run metadata at {model_root / 'render.run.json'}: disk full"
    assert error.metadata_path == model_root / "render.run.json"
    assert error.payload.run.model == "233541"
    assert error.payload.run.run_type == RunType.RENDER
    assert error.payload.run.status == RunStatus.COMPLETED
    assert error.payload.run.warnings == ["render warning"]
    assert error.payload.details == {"validation_ok": True}
    assert isinstance(error.cause, OSError)
    assert artifacts.metadata_path == model_root / "render.run.json"
