import { useMemo } from "react";
import type { PriceMonitoringReviewResponse } from "../../../api/commerceTypes";
import {
  getReviewActionErrors,
  getReviewActionPayload,
} from "../reviewActions";
import type { RowActionState } from "../types";

export function usePriceMonitoringReview({
  review,
  rowActions,
}: {
  review: PriceMonitoringReviewResponse | null;
  rowActions: Record<string, RowActionState>;
}) {
  const actionRows = useMemo(() => review?.items ?? [], [review?.items]);
  const actionErrors = useMemo(
    () => getReviewActionErrors(actionRows, rowActions),
    [actionRows, rowActions],
  );
  const actionPayload = useMemo(
    () => getReviewActionPayload(actionRows, rowActions),
    [actionRows, rowActions],
  );

  return {
    actionRows,
    actionErrors,
    actionPayload,
  };
}
