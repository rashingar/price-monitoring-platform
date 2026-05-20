"""Canonical field names, source contracts, and enum-like values."""

from __future__ import annotations

from dataclasses import dataclass

INPUT_REQUIRED_COLUMNS: tuple[str, ...] = ("model", "mpn", "price")

COMMON_FETCH_MONITORING_COLUMNS: tuple[str, ...] = (
    "match_status",
    "observed_at",
    "error_reason",
    "price_relation",
    "price_delta",
    "matched_mpn",
)

PRICE_ONLY_COLUMNS: tuple[str, ...] = ("model", "mpn", "price")

MATCH_STATUS_VALUES: tuple[str, ...] = ("matched", "not_found", "ambiguous", "error")

PRICE_RELATION_VALUES: tuple[str, ...] = ("higher", "lower", "equal")

RULE_FAMILIES: tuple[str, ...] = (
    "fixed_offset",
    "percentage_discount",
    "fixed_offset_with_floor",
    "formula_with_rounding",
    "bestprice_store_positioning",
)

ROUNDING_MODES: tuple[str, ...] = (
    "floor",
    "ceil",
    "nearest",
    "minus_one_if_decimal_79_99",
    "keep_2dp",
)


@dataclass(frozen=True)
class FetchSourceContract:
    source_name: str
    price_column: str
    url_column: str
    enriched_suffix: str
    source_extra_columns: tuple[str, ...] = ()

    @property
    def fetch_monitoring_columns(self) -> tuple[str, ...]:
        return (
            (self.price_column, self.url_column)
            + COMMON_FETCH_MONITORING_COLUMNS
            + self.source_extra_columns
        )

    @property
    def required_enriched_columns(self) -> tuple[str, ...]:
        return (
            INPUT_REQUIRED_COLUMNS
            + (self.price_column, self.url_column)
            + COMMON_FETCH_MONITORING_COLUMNS
        )

    @property
    def priced_output_columns(self) -> tuple[str, ...]:
        return (
            "model",
            "mpn",
            "price",
            self.price_column,
            "new_price",
            self.url_column,
            "match_status",
            "observed_at",
            "error_reason",
            "price_relation",
            "price_delta",
            "matched_mpn",
        ) + self.source_extra_columns


FETCH_SOURCE_CONTRACTS: dict[str, FetchSourceContract] = {
    "skroutz": FetchSourceContract(
        source_name="skroutz",
        price_column="skroutz_price",
        url_column="skroutz_url",
        enriched_suffix="_skroutz_enriched",
    ),
    "bestprice": FetchSourceContract(
        source_name="bestprice",
        price_column="bestprice_price",
        url_column="bestprice_url",
        enriched_suffix="_bestprice_enriched",
        source_extra_columns=(
            "bestprice_best_store",
            "bestprice_best_store_price",
            "bestprice_next_store",
            "bestprice_next_store_price",
        ),
    ),
}

FETCH_MONITORING_COLUMNS: tuple[str, ...] = FETCH_SOURCE_CONTRACTS[
    "skroutz"
].fetch_monitoring_columns
PRICED_OUTPUT_COLUMNS: tuple[str, ...] = FETCH_SOURCE_CONTRACTS[
    "skroutz"
].priced_output_columns


def get_fetch_source_contract(source_name: str) -> FetchSourceContract:
    try:
        return FETCH_SOURCE_CONTRACTS[source_name]
    except KeyError as exc:
        supported = ", ".join(FETCH_SOURCE_CONTRACTS)
        raise ValueError(
            f"unsupported fetch source: {source_name}. Supported: {supported}"
        ) from exc


def detect_enriched_source(headers: list[str]) -> str:
    available_headers = set(headers)
    matched_sources = [
        source_name
        for source_name, contract in FETCH_SOURCE_CONTRACTS.items()
        if set(contract.required_enriched_columns).issubset(available_headers)
    ]
    if len(matched_sources) == 1:
        return matched_sources[0]
    if len(matched_sources) > 1:
        raise ValueError("enriched CSV matches multiple source contracts")

    missing_messages: list[str] = []
    for source_name, contract in FETCH_SOURCE_CONTRACTS.items():
        missing = [
            header
            for header in contract.required_enriched_columns
            if header not in available_headers
        ]
        missing_messages.append(f"{source_name}: missing {', '.join(missing)}")
    details = "; ".join(missing_messages)
    raise ValueError(
        f"input file does not match a supported enriched contract ({details})"
    )
