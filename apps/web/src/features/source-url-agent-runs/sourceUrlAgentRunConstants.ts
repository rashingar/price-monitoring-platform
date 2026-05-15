import type { SourceUrlAgentRunRequest } from "../../api/commerceTypes";

export const DEFAULT_RUN_REQUEST: SourceUrlAgentRunRequest = {
  mode: "catalog",
  source: "all",
  selected_models: [],
  missing_only: true,
  active_only: true,
  dry_run: true,
  apply_high_confidence: false,
  limit: 20,
  rate_limit_seconds: 2,
};
