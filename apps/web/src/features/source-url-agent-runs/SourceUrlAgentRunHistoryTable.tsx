import { Link } from "react-router-dom";
import type { SourceUrlAgentRun } from "../../api/commerceTypes";
import {
  formatDate,
  formatNumber,
  formatTaskProgress,
  formatValue,
  getCounter,
  getRunId,
  normalizeLabel,
  statusClass,
} from "./sourceUrlAgentRunFormatters";

type SourceUrlAgentRunHistoryTableProps = {
  runs: SourceUrlAgentRun[];
  refreshingRunId: string | null;
  onRefreshRun: (run: SourceUrlAgentRun) => void;
  onOpenArtifacts: (run: SourceUrlAgentRun) => void;
};

export function SourceUrlAgentRunHistoryTable({
  runs,
  refreshingRunId,
  onRefreshRun,
  onOpenArtifacts,
}: SourceUrlAgentRunHistoryTableProps) {
  if (runs.length === 0) {
    return null;
  }

  return (
    <div className="table-wrap source-url-agent-runs-table-wrap">
      <table>
        <colgroup>
          <col className="source-url-run-column" />
          <col className="source-url-state-column" />
          <col className="source-url-counts-column" />
          <col className="source-url-activity-column" />
          <col className="source-url-actions-column" />
        </colgroup>
        <thead>
          <tr>
            <th>Run</th>
            <th>State</th>
            <th>Counts</th>
            <th>Activity</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run, index) => {
            const runId = getRunId(run);
            const isRefreshing = refreshingRunId === runId;
            return (
              <tr key={`${runId}-${index}`}>
                <td>
                  <div className="source-url-run-cell">
                    <span className="source-url-agent-run-id" title={runId}>
                      {runId}
                    </span>
                    <span className="muted">
                      {formatValue(run.source)} / {formatValue(run.mode)}
                    </span>
                  </div>
                </td>
                <td>
                  <div className="source-url-state-cell">
                    <span className={`status-badge ${statusClass(run.status)}`}>
                      {normalizeLabel(run.status)}
                    </span>
                    <span className="muted">Tasks {formatTaskProgress(run)}</span>
                  </div>
                </td>
                <td>
                  <dl className="source-url-run-counts">
                    <div>
                      <dt>Selected</dt>
                      <dd>{formatNumber(getCounter(run, "selected_count"))}</dd>
                    </div>
                    <div>
                      <dt>Candidates</dt>
                      <dd>{formatNumber(getCounter(run, "candidate_count"))}</dd>
                    </div>
                    <div>
                      <dt>Matched</dt>
                      <dd>{formatNumber(getCounter(run, "matched_count"))}</dd>
                    </div>
                    <div>
                      <dt>Review</dt>
                      <dd>{formatNumber(getCounter(run, "needs_review_count"))}</dd>
                    </div>
                    <div>
                      <dt>Missing</dt>
                      <dd>{formatNumber(getCounter(run, "not_found_count"))}</dd>
                    </div>
                    <div>
                      <dt>Errors</dt>
                      <dd>{formatNumber(getCounter(run, "error_count"))}</dd>
                    </div>
                  </dl>
                </td>
                <td>
                  <dl className="source-url-run-activity">
                    <div>
                      <dt>Created</dt>
                      <dd>{formatDate(run.created_at)}</dd>
                    </div>
                    <div>
                      <dt>Started</dt>
                      <dd>{formatDate(run.started_at)}</dd>
                    </div>
                    <div>
                      <dt>Completed</dt>
                      <dd>{formatDate(run.completed_at)}</dd>
                    </div>
                  </dl>
                </td>
                <td>
                  <div className="source-url-agent-actions source-url-agent-run-actions">
                    <button
                      className="button secondary compact-button"
                      type="button"
                      disabled={isRefreshing || runId === "-"}
                      onClick={() => onRefreshRun(run)}
                    >
                      {isRefreshing ? "Refreshing..." : "Refresh"}
                    </button>
                    <Link
                      className="button secondary compact-button"
                      to={`/find-source/candidates?run_id=${encodeURIComponent(runId)}`}
                    >
                      Review candidates
                    </Link>
                    <button
                      className="button secondary compact-button"
                      type="button"
                      disabled={runId === "-"}
                      onClick={() => onOpenArtifacts(run)}
                    >
                      Open artifacts
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
