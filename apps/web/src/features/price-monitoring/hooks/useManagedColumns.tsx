import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { isRecord } from "../format";

const MIN_COLUMN_WIDTH = 72;
const MAX_COLUMN_WIDTH = 640;

export interface ManagedColumn<Row, ColumnId extends string> {
  id: ColumnId;
  label: string;
  defaultWidth: number;
  minWidth?: number;
  required?: boolean;
  available?: boolean;
  className?: string;
  render: (row: Row) => ReactNode;
}

export interface ColumnPreferences<ColumnId extends string> {
  order: ColumnId[];
  visible: ColumnId[];
  widths: Partial<Record<ColumnId, number>>;
}

function clampColumnWidth(width: number, minWidth = MIN_COLUMN_WIDTH): number {
  if (!Number.isFinite(width)) {
    return minWidth;
  }

  return Math.min(MAX_COLUMN_WIDTH, Math.max(minWidth, Math.round(width)));
}

function defaultColumnPreferences<ColumnId extends string>(
  columns: Array<ManagedColumn<unknown, ColumnId>>,
): ColumnPreferences<ColumnId> {
  return {
    order: columns.map((column) => column.id),
    visible: columns.map((column) => column.id),
    widths: columns.reduce<Partial<Record<ColumnId, number>>>((widths, column) => {
      widths[column.id] = clampColumnWidth(column.defaultWidth, column.minWidth);
      return widths;
    }, {}),
  };
}

function normalizeColumnPreferences<ColumnId extends string>(
  value: ColumnPreferences<ColumnId>,
  columns: Array<ManagedColumn<unknown, ColumnId>>,
): ColumnPreferences<ColumnId> {
  const availableIds = new Set(columns.map((column) => column.id));
  const requiredIds = columns.filter((column) => column.required).map((column) => column.id);
  const ordered = value.order.filter((columnId) => availableIds.has(columnId));
  const missing = columns.map((column) => column.id).filter((columnId) => !ordered.includes(columnId));
  const visible = value.visible.filter((columnId) => availableIds.has(columnId));
  const nextVisible = Array.from(new Set([...requiredIds, ...visible]));
  const widths = columns.reduce<Partial<Record<ColumnId, number>>>((nextWidths, column) => {
    nextWidths[column.id] = clampColumnWidth(
      value.widths[column.id] ?? column.defaultWidth,
      column.minWidth,
    );
    return nextWidths;
  }, {});

  return {
    order: [...ordered, ...missing],
    visible: nextVisible.length > 0 ? nextVisible : columns.slice(0, 1).map((column) => column.id),
    widths,
  };
}

function loadColumnPreferences<ColumnId extends string>(
  storageKey: string,
  columns: Array<ManagedColumn<unknown, ColumnId>>,
): ColumnPreferences<ColumnId> {
  const defaults = defaultColumnPreferences(columns);
  if (typeof window === "undefined") {
    return defaults;
  }

  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) {
      return defaults;
    }
    const parsed = JSON.parse(raw) as Partial<ColumnPreferences<ColumnId>>;
    return normalizeColumnPreferences(
      {
        order: Array.isArray(parsed.order) ? parsed.order : defaults.order,
        visible: Array.isArray(parsed.visible) ? parsed.visible : defaults.visible,
        widths: isRecord(parsed.widths)
          ? (parsed.widths as Partial<Record<ColumnId, number>>)
          : defaults.widths,
      },
      columns,
    );
  } catch {
    return defaults;
  }
}

