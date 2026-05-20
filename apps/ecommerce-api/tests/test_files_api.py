import csv
import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.file_editor.safe_paths import FILE_ROOTS_ENV_VAR  # noqa: E402


def _client_with_file_root(tmp_path: Path, monkeypatch) -> tuple[TestClient, Path]:
    root = tmp_path / "safe-root"
    root.mkdir()
    monkeypatch.setenv(FILE_ROOTS_ENV_VAR, str(root))
    return TestClient(create_app()), root


def test_files_roots_endpoint(tmp_path: Path, monkeypatch) -> None:
    client, root = _client_with_file_root(tmp_path, monkeypatch)

    response = client.get("/api/files/roots")

    assert response.status_code == 200
    assert response.json() == {
        "roots": [{"path": str(root.resolve(strict=False)), "exists": True}]
    }


def test_files_list_endpoint_lists_csv_files_and_folders(
    tmp_path: Path, monkeypatch
) -> None:
    client, root = _client_with_file_root(tmp_path, monkeypatch)
    (root / "b.csv").write_text("model\n2\n", encoding="utf-8")
    (root / "a.txt").write_text("ignored\n", encoding="utf-8")
    (root / "folder").mkdir()

    response = client.get("/api/files/list", params={"root": str(root)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["root"] == str(root.resolve(strict=False))
    assert [(item["name"], item["type"]) for item in payload["items"]] == [
        ("folder", "directory"),
        ("b.csv", "file"),
    ]


def test_files_list_rejects_path_traversal(tmp_path: Path, monkeypatch) -> None:
    client, root = _client_with_file_root(tmp_path, monkeypatch)

    response = client.get(
        "/api/files/list", params={"root": str(root), "relative_path": ".."}
    )

    assert response.status_code == 403


def test_files_read_endpoint(tmp_path: Path, monkeypatch) -> None:
    client, root = _client_with_file_root(tmp_path, monkeypatch)
    csv_path = root / "source.csv"
    csv_path.write_text(
        "model,mpn,name\n005606,ABC123,Product\n123456,,\n", encoding="utf-8-sig"
    )

    response = client.post(
        "/api/files/read",
        json={"path": str(csv_path), "delimiter": None, "max_rows": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "source.csv"
    assert payload["delimiter"] == ","
    assert payload["encoding"] == "utf-8-sig"
    assert payload["columns"] == ["model", "mpn", "name"]
    assert payload["rows"] == [{"model": "005606", "mpn": "ABC123", "name": "Product"}]
    assert payload["returned_rows"] == 1
    assert payload["total_rows"] == 2


def test_files_read_rejects_outside_safe_roots(tmp_path: Path, monkeypatch) -> None:
    client, _root = _client_with_file_root(tmp_path, monkeypatch)
    outside = tmp_path / "outside.csv"
    outside.write_text("model\n005606\n", encoding="utf-8")

    response = client.post("/api/files/read", json={"path": str(outside)})

    assert response.status_code == 403


def test_files_save_endpoint(tmp_path: Path, monkeypatch) -> None:
    client, root = _client_with_file_root(tmp_path, monkeypatch)
    target = root / "edited.csv"

    response = client.post(
        "/api/files/save",
        json={
            "path": str(target),
            "columns": ["name", "model", "mpn"],
            "rows": [{"model": "005606", "mpn": "ABC,123", "name": "Product"}],
            "delimiter": ",",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "edited.csv"
    assert payload["written_rows"] == 1
    assert payload["columns"] == ["name", "model", "mpn"]

    with target.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows == [["name", "model", "mpn"], ["Product", "005606", "ABC,123"]]


def test_files_save_rejects_non_csv_extension(tmp_path: Path, monkeypatch) -> None:
    client, root = _client_with_file_root(tmp_path, monkeypatch)

    response = client.post(
        "/api/files/save",
        json={
            "path": str(root / "edited.txt"),
            "columns": ["model"],
            "rows": [],
            "delimiter": ",",
        },
    )

    assert response.status_code == 400
    assert "Only .csv files" in response.json()["detail"]


def test_files_save_copy_endpoint(tmp_path: Path, monkeypatch) -> None:
    client, root = _client_with_file_root(tmp_path, monkeypatch)
    source = root / "source.csv"
    target = root / "copy.csv"
    source.write_text("model\n005606\n", encoding="utf-8-sig")

    response = client.post(
        "/api/files/save-copy",
        json={
            "source_path": str(source),
            "target_path": str(target),
            "columns": ["model", "name"],
            "rows": [{"model": "005606", "name": "Product"}],
            "delimiter": ";",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "copy.csv"
    assert payload["delimiter"] == ";"
    assert target.read_text(encoding="utf-8") == "model;name\n005606;Product\n"
