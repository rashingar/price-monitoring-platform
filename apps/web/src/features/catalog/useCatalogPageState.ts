import { useEffect, useMemo, useState } from "react";
import type { CatalogColumnId, CatalogLayoutPreferences, CatalogPageControls, CatalogPageState } from "./catalogTypes";
import {
  CATALOG_STATE_KEY,
  initialCatalogPageState,
  normalizeVisibleColumnIds,
  serializeVisibleColumnIds,
  shouldUseCurrentCatalogColumnDefaults,
} from "./catalogConstants";
import { usePersistentPageState } from "../../hooks/usePersistentPageState";

export function useCatalogPageState(initialLayoutPreferences: CatalogLayoutPreferences): CatalogPageControls {
  const [persistedState, setPersistedState, resetPersistedState] =
    usePersistentPageState<CatalogPageState>(CATALOG_STATE_KEY, {
      ...initialCatalogPageState,
      pageSize: initialLayoutPreferences.pageSize,
      visibleColumnIds: initialLayoutPreferences.visibleColumnIds,
    });

  const [q, setQ] = useState(persistedState.q);
  const [selectedFamily, setSelectedFamily] = useState(persistedState.selectedFamily);
  const [selectedCategory, setSelectedCategory] = useState(persistedState.selectedCategory);
  const [selectedSubCategory, setSelectedSubCategory] = useState(persistedState.selectedSubCategory);
  const [manufacturer, setManufacturer] = useState(persistedState.manufacturer);
  const [marketplace, setMarketplace] = useState(persistedState.marketplace);
  const [source, setSource] = useState(persistedState.source);
  const [showComposite, setShowComposite] = useState(persistedState.showComposite);
  const [includeIgnored, setIncludeIgnored] = useState(persistedState.includeIgnored);
  const [sourceUrlsOnly, setSourceUrlsOnly] = useState(persistedState.sourceUrlsOnly === true);
  const [hasQuantity, setHasQuantity] = useState(persistedState.hasQuantity === true);
  const [page, setPage] = useState(persistedState.page);
  const [pageSize, setPageSize] = useState(persistedState.pageSize);
  const [visibleColumnIds, setVisibleColumnIds] = useState<Set<CatalogColumnId>>(
    () => {
      const persistedVisibleColumnIds = normalizeVisibleColumnIds(persistedState.visibleColumnIds);
      return new Set(
        shouldUseCurrentCatalogColumnDefaults(persistedVisibleColumnIds)
          ? initialLayoutPreferences.visibleColumnIds
          : persistedVisibleColumnIds ?? initialLayoutPreferences.visibleColumnIds,
      );
    },
  );

  const visibleColumnIdsArray = useMemo(
    () => serializeVisibleColumnIds(visibleColumnIds),
    [visibleColumnIds],
  );

  useEffect(() => {
    setPersistedState({
      q,
      selectedFamily,
      selectedCategory,
      selectedSubCategory,
      manufacturer,
      marketplace,
      source,
      showComposite,
      includeIgnored,
      sourceUrlsOnly,
      hasQuantity,
      page,
      pageSize,
      visibleColumnIds: visibleColumnIdsArray,
    });
  }, [
    hasQuantity,
    includeIgnored,
    manufacturer,
    marketplace,
    page,
    pageSize,
    q,
    selectedCategory,
    selectedFamily,
    selectedSubCategory,
    setPersistedState,
    showComposite,
    source,
    sourceUrlsOnly,
    visibleColumnIdsArray,
  ]);

  const resetCatalogState = () => {
    resetPersistedState();
    setQ(initialCatalogPageState.q);
    setSelectedFamily(initialCatalogPageState.selectedFamily);
    setSelectedCategory(initialCatalogPageState.selectedCategory);
    setSelectedSubCategory(initialCatalogPageState.selectedSubCategory);
    setManufacturer(initialCatalogPageState.manufacturer);
    setMarketplace(initialCatalogPageState.marketplace);
    setSource(initialCatalogPageState.source);
    setShowComposite(initialCatalogPageState.showComposite);
    setIncludeIgnored(initialCatalogPageState.includeIgnored);
    setSourceUrlsOnly(initialCatalogPageState.sourceUrlsOnly);
    setHasQuantity(initialCatalogPageState.hasQuantity);
    setPage(initialCatalogPageState.page);
    setPageSize(initialCatalogPageState.pageSize);
    setVisibleColumnIds(new Set(initialCatalogPageState.visibleColumnIds));
  };

  return {
    q,
    selectedFamily,
    selectedCategory,
    selectedSubCategory,
    manufacturer,
    marketplace,
    source,
    showComposite,
    includeIgnored,
    sourceUrlsOnly,
    hasQuantity,
    page,
    pageSize,
    visibleColumnIds,
    setQ,
    setSelectedFamily,
    setSelectedCategory,
    setSelectedSubCategory,
    setManufacturer,
    setMarketplace,
    setSource,
    setShowComposite,
    setIncludeIgnored,
    setSourceUrlsOnly,
    setHasQuantity,
    setPage,
    setPageSize,
    setVisibleColumnIds,
    visibleColumnIdsArray,
    resetCatalogState,
  };
}
