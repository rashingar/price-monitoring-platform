import sys
import types
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.catalog_update import service  # noqa: E402
from ecommerce.catalog_update.service import CatalogExportResult, CatalogUpdateConfigError  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models import Base  # noqa: E402
from ecommerce.db.session import get_engine  # noqa: E402


def _client(tmp_path: Path, monkeypatch) -> tuple[TestClient, str]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    Base.metadata.create_all(get_engine(database_url))
    return TestClient(create_app()), database_url


def test_catalog_update_config_validation_reports_missing_env(monkeypatch) -> None:
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

    def fake_export(config, selected_output_dir):
        calls.append(("export", selected_output_dir))
        downloaded = selected_output_dir / "opencart-products.csv"
        downloaded.write_text("model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n", encoding="utf-8")
        return CatalogExportResult(downloaded_path=downloaded, downloaded_size=downloaded.stat().st_size)

    def fake_ingest(path: Path):
        calls.append(("ingest", path))
        return {"imported": 0, "source_path": str(path)}

    monkeypatch.setattr(service, "catalog_update_output_dir", lambda job_id: output_dir)
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
    assert normalized.exists()
    assert calls == [
        ("alembic", None),
        ("export", output_dir),
        ("ingest", normalized),
    ]
    assert result["imported_csv_path"].endswith("sourceCata.csv")
    assert result["downloaded_filename"] == "opencart-products.csv"
    assert "supersecret" not in str(result)


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

    def fake_download(_page, selected_output_dir: Path, _timeout_ms: int) -> Path:
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
