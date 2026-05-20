"""CSV writers that preserve output order and allow incremental row writes."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TextIO


class IncrementalCsvWriter:
    """Open a CSV once, write the header immediately, and append rows incrementally."""

    def __init__(
        self, path: Path, fieldnames: list[str], encoding: str, delimiter: str = ","
    ) -> None:
        self.path = path
        self.fieldnames = fieldnames
        self.encoding = encoding
        self.delimiter = delimiter
        self._handle: TextIO | None = None
        self._writer: csv.DictWriter[str] | None = None

    def __enter__(self) -> "IncrementalCsvWriter":
        self._handle = self.path.open("w", encoding=self.encoding, newline="")
        self._writer = csv.DictWriter(
            self._handle,
            fieldnames=self.fieldnames,
            extrasaction="ignore",
            delimiter=self.delimiter,
        )
        self._writer.writeheader()
        self._handle.flush()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._handle is not None:
            self._handle.close()
        self._handle = None
        self._writer = None

    def write_row(self, row: dict[str, str]) -> None:
        if self._writer is None or self._handle is None:
            raise RuntimeError("CSV writer is not open")
        self._writer.writerow(row)
        self._handle.flush()
