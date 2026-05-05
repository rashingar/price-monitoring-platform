"""Input-row contracts used by the Phase 1-2 validation layer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class InputRow:
    """Canonical representation of one input CSV row."""

    row_number: int
    model: str
    mpn: str
    price: str
    original_values: dict[str, str] = field(default_factory=dict)
    extra_values: dict[str, str] = field(default_factory=dict)
