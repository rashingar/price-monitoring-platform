import type {
  SourceUrlCandidateReviewLayout,
  SourceUrlCandidateReviewLayoutColumn,
} from "../../api/commerceTypes";
import {
  DEFAULT_COLUMNS,
  DEFAULT_COLUMN_WIDTH_PX,
  FALLBACK_REVIEW_ACTIONS,
  MAX_COLUMN_WIDTH_PX,
  MIN_COLUMN_WIDTH_PX,
  REVIEW_LAYOUT_USER_KEY,
  SOURCE_URL_CANDIDATE_REVIEW_LAYOUT_STORAGE_KEY,
} from "./sourceUrlCandidateConstants";

interface LocalReviewLayoutPreferences {
  columns?: Array<{
    key: string;
    visible: boolean;
    order: number;
    width_px: number;
  }>;
}

export function columnKey(column: SourceUrlCandidateReviewLayoutColumn): string {
  return String(column.key ?? column.id ?? column.field ?? "");
}

export function columnLabel(column: SourceUrlCandidateReviewLayoutColumn): string {
  const key = columnKey(column);
  return String(column.label ?? column.title ?? key.replace(/_/g, " "));
}

export function isColumnVisible(column: SourceUrlCandidateReviewLayoutColumn): boolean {
  if (columnKey(column) === "actions") {
    return false;
  }

  if (typeof column.visible === "boolean") {
    return column.visible;
  }

  if (typeof column.table_column_visible === "boolean") {
    return column.table_column_visible;
  }

  return true;
}

export function normalizeColumns(
  columns: SourceUrlCandidateReviewLayoutColumn[],
): SourceUrlCandidateReviewLayoutColumn[] {
  const sourceByKey = new Map(
    columns
      .filter((column) => columnKey(column).length > 0)
      .map((column) => [columnKey(column), column]),
  );
  const source = DEFAULT_COLUMNS.map((defaultColumn) => {
    const sourceColumn = sourceByKey.get(columnKey(defaultColumn));
    return sourceColumn
      ? {
          ...sourceColumn,
          key: columnKey(defaultColumn),
          label: defaultColumn.label,
          visible: typeof sourceColumn.visible === "boolean" ? sourceColumn.visible : defaultColumn.visible,
          table_column_visible:
            typeof sourceColumn.table_column_visible === "boolean"
              ? sourceColumn.table_column_visible
              : defaultColumn.table_column_visible,
          order: typeof sourceColumn.order === "number" ? sourceColumn.order : defaultColumn.order,
          width_px: typeof sourceColumn.width_px === "number" ? sourceColumn.width_px : defaultColumn.width_px,
        }
      : defaultColumn;
  });

  return source
    .filter((column) => columnKey(column).length > 0 && columnKey(column) !== "actions")
    .map((column, index) => ({
      ...column,
      key: columnKey(column),
      label: columnLabel(column),
      visible: isColumnVisible(column),
      table_column_visible: isColumnVisible(column),
      width_px: typeof column.width_px === "number" ? column.width_px : DEFAULT_COLUMN_WIDTH_PX,
      order: typeof column.order === "number" ? column.order : index,
    }))
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
}

export function makeFallbackLayout(): SourceUrlCandidateReviewLayout {
  return {
    user_key: REVIEW_LAYOUT_USER_KEY,
    columns: normalizeColumns(DEFAULT_COLUMNS),
    actions: { table_column_visible: false, replacement: "inline_panel" },
    review_panel: { mode: "inline_row", open_on: "row_single_click", review_actions: FALLBACK_REVIEW_ACTIONS },
  };
}

export function localStorageOrNull(): Storage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

export function serializeLocalReviewLayout(layout: SourceUrlCandidateReviewLayout): LocalReviewLayoutPreferences {
  return {
    columns: normalizeColumns(layout.columns).map((column, order) => ({
      key: columnKey(column),
      visible: isColumnVisible(column),
      order,
      width_px: getColumnWidth(column),
    })),
  };
}

export function loadLocalSourceUrlCandidateReviewLayout(): SourceUrlCandidateReviewLayout {
  const fallback = makeFallbackLayout();
  const storage = localStorageOrNull();
  if (storage === null) {
    return fallback;
  }

  try {
    const rawValue = storage.getItem(SOURCE_URL_CANDIDATE_REVIEW_LAYOUT_STORAGE_KEY);
    if (!rawValue) {
      return fallback;
    }
    const payload = JSON.parse(rawValue) as LocalReviewLayoutPreferences;
    const columns = Array.isArray(payload.columns) ? payload.columns : [];
    return {
      ...fallback,
      columns: normalizeColumns(columns),
    };
  } catch {
    return fallback;
  }
}

export function saveLocalSourceUrlCandidateReviewLayout(
  layout: SourceUrlCandidateReviewLayout,
): SourceUrlCandidateReviewLayout {
  const nextLayout = {
    ...makeFallbackLayout(),
    columns: normalizeColumns(layout.columns),
  };
  const storage = localStorageOrNull();
  if (storage !== null) {
    storage.setItem(
      SOURCE_URL_CANDIDATE_REVIEW_LAYOUT_STORAGE_KEY,
      JSON.stringify(serializeLocalReviewLayout(nextLayout)),
    );
  }
  return nextLayout;
}

export function resetLocalSourceUrlCandidateReviewLayout(): SourceUrlCandidateReviewLayout {
  localStorageOrNull()?.removeItem(SOURCE_URL_CANDIDATE_REVIEW_LAYOUT_STORAGE_KEY);
  return makeFallbackLayout();
}

export function getColumnWidth(column: SourceUrlCandidateReviewLayoutColumn): number {
  const width = typeof column.width_px === "number" ? column.width_px : DEFAULT_COLUMN_WIDTH_PX;
  return Math.min(MAX_COLUMN_WIDTH_PX, Math.max(MIN_COLUMN_WIDTH_PX, width));
}

export function moveColumn(
  columns: SourceUrlCandidateReviewLayoutColumn[],
  index: number,
  direction: -1 | 1,
): SourceUrlCandidateReviewLayoutColumn[] {
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= columns.length) {
    return columns;
  }

  const next = [...columns];
  const [item] = next.splice(index, 1);
  next.splice(nextIndex, 0, item);
  return next.map((column, order) => ({ ...column, order }));
}
