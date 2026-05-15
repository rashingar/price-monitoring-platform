import { Link } from "react-router-dom";
import type { PriceMonitoringSelectionResult, SourceUrlAgentRun } from "../../api/commerceTypes";
import { ErrorState } from "../../components/layout/StateBlocks";
import {
  getSourceUrlAgentRunCount,
  getSourceUrlAgentTaskProgress,
} from "./sourceUrlDiscovery";
import { CatalogSelectionResultSummary, SummaryText } from "./CatalogSelectionResultSummary";

export function CatalogActionsPanel({
  filteredTotal,
  selectedCount,
  previewResult,
  previewError,
  isPreviewLoading,
  runResult,
  runError,
  isRunLoading,
  discoveryRun,
  discoveryRunError,
  discoveryRunId,
  discoveryReviewLink,
  isDiscoveryLaunching,
  isDiscoveryPolling,
  missingSourceUrlModelCount,
  isCatalogLocked,
  onPreview,
  onCreateRun,
  onFindMore,
}: {
  filteredTotal: number;
  selectedCount: number;
  previewResult: PriceMonitoringSelectionResult | null;
  previewError: string | null;
  isPreviewLoading: boolean;
  runResult: PriceMonitoringSelectionResult | null;
  runError: string | null;
  isRunLoading: boolean;
  discoveryRun: SourceUrlAgentRun | null;
  discoveryRunError: string | null;
  discoveryRunId: string | null;
  discoveryReviewLink: string;
  isDiscoveryLaunching: boolean;
  isDiscoveryPolling: boolean;
  missingSourceUrlModelCount: number;
  isCatalogLocked: boolean;
  onPreview: () => void;
  onCreateRun: () => void;
  onFindMore: () => void;
}) {
  return (
    <>
      <div className="toolbar">
        <p className="muted">
          {filteredTotal.toLocaleString()} matching products.
          {selectedCount > 0 ? ` ${selectedCount} selected.` : " No products selected."}
          {" "}Selection clears when filters change.
        </p>
        <div className="button-row">
          <button
            className="button secondary"
            type="button"
            onClick={onPreview}
            disabled={isPreviewLoading || isRunLoading || isCatalogLocked}
          >
            {isPreviewLoading ? "Previewing..." : "Preview"}
          </button>
          <button
            className="button primary"
            type="button"
            onClick={onCreateRun}
            disabled={isRunLoading || isPreviewLoading || isCatalogLocked}
          >
            {isRunLoading ? "Creating..." : "Create run"}
          </button>
          <button
            className="button secondary"
            type="button"
            onClick={onFindMore}
            disabled={
              isRunLoading ||
              isPreviewLoading ||
              isDiscoveryLaunching ||
              isDiscoveryPolling ||
              isCatalogLocked
            }
            title={
              previewResult
                ? `Find source URLs for ${missingSourceUrlModelCount.toLocaleString()} skipped products missing active source URLs.`
                : "Preview the selection, then find source URLs for skipped products missing active source URLs."
            }
          >
            {isDiscoveryLaunching || isDiscoveryPolling ? "Finding..." : "Find more"}
          </button>
        </div>
      </div>

      {previewError ? <ErrorState message={previewError} /> : null}
      {previewResult ? (
        <div className="state-block">
          <strong>Selection preview</strong>
          <CatalogSelectionResultSummary result={previewResult} />
        </div>
      ) : null}

      {runError ? <ErrorState message={runError} /> : null}
      {runResult ? (
        <div className="state-block">
          <strong>Price monitoring run</strong>
          <CatalogSelectionResultSummary result={runResult} />
        </div>
      ) : null}

      {discoveryRunError ? <ErrorState message={discoveryRunError} /> : null}
      {discoveryRun ? (
        <div className="state-block">
          <strong>Find more</strong>
          <dl className="summary-grid">
            <SummaryText label="Run ID" value={discoveryRunId} />
            <SummaryText label="Status" value={discoveryRun.status} />
            <SummaryText label="Selected" value={getSourceUrlAgentRunCount(discoveryRun, "selected_count")} />
            <SummaryText label="Candidates" value={getSourceUrlAgentRunCount(discoveryRun, "candidate_count")} />
            <SummaryText label="Needs review" value={getSourceUrlAgentRunCount(discoveryRun, "needs_review_count")} />
            <SummaryText label="Task progress" value={getSourceUrlAgentTaskProgress(discoveryRun)} />
          </dl>
          <p className="button-row">
            <Link className="button secondary" to="/find-source/runs">
              View runs
            </Link>
            <Link className="button secondary" to={discoveryReviewLink}>
              Review candidates
            </Link>
          </p>
        </div>
      ) : null}
    </>
  );
}
