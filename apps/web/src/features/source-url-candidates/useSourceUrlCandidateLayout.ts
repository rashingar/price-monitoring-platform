import { useState } from "react";
import type { SourceUrlCandidateReviewLayout } from "../../api/commerceTypes";
import {
  loadLocalSourceUrlCandidateReviewLayout,
  resetLocalSourceUrlCandidateReviewLayout,
  saveLocalSourceUrlCandidateReviewLayout,
} from "./sourceUrlCandidateLayout";

export function useSourceUrlCandidateLayout(onNotice: (notice: string) => void) {
  const [layout, setLayout] = useState<SourceUrlCandidateReviewLayout>(() => loadLocalSourceUrlCandidateReviewLayout());
  const [isLayoutSaving, setIsLayoutSaving] = useState(false);
  const [layoutError, setLayoutError] = useState<string | null>(null);

  const saveLayout = async () => {
    setIsLayoutSaving(true);
    setLayoutError(null);
    try {
      const nextLayout = saveLocalSourceUrlCandidateReviewLayout(layout);
      setLayout(nextLayout);
      onNotice("Review table layout saved.");
    } catch (saveError) {
      setLayoutError(saveError instanceof Error ? saveError.message : "Review table layout could not be saved locally.");
    } finally {
      setIsLayoutSaving(false);
    }
  };

  const resetLayout = async () => {
    setIsLayoutSaving(true);
    setLayoutError(null);
    try {
      const nextLayout = resetLocalSourceUrlCandidateReviewLayout();
      setLayout(nextLayout);
      onNotice("Review table layout reset.");
    } catch (resetError) {
      setLayoutError(resetError instanceof Error ? resetError.message : "Review table layout could not be reset locally.");
    } finally {
      setIsLayoutSaving(false);
    }
  };

  return {
    layout,
    setLayout,
    isLayoutSaving,
    layoutError,
    saveLayout,
    resetLayout,
  };
}
