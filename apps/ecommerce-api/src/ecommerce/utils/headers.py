"""Header-resolution helpers with case-insensitive required-column support."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HeaderResolution:
    canonical_to_actual: dict[str, str]
    extra_headers: list[str]
    original_headers: list[str]


def resolve_required_headers(
    headers: list[str],
    required_columns: tuple[str, ...],
) -> HeaderResolution:
    if not headers:
        raise ValueError("CSV header row is missing")

    lowered_map: dict[str, list[str]] = {}
    for header in headers:
        lowered_map.setdefault(header.casefold(), []).append(header)

    canonical_to_actual: dict[str, str] = {}
    for canonical in required_columns:
        matches = lowered_map.get(canonical.casefold(), [])
        if not matches:
            raise ValueError(f"missing required column: {canonical}")
        if len(matches) > 1:
            joined = ", ".join(matches)
            raise ValueError(
                f"multiple columns matched required field '{canonical}': {joined}"
            )
        canonical_to_actual[canonical] = matches[0]

    required_actual_headers = {
        canonical_to_actual[column] for column in required_columns
    }
    extra_headers = [
        header for header in headers if header not in required_actual_headers
    ]
    return HeaderResolution(
        canonical_to_actual=canonical_to_actual,
        extra_headers=extra_headers,
        original_headers=headers,
    )
