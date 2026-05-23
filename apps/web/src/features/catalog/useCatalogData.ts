import { useCallback, useEffect, useMemo, useState } from "react";
import { CommerceApiError, commerceClient, getCommerceApiErrorMessage } from "../../api/commerceClient";
import {
  getCatalogReadinessBlock,
  getCatalogReadinessWarning,
} from "../../api/catalogReadinessGate";
import type { CatalogReadinessBlock } from "../../api/catalogReadinessGate";
import type {
  CatalogBrandOption,
  CatalogCategoryHierarchyResponse,
  CatalogProductsParams,
  CatalogProductsResponse,
  CatalogSummary,
} from "../../api/commerceTypes";
import {
  CATEGORY_HIERARCHY_UNAVAILABLE_MESSAGE,
  getCategoryOptions,
  getFamilyOptions,
  getSubCategoryOptions,
  makeHierarchyFilterParams,
} from "../../utils/categoryHierarchy";
import { DEFAULT_PAGE_SIZE } from "./catalogConstants";
import type { CatalogFilterState } from "./catalogTypes";

function sourceUrlDiscoverySource(filters: CatalogFilterState): string {
  if (filters.marketplace === "bestprice" || filters.marketplace === "skroutz") {
    return filters.marketplace;
  }
  return filters.source || "bestprice";
}

function getCategoryHierarchyErrorMessage(error: unknown): string {
  return error instanceof CommerceApiError && error.status === 404
    ? CATEGORY_HIERARCHY_UNAVAILABLE_MESSAGE
    : getCommerceApiErrorMessage(error);
}

