import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.artifacts import ARTIFACT_ROOTS_ENV_VAR  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.file_editor import FILE_ROOTS_ENV_VAR  # noqa: E402


def test_paths_roots_endpoint_combines_known_roots(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    artifact_root = tmp_path / "custom-artifacts"
    file_root = tmp_path / "file-root"
    artifact_root.mkdir()
    file_root.mkdir()
    (tmp_path / "output").mkdir()
    monkeypatch.setenv(ARTIFACT_ROOTS_ENV_VAR, str(artifact_root))
    monkeypatch.setenv(FILE_ROOTS_ENV_VAR, str(file_root))
    monkeypatch.delenv(DATABASE_URL_ENV_VAR, raising=False)
    monkeypatch.setenv("ECOMMERCE_SECRET_TOKEN", "do-not-expose")

    response = TestClient(create_app()).get("/api/paths/roots")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"artifact_roots", "file_roots", "output_roots", "env", "path_separator", "platform"}
    assert payload["path_separator"] == ";"
    assert payload["platform"] == "Windows-compatible"
    assert payload["env"] == {
        ARTIFACT_ROOTS_ENV_VAR: "configured",
        FILE_ROOTS_ENV_VAR: "configured",
        DATABASE_URL_ENV_VAR: "not_configured",
    }
    assert "ECOMMERCE_SECRET_TOKEN" not in payload["env"]

    artifact_paths = {item["path"]: item for item in payload["artifact_roots"]}
    assert str(artifact_root.resolve(strict=False)) in artifact_paths
    assert artifact_paths[str(artifact_root.resolve(strict=False))]["source"] == ARTIFACT_ROOTS_ENV_VAR
    assert artifact_paths[str(artifact_root.resolve(strict=False))]["is_configured"] is True

    file_paths = {item["path"]: item for item in payload["file_roots"]}
    assert str(file_root.resolve(strict=False)) in file_paths
    assert file_paths[str(file_root.resolve(strict=False))]["source"] == FILE_ROOTS_ENV_VAR

    output_paths = {item["path"]: item for item in payload["output_roots"]}
    output_root = str((tmp_path / "output").resolve(strict=False))
    assert output_root in output_paths
    assert output_paths[output_root]["source"] == "default"
    assert output_paths[output_root]["is_default"] is True

    for root_group in ("artifact_roots", "file_roots", "output_roots"):
        for item in payload[root_group]:
            assert set(item) == {"path", "source", "exists", "is_default", "is_configured"}


def test_paths_roots_endpoint_reports_unconfigured_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(ARTIFACT_ROOTS_ENV_VAR, raising=False)
    monkeypatch.delenv(FILE_ROOTS_ENV_VAR, raising=False)
    monkeypatch.delenv(DATABASE_URL_ENV_VAR, raising=False)

    response = TestClient(create_app()).get("/api/paths/roots")

    assert response.status_code == 200
    payload = response.json()
    assert payload["env"] == {
        ARTIFACT_ROOTS_ENV_VAR: "not_configured",
        FILE_ROOTS_ENV_VAR: "not_configured",
        DATABASE_URL_ENV_VAR: "not_configured",
    }
    assert payload["file_roots"]
    assert payload["output_roots"]
