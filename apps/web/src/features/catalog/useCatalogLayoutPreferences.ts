import { useCallback, useEffect } from "react";
import {
  CATALOG_COLUMNS_STORAGE_KEY,
  CATALOG_PAGE_SIZE_OPTIONS,
  DEFAULT_PAGE_SIZE,
  DEFAULT_VISIBLE_CATALOG_COLUMNS,
  REQUIRED_CATALOG_COLUMNS,
  normalizeVisibleColumnIds,
} from "./catalogConstants";
import type { CatalogColumnId, CatalogLayoutPreferences } from "./catalogTypes";

export function readCatalogLayoutPreferences(): CatalogLayoutPreferences {
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
      typeof record.pageSize === "number" && CATALOG_PAGE_SIZE_OPTIONS.includes(record.pageSize as 50 | 100 | 200)
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

export function useCatalogLayoutPreferences({
  visibleColumnIds,
  visibleColumnIdsArray,
  setVisibleColumnIds,
  pageSize,
  setPageSize,
}: {
  visibleColumnIds: Set<CatalogColumnId>;
  visibleColumnIdsArray: CatalogColumnId[];
  setVisibleColumnIds: React.Dispatch<React.SetStateAction<Set<CatalogColumnId>>>;
  pageSize: number;
  setPageSize: React.Dispatch<React.SetStateAction<number>>;
}) {
  const isColumnVisible = useCallback(
    (columnId: CatalogColumnId) => visibleColumnIds.has(columnId),
    [visibleColumnIds],
  );

  const toggleColumn = useCallback(
    (columnId: CatalogColumnId) => {
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
    },
    [setVisibleColumnIds],
  );

  const resetColumns = useCallback(() => {
    setVisibleColumnIds(new Set(DEFAULT_VISIBLE_CATALOG_COLUMNS));
    setPageSize(DEFAULT_PAGE_SIZE);
  }, [setPageSize, setVisibleColumnIds]);

  useEffect(() => {
    writeCatalogLayoutPreferences({
      visibleColumnIds: visibleColumnIdsArray,
      pageSize,
    });
  }, [pageSize, visibleColumnIdsArray]);

  return {
    isColumnVisible,
    toggleColumn,
    resetColumns,
  };
}
