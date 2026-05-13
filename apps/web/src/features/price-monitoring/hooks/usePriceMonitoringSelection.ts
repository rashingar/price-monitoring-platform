import { useMemo } from "react";
import type {
  CatalogCategoryHierarchyResponse,
  VendorSourceCapability,
} from "../../../api/commerceTypes";
import {
  getCategoryOptions,
  getFamilyOptions,
  getSubCategoryOptions,
} from "../../../utils/categoryHierarchy";
import type { PriceMonitoringSourceFilter } from "../types";

export function normalizeSelectedSource(value: string | null | undefined): string {
  const sourceName = typeof value === "string" ? value.trim() : "";
  return sourceName && sourceName.toLowerCase() !== "all" ? sourceName : "";
}

export function dedupeVendorSources(sources: VendorSourceCapability[]): VendorSourceCapability[] {
  const seen = new Set<string>();
  return sources.filter((source) => {
    const sourceName = String(source.source_name).trim();
    if (!sourceName) {
      return false;
    }

    const key = sourceName.toLowerCase();
    if (seen.has(key)) {
      return false;
    }

    seen.add(key);
    return true;
  });
}

export function usePriceMonitoringSelection({
  categoryHierarchy,
  selectedFamily,
  selectedCategory,
  vendorSources,
  source,
}: {
  categoryHierarchy: CatalogCategoryHierarchyResponse | null;
  selectedFamily: string;
  selectedCategory: string;
  vendorSources: VendorSourceCapability[];
  source: PriceMonitoringSourceFilter;
}) {
  const familyOptions = useMemo(
    () => getFamilyOptions(categoryHierarchy),
    [categoryHierarchy],
  );

  const categoryOptions = useMemo(
    () => getCategoryOptions(categoryHierarchy, selectedFamily),
    [categoryHierarchy, selectedFamily],
  );

  const subCategoryOptions = useMemo(
    () => getSubCategoryOptions(categoryHierarchy, selectedFamily, selectedCategory),
    [categoryHierarchy, selectedCategory, selectedFamily],
  );

  const sourceUrlFilterOptions = useMemo(
    () =>
      dedupeVendorSources(
        vendorSources.filter((option) => normalizeSelectedSource(String(option.source_name))),
      ),
    [vendorSources],
  );
  const selectedSourceName = normalizeSelectedSource(source);

  return {
    familyOptions,
    categoryOptions,
    subCategoryOptions,
    sourceUrlFilterOptions,
    selectedSourceName,
    sourceRequired: selectedSourceName.length === 0,
  };
}
