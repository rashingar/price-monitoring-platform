import type {
  SourceUrlCandidateReviewLayout,
  SourceUrlCandidateReviewLayoutColumn,
} from "../../api/commerceTypes";
import {
  DEFAULT_COLUMN_WIDTH_PX,
  MAX_COLUMN_WIDTH_PX,
  MIN_COLUMN_WIDTH_PX,
} from "./sourceUrlCandidateConstants";
import {
  columnKey,
  columnLabel,
  getColumnWidth,
  isColumnVisible,
  moveColumn,
  normalizeColumns,
} from "./sourceUrlCandidateLayout";

interface SourceUrlCandidateLayoutSettingsCardProps {
  layout: SourceUrlCandidateReviewLayout;
  error: string | null;
  isSaving: boolean;
  onChange: (layout: SourceUrlCandidateReviewLayout) => void;
  onSave: () => void;
  onReset: () => void;
}

export function SourceUrlCandidateLayoutSettingsCard({
  layout,
  error,
  isSaving,
  onChange,
  onSave,
  onReset,
}: SourceUrlCandidateLayoutSettingsCardProps) {
  const columns = normalizeColumns(layout.columns);

  function updateColumn(index: number, update: Partial<SourceUrlCandidateReviewLayoutColumn>) {
    const nextColumns = columns.map((column, columnIndex) =>
      columnIndex === index ? { ...column, ...update } : column,
    );
    onChange({ ...layout, columns: nextColumns });
  }

  return (
    <details className="panel source-url-layout-card">
      <summary>
        <span>
          <strong>Table settings</strong>
          <small> Columns, order, and widths</small>
        </span>
      </summary>

      {error ? <p className="form-error">{error}</p> : null}
      <div className="source-url-layout-controls">
        {columns.map((column, index) => (
          <div className="source-url-layout-row" key={columnKey(column)}>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={isColumnVisible(column)}
                onChange={(event) =>
                  updateColumn(index, {
                    visible: event.target.checked,
                    table_column_visible: event.target.checked,
                  })
                }
              />
              <span>{columnLabel(column)}</span>
            </label>
            <div className="button-row">
              <button
                className="button secondary compact-button"
                type="button"
                aria-label={`Move ${columnLabel(column)} up`}
                title={`Move ${columnLabel(column)} up`}
                disabled={index === 0}
                onClick={() => onChange({ ...layout, columns: moveColumn(columns, index, -1) })}
              >
                ↑
              </button>
              <button
                className="button secondary compact-button"
                type="button"
                aria-label={`Move ${columnLabel(column)} down`}
                title={`Move ${columnLabel(column)} down`}
                disabled={index === columns.length - 1}
                onClick={() => onChange({ ...layout, columns: moveColumn(columns, index, 1) })}
              >
                ↓
              </button>
              <label className="source-url-width-field">
                <span>Width</span>
                <input
                  type="number"
                  min={MIN_COLUMN_WIDTH_PX}
                  max={MAX_COLUMN_WIDTH_PX}
                  step={1}
                  value={getColumnWidth(column)}
                  onChange={(event) =>
                    updateColumn(index, { width_px: Number(event.target.value) || DEFAULT_COLUMN_WIDTH_PX })
                  }
                />
              </label>
            </div>
          </div>
        ))}
      </div>
      <div className="button-row">
        <button className="button primary" type="button" disabled={isSaving} onClick={onSave}>
          {isSaving ? "Saving..." : "Save layout"}
        </button>
        <button className="button secondary" type="button" disabled={isSaving} onClick={onReset}>
          Reset layout
        </button>
      </div>
    </details>
  );
}
