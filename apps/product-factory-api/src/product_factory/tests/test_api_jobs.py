from __future__ import annotations

from pathlib import Path

import pytest

from product_factory.api.artifact_resolver import resolve_job_artifacts
from product_factory.jobs.models import JobRecord, JobStatus, JobType
from product_factory.jobs.runner import (
    LogCallback,
    SequentialJobRunner,
    run_authoring_intro_job,
    run_authoring_seo_job,
)
from product_factory.jobs.store import JobStore
from product_factory.services.authoring_service import (
    AuthoringStatus,
    IntroTextTaskStatus,
    PreparedAuthoringArtifactsNotFoundError,
    SeoMetaTaskStatus,
)
from product_factory.services.errors import ServiceError, ServiceErrorCode


def test_prepare_route_enqueues_job_and_exposes_logs_and_artifacts(
    tmp_path: Path,
) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")

    def fake_callback(record: JobRecord, log: LogCallback) -> None:
        log(f"fake callback for {record.job_id}")
        store.update_artifacts(
            record.job_id,
            {
                "source_json_path": tmp_path
                / "work"
                / record.model
                / "scrape"
                / f"{record.model}.source.json"
            },
        )

    runner = SequentialJobRunner(store, fake_callback)
    app = create_app(job_store=store, job_runner=runner)
    client = fastapi_testclient.TestClient(app)

    try:
        response = client.post(
            "/api/jobs/prepare",
            json={
                "model": "999001",
                "url": "https://www.electronet.gr/example",
                "photos": 6,
                "sections": 2,
                "skroutz_status": 1,
                "boxnow": 0,
                "price": "2099",
                "gallery_url": "https://www.electronet.gr/gallery",
                "characteristics_url": "https://www.electronet.gr/specs",
                "second_opencart_image_index": 4,
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        queued_payload = store.get_job(job_id).payload
        assert queued_payload["bestprice_status"] == 1
        assert queued_payload["gallery_url"] == "https://www.electronet.gr/gallery"
        assert (
            queued_payload["characteristics_url"] == "https://www.electronet.gr/specs"
        )
        assert queued_payload["second_opencart_image_index"] == 4

        assert runner.wait_until_idle(timeout=2.0)

        job_response = client.get(f"/api/jobs/{job_id}")
        logs_response = client.get(f"/api/jobs/{job_id}/logs")
        artifacts_response = client.get(f"/api/jobs/{job_id}/artifacts")
    finally:
        runner.stop()

    assert job_response.status_code == 200
    assert job_response.json()["status"] == JobStatus.SUCCEEDED.value
    assert logs_response.status_code == 200
    assert f"fake callback for {job_id}" in logs_response.json()["lines"]
    assert artifacts_response.status_code == 200
    assert artifacts_response.json()["artifacts"] == [
        {
            "name": "source_json_path",
            "path": str(tmp_path / "work" / "999001" / "scrape" / "999001.source.json"),
            "kind": None,
            "content_type": None,
            "content": None,
        }
    ]


def test_prepare_route_accepts_legacy_payload_and_rejects_invalid_second_image_index(
    tmp_path: Path,
) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(store, lambda _record, _log: None)
    client = fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    )

    try:
        legacy_response = client.post(
            "/api/jobs/prepare",
            json={
                "model": "999001",
                "url": "https://www.electronet.gr/example",
                "photos": 1,
                "sections": 0,
                "skroutz_status": 0,
                "boxnow": 0,
                "price": 0,
            },
        )
        invalid_response = client.post(
            "/api/jobs/prepare",
            json={
                "model": "999002",
                "url": "https://www.electronet.gr/example",
                "second_opencart_image_index": 0,
            },
        )
    finally:
        runner.stop()

    assert legacy_response.status_code == 202
    assert (
        store.get_job(legacy_response.json()["job_id"]).payload.get("gallery_url")
        is None
    )
    assert (
        store.get_job(legacy_response.json()["job_id"]).payload["bestprice_status"] == 1
    )
    assert (
        store.get_job(legacy_response.json()["job_id"]).payload.get(
            "characteristics_url"
        )
        is None
    )
    assert (
        store.get_job(legacy_response.json()["job_id"]).payload.get("gallery_mode")
        is None
    )
    assert invalid_response.status_code == 422


def test_authoring_routes_enqueue_job_responses_and_preserve_model(
    tmp_path: Path,
) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(
        store, lambda record, log: log(f"queued {record.job_type.value}")
    )
    client = fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    )

    try:
        responses = [
            client.post("/api/authoring/000001/intro-text"),
            client.post("/api/authoring/000001/intro-text/retry"),
            client.post("/api/authoring/000001/seo-meta"),
            client.post("/api/authoring/000001/seo-meta/retry"),
        ]
        canonical_intro = client.post(
            "/api/jobs/authoring/intro-text", json={"model": "000001"}
        )
        canonical_seo = client.post(
            "/api/jobs/authoring/seo-meta", json={"model": "000001", "retry": True}
        )
    finally:
        runner.stop()

    assert [response.status_code for response in responses] == [202, 202, 202, 202]
    assert [response.json()["job_type"] for response in responses] == [
        "authoring_intro",
        "authoring_intro",
        "authoring_seo",
        "authoring_seo",
    ]
    assert all(
        response.json()["job_id"].startswith("000001-authoring_")
        for response in responses
    )
    assert all(response.json()["model"] == "000001" for response in responses)
    assert canonical_intro.status_code == 202
    assert canonical_intro.json()["job_type"] == "authoring_intro"
    assert canonical_seo.status_code == 202
    assert canonical_seo.json()["job_type"] == "authoring_seo"


