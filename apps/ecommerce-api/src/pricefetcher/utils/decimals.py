"""Decimal parsing helpers for contract validation."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def parse_dot_decimal_text(value: str) -> Decimal:
    """Parse dot-decimal numeric text and reject unsupported formats."""

    text = value.strip()
    if not text:
        raise ValueError("missing required row value: price")
    if "," in text:
        raise ValueError("invalid input price format")
    if any(character in text.lower() for character in ("e", "+")):
        raise ValueError("invalid input price format")

    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("invalid input price format") from exc

    if parsed.is_nan() or parsed.is_infinite():
        raise ValueError("invalid input price format")
    if parsed < 0:
        raise ValueError("invalid input price format")
    return parsed


def format_decimal_two_places(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"
