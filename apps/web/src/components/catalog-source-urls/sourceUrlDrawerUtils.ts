import type {
  MarketplaceFilter,
  PriceMonitoringSource,
  ProductSourceUrlCandidateHistoryResponse,
  SourceUrl,
  SourceUrlAgentRun,
  SourceUrlCandidate,
} from "../../api/commerceTypes";
import {
  getSourceUrlAgentRunId,
  isActiveSourceUrlAgentRun,
} from "../../features/catalog/sourceUrlDiscovery";

export function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return String(value);
}

export function formatDate(value: unknown): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    return "-";
  }

  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function sourceUrlId(sourceUrl: SourceUrl): string | number | null {
  return sourceUrl.id ?? sourceUrl.source_url_id ?? null;
}

export function sourceUrlStatusClass(status: string | null | undefined): string {
  switch (status) {
    case "active":
    case "success":
    case "succeeded":
      return "success";
    case "needs_review":
    case "warning":
      return "warning";
    case "broken":
    case "failed":
    case "error":
      return "danger";
    case "disabled":
      return "neutral";
    case "redirected":
      return "queued";
    default:
      return "neutral";
  }
}

export function discoverySourceForDrawer(
  marketplace: MarketplaceFilter,
  source: PriceMonitoringSource,
): string {
  if (marketplace === "bestprice" || marketplace === "skroutz") {
    return marketplace;
  }
  return source || "bestprice";
}

export function sourceUrlProvenanceLabel(sourceUrl: SourceUrl): string {
  const provenance = String(sourceUrl.provenance ?? "unknown").toLowerCase();
  if (provenance === "manual") {
    return "Manual";
  }
  if (provenance === "discovery") {
    return "Discovery";
  }
  if (provenance === "import") {
    return "Import";
  }
  return "Unknown";
}

export function isTerminalDiscoveryRun(run: SourceUrlAgentRun | null): boolean {
  return !isActiveSourceUrlAgentRun(run);
}

export function isSuccessfulDiscoveryRun(run: SourceUrlAgentRun | null): boolean {
  const status = typeof run?.status === "string" ? run.status.toLowerCase() : "";
  return status === "succeeded" || status === "success" || status === "completed";
}

export function runMessage(run: SourceUrlAgentRun | null): string | null {
  const taskError = run?.tasks?.find((task) => String(task.error_message ?? "").trim().length > 0)?.error_message;
  if (taskError) {
    return String(taskError);
  }
  const warnings = Array.isArray(run?.warnings) ? run?.warnings : [];
  return warnings.length > 0 ? String(warnings[0]) : null;
}

export function reviewableCandidates(history: ProductSourceUrlCandidateHistoryResponse | null): SourceUrlCandidate[] {
  const latest = history?.items?.[0];
  if (!latest) {
    return [];
  }
  return latest.candidates.filter((candidate) => {
    const status = String(candidate.status ?? "").toLowerCase();
    return Boolean(candidate.candidate_url) && (status === "needs_review" || status === "pending");
  });
}

export function candidateKey(candidate: SourceUrlCandidate): string {
  return String(candidate.id);
}

export function hasCaptureMetadata(sourceUrl: SourceUrl): boolean {
  return Boolean(
    sourceUrl.product_source_id ??
      sourceUrl.capture_status ??
      sourceUrl.last_capture_status ??
      sourceUrl.last_fetch_status ??
      sourceUrl.last_capture_strategy ??
      sourceUrl.last_capture_snapshot_id ??
      sourceUrl.source_capture_snapshot_id ??
      sourceUrl.snapshot_ref ??
      sourceUrl.full_snapshot_ref,
  );
}

export function formatArtifactReference(value: unknown): string {
  if (typeof value === "string" && value.trim().length > 0) {
    return value;
  }

  if (typeof value === "object" && value !== null && "path" in value) {
    const path = (value as { path?: unknown }).path;
    return typeof path === "string" && path.trim().length > 0 ? path : "-";
  }

  return "-";
}

export function normalizeActionLabel(status: string): string {
  return status.replace(/_/g, " ");
}

export function sourceUrlAgentRunId(run: SourceUrlAgentRun | null): string | null {
  return getSourceUrlAgentRunId(run);
}