def test_authoring_get_remains_read_status_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory import repo_paths
    from product_factory.api.app import create_app

    monkeypatch.setattr(repo_paths, "REPO_ROOT", tmp_path)
    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(store)
    client = fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    )

    try:
        response = client.get("/api/authoring/missing-model")
    finally:
        runner.stop()

    assert response.status_code == 404
    assert "Run prepare first" in response.json()["detail"]
    assert store.list_jobs() == []


def test_full_pipeline_route_enqueues_defaults_and_preserves_listing_flags(
    tmp_path: Path,
) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(
        store, lambda record, log: log(f"queued {record.job_type.value}")
    )
    client = fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    )
    source_url = "https://www.electronet.gr/example"

    try:
        response = client.post(
            "/api/jobs/full-pipeline",
            json={
                "model": "000001",
                "product_name": "Example product",
                "source_url": source_url,
                "skroutz_status": 1,
                "boxnow": 0,
                "trigger_source": "telegram",
                "telegram_chat_id": "12345",
                "source_resolution": {"candidate_id": "abc"},
            },
        )
        assert runner.wait_until_idle(timeout=2.0)
    finally:
        runner.stop()

    assert response.status_code == 202
    body = response.json()
    record = store.get_job(body["job_id"])
    assert body["job_type"] == JobType.FULL_PIPELINE.value
    assert record.payload["source_url"] == source_url
    assert record.payload["bestprice_status"] == 1
    assert record.payload["skroutz_status"] == 1
    assert record.payload["boxnow"] == 0
    assert record.payload["photos"] == 100
    assert record.payload["sections"] == 20
    assert record.payload["gallery_mode"] == "all"
    assert record.payload["source_resolution"] == {"candidate_id": "abc"}


def test_full_pipeline_route_preserves_explicit_disabled_bestprice_status(
    tmp_path: Path,
) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(store, lambda record, log: None)
    client = fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    )

    try:
        response = client.post(
            "/api/jobs/full-pipeline",
            json={
                "model": "000001",
                "source_url": "https://www.electronet.gr/example",
                "bestprice_status": 0,
            },
        )
    finally:
        runner.stop()

    assert response.status_code == 202
    record = store.get_job(response.json()["job_id"])
    assert record.payload["bestprice_status"] == 0


def test_prepare_and_full_pipeline_routes_reject_invalid_status_values(
    tmp_path: Path,
) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(store, lambda record, log: None)
    client = fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    )

    try:
        prepare_response = client.post(
            "/api/jobs/prepare",
            json={
                "model": "999001",
                "url": "https://www.electronet.gr/example",
                "bestprice_status": "maybe",
            },
        )
        full_pipeline_response = client.post(
            "/api/jobs/full-pipeline",
            json={
                "model": "000001",
                "source_url": "https://www.electronet.gr/example",
                "bestprice_status": 2,
            },
        )
    finally:
        runner.stop()

    assert prepare_response.status_code == 422
    assert full_pipeline_response.status_code == 422


