"""Pricing workflow for Milestone 5."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ecommerce.core.validation import validate_enriched_rows
from ecommerce.io.csv_reader import load_csv
from ecommerce.io.csv_writer import IncrementalCsvWriter
from ecommerce.io.json_writer import write_json
from ecommerce.io.paths import (
    PriceOutputPaths,
    ensure_output_dir,
    load_runtime_config,
    resolve_output_dir,
    resolve_price_output_paths,
)
from ecommerce.schemas import (
    INPUT_REQUIRED_COLUMNS,
    PRICE_ONLY_COLUMNS,
    PriceOnlyRow,
    PricedRow,
    PricingSummary,
    ROUNDING_MODES,
    RULE_FAMILIES,
    detect_enriched_source,
    get_fetch_source_contract,
)
from ecommerce.pricing.engine import PricingContext, PricingRule, compute_new_price
from ecommerce.utils.timestamps import format_greece_timestamp


@dataclass(frozen=True)
class PriceRunResult:
    output_paths: PriceOutputPaths
    summary: PricingSummary


def run_price(
    input_path: Path,
    rule_config_path: Path,
    output_dir_override: str | None = None,
) -> PriceRunResult:
    runtime_config = load_runtime_config()
    pricing_rule = _load_pricing_rule_config(rule_config_path)
    output_dir = ensure_output_dir(
        resolve_output_dir(output_dir_override, runtime_config)
    )
    output_paths = resolve_price_output_paths(input_path, output_dir)

    started_at = format_greece_timestamp()
    preview_csv = load_csv(
        path=input_path,
        required_columns=INPUT_REQUIRED_COLUMNS,
        encoding=runtime_config.csv_encoding,
    )
    source_name = detect_enriched_source(preview_csv.headers)
    source_contract = get_fetch_source_contract(source_name)
    loaded_csv = load_csv(
        path=input_path,
        required_columns=source_contract.required_enriched_columns,
        encoding=runtime_config.csv_encoding,
    )
    _validate_rule_against_source_columns(pricing_rule, source_name, loaded_csv.headers)
    validated_rows = validate_enriched_rows(loaded_csv)

    priced_rows_count = 0
    blank_new_price_rows = 0
    processed_priced_rows: list[PricedRow] = []
    with IncrementalCsvWriter(
        output_paths.priced_enriched_csv,
        list(source_contract.priced_output_columns),
        runtime_config.csv_encoding,
    ) as priced_writer:
        for validated_row in validated_rows:
            priced_row = validated_row.priced_row
            if (
                validated_row.is_usable_for_pricing
                and validated_row.parsed_observed_price is not None
            ):
                new_price = compute_new_price(
                    pricing_rule,
                    validated_row.parsed_observed_price,
                    pricing_context=PricingContext(
                        source_name=validated_row.source_name,
                        observed_price=validated_row.parsed_observed_price,
                        input_price=validated_row.parsed_input_price,
                        source_extra_values=priced_row.source_extra_values,
                    ),
                )
                priced_row = PricedRow(
                    model=priced_row.model,
                    mpn=priced_row.mpn,
                    price=priced_row.price,
                    observed_price=priced_row.observed_price,
                    new_price=new_price,
                    observed_url=priced_row.observed_url,
                    match_status=priced_row.match_status,
                    observed_at=priced_row.observed_at,
                    error_reason=priced_row.error_reason,
                    price_relation=priced_row.price_relation,
                    price_delta=priced_row.price_delta,
                    matched_mpn=priced_row.matched_mpn,
                    source_extra_values=priced_row.source_extra_values,
                )
                priced_rows_count += 1
            else:
                blank_new_price_rows += 1
            priced_writer.write_row(
                priced_row.to_csv_row(
                    price_column=source_contract.price_column,
                    url_column=source_contract.url_column,
                    source_extra_headers=source_contract.source_extra_columns,
                )
            )
            processed_priced_rows.append(priced_row)

    with IncrementalCsvWriter(
        output_paths.price_only_csv,
        list(PRICE_ONLY_COLUMNS),
        runtime_config.csv_encoding,
    ) as price_only_writer:
        for validated_row, priced_row in zip(
            validated_rows, processed_priced_rows, strict=True
        ):
            output_price = (
                priced_row.new_price
                if priced_row.new_price
                else validated_row.price_only_row.price
            )
            price_only_writer.write_row(
                PriceOnlyRow(
                    model=validated_row.price_only_row.model,
                    mpn=validated_row.price_only_row.mpn,
                    price=output_price,
                ).to_csv_row()
            )

    summary = PricingSummary(
        operation="price",
        source=source_name,
        input_file=str(input_path),
        output_files=[
            str(output_paths.priced_enriched_csv),
            str(output_paths.price_only_csv),
        ],
        started_at=started_at,
        finished_at=format_greece_timestamp(),
        total_rows=len(validated_rows),
        priced_rows=priced_rows_count,
        blank_new_price_rows=blank_new_price_rows,
    )
    write_json(
        output_paths.summary_json, summary.to_dict(), runtime_config.csv_encoding
    )
    return PriceRunResult(output_paths=output_paths, summary=summary)


def _load_pricing_rule_config(rule_config_path: Path) -> PricingRule:
    with rule_config_path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError("pricing rule config must be a JSON object")

    rule_family = payload.get("rule_family")
    if rule_family not in RULE_FAMILIES:
        supported = ", ".join(RULE_FAMILIES)
        raise ValueError(
            f"unsupported rule_family in pricing config: {rule_family}. Supported: {supported}"
        )

    rounding_mode = payload.get("rounding_mode")
    if rounding_mode is not None and rounding_mode not in ROUNDING_MODES:
        supported = ", ".join(ROUNDING_MODES)
        raise ValueError(
            f"unsupported rounding_mode in pricing config: {rounding_mode}. Supported: {supported}"
        )

    parameters = payload.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("pricing rule config parameters must be a JSON object")

    return PricingRule(
        rule_family=str(rule_family),
        parameters=parameters,
        rounding_mode=str(rounding_mode) if rounding_mode is not None else None,
    )


def _validate_rule_against_source_columns(
    pricing_rule: PricingRule,
    source_name: str,
    headers: list[str],
) -> None:
    if pricing_rule.rule_family != "bestprice_store_positioning":
        return
    if source_name != "bestprice":
        raise ValueError(
            "bestprice_store_positioning requires a BestPrice enriched CSV"
        )

    required_headers = (
        "bestprice_best_store",
        "bestprice_best_store_price",
        "bestprice_next_store",
        "bestprice_next_store_price",
    )
    missing = [header for header in required_headers if header not in headers]
    if missing:
        details = ", ".join(missing)
        raise ValueError(
            "bestprice_store_positioning requires BestPrice ladder columns from a fresh fetch run "
            f"({details})"
        )
