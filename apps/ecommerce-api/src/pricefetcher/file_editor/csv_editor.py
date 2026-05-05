"""String-preserving CSV read/write helpers for the local file editor."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_DELIMITERS = {",", ";", "\t"}
READ_ENCODING = "utf-8-sig"
WRITE_ENCODING = "utf-8"


class InvalidCsvDelimiterError(ValueError):
    """Raised when a delimiter is not one of the supported CSV delimiters."""


@dataclass(frozen=True)
class CsvReadResult:
    path: Path
    delimiter: str
    encoding: str
    columns: list[str]
    rows: list[dict[str, str]]
    returned_rows: int
    total_rows: int


@dataclass(frozen=True)
class CsvWriteResult:
    path: Path
    delimiter: str
    columns: list[str]
    written_rows: int


def read_csv_file(path: Path, delimiter: str | None = None, max_rows: int | None = None) -> CsvReadResult:
    used_delimiter = _normalize_delimiter(delimiter) if delimiter is not None else _detect_delimiter(path)
    with path.open("r", encoding=READ_ENCODING, newline="") as f:
        reader = csv.DictReader(f, delimiter=used_delimiter, restval="")
        columns = list(reader.fieldnames or [])
        all_rows: list[dict[str, str]] = []
        for row in reader:
            all_rows.append({column: _cell_to_string(row.get(column, "")) for column in columns})

    returned_rows = all_rows if max_rows is None else all_rows[: max(0, max_rows)]
    return CsvReadResult(
        path=path,
        delimiter=used_delimiter,
        encoding=READ_ENCODING,
        columns=columns,
        rows=returned_rows,
        returned_rows=len(returned_rows),
        total_rows=len(all_rows),
    )


def write_csv_file(
    path: Path,
    columns: list[str],
    rows: list[dict[str, str]],
    delimiter: str = ",",
) -> CsvWriteResult:
    used_delimiter = _normalize_delimiter(delimiter)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=WRITE_ENCODING, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, delimiter=used_delimiter, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _cell_to_string(row.get(column, "")) for column in columns})
    return CsvWriteResult(path=path, delimiter=used_delimiter, columns=columns, written_rows=len(rows))


def write_csv_copy(
    source_path: Path,
    target_path: Path,
    columns: list[str],
    rows: list[dict[str, str]],
    delimiter: str = ",",
) -> CsvWriteResult:
    _ = source_path
    return write_csv_file(target_path, columns, rows, delimiter)


def _detect_delimiter(path: Path) -> str:
    with path.open("r", encoding=READ_ENCODING, newline="") as f:
        sample = f.read(4096)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        if dialect.delimiter in SUPPORTED_DELIMITERS:
            return dialect.delimiter
    except csv.Error:
        pass
    return ","


def _normalize_delimiter(delimiter: str) -> str:
    value = "\t" if delimiter == "\\t" else delimiter
    if value not in SUPPORTED_DELIMITERS:
        raise InvalidCsvDelimiterError("Delimiter must be one of: comma, semicolon, tab")
    return value


def _cell_to_string(value: object) -> str:
    if value is None:
        return ""
    return str(value)
