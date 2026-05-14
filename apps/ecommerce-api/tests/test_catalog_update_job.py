import sys
import types
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.catalog_db import ingest_source_catalog  # noqa: E402
from ecommerce.catalog_update import service  # noqa: E402
from ecommerce.catalog_update.service import CatalogExportResult, CatalogUpdateConfigError, CatalogUpdateError  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models import Base, CatalogProductRow, SourceUrl  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402


def _client(tmp_path: Path, monkeypatch) -> tuple[TestClient, str]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    Base.metadata.create_all(get_engine(database_url))
    return TestClient(create_app()), database_url


def test_catalog_update_config_validation_reports_missing_env(monkeypatch) -> None:
    monkeypatch.setattr(service, "load_local_env_if_present", lambda: None)
    for name in (
        "OPENCART_STORE_BASE",
        "OPENCART_ADMIN_PATH",
        "OPENCART_ADMIN_USER",
        "OPENCART_ADMIN_PASS",
        "OPENCART_EXPORT_PROFILE",
    ):
        monkeypatch.delenv(name, raising=False)

    try:
        service.load_catalog_update_config()
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

    config = service.load_catalog_update_config()

    assert config.export_profile == "sourceCata"
    assert config.admin_url == "https://shop.example/admin"
    assert "supersecret" not in str(config.safe_payload())


def test_catalog_update_admin_index_matches_product_factory_normalization() -> None:
    assert service.build_admin_index("https://shop.example/", "/ADMIN/index.php") == "https://shop.example/ADMIN/index.php"
    assert service.build_admin_index("https://shop.example", "admin") == "https://shop.example/admin"
    assert service.build_admin_index("https://shop.example", "") == "https://shop.example/index.php"
    assert service.build_admin_index("https://shop.example", "C:/site/ADMIN/index.php") == "https://shop.example/ADMIN/index.php"


def test_export_page_url_reuses_login_session_token() -> None:
    target = service._append_session_token(
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

    result = service.run_catalog_update(
        "job-1",
        config=service.CatalogUpdateConfig(
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


def test_run_catalog_update_filters_excluded_models_before_ingest(tmp_path: Path, monkeypatch) -> None:
    calls: list[tuple[str, Path | None]] = []
    output_dir = tmp_path / "catalog_updates" / "job-2"
    exclusions_path = tmp_path / "excluded.csv"
    exclusions_path.write_text("model\n005606\n", encoding="utf-8")
    monkeypatch.setenv(service.EXCLUDED_MODELS_ENV_VAR, str(exclusions_path))

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

    result = service.run_catalog_update(
        "job-2",
        config=service.CatalogUpdateConfig(
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

    exclusions = service.ExcludedModels(
        path=tmp_path / "excluded.csv",
        found=True,
        explicit_path=True,
        models=frozenset({"005606"}),
    )
    result = service.filter_source_catalog_exclusions(source, tmp_path, exclusions)
    filtered_text = result.filtered_csv_path.read_text(encoding="utf-8")
    assert "5606" in filtered_text
    assert "005606" not in filtered_text

    exclusions = service.ExcludedModels(
        path=tmp_path / "excluded.csv",
        found=True,
        explicit_path=True,
        models=frozenset({"5606"}),
    )
    result = service.filter_source_catalog_exclusions(source, tmp_path, exclusions)
    filtered_text = result.filtered_csv_path.read_text(encoding="utf-8")
    assert "005606" in filtered_text
    assert "5606,M1" not in filtered_text


def test_catalog_update_missing_default_exclusion_file_continues_with_zero_exclusions(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "catalog_updates" / "job-3"
    monkeypatch.delenv(service.EXCLUDED_MODELS_ENV_VAR, raising=False)
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
        config=service.CatalogUpdateConfig(
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
    monkeypatch.setenv(service.EXCLUDED_MODELS_ENV_VAR, str(missing_path))

    try:
        service.load_excluded_models()
    except CatalogUpdateError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected CatalogUpdateError")

    assert "Catalog exclusion file not found" in message
    assert str(missing_path) in message


def test_catalog_update_purges_previously_imported_excluded_catalog_products(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    Base.metadata.create_all(get_engine(database_url))
    output_dir = tmp_path / "catalog_updates" / "job-4"
    exclusions_path = tmp_path / "excluded.csv"
    exclusions_path.write_text("005606\n", encoding="utf-8")
    monkeypatch.setenv(service.EXCLUDED_MODELS_ENV_VAR, str(exclusions_path))

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
    monkeypatch.setenv(service.EXCLUDED_MODELS_ENV_VAR, str(exclusions_path))

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


def _catalog_update_config() -> service.CatalogUpdateConfig:
    return service.CatalogUpdateConfig(
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
    monkeypatch.setattr(service, "_login_to_opencart", lambda _page, _config, _timeout_ms: None)
    monkeypatch.setattr(service, "_open_csv_product_export", lambda _page, _config, _timeout_ms: None)
    monkeypatch.setattr(service, "_load_export_profile", lambda _page, _profile: None)
    monkeypatch.setattr(service, "_advance_export_step_two", lambda _page: None)

    def fake_download(_page, selected_output_dir: Path, _timeout_ms: int, **_kwargs) -> Path:
        downloaded = selected_output_dir / "opencart-products.csv"
        downloaded.write_text("model,name\n", encoding="utf-8")
        return downloaded

    monkeypatch.setattr(service, "_download_export", fake_download)

    result = service.export_catalog_csv(
        service.CatalogUpdateConfig(
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
    monkeypatch.setattr(service, "_login_to_opencart", lambda _page, _config, _timeout_ms: None)

    def fail_open(_page, _config, _timeout_ms):
        raise service.CatalogUpdateError("profile selector missing for admin@example user_token=abc123 supersecret")

    monkeypatch.setattr(service, "_open_csv_product_export", fail_open)

    config = service.CatalogUpdateConfig(
        store_base="https://shop.example",
        admin_path="admin",
        admin_user="admin@example",
        admin_pass="supersecret",
    )

    try:
        service.export_catalog_csv(config, tmp_path, job_id="job-1")
    except service.CatalogUpdateError as exc:
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
    monkeypatch.setattr(service, "_login_to_opencart", lambda _page, _config, _timeout_ms: None)

    def fail_open(_page, _config, _timeout_ms):
        raise service.CatalogUpdateError("CSV Product Export menu item not found.")

    monkeypatch.setattr(service, "_open_csv_product_export", fail_open)

    config = service.CatalogUpdateConfig(
        store_base="https://shop.example",
        admin_path="admin",
        admin_user="admin@example",
        admin_pass="supersecret",
    )

    try:
        service.export_catalog_csv(config, tmp_path, job_id="job-1")
    except service.CatalogUpdateError as exc:
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
        "ecommerce.api.routes_catalog_update.run_catalog_update",
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

    monkeypatch.setattr("ecommerce.api.routes_catalog_update.run_catalog_update", fail_update)

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
        "ecommerce.api.routes_catalog_update.run_catalog_update",
        lambda job_id: {"job_id": job_id, "export_profile": "sourceCata"},
    )

    start_response = client.post("/api/catalog/update-db")
    latest_response = client.get("/api/catalog/update-db/latest")
    job_response = client.get(f"/api/jobs/{start_response.json()['job_id']}")

    combined = f"{start_response.text}\n{latest_response.text}\n{job_response.text}"
    assert "supersecret" not in combined
