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
        <thead>
          <tr>
            <th>run_id</th>
            <th>source</th>
            <th>mode</th>
            <th>status</th>
            <th>selected_count</th>
            <th>candidate_count</th>
            <th>task progress</th>
            <th>matched_count</th>
            <th>needs_review_count</th>
            <th>not_found_count</th>
            <th>error_count</th>
            <th>created</th>
            <th>started</th>
            <th>completed</th>
            <th>actions</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run, index) => {
            const runId = getRunId(run);
            const isRefreshing = refreshingRunId === runId;
            return (
              <tr key={`${runId}-${index}`}>
                <td className="source-url-agent-run-id">{runId}</td>
                <td>{formatValue(run.source)}</td>
                <td>{formatValue(run.mode)}</td>
                <td>
                  <span className={`status-badge ${statusClass(run.status)}`}>
                    {normalizeLabel(run.status)}
                  </span>
                </td>
                <td>{formatNumber(getCounter(run, "selected_count"))}</td>
                <td>{formatNumber(getCounter(run, "candidate_count"))}</td>
                <td>{formatTaskProgress(run)}</td>
                <td>{formatNumber(getCounter(run, "matched_count"))}</td>
                <td>{formatNumber(getCounter(run, "needs_review_count"))}</td>
                <td>{formatNumber(getCounter(run, "not_found_count"))}</td>
                <td>{formatNumber(getCounter(run, "error_count"))}</td>
                <td>{formatDate(run.created_at)}</td>
                <td>{formatDate(run.started_at)}</td>
                <td>{formatDate(run.completed_at)}</td>
                <td>
                  <div className="source-url-agent-actions">
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
