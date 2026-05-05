import csv
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.file_editor.csv_editor import read_csv_file, write_csv_copy, write_csv_file  # noqa: E402
from ecommerce.file_editor.safe_paths import (  # noqa: E402
    FILE_ROOTS_ENV_VAR,
    UnsafePathError,
    get_allowed_roots,
    is_path_allowed,
    resolve_safe_path,
)


def test_allowed_root_resolution_uses_env_override(tmp_path: Path, monkeypatch) -> None:
    root_one = tmp_path / "root-one"
    root_two = tmp_path / "root-two"
    monkeypatch.setenv(FILE_ROOTS_ENV_VAR, f"{root_one};{root_two}")

    roots = get_allowed_roots()

    assert roots == [root_one.resolve(strict=False), root_two.resolve(strict=False)]


def test_rejecting_paths_outside_safe_roots(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "safe"
    outside = tmp_path / "outside" / "file.csv"
    monkeypatch.setenv(FILE_ROOTS_ENV_VAR, str(root))

    assert not is_path_allowed(outside, get_allowed_roots())
    with pytest.raises(UnsafePathError):
        resolve_safe_path(outside)


def test_rejecting_path_traversal_outside_safe_root(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "safe"
    root.mkdir()
    traversal = root / ".." / "outside.csv"
    monkeypatch.setenv(FILE_ROOTS_ENV_VAR, str(root))

    with pytest.raises(UnsafePathError):
        resolve_safe_path(traversal)


def test_read_comma_csv_preserves_strings_leading_zeroes_and_missing_cells(tmp_path: Path) -> None:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("model,mpn,name\n005606,ABC123,Product\n123456,,\n", encoding="utf-8-sig")

    result = read_csv_file(csv_path)

    assert result.delimiter == ","
    assert result.columns == ["model", "mpn", "name"]
    assert result.rows == [
        {"model": "005606", "mpn": "ABC123", "name": "Product"},
        {"model": "123456", "mpn": "", "name": ""},
    ]


def test_read_semicolon_csv_detects_delimiter(tmp_path: Path) -> None:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("model;mpn;name\n005606;ABC123;Product\n", encoding="utf-8-sig")

    result = read_csv_file(csv_path)

    assert result.delimiter == ";"
    assert result.rows[0]["model"] == "005606"


def test_write_csv_file_preserves_exact_header_order(tmp_path: Path) -> None:
    csv_path = tmp_path / "edited.csv"
    write_csv_file(
        csv_path,
        ["name", "model", "mpn"],
        [{"model": "005606", "mpn": "ABC,123", "name": "Product"}],
    )

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))

    assert rows == [["name", "model", "mpn"], ["Product", "005606", "ABC,123"]]


def test_write_csv_copy_writes_target_csv(tmp_path: Path) -> None:
    source_path = tmp_path / "source.csv"
    target_path = tmp_path / "target.csv"
    source_path.write_text("model\n005606\n", encoding="utf-8-sig")

    result = write_csv_copy(source_path, target_path, ["model"], [{"model": "005606"}])

    assert result.path == target_path
    assert target_path.read_text(encoding="utf-8") == "model\n005606\n"