def test_retry_requeues_failed_full_pipeline_from_prepared_artifacts(
    tmp_path: Path,
) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(
        store, lambda record, log: log(f"queued {record.job_type.value}")
    )
    payload = {
        "model": "233541",
        "source_url": "https://www.electronet.gr/example",
        "bestprice_status": 0,
        "skroutz_status": 1,
        "boxnow": 1,
        "photos": 100,
        "sections": 20,
        "gallery_mode": "all",
        "source_resolution": {"source": "operator"},
    }
    failed = store.enqueue(JobType.FULL_PIPELINE, payload, job_id="job-1")
    store.mark_failed(
        failed.job_id, "publish failed", message="Full pipeline failed during publish."
    )
    client = fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    )

    try:
        response = client.post(f"/api/jobs/{failed.job_id}/retry")
    finally:
        runner.stop()

    assert response.status_code == 200
    retried = store.get_job(response.json()["job_id"])
    assert response.json()["job_type"] == JobType.FULL_PIPELINE.value
    assert retried.payload == {
        **payload,
        "retry_source_job_id": failed.job_id,
        "retry_mode": "from_prepared_artifacts",
        "skip_prepare": True,
    }


def test_start_requeues_terminal_full_pipeline_from_scratch_without_retry_metadata(
    tmp_path: Path,
) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(
        store, lambda record, log: log(f"queued {record.job_type.value}")
    )
    payload = {
        "model": "233541",
        "source_url": "https://www.electronet.gr/example",
        "bestprice_status": 0,
        "skroutz_status": 1,
        "boxnow": 1,
        "photos": 100,
        "sections": 20,
        "gallery_mode": "all",
        "source_resolution": {"source": "operator"},
        "retry_source_job_id": "job-original",
        "retry_mode": "from_prepared_artifacts",
        "skip_prepare": True,
    }
    failed = store.enqueue(JobType.FULL_PIPELINE, payload, job_id="job-1")
    store.mark_failed(
        failed.job_id, "render failed", message="Full pipeline failed during render."
    )
    client = fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    )

    try:
        response = client.post(f"/api/jobs/{failed.job_id}/start")
    finally:
        runner.stop()

    assert response.status_code == 200
    started = store.get_job(response.json()["job_id"])
    assert response.json()["job_type"] == JobType.FULL_PIPELINE.value
    assert started.payload == {
        "model": "233541",
        "source_url": "https://www.electronet.gr/example",
        "bestprice_status": 0,
        "skroutz_status": 1,
        "boxnow": 1,
        "photos": 100,
        "sections": 20,
        "gallery_mode": "all",
        "source_resolution": {"source": "operator"},
    }


def test_retry_and_start_reject_active_or_missing_jobs(tmp_path: Path) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(store, lambda record, log: None)
    active = store.enqueue(
        JobType.FULL_PIPELINE,
        {"model": "233541", "source_url": "https://www.electronet.gr/example"},
        job_id="job-1",
    )
    client = fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    )

    try:
        retry_active = client.post(f"/api/jobs/{active.job_id}/retry")
        start_active = client.post(f"/api/jobs/{active.job_id}/start")
        retry_missing = client.post("/api/jobs/missing/retry")
        start_missing = client.post("/api/jobs/missing/start")
    finally:
        runner.stop()

    assert retry_active.status_code == 409
    assert start_active.status_code == 409
    assert retry_missing.status_code == 404
    assert start_missing.status_code == 404


def test_start_rejects_non_full_pipeline_jobs_intentionally(tmp_path: Path) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(store, lambda record, log: None)
    record = store.enqueue(JobType.RENDER, {"model": "233541"}, job_id="job-1")
    store.mark_failed(record.job_id, "validation failed", message="Render job failed.")
    client = fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    )

    try:
        response = client.post(f"/api/jobs/{record.job_id}/start")
    finally:
        runner.stop()

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Start from scratch is supported only for full_pipeline jobs."
    )


def test_start_rejects_full_pipeline_with_missing_original_payload_fields(
    tmp_path: Path,
) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(store, lambda record, log: None)
    record = store.enqueue(JobType.FULL_PIPELINE, {"model": "233541"}, job_id="job-1")
    store.mark_failed(record.job_id, "bad payload", message="Full pipeline failed.")
    client = fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    )

    try:
        response = client.post(f"/api/jobs/{record.job_id}/start")
    finally:
        runner.stop()

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Full pipeline job payload is missing source_url; cannot start job."
    )


