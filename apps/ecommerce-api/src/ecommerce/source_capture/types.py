from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

CAPTURE_VERSION = "source-capture-v1"


@dataclass(frozen=True)
class VendorDefinition:
    slug: str
    name: str
    base_url: str
    vendor_type: str
    active: bool
    supports_direct_product_url: bool
    supports_search: bool
    supports_xhr_capture: bool
    domains: tuple[str, ...]


@dataclass(frozen=True)
class ResponseCandidate:
    url: str
    method: str = "GET"
    status: int | None = None
    content_type: str = ""
    body_text: str = ""
    body_json: Any | None = None
    network_event_type: str = "response"
    trigger_action: str | None = None
    occurred_after_trigger: bool = False


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: ResponseCandidate
    score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ParsedPriceObservation:
    price: Decimal | None
    original_price: Decimal | None = None
    currency: str = "EUR"
    discount_percent: Decimal | None = None
    availability: str | None = None
    stock_status: str | None = None
    shipping_cost: Decimal | None = None
    delivery_text: str | None = None
    seller_name: str | None = None
    product_name: str | None = None
    raw_observation: dict[str, Any] = field(default_factory=dict)
    timestamp_source: str | None = None
    timestamp_quality: str | None = None


@dataclass(frozen=True)
class ParsedOfferObservation:
    seller_name: str | None
    price: Decimal | None
    seller_url: str | None = None
    original_price: Decimal | None = None
    currency: str = "EUR"
    availability: str | None = None
    stock_status: str | None = None
    shipping_cost: Decimal | None = None
    delivery_text: str | None = None
    raw_observation: dict[str, Any] = field(default_factory=dict)
    timestamp_source: str | None = None
    timestamp_quality: str | None = None


@dataclass(frozen=True)
class CaptureSnapshotPayload:
    capture_strategy: str
    page_url: str
    final_url: str | None = None
    request_url: str | None = None
    request_method: str | None = None
    response_status: int | None = None
    response_content_type: str | None = None
    response_body_json: dict[str, Any] | list[Any] | None = None
    response_body_text: str | None = None
    raw_html: str | None = None
    artifact_ref: str | None = None
    content_hash: str | None = None
    parser_version: str | None = None
    capture_version: str = CAPTURE_VERSION
    playwright_version: str | None = None
    fetch_status_code: int | None = None
    fetch_latency_ms: int | None = None
    candidate_score: int | None = None
    candidate_reason: str | None = None
    network_event_type: str | None = None
    trigger_action: str | None = None
    data_quality_flags: list[str] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    captured_at: datetime | None = None
    fetched_at: datetime | None = None
    parsed_at: datetime | None = None
    imported_at: datetime | None = None


@dataclass(frozen=True)
class CaptureResult:
    vendor_slug: str
    status: str
    snapshot: CaptureSnapshotPayload
    price_observations: tuple[ParsedPriceObservation, ...] = ()
    offer_observations: tuple[ParsedOfferObservation, ...] = ()
    error_code: str | None = None
    error_message: str | None = None

    @property
    def successful(self) -> bool:
        return self.status == "success"
