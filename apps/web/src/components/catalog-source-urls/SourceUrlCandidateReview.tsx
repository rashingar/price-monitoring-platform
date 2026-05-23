import type {
  SourceUrlCandidate,
  SourceUrlCandidateReviewDecision,
} from "../../api/commerceTypes";
import { candidateKey, formatValue } from "./sourceUrlDrawerUtils";

function CandidateSummary({ candidate }: { candidate: SourceUrlCandidate }) {
  return (
    <div className="source-url-drawer-candidate">
      <div>
        <strong>{formatValue(candidate.candidate_title ?? candidate.product_name)}</strong>
        <p className="muted">
          {formatValue(candidate.source_name)} / {formatValue(candidate.source_domain)}
          {" - "}
          confidence {formatValue(candidate.confidence_score)}
        </p>
      </div>
      {candidate.candidate_url ? (
        <a href={candidate.candidate_url} target="_blank" rel="noreferrer noopener">
          {candidate.candidate_url}
        </a>
      ) : null}
    </div>
  );
}

export function SourceUrlCandidateReview({
  candidates,
  expanded,
  pendingCandidateId,
  onToggleExpanded,
  onReview,
}: {
  candidates: SourceUrlCandidate[];
  expanded: boolean;
  pendingCandidateId: string | null;
  onToggleExpanded: () => void;
  onReview: (candidate: SourceUrlCandidate, decision: SourceUrlCandidateReviewDecision) => void;
}) {
  if (candidates.length === 0) {
    return null;
  }

  const visibleCandidates = expanded ? candidates : candidates.slice(0, 1);
  return (
    <section className="source-url-discovery-block" aria-label="Discovery candidate review">
      <div className="source-url-discovery-block-header">
        <strong>Candidate review</strong>
        {candidates.length > 1 ? (
          <button className="button secondary compact-button" type="button" onClick={onToggleExpanded}>
            {expanded ? "Show top only" : `Show ${candidates.length - 1} more`}
          </button>
        ) : null}
      </div>
      <div className="source-url-drawer-candidates">
        {visibleCandidates.map((candidate) => {
          const id = candidateKey(candidate);
          const isPending = pendingCandidateId === id;
          return (
            <article key={id} className="source-url-drawer-candidate-card">
              <CandidateSummary candidate={candidate} />
              <div className="button-row">
                <button
                  className="button primary compact-button"
                  type="button"
                  disabled={isPending}
                  onClick={() => onReview(candidate, "accept")}
                >
                  {isPending ? "Submitting..." : "Accept"}
                </button>
                <button
                  className="button danger compact-button"
                  type="button"
                  disabled={isPending}
                  onClick={() => onReview(candidate, "reject")}
                >
                  {isPending ? "Submitting..." : "Reject"}
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