def test_authoring_intro_runner_dispatches_and_exposes_preview_artifacts(
    tmp_path: Path,
) -> None:
    llm_dir = tmp_path / "work" / "000001" / "llm"
    llm_dir.mkdir(parents=True)
    (llm_dir / "intro_text.output.txt").write_text(
        "Intro <strong>preview</strong> text.", encoding="utf-8"
    )
    (llm_dir / "task_manifest.json").write_text("{}\n", encoding="utf-8")
    record = JobRecord(
        job_id="000001-authoring_intro-test",
        job_type=JobType.AUTHORING_INTRO,
        status=JobStatus.RUNNING,
        model="000001",
        payload={"model": "000001", "retry": True},
    )
    calls: list[tuple[str, bool]] = []

    result = run_authoring_intro_job(
        record,
        lambda line: None,
        run_intro_text_authoring_fn=lambda model, retry=False: calls.append(
            (model, retry)
        )
        or _authoring_status(llm_dir),
    )

    assert calls == [("000001", True)]
    assert result.status == JobStatus.SUCCEEDED
    assert result.artifacts["intro_text_preview_path"] == str(
        llm_dir / "intro_text.preview.html"
    )
    assert (llm_dir / "intro_text.preview.html").read_text(
        encoding="utf-8"
    ) == "Intro <strong>preview</strong> text."


def test_authoring_seo_runner_dispatches_independently_of_failed_intro(
    tmp_path: Path,
) -> None:
    llm_dir = tmp_path / "work" / "000001" / "llm"
    llm_dir.mkdir(parents=True)
    (llm_dir / "seo_meta.output.json").write_text(
        '{"product":{"meta_description":"Description","meta_keywords":["a","b"]}}\n',
        encoding="utf-8",
    )
    intro_record = JobRecord(
        job_id="000001-authoring_intro-test",
        job_type=JobType.AUTHORING_INTRO,
        status=JobStatus.RUNNING,
        model="000001",
        payload={"model": "000001"},
    )
    seo_record = JobRecord(
        job_id="000001-authoring_seo-test",
        job_type=JobType.AUTHORING_SEO,
        status=JobStatus.RUNNING,
        model="000001",
        payload={"model": "000001"},
    )

    intro_result = run_authoring_intro_job(
        intro_record,
        lambda line: None,
        run_intro_text_authoring_fn=lambda model, retry=False: (_ for _ in ()).throw(
            ServiceError(
                ServiceErrorCode.VALIDATION_FAILURE.value,
                "invalid intro",
                details={"error_code": "bad_intro"},
            )
        ),
    )
    seo_result = run_authoring_seo_job(
        seo_record,
        lambda line: None,
        run_seo_meta_authoring_fn=lambda model, retry=False: _authoring_status(llm_dir),
    )

    assert intro_result.status == JobStatus.FAILED
    assert intro_result.error_code == "bad_intro"
    assert seo_result.status == JobStatus.SUCCEEDED
    assert seo_result.artifacts["seo_meta_preview_path"] == str(
        llm_dir / "seo_meta.preview.json"
    )
    assert "Description" in (llm_dir / "seo_meta.preview.json").read_text(
        encoding="utf-8"
    )


def test_authoring_intro_runner_reports_missing_prepared_artifacts_as_structured_failure() -> (
    None
):
    record = JobRecord(
        job_id="000001-authoring_intro-test",
        job_type=JobType.AUTHORING_INTRO,
        status=JobStatus.RUNNING,
        model="000001",
        payload={"model": "000001"},
    )
    logs: list[str] = []

    result = run_authoring_intro_job(
        record,
        logs.append,
        run_intro_text_authoring_fn=lambda model, retry=False: (_ for _ in ()).throw(
            PreparedAuthoringArtifactsNotFoundError(
                f"Prepared authoring artifacts not found for model {model}. Run prepare first."
            )
        ),
    )

    assert result.status == JobStatus.FAILED
    assert result.error_code == ServiceErrorCode.MISSING_ARTIFACT.value
    assert "Run prepare first" in str(result.error)
    assert any("missing_artifact" in line for line in logs)


