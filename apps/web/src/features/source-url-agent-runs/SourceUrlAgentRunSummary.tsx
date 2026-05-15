import type { SourceUrlAgentRun } from "../../api/commerceTypes";
import { activeTaskCount, formatNumber } from "./sourceUrlAgentRunFormatters";
import type { SourceUrlAgentRunTotals } from "./sourceUrlAgentRunTypes";

function SummaryItem({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{formatNumber(value)}</dd>
    </div>
  );
}

type SourceUrlAgentRunSummaryProps = {
  runs: SourceUrlAgentRun[];
  totals: SourceUrlAgentRunTotals;
};

export function SourceUrlAgentRunSummary({ runs, totals }: SourceUrlAgentRunSummaryProps) {
  const needsReviewCount = Number(totals.needs_review_count);
  const errorCount = Number(totals.error_count);
  const activeTasks = activeTaskCount(runs);

  return (
    <dl className="summary-grid source-url-agent-summary-grid">
      <SummaryItem label="Runs" value={runs.length} />
      <SummaryItem label="Candidates" value={totals.candidate_count} />
      {needsReviewCount > 0 ? <SummaryItem label="Needs review" value={needsReviewCount} /> : null}
      {errorCount > 0 ? <SummaryItem label="Errors" value={errorCount} /> : null}
      {activeTasks > 0 ? <SummaryItem label="Active tasks" value={activeTasks} /> : null}
    </dl>
  );
}
