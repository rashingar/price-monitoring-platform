import { Fragment, type ReactNode } from "react";
import type {
  SourceUrlCandidate,
  SourceUrlCandidateReviewDecision,
  SourceUrlCandidateReviewLayout,
  SourceUrlCandidateReviewLayoutColumn,
} from "../../api/commerceTypes";
import {
  formatConfidence,
  formatDate,
  formatMoney,
  formatValue,
  normalizeLabel,
  statusClass,
} from "./sourceUrlCandidateFormatters";
import { candidateId, isInteractiveClick } from "./sourceUrlCandidateHelpers";
import {
  columnKey,
  columnLabel,
  getColumnWidth,
} from "./sourceUrlCandidateLayout";
import { SourceUrlCandidateReviewPanel } from "./SourceUrlCandidateReviewPanel";

interface SourceUrlCandidatesTableProps {
  candidates: SourceUrlCandidate[];
  tableColumns: SourceUrlCandidateReviewLayoutColumn[];
  selectedCandidateId: string | null;
  selectedCandidate: SourceUrlCandidate | null;
  layout: SourceUrlCandidateReviewLayout;
  isDetailLoading: boolean;
  pendingCandidateId: string | null;
  onToggleCandidateReview: (candidate: SourceUrlCandidate) => void;
  onReviewCandidate: (
    candidate: SourceUrlCandidate,
    decision: SourceUrlCandidateReviewDecision,
    reviewedUrl: string,
    notes: string,
  ) => void;
}

function getCandidateField(candidate: SourceUrlCandidate, key: string): unknown {
  if (key === "candidate_id") {
    return candidate.id;
  }

  return candidate[key];
}

function renderCandidateCell(candidate: SourceUrlCandidate, key: string): ReactNode {
  switch (key) {
    case "id":
    case "candidate_id":
      return formatValue(candidate.id);
    case "status":
    case "review_status":
      return (
        <span className={`status-badge ${statusClass(candidate.status)}`}>
          {normalizeLabel(candidate.status ?? null)}
        </span>
      );
    case "candidate_price":
    case "own_price":
      return formatMoney(getCandidateField(candidate, key));
    case "confidence_score":
    case "confidence":
      return formatConfidence(candidate.confidence_score);
    case "source_name":
      return formatValue(candidate.source_name);
    case "source_domain":
      return formatValue(candidate.source_domain);
    case "created_at":
    case "updated_at":
    case "reviewed_at":
      return formatDate(getCandidateField(candidate, key));
    case "candidate_url":
    case "canonical_url": {
      const url = getCandidateField(candidate, key);
      return typeof url === "string" && url.trim().length > 0 ? (
        <a href={url} target="_blank" rel="noreferrer">
          Open
        </a>
      ) : (
        "-"
      );
    }
    default:
      return formatValue(getCandidateField(candidate, key));
  }
}

export function SourceUrlCandidatesTable({
  candidates,
  tableColumns,
  selectedCandidateId,
  selectedCandidate,
  layout,
  isDetailLoading,
  pendingCandidateId,
  onToggleCandidateReview,
  onReviewCandidate,
}: SourceUrlCandidatesTableProps) {
  return (
    <div className="table-wrap source-url-candidates-table-wrap">
      <table>
        <colgroup>
          {tableColumns.map((column) => (
            <col key={columnKey(column)} style={{ width: `${getColumnWidth(column)}px` }} />
          ))}
        </colgroup>
        <thead>
          <tr>
            {tableColumns.map((column) => (
              <th key={columnKey(column)}>{columnLabel(column)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {candidates.map((candidate) => {
            const id = candidateId(candidate);
            const isSelected = selectedCandidateId === id;
            return (
              <Fragment key={id}>
                <tr
                  className={isSelected ? "selected-row" : undefined}
                  aria-expanded={isSelected}
                  onClick={(event) => {
                    if (!isInteractiveClick(event.target)) {
                      onToggleCandidateReview(candidate);
                    }
                  }}
                >
                  {tableColumns.map((column) => {
                    const key = columnKey(column);
                    return (
                      <td key={key} className="source-url-candidate-cell">
                        <span className="source-url-candidate-cell-content">
                          {renderCandidateCell(candidate, key)}
                        </span>
                      </td>
                    );
                  })}
                </tr>
                {isSelected ? (
                  <tr className="source-url-expanded-row">
                    <td colSpan={tableColumns.length}>
                      <SourceUrlCandidateReviewPanel
                        candidate={selectedCandidate}
                        layout={layout}
                        isLoading={isDetailLoading}
                        isPending={pendingCandidateId === id}
                        onReview={onReviewCandidate}
                      />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
