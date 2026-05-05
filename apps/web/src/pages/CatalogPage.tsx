import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CommerceApiError,
  commerceClient,
  getCommerceApiErrorMessage,
} from "../api/commerceClient";
import {
  CATALOG_READINESS_REQUIRED_MESSAGE,
  getCatalogReadinessBlock,
  getCatalogReadinessWarning,
} from "../api/catalogReadinessGate";
import type { CatalogReadinessBlock } from "../api/catalogReadinessGate";
import type {
  CatalogBrandOption,
  CatalogCategoryHierarchyResponse,
  CatalogProduct,
  CatalogProductsParams,
  CatalogProductsResponse,
  CatalogSummary,
  MarketplaceFilter,
  PriceMonitoringSelectionBody,
  PriceMonitoringSelectionResult,
  PriceMonitoringSource,
} from "../api/commerceTypes";
import {
  CatalogSourceUrlManager,
  SourceUrlImportPanel,
} from "../components/CatalogSourceUrls";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";
import { usePersistentPageState } from "../hooks/usePersistentPageState";
import {
  CATEGORY_HIERARCHY_UNAVAILABLE_MESSAGE,
  formatHierarchyOptionLabel,
  getCategoryOptions,
  getFamilyOptions,
  getSubCategoryOptions,
  makeHierarchyFilterParams,
} from "../utils/categoryHierarchy";

const DEFAULT_PAGE_SIZE = 100;
const CATALOG_COLUMNS_STORAGE_KEY = "productAgentUi.catalog.columns.v1";
const CATALOG_STATE_KEY = "product-agent-ui:catalog:v1";

type CatalogColumnId =
  | "select"
  | "model"
  | "name"
  | "manufacturer"
  | "family"
  | "category_name"
  | "sub_category"
  | "mpn"
  | "price"
  | "quantity"
  | "bestprice_status"
  | "skroutz_status"
  | "ignored"
  | "warnings"
  | "status"
  | "automation_eligible"
  | "is_atomic_model"
  | "raw_category"
  | "category_levels";

interface CatalogColumnDefinition {
  id: CatalogColumnId;
  label: string;
  required?: boolean;
}

interface CatalogLayoutPreferences {
  visibleColumnIds: CatalogColumnId[];
  pageSize: number;
}

interface CatalogPageState {
  q: string;
  selectedFamily: string;
  selectedCategory: string;
  selectedSubCategory: string;
  manufacturer: string;
  marketplace: MarketplaceFilter;
  source: PriceMonitoringSource;
  showComposite: boolean;
  includeIgnored: boolean;
  page: number;
  pageSize: number;
  visibleColumnIds: CatalogColumnId[];
}

const CATALOG_COLUMNS: CatalogColumnDefinition[] = [
  { id: "select", label: "Select", required: true },
  { id: "model", label: "Model", required: true },
  { id: "name", label: "Name", required: true },
  { id: "manufacturer", label: "Manufacturer" },
  { id: "family", label: "Family" },
  { id: "category_name", label: "Category" },
  { id: "sub_category", label: "Sub-Category" },
  { id: "mpn", label: "MPN" },
  { id: "price", label: "Price" },
  { id: "quantity", label: "Qty" },
  { id: "bestprice_status", label: "BestPrice" },
  { id: "skroutz_status", label: "Skroutz" },
  { id: "ignored", label: "Ignored" },
  { id: "warnings", label: "Warnings / eligibility" },
  { id: "status", label: "Status" },
  { id: "automation_eligible", label: "Automation eligible" },
  { id: "is_atomic_model", label: "Atomic" },
  { id: "raw_category", label: "Raw category" },
  { id: "category_levels", label: "Category levels" },
];

const DEFAULT_VISIBLE_CATALOG_COLUMNS: CatalogColumnId[] = [
  "select",
  "model",
  "name",
  "manufacturer",
  "family",
  "category_name",
  "sub_category",
  "mpn",
  "price",
  "quantity",
  "bestprice_status",
  "skroutz_status",
  "ignored",
  "warnings",
];

const initialCatalogPageState: CatalogPageState = {
  q: "",
  selectedFamily: "",
  selectedCategory: "",
  selectedSubCategory: "",
  manufacturer: "",
  marketplace: "all",
  source: "skroutz",
  showComposite: false,
  includeIgnored: false,
  page: 1,
  pageSize: DEFAULT_PAGE_SIZE,
  visibleColumnIds: DEFAULT_VISIBLE_CATALOG_COLUMNS,
};

