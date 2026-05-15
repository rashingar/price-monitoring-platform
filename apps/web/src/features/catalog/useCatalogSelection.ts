import { useEffect, useMemo, useRef, useState } from "react";
import type { CatalogProduct, PriceMonitoringSource } from "../../api/commerceTypes";
import type { CatalogFilterState } from "./catalogTypes";
import {
  getSelectionBlocker,
  makeSelectionBody,
  normalizeModel,
} from "./catalogSelection";

export function useCatalogSelection({
  products,
  filters,
  pageSize,
  setPage,
  onSelectionScopeChange,
}: {
  products: CatalogProduct[];
  filters: CatalogFilterState;
  pageSize: number;
  setPage: React.Dispatch<React.SetStateAction<number>>;
  onSelectionScopeChange: () => void;
}) {
  const filterResetMountedRef = useRef(false);
  const [selectedModels, setSelectedModels] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    if (!filterResetMountedRef.current) {
      filterResetMountedRef.current = true;
      return;
    }

    setPage(1);
    setSelectedModels(new Set());
    onSelectionScopeChange();
  }, [
    filters.hasQuantity,
    filters.includeIgnored,
    filters.manufacturer,
    filters.marketplace,
    pageSize,
    filters.q,
    filters.selectedCategory,
    filters.selectedFamily,
    filters.selectedSubCategory,
    filters.showComposite,
    filters.sourceUrlsOnly,
    onSelectionScopeChange,
    setPage,
  ]);

  const eligibleVisibleModels = useMemo(
    () =>
      products
        .filter((product) => getSelectionBlocker(product) === null)
        .map((product) => normalizeModel(product.model))
        .filter((model) => model.length > 0),
    [products],
  );

  const selectedVisibleCount = eligibleVisibleModels.filter((model) =>
    selectedModels.has(model),
  ).length;
  const allVisibleSelected =
    eligibleVisibleModels.length > 0 && selectedVisibleCount === eligibleVisibleModels.length;

  const toggleModel = (model: string) => {
    const normalizedModel = normalizeModel(model);
    if (normalizedModel.length === 0) {
      return;
    }

    setSelectedModels((current) => {
      const next = new Set(current);
      if (next.has(normalizedModel)) {
        next.delete(normalizedModel);
      } else {
        next.add(normalizedModel);
      }

      return next;
    });
  };

  const toggleAllVisible = () => {
    setSelectedModels((current) => {
      const next = new Set(current);
      if (allVisibleSelected) {
        eligibleVisibleModels.forEach((model) => next.delete(model));
      } else {
        eligibleVisibleModels.forEach((model) => next.add(model));
      }

      return next;
    });
  };

  const buildSelectionBody = (source: PriceMonitoringSource, dryRun: boolean) =>
    makeSelectionBody(
      source,
      selectedModels,
      {
        q: filters.q,
        family: filters.selectedFamily,
        categoryName: filters.selectedCategory,
        subCategory: filters.selectedSubCategory,
        manufacturer: filters.manufacturer,
        marketplace: filters.marketplace,
        includeIgnored: filters.includeIgnored,
      },
      dryRun,
    );

  return {
    selectedModels,
    setSelectedModels,
    eligibleVisibleModels,
    allVisibleSelected,
    toggleModel,
    toggleAllVisible,
    buildSelectionBody,
  };
}
