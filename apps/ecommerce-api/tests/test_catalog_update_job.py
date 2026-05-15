import sys
import types
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.catalog_db import ingest_source_catalog  # noqa: E402
import ecommerce.catalog_update as catalog_update  # noqa: E402
from ecommerce.catalog_update import config as catalog_update_config  # noqa: E402
from ecommerce.catalog_update import service  # noqa: E402
from ecommerce.catalog_update import browser_steps, progress  # noqa: E402
from ecommerce.catalog_update.browser_steps import append_session_token  # noqa: E402
from ecommerce.catalog_update.config import build_admin_index, load_catalog_update_config  # noqa: E402
from ecommerce.catalog_update.constants import CATALOG_UPDATE_JOB_TYPE  # noqa: E402
from ecommerce.catalog_update.exclusions import excluded_models_from_rows, filter_source_catalog_exclusions  # noqa: E402
from ecommerce.catalog_update.exporter import export_catalog_csv  # noqa: E402
from ecommerce.catalog_update.progress import CatalogUpdateJobProgressReporter  # noqa: E402
from ecommerce.catalog_update.redaction import redact_opencart_sensitive_data, redact_opencart_url  # noqa: E402
from ecommerce.catalog_update.types import (  # noqa: E402
    EXCLUDED_MODELS_ENV_VAR,
    CatalogExclusionCleanupResult,
    CatalogExportResult,
    CatalogUpdateConfig,
    CatalogUpdateConfigError,
    CatalogUpdateError,
    ExcludedModels,
)
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models import Base, CatalogProductRow, SourceUrl  # noqa: E402
from ecommerce.db.repositories.jobs import create_queued_job, get_job_by_id, mark_running  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402


def _client(tmp_path: Path, monkeypatch) -> tuple[TestClient, str]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    Base.metadata.create_all(get_engine(database_url))
    return TestClient(create_app()), database_url


def test_catalog_update_config_validation_reports_missing_env(monkeypatch) -> None:
    monkeypatch.setattr(catalog_update_config, "load_local_env_if_present", lambda: None)
    for name in (
        "OPENCART_STORE_BASE",
        "OPENCART_ADMIN_PATH",
        "OPENCART_ADMIN_USER",
        "OPENCART_ADMIN_PASS",
        "OPENCART_EXPORT_PROFILE",
    ):
        monkeypatch.delenv(name, raising=False)

    try:
        load_catalog_update_config()
    except CatalogUpdateConfigError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected CatalogUpdateConfigError")

    assert "OPENCART_STORE_BASE" in message
    assert "OPENCART_ADMIN_PASS" in message


def test_catalog_update_config_defaults_export_profile(monkeypatch) -> None:
    monkeypatch.setenv("OPENCART_STORE_BASE", "https://shop.example")
    monkeypatch.setenv("OPENCART_ADMIN_PATH", "admin")
    monkeypatch.setenv("OPENCART_ADMIN_USER", "admin")
    monkeypatch.setenv("OPENCART_ADMIN_PASS", "supersecret")
    monkeypatch.delenv("OPENCART_EXPORT_PROFILE", raising=False)

    config = load_catalog_update_config()

    assert config.export_profile == "sourceCata"
    assert config.admin_url == "https://shop.example/admin"
    assert "supersecret" not in str(config.safe_payload())


def test_catalog_update_admin_index_matches_product_factory_normalization() -> None:
    assert build_admin_index("https://shop.example/", "/ADMIN/index.php") == "https://shop.example/ADMIN/index.php"
    assert build_admin_index("https://shop.example", "admin") == "https://shop.example/admin"
    assert build_admin_index("https://shop.example", "") == "https://shop.example/index.php"
    assert build_admin_index("https://shop.example", "C:/site/ADMIN/index.php") == "https://shop.example/ADMIN/index.php"


def test_catalog_update_package_preserves_public_exports() -> None:
    assert catalog_update.CATALOG_UPDATE_JOB_TYPE == CATALOG_UPDATE_JOB_TYPE
    assert catalog_update.CatalogUpdateConfig is CatalogUpdateConfig
    assert catalog_update.CatalogUpdateError is CatalogUpdateError
    assert catalog_update.CatalogUpdateConfigError is CatalogUpdateConfigError
    assert catalog_update.run_catalog_update is service.run_catalog_update
    assert catalog_update.run_catalog_update_durable_job is service.run_catalog_update_durable_job


