"""Summary JSON contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class FetchSummary:
    operation: str
    source: str
    input_file: str
    output_file: str
    started_at: str
    finished_at: str
    total_rows: int
    matched: int
    not_found: int
    ambiguous: int
    error: int
    higher: int
    lower: int
    equal: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class PricingSummary:
    operation: str
    source: str
    input_file: str
    output_files: list[str]
    started_at: str
    finished_at: str
    total_rows: int
    priced_rows: int
    blank_new_price_rows: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
