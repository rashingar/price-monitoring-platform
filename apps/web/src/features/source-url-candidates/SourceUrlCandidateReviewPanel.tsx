import { useEffect, useState } from "react";
import type {
  SourceUrlCandidate,
  SourceUrlCandidateReviewActionConfig,
  SourceUrlCandidateReviewDecision,
  SourceUrlCandidateReviewLayout,
} from "../../api/commerceTypes";
import { LoadingState } from "../../components/layout/StateBlocks";
import { FALLBACK_REVIEW_ACTIONS } from "./sourceUrlCandidateConstants";
import { normalizeLabel } from "./sourceUrlCandidateFormatters";
import { isRecord } from "./sourceUrlCandidateHelpers";
import { SkroutzNetworkDiagnosticPanel } from "./SkroutzNetworkDiagnosticPanel";
import { SourceUrlCandidateDebugPanel } from "./SourceUrlCandidateDebugPanel";

interface SourceUrlCandidateReviewPanelProps {
  candidate: SourceUrlCandidate | null;
  layout: SourceUrlCandidateReviewLayout;
  isLoading: boolean;
  isPending: boolean;
  onReview: (
    candidate: SourceUrlCandidate,
    decision: SourceUrlCandidateReviewDecision,
    reviewedUrl: string,
    notes: string,
  ) => void;
}

function getReviewActions(layout: SourceUrlCandidateReviewLayout, candidate: SourceUrlCandidate | null) {
  const candidateReviewPanel = isRecord(candidate?.review_panel) ? candidate?.review_panel : null;
  const candidateActions = Array.isArray(candidateReviewPanel?.review_actions)
    ? candidateReviewPanel.review_actions
    : [];
  const layoutActions = layout.review_panel?.review_actions ?? [];
  const actions = candidateActions.length > 0 ? candidateActions : layoutActions;
  return actions.length > 0 ? actions : FALLBACK_REVIEW_ACTIONS;
}

function getActionDecision(action: SourceUrlCandidateReviewActionConfig): SourceUrlCandidateReviewDecision {
  return (action.decision ?? "reject") as SourceUrlCandidateReviewDecision;
}

function getActionLabel(action: SourceUrlCandidateReviewActionConfig): string {
  return action.label ?? normalizeLabel(String(action.decision ?? "reject"));
}

function actionRequiresUrl(action: SourceUrlCandidateReviewActionConfig): boolean {
  return action.requires_url === true ||
    action.requires_reviewed_url === true ||
    action.decision === "replace_url";
}

function actionButtonClass(action: SourceUrlCandidateReviewActionConfig): string {
  const decision = action.decision;
  if (action.style === "danger" || decision === "reject") {
    return "button danger";
  }
  if (action.style === "primary" || decision === "accept") {
    return "button primary";
  }
  return "button secondary";
}

export function SourceUrlCandidateReviewPanel({
  candidate,
  layout,
  isLoading,
  isPending,
  onReview,
}: SourceUrlCandidateReviewPanelProps) {
  const [replacementUrl, setReplacementUrl] = useState("");
  const [isReplaceOpen, setIsReplaceOpen] = useState(false);
  const [isDebugOpen, setIsDebugOpen] = useState(false);

  useEffect(() => {
    setReplacementUrl("");
    setIsReplaceOpen(false);
    setIsDebugOpen(false);
  }, [candidate?.id, candidate?.notes]);

  if (!candidate) {
    return null;
  }

  const reviewActions = getReviewActions(layout, candidate);
  const acceptAction = reviewActions.find((action) => getActionDecision(action) === "accept");
  const rejectAction = reviewActions.find((action) => getActionDecision(action) === "reject");
  const replaceAction = reviewActions.find((action) => getActionDecision(action) === "replace_url");
  const reviewNotes = typeof candidate.notes === "string" ? candidate.notes : "";

  return (
    <section
      className="source-url-inline-review-panel"
      role="region"
      aria-label={`Find Source candidate ${candidate.id} review`}
    >
      {isLoading ? <LoadingState label="Loading candidate details..." /> : null}

      <div className="source-url-inline-review-grid">
        <section className="candidate-detail-card source-url-review-decision-card">
          <div className="button-row source-url-review-actions">
            {candidate.candidate_url ? (
              <a
                className="button secondary"
                href={candidate.candidate_url}
                target="_blank"
                rel="noreferrer noopener"
              >
                Open candidate URL
              </a>
            ) : null}
            {acceptAction ? (
              <button
                className={actionButtonClass(acceptAction)}
                type="button"
                disabled={isPending}
                onClick={() => onReview(candidate, "accept", "", reviewNotes)}
              >
                {isPending ? "Submitting..." : getActionLabel(acceptAction)}
              </button>
            ) : null}
            {rejectAction ? (
              <button
                className={actionButtonClass(rejectAction)}
                type="button"
                disabled={isPending}
                onClick={() => onReview(candidate, "reject", "", reviewNotes)}
              >
                {isPending ? "Submitting..." : getActionLabel(rejectAction)}
              </button>
            ) : null}
            {replaceAction ? (
              <button
                className="button secondary"
                type="button"
                aria-expanded={isReplaceOpen}
                onClick={() => setIsReplaceOpen((current) => !current)}
              >
                {getActionLabel(replaceAction)}
              </button>
            ) : null}
            <button
              className="button secondary"
              type="button"
              aria-expanded={isDebugOpen}
              onClick={() => setIsDebugOpen((current) => !current)}
            >
              Debug
            </button>
          </div>
          {isReplaceOpen && replaceAction ? (
            <div className="source-url-replace-inline-row">
              <label className="inline-field wide">
                <span>Replacement URL</span>
                <input
                  type="url"
                  value={replacementUrl}
                  onChange={(event) => setReplacementUrl(event.target.value)}
                  placeholder="https://example.com/product"
                />
              </label>
              <button
                className="button secondary"
                type="button"
                disabled={isPending || (actionRequiresUrl(replaceAction) && replacementUrl.trim().length === 0)}
                onClick={() => onReview(candidate, "replace_url", replacementUrl, reviewNotes)}
              >
                {isPending ? "Submitting..." : "Submit replacement"}
              </button>
            </div>
          ) : null}
          {isDebugOpen ? <SourceUrlCandidateDebugPanel candidate={candidate} /> : null}
        </section>
        <SkroutzNetworkDiagnosticPanel candidate={candidate} />
      </div>
    </section>
  );
}
