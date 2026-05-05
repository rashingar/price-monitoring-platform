"""Compatibility import for the price observation parser."""

from ecommerce.price_monitoring.observations import (
    ParsedPriceObservation,
    ParsedPriceObservationsResult,
    parse_price_observations_csv,
)

__all__ = [
    "ParsedPriceObservation",
    "ParsedPriceObservationsResult",
    "parse_price_observations_csv",
]
