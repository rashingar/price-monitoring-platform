import type { SourceUrlCandidateStatus } from "../../api/commerceTypes";

export interface CandidateFilters {
  status: SourceUrlCandidateStatus | "all";
  sourceName: string;
  runId: string;
  model: string;
  catalogProductId: string;
  minConfidence: string;
  maxConfidence: string;
  matchMethod: string;
  createdFrom: string;
  createdTo: string;
}
