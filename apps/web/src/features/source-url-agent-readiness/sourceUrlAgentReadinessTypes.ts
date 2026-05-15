import type { SourceUrlAgentReadiness } from "../../api/commerceTypes";

export type SourceUrlAgentReadinessStatus = SourceUrlAgentReadiness["status"];

export interface SourceUrlAgentReadinessState {
  readiness: SourceUrlAgentReadiness | null;
  isLoading: boolean;
  error: string | null;
}