def test_catalog_update_service_does_not_expose_old_private_helper_aliases() -> None:
    old_aliases = (
        "_append_session_token",
        "_safe_filename",
        "_safe_path_segment",
        "_sanitize_output",
        "_sanitize_progress_details",
        "_now",
        "_elapsed_seconds",
        "CATALOG_UPDATE_JOB_TYPE",
    )
    assert [name for name in old_aliases if hasattr(service, name)] == []


def test_export_page_url_reuses_login_session_token() -> None:
    target = append_session_token(
        "https://shop.example/ADMIN/index.php?route=extension/ka_extensions/csv_product_export/ka_product_export",
        "https://shop.example/ADMIN/index.php?route=common/dashboard&user_token=abc123",
    )

    assert target == (
        "https://shop.example/ADMIN/index.php"
        "?route=extension/ka_extensions/csv_product_export/ka_product_export&user_token=abc123"
    )


def test_run_catalog_update_calls_migration_and_ingests_downloaded_csv(tmp_path: Path, monkeypatch) -> None:
    calls: list[tuple[str, Path | None]] = []
    output_dir = tmp_path / "catalog_updates" / "job-1"

    def fake_export(config, selected_output_dir, **_kwargs):
        calls.append(("export", selected_output_dir))
        downloaded = selected_output_dir / "opencart-products.csv"
        downloaded.write_text("model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n", encoding="utf-8")
        return CatalogExportResult(downloaded_path=downloaded, downloaded_size=downloaded.stat().st_size)

    def fake_ingest(path: Path):
        calls.append(("ingest", path))
        return {"imported": 0, "source_path": str(path)}

    monkeypatch.setattr(service, "catalog_update_output_dir", lambda job_id: output_dir)
    monkeypatch.setattr(service, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(service, "run_alembic_upgrade", lambda: calls.append(("alembic", None)) or {"status": "succeeded"})
    monkeypatch.setattr(service, "export_catalog_csv", fake_export)
    monkeypatch.setattr(service, "run_catalog_ingest", fake_ingest)
    monkeypatch.setattr(service, "purge_excluded_catalog_state", lambda _models, **_kwargs: CatalogExclusionCleanupResult())

    result = service.run_catalog_update(
        "job-1",
        config=CatalogUpdateConfig(
            store_base="https://shop.example",
            admin_path="admin",
            admin_user="admin",
            admin_pass="supersecret",
        ),
    )

    normalized = output_dir / "sourceCata.csv"
    filtered = output_dir / "sourceCata.filtered.csv"
    assert normalized.exists()
    assert filtered.exists()
    assert calls == [
        ("alembic", None),
        ("export", output_dir),
        ("ingest", filtered),
    ]
    assert result["normalized_csv_path"].endswith("sourceCata.csv")
    assert result["imported_csv_path"].endswith("sourceCata.filtered.csv")
    assert result["downloaded_filename"] == "opencart-products.csv"
    assert result["exclusions"]["exclusion_file_found"] is False
    assert "supersecret" not in str(result)


def test_run_catalog_update_emits_step_progress(tmp_path: Path, monkeypatch) -> None:
    progress_steps: list[str] = []
    output_dir = tmp_path / "catalog_updates" / "job-progress"

    def fake_export(config, selected_output_dir, **kwargs):
        step_tracker = kwargs["step_tracker"]
        step_tracker.mark("playwright_start", progress_step="playwright_started")
        step_tracker.mark("login", progress_step="login_started")
        step_tracker.emit_progress("login_completed")
        step_tracker.mark("wait_for_download", progress_step="download_waiting")
        downloaded = selected_output_dir / "opencart-products.csv"
        downloaded.write_text("model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n", encoding="utf-8")
        return CatalogExportResult(downloaded_path=downloaded, downloaded_size=downloaded.stat().st_size)

    monkeypatch.setattr(service, "catalog_update_output_dir", lambda job_id: output_dir)
    monkeypatch.setattr(service, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(service, "run_alembic_upgrade", lambda: {"status": "succeeded"})
    monkeypatch.setattr(service, "export_catalog_csv", fake_export)
    monkeypatch.setattr(service, "run_catalog_ingest", lambda path: {"imported": 0, "source_path": str(path)})

    def record_step(step: str, _details=None):
        progress_steps.append(step)

    service.run_catalog_update(
        "job-progress",
        config=_catalog_update_config(),
        progress_callback=record_step,
    )

    assert progress_steps == [
        "config_loaded",
        "alembic_upgrade_started",
        "alembic_upgrade_completed",
        "playwright_started",
        "login_started",
        "login_completed",
        "download_waiting",
        "exclusion_filtering_started",
        "exclusion_filtering_completed",
        "ingest_started",
        "ingest_completed",
        "exclusion_purge_started",
        "exclusion_purge_completed",
    ]


def test_catalog_update_progress_definitions_separate_phases_from_events() -> None:
    phase_ids = [phase.id for phase in progress.WORKFLOW_PHASES]
    event_ids = [event.id for event in progress.PROGRESS_EVENTS]

    assert "alembic_upgrade" in phase_ids
    assert "alembic_upgrade_started" in event_ids
    assert "alembic_upgrade_completed" in event_ids
    assert "alembic_upgrade" not in event_ids
    assert progress.PROGRESS_EVENT_LABELS["download_waiting"] == "Download waiting"


def test_catalog_update_long_step_progress_events_have_started_and_completed_boundaries() -> None:
    events_by_phase = {event.phase_id: set() for event in progress.PROGRESS_EVENTS}
    for event in progress.PROGRESS_EVENTS:
        events_by_phase[event.phase_id].add(event.boundary)

    for phase_id in ("alembic_upgrade", "login", "wait_for_download", "filter_exclusions", "ingest_catalog", "purge_exclusions"):
        assert {"started", "completed"} <= events_by_phase[phase_id]


def test_catalog_update_durable_job_writes_progress_and_heartbeat(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    Base.metadata.create_all(get_engine(database_url))
    output_dir = tmp_path / "catalog_updates" / "job-progress"
    clock = _Clock(datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc))

    with session_scope(database_url) as session:
        create_queued_job(session, job_type=CATALOG_UPDATE_JOB_TYPE, payload={}, job_id="job-progress")
        mark_running(session, "job-progress")

    def fake_export(config, selected_output_dir, **kwargs):
        kwargs["step_tracker"].mark("wait_for_download", progress_step="download_waiting")
        downloaded = selected_output_dir / "opencart-products.csv"
        downloaded.write_text("model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n", encoding="utf-8")
        return CatalogExportResult(downloaded_path=downloaded, downloaded_size=downloaded.stat().st_size)

    monkeypatch.setattr(service, "catalog_update_output_dir", lambda job_id: output_dir)
    monkeypatch.setattr(service, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(service, "run_alembic_upgrade", lambda: {"status": "succeeded"})
    monkeypatch.setattr(service, "export_catalog_csv", fake_export)
    monkeypatch.setattr(service, "run_catalog_ingest", lambda path: {"imported": 0, "source_path": str(path)})

    service.run_catalog_update_durable_job(
        "job-progress",
        config=_catalog_update_config(),
        heartbeat_interval_seconds=60,
        now=clock,
    )

    with session_scope(database_url) as session:
        job = get_job_by_id(session, "job-progress")
        assert job is not None
        assert job.status == "running"
        assert job.heartbeat_at is not None
        progress = job.result_json["progress"]
        assert progress["current_step"] == "exclusion_purge_completed"
        assert progress["current_step_label"] == "Exclusion purge completed"
        assert progress["steps_completed"] >= 8
        assert progress["elapsed_seconds"] >= 1
        assert progress["current_step_elapsed_seconds"] >= 0
        assert isinstance(progress["step_started_at"], str)
        assert isinstance(progress["last_progress_at"], str)
        assert progress["completed_steps"]


def test_catalog_update_progress_details_are_sanitized(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    monkeypatch.setenv("OPENCART_ADMIN_USER", "admin@example.test")
    monkeypatch.setenv("OPENCART_ADMIN_PASS", "supersecret")
    Base.metadata.create_all(get_engine(database_url))
    clock = _Clock(datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc))

    with session_scope(database_url) as session:
        create_queued_job(session, job_type=CATALOG_UPDATE_JOB_TYPE, payload={}, job_id="job-sanitized")
        mark_running(session, "job-sanitized")

    with CatalogUpdateJobProgressReporter("job-sanitized", heartbeat_interval_seconds=60, now=clock) as reporter:
        reporter.report(
            "profile_loaded",
            {
                "admin_user": "admin@example.test",
                "password": "supersecret",
                "current_url": "https://shop.example/admin?route=export&user_token=abc123&ok=1",
                "note": "loaded by admin@example.test with supersecret",
            },
        )

    with session_scope(database_url) as session:
        job = get_job_by_id(session, "job-sanitized")
        assert job is not None
        text = json.dumps(job.result_json["progress"], sort_keys=True)

    assert "admin@example.test" not in text
    assert "supersecret" not in text
    assert "abc123" not in text
    assert "user_token=[redacted]" in text
    assert "ok=1" in text


def test_run_catalog_update_filters_excluded_models_before_ingest(tmp_path: Path, monkeypatch) -> None:
    calls: list[tuple[str, Path | None]] = []
    output_dir = tmp_path / "catalog_updates" / "job-2"
    exclusions_path = tmp_path / "excluded.csv"
    exclusions_path.write_text("model\n005606\n", encoding="utf-8")
    monkeypatch.setenv(EXCLUDED_MODELS_ENV_VAR, str(exclusions_path))

    def fake_export(config, selected_output_dir, **_kwargs):
        calls.append(("export", selected_output_dir))
        downloaded = selected_output_dir / "opencart-products.csv"
        downloaded.write_text(
            "model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n"
            "005606,M1,Excluded,Cat,Brand,10,1,1,1,1\n"
            "123456,M2,Kept,Cat,Brand,20,2,1,1,1\n",
            encoding="utf-8",
        )
        return CatalogExportResult(downloaded_path=downloaded, downloaded_size=downloaded.stat().st_size)

    def fake_ingest(path: Path):
        calls.append(("ingest", path))
        return {"imported": 1, "catalog_source": "sourceCata", "source_path": str(path)}

    monkeypatch.setattr(service, "catalog_update_output_dir", lambda job_id: output_dir)
    monkeypatch.setattr(service, "run_alembic_upgrade", lambda: calls.append(("alembic", None)) or {"status": "succeeded"})
    monkeypatch.setattr(service, "export_catalog_csv", fake_export)
    monkeypatch.setattr(service, "run_catalog_ingest", fake_ingest)
    monkeypatch.setattr(service, "purge_excluded_catalog_state", lambda _models, **_kwargs: CatalogExclusionCleanupResult())

    result = service.run_catalog_update(
        "job-2",
        config=CatalogUpdateConfig(
            store_base="https://shop.example",
            admin_path="admin",
            admin_user="admin",
            admin_pass="supersecret",
        ),
    )

    filtered = output_dir / "sourceCata.filtered.csv"
    assert calls[-1] == ("ingest", filtered)
    assert "005606" not in filtered.read_text(encoding="utf-8")
    assert "123456" in filtered.read_text(encoding="utf-8")
    assert result["exclusions"]["excluded_model_count"] == 1
    assert result["exclusions"]["input_row_count"] == 2
    assert result["exclusions"]["removed_row_count"] == 1
    assert result["exclusions"]["output_row_count"] == 1


def test_catalog_update_exclusion_matching_preserves_model_string_identity(tmp_path: Path) -> None:
    source = tmp_path / "sourceCata.csv"
    source.write_text(
        "model,mpn,name\n"
        "5606,M1,Short\n"
        "005606,M2,Padded\n",
        encoding="utf-8",
    )

    exclusions = ExcludedModels(
        path=tmp_path / "excluded.csv",
        found=True,
        explicit_path=True,
        models=frozenset({"005606"}),
    )
    result = filter_source_catalog_exclusions(source, tmp_path, exclusions)
    filtered_text = result.filtered_csv_path.read_text(encoding="utf-8")
    assert "5606" in filtered_text
    assert "005606" not in filtered_text

    exclusions = ExcludedModels(
        path=tmp_path / "excluded.csv",
        found=True,
        explicit_path=True,
        models=frozenset({"5606"}),
    )
    result = filter_source_catalog_exclusions(source, tmp_path, exclusions)
    filtered_text = result.filtered_csv_path.read_text(encoding="utf-8")
    assert "005606" in filtered_text
    assert "5606,M1" not in filtered_text


def test_catalog_update_exclusion_parser_preserves_leading_zero_models(tmp_path: Path) -> None:
    path = tmp_path / "excluded.csv"

    assert excluded_models_from_rows([["model"], ["005606"], ["5606"]], path) == {"005606", "5606"}
    assert excluded_models_from_rows([["005606"], ["5606"]], path) == {"005606", "5606"}


def test_catalog_update_missing_default_exclusion_file_continues_with_zero_exclusions(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "catalog_updates" / "job-3"
    monkeypatch.delenv(EXCLUDED_MODELS_ENV_VAR, raising=False)
    monkeypatch.setattr(service, "repo_root", lambda: tmp_path)

    def fake_export(config, selected_output_dir, **_kwargs):
        downloaded = selected_output_dir / "opencart-products.csv"
        downloaded.write_text(
            "model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n"
            "005606,M1,Kept,Cat,Brand,10,1,1,1,1\n",
            encoding="utf-8",
        )
        return CatalogExportResult(downloaded_path=downloaded, downloaded_size=downloaded.stat().st_size)

    monkeypatch.setattr(service, "catalog_update_output_dir", lambda job_id: output_dir)
    monkeypatch.setattr(service, "run_alembic_upgrade", lambda: {"status": "succeeded"})
    monkeypatch.setattr(service, "export_catalog_csv", fake_export)
    monkeypatch.setattr(service, "run_catalog_ingest", lambda path: {"imported": 1, "catalog_source": "sourceCata", "source_path": str(path)})

    result = service.run_catalog_update(
        "job-3",
        config=CatalogUpdateConfig(
            store_base="https://shop.example",
            admin_path="admin",
            admin_user="admin",
            admin_pass="supersecret",
        ),
    )

    assert result["exclusions"]["exclusion_file_found"] is False
    assert result["exclusions"]["excluded_model_count"] == 0
    assert result["exclusions"]["removed_row_count"] == 0
    assert (output_dir / "sourceCata.filtered.csv").exists()


def test_catalog_update_explicit_missing_exclusion_file_fails(tmp_path: Path, monkeypatch) -> None:
    missing_path = tmp_path / "missing.csv"
    monkeypatch.setenv(EXCLUDED_MODELS_ENV_VAR, str(missing_path))

    try:
        service.load_excluded_models()
    except CatalogUpdateError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected CatalogUpdateError")

    assert "Catalog exclusion file not found" in message
    assert str(missing_path) in message


def test_catalog_update_redaction_removes_opencart_secret_values(monkeypatch) -> None:
    monkeypatch.setenv("OPENCART_ADMIN_USER", "admin@example.test")
    monkeypatch.setenv("OPENCART_ADMIN_PASS", "supersecret")

    redacted_url = redact_opencart_url(
        "https://shop.example/admin?route=common/dashboard&user_token=abc123&username=admin@example.test&ok=1"
    )
    redacted_text = redact_opencart_sensitive_data("admin@example.test password=supersecret token=abc123")

    assert "admin@example.test" not in redacted_url
    assert "abc123" not in redacted_url
    assert "ok=1" in redacted_url
    assert redacted_text == "[redacted] password=[redacted] token=[redacted]"


def test_catalog_update_purges_previously_imported_excluded_catalog_products(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    Base.metadata.create_all(get_engine(database_url))
    output_dir = tmp_path / "catalog_updates" / "job-4"
    exclusions_path = tmp_path / "excluded.csv"
    exclusions_path.write_text("005606\n", encoding="utf-8")
    monkeypatch.setenv(EXCLUDED_MODELS_ENV_VAR, str(exclusions_path))

    with session_scope(database_url) as session:
        session.add(_catalog_row("005606", name="Previously imported"))

    def fake_export(config, selected_output_dir, **_kwargs):
        downloaded = selected_output_dir / "opencart-products.csv"
        downloaded.write_text(
            "model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n"
            "005606,M1,Excluded,Cat,Brand,10,1,1,1,1\n"
            "123456,M2,Kept,Cat,Brand,20,2,1,1,1\n",
            encoding="utf-8",
        )
        return CatalogExportResult(downloaded_path=downloaded, downloaded_size=downloaded.stat().st_size)

    monkeypatch.setattr(service, "catalog_update_output_dir", lambda job_id: output_dir)
    monkeypatch.setattr(service, "run_alembic_upgrade", lambda: {"status": "succeeded"})
    monkeypatch.setattr(service, "export_catalog_csv", fake_export)
    monkeypatch.setattr(service, "run_catalog_ingest", _db_ingest)

    result = service.run_catalog_update("job-4", config=_catalog_update_config())

    with session_scope(database_url) as session:
        excluded = session.execute(select(CatalogProductRow).where(CatalogProductRow.model == "005606")).scalars().all()
        kept = session.execute(select(CatalogProductRow).where(CatalogProductRow.model == "123456")).scalar_one_or_none()

    assert excluded == []
    assert kept is not None and kept.active is True
    assert result["exclusions"]["removed_row_count"] == 1
    assert result["exclusions"]["purged_catalog_products"] == 1


def test_catalog_update_purges_source_urls_for_excluded_catalog_products(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    Base.metadata.create_all(get_engine(database_url))
    output_dir = tmp_path / "catalog_updates" / "job-5"
    exclusions_path = tmp_path / "excluded.csv"
    exclusions_path.write_text("model\n005606\n", encoding="utf-8")
    monkeypatch.setenv(EXCLUDED_MODELS_ENV_VAR, str(exclusions_path))

    with session_scope(database_url) as session:
        row = _catalog_row("005606", name="Excluded with source URL")
        session.add(row)
        session.flush()
        session.add(
            SourceUrl(
                catalog_product_id=row.id,
                catalog_source="sourceCata",
                model="005606",
                mpn="M1",
                manufacturer="Brand",
                source_name="bestprice",
                source_domain="example.com",
                url="https://example.com/product",
                url_normalized="https://example.com/product",
                status="active",
                url_type="manual",
                trust_level="manual",
                created_at=_now(),
                updated_at=_now(),
            )
        )

    def fake_export(config, selected_output_dir, **_kwargs):
        downloaded = selected_output_dir / "opencart-products.csv"
        downloaded.write_text(
            "model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n"
            "005606,M1,Excluded,Cat,Brand,10,1,1,1,1\n",
            encoding="utf-8",
        )
        return CatalogExportResult(downloaded_path=downloaded, downloaded_size=downloaded.stat().st_size)

    monkeypatch.setattr(service, "catalog_update_output_dir", lambda job_id: output_dir)
    monkeypatch.setattr(service, "run_alembic_upgrade", lambda: {"status": "succeeded"})
    monkeypatch.setattr(service, "export_catalog_csv", fake_export)
    monkeypatch.setattr(service, "run_catalog_ingest", _db_ingest)

    result = service.run_catalog_update("job-5", config=_catalog_update_config())

    with session_scope(database_url) as session:
        source_urls = session.execute(select(SourceUrl).where(SourceUrl.model == "005606")).scalars().all()
        catalog_rows = session.execute(select(CatalogProductRow).where(CatalogProductRow.model == "005606")).scalars().all()

    assert source_urls == []
    assert catalog_rows == []
    assert result["exclusions"]["purged_source_urls"] == 1
    assert result["exclusions"]["purged_catalog_products"] == 1


def _catalog_update_config() -> CatalogUpdateConfig:
    return CatalogUpdateConfig(
        store_base="https://shop.example",
        admin_path="admin",
        admin_user="admin",
        admin_pass="supersecret",
    )


def _db_ingest(path: Path) -> dict:
    with session_scope() as session:
        return ingest_source_catalog(session, source_cata_path=path).to_dict()


def _catalog_row(model: str, *, name: str) -> CatalogProductRow:
    return CatalogProductRow(
        catalog_source="sourceCata",
        model=model,
        mpn="M1",
        name=name,
        category="Cat",
        raw_category="Cat",
        manufacturer="Brand",
        active=True,
        imported_at=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def __call__(self) -> datetime:
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value


def test_export_catalog_csv_closes_browser_before_playwright_stops(tmp_path: Path, monkeypatch) -> None:
    browsers: list[FakeBrowser] = []

    class FakePage:
        def set_default_timeout(self, _timeout_ms: int) -> None:
            return None

    class FakeContext:
        def __init__(self) -> None:
            self.closed = False

        def new_page(self) -> FakePage:
            return FakePage()

        def close(self) -> None:
            self.closed = True

    class FakeBrowser:
        def __init__(self, playwright) -> None:
            self.playwright = playwright
            self.closed = False

        def new_context(self, *, accept_downloads: bool) -> FakeContext:
            assert accept_downloads is True
            return FakeContext()

        def close(self) -> None:
            if self.playwright.stopped:
                raise RuntimeError("Event loop is closed! Is Playwright already stopped?")
            self.closed = True

    class FakeChromium:
        def __init__(self, playwright) -> None:
            self.playwright = playwright

        def launch(self, *, headless: bool) -> FakeBrowser:
            assert headless is True
            browser = FakeBrowser(self.playwright)
            browsers.append(browser)
            return browser

    class FakePlaywright:
        def __init__(self) -> None:
            self.stopped = False
            self.chromium = FakeChromium(self)

    class FakePlaywrightContextManager:
        def __init__(self) -> None:
            self.playwright = FakePlaywright()

        def __enter__(self) -> FakePlaywright:
            return self.playwright

        def __exit__(self, _exc_type, _exc, _traceback) -> None:
            self.playwright.stopped = True

    fake_sync_api = types.SimpleNamespace(
        TimeoutError=TimeoutError,
        sync_playwright=lambda: FakePlaywrightContextManager(),
    )
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync_api)
    monkeypatch.setattr(browser_steps, "login_to_opencart", lambda _page, _config, _timeout_ms: None)
    monkeypatch.setattr(browser_steps, "open_csv_product_export", lambda _page, _config, _timeout_ms: None)
    monkeypatch.setattr(browser_steps, "load_export_profile", lambda _page, _profile: None)
    monkeypatch.setattr(browser_steps, "advance_export_step_two", lambda _page: None)

    def fake_download(_page, selected_output_dir: Path, _timeout_ms: int, **_kwargs) -> Path:
        downloaded = selected_output_dir / "opencart-products.csv"
        downloaded.write_text("model,name\n", encoding="utf-8")
        return downloaded

    monkeypatch.setattr(browser_steps, "download_export", fake_download)

    result = export_catalog_csv(
        CatalogUpdateConfig(
            store_base="https://shop.example",
            admin_path="admin",
            admin_user="admin",
            admin_pass="supersecret",
        ),
        tmp_path,
    )

    assert result.downloaded_path == tmp_path / "opencart-products.csv"
    assert browsers and browsers[0].closed is True
    assert not (tmp_path / "diagnostics").exists()


class FakeDiagnosticLocator:
    @property
    def first(self):
        return self

    def fill(self, _value: str) -> None:
        return None


class FakeDiagnosticPage:
    def __init__(self, *, url: str, screenshot_fails: bool = False) -> None:
        self.url = url
        self.screenshot_fails = screenshot_fails
        self.screenshot_paths: list[Path] = []

    def set_default_timeout(self, _timeout_ms: int) -> None:
        return None

    def locator(self, _selector: str) -> FakeDiagnosticLocator:
        return FakeDiagnosticLocator()

    def screenshot(self, *, path: str, full_page: bool) -> None:
        assert full_page is True
        if self.screenshot_fails:
            raise RuntimeError("screenshot failed for supersecret")
        screenshot_path = Path(path)
        screenshot_path.write_bytes(b"fake-png")
        self.screenshot_paths.append(screenshot_path)


def _install_fake_playwright(monkeypatch, page: FakeDiagnosticPage):
    class FakeContext:
        def __init__(self) -> None:
            self.closed = False

        def new_page(self) -> FakeDiagnosticPage:
            return page

        def close(self) -> None:
            self.closed = True

    class FakeBrowser:
        def __init__(self) -> None:
            self.context = FakeContext()
            self.closed = False

        def new_context(self, *, accept_downloads: bool) -> FakeContext:
            assert accept_downloads is True
            return self.context

        def close(self) -> None:
            self.closed = True

    class FakeChromium:
        def __init__(self) -> None:
            self.browser = FakeBrowser()

        def launch(self, *, headless: bool) -> FakeBrowser:
            assert headless is True
            return self.browser

    class FakePlaywright:
        def __init__(self) -> None:
            self.chromium = FakeChromium()

    class FakePlaywrightContextManager:
        def __init__(self) -> None:
            self.playwright = FakePlaywright()

        def __enter__(self) -> FakePlaywright:
            return self.playwright

        def __exit__(self, _exc_type, _exc, _traceback) -> None:
            return None

    fake_sync_api = types.SimpleNamespace(
        TimeoutError=TimeoutError,
        sync_playwright=lambda: FakePlaywrightContextManager(),
    )
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync_api)


def test_export_catalog_csv_writes_redacted_failure_diagnostics_on_playwright_failure(tmp_path: Path, monkeypatch) -> None:
    page = FakeDiagnosticPage(
        url=(
            "https://shop.example/ADMIN/index.php?route=common/dashboard"
            "&user_token=abc123&username=admin@example&password=supersecret&ok=1"
        ),
    )
    _install_fake_playwright(monkeypatch, page)
    monkeypatch.setattr(browser_steps, "login_to_opencart", lambda _page, _config, _timeout_ms: None)

    def fail_open(_page, _config, _timeout_ms):
        raise CatalogUpdateError("profile selector missing for admin@example user_token=abc123 supersecret")

    monkeypatch.setattr(browser_steps, "open_csv_product_export", fail_open)

    config = CatalogUpdateConfig(
        store_base="https://shop.example",
        admin_path="admin",
        admin_user="admin@example",
        admin_pass="supersecret",
    )

    try:
        export_catalog_csv(config, tmp_path, job_id="job-1")
    except CatalogUpdateError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected CatalogUpdateError")

    context_path = tmp_path / "diagnostics" / "failure_context.json"
    screenshot_path = tmp_path / "diagnostics" / "failure.png"
    payload = json.loads(context_path.read_text(encoding="utf-8"))
    combined = f"{message}\n{context_path.read_text(encoding='utf-8')}"

    assert screenshot_path in page.screenshot_paths
    assert screenshot_path.exists()
    assert payload["job_id"] == "job-1"
    assert payload["step"] == "open_csv_product_export"
    assert "user_token=[redacted]" in payload["current_url"]
    assert "username=" in payload["current_url"]
    assert "password=[redacted]" in payload["current_url"]
    assert "ok=1" in payload["current_url"]
    assert payload["sanitized_error_message"] == "profile selector missing for [redacted] user_token=[redacted] [redacted]"
    assert "Diagnostics saved to" in message
    assert "admin@example" not in combined
    assert "supersecret" not in combined
    assert "abc123" not in combined


def test_export_catalog_csv_preserves_original_error_when_screenshot_capture_fails(tmp_path: Path, monkeypatch) -> None:
    page = FakeDiagnosticPage(
        url="https://shop.example/ADMIN/index.php?route=common/dashboard&user_token=abc123",
        screenshot_fails=True,
    )
    _install_fake_playwright(monkeypatch, page)
    monkeypatch.setattr(browser_steps, "login_to_opencart", lambda _page, _config, _timeout_ms: None)

    def fail_open(_page, _config, _timeout_ms):
        raise CatalogUpdateError("CSV Product Export menu item not found.")

    monkeypatch.setattr(browser_steps, "open_csv_product_export", fail_open)

    config = CatalogUpdateConfig(
        store_base="https://shop.example",
        admin_path="admin",
        admin_user="admin@example",
        admin_pass="supersecret",
    )

    try:
        export_catalog_csv(config, tmp_path, job_id="job-1")
    except CatalogUpdateError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected CatalogUpdateError")

    payload = json.loads((tmp_path / "diagnostics" / "failure_context.json").read_text(encoding="utf-8"))

    assert "CSV Product Export menu item not found." in message
    assert "screenshot failed" not in message
    assert payload["screenshot_error"] == "screenshot failed for [redacted]"


def test_catalog_update_endpoint_creates_durable_job(tmp_path: Path, monkeypatch) -> None:
    client, _database_url = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "ecommerce.api.routes_catalog_update.run_catalog_update_durable_job",
        lambda job_id: {"job_id": job_id, "export_profile": "sourceCata", "ingest": {"imported": 1}},
    )

    response = client.post("/api/catalog/update-db")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_type"] == "catalog_update_from_opencart"
    assert payload["job_id"]
    assert payload["status_url"] == f"/api/jobs/{payload['job_id']}"

    detail = client.get(f"/api/jobs/{payload['job_id']}").json()
    assert detail["status"] == "succeeded"
    assert detail["result"]["ingest"]["imported"] == 1


def test_catalog_update_job_failure_is_finalized(tmp_path: Path, monkeypatch) -> None:
    client, _database_url = _client(tmp_path, monkeypatch)

    def fail_update(job_id: str):
        raise RuntimeError(f"login failed for job {job_id}")

    monkeypatch.setattr("ecommerce.api.routes_catalog_update.run_catalog_update_durable_job", fail_update)

    response = client.post("/api/catalog/update-db")

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["status"] == "failed"
    assert "login failed" in detail["error_message"]


def test_catalog_update_responses_do_not_include_opencart_password(tmp_path: Path, monkeypatch) -> None:
    client, _database_url = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("OPENCART_ADMIN_PASS", "supersecret")
    monkeypatch.setattr(
        "ecommerce.api.routes_catalog_update.run_catalog_update_durable_job",
        lambda job_id: {"job_id": job_id, "export_profile": "sourceCata"},
    )

    start_response = client.post("/api/catalog/update-db")
    latest_response = client.get("/api/catalog/update-db/latest")
    job_response = client.get(f"/api/jobs/{start_response.json()['job_id']}")

    combined = f"{start_response.text}\n{latest_response.text}\n{job_response.text}"
    assert "supersecret" not in combined
