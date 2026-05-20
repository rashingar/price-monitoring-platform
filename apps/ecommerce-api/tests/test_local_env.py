import os
import subprocess
from pathlib import Path

import pytest

from alembic import command
from alembic.config import Config

from ecommerce.db.config import get_database_url
from ecommerce.env import load_local_env_if_present
from ecommerce.jobs import check_db_setup

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]


def test_load_local_env_if_present_loads_missing_values_from_repo_root_env(
    tmp_path: Path, monkeypatch
) -> None:
    child = tmp_path / "apps" / "ecommerce-api"
    child.mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("# test repo\n", encoding="utf-8")
    (tmp_path / ".env").write_text(
        "\n"
        "# local settings\n"
        "ECOMMERCE_DATABASE_URL='sqlite+pysqlite:///local.db'\n"
        'ECOMMERCE_SOURCE_CATA_PATH="C:\\Exports\\sourceCata.csv"\n'
        "ECOMMERCE_PRICE_IGNORE_PATH=C:\\Exports\\price_ignore.csv\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(child)
    for name in (
        "ECOMMERCE_DATABASE_URL",
        "ECOMMERCE_SOURCE_CATA_PATH",
        "ECOMMERCE_PRICE_IGNORE_PATH",
    ):
        monkeypatch.delenv(name, raising=False)

    status = load_local_env_if_present()

    assert status["loaded"] is True
    assert status["path"] == str(tmp_path / ".env")
    assert status["root_path"] == str(tmp_path / ".env")
    assert status["deprecated_app_env_detected"] is False
    assert status["keys_loaded"] == [
        "ECOMMERCE_DATABASE_URL",
        "ECOMMERCE_SOURCE_CATA_PATH",
        "ECOMMERCE_PRICE_IGNORE_PATH",
    ]
    assert status["keys_loaded_from_root"] == status["keys_loaded"]
    assert status["keys_loaded_from_deprecated_app"] == []
    assert status["keys_skipped_existing"] == []
    assert get_database_url() == "sqlite+pysqlite:///local.db"


def test_load_local_env_if_present_loads_repo_root_env_from_web_app(
    tmp_path: Path, monkeypatch
) -> None:
    web_root = tmp_path / "apps" / "web"
    web_root.mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("# test repo\n", encoding="utf-8")
    (tmp_path / ".env").write_text(
        "ECOMMERCE_DATABASE_URL=sqlite+pysqlite:///from-root.db\n", encoding="utf-8"
    )
    monkeypatch.chdir(web_root)
    monkeypatch.delenv("ECOMMERCE_DATABASE_URL", raising=False)

    status = load_local_env_if_present()

    assert status["root_path"] == str(tmp_path / ".env")
    assert status["keys_loaded_from_root"] == ["ECOMMERCE_DATABASE_URL"]
    assert get_database_url() == "sqlite+pysqlite:///from-root.db"


def test_load_local_env_if_present_keeps_existing_os_environment(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "AGENTS.md").write_text("# test repo\n", encoding="utf-8")
    (tmp_path / ".env").write_text(
        "ECOMMERCE_DATABASE_URL=sqlite+pysqlite:///from-dotenv.db\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", "sqlite+pysqlite:///from-os.db")

    status = load_local_env_if_present()

    assert status["keys_loaded"] == []
    assert status["keys_skipped_existing"] == ["ECOMMERCE_DATABASE_URL"]
    assert get_database_url() == "sqlite+pysqlite:///from-os.db"


def test_deprecated_app_env_fills_only_missing_values(
    tmp_path: Path, monkeypatch
) -> None:
    app_root = tmp_path / "apps" / "ecommerce-api"
    app_root.mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("# test repo\n", encoding="utf-8")
    (tmp_path / ".env").write_text(
        "ECOMMERCE_DATABASE_URL=sqlite+pysqlite:///from-root.db\n"
        "ECOMMERCE_SOURCE_CATA_PATH=C:\\Root\\sourceCata.csv\n",
        encoding="utf-8",
    )
    (app_root / ".env").write_text(
        "ECOMMERCE_DATABASE_URL=sqlite+pysqlite:///from-app.db\n"
        "ECOMMERCE_PRICE_IGNORE_PATH=C:\\App\\price_ignore.csv\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(app_root)
    for name in (
        "ECOMMERCE_DATABASE_URL",
        "ECOMMERCE_SOURCE_CATA_PATH",
        "ECOMMERCE_PRICE_IGNORE_PATH",
    ):
        monkeypatch.delenv(name, raising=False)

    status = load_local_env_if_present()

    assert get_database_url() == "sqlite+pysqlite:///from-root.db"
    assert status["deprecated_app_env_detected"] is True
    assert status["keys_loaded_from_root"] == [
        "ECOMMERCE_DATABASE_URL",
        "ECOMMERCE_SOURCE_CATA_PATH",
    ]
    assert status["keys_loaded_from_deprecated_app"] == ["ECOMMERCE_PRICE_IGNORE_PATH"]
    assert status["keys_skipped_deprecated_duplicate"] == ["ECOMMERCE_DATABASE_URL"]
    assert "Deprecated app-local .env detected" in status["warnings"][0]


def test_deprecated_app_env_does_not_print_secret_values(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    app_root = tmp_path / "apps" / "ecommerce-api"
    app_root.mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("# test repo\n", encoding="utf-8")
    (tmp_path / ".env").write_text(
        "OPENCART_ADMIN_PASS=root-secret\n", encoding="utf-8"
    )
    (app_root / ".env").write_text("OPENCART_ADMIN_PASS=app-secret\n", encoding="utf-8")
    monkeypatch.chdir(app_root)
    monkeypatch.delenv("OPENCART_ADMIN_PASS", raising=False)

    status = load_local_env_if_present()
    print("\n".join(status["warnings"]))
    print(",".join(status["keys_skipped_deprecated_duplicate"]))
    output = capsys.readouterr().out

    assert "OPENCART_ADMIN_PASS" in output
    assert "root-secret" not in output
    assert "app-secret" not in output


@pytest.mark.runtime
def test_power_shell_root_env_helper_uses_root_before_app_local(tmp_path: Path) -> None:
    app_root = tmp_path / "apps" / "web"
    app_root.mkdir(parents=True)
    (tmp_path / ".env").write_text(
        "VITE_COMMERCE_API_PROXY_TARGET=http://root.example\n"
        "OPENCART_ADMIN_PASS=root-secret\n",
        encoding="utf-8",
    )
    (app_root / ".env").write_text(
        "VITE_COMMERCE_API_PROXY_TARGET=http://app.example\n"
        "VITE_API_PROXY_TARGET=http://app-only.example\n"
        "OPENCART_ADMIN_PASS=app-secret\n",
        encoding="utf-8",
    )
    helper = REPO_ROOT / "scripts" / "dev" / "load-root-env.ps1"
    command = (
        f"& '{helper}' -RepoRoot '{tmp_path}' -DeprecatedAppEnvPath '{app_root / '.env'}' -Quiet | ConvertTo-Json -Depth 5; "
        "$payload = [pscustomobject]@{ "
        "commerce=$env:VITE_COMMERCE_API_PROXY_TARGET; "
        "api=$env:VITE_API_PROXY_TARGET; "
        "passConfigured=[bool]$env:OPENCART_ADMIN_PASS "
        "}; $payload | ConvertTo-Json -Depth 3"
    )
    env = os.environ.copy()
    for key in (
        "VITE_COMMERCE_API_PROXY_TARGET",
        "VITE_API_PROXY_TARGET",
        "OPENCART_ADMIN_PASS",
    ):
        env.pop(key, None)

    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "root-secret" not in completed.stdout
    assert "app-secret" not in completed.stdout
    assert "http://root.example" in completed.stdout
    assert "http://app-only.example" in completed.stdout
    assert "http://app.example" not in completed.stdout


def test_load_local_env_if_present_handles_missing_and_comment_only_env(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ECOMMERCE_DATABASE_URL", raising=False)

    missing_status = load_local_env_if_present()

    assert missing_status == {
        "loaded": False,
        "path": None,
        "root_path": None,
        "deprecated_app_path": None,
        "deprecated_app_env_detected": False,
        "keys_loaded": [],
        "keys_loaded_from_root": [],
        "keys_loaded_from_deprecated_app": [],
        "keys_skipped_existing": [],
        "keys_skipped_deprecated_duplicate": [],
        "warnings": [],
    }

    (tmp_path / ".env").write_text(
        "# comments only\n" "\n" "not a key value line\n" "1INVALID=value\n",
        encoding="utf-8",
    )

    comment_only_status = load_local_env_if_present()

    assert comment_only_status["loaded"] is True
    assert comment_only_status["keys_loaded"] == []
    assert get_database_url() is None


def test_check_db_setup_loads_dotenv_and_sanitizes_output(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    raw_url = "postgresql+psycopg://ecommerce:super-secret@127.0.0.1:5432/ecommerce"
    (tmp_path / ".env").write_text(
        f"ECOMMERCE_DATABASE_URL={raw_url}\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ECOMMERCE_DATABASE_URL", raising=False)

    def fake_status() -> dict:
        database_url = get_database_url()
        assert database_url == raw_url
        return {
            "configured": True,
            "reachable": False,
            "dialect": None,
            "sanitized_database_url": "postgresql+psycopg://ecommerce:***@127.0.0.1:5432/ecommerce",
            "alembic_current_revision": None,
            "alembic_head_revision": "20260429_0002",
            "alembic_up_to_date": None,
            "required_tables": {},
            "required_tables_present": False,
            "row_counts": None,
            "price_monitoring_database_mode": "unreachable",
            "error": "could not connect with password ***",
        }

    monkeypatch.setattr(check_db_setup, "collect_database_status", fake_status)

    assert check_db_setup.main([]) == 1
    output = capsys.readouterr().out

    assert "ECOMMERCE_DATABASE_URL configured: True" in output
    assert "ECOMMERCE_DATABASE_URL source: repo-root .env" in output
    assert "super-secret" not in output
    assert "ecommerce:***@127.0.0.1" in output


def test_alembic_upgrade_can_read_database_url_from_dotenv(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "alembic-dotenv.db"
    (tmp_path / ".env").write_text(
        f"ECOMMERCE_DATABASE_URL=sqlite+pysqlite:///{database_path.as_posix()}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ECOMMERCE_DATABASE_URL", raising=False)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))

    command.upgrade(config, "head")

    assert database_path.exists()
