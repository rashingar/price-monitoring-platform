import type { PriceMonitoringSelectionResult } from "../../api/commerceTypes";
import { formatValue } from "./catalogFormatters";

export function SummaryText({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{formatValue(value)}</dd>
    </div>
  );
}

export function CatalogSelectionResultSummary({ result }: { result: PriceMonitoringSelectionResult }) {
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
