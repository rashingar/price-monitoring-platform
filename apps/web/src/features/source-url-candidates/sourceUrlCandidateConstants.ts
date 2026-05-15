import type {
  SourceUrlCandidateReviewActionConfig,
  SourceUrlCandidateReviewLayoutColumn,
  SourceUrlCandidateStatus,
} from "../../api/commerceTypes";
import type { CandidateFilters } from "./sourceUrlCandidateTypes";

export const DEFAULT_LIMIT = 50;
export const REVIEW_LAYOUT_USER_KEY = "default";
export const SOURCE_URL_CANDIDATE_REVIEW_LAYOUT_STORAGE_KEY =
  "price-monitoring-platform:source-url-candidate-review-layout:v1";
export const MIN_COLUMN_WIDTH_PX = 28;
export const MAX_COLUMN_WIDTH_PX = 800;
export const DEFAULT_COLUMN_WIDTH_PX = 80;

export const REVIEW_STATUSES: Array<SourceUrlCandidateStatus | "all"> = [
  "pending",
  "needs_review",
  "accepted",
  "rejected",
  "not_found",
  "error",
  "all",
];

export const DEFAULT_COLUMNS: SourceUrlCandidateReviewLayoutColumn[] = [
  { key: "status", label: "Status", visible: true, table_column_visible: true, width_px: 56, order: 0 },
  { key: "confidence_score", label: "Confidence", visible: true, table_column_visible: true, width_px: 32, order: 1 },
  { key: "model", label: "Model", visible: false, table_column_visible: false, width_px: 28, order: 2 },
  { key: "mpn", label: "MPN", visible: true, table_column_visible: true, width_px: 48, order: 3 },
  { key: "manufacturer", label: "Brand", visible: true, table_column_visible: true, width_px: 32, order: 4 },
  { key: "source_name", label: "Source", visible: true, table_column_visible: true, width_px: 32, order: 5 },
  { key: "candidate_price", label: "Source price", visible: true, table_column_visible: true, width_px: 32, order: 6 },
  { key: "own_price", label: "Own price", visible: true, table_column_visible: true, width_px: 32, order: 7 },
  { key: "candidate_title", label: "Source title", visible: true, table_column_visible: true, width_px: 260, order: 8 },
];

export const FALLBACK_REVIEW_ACTIONS: SourceUrlCandidateReviewActionConfig[] = [
  { decision: "accept", label: "Accept", style: "primary" },
  { decision: "reject", label: "Reject", style: "danger" },
  { decision: "replace_url", label: "Replace URL", style: "secondary", requires_url: true },
];

export const initialFilters: CandidateFilters = {
  status: "needs_review",
  sourceName: "",
  runId: "",
  model: "",
  catalogProductId: "",
  minConfidence: "",
  maxConfidence: "",
  matchMethod: "",
  createdFrom: "",
  createdTo: "",
};
