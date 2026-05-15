import { Link } from "react-router-dom";
import { EmptyState, ErrorState, LoadingState } from "../../components/layout/StateBlocks";
import type {
  ProductSourceUrlCandidateHistoryResponse,
  ProductSourceUrlCandidateRunGroup,
  SourceUrlCandidate,
} from "./catalogProductDetailTypes";
import { formatDateTime, formatDetailValue, statusTone } from "./catalogProductDetailFormatters";

const CANDIDATE_COUNT_STATUSES = [
  "accepted",
  "needs_review",
  "pending",
  "rejected",
  "not_found",
  "error",
] as const;

export function ProductSourceUrlCandidateHistoryPanel({
  data,
  isLoading,
  error,
  onRetry,
}: {
  data: ProductSourceUrlCandidateHistoryResponse | null;
  isLoading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  const groups = data?.items ?? [];
  const totalCandidates = data?.total_candidates ?? 0;

  return (
    <section className="panel catalog-product-candidate-history-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Source URL Agent</p>
          <h3>Candidate history</h3>
        </div>
        <div className="catalog-product-candidate-heading-actions">
          <span className="status-badge neutral">Read-only</span>
          <span className="status-badge neutral">{totalCandidates} candidates</span>
        </div>
      </div>

      {isLoading ? <LoadingState label="Loading Source URL Agent candidate history..." /> : null}
      {error ? <ErrorState message={error} onRetry={onRetry} /> : null}
      {!isLoading && !error && groups.length === 0 ? (
        <EmptyState
          title="No Source URL Agent candidates"
          message="This catalog product exists, but no Source URL Agent candidates have been recorded."
        />
      ) : null}
      {!isLoading && !error && groups.length > 0 ? (
        <div className="catalog-product-candidate-run-list">
          {groups.map((group, index) => (
            <CandidateRunGroup key={String(group.run_id ?? index)} group={group} defaultOpen={index === 0} />
          ))}
        </div>
      ) : null}
    </section>
  );
}

function CandidateRunGroup({
  group,
  defaultOpen,
}: {
  group: ProductSourceUrlCandidateRunGroup;
  defaultOpen: boolean;
}) {
  const runId = group.run_id ?? group.run.run_id ?? "";
  const sourceName = group.run.source_name ?? group.run.source;

  return (
    <details className="catalog-product-candidate-run" open={defaultOpen}>
      <summary>
        <div className="catalog-product-candidate-run-summary">
          <div>
            <strong>{formatDetailValue(runId)}</strong>
            <span className="muted table-cell-subtext">
              {formatDetailValue(sourceName)} / {formatDetailValue(group.run.mode)}
            </span>
          </div>
          <div className="catalog-product-candidate-run-meta">
            <span className={`status-badge ${statusTone(group.run.status)}`}>
              {formatDetailValue(group.run.status)}
            </span>
            <span className="status-badge neutral">{group.candidates.length} rows</span>
          </div>
        </div>
      </summary>

      <div className="catalog-product-candidate-run-body">
        <div className="catalog-product-candidate-run-details">
          <span>Created {formatDateTime(group.run.created_at)}</span>
          <span>Started {formatDateTime(group.run.started_at)}</span>
          <span>Completed {formatDateTime(group.run.completed_at)}</span>
          <Link to={`/find-source/candidates?run_id=${encodeURIComponent(String(runId))}`}>
            View run candidates
          </Link>
        </div>
        <div className="catalog-product-candidate-counts">
          {CANDIDATE_COUNT_STATUSES.map((status) => (
            <span key={status} className={`status-badge ${statusTone(status)}`}>
              {status} {group.counts[status] ?? 0}
            </span>
          ))}
        </div>
        <CandidateTable candidates={group.candidates} />
      </div>
    </details>
  );
}

function CandidateTable({ candidates }: { candidates: SourceUrlCandidate[] }) {
  return (
    <div className="table-wrap catalog-product-candidate-table-wrap">
      <table>
        <thead>
          <tr>
            <th>Status</th>
            <th>Confidence</th>
            <th>Source</th>
            <th>Candidate title</th>
            <th>Candidate price</th>
            <th>Own price</th>
            <th>Match method</th>
            <th>Candidate URL</th>
            <th>Reviewed</th>
            <th>Notes</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((candidate) => (
            <tr key={String(candidate.id)}>
              <td>
                <span className={`status-badge ${statusTone(candidate.status)}`}>
                  {formatDetailValue(candidate.status)}
                </span>
              </td>
              <td>{formatConfidence(candidate.confidence_score)}</td>
              <td>
                <strong>{formatDetailValue(candidate.source_name)}</strong>
                <span className="muted table-cell-subtext">
                  {formatDetailValue(candidate.source_domain)}
                </span>
              </td>
              <td className="candidate-title-cell">{formatDetailValue(candidate.candidate_title)}</td>
              <td>{formatMoneyValue(candidate.candidate_price)}</td>
              <td>{formatMoneyValue(candidate.own_price)}</td>
              <td>{formatDetailValue(candidate.match_method)}</td>
              <td className="url-cell">
                {candidate.candidate_url ? (
                  <a href={candidate.candidate_url} target="_blank" rel="noreferrer noopener">
                    Open candidate
                  </a>
                ) : (
                  "-"
                )}
                <span className="muted table-cell-subtext">
                  {formatDetailValue(candidate.canonical_url)}
                </span>
              </td>
              <td>
                {formatDetailValue(candidate.reviewed_by)}
                <span className="muted table-cell-subtext">
                  {formatDateTime(candidate.reviewed_at)}
                </span>
              </td>
              <td className="notes-cell">{formatDetailValue(candidate.notes)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatConfidence(value: string | number | null | undefined): string {
  const numberValue = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  if (!Number.isFinite(numberValue)) {
    return "-";
  }
  return `${Math.round(numberValue * 1000) / 10}%`;
}

function formatMoneyValue(value: string | number | null | undefined): string {
  const numberValue = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  if (!Number.isFinite(numberValue)) {
    return "-";
  }
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 2,
  }).format(numberValue);
}