const REQUIRED_CATALOG_COLUMNS = CATALOG_COLUMNS.filter((column) => column.required).map(
  (column) => column.id,
);
const CATALOG_COLUMN_IDS = new Set(CATALOG_COLUMNS.map((column) => column.id));

function normalizeVisibleColumnIds(value: unknown): CatalogColumnId[] | null {
  if (!Array.isArray(value)) {
    return null;
  }

  const visibleColumnIds = value.filter(
    (item): item is CatalogColumnId =>
      typeof item === "string" && CATALOG_COLUMN_IDS.has(item as CatalogColumnId),
  );

  if (visibleColumnIds.length === 0) {
    return null;
  }

  return Array.from(new Set([...REQUIRED_CATALOG_COLUMNS, ...visibleColumnIds]));
}

function readCatalogLayoutPreferences(): CatalogLayoutPreferences {
  if (typeof window === "undefined") {
    return {
      visibleColumnIds: DEFAULT_VISIBLE_CATALOG_COLUMNS,
      pageSize: DEFAULT_PAGE_SIZE,
    };
  }

  try {
    const rawPreferences = window.localStorage.getItem(CATALOG_COLUMNS_STORAGE_KEY);
    if (!rawPreferences) {
      throw new Error("No saved preferences");
    }

    const parsed = JSON.parse(rawPreferences) as unknown;
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      throw new Error("Invalid saved preferences");
    }

    const record = parsed as Record<string, unknown>;
    const visibleColumnIds = normalizeVisibleColumnIds(record.visibleColumnIds);
    const pageSize =
      typeof record.pageSize === "number" && [50, 100, 200].includes(record.pageSize)
        ? record.pageSize
        : DEFAULT_PAGE_SIZE;

    return {
      visibleColumnIds: visibleColumnIds ?? DEFAULT_VISIBLE_CATALOG_COLUMNS,
      pageSize,
    };
  } catch {
    return {
      visibleColumnIds: DEFAULT_VISIBLE_CATALOG_COLUMNS,
      pageSize: DEFAULT_PAGE_SIZE,
    };
  }
}

function writeCatalogLayoutPreferences(preferences: CatalogLayoutPreferences): void {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(CATALOG_COLUMNS_STORAGE_KEY, JSON.stringify(preferences));
}

function normalizeModel(model: string): string {
  return model.trim();
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return String(value);
}

function formatMoney(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }

  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 2,
  }).format(value);
}

