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
  return (
    <dl className="summary-grid source-url-agent-summary-grid">
      <SummaryItem label="Runs" value={runs.length} />
      <SummaryItem label="Selected" value={totals.selected_count} />
      <SummaryItem label="Candidates" value={totals.candidate_count} />
      <SummaryItem label="Needs review" value={totals.needs_review_count} />
      <SummaryItem label="Errors" value={totals.error_count} />
      <SummaryItem label="Active tasks" value={activeTaskCount(runs)} />
    </dl>
  );
}
