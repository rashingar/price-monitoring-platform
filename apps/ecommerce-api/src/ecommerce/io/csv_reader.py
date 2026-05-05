"""CSV loading with case-insensitive required-column resolution."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from ecommerce.utils.headers import HeaderResolution, resolve_required_headers


@dataclass(frozen=True)
class LoadedCsv:
    path: Path
    headers: list[str]
    delimiter: str
    resolution: HeaderResolution
    rows: list[dict[str, str]]


def load_csv(
    path: Path,
    required_columns: tuple[str, ...],
    encoding: str,
) -> LoadedCsv:
    sample = path.read_text(encoding=encoding)[:4096]
    delimiter = _detect_delimiter(sample)

    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        headers = list(reader.fieldnames or [])
        resolution = resolve_required_headers(headers, required_columns)
        rows: list[dict[str, str]] = []
        for row in reader:
            normalized_row = {key: value if value is not None else "" for key, value in row.items()}
            rows.append(normalized_row)

    return LoadedCsv(
        path=path,
        headers=headers,
        delimiter=delimiter,
        resolution=resolution,
        rows=rows,
    )


def _detect_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,")
        if dialect.delimiter in {";", ","}:
            return dialect.delimiter
    except csv.Error:
        pass

    semicolon_count = sample.count(";")
    comma_count = sample.count(",")
    if semicolon_count >= comma_count and semicolon_count > 0:
        return ";"
    return ","
