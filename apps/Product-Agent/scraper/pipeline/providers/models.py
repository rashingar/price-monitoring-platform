from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..models import FieldDiagnostic, SourceProductData


class ProviderKind(str, Enum):
    VENDOR_SITE = "vendor_site"
    MANUFACTURER_SITE = "manufacturer_site"
    FIXTURE = "fixture"


class ProviderCapability(str, Enum):
    URL_INPUT = "url_input"
    MODEL_INPUT = "model_input"
    SKU_INPUT = "sku_input"
    BRAND_MPN_INPUT = "brand_mpn_input"
    LIVE_FETCH = "live_fetch"
    FIXTURE_FETCH = "fixture_fetch"
    HTML_SNAPSHOT = "html_snapshot"
    JSON_SNAPSHOT = "json_snapshot"
    PDF_SNAPSHOT = "pdf_snapshot"
    NORMALIZED_PRODUCT = "normalized_product"


class ProviderSnapshotKind(str, Enum):
    HTML = "html"
    JSON = "json"
    PDF = "pdf"
    BINARY = "binary"
    TEXT = "text"
    FIXTURE = "fixture"


class ProviderStage(str, Enum):
    IDENTITY = "identity"
    FETCH = "fetch"
    NORMALIZE = "normalize"
    REGISTRY = "registry"


class ProviderErrorCode(str, Enum):
    UNSUPPORTED_IDENTITY = "unsupported_identity"
    NOT_FOUND = "not_found"
    FETCH_FAILED = "fetch_failed"
    RATE_LIMITED = "rate_limited"
    ACCESS_BLOCKED = "access_blocked"
    INVALID_RESPONSE = "invalid_response"
    NORMALIZATION_FAILED = "normalization_failed"
    REGISTRATION_FAILED = "registration_failed"
    INTERNAL_ERROR = "internal_error"


@dataclass(slots=True, frozen=True)
class ProviderDefinition:
    provider_id: str
    source_name: str
    kind: ProviderKind
    capabilities: frozenset[ProviderCapability] = field(default_factory=frozenset)
    display_name: str = ""
    description: str = ""


@dataclass(slots=True)
class ProviderInputIdentity:
    model: str = ""
    url: str = ""
    sku: str = ""
    brand: str = ""
    vendor_code: str = ""
    mpn: str = ""
    extra: dict[str, str | int | float | bool | None] = field(default_factory=dict)

    def present_fields(self) -> tuple[str, ...]:
        fields: list[str] = []
        if self.model:
            fields.append("model")
        if self.url:
            fields.append("url")
        if self.sku:
            fields.append("sku")
        if self.brand:
            fields.append("brand")
        if self.vendor_code:
            fields.append("vendor_code")
        if self.mpn:
            fields.append("mpn")
        fields.extend(sorted(self.extra))
        return tuple(fields)


@dataclass(slots=True)
class ProviderSnapshot:
    provider_id: str
    identity: ProviderInputIdentity
    snapshot_kind: ProviderSnapshotKind
    requested_url: str = ""
    final_url: str = ""
    content_type: str = ""
    status_code: int | None = None
    body_text: str = ""
    body_bytes: bytes = b""
    encoding: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderResult:
    provider: ProviderDefinition
    identity: ProviderInputIdentity
    snapshot: ProviderSnapshot
    product: SourceProductData
    provenance: dict[str, str] = field(default_factory=dict)
    field_diagnostics: dict[str, FieldDiagnostic] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    critical_missing: list[str] = field(default_factory=list)
    overall_confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ProviderErrorInfo:
    provider_id: str
    code: ProviderErrorCode
    stage: ProviderStage
    message: str
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)
