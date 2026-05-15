from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]


def test_env_example_exists_with_safe_database_placeholder() -> None:
    env_example = REPO_ROOT / ".env.example"

    text = env_example.read_text(encoding="utf-8")

    assert "ECOMMERCE_DATABASE_URL=postgresql+psycopg://ecommerce:ecommerce@127.0.0.1:5432/ecommerce" in text
    assert "Do not commit .env" in text
    assert "super-secret" not in text


def test_gitignore_ignores_dotenv_but_allows_example() -> None:
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".env" in text
    assert "!.env.example" in text


def test_windows_postgres_setup_script_exists_and_readme_references_it() -> None:
    script = APP_ROOT / "scripts" / "setup_postgres_windows.ps1"
    readme = (APP_ROOT / "README.md").read_text(encoding="utf-8")

    assert script.exists()
    script_text = script.read_text(encoding="utf-8")
    assert "Docker" not in script_text
    assert "PersistUserEnv" in script_text
    assert "WriteDotEnv" in script_text
    assert "ResetAppUserPassword" in script_text
    assert "drop database" not in script_text.lower()
    assert "drop user" not in script_text.lower()
    assert "setup_postgres_windows.ps1" in readme


def test_readme_documents_env_template_and_native_windows_troubleshooting() -> None:
    readme = (APP_ROOT / "README.md").read_text(encoding="utf-8")

    assert "Native Windows PostgreSQL setup and first-run verification" in readme
    assert ".env.example` file is the canonical template" in readme
    assert "do not commit `.env`" in readme.lower()
    assert "Ecommerce loads `.env` automatically for local commands" in readme
    assert "OS environment value wins over `.env`" in readme
    assert "Docker is not used by this project setup" in readme
    assert "python -m ecommerce.jobs.check_db_setup" in readme
    assert "alembic upgrade head" in readme
    assert "Tables exist but monitoring row counts are zero before first run" in readme