export function useManagedColumns<Row, ColumnId extends string>(
  storageKey: string,
  columns: Array<ManagedColumn<Row, ColumnId>>,
) {
  const unknownColumns = columns as Array<ManagedColumn<unknown, ColumnId>>;
  const [preferences, setPreferences] = useState<ColumnPreferences<ColumnId>>(() =>
    loadColumnPreferences(storageKey, unknownColumns),
  );
  const normalizedPreferences = useMemo(
    () => normalizeColumnPreferences(preferences, unknownColumns),
    [preferences, unknownColumns],
  );
  const availableColumns = useMemo(
    () => columns.filter((column) => column.available !== false),
    [columns],
  );
  const visibleColumnIds = useMemo(() => new Set(normalizedPreferences.visible), [normalizedPreferences.visible]);
  const activeColumns = useMemo(() => {
    const byId = new Map(availableColumns.map((column) => [column.id, column]));
    return normalizedPreferences.order
      .map((columnId) => byId.get(columnId))
      .filter((column): column is ManagedColumn<Row, ColumnId> => Boolean(column))
      .filter((column) => visibleColumnIds.has(column.id));
  }, [availableColumns, normalizedPreferences.order, visibleColumnIds]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(storageKey, JSON.stringify(normalizedPreferences));
  }, [normalizedPreferences, storageKey]);

  const toggleColumn = useCallback(
    (columnId: ColumnId) => {
      const column = columns.find((candidate) => candidate.id === columnId);
      if (column?.required) {
        return;
      }
      setPreferences((current) => {
        const currentVisible = new Set(current.visible);
        if (currentVisible.has(columnId)) {
          currentVisible.delete(columnId);
        } else {
          currentVisible.add(columnId);
        }
        return { ...current, visible: Array.from(currentVisible) };
      });
    },
    [columns],
  );
  const moveColumn = useCallback((columnId: ColumnId, direction: -1 | 1) => {
    setPreferences((current) => {
      const order = [...current.order];
      const index = order.indexOf(columnId);
      const nextIndex = index + direction;
      if (index < 0 || nextIndex < 0 || nextIndex >= order.length) {
        return current;
      }
      [order[index], order[nextIndex]] = [order[nextIndex], order[index]];
      return { ...current, order };
    });
  }, []);
  const resizeColumn = useCallback(
    (columnId: ColumnId, width: number) => {
      const column = columns.find((candidate) => candidate.id === columnId);
      setPreferences((current) => ({
        ...current,
        widths: {
          ...current.widths,
          [columnId]: clampColumnWidth(width, column?.minWidth),
        },
      }));
    },
    [columns],
  );
  const resetColumns = useCallback(() => {
    setPreferences(defaultColumnPreferences(unknownColumns));
  }, [unknownColumns]);

  return {
    activeColumns,
    availableColumns,
    preferences: normalizedPreferences,
    visibleColumnIds,
    toggleColumn,
    moveColumn,
    resizeColumn,
    resetColumns,
  };
}

export function getColumnWidth<Row, ColumnId extends string>(
  column: ManagedColumn<Row, ColumnId>,
  preferences: ColumnPreferences<ColumnId>,
): number {
  return clampColumnWidth(preferences.widths[column.id] ?? column.defaultWidth, column.minWidth);
}

export function getManagedTableWidth<Row, ColumnId extends string>(
  columns: Array<ManagedColumn<Row, ColumnId>>,
  preferences: ColumnPreferences<ColumnId>,
): number {
  return columns.reduce((total, column) => total + getColumnWidth(column, preferences), 0);
}

export function ColumnControls<Row, ColumnId extends string>({
  columns,
  preferences,
  visibleColumnIds,
  onToggleColumn,
  onMoveColumn,
  onResizeColumn,
  onReset,
}: {
  columns: Array<ManagedColumn<Row, ColumnId>>;
  preferences: ColumnPreferences<ColumnId>;
  visibleColumnIds: Set<ColumnId>;
  onToggleColumn: (columnId: ColumnId) => void;
  onMoveColumn: (columnId: ColumnId, direction: -1 | 1) => void;
  onResizeColumn: (columnId: ColumnId, width: number) => void;
  onReset: () => void;
}) {
  const byId = new Map(columns.map((column) => [column.id, column]));
  const orderedColumns = preferences.order
    .map((columnId) => byId.get(columnId))
    .filter((column): column is ManagedColumn<Row, ColumnId> => Boolean(column))
    .filter((column) => column.available !== false);

  return (
    <details className="column-controls managed-column-controls">
      <summary>Columns</summary>
      <div className="column-controls-panel managed-column-controls-panel">
        {orderedColumns.map((column, index) => (
          <div className="column-control-row" key={column.id}>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={visibleColumnIds.has(column.id)}
                disabled={column.required}
                onChange={() => onToggleColumn(column.id)}
              />
              <span>{column.label}</span>
            </label>
            <div className="column-control-actions">
              <button
                className="button secondary icon-button"
                type="button"
                disabled={index === 0}
                title="Move column left"
                onClick={() => onMoveColumn(column.id, -1)}
              >
                {"<"}
              </button>
              <button
                className="button secondary icon-button"
                type="button"
                disabled={index === orderedColumns.length - 1}
                title="Move column right"
                onClick={() => onMoveColumn(column.id, 1)}
              >
                {">"}
              </button>
              <label className="column-width-control">
                Width
                <input
                  className="column-width-input"
                  type="number"
                  min={column.minWidth ?? MIN_COLUMN_WIDTH}
                  max={MAX_COLUMN_WIDTH}
                  step="10"
                  value={getColumnWidth(column, preferences)}
                  onChange={(event) => onResizeColumn(column.id, Number(event.target.value))}
                />
              </label>
            </div>
          </div>
        ))}
        <button className="button secondary inline-button" type="button" onClick={onReset}>
          Reset columns
        </button>
      </div>
    </details>
  );
}