export function useCatalogData(filters: CatalogFilterState & { page: number; pageSize: number }) {
  const [summary, setSummary] = useState<CatalogSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [summaryReadinessBlock, setSummaryReadinessBlock] = useState<CatalogReadinessBlock | null>(null);
  const [isSummaryLoading, setIsSummaryLoading] = useState(true);

  const [categoryHierarchy, setCategoryHierarchy] =
    useState<CatalogCategoryHierarchyResponse | null>(null);
  const [brandOptions, setBrandOptions] = useState<CatalogBrandOption[]>([]);
  const [filtersError, setFiltersError] = useState<string | null>(null);
  const [filtersReadinessBlock, setFiltersReadinessBlock] = useState<CatalogReadinessBlock | null>(null);
  const [areFiltersLoading, setAreFiltersLoading] = useState(true);

  const [productsResponse, setProductsResponse] = useState<CatalogProductsResponse>({
    items: [],
    page: 1,
    page_size: DEFAULT_PAGE_SIZE,
    total: 0,
    filtered_total: 0,
  });
  const [productsError, setProductsError] = useState<string | null>(null);
  const [productsReadinessBlock, setProductsReadinessBlock] = useState<CatalogReadinessBlock | null>(null);
  const [productsWarningBlock, setProductsWarningBlock] = useState<CatalogReadinessBlock | null>(null);
  const [areProductsLoading, setAreProductsLoading] = useState(true);

  const loadSummary = useCallback(async (signal?: AbortSignal) => {
    setIsSummaryLoading(true);
    try {
      const nextSummary = await commerceClient.getCatalogSummary(signal);
      if (signal?.aborted) {
        return;
      }

      setSummary(nextSummary);
      setSummaryError(null);
      setSummaryReadinessBlock(null);
    } catch (error) {
      if (!signal?.aborted) {
        const readinessBlock = getCatalogReadinessBlock(error);
        setSummaryReadinessBlock(readinessBlock);
        setSummaryError(readinessBlock ? null : getCommerceApiErrorMessage(error));
      }
    } finally {
      if (!signal?.aborted) {
        setIsSummaryLoading(false);
      }
    }
  }, []);

  const loadFilterOptions = useCallback(async (signal?: AbortSignal) => {
    setAreFiltersLoading(true);
    const [nextHierarchy, nextBrands] = await Promise.allSettled([
      commerceClient.getCatalogCategoryHierarchy(signal),
      commerceClient.listCatalogBrandOptions(signal),
    ]);

    if (signal?.aborted) {
      return;
    }

    const errors: string[] = [];
    let readinessBlock: CatalogReadinessBlock | null = null;
    if (nextHierarchy.status === "fulfilled") {
      setCategoryHierarchy(nextHierarchy.value);
    } else {
      setCategoryHierarchy(null);
      readinessBlock = readinessBlock ?? getCatalogReadinessBlock(nextHierarchy.reason);
      if (!readinessBlock) {
        errors.push(getCategoryHierarchyErrorMessage(nextHierarchy.reason));
      }
    }

    if (nextBrands.status === "fulfilled") {
      setBrandOptions(
        nextBrands.value
          .filter((option) => option.manufacturer.trim().length > 0)
          .map((option) => ({
            manufacturer: option.manufacturer.trim(),
            count: option.count,
          })),
      );
    } else {
      setBrandOptions([]);
      readinessBlock = readinessBlock ?? getCatalogReadinessBlock(nextBrands.reason);
      if (!readinessBlock) {
        errors.push(`Could not load manufacturers: ${getCommerceApiErrorMessage(nextBrands.reason)}`);
      }
    }

    setFiltersReadinessBlock(readinessBlock);
    setFiltersError(errors.length > 0 ? errors.join(" ") : null);
    setAreFiltersLoading(false);
  }, []);

  const familyOptions = useMemo(
    () => getFamilyOptions(categoryHierarchy),
    [categoryHierarchy],
  );

  const categoryLevelOptions = useMemo(
    () => getCategoryOptions(categoryHierarchy, filters.selectedFamily),
    [categoryHierarchy, filters.selectedFamily],
  );

  const subCategoryOptions = useMemo(
    () => getSubCategoryOptions(categoryHierarchy, filters.selectedFamily, filters.selectedCategory),
    [categoryHierarchy, filters.selectedCategory, filters.selectedFamily],
  );

  const productParams = useMemo<CatalogProductsParams>(
    () => {
      const trimmedQ = filters.q.trim();
      const trimmedManufacturer = filters.manufacturer.trim();
      const params: CatalogProductsParams = {
        page: filters.page,
        page_size: filters.pageSize,
        atomic_only: !filters.showComposite,
        ignored: filters.includeIgnored ? "include" : "exclude",
        source_name: filters.source,
        source_url_discovery_source: sourceUrlDiscoverySource(filters),
      };

      if (filters.sourceUrlsOnly) {
        params.has_source_url = true;
      }

      if (filters.hasQuantity) {
        params.has_quantity = true;
      }

      if (trimmedQ.length > 0) {
        params.q = trimmedQ;
      }

      Object.assign(
        params,
        makeHierarchyFilterParams({
          family: filters.selectedFamily,
          categoryName: filters.selectedCategory,
          subCategory: filters.selectedSubCategory,
        }),
      );

      if (trimmedManufacturer.length > 0) {
        params.manufacturer = trimmedManufacturer;
      }

      if (filters.marketplace !== "all") {
        params.marketplace = filters.marketplace;
      }

      return params;
    },
    [
      filters.hasQuantity,
      filters.includeIgnored,
      filters.manufacturer,
      filters.marketplace,
      filters.page,
      filters.pageSize,
      filters.q,
      filters.selectedCategory,
      filters.selectedFamily,
      filters.selectedSubCategory,
      filters.showComposite,
      filters.source,
      filters.sourceUrlsOnly,
    ],
  );

  const loadProducts = useCallback(
    async (signal?: AbortSignal) => {
      setAreProductsLoading(true);
      try {
        const nextProducts = await commerceClient.listCatalogProducts(productParams, signal);
        if (signal?.aborted) {
          return;
        }

        setProductsResponse(nextProducts);
        setProductsError(null);
        setProductsReadinessBlock(null);
        setProductsWarningBlock(
          nextProducts.items.length === 0 ? getCatalogReadinessWarning(nextProducts.warning) : null,
        );
      } catch (error) {
        if (!signal?.aborted) {
          const readinessBlock = getCatalogReadinessBlock(error);
          setProductsReadinessBlock(readinessBlock);
          setProductsWarningBlock(null);
          setProductsError(readinessBlock ? null : getCommerceApiErrorMessage(error));
        }
      } finally {
        if (!signal?.aborted) {
          setAreProductsLoading(false);
        }
      }
    },
    [productParams],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadSummary(controller.signal);
    void loadFilterOptions(controller.signal);
    return () => controller.abort();
  }, [loadFilterOptions, loadSummary]);

  useEffect(() => {
    const controller = new AbortController();
    void loadProducts(controller.signal);
    return () => controller.abort();
  }, [loadProducts]);

  const totalPages = Math.max(
    1,
    Math.ceil(productsResponse.filtered_total / productsResponse.page_size),
  );
  const catalogReadinessBlock =
    productsReadinessBlock ?? productsWarningBlock ?? summaryReadinessBlock ?? filtersReadinessBlock;
  const isCatalogLocked = catalogReadinessBlock !== null;

  return {
    summary,
    summaryError,
    summaryReadinessBlock,
    isSummaryLoading,
    brandOptions,
    filtersError,
    areFiltersLoading,
    familyOptions,
    categoryLevelOptions,
    subCategoryOptions,
    productsResponse,
    productsError,
    productsReadinessBlock,
    productsWarningBlock,
    areProductsLoading,
    totalPages,
    catalogReadinessBlock,
    isCatalogLocked,
    loadSummary,
    loadFilterOptions,
    loadProducts,
  };
}