function getSummaryNumber(summary: CatalogSummary | null, keys: string[]): number | null {
  if (!summary) {
    return null;
  }

  for (const key of keys) {
    const value = summary[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
  }

  return null;
}

function getSelectionBlocker(product: CatalogProduct): string | null {
  if (product.is_atomic_model === false) {
    return "Composite model";
  }

  if (product.automation_eligible === false) {
    return "Not eligible";
  }

  if (product.ignored === true) {
    return "Ignored";
  }

  return null;
}

function getMarketplaceStatus(value: number | null | undefined): string {
  if (value === 1) {
    return "active";
  }

  if (value === 0) {
    return "inactive";
  }

  return formatValue(value);
}

function formatOptionCount(count: number | null | undefined): string {
  return typeof count === "number" && Number.isFinite(count) ? ` (${count})` : "";
}

function makeSelectionBody(
  source: PriceMonitoringSource,
  selectedModels: Set<string>,
  filters: {
    q: string;
    family: string;
    categoryName: string;
    subCategory: string;
    manufacturer: string;
    marketplace: MarketplaceFilter;
    includeIgnored: boolean;
  },
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

function SummaryCard({
  label,
  value,
}: {
  label: string;
  value: number | null;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value === null ? "-" : value.toLocaleString()}</dd>
    </div>
  );
}

function getCategoryHierarchyErrorMessage(error: unknown): string {
  return error instanceof CommerceApiError && error.status === 404
    ? CATEGORY_HIERARCHY_UNAVAILABLE_MESSAGE
    : getCommerceApiErrorMessage(error);
}

function ResultSummary({ result }: { result: PriceMonitoringSelectionResult }) {
  const selectedItems = result.selected_items ?? result.selected ?? [];

  return (
    <div className="result-block">
      <dl className="summary-grid">
        {"run_id" in result ? <SummaryText label="Run ID" value={result.run_id} /> : null}
        {"status" in result ? <SummaryText label="Status" value={result.status} /> : null}
        {"source" in result ? <SummaryText label="Source" value={result.source} /> : null}
        {"selected_count" in result ? (
          <SummaryText label="Selected" value={result.selected_count} />
        ) : null}
        {"skipped_count" in result ? <SummaryText label="Skipped" value={result.skipped_count} /> : null}
        {"output_dir" in result ? <SummaryText label="Output dir" value={result.output_dir} /> : null}
        {"input_csv_path" in result ? (
          <SummaryText label="Input CSV" value={result.input_csv_path} />
        ) : null}
        {"selection_summary_path" in result ? (
          <SummaryText label="Selection summary" value={result.selection_summary_path} />
        ) : null}
      </dl>

      {result.skipped_by_reason ? (
        <div className="compact-list">
          <strong>Skipped by reason</strong>
          <ul>
            {Object.entries(result.skipped_by_reason).map(([reason, count]) => (
              <li key={reason}>
                {reason}: {count}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {selectedItems.length > 0 ? (
        <div className="compact-list">
          <strong>Selected items</strong>
          <ul>
            {selectedItems.slice(0, 25).map((item, index) => (
              <li key={`${item.model ?? "item"}-${index}`}>
                {formatValue(item.model)} {item.name ? `- ${item.name}` : ""}
              </li>
            ))}
          </ul>
          {selectedItems.length > 25 ? (
            <p className="muted">Showing 25 of {selectedItems.length} returned items.</p>
          ) : null}
        </div>
      ) : null}

      {result.skipped_reasons ? (
        <div className="compact-list">
          <strong>Skipped reasons</strong>
          <pre className="json-block">{JSON.stringify(result.skipped_reasons, null, 2)}</pre>
        </div>
      ) : null}
    </div>
  );
}

function SummaryText({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{formatValue(value)}</dd>
    </div>
  );
}

function CatalogSetupHint() {
  return (
    <div className="setup-hint compact">
      <strong>Catalog setup check</strong>
      <ul>
        <li>Commerce API must be running: <code>ecommerce-api</code></li>
        <li>Database URL: <code>ECOMMERCE_DATABASE_URL</code></li>
        <li>Run migrations: <code>alembic upgrade head</code></li>
        <li>Import catalog input: <code>python -m ecommerce.jobs.ingest_catalog</code></li>
        <li>UI endpoint: <code>/commerce-api/catalog/summary</code></li>
        <li>Backend endpoint: <code>http://127.0.0.1:8001/api/catalog/summary</code></li>
      </ul>
    </div>
  );
}

function CatalogReadinessBanner({
  block,
  onRetry,
}: {
  block: CatalogReadinessBlock;
  onRetry?: () => void;
}) {
  return (
    <div className="db-status-banner warning" role="alert">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Catalog</p>
          <h3>Catalog database/import required</h3>
        </div>
        {onRetry ? (
          <button className="button secondary" type="button" onClick={onRetry}>
            Retry Catalog
          </button>
        ) : null}
      </div>
      <p>{block.message}</p>
      <p className="muted">
        Catalog browsing reads from PostgreSQL after sourceCata.csv has been imported. This does not
        mean CSV/Bridge, files, paths, artifacts, or general commerce health are unavailable when
        their endpoints are running.
      </p>
      {block.details.length > 0 ? (
        <ul className="db-status-hints">
          {block.details.map((detail) => (
            <li key={detail}>{detail}</li>
          ))}
        </ul>
      ) : null}
      <ul className="db-status-hints">
        {block.setupHints.map((hint) => (
          <li key={hint}>{hint}</li>
        ))}
      </ul>
    </div>
  );
}

export function CatalogPage() {
  const initialLayoutPreferences = useMemo(() => readCatalogLayoutPreferences(), []);
  const filterResetMountedRef = useRef(false);
  const [persistedState, setPersistedState, resetPersistedState] =
    usePersistentPageState<CatalogPageState>(CATALOG_STATE_KEY, {
      ...initialCatalogPageState,
      pageSize: initialLayoutPreferences.pageSize,
      visibleColumnIds: initialLayoutPreferences.visibleColumnIds,
    });
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

  const [q, setQ] = useState(persistedState.q);
  const [selectedFamily, setSelectedFamily] = useState(persistedState.selectedFamily);
  const [selectedCategory, setSelectedCategory] = useState(persistedState.selectedCategory);
  const [selectedSubCategory, setSelectedSubCategory] = useState(persistedState.selectedSubCategory);
  const [manufacturer, setManufacturer] = useState(persistedState.manufacturer);
  const [marketplace, setMarketplace] = useState<MarketplaceFilter>(persistedState.marketplace);
  const [source, setSource] = useState<PriceMonitoringSource>(persistedState.source);
  const [showComposite, setShowComposite] = useState(persistedState.showComposite);
  const [includeIgnored, setIncludeIgnored] = useState(persistedState.includeIgnored);
  const [page, setPage] = useState(persistedState.page);
  const [pageSize, setPageSize] = useState(persistedState.pageSize);
  const [visibleColumnIds, setVisibleColumnIds] = useState<Set<CatalogColumnId>>(
    () => new Set(normalizeVisibleColumnIds(persistedState.visibleColumnIds) ?? initialLayoutPreferences.visibleColumnIds),
  );
  const [selectedModels, setSelectedModels] = useState<Set<string>>(() => new Set());
  const [sourceUrlProduct, setSourceUrlProduct] = useState<CatalogProduct | null>(null);
  const [sourceUrlRefreshToken, setSourceUrlRefreshToken] = useState(0);

  const [previewResult, setPreviewResult] = useState<PriceMonitoringSelectionResult | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  const [runResult, setRunResult] = useState<PriceMonitoringSelectionResult | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [isRunLoading, setIsRunLoading] = useState(false);

  const isColumnVisible = useCallback(
    (columnId: CatalogColumnId) => visibleColumnIds.has(columnId),
    [visibleColumnIds],
  );

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
    () => getCategoryOptions(categoryHierarchy, selectedFamily),
    [categoryHierarchy, selectedFamily],
  );

  const subCategoryOptions = useMemo(
    () => getSubCategoryOptions(categoryHierarchy, selectedFamily, selectedCategory),
    [categoryHierarchy, selectedCategory, selectedFamily],
  );

  const productParams = useMemo<CatalogProductsParams>(
    () => {
      const trimmedQ = q.trim();
      const trimmedManufacturer = manufacturer.trim();
      const params: CatalogProductsParams = {
        page,
        page_size: pageSize,
        atomic_only: !showComposite,
        ignored: includeIgnored ? "include" : "exclude",
      };

      if (trimmedQ.length > 0) {
        params.q = trimmedQ;
      }

      Object.assign(
        params,
        makeHierarchyFilterParams({
          family: selectedFamily,
          categoryName: selectedCategory,
          subCategory: selectedSubCategory,
        }),
      );

      if (trimmedManufacturer.length > 0) {
        params.manufacturer = trimmedManufacturer;
      }

      if (marketplace !== "all") {
        params.marketplace = marketplace;
      }

      return params;
    },
    [
      includeIgnored,
      manufacturer,
      marketplace,
      page,
      pageSize,
      q,
      selectedCategory,
      selectedFamily,
      selectedSubCategory,
      showComposite,
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

  useEffect(() => {
    writeCatalogLayoutPreferences({
      visibleColumnIds: CATALOG_COLUMNS.map((column) => column.id).filter((columnId) =>
        visibleColumnIds.has(columnId),
      ),
      pageSize,
    });
  }, [pageSize, visibleColumnIds]);

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
      page,
      pageSize,
      visibleColumnIds: CATALOG_COLUMNS.map((column) => column.id).filter((columnId) =>
        visibleColumnIds.has(columnId),
      ),
    });
  }, [
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
    visibleColumnIds,
  ]);

  useEffect(() => {
    if (!filterResetMountedRef.current) {
      filterResetMountedRef.current = true;
      return;
    }

    setPage(1);
    setSelectedModels(new Set());
    setPreviewResult(null);
    setRunResult(null);
  }, [
    includeIgnored,
    manufacturer,
    marketplace,
    pageSize,
    q,
    selectedCategory,
    selectedFamily,
    selectedSubCategory,
    showComposite,
  ]);

  const eligibleVisibleModels = useMemo(
    () =>
      productsResponse.items
        .filter((product) => getSelectionBlocker(product) === null)
        .map((product) => normalizeModel(product.model))
        .filter((model) => model.length > 0),
    [productsResponse.items],
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

  const toggleColumn = (columnId: CatalogColumnId) => {
    if (REQUIRED_CATALOG_COLUMNS.includes(columnId)) {
      return;
    }

    setVisibleColumnIds((currentColumns) => {
      const nextColumns = new Set(currentColumns);
      if (nextColumns.has(columnId)) {
        nextColumns.delete(columnId);
      } else {
        nextColumns.add(columnId);
      }

      REQUIRED_CATALOG_COLUMNS.forEach((requiredColumn) => nextColumns.add(requiredColumn));
      return nextColumns;
    });
  };

  const resetColumns = () => {
    setVisibleColumnIds(new Set(DEFAULT_VISIBLE_CATALOG_COLUMNS));
    setPageSize(DEFAULT_PAGE_SIZE);
  };

  const resetSavedCatalogState = () => {
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
    setPage(initialCatalogPageState.page);
    setPageSize(initialCatalogPageState.pageSize);
    setVisibleColumnIds(new Set(initialCatalogPageState.visibleColumnIds));
    setSelectedModels(new Set());
    setSourceUrlProduct(null);
    setPreviewResult(null);
    setRunResult(null);
  };

  const buildSelectionBody = (dryRun: boolean) =>
    makeSelectionBody(
      source,
      selectedModels,
      {
        q,
        family: selectedFamily,
        categoryName: selectedCategory,
        subCategory: selectedSubCategory,
        manufacturer,
        marketplace,
        includeIgnored,
      },
      dryRun,
    );

  const previewSelection = async () => {
    setIsPreviewLoading(true);
    setPreviewError(null);
    setPreviewResult(null);
    try {
      const result = await commerceClient.previewPriceMonitoringSelection(buildSelectionBody(true));
      setPreviewResult(result);
    } catch (error) {
      setPreviewError(getCommerceApiErrorMessage(error));
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const createRun = async () => {
    setIsRunLoading(true);
    setRunError(null);
    setRunResult(null);
    try {
      const result = await commerceClient.createPriceMonitoringRun(buildSelectionBody(false));
      setRunResult(result);
    } catch (error) {
      setRunError(getCommerceApiErrorMessage(error));
    } finally {
      setIsRunLoading(false);
    }
  };

  const totalPages = Math.max(
    1,
    Math.ceil(productsResponse.filtered_total / productsResponse.page_size),
  );
  const catalogReadinessBlock =
    productsReadinessBlock ?? productsWarningBlock ?? summaryReadinessBlock ?? filtersReadinessBlock;
  const isCatalogLocked = catalogReadinessBlock !== null;

  return (
    <div className="page-stack catalog-page">
      <section className="page-header">
        <p className="eyebrow">Catalog</p>
        <h2>Commerce catalog</h2>
        <p>Commerce API base URL: {commerceClient.commerceApiBaseUrl}</p>
        <button className="text-button" type="button" onClick={resetSavedCatalogState}>
          Reset saved Catalog state
        </button>
      </section>

      {catalogReadinessBlock ? (
        <CatalogReadinessBanner
          block={catalogReadinessBlock}
          onRetry={() => {
            void loadSummary();
            void loadFilterOptions();
            void loadProducts();
          }}
        />
      ) : null}

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Summary</p>
            <h3>Catalog health</h3>
          </div>
          <button className="button secondary" type="button" onClick={() => void loadSummary()}>
            Refresh
          </button>
        </div>
        {isSummaryLoading ? <LoadingState label="Loading catalog summary..." /> : null}
        {summaryError ? (
          <>
            <ErrorState message={summaryError} onRetry={() => void loadSummary()} />
            <CatalogSetupHint />
          </>
        ) : null}
        {!isSummaryLoading && !summaryError && !summaryReadinessBlock ? (
          <dl className="summary-grid catalog-summary-grid">
            <SummaryCard label="Total products" value={getSummaryNumber(summary, ["total_products", "total"])} />
            <SummaryCard label="Active products" value={getSummaryNumber(summary, ["active_products", "active"])} />
            <SummaryCard label="Atomic products" value={getSummaryNumber(summary, ["atomic_products", "atomic"])} />
            <SummaryCard
              label="Composite/invalid"
              value={getSummaryNumber(summary, [
                "composite_invalid_models",
                "composite_products",
                "non_atomic_products",
              ])}
            />
            <SummaryCard
              label="BestPrice products"
              value={getSummaryNumber(summary, ["bestprice_products", "bestprice"])}
            />
            <SummaryCard
              label="Skroutz products"
              value={getSummaryNumber(summary, ["skroutz_products", "skroutz"])}
            />
            <SummaryCard
              label="Missing MPN"
              value={getSummaryNumber(summary, ["missing_mpn", "missing_mpn_products"])}
            />
          </dl>
        ) : null}
      </section>

      <SourceUrlImportPanel
        disabled={isCatalogLocked}
        onApplied={() => {
          setSourceUrlRefreshToken((value) => value + 1);
        }}
      />

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Filters</p>
            <h3>Catalog products</h3>
          </div>
          <button className="button secondary" type="button" onClick={() => void loadProducts()}>
            Refresh
          </button>
        </div>

        {areFiltersLoading ? <p className="muted">Loading categories and brands...</p> : null}
        {filtersError ? (
          <ErrorState message={filtersError} onRetry={() => void loadFilterOptions()} />
        ) : null}

        <div className="filter-grid">
          <label>
            Search
            <input
              type="search"
              value={q}
              onChange={(event) => setQ(event.target.value)}
              placeholder="Model, MPN, or name"
            />
          </label>

          <label>
            Family
            <select
              value={selectedFamily}
              onChange={(event) => {
                setSelectedFamily(event.target.value);
                setSelectedCategory("");
                setSelectedSubCategory("");
              }}
            >
              <option value="">All families</option>
              {familyOptions.map((item) => (
                <option key={item.value} value={item.value}>
                  {formatHierarchyOptionLabel(item)}
                </option>
              ))}
            </select>
          </label>

          <label>
            Category
            <select
              value={selectedCategory}
              onChange={(event) => {
                setSelectedCategory(event.target.value);
                setSelectedSubCategory("");
              }}
              disabled={!selectedFamily}
            >
              <option value="">All categories</option>
              {categoryLevelOptions.map((item) => (
                <option key={item.value} value={item.value}>
                  {formatHierarchyOptionLabel(item)}
                </option>
              ))}
            </select>
          </label>

          <label>
            Sub-Category
            <select
              value={selectedSubCategory}
              onChange={(event) => setSelectedSubCategory(event.target.value)}
              disabled={!selectedFamily || !selectedCategory}
            >
              <option value="">All sub-categories</option>
              {subCategoryOptions.map((item) => (
                <option key={item.value} value={item.value}>
                  {formatHierarchyOptionLabel(item)}
                </option>
              ))}
            </select>
          </label>

          <label>
            Manufacturer
            <select value={manufacturer} onChange={(event) => setManufacturer(event.target.value.trim())}>
              <option value="">All manufacturers</option>
              {brandOptions.map((item) => (
                <option key={item.manufacturer} value={item.manufacturer}>
                  {item.manufacturer}
                  {formatOptionCount(item.count)}
                </option>
              ))}
            </select>
          </label>

          <label>
            Marketplace
            <select
              value={marketplace}
              onChange={(event) => setMarketplace(event.target.value as MarketplaceFilter)}
            >
              <option value="all">All</option>
              <option value="bestprice">BestPrice</option>
              <option value="skroutz">Skroutz</option>
              <option value="both">Both</option>
              <option value="none">None</option>
            </select>
          </label>

          <label title="Marketplace monitoring source. Direct vendor source URL capture uses Vendor Sources.">
            Marketplace source (Skroutz / BestPrice)
            <select
              value={source}
              onChange={(event) => setSource(event.target.value as PriceMonitoringSource)}
            >
              <option value="skroutz">Skroutz</option>
              <option value="bestprice">BestPrice</option>
            </select>
          </label>

          <label>
            Page size
            <select
              value={pageSize}
              onChange={(event) => setPageSize(Number(event.target.value))}
            >
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
            </select>
          </label>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={showComposite}
              onChange={(event) => setShowComposite(event.target.checked)}
            />
            Show composite models
          </label>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={includeIgnored}
              onChange={(event) => setIncludeIgnored(event.target.checked)}
            />
            Include ignored
          </label>
        </div>

        <p className="muted">
          Family, Category, and Sub-Category use backend-native hierarchy filters. Raw OpenCart
          category data is available in each product row for debugging.
        </p>

        <details className="column-controls">
          <summary>Columns</summary>
          <div className="column-controls-panel">
            {CATALOG_COLUMNS.map((column) => (
              <label className="checkbox-row" key={column.id}>
                <input
                  type="checkbox"
                  checked={visibleColumnIds.has(column.id)}
                  disabled={column.required}
                  onChange={() => toggleColumn(column.id)}
                />
                {column.label}
                {column.required ? <span className="muted">required</span> : null}
              </label>
            ))}
            <button className="button secondary inline-button" type="button" onClick={resetColumns}>
              Reset columns
            </button>
          </div>
        </details>

        <div className="toolbar">
          <p className="muted">
            {productsResponse.filtered_total.toLocaleString()} matching products.
            {selectedModels.size > 0 ? ` ${selectedModels.size} selected.` : " No products selected."}
            {" "}Selection clears when filters change.
          </p>
          <div className="button-row">
            <button
              className="button secondary"
              type="button"
              onClick={() => void previewSelection()}
              disabled={isPreviewLoading || isRunLoading || isCatalogLocked}
            >
              {isPreviewLoading ? "Previewing..." : "Preview selection"}
            </button>
            <button
              className="button primary"
              type="button"
              onClick={() => void createRun()}
              disabled={isRunLoading || isPreviewLoading || isCatalogLocked}
            >
              {isRunLoading ? "Creating..." : "Create price monitoring run"}
            </button>
          </div>
        </div>

        {previewError ? <ErrorState message={previewError} /> : null}
        {previewResult ? (
          <div className="state-block">
            <strong>Selection preview</strong>
            <ResultSummary result={previewResult} />
          </div>
        ) : null}

        {runError ? <ErrorState message={runError} /> : null}
        {runResult ? (
          <div className="state-block">
            <strong>Price monitoring run</strong>
            <ResultSummary result={runResult} />
          </div>
        ) : null}

        {areProductsLoading ? <LoadingState label="Loading catalog products..." /> : null}
        {productsError ? (
          <>
            <ErrorState message={productsError} onRetry={() => void loadProducts()} />
            <CatalogSetupHint />
          </>
        ) : null}
        {!areProductsLoading && !productsError && !productsReadinessBlock && productsResponse.items.length === 0 ? (
          <EmptyState
            title={productsWarningBlock ? "Catalog database/import required" : "No products found"}
            message={
              productsWarningBlock
                ? CATALOG_READINESS_REQUIRED_MESSAGE
                : "Try broadening the current filters."
            }
          />
        ) : null}
        {!areProductsLoading && !productsError && productsResponse.items.length > 0 ? (
          <>
            <div className="table-wrap catalog-table-wrap">
              <table>
                <thead>
                  <tr>
                    {isColumnVisible("select") ? (
                      <th>
                        <input
                          type="checkbox"
                          aria-label="Select all visible eligible products"
                          checked={allVisibleSelected}
                          disabled={eligibleVisibleModels.length === 0}
                          onChange={toggleAllVisible}
                        />
                      </th>
                    ) : null}
                    {isColumnVisible("model") ? <th>Model</th> : null}
                    {isColumnVisible("name") ? <th>Name</th> : null}
                    {isColumnVisible("manufacturer") ? <th>Manufacturer</th> : null}
                    {isColumnVisible("family") ? <th>Family</th> : null}
                    {isColumnVisible("category_name") ? <th>Category</th> : null}
                    {isColumnVisible("sub_category") ? <th>Sub-Category</th> : null}
                    {isColumnVisible("mpn") ? <th>MPN</th> : null}
                    {isColumnVisible("price") ? <th>Price</th> : null}
                    {isColumnVisible("quantity") ? <th>Qty</th> : null}
                    {isColumnVisible("bestprice_status") ? <th>BestPrice</th> : null}
                    {isColumnVisible("skroutz_status") ? <th>Skroutz</th> : null}
                    {isColumnVisible("ignored") ? <th>Ignored</th> : null}
                    {isColumnVisible("status") ? <th>Status</th> : null}
                    {isColumnVisible("automation_eligible") ? <th>Automation</th> : null}
                    {isColumnVisible("is_atomic_model") ? <th>Atomic</th> : null}
                    {isColumnVisible("category_levels") ? <th>Category levels</th> : null}
                    {isColumnVisible("raw_category") ? <th>Raw category</th> : null}
                    {isColumnVisible("warnings") ? <th>Warnings / eligibility</th> : null}
                    <th>Source URLs</th>
                  </tr>
                </thead>
                <tbody>
                  {productsResponse.items.map((product) => {
                    const model = normalizeModel(product.model);
                    const selectionBlocker = getSelectionBlocker(product);
                    const isSelected = selectedModels.has(model);
                    const warnings = Array.isArray(product.warnings) ? product.warnings : [];
                    const rawCategory = product.raw_category ?? product.category ?? "";
                    const categoryLevels = Array.isArray(product.category_levels)
                      ? product.category_levels.join(" > ")
                      : "";

                    return (
                      <tr key={model}>
                        {isColumnVisible("select") ? (
                          <td>
                            <input
                              type="checkbox"
                              aria-label={`Select ${model}`}
                              checked={isSelected}
                              disabled={selectionBlocker !== null}
                              onChange={() => toggleModel(model)}
                            />
                          </td>
                        ) : null}
                        {isColumnVisible("model") ? <td className="nowrap-cell">{model}</td> : null}
                        {isColumnVisible("name") ? <td>{formatValue(product.name)}</td> : null}
                        {isColumnVisible("manufacturer") ? <td>{formatValue(product.manufacturer)}</td> : null}
                        {isColumnVisible("family") ? <td>{formatValue(product.family)}</td> : null}
                        {isColumnVisible("category_name") ? <td>{formatValue(product.category_name)}</td> : null}
                        {isColumnVisible("sub_category") ? <td>{formatValue(product.sub_category)}</td> : null}
                        {isColumnVisible("mpn") ? <td>{formatValue(product.mpn)}</td> : null}
                        {isColumnVisible("price") ? (
                          <td className="nowrap-cell">{formatMoney(product.price)}</td>
                        ) : null}
                        {isColumnVisible("quantity") ? <td>{formatValue(product.quantity)}</td> : null}
                        {isColumnVisible("bestprice_status") ? (
                          <td>
                            <span className="status-badge neutral">
                              {getMarketplaceStatus(product.bestprice_status)}
                            </span>
                          </td>
                        ) : null}
                        {isColumnVisible("skroutz_status") ? (
                          <td>
                            <span className="status-badge neutral">
                              {getMarketplaceStatus(product.skroutz_status)}
                            </span>
                          </td>
                        ) : null}
                        {isColumnVisible("ignored") ? <td>{product.ignored ? "yes" : "no"}</td> : null}
                        {isColumnVisible("status") ? <td>{formatValue(product.status)}</td> : null}
                        {isColumnVisible("automation_eligible") ? (
                          <td>
                            {typeof product.automation_eligible === "boolean"
                              ? product.automation_eligible
                                ? "yes"
                                : "no"
                              : "-"}
                          </td>
                        ) : null}
                        {isColumnVisible("is_atomic_model") ? (
                          <td>
                            {typeof product.is_atomic_model === "boolean"
                              ? product.is_atomic_model
                                ? "yes"
                                : "no"
                              : "-"}
                          </td>
                        ) : null}
                        {isColumnVisible("category_levels") ? (
                          <td className="compact-debug-cell">{formatValue(categoryLevels)}</td>
                        ) : null}
                        {isColumnVisible("raw_category") ? (
                          <td>
                            <details className="raw-category-detail">
                              <summary>Raw</summary>
                              <span>{formatValue(rawCategory)}</span>
                            </details>
                          </td>
                        ) : null}
                        {isColumnVisible("warnings") ? (
                          <td>
                            <div className="eligibility-cell">
                              {selectionBlocker ? (
                                <span className="status-badge queued">{selectionBlocker}</span>
                              ) : (
                                <span className="status-badge success">Eligible</span>
                              )}
                              {warnings.length > 0 ? (
                                <span className="muted">{warnings.join(", ")}</span>
                              ) : null}
                            </div>
                          </td>
                        ) : null}
                        <td>
                          <button
                            className="button secondary compact-button"
                            type="button"
                            onClick={() => setSourceUrlProduct(product)}
                            disabled={isCatalogLocked}
                            aria-label={`Source URLs for ${model}`}
                          >
                            Source URLs
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="pagination-row">
              <button
                className="button secondary"
                type="button"
                disabled={page <= 1 || areProductsLoading}
                onClick={() => setPage((currentPage) => Math.max(1, currentPage - 1))}
              >
                Previous
              </button>
              <span className="muted">
                Page {productsResponse.page} of {totalPages}
              </span>
              <button
                className="button secondary"
                type="button"
                disabled={page >= totalPages || areProductsLoading}
                onClick={() => setPage((currentPage) => currentPage + 1)}
              >
                Next
              </button>
            </div>
          </>
        ) : null}
      </section>
      <CatalogSourceUrlManager
        product={sourceUrlProduct}
        disabled={isCatalogLocked}
        refreshToken={sourceUrlRefreshToken}
        onClose={() => setSourceUrlProduct(null)}
      />
    </div>
  );
}
