import { EmptyState } from "../../components/layout/StateBlocks";
import type { CatalogProductSourceUrlSummary, SourceUrl } from "./catalogProductDetailTypes";
import { ProductSourceUrlLifecycleTable } from "./ProductSourceUrlLifecycleTable";
import { ProductSourceUrlStatusSummary } from "./ProductSourceUrlStatusSummary";

export function ProductSourceUrlHistoryPanel({
  sourceUrls,
  summary,
}: {
  sourceUrls: SourceUrl[];
  summary: CatalogProductSourceUrlSummary;
}) {
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Source URL lifecycle</p>
          <h3>Capture and fetch status</h3>
        </div>
        <span className="status-badge neutral">{summary.total_count ?? sourceUrls.length} URLs</span>
      </div>
      <ProductSourceUrlStatusSummary summary={summary} />
      {sourceUrls.length === 0 ? (
        <EmptyState
          title="No source URLs"
          message="This catalog product exists, but no source URL lifecycle rows have been recorded."
        />
      ) : (
        <ProductSourceUrlLifecycleTable sourceUrls={sourceUrls} />
      )}
    </section>
  );
}

