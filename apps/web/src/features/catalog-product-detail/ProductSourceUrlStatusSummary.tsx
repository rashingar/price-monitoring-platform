import type { CatalogProductSourceUrlSummary } from "./catalogProductDetailTypes";
import { recordEntries, statusTone } from "./catalogProductDetailFormatters";

export function ProductSourceUrlStatusSummary({
  summary,
}: {
  summary: CatalogProductSourceUrlSummary;
}) {
  const statusEntries = recordEntries(summary.by_status);
  const sourceEntries = recordEntries(summary.by_source);
  const typeEntries = recordEntries(summary.by_type);

  return (
    <div className="catalog-product-source-summary">
      <SummaryGroup title="Statuses" entries={statusEntries} />
      <SummaryGroup title="Sources" entries={sourceEntries} />
      <SummaryGroup title="Types" entries={typeEntries} />
    </div>
  );
}

function SummaryGroup({ title, entries }: { title: string; entries: Array<[string, number]> }) {
  return (
    <div>
      <p className="eyebrow">{title}</p>
      <div className="catalog-product-source-summary-badges">
        {entries.length > 0 ? (
          entries.map(([key, count]) => (
            <span className={`status-badge ${statusTone(key)}`} key={key}>
              {key} {count}
            </span>
          ))
        ) : (
          <span className="status-badge neutral">None</span>
        )}
      </div>
    </div>
  );
}

