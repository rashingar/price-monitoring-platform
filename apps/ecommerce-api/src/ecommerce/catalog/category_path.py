"""OpenCart category path parsing utilities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedCategoryPath:
    raw: str
    family: str
    category_name: str
    sub_category: str
    levels: list[str]


def parse_opencart_category(serialized_category: str | None) -> ParsedCategoryPath:
    """Parse an OpenCart serialized category path without raising on bad input."""
    raw = _text(serialized_category)
    if not raw:
        return ParsedCategoryPath(
            raw="", family="", category_name="", sub_category="", levels=[]
        )

    deepest_levels: list[str] = []
    for node in raw.split(":::"):
        levels = [_text(part) for part in node.split("///")]
        levels = [level for level in levels if level]
        if len(levels) >= len(deepest_levels):
            deepest_levels = levels

    family = deepest_levels[0] if len(deepest_levels) >= 1 else ""
    category_name = deepest_levels[1] if len(deepest_levels) >= 2 else ""
    sub_category = deepest_levels[2] if len(deepest_levels) >= 3 else ""
    return ParsedCategoryPath(
        raw=raw,
        family=family,
        category_name=category_name,
        sub_category=sub_category,
        levels=deepest_levels,
    )


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()
