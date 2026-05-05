from pathlib import Path

from alembic import command
from alembic.config import Config

from ecommerce.db.config import get_database_url
from ecommerce.env import load_local_env_if_present
from ecommerce.jobs import check_db_setup


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_load_local_env_if_present_loads_missing_values_from_nearest_env(tmp_path: Path, monkeypatch) -> None:
    child = tmp_path / "one" / "two"
    child.mkdir(parents=True)
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
    assert status["keys_loaded"] == [
        "ECOMMERCE_DATABASE_URL",
        "ECOMMERCE_SOURCE_CATA_PATH",
        "ECOMMERCE_PRICE_IGNORE_PATH",
    ]
    assert status["keys_skipped_existing"] == []
    assert get_database_url() == "sqlite+pysqlite:///local.db"


def test_load_local_env_if_present_keeps_existing_os_environment(tmp_path: Path, monkeypatch) -> None:
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


def test_load_local_env_if_present_handles_missing_and_comment_only_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ECOMMERCE_DATABASE_URL", raising=False)

    missing_status = load_local_env_if_present()

    assert missing_status == {
        "loaded": False,
        "path": None,
        "keys_loaded": [],
        "keys_skipped_existing": [],
    }

    (tmp_path / ".env").write_text(
        "# comments only\n"
        "\n"
        "not a key value line\n"
        "1INVALID=value\n",
        encoding="utf-8",
    )

    comment_only_status = load_local_env_if_present()

    assert comment_only_status["loaded"] is True
    assert comment_only_status["keys_loaded"] == []
    assert get_database_url() is None


def test_check_db_setup_loads_dotenv_and_sanitizes_output(tmp_path: Path, monkeypatch, capsys) -> None:
    raw_url = "postgresql+psycopg://ecommerce:super-secret@127.0.0.1:5432/ecommerce"
    (tmp_path / ".env").write_text(f"ECOMMERCE_DATABASE_URL={raw_url}\n", encoding="utf-8")
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
    assert "ECOMMERCE_DATABASE_URL source: .env" in output
    assert "super-secret" not in output
    assert "ecommerce:***@127.0.0.1" in output


def test_alembic_upgrade_can_read_database_url_from_dotenv(tmp_path: Path, monkeypatch) -> None:
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
