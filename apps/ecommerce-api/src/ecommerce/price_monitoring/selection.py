"""Product selection for Price Monitoring run preparation."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from ecommerce.catalog import CatalogProduct
from ecommerce.catalog_db import load_active_catalog_products
from ecommerce.ignore import load_ignored_products

SourceName = str
DEFAULT_SOURCE_NAME = ""
MarketplaceFilter = Literal["bestprice", "skroutz", "both", "none"]
SOURCE_REQUIRED_MESSAGE = (
    "Price Monitoring requires exactly one source/vendor; provide one source_name, "
    "vendor_slug, source, or source_filter, and do not use all."
)
SKIPPED_REASON_KEYS = (
    "ignored",
    "non_atomic_model",
    "inactive",
    "missing_mpn",
    "missing_or_invalid_price",
    "explicitly_excluded",
    "missing_active_source_url",
)


@dataclass(frozen=True)
class SourceUrlProductCoverage:
    catalog_product_id: int | None
    active_source_url_count: int
    active_source_urls: list[dict[str, Any]]
    has_active_source_url: bool
    source_url_status_counts: dict[str, int]
    source_url_warning: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "catalog_product_id": self.catalog_product_id,
            "has_active_source_url": self.has_active_source_url,
            "active_source_url_count": self.active_source_url_count,
            "active_source_urls": self.active_source_urls,
            "status_counts": dict(self.source_url_status_counts),
            "source_url_status_counts": dict(self.source_url_status_counts),
            "warning": self.source_url_warning,
            "source_url_warning": self.source_url_warning,
        }


@dataclass(frozen=True)
class SourceUrlCoverageSummary:
    source: SourceName
    source_filter: SourceName | None
    selected_count: int
    products_with_active_source_urls: int
    products_without_active_source_urls: int
    coverage_percent: float
    active_source_url_count: int
    needs_review_source_url_count: int
    broken_source_url_count: int
    disabled_source_url_count: int
    redirected_source_url_count: int
    missing_source_url_models: list[str]
    missing_source_url_catalog_product_ids: list[int]
    warning: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PriceMonitoringFilters:
    q: str | None = None
    category: str | None = None
    family: str | None = None
    category_name: str | None = None
    sub_category: str | None = None
    manufacturer: str | None = None
    marketplace: MarketplaceFilter | None = None
    has_mpn: bool | None = True
    atomic_only: bool = True
    automation_eligible_only: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PriceMonitoringSelectionRequest:
    source: str = DEFAULT_SOURCE_NAME
    source_name: str | None = None
    vendor_slug: str | None = None
    source_filter: str | None = None
    filters: PriceMonitoringFilters = field(default_factory=PriceMonitoringFilters)
    selected_models: list[str] = field(default_factory=list)
    excluded_models: list[str] = field(default_factory=list)
    include_ignored: bool = False
    dry_run: bool = False


@dataclass(frozen=True)
class SelectedPriceMonitoringProduct:
    model: str
    mpn: str
    name: str
    manufacturer: str
    category: str
    raw_category: str
    family: str
    category_name: str
    sub_category: str
    category_levels: list[str]
    price: float
    source: SourceName
    source_filter: SourceName | None = None
    catalog_product_id: int | None = None
    source_url_coverage: SourceUrlProductCoverage | None = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["source_url_coverage"] = (
            self.source_url_coverage.to_dict() if self.source_url_coverage is not None else None
        )
        return payload


@dataclass(frozen=True)
class SkippedPriceMonitoringProduct:
    model: str
    reasons: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PriceMonitoringSelectionResult:
    source: SourceName
    source_filter: SourceName | None
    filters: PriceMonitoringFilters
    items: list[SelectedPriceMonitoringProduct]
    skipped: list[SkippedPriceMonitoringProduct]
    source_url_coverage: SourceUrlCoverageSummary | None = None
    source_url_required: bool = True

    @property
    def selected_count(self) -> int:
        return len(self.items)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    @property
    def skipped_by_reason(self) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for skipped_product in self.skipped:
            counts.update(skipped_product.reasons)
        return {reason: counts[reason] for reason in SKIPPED_REASON_KEYS if counts[reason]}


def select_price_monitoring_products(
    request: PriceMonitoringSelectionRequest,
    catalog_products: list[CatalogProduct] | None = None,
    ignored_models: set[str] | None = None,
) -> PriceMonitoringSelectionResult:
    source_filter = _source_filter_from_request(request)
    source = source_filter
    products = catalog_products if catalog_products is not None else load_active_catalog_products()
    ignored = ignored_models if ignored_models is not None else {product.model for product in load_ignored_products()}
    products_by_model = {_normalize_model(product.model): product for product in products}
    excluded_models = {_normalize_model(model) for model in request.excluded_models if _normalize_model(model)}

    candidates = _candidate_products(request, products, products_by_model)
    selected_items: list[SelectedPriceMonitoringProduct] = []
    skipped_items: list[SkippedPriceMonitoringProduct] = []

    for product in candidates:
        reasons = _skip_reasons(product, ignored, excluded_models, request.include_ignored)
        if reasons:
            skipped_items.append(SkippedPriceMonitoringProduct(model=product.model, reasons=reasons))
            continue
        selected_items.append(
            SelectedPriceMonitoringProduct(
                model=product.model,
                mpn=product.mpn,
                name=product.name,
                manufacturer=product.manufacturer,
                category=product.category,
                raw_category=product.raw_category,
                family=product.family,
                category_name=product.category_name,
                sub_category=product.sub_category,
                category_levels=product.category_levels,
                price=float(product.price),
                source=source,
                source_filter=source_filter,
                catalog_product_id=product.catalog_product_id,
            )
        )

    return PriceMonitoringSelectionResult(
        source=source,
        source_filter=source_filter,
        filters=request.filters,
        items=selected_items,
        skipped=skipped_items,
    )


def _source_filter_from_request(request: PriceMonitoringSelectionRequest) -> str | None:
    resolved: set[str] = set()
    for value in (request.source_filter, request.source_name, request.vendor_slug, request.source):
        text = str(value or "").strip().lower()
        if text == "all":
            raise ValueError(SOURCE_REQUIRED_MESSAGE)
        if not text:
            continue
        resolved.add(text)
    if not resolved:
        raise ValueError(SOURCE_REQUIRED_MESSAGE)
    if len(resolved) > 1:
        raise ValueError("Price Monitoring requires exactly one source/vendor; conflicting source values were provided.")
    return next(iter(resolved))


def _candidate_products(
    request: PriceMonitoringSelectionRequest,
    products: list[CatalogProduct],
    products_by_model: dict[str, CatalogProduct],
) -> list[CatalogProduct]:
    normalized_selected = [_normalize_model(model) for model in request.selected_models]
    normalized_selected = [model for model in normalized_selected if model]
    if normalized_selected:
        seen: set[str] = set()
        selected_products: list[CatalogProduct] = []
        for model in normalized_selected:
            if model in seen:
                continue
            seen.add(model)
            product = products_by_model.get(model)
            if product is not None:
                selected_products.append(product)
        return selected_products
    return [product for product in products if _matches_filters(product, request.filters)]


def _matches_filters(product: CatalogProduct, filters: PriceMonitoringFilters) -> bool:
    q_norm = filters.q.strip().casefold() if filters.q else ""
    category = _filter_value(filters.category)
    family = _filter_value(filters.family)
    category_name = _filter_value(filters.category_name)
    sub_category = _filter_value(filters.sub_category)
    manufacturer = _filter_value(filters.manufacturer)
    if q_norm:
        values = (product.model, product.mpn, product.name, product.manufacturer)
        if not any(q_norm in value.casefold() for value in values):
            return False
    if category is not None and product.category != category:
        return False
    if family is not None and product.family != family:
        return False
    if category_name is not None and product.category_name != category_name:
        return False
    if sub_category is not None and product.sub_category != sub_category:
        return False
    if manufacturer is not None and product.manufacturer != manufacturer:
        return False
    if filters.marketplace and not _matches_marketplace(product, filters.marketplace):
        return False
    if filters.has_mpn is not None and bool(product.mpn) is not filters.has_mpn:
        return False
    if filters.atomic_only and not product.is_atomic_model:
        return False
    if filters.automation_eligible_only and not product.automation_eligible:
        return False
    return True


def _matches_marketplace(product: CatalogProduct, marketplace: MarketplaceFilter) -> bool:
    bestprice = product.bestprice_status == 1
    skroutz = product.skroutz_status == 1
    if marketplace == "bestprice":
        return bestprice
    if marketplace == "skroutz":
        return skroutz
    if marketplace == "both":
        return bestprice and skroutz
    return not bestprice and not skroutz


def _skip_reasons(
    product: CatalogProduct,
    ignored_models: set[str],
    excluded_models: set[str],
    include_ignored: bool,
) -> list[str]:
    reasons: list[str] = []
    if product.model in excluded_models:
        reasons.append("explicitly_excluded")
    if not include_ignored and product.model in ignored_models:
        reasons.append("ignored")
    if not product.is_atomic_model:
        reasons.append("non_atomic_model")
    if product.status != 1:
        reasons.append("inactive")
    if not product.mpn:
        reasons.append("missing_mpn")
    if product.price is None or product.price <= 0:
        reasons.append("missing_or_invalid_price")
    return reasons


def _normalize_model(model: object) -> str:
    if model is None:
        return ""
    return str(model).strip()


def _filter_value(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text if text else None
