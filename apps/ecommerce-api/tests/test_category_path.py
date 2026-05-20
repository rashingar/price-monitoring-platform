import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.catalog.category_path import parse_opencart_category  # noqa: E402


def test_parse_three_level_serialized_category() -> None:
    raw = (
        "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ:::"
        "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Σκεύη Μαγειρικής:::"
        "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Σκεύη Μαγειρικής///Γάστρες"
    )

    parsed = parse_opencart_category(raw)

    assert parsed.raw == raw
    assert parsed.family == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"
    assert parsed.category_name == "Σκεύη Μαγειρικής"
    assert parsed.sub_category == "Γάστρες"
    assert parsed.levels == ["ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ", "Σκεύη Μαγειρικής", "Γάστρες"]


def test_parse_two_level_serialized_category() -> None:
    parsed = parse_opencart_category(
        "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ:::ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ///Απορροφητήρες"
    )

    assert parsed.family == "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ"
    assert parsed.category_name == "Απορροφητήρες"
    assert parsed.sub_category == ""
    assert parsed.levels == ["ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ", "Απορροφητήρες"]


def test_parse_plain_or_malformed_category() -> None:
    plain = parse_opencart_category(" Plain Value ")
    malformed = parse_opencart_category("::: /// ::: Broken /// Value ")

    assert plain.family == "Plain Value"
    assert plain.category_name == ""
    assert plain.sub_category == ""
    assert plain.levels == ["Plain Value"]
    assert malformed.family == "Broken"
    assert malformed.category_name == "Value"
    assert malformed.sub_category == ""
    assert malformed.levels == ["Broken", "Value"]


def test_parse_empty_or_null_category() -> None:
    assert parse_opencart_category("").levels == []
    assert parse_opencart_category(None).levels == []