def test_authoring_intro_runner_reports_service_error_without_throwing() -> None:
    record = JobRecord(
        job_id="000001-authoring_intro-test",
        job_type=JobType.AUTHORING_INTRO,
        status=JobStatus.RUNNING,
        model="000001",
        payload={"model": "000001"},
    )

    result = run_authoring_intro_job(
        record,
        lambda line: None,
        run_intro_text_authoring_fn=lambda model, retry=False: (_ for _ in ()).throw(
            ServiceError(ServiceErrorCode.PROVIDER_FAILURE.value, "provider failed")
        ),
    )

    assert result.status == JobStatus.FAILED
    assert result.error == "provider failed"
    assert result.error_code == ServiceErrorCode.PROVIDER_FAILURE.value


def test_authoring_seo_runner_reports_unexpected_error_without_throwing() -> None:
    record = JobRecord(
        job_id="000001-authoring_seo-test",
        job_type=JobType.AUTHORING_SEO,
        status=JobStatus.RUNNING,
        model="000001",
        payload={"model": "000001"},
    )

    result = run_authoring_seo_job(
        record,
        lambda line: None,
        run_seo_meta_authoring_fn=lambda model, retry=False: (_ for _ in ()).throw(
            RuntimeError("resolver exploded")
        ),
    )

    assert result.status == JobStatus.FAILED
    assert result.error == "resolver exploded"
    assert result.error_code == ServiceErrorCode.UNEXPECTED_FAILURE.value


def test_stop_route_returns_404_for_missing_or_invalid_job(tmp_path: Path) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(store, lambda record, log: None)
    client = fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    )

    try:
        missing_response = client.post("/api/jobs/missing/stop")
        invalid_response = client.post("/api/jobs/bad$id/stop")
    finally:
        runner.stop()

    assert missing_response.status_code == 404
    assert invalid_response.status_code == 404


def test_stop_route_cancels_queued_job_and_writes_log(tmp_path: Path) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(store)
    record = store.enqueue(JobType.RENDER, {"model": "233541"}, job_id="job-1")
    client = fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    )

    try:
        response = client.post(
            f"/api/jobs/{record.job_id}/stop", json={"reason": "stuck"}
        )
    finally:
        runner.stop()

    body = response.json()
    loaded = store.get_job(record.job_id)
    assert response.status_code == 200
    assert body["status"] == JobStatus.CANCELLED.value
    assert body["finished_at"] is not None
    assert loaded.status == JobStatus.CANCELLED
    assert loaded.stop_reason == "stuck"
    assert "Stop requested by operator before job started." in store.read_logs(
        record.job_id
    )


def test_jobs_by_model_lists_latest_first_and_retry_requeues_failed_stage(
    tmp_path: Path,
) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(store)
    first = store.enqueue(JobType.PREPARE, {"model": "233541"}, job_id="job-1")
    second = store.enqueue(JobType.RENDER, {"model": "233541"}, job_id="job-2")
    other = store.enqueue(JobType.PUBLISH, {"model": "999001"}, job_id="job-3")
    store.mark_succeeded(first.job_id)
    store.mark_failed(second.job_id, "validation failed", message="Render job failed.")
    store.mark_failed(other.job_id, "publish failed", message="Publish job failed.")
    client = fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    )

    try:
        by_model = client.get("/api/jobs/by-model/233541")
        retry = client.post(f"/api/jobs/{second.job_id}/retry")
    finally:
        runner.stop()

    assert by_model.status_code == 200
    assert [job["job_id"] for job in by_model.json()["jobs"]] == ["job-2", "job-1"]
    assert retry.status_code == 200
    assert retry.json()["job_id"].startswith("233541-render-")
    assert retry.json()["job_type"] == "render"


def test_stop_route_cancels_stale_running_job(tmp_path: Path) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from product_factory.api.app import create_app

    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(store)
    record = store.enqueue(JobType.PUBLISH, {"model": "233541"}, job_id="job-1")
    store.mark_running(record.job_id, message="Job started.")
    client = fastapi_testclient.TestClient(
        create_app(job_store=store, job_runner=runner)
    )

    try:
        response = client.post(f"/api/jobs/{record.job_id}/stop")
    finally:
        runner.stop()

    assert response.status_code == 200
    assert response.json()["status"] == JobStatus.CANCELLED.value
    assert store.get_job(record.job_id).status == JobStatus.CANCELLED
    assert "Stop requested for stale running job record." in store.read_logs(
        record.job_id
    )


