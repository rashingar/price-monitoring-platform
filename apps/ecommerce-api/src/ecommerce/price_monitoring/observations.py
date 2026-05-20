"""Tolerant parsing of fetch-enriched CSV rows into price observations."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from ecommerce.catalog.source_catalog import DEFAULT_CATALOG_SOURCE

NORMALIZED_COLUMN_RE = re.compile(r"[^a-z0-9_]+")
UNDERSCORE_RE = re.compile(r"_+")


@dataclass(frozen=True)
class ParsedPriceObservation:
    run_id: str
    catalog_source: str
    source: str
    model: str | None
    mpn: str | None
    product_name: str | None
    competitor_name: str | None
    competitor_price: Decimal | None
    currency: str
    availability: str | None
    product_url: str | None
    own_price: Decimal | None
    price_delta: Decimal | None
    price_delta_percent: Decimal | None
    raw_observation: dict[str, Any]
    observed_at: datetime


@dataclass(frozen=True)
class ParsedPriceObservationsResult:
    observations: list[ParsedPriceObservation]
    warnings: list[str]


def parse_price_observations_csv(
    path: Path,
    *,
    run_id: str,
    source: str,
    catalog_source: str = DEFAULT_CATALOG_SOURCE,
    default_observed_at: datetime | str | None = None,
) -> ParsedPriceObservationsResult:
    rows = _read_csv(path)
    default_observed = _parse_datetime(default_observed_at) or _now()
    observations: list[ParsedPriceObservation] = []
    warnings: list[str] = []

    for row_number, row in enumerate(rows, start=2):
        observation, row_warnings = _parse_row(
            row,
            run_id=run_id,
            catalog_source=catalog_source,
            source=source,
            default_observed_at=default_observed,
            row_number=row_number,
        )
        warnings.extend(row_warnings)
        if observation is not None:
            observations.append(observation)

    if not observations:
        warnings.append(f"No parseable price observations found in {path}.")
    return ParsedPriceObservationsResult(observations=observations, warnings=warnings)


def _parse_row(
    row: dict[str, str],
    *,
    run_id: str,
    catalog_source: str,
    source: str,
    default_observed_at: datetime,
    row_number: int,
) -> tuple[ParsedPriceObservation | None, list[str]]:
    warnings: list[str] = []
    normalized = {_normalize_column(key): key for key in row.keys() if key is not None}
    resolved_source = _first_text(row, normalized, ("source", "marketplace")) or source
    source_key = _normalize_column(resolved_source or source)
    model = _first_text(row, normalized, ("model", "sku", "product_model"))
    mpn = _first_text(
        row, normalized, ("mpn", "manufacturer_part_number", "matched_mpn")
    )
    if not model and not mpn:
        warnings.append(f"Row {row_number} skipped: missing model and MPN.")
        return None, warnings

    competitor_column = _first_column(
        normalized,
        (
            f"{source_key}_price",
            f"{source_key}_best_store_price",
            f"{source_key}_next_store_price",
            "competitor_price",
            "fetched_price",
            "source_price",
            "marketplace_price",
            "best_price",
            "observed_price",
            "price_found",
            "target_price",
            "bestprice_price",
            "bestprice_best_store_price",
            "bestprice_next_store_price",
            "skroutz_price",
            "price",
        ),
    )
    competitor_price, competitor_warning = _parse_decimal_with_warning(
        row.get(competitor_column) if competitor_column else None,
        row_number=row_number,
        field_name="competitor_price",
    )
    if competitor_warning:
        warnings.append(competitor_warning)

    own_aliases = (
        "own_price",
        "our_price",
        "current_price",
        "internal_price",
        "input_price",
        "original_price",
        "catalog_price",
    )
    if competitor_column and _normalize_column(competitor_column) != "price":
        own_aliases = own_aliases + ("price",)
    own_price, own_warning = _parse_decimal_with_warning(
        _first_raw(row, normalized, own_aliases),
        row_number=row_number,
        field_name="own_price",
    )
    if own_warning:
        warnings.append(own_warning)
    price_delta = _parse_decimal(_first_raw(row, normalized, ("price_delta", "delta")))
    if price_delta is None and own_price is not None and competitor_price is not None:
        # Positive values mean our own catalog price is higher than the competitor/source price.
        price_delta = own_price - competitor_price
    price_delta_percent = _parse_decimal(
        _first_raw(row, normalized, ("price_delta_percent", "delta_percent"))
    )
    if (
        price_delta_percent is None
        and price_delta is not None
        and own_price is not None
        and own_price != 0
    ):
        price_delta_percent = (price_delta / own_price) * Decimal("100")

    return (
        ParsedPriceObservation(
            run_id=run_id,
            catalog_source=_text(catalog_source) or DEFAULT_CATALOG_SOURCE,
            source=(resolved_source or source).strip().lower(),
            model=_empty_to_none(model),
            mpn=_empty_to_none(mpn),
            product_name=_empty_to_none(
                _first_text(row, normalized, ("name", "product_name", "title"))
            ),
            competitor_name=_empty_to_none(
                _first_text(
                    row,
                    normalized,
                    (
                        "seller",
                        "store",
                        "competitor",
                        "shop",
                        "competitor_name",
                        "competitor_store",
                        "marketplace",
                        "bestprice_best_store",
                        "bestprice_next_store",
                    ),
                )
            ),
            competitor_price=competitor_price,
            currency=_first_text(row, normalized, ("currency",)) or "EUR",
            availability=_empty_to_none(
                _first_text(row, normalized, ("availability", "stock_status", "status"))
            ),
            product_url=_empty_to_none(
                _first_text(
                    row,
                    normalized,
                    (
                        "url",
                        "product_url",
                        "source_url",
                        "marketplace_url",
                        f"{source_key}_url",
                        "competitor_url",
                        "skroutz_url",
                        "bestprice_url",
                    ),
                )
            ),
            own_price=own_price,
            price_delta=price_delta,
            price_delta_percent=price_delta_percent,
            raw_observation=_json_safe_row(row),
            observed_at=_parse_datetime(
                _first_raw(row, normalized, ("observed_at", "created_at", "timestamp"))
            )
            or default_observed_at,
        ),
        warnings,
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        reader = csv.DictReader(f, delimiter=_detect_delimiter(sample))
        return [
            {key: value if value is not None else "" for key, value in row.items()}
            for row in reader
        ]


def _detect_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        if dialect.delimiter in {",", ";", "\t"}:
            return dialect.delimiter
    except csv.Error:
        pass
    if sample.count(";") > sample.count(","):
        return ";"
    return ","


def _first_text(
    row: dict[str, str], normalized: dict[str, str], aliases: tuple[str, ...]
) -> str:
    value = _first_raw(row, normalized, aliases)
    return _text(value)


def _first_raw(
    row: dict[str, str], normalized: dict[str, str], aliases: tuple[str, ...]
) -> str:
    column = _first_column(normalized, aliases)
    if column is None:
        return ""
    return row.get(column, "")


def _first_column(normalized: dict[str, str], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        column = normalized.get(_normalize_column(alias))
        if column is not None:
            return column
    return None


def _normalize_column(value: object) -> str:
    text = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    text = NORMALIZED_COLUMN_RE.sub("_", text)
    return UNDERSCORE_RE.sub("_", text).strip("_")


def _parse_decimal(value: object) -> Decimal | None:
    parsed, _warning = _parse_decimal_with_warning(
        value, row_number=None, field_name=""
    )
    return parsed


def _parse_decimal_with_warning(
    value: object,
    *,
    row_number: int | None,
    field_name: str,
) -> tuple[Decimal | None, str | None]:
    text = _text(value)
    if not text:
        return None, None
    cleaned = (
        text.replace("EUR", "").replace("€", "").replace(" ", "").replace(",", ".")
    )
    try:
        return Decimal(cleaned), None
    except InvalidOperation:
        if row_number is None:
            return None, None
        return None, f"Row {row_number} has malformed {field_name}: {text}."


def _parse_datetime(value: datetime | str | None) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    text = _text(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    if "T" not in normalized and " " in normalized:
        normalized = normalized.replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _json_safe_row(row: dict[str, str]) -> dict[str, Any]:
    return json.loads(json.dumps(row, ensure_ascii=False, default=str))


def _empty_to_none(value: str) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
