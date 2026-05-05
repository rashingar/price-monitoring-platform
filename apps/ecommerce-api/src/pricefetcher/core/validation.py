"""Row-level validation for input and enriched CSVs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from pricefetcher.io.csv_reader import LoadedCsv
from pricefetcher.schemas import (
    InputRow,
    PriceOnlyRow,
    PricedRow,
    detect_enriched_source,
    get_fetch_source_contract,
)
from pricefetcher.utils.decimals import parse_dot_decimal_text


@dataclass(frozen=True)
class ValidatedInputRow:
    row: InputRow
    error_reason: str = ""
    parsed_price: Decimal | None = None

    @property
    def is_valid(self) -> bool:
        return not self.error_reason


@dataclass(frozen=True)
class ValidatedEnrichedRow:
    source_name: str
    priced_row: PricedRow
    price_only_row: PriceOnlyRow
    parsed_input_price: Decimal | None = None
    parsed_observed_price: Decimal | None = None
    is_usable_for_pricing: bool = False


def _trim_required(raw_value: str) -> str:
    return raw_value.strip()


def validate_input_rows(loaded_csv: LoadedCsv) -> list[ValidatedInputRow]:
    validated_rows: list[ValidatedInputRow] = []
    resolution = loaded_csv.resolution

    for index, raw_row in enumerate(loaded_csv.rows, start=2):
        model = _trim_required(raw_row[resolution.canonical_to_actual["model"]])
        mpn = _trim_required(raw_row[resolution.canonical_to_actual["mpn"]])
        price = _trim_required(raw_row[resolution.canonical_to_actual["price"]])
        extras = {header: raw_row.get(header, "") for header in resolution.extra_headers}

        input_row = InputRow(
            row_number=index,
            model=model,
            mpn=mpn,
            price=price,
            original_values={header: raw_row.get(header, "") for header in loaded_csv.headers},
            extra_values=extras,
        )

        error_reason, parsed_price = _validate_input_row(input_row)
        validated_rows.append(
            ValidatedInputRow(
                row=input_row,
                error_reason=error_reason,
                parsed_price=parsed_price,
            )
        )

    return validated_rows


def _validate_input_row(row: InputRow) -> tuple[str, Decimal | None]:
    if not row.model:
        return "missing required row value: model", None
    if not row.mpn:
        return "missing required row value: mpn", None
    if not row.price:
        return "missing required row value: price", None

    try:
        parsed_price = parse_dot_decimal_text(row.price)
    except ValueError as exc:
        return str(exc), None
    return "", parsed_price


def validate_enriched_rows(loaded_csv: LoadedCsv) -> list[ValidatedEnrichedRow]:
    validated_rows: list[ValidatedEnrichedRow] = []
    resolution = loaded_csv.resolution
    source_name = detect_enriched_source(loaded_csv.headers)
    contract = get_fetch_source_contract(source_name)

    for raw_row in loaded_csv.rows:
        model = _trim_required(raw_row[resolution.canonical_to_actual["model"]])
        mpn = _trim_required(raw_row[resolution.canonical_to_actual["mpn"]])
        price = _trim_required(raw_row[resolution.canonical_to_actual["price"]])
        observed_price = _trim_required(raw_row[resolution.canonical_to_actual[contract.price_column]])
        observed_url = _trim_required(raw_row[resolution.canonical_to_actual[contract.url_column]])
        match_status = _trim_required(raw_row[resolution.canonical_to_actual["match_status"]])
        observed_at = _trim_required(raw_row[resolution.canonical_to_actual["observed_at"]])
        error_reason = _trim_required(raw_row[resolution.canonical_to_actual["error_reason"]])
        price_relation = _trim_required(raw_row[resolution.canonical_to_actual["price_relation"]])
        price_delta = _trim_required(raw_row[resolution.canonical_to_actual["price_delta"]])
        matched_mpn = _trim_required(raw_row[resolution.canonical_to_actual["matched_mpn"]])
        source_extra_values = {
            header: _trim_required(raw_row.get(header, ""))
            for header in contract.source_extra_columns
        }

        priced_row = PricedRow(
            model=model,
            mpn=mpn,
            price=price,
            observed_price=observed_price,
            new_price="",
            observed_url=observed_url,
            match_status=match_status,
            observed_at=observed_at,
            error_reason=error_reason,
            price_relation=price_relation,
            price_delta=price_delta,
            matched_mpn=matched_mpn,
            source_extra_values=source_extra_values,
        )
        price_only_row = PriceOnlyRow(model=model, mpn=mpn, price=price)
        parsed_input_price = _try_parse_price(price)
        parsed_observed_price = _try_parse_price(observed_price) if observed_price else None
        is_usable_for_pricing = (
            match_status == "matched"
            and parsed_input_price is not None
            and parsed_observed_price is not None
        )
        validated_rows.append(
            ValidatedEnrichedRow(
                source_name=source_name,
                priced_row=priced_row,
                price_only_row=price_only_row,
                parsed_input_price=parsed_input_price,
                parsed_observed_price=parsed_observed_price,
                is_usable_for_pricing=is_usable_for_pricing,
            )
        )

    return validated_rows


def _try_parse_price(value: str) -> Decimal | None:
    try:
        return parse_dot_decimal_text(value)
    except ValueError:
        return None
