export type ReviewColumnId =
  | "model"
  | "name"
  | "mpn"
  | "current_price"
  | "competitor_price"
  | "competitor_store"
  | "competitor_url"
  | "price_delta"
  | "price_delta_percent"
  | "recommended_action"
  | "selected_action"
  | "undercut_amount"
  | "target_price"
  | "reason"
  | "status"
  | "warnings";

export const reviewColumnIds: ReviewColumnId[] = [
  "model",
  "name",
  "mpn",
  "current_price",
  "competitor_price",
  "competitor_store",
  "competitor_url",
  "price_delta",
  "price_delta_percent",
  "recommended_action",
  "selected_action",
  "undercut_amount",
  "target_price",
  "reason",
  "status",
  "warnings",
];
