"""Compatibility import for the price observation parser."""

from pricefetcher.price_monitoring.observations import (
    ParsedPriceObservation,
    ParsedPriceObservationsResult,
    parse_price_observations_csv,
)

__all__ = [
    "ParsedPriceObservation",
    "ParsedPriceObservationsResult",
    "parse_price_observations_csv",
]
