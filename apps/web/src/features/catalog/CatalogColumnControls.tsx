import { CATALOG_COLUMNS } from "./catalogConstants";
import type { CatalogColumnId } from "./catalogTypes";

export function CatalogColumnControls({
  visibleColumnIds,
  onToggleColumn,
  onResetColumns,
}: {
  visibleColumnIds: Set<CatalogColumnId>;
  onToggleColumn: (columnId: CatalogColumnId) => void;
  onResetColumns: () => void;
}) {
  return (
    <details className="column-controls">
      <summary>Columns</summary>
      <div className="column-controls-panel">
        {CATALOG_COLUMNS.map((column) => (
          <label className="checkbox-row" key={column.id}>
            <input
              type="checkbox"
              checked={visibleColumnIds.has(column.id)}
              disabled={column.required}
              onChange={() => onToggleColumn(column.id)}
            />
            {column.label}
            {column.required ? <span className="muted">required</span> : null}
          </label>
        ))}
        <button className="button secondary inline-button" type="button" onClick={onResetColumns}>
          Reset columns
        </button>
      </div>
    </details>
  );
}
