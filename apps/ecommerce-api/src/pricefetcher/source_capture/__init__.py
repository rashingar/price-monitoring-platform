"""Shared source capture layer for product source ingestion and monitoring."""

from pricefetcher.source_capture.canonicalize_url import canonical_url_hash, canonicalize_url
from pricefetcher.source_capture.detect_vendor import detect_vendor_slug
from pricefetcher.source_capture.runner import CaptureError, capture_source_url
from pricefetcher.source_capture.scoring import score_response_candidate

__all__ = [
    "CaptureError",
    "canonical_url_hash",
    "canonicalize_url",
    "capture_source_url",
    "detect_vendor_slug",
    "score_response_candidate",
]
