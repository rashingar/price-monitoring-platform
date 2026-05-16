from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class CLIInput:
    model: str
    url: str
    photos: int = 1
    sections: int = 0
    bestprice_status: int = 1
    skroutz_status: int = 0
    boxnow: int = 0
    price: str | float | int = 0
    gallery_url: str | None = None
    characteristics_url: str | None = None
    second_opencart_image_index: int | None = None
    gallery_mode: str | None = None
    out: str = "out"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FetchResult:
    url: str
    final_url: str
    html: str
    status_code: int
    method: str
    fallback_used: bool = False
    response_headers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class GalleryImage:
    url: str
    alt: str = ""
    position: int = 0
    local_filename: str = ""
    local_path: str = ""
    content_type: str = ""
    downloaded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SpecItem:
    label: str
    value: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SpecSection:
    section: str
    items: list[SpecItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"section": self.section, "items": [item.to_dict() for item in self.items]}


@dataclass(slots=True)
class NormalizedPresentationSectionMetrics:
    word_count: int = 0
    alphabetic_char_count: int = 0
    char_count: int = 0
    alpha_ratio: float = 0.0
    unique_word_ratio: float = 0.0
    has_title: bool = False
    has_image: bool = False
    is_duplicate: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NormalizedPresentationSection:
    source_index: int = 0
    title: str = ""
    body_text: str = ""
    image_url: str = ""
    quality: str = "missing"
    reason: str = "missing_extraction"
    metrics: NormalizedPresentationSectionMetrics = field(default_factory=NormalizedPresentationSectionMetrics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_index": self.source_index,
            "title": self.title,
            "body_text": self.body_text,
            "image_url": self.image_url,
            "quality": self.quality,
            "reason": self.reason,
            "metrics": self.metrics.to_dict(),
        }


@dataclass(slots=True)
class SelectorTraceEntry:
    strategy: str
    selector: str = ""
    match_count: int = 0
    success: bool = False
    chosen_preview: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FieldDiagnostic:
    confidence: float = 0.0
    selected_strategy: str = ""
    value_present: bool = False
    value_preview: str = ""
    selector_trace: list[SelectorTraceEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "selected_strategy": self.selected_strategy,
            "value_present": self.value_present,
            "value_preview": self.value_preview,
            "selector_trace": [item.to_dict() for item in self.selector_trace],
        }


@dataclass(slots=True)
class SourceProductData:
    source_name: str = ""
    page_type: str = "product"
    url: str = ""
    canonical_url: str = ""
    breadcrumbs: list[str] = field(default_factory=list)
    skroutz_family: str = ""
    category_tag_text: str = ""
    category_tag_href: str = ""
    category_tag_slug: str = ""
    taxonomy_source_category: str = ""
    taxonomy_match_type: str = ""
    taxonomy_rule_id: str = ""
    taxonomy_ambiguity: bool = False
    taxonomy_escalation_reason: str = ""
    taxonomy_tv_inches: Optional[int] = None
    product_code: str = ""
    brand: str = ""
    name: str = ""
    hero_summary: str = ""
    price_text: str = ""
    price_value: Optional[float] = None
    installments_text: str = ""
    delivery_text: str = ""
    pickup_text: str = ""
    gallery_images: list[GalleryImage] = field(default_factory=list)
    besco_images: list[GalleryImage] = field(default_factory=list)
    energy_label_asset_url: str = ""
    product_sheet_asset_url: str = ""
    key_specs: list[SpecItem] = field(default_factory=list)
    spec_sections: list[SpecSection] = field(default_factory=list)
    manufacturer_spec_sections: list[SpecSection] = field(default_factory=list)
    manufacturer_source_text: str = ""
    manufacturer_documents: list[dict[str, Any]] = field(default_factory=list)
    presentation_source_html: str = ""
    presentation_source_text: str = ""
    raw_html_path: str = ""
    scraped_at: str = ""
    fallback_used: bool = False
    mpn: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "page_type": self.page_type,
            "url": self.url,
            "canonical_url": self.canonical_url,
            "breadcrumbs": self.breadcrumbs,
            "skroutz_family": self.skroutz_family,
            "category_tag_text": self.category_tag_text,
            "category_tag_href": self.category_tag_href,
            "category_tag_slug": self.category_tag_slug,
            "taxonomy_source_category": self.taxonomy_source_category,
            "taxonomy_match_type": self.taxonomy_match_type,
            "taxonomy_rule_id": self.taxonomy_rule_id,
            "taxonomy_ambiguity": self.taxonomy_ambiguity,
            "taxonomy_escalation_reason": self.taxonomy_escalation_reason,
            "taxonomy_tv_inches": self.taxonomy_tv_inches,
            "product_code": self.product_code,
            "brand": self.brand,
            "name": self.name,
            "hero_summary": self.hero_summary,
            "price_text": self.price_text,
            "price_value": self.price_value,
            "installments_text": self.installments_text,
            "delivery_text": self.delivery_text,
            "pickup_text": self.pickup_text,
            "gallery_images": [img.to_dict() for img in self.gallery_images],
            "besco_images": [img.to_dict() for img in self.besco_images],
            "energy_label_asset_url": self.energy_label_asset_url,
            "product_sheet_asset_url": self.product_sheet_asset_url,
            "key_specs": [item.to_dict() for item in self.key_specs],
            "spec_sections": [section.to_dict() for section in self.spec_sections],
            "manufacturer_spec_sections": [section.to_dict() for section in self.manufacturer_spec_sections],
            "manufacturer_source_text": self.manufacturer_source_text,
            "manufacturer_documents": self.manufacturer_documents,
            "presentation_source_html": self.presentation_source_html,
            "presentation_source_text": self.presentation_source_text,
            "raw_html_path": self.raw_html_path,
            "scraped_at": self.scraped_at,
            "fallback_used": self.fallback_used,
            "mpn": self.mpn,
        }


@dataclass(slots=True)
class ParsedProduct:
    source: SourceProductData
    provenance: dict[str, str] = field(default_factory=dict)
    field_diagnostics: dict[str, FieldDiagnostic] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    critical_missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "provenance": self.provenance,
            "field_diagnostics": {key: value.to_dict() for key, value in self.field_diagnostics.items()},
            "missing_fields": self.missing_fields,
            "warnings": self.warnings,
            "critical_missing": self.critical_missing,
        }


@dataclass(slots=True)
class TaxonomyResolution:
    category_id: str = ""
    parent_category: str = ""
    leaf_category: str = ""
    sub_category: Optional[str] = None
    taxonomy_path: str = ""
    cta_url: str = ""
    confidence: float = 0.0
    reason: str = ""
    gender: str = ""
    plural_label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SchemaMatchResult:
    matched_schema_id: Optional[str] = None
    matched_sub_category: Optional[str] = None
    score: float = 0.0
    warnings: list[str] = field(default_factory=list)
    subcategory_match_policy: str = ""
    resolved_category_path: str = ""
    candidate_pool_size: int = 0
    candidate_template_ids: list[str] = field(default_factory=list)
    selected_template_id: Optional[str] = None
    match_mode: str = ""
    hard_gate_failures: list[dict[str, Any]] = field(default_factory=list)
    fail_reason: str = ""
    discriminator_hits: list[str] = field(default_factory=list)
    discriminator_misses: list[str] = field(default_factory=list)
    section_overlap_score: float = 0.0
    label_overlap_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
