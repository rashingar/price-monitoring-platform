import { EmptyState } from "../../components/layout/StateBlocks";
import type { CatalogProductSourceUrlSummary, SourceUrl } from "./catalogProductDetailTypes";
import { ProductSourceUrlLifecycleTable } from "./ProductSourceUrlLifecycleTable";
import { ProductSourceUrlStatusSummary } from "./ProductSourceUrlStatusSummary";

export function ProductSourceUrlHistoryPanel({
  sourceUrls,
  summary,
  pendingSourceUrlId,
  pendingActionLabel,
  onValidate,
  onUpdateStatus,
  onSaveNote,
}: {
  sourceUrls: SourceUrl[];
  summary: CatalogProductSourceUrlSummary;
  pendingSourceUrlId: string | number | null;
  pendingActionLabel: string | null;
  onValidate: (sourceUrl: SourceUrl) => Promise<void>;
  onUpdateStatus: (sourceUrl: SourceUrl, status: string, label: string) => Promise<void>;
  onSaveNote: (sourceUrl: SourceUrl, notes: string | null) => Promise<void>;
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
        <ProductSourceUrlLifecycleTable
          sourceUrls={sourceUrls}
          pendingSourceUrlId={pendingSourceUrlId}
          pendingActionLabel={pendingActionLabel}
          onValidate={onValidate}
          onUpdateStatus={onUpdateStatus}
          onSaveNote={onSaveNote}
        />
      )}
    </section>
  );
}
