import type {
  PriceMonitoringAction,
  PriceMonitoringReviewAction,
  PriceMonitoringReviewItem,
} from "../../api/commerceTypes";
import type { RowActionState } from "./types";

export function isPriceMonitoringAction(value: unknown): value is PriceMonitoringAction {
  return value === "match_price" || value === "undercut" || value === "ignore";
}

export function getActionState(
  row: PriceMonitoringReviewItem,
  actionState: Record<string, RowActionState>,
): RowActionState {
  return (
    actionState[row.model] ?? {
      selected_action: isPriceMonitoringAction(row.selected_action) ? row.selected_action : "",
      undercut_amount:
        typeof row.undercut_amount === "number" && Number.isFinite(row.undercut_amount)
          ? String(row.undercut_amount)
          : "",
      reason: "",
    }
  );
}

export function computeTargetPrice(row: PriceMonitoringReviewItem, state: RowActionState): number | null {
  if (state.selected_action === "match_price") {
    return typeof row.competitor_price === "number" ? row.competitor_price : null;
  }

  if (state.selected_action === "undercut") {
    const undercutAmount = Number(state.undercut_amount);
    return typeof row.competitor_price === "number" &&
      Number.isFinite(row.competitor_price) &&
      Number.isFinite(undercutAmount)
      ? row.competitor_price - undercutAmount
      : null;
  }

  return typeof row.target_price === "number" ? row.target_price : null;
}

export function getActionError(row: PriceMonitoringReviewItem, state: RowActionState): string | null {
  if (state.selected_action === "") {
    return null;
  }

  if (state.selected_action === "ignore") {
    return null;
  }

  if (typeof row.competitor_price !== "number" || !Number.isFinite(row.competitor_price)) {
    return "Competitor price is required.";
  }

  if (state.selected_action === "undercut") {
    const undercutAmount = Number(state.undercut_amount);
    if (!Number.isFinite(undercutAmount) || undercutAmount <= 0) {
      return "Undercut amount must be greater than 0.";
    }
  }

  return null;
}

export function getRecommendedRowActions(
  items: PriceMonitoringReviewItem[],
): Record<string, RowActionState> {
  return items.reduce<Record<string, RowActionState>>((nextActions, item) => {
    const recommendedAction = isPriceMonitoringAction(item.recommended_action)
      ? item.recommended_action
      : "";
    const isNotExportable = item.status === "not_exportable";
    nextActions[item.model] =
      recommendedAction && (!isNotExportable || recommendedAction === "ignore")
        ? {
            selected_action: recommendedAction,
            undercut_amount:
              recommendedAction === "undercut" &&
              typeof item.undercut_amount === "number" &&
              Number.isFinite(item.undercut_amount)
                ? String(item.undercut_amount)
                : "",
            reason: recommendedAction === "ignore" ? "manual ignore from price review" : "",
          }
        : {
            selected_action: "",
            undercut_amount: "",
            reason: "",
          };
    return nextActions;
  }, {});
}

export function getReviewActionErrors(
  items: PriceMonitoringReviewItem[],
  rowActions: Record<string, RowActionState>,
): string[] {
  return items
    .map((row) => {
      const state = getActionState(row, rowActions);
      const error = getActionError(row, state);
      return error ? `${row.model}: ${error}` : null;
    })
    .filter((error): error is string => error !== null);
}

export function getReviewActionPayload(
  items: PriceMonitoringReviewItem[],
  rowActions: Record<string, RowActionState>,
): PriceMonitoringReviewAction[] {
  return items
    .map((row) => {
      const state = getActionState(row, rowActions);
      if (!state.selected_action) {
        return null;
      }

      const action: PriceMonitoringReviewAction = {
        model: row.model,
        selected_action: state.selected_action,
      };

      if (state.selected_action === "undercut") {
        action.undercut_amount = Number(state.undercut_amount);
      }

      if (state.selected_action === "ignore" && state.reason.trim().length > 0) {
        action.reason = state.reason.trim();
      }

      return action;
    })
    .filter((action): action is PriceMonitoringReviewAction => action !== null);
}
