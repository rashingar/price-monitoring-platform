import type {
  CatalogProduct,
  MarketplaceFilter,
  PriceMonitoringSelectionBody,
  PriceMonitoringSelectionItem,
  PriceMonitoringSelectionResult,
  PriceMonitoringSource,
} from "../../api/commerceTypes";
import { makeHierarchyFilterParams } from "../../utils/categoryHierarchy";

export interface SourceUrlEligibility {
  label: string;
  className: string;
  blocker: string | null;
}

export interface CatalogSelectionFilters {
  q: string;
  family: string;
  categoryName: string;
  subCategory: string;
  manufacturer: string;
  marketplace: MarketplaceFilter;
  includeIgnored: boolean;
}

export function normalizeModel(model: string): string {
  return model.trim();
}

export function getSourceUrlStatusCount(product: CatalogProduct, status: string): number {
  const coverage = product.source_url_coverage;
  const directValue =
    status === "active"
      ? coverage?.active_source_url_count
      : status === "needs_review"
        ? coverage?.needs_review_source_url_count
        : undefined;
  if (typeof directValue === "number" && Number.isFinite(directValue)) {
    return directValue;
  }

  const statusValue = coverage?.status_counts?.[status];
  return typeof statusValue === "number" && Number.isFinite(statusValue) ? statusValue : 0;
}

export function getSourceUrlEligibility(product: CatalogProduct): SourceUrlEligibility {
  const activeCount = getSourceUrlStatusCount(product, "active");
  const reviewCount = getSourceUrlStatusCount(product, "needs_review");
  if (activeCount > 0 || product.source_url_coverage?.has_active_source_url === true) {
    return { label: "Eligible", className: "success", blocker: null };
  }
  if (reviewCount > 0) {
    return { label: "Review", className: "warning", blocker: "Source URL review" };
  }
  return { label: "Missing", className: "danger", blocker: "Missing source URL" };
}

export function getSelectionBlocker(product: CatalogProduct): string | null {
  if (product.is_atomic_model === false) {
    return "Composite model";
  }

  if (product.automation_eligible === false) {
    return "Not eligible";
  }

  if (product.ignored === true) {
    return "Ignored";
  }

  return getSourceUrlEligibility(product).blocker;
}

export function makeSelectionBody(
  source: PriceMonitoringSource,
  selectedModels: Set<string>,
  filters: CatalogSelectionFilters,
  dryRun: boolean,
): PriceMonitoringSelectionBody {
  const q = filters.q.trim();

  return {
    source,
    filters: {
      q: q.length > 0 ? q : null,
      ...makeHierarchyFilterParams({
        family: filters.family,
        categoryName: filters.categoryName,
        subCategory: filters.subCategory,
      }),
      manufacturer: filters.manufacturer || null,
      marketplace: filters.marketplace === "all" ? null : filters.marketplace,
      has_mpn: true,
      atomic_only: true,
      automation_eligible_only: true,
    },
    selected_models: Array.from(selectedModels),
    excluded_models: [],
    include_ignored: filters.includeIgnored,
    dry_run: dryRun,
  };
}

export function getSkippedMissingSourceUrlModels(result: PriceMonitoringSelectionResult | null): string[] {
  if (!result) {
    return [];
  }

  const seen = new Set<string>();
  const addModel = (value: unknown) => {
    if (typeof value !== "string") {
      return;
    }

    const model = value.trim();
    if (model.length > 0) {
      seen.add(model);
    }
  };

  const addSkippedItem = (item: PriceMonitoringSelectionItem) => {
    const reason = String(item.skip_reason ?? item.reason ?? "").toLowerCase();
    const reasons = Array.isArray(item.reasons)
      ? item.reasons.map((value) => String(value).toLowerCase())
      : [];
    const coverage = item.source_url_coverage;
    const isMissing =
      reason.includes("missing_active_source_url") ||
      reason.includes("no_active_source_url") ||
      reasons.some(
        (itemReason) =>
          itemReason.includes("missing_active_source_url") ||
          itemReason.includes("no_active_source_url"),
      ) ||
      coverage?.has_active_source_url === false ||
      (coverage?.active_source_url_count !== undefined && coverage.active_source_url_count <= 0);

    if (isMissing) {
      addModel(item.model);
    }
  };

  result.skipped_items?.forEach(addSkippedItem);
  result.source_url_coverage?.missing_source_url_models?.forEach(addModel);

  return Array.from(seen);
}
