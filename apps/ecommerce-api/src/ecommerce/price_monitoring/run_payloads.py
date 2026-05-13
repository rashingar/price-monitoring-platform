"""HTTP payloads and request mapping for Price Monitoring routes."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from ecommerce.price_monitoring.review import PriceActionInput
from ecommerce.price_monitoring.selection import PriceMonitoringFilters, PriceMonitoringSelectionRequest


class PriceMonitoringFiltersRequest(BaseModel):
    q: str | None = None
    category: str | None = None
    family: str | None = None
    category_name: str | None = None
    sub_category: str | None = None
    manufacturer: str | None = None
    marketplace: str | None = None
    has_mpn: bool | None = True
    atomic_only: bool = True
    automation_eligible_only: bool = True


class PriceMonitoringSelectionApiRequest(BaseModel):
    source: str | None = None
    source_name: str | None = None
    vendor_slug: str | None = None
    source_filter: str | None = None
    filters: PriceMonitoringFiltersRequest = Field(default_factory=PriceMonitoringFiltersRequest)
    selected_models: list[str] = Field(default_factory=list)
    excluded_models: list[str] = Field(default_factory=list)
    include_ignored: bool = False
    dry_run: bool = False


class PriceActionApiInput(BaseModel):
    model: str = ""
    selected_action: str = ""
    undercut_amount: Decimal | None = None
    reason: str = ""


class PriceReviewActionsApiRequest(BaseModel):
    enriched_csv_path: str | None = None
    actions: list[PriceActionApiInput] = Field(default_factory=list)


class PriceUpdateExportApiRequest(BaseModel):
    review_csv_path: str | None = None
    output_path: str | None = None


class PriceMonitoringFetchApiRequest(BaseModel):
    source: str | None = None
    catalog_url: str | None = None


class PriceMonitoringFetchCancelApiRequest(BaseModel):
    reason: str | None = None


def to_selection_request(
    request: PriceMonitoringSelectionApiRequest,
    *,
    dry_run: bool,
) -> PriceMonitoringSelectionRequest:
    return PriceMonitoringSelectionRequest(
        source=request.source or "",
        source_name=request.source_name,
        vendor_slug=request.vendor_slug,
        source_filter=request.source_filter,
        filters=PriceMonitoringFilters(
            q=request.filters.q,
            category=request.filters.category,
            family=request.filters.family,
            category_name=request.filters.category_name,
            sub_category=request.filters.sub_category,
            manufacturer=request.filters.manufacturer,
            marketplace=marketplace_or_none(request.filters.marketplace),
            has_mpn=request.filters.has_mpn,
            atomic_only=request.filters.atomic_only,
            automation_eligible_only=request.filters.automation_eligible_only,
        ),
        selected_models=request.selected_models,
        excluded_models=request.excluded_models,
        include_ignored=request.include_ignored,
        dry_run=dry_run,
    )


def to_action_input(action: PriceActionApiInput) -> PriceActionInput:
    return PriceActionInput(
        model=action.model,
        selected_action=action.selected_action,
        undercut_amount=action.undercut_amount,
        reason=action.reason,
    )


def marketplace_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in {"bestprice", "skroutz", "both", "none"}:
        raise ValueError("marketplace must be one of: bestprice, skroutz, both, none")
    return normalized
