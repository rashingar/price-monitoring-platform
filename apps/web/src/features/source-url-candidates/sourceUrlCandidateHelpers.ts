import type {
  SourceUrlCandidate,
  SourceUrlCandidateListParams,
  SkroutzNetworkCapturedEndpoint,
} from "../../api/commerceTypes";
import { DEFAULT_LIMIT } from "./sourceUrlCandidateConstants";
import { formatValue } from "./sourceUrlCandidateFormatters";
import type { CandidateFilters } from "./sourceUrlCandidateTypes";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function candidateId(candidate: SourceUrlCandidate): string {
  return String(candidate.id);
}

export function yesNo(value: unknown): string {
  return value === true ? "yes" : "no";
}

export function getJsonSection(source: unknown, keys: string[]): unknown {
  if (!isRecord(source)) {
    return undefined;
  }

  for (const key of keys) {
    if (source[key] !== undefined) {
      return source[key];
    }
  }

  return undefined;
}

export function renderJsonValue(value: unknown): string {
  if (value === undefined || value === null || value === "") {
    return "-";
  }

  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  return JSON.stringify(value, null, 2);
}

export function diagnosticTone(classification: string | null | undefined): string {
  switch (classification) {
    case "PRIMARY_CANDIDATE_PRODUCT_OFFERS":
      return "success";
    case "SECONDARY_CANDIDATE_SHOP_DETAILS":
      return "active";
    case "BLOCKED_OR_CHALLENGE":
      return "danger";
    default:
      return "neutral";
  }
}

export function endpointKeySummary(endpoint: SkroutzNetworkCapturedEndpoint): string {
  const summary = endpoint.json_summary;
  const keys = Array.isArray(summary?.top_level_keys) ? summary.top_level_keys : [];
  if (keys.length > 0) {
    return keys.slice(0, 6).join(", ");
  }

  if (Array.isArray(summary?.first_item_keys) && summary.first_item_keys.length > 0) {
    return `first item: ${summary.first_item_keys.slice(0, 6).join(", ")}`;
  }

  return formatValue(summary?.top_level_type);
}

export function diagnosticSourceUrlId(candidate: SourceUrlCandidate): string | number | null {
  const value = candidate.source_url_id;
  return typeof value === "string" || typeof value === "number" ? value : null;
}

export function isSkroutzCandidate(candidate: SourceUrlCandidate): boolean {
  const sourceName = String(candidate.source_name ?? "").toLowerCase();
  const domain = String(candidate.source_domain ?? "").toLowerCase();
  const url = String(candidate.candidate_url ?? candidate.canonical_url ?? "").toLowerCase();
  return sourceName === "skroutz" || domain.includes("skroutz.gr") || url.includes("skroutz.gr");
}

export function passesCreatedDateFilter(candidate: SourceUrlCandidate, filters: CandidateFilters): boolean {
  if (!filters.createdFrom && !filters.createdTo) {
    return true;
  }

  if (!candidate.created_at) {
    return false;
  }

  const createdTime = new Date(candidate.created_at).getTime();
  if (Number.isNaN(createdTime)) {
    return true;
  }

  if (filters.createdFrom) {
    const fromTime = new Date(`${filters.createdFrom}T00:00:00`).getTime();
    if (!Number.isNaN(fromTime) && createdTime < fromTime) {
      return false;
    }
  }

  if (filters.createdTo) {
    const toTime = new Date(`${filters.createdTo}T23:59:59.999`).getTime();
    if (!Number.isNaN(toTime) && createdTime > toTime) {
      return false;
    }
  }

  return true;
}

export function buildParams(filters: CandidateFilters, offset: number): SourceUrlCandidateListParams {
  return {
    status: filters.status === "all" ? null : filters.status,
    source_name: filters.sourceName.trim() || null,
    run_id: filters.runId.trim() || null,
    model: filters.model.trim() || null,
    catalog_product_id: filters.catalogProductId.trim() || null,
    min_confidence: filters.minConfidence.trim() || null,
    max_confidence: filters.maxConfidence.trim() || null,
    limit: DEFAULT_LIMIT,
    offset,
  };
}

export function isInteractiveClick(target: EventTarget | null): boolean {
  return target instanceof Element
    ? Boolean(target.closest("a, button, input, select, textarea, label, summary, [role='button']"))
    : false;
}
