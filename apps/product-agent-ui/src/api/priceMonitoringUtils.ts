import type {
  FetchPriceMonitoringResult,
  MarketplaceFilter,
  PriceMonitoringAction,
  PriceMonitoringSource,
} from "./commerceTypes";

export const PRICE_MONITORING_STATE_KEY = "product-agent-ui:price-monitoring:v1";
export const PRICE_MONITORING_EXECUTIONS_STATE_KEY =
  "product-agent-ui:price-monitoring-executions:v1";

export type SourceOverride = "" | PriceMonitoringSource;
export type StoredObservationMatchFilter = "all" | "matched" | "unmatched";

export interface StoredReviewActionDraft {
  run_id: string;
  model: string;
  selected_action: "" | PriceMonitoringAction;
  undercut_amount: string;
  reason: string;
}

export interface PriceMonitoringWorkflowState {
  source: string;
  q: string;
  selectedFamily: string;
  selectedCategory: string;
  selectedSubCategory: string;
  manufacturer: string;
  marketplace: MarketplaceFilter;
  selectedModelText: string;
  excludedModelText: string;
  includeIgnored: boolean;
  automationEligibleOnly: boolean;
  atomicOnly: boolean;
  hasMpn: boolean;
  currentRunId: string;
  currentExecutionId: string;
  fetchSource: SourceOverride;
  catalogUrl: string;
  enrichedCsvPath: string;
  storedMatchStatus: StoredObservationMatchFilter;
  includeUnmatchedObservations: boolean;
  storedModelFilter: string;
  storedMpnFilter: string;
  reviewCsvPath: string;
  useCustomExportPath: boolean;
  selectedExportArtifactRoot: string;
  exportOutputPath: string;
  reviewActionDrafts: StoredReviewActionDraft[];
}

export const initialPriceMonitoringWorkflowState: PriceMonitoringWorkflowState = {
  source: "",
  q: "",
  selectedFamily: "",
  selectedCategory: "",
  selectedSubCategory: "",
  manufacturer: "",
  marketplace: "all",
  selectedModelText: "",
  excludedModelText: "",
  includeIgnored: false,
  automationEligibleOnly: true,
  atomicOnly: true,
  hasMpn: true,
  currentRunId: "",
  currentExecutionId: "",
  fetchSource: "",
  catalogUrl: "",
  enrichedCsvPath: "",
  storedMatchStatus: "all",
  includeUnmatchedObservations: true,
  storedModelFilter: "",
  storedMpnFilter: "",
  reviewCsvPath: "",
  useCustomExportPath: false,
  selectedExportArtifactRoot: "",
  exportOutputPath: "",
  reviewActionDrafts: [],
};

export function normalizeFetchStatus(status: unknown): string {
  if (typeof status !== "string" || status.trim().length === 0) {
    return "";
  }

  if (status === "fetch_completed") {
    return "succeeded";
  }

  if (status === "fetch_failed") {
    return "failed";
  }

  return status.trim().toLowerCase();
}

export function isActiveFetchStatus(status: unknown): boolean {
  const normalized = normalizeFetchStatus(status);
  return normalized === "queued" || normalized === "running";
}

export function isSuccessfulFetchStatus(status: unknown): boolean {
  return normalizeFetchStatus(status) === "succeeded";
}

export function isFailedFetchStatus(status: unknown): boolean {
  const normalized = normalizeFetchStatus(status);
  return normalized === "failed" || normalized === "killed";
}

export function isKilledFetchStatus(status: unknown): boolean {
  return normalizeFetchStatus(status) === "killed";
}

export function isCancelledFetchStatus(status: unknown): boolean {
  return normalizeFetchStatus(status) === "cancelled";
}

export function isTerminalFetchStatus(status: unknown): boolean {
  return (
    isSuccessfulFetchStatus(status) ||
    isFailedFetchStatus(status) ||
    isCancelledFetchStatus(status)
  );
}

export function getFetchStatusTone(status: unknown): string {
  const normalized = normalizeFetchStatus(status);
  if (normalized === "queued" || normalized === "running") {
    return "active";
  }

  if (normalized === "succeeded") {
    return "ok";
  }

  if (normalized === "failed" || normalized === "killed") {
    return "danger";
  }

  if (normalized === "cancelled") {
    return "warning";
  }

  return "neutral";
}

export function formatFetchStatus(status: unknown): string {
  const normalized = normalizeFetchStatus(status);
  if (!normalized) {
    return "-";
  }

  return normalized.replace(/_/g, " ").replace(/^\w/, (first) => first.toUpperCase());
}

export function shouldTreatArtifactsAsDiagnostic(result: FetchPriceMonitoringResult): boolean {
  if (result.artifacts_are_diagnostic === true) {
    return true;
  }

  if (result.artifacts_are_diagnostic === false) {
    return false;
  }

  return isFailedFetchStatus(result.status);
}
