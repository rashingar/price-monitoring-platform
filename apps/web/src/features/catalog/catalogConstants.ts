import type { CatalogColumnDefinition, CatalogColumnId, CatalogPageState } from "./catalogTypes";

export const DEFAULT_PAGE_SIZE = 100;
export const CATALOG_COLUMNS_STORAGE_KEY = "productFactoryUi.catalog.columns.v1";
export const CATALOG_STATE_KEY = "product-factory-ui:catalog:v2";
export const CATALOG_PAGE_SIZE_OPTIONS = [50, 100, 200] as const;

export const CATALOG_COLUMNS: CatalogColumnDefinition[] = [
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
  { id: "warnings", label: "Warnings" },
  { id: "status", label: "Status" },
  { id: "automation_eligible", label: "Automation eligible" },
  { id: "is_atomic_model", label: "Atomic" },
  { id: "raw_category", label: "Raw category" },
  { id: "category_levels", label: "Category levels" },
];

export const DEFAULT_VISIBLE_CATALOG_COLUMNS: CatalogColumnId[] = [
  "select",
  "model",
  "name",
  "price",
  "quantity",
  "bestprice_status",
  "ignored",
  "warnings",
];

export const LEGACY_DEFAULT_VISIBLE_CATALOG_COLUMNS: CatalogColumnId[] = [
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

export const initialCatalogPageState: CatalogPageState = {
  q: "",
  selectedFamily: "",
  selectedCategory: "",
  selectedSubCategory: "",
  manufacturer: "",
  marketplace: "all",
  source: "bestprice",
  showComposite: false,
  includeIgnored: false,
  sourceUrlsOnly: false,
  hasQuantity: false,
  page: 1,
  pageSize: DEFAULT_PAGE_SIZE,
  visibleColumnIds: DEFAULT_VISIBLE_CATALOG_COLUMNS,
};

export const REQUIRED_CATALOG_COLUMNS = CATALOG_COLUMNS.filter((column) => column.required).map(
  (column) => column.id,
);

export const CATALOG_COLUMN_IDS = new Set(CATALOG_COLUMNS.map((column) => column.id));

export function normalizeVisibleColumnIds(value: unknown): CatalogColumnId[] | null {
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

export function shouldUseCurrentCatalogColumnDefaults(value: CatalogColumnId[] | null): boolean {
  if (!value || value.length !== LEGACY_DEFAULT_VISIBLE_CATALOG_COLUMNS.length) {
    return false;
  }

  const legacyColumns = new Set(LEGACY_DEFAULT_VISIBLE_CATALOG_COLUMNS);
  return value.every((columnId) => legacyColumns.has(columnId));
}

export function serializeVisibleColumnIds(visibleColumnIds: Set<CatalogColumnId>): CatalogColumnId[] {
  return CATALOG_COLUMNS.map((column) => column.id).filter((columnId) => visibleColumnIds.has(columnId));
}
