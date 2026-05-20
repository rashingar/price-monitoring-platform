"""Parse compact Telegram Product Factory commands."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

_MODEL_RE = re.compile(r"^\d{6}$")
_ACCEPTED_FLAG_SEQUENCES = {
    (): (False, False, False),
    ("B",): (True, False, False),
    ("S",): (False, True, False),
    ("B", "S"): (True, True, False),
    ("B", "B"): (True, False, True),
    ("S", "B"): (False, True, True),
    ("B", "S", "B"): (True, True, True),
}


@dataclass(frozen=True)
class ProductFactoryCommand:
    model: str
    bestprice_enabled: bool
    skroutz_enabled: bool
    boxnow_enabled: bool
    manual_url: str | None = None


class ProductFactoryCommandParseError(ValueError):
    """Raised when a Telegram command cannot be parsed."""


def parse_product_factory_command(text: str) -> ProductFactoryCommand:
    tokens = str(text or "").split()
    if not tokens:
        raise ProductFactoryCommandParseError("Command is empty.")

    model = tokens[0]
    if not _MODEL_RE.fullmatch(model):
        raise ProductFactoryCommandParseError("Model must be a 6-digit string.")

    remaining = tokens[1:]
    manual_url: str | None = None
    if remaining:
        url_index = _url_token_index(remaining)
        if url_index is not None:
            if url_index != len(remaining) - 1:
                raise ProductFactoryCommandParseError(
                    "Manual URL must be the final token."
                )
            manual_url = _validate_manual_url(remaining[url_index])
            remaining = remaining[:url_index]

    flag_sequence = tuple(token.upper() for token in remaining)
    if any(token not in {"B", "S"} for token in flag_sequence):
        raise ProductFactoryCommandParseError("Unknown flag token.")
    if flag_sequence not in _ACCEPTED_FLAG_SEQUENCES:
        raise ProductFactoryCommandParseError("Invalid or duplicate flag sequence.")

    bestprice_enabled, skroutz_enabled, boxnow_enabled = _ACCEPTED_FLAG_SEQUENCES[
        flag_sequence
    ]
    return ProductFactoryCommand(
        model=model,
        bestprice_enabled=bestprice_enabled,
        skroutz_enabled=skroutz_enabled,
        boxnow_enabled=boxnow_enabled,
        manual_url=manual_url,
    )


def _url_token_index(tokens: list[str]) -> int | None:
    for index, token in enumerate(tokens):
        parts = urlsplit(token)
        if parts.scheme or "://" in token:
            return index
    return None


def _validate_manual_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ProductFactoryCommandParseError(
            "Manual URL must be an absolute http/https URL."
        )
    return value
