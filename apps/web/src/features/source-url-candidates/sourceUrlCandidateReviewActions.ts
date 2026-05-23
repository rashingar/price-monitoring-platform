import { commerceClient } from "../../api/commerceClient";
import type {
  SourceUrlCandidate,
  SourceUrlCandidateReviewBody,
  SourceUrlCandidateReviewDecision,
} from "../../api/commerceTypes";

export async function submitSourceUrlCandidateReview({
  candidateId,
  decision,
  reviewedUrl,
  reviewNotes,
  reviewedBy = "operator",
  signal,
}: {
  candidateId: string | number;
  decision: SourceUrlCandidateReviewDecision;
  reviewedUrl?: string | null;
  reviewNotes?: string | null;
  reviewedBy?: string | null;
  signal?: AbortSignal;
}): Promise<SourceUrlCandidate> {
  const body: SourceUrlCandidateReviewBody = {
    decision,
    reviewed_url: decision === "replace_url" ? reviewedUrl?.trim() || null : null,
    review_notes: reviewNotes?.trim() || null,
    reviewed_by: reviewedBy,
  };
  return commerceClient.reviewSourceUrlCandidate(candidateId, body, signal);
}