def test_artifact_resolver_returns_existing_render_expected_paths(
    tmp_path: Path,
) -> None:
    candidate_dir = tmp_path / "work" / "233541" / "candidate"
    candidate_dir.mkdir(parents=True)
    csv_path = candidate_dir / "233541.csv"
    csv_path.write_text("csv\n", encoding="utf-8")
    validation_path = candidate_dir / "233541.validation.json"
    validation_path.write_text("{}\n", encoding="utf-8")

    record = JobRecord(
        job_id="job-1",
        job_type=JobType.RENDER,
        status=JobStatus.SUCCEEDED,
        model="233541",
    )

    artifacts = resolve_job_artifacts(record, repo_root=tmp_path)

    assert {artifact.name: artifact.kind for artifact in artifacts} == {
        "candidate_csv_path": "file",
        "candidate_dir": "directory",
        "model_root": "directory",
        "validation_report_path": "file",
    }


def test_artifact_resolver_includes_stored_publish_detail_paths(tmp_path: Path) -> None:
    record = JobRecord(
        job_id="job-1",
        job_type=JobType.PUBLISH,
        status=JobStatus.SUCCEEDED,
        model="233541",
        artifacts={
            "upload_report_path": str(
                tmp_path / "work" / "233541" / "upload.opencart.json"
            ),
            "import_report_path": str(
                tmp_path / "work" / "233541" / "import.opencart.json"
            ),
        },
    )

    artifacts = resolve_job_artifacts(record, repo_root=tmp_path)

    assert [
        (artifact.name, artifact.path, artifact.kind) for artifact in artifacts
    ] == [
        (
            "import_report_path",
            str(tmp_path / "work" / "233541" / "import.opencart.json"),
            None,
        ),
        (
            "upload_report_path",
            str(tmp_path / "work" / "233541" / "upload.opencart.json"),
            None,
        ),
    ]


def test_artifact_resolver_includes_authoring_preview_content(tmp_path: Path) -> None:
    llm_dir = tmp_path / "work" / "000001" / "llm"
    llm_dir.mkdir(parents=True)
    (llm_dir / "intro_text.preview.html").write_text(
        "Rendered <strong>intro</strong>.", encoding="utf-8"
    )
    record = JobRecord(
        job_id="job-1",
        job_type=JobType.AUTHORING_INTRO,
        status=JobStatus.SUCCEEDED,
        model="000001",
    )

    artifacts = resolve_job_artifacts(record, repo_root=tmp_path)
    preview = next(
        artifact for artifact in artifacts if artifact.name == "intro_text_preview_path"
    )

    assert preview.kind == "text_preview"
    assert preview.content_type == "text/html"
    assert preview.content == "Rendered <strong>intro</strong>."


def test_artifact_resolver_includes_authoring_lint_trace(tmp_path: Path) -> None:
    llm_dir = tmp_path / "work" / "000001" / "llm"
    llm_dir.mkdir(parents=True)
    lint_path = llm_dir / "intro_text.lint_trace.json"
    lint_path.write_text(
        '{"warning_codes":["intro_text_duplicate_category_phrase"]}\n',
        encoding="utf-8",
    )
    record = JobRecord(
        job_id="job-1",
        job_type=JobType.AUTHORING_INTRO,
        status=JobStatus.SUCCEEDED,
        model="000001",
    )

    artifacts = resolve_job_artifacts(record, repo_root=tmp_path)

    assert ("intro_text_lint_trace_path", str(lint_path), "file") in [
        (artifact.name, artifact.path, artifact.kind) for artifact in artifacts
    ]


def _authoring_status(llm_dir: Path) -> AuthoringStatus:
    return AuthoringStatus(
        model="000001",
        llm_dir=str(llm_dir),
        intro_text=IntroTextTaskStatus(
            status="valid",
            output_path=str(llm_dir / "intro_text.output.txt"),
            trace_path=str(llm_dir / "intro_text.retry_trace.json"),
            word_count=90,
            min_words=70,
            max_words=180,
            max_attempts=3,
        ),
        seo_meta=SeoMetaTaskStatus(
            status="valid",
            output_path=str(llm_dir / "seo_meta.output.json"),
        ),
        ready_for_render=True,
    )
