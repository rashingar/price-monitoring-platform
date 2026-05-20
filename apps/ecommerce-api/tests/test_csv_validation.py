import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.core.price_workflow import run_price
from ecommerce.core.validation import validate_input_rows
from ecommerce.io.csv_reader import load_csv
from ecommerce.schemas import INPUT_REQUIRED_COLUMNS, get_fetch_source_contract


def test_case_insensitive_required_columns_and_row_validation(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    input_csv.write_text(
        "MODEL,Mpn,Price,Color\n"
        "  Phone X  ,  ABC  , 178.99 ,Black\n"
        "Tablet,XYZ,12.50,Silver\n",
        encoding="utf-8-sig",
    )

    loaded_csv = load_csv(input_csv, INPUT_REQUIRED_COLUMNS, "utf-8-sig")
    assert loaded_csv.resolution.canonical_to_actual == {
        "model": "MODEL",
        "mpn": "Mpn",
        "price": "Price",
    }
    assert loaded_csv.resolution.extra_headers == ["Color"]

    validated_rows = validate_input_rows(loaded_csv)
    assert validated_rows[0].row.model == "Phone X"
    assert validated_rows[0].row.mpn == "ABC"
    assert validated_rows[0].row.price == "178.99"
    assert validated_rows[0].error_reason == ""

    assert validated_rows[1].row.price == "12.50"
    assert validated_rows[1].error_reason == ""


def test_invalid_input_price_format_is_reported(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    input_csv.write_text(
        "model,mpn,price\n" 'Phone X,ABC,"178,99"\n',
        encoding="utf-8-sig",
    )

    loaded_csv = load_csv(input_csv, INPUT_REQUIRED_COLUMNS, "utf-8-sig")
    validated_rows = validate_input_rows(loaded_csv)
    assert validated_rows[0].error_reason == "invalid input price format"


def test_price_fails_whole_run_when_required_enriched_columns_are_missing(
    tmp_path: Path,
) -> None:
    enriched_csv = tmp_path / "export_skroutz_enriched.csv"
    reduced_headers = [
        header
        for header in get_fetch_source_contract("skroutz").required_enriched_columns
        if header != "matched_mpn"
    ]
    enriched_csv.write_text(
        ",".join(reduced_headers) + "\n" "Phone X,ABC,178.99,,,,,,,,\n",
        encoding="utf-8-sig",
    )

    rule_config = PROJECT_ROOT / "config" / "pricing" / "default_rule.json"
    with pytest.raises(ValueError, match="matched_mpn"):
        run_price(enriched_csv, rule_config, output_dir_override=str(tmp_path / "out"))
