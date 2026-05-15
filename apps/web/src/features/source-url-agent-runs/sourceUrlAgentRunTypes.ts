import type { SourceUrlAgentReadiness, SourceUrlAgentRun } from "../../api/commerceTypes";

export type SourceUrlAgentReadinessState = {
  readiness: SourceUrlAgentReadiness | null;
  isLoading: boolean;
  error: string | null;
};

export type SourceUrlAgentRunTotals = {
  selected_count: number;
  candidate_count: number;
  needs_review_count: number;
  error_count: number;
};

export type SourceUrlAgentRunsState = {
  runs: SourceUrlAgentRun[];
  isLoading: boolean;
  error: string | null;
};
