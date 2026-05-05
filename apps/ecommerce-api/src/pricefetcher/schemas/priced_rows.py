"""Contracts for price outputs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PricedRow:
    """Canonical priced enriched output row."""

    model: str
    mpn: str
    price: str
    observed_price: str
    new_price: str = ""
    observed_url: str = ""
    match_status: str = ""
    observed_at: str = ""
    error_reason: str = ""
    price_relation: str = ""
    price_delta: str = ""
    matched_mpn: str = ""
    source_extra_values: dict[str, str] = field(default_factory=dict)

    def to_csv_row(
        self,
        *,
        price_column: str,
        url_column: str,
        source_extra_headers: tuple[str, ...] = (),
    ) -> dict[str, str]:
        row = {
            "model": self.model,
            "mpn": self.mpn,
            "price": self.price,
            price_column: self.observed_price,
            "new_price": self.new_price,
            url_column: self.observed_url,
            "match_status": self.match_status,
            "observed_at": self.observed_at,
            "error_reason": self.error_reason,
            "price_relation": self.price_relation,
            "price_delta": self.price_delta,
            "matched_mpn": self.matched_mpn,
        }
        for header in source_extra_headers:
            row[header] = self.source_extra_values.get(header, "")
        return row


@dataclass(frozen=True)
class PriceOnlyRow:
    """Final price-only output row."""

    model: str
    mpn: str
    price: str

    def to_csv_row(self) -> dict[str, str]:
        return {
            "model": self.model,
            "mpn": self.mpn,
            "price": self.price,
        }
