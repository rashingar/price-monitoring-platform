import { useState } from "react";
import {
  commerceClient,
  getCommerceApiErrorMessage,
} from "../../api/commerceClient";
import type {
  SourceUrlCandidate,
  SourceUrlCandidateReviewDecision,
} from "../../api/commerceTypes";
import { submitSourceUrlCandidateReview } from "./sourceUrlCandidateReviewActions";
import { normalizeLabel } from "./sourceUrlCandidateFormatters";
import { candidateId } from "./sourceUrlCandidateHelpers";

interface UseSourceUrlCandidateReviewOptions {
  updateCandidateInState: (candidate: SourceUrlCandidate) => void;
  setNotice: (notice: string | null) => void;
}

export function useSourceUrlCandidateReview({
  updateCandidateInState,
  setNotice,
}: UseSourceUrlCandidateReviewOptions) {
  const [pendingCandidateId, setPendingCandidateId] = useState<string | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<SourceUrlCandidate | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);

  const updateSelectedCandidate = (updated: SourceUrlCandidate) => {
    setSelectedCandidate((current) =>
      current && candidateId(current) === candidateId(updated) ? { ...current, ...updated } : current,
    );
  };

  const toggleCandidateReview = async (candidate: SourceUrlCandidate) => {
    const id = candidateId(candidate);
    if (selectedCandidateId === id) {
      setSelectedCandidateId(null);
      setSelectedCandidate(null);
      setIsDetailLoading(false);
      return;
    }

    setSelectedCandidateId(id);
    setSelectedCandidate(candidate);
    setIsDetailLoading(true);
    setNotice(null);
    try {
      const detail = await commerceClient.getSourceUrlCandidate(candidate.id);
      setSelectedCandidate((current) =>
        current && candidateId(current) === id ? { ...current, ...detail } : current,
      );
    } catch (detailError) {
      setNotice(getCommerceApiErrorMessage(detailError));
    } finally {
      setIsDetailLoading(false);
    }
  };

  const reviewCandidate = async (
    candidate: SourceUrlCandidate,
    decision: SourceUrlCandidateReviewDecision,
    reviewedUrl: string,
    reviewNotes: string,
  ) => {
    const id = candidateId(candidate);
    if (decision === "replace_url" && reviewedUrl.trim().length === 0) {
      setNotice("Enter a corrected URL before replacing.");
      return;
    }

    setPendingCandidateId(id);
    setNotice(null);
    try {
      const updated = await submitSourceUrlCandidateReview({
        candidateId: candidate.id,
        decision,
        reviewedUrl,
        reviewNotes,
      });
      updateCandidateInState(updated);
      updateSelectedCandidate(updated);
      setNotice(`Candidate ${id} marked ${normalizeLabel(updated.status)}.`);
    } catch (reviewError) {
      setNotice(getCommerceApiErrorMessage(reviewError));
    } finally {
      setPendingCandidateId(null);
    }
  };

  return {
    pendingCandidateId,
    selectedCandidateId,
    selectedCandidate,
    isDetailLoading,
    toggleCandidateReview,
    reviewCandidate,
  };
}
