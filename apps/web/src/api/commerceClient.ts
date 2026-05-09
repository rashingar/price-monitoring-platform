import type {
  AlertEvent,
  AlertEventStatus,
  AlertEventsResponse,
  AlertRule,
  AlertRulesResponse,
  ApplyPriceMonitoringReviewActionsBody,
  ApplyPriceMonitoringReviewActionsResult,
  ArtifactItem,
  ArtifactListResponse,
  ArtifactPayload,
  ArtifactReadResponse,
  ArtifactRoot,
  BridgeRunBody,
  BridgeRunResponse,
  CatalogBrandOption,
  CatalogCategoryHierarchyResponse,
  CatalogCategoryNode,
  CatalogCategoryOption,
  CatalogFamilyNode,
  CatalogProduct,
  CatalogProductsParams,
  CatalogProductsResponse,
  CatalogSnapshot,
  CatalogSnapshotResponse,
  CatalogSubCategoryNode,
  CatalogSummary,
  CancelPriceMonitoringFetchBody,
  CreateAlertRuleBody,
  EvaluateAlertsResponse,
  ExportPriceMonitoringPriceUpdateBody,
  ExportPriceMonitoringPriceUpdateResult,
  FetchPriceMonitoringBody,
  FetchPriceMonitoringResult,
  FileListParams,
  FileListResponse,
  FileListItem,
  FileRoot,
  PathRootsEnv,
  PathRootsResponse,
  ProductFactoryHandoffImportRequest,
  PriceHistoryResponse,
  PriceMonitoringDbStatus,
  PriceMonitoringFetchLogsResponse,
  PriceObservation,
  PriceObservationsParams,
  PriceObservationsResponse,
  PriceMonitoringReviewItem,
  PriceMonitoringReviewParams,
  PriceMonitoringReviewResponse,
  PriceMonitoringRun,
  PriceMonitoringSelectionBody,
  PriceMonitoringSelectionItem,
  PriceMonitoringSelectionResult,
  PriceMonitoringSourceUrlCoverage,
  RunPriceObservationsResponse,
  ReadCsvFileBody,
  ReadCsvFileResponse,
  SaveCsvCopyBody,
  SaveCsvFileBody,
  SaveCsvResponse,
  MissingSourceUrlProduct,
  SourceUrl,
  SourceUrlCreateBody,
  SourceUrlImportRequest,
  SourceUrlImportResponse,
  SourceUrlImportCandidateReport,
  SourceUrlImportSummary,
  SourceUrlCandidate,
  SourceUrlCandidateListParams,
  SourceUrlCandidateListResponse,
  SourceUrlCandidateReviewActionConfig,
  SourceUrlCandidateReviewBody,
  SourceUrlCandidateReviewLayout,
  SourceUrlCandidateReviewLayoutColumn,
  SourceUrlAgentRun,
  SourceUrlAgentRunArtifactsResponse,
  SourceUrlAgentRunRequest,
  SourceUrlAgentTask,
  SourceUrlAgentRunSummary,
  SkroutzNetworkCapturedEndpoint,
  SkroutzNetworkDiagnosticReport,
  SkroutzNetworkDiagnosticSummary,
  SourceUrlListResponse,
  SourceUrlSummaryResponse,
  SourceUrlUpdateBody,
  SourceUrlValidationResponse,
  UpdateAlertRuleBody,
  VendorSourceCaptureRun,
  VendorSourceCaptureRunArtifactsResponse,
  VendorSourceCaptureRunRequest,
  VendorSourceCaptureRunSummary,
  VendorSourceCapability,
} from "./commerceTypes";

const DEFAULT_COMMERCE_API_BASE_URL = "/commerce-api";

const configuredCommerceApiBaseUrl = import.meta.env.VITE_COMMERCE_API_BASE_URL?.replace(
  /\/+$/,
  "",
);
const commerceApiBaseUrl =
  configuredCommerceApiBaseUrl && configuredCommerceApiBaseUrl.length > 0
    ? configuredCommerceApiBaseUrl
    : DEFAULT_COMMERCE_API_BASE_URL;

export class CommerceApiError extends Error {
  readonly status: number;
  readonly details: unknown;
  readonly path?: string;

  constructor(message: string, status: number, details: unknown, path?: string) {
    super(message);
    this.name = "CommerceApiError";
    this.status = status;
    this.details = details;
    this.path = path;
  }
}

type CommerceRequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getPayloadMessage(payload: unknown): string | null {
  if (typeof payload === "string" && payload.trim().length > 0) {
    return payload;
  }

  if (!isRecord(payload)) {
    return null;
  }

  for (const key of ["message", "detail", "error"]) {
    const value = payload[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return value;
    }

    if (Array.isArray(value) && value.length > 0) {
      return value
        .map((item) => {
          if (typeof item === "string") {
            return item;
          }

          if (isRecord(item)) {
            const message = item.msg ?? item.message ?? item.detail;
            if (typeof message === "string") {
              return message;
            }

            return JSON.stringify(item);
          }

          return String(item);
        })
        .join("; ");
    }
  }

  return null;
}

export function getCommerceApiErrorMessage(error: unknown): string {
  if (error instanceof CommerceApiError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Something went wrong while talking to the commerce backend.";
}

async function parseResponse(response: Response): Promise<unknown> {
  const text = await response.text();
  if (text.trim().length === 0) {
    return null;
  }

  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function buildHeaders(options: CommerceRequestOptions): HeadersInit {
  const headers = new Headers(options.headers);
  if (options.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  return headers;
}

type QueryParams = Record<string, string | number | boolean | null | undefined>;

function appendQuery(path: string, params?: QueryParams): string {
  if (!params) {
    return path;
  }

  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "" || value === "all") {
      return;
    }

    search.set(key, String(value));
  });

  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

export function toCommerceArtifactUrl(urlOrPath: string): string {
  const value = urlOrPath.trim();
  if (value.length === 0) {
    return "";
  }

  if (value.startsWith("/commerce-api/")) {
    return value;
  }

  if (value.startsWith("/api/artifacts/")) {
    return value.replace(/^\/api\/artifacts\//, "/commerce-api/artifacts/");
  }

  return `/commerce-api/artifacts/download?path=${encodeURIComponent(value)}`;
}

export function getArtifactPath(value: ArtifactPayload | string | null | undefined): string {
  if (typeof value === "string") {
    return value;
  }

  return value?.path ?? "";
}

function normalizeStringList(payload: unknown): string[] {
  const list = Array.isArray(payload)
    ? payload
    : isRecord(payload)
      ? payload.items ?? payload.categories ?? payload.brands ?? payload.data ?? payload.results
      : null;

  if (!Array.isArray(list)) {
    return [];
  }

  return list
    .filter((value): value is string | number => typeof value === "string" || typeof value === "number")
    .map((value) => String(value));
}

function getArrayPayload(payload: unknown, keys: string[]): unknown[] {
  if (Array.isArray(payload)) {
    return payload;
  }

  if (!isRecord(payload)) {
    return [];
  }

  for (const key of keys) {
    const value = payload[key];
    if (Array.isArray(value)) {
      return value;
    }
  }

  return [];
}

function toNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function normalizeProduct(value: unknown): CatalogProduct | null {
  if (!isRecord(value) || typeof value.model !== "string") {
    return null;
  }

  return value as CatalogProduct;
}

function normalizeProductsResponse(payload: unknown): CatalogProductsResponse {
  if (!isRecord(payload)) {
    return {
      items: [],
      page: 1,
      page_size: 100,
      total: 0,
      filtered_total: 0,
      warning: null,
    };
  }

  const items = Array.isArray(payload.items)
    ? payload.items.map(normalizeProduct).filter((item): item is CatalogProduct => item !== null)
    : [];
  const warnings = normalizeStringArray(payload.warnings);
  const warning =
    typeof payload.warning === "string" && payload.warning.trim().length > 0
      ? payload.warning
      : warnings.length > 0
        ? warnings.join(" ")
        : null;

  return {
    items,
    page: toNumber(payload.page, 1),
    page_size: toNumber(payload.page_size, items.length || 100),
    total: toNumber(payload.total, items.length),
    filtered_total: toNumber(payload.filtered_total, items.length),
    warning,
  };
}

function normalizeOptionalNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
}

function normalizeCounter(value: unknown): number {
  return normalizeOptionalNumber(value) ?? 0;
}

function normalizeSourceUrl(value: unknown): SourceUrl | null {
  if (!isRecord(value)) {
    return null;
  }

  const url = normalizeNullableString(value.url ?? value.url_normalized);
  if (!url || url.trim().length === 0) {
    return null;
  }

  return {
    ...value,
    id: normalizeNullableId(value.id ?? value.source_url_id),
    source_url_id: normalizeNullableId(value.source_url_id ?? value.id),
    catalog_product_id: normalizeNullableId(value.catalog_product_id),
    product_source_id: normalizeNullableId(value.product_source_id),
    catalog_source: normalizeNullableString(value.catalog_source),
    model: normalizeNullableString(value.model),
    mpn: normalizeNullableString(value.mpn),
    manufacturer: normalizeNullableString(value.manufacturer),
    source_name: normalizeNullableString(value.source_name),
    source_domain: normalizeNullableString(value.source_domain),
    url,
    url_normalized: normalizeNullableString(value.url_normalized),
    status: normalizeNullableString(value.status) ?? "active",
    url_type: normalizeNullableString(value.url_type) ?? "manual",
    trust_level: normalizeNullableString(value.trust_level),
    added_by: normalizeNullableString(value.added_by),
    notes: normalizeNullableString(value.notes),
    last_seen_at: normalizeNullableString(value.last_seen_at),
    last_success_at: normalizeNullableString(value.last_success_at),
    last_failed_at: normalizeNullableString(value.last_failed_at),
    failure_count: normalizeOptionalNumber(value.failure_count),
    last_error: normalizeNullableString(value.last_error),
    capture_status: normalizeNullableString(value.capture_status),
    last_fetch_status: normalizeNullableString(value.last_fetch_status),
    last_capture_status: normalizeNullableString(value.last_capture_status),
    last_capture_strategy: normalizeNullableString(value.last_capture_strategy),
    last_capture_at: normalizeNullableString(value.last_capture_at),
    last_fetched_at: normalizeNullableString(value.last_fetched_at ?? value.fetched_at),
    last_capture_snapshot_id: normalizeNullableId(value.last_capture_snapshot_id),
    source_capture_snapshot_id: normalizeNullableId(value.source_capture_snapshot_id),
    artifact_ref: normalizeArtifactPathValue(value.artifact_ref),
    artifact_refs: getArrayPayload(value.artifact_refs, ["items", "artifacts", "data", "results"])
      .map(normalizeCommerceArtifact)
      .filter((item): item is ArtifactItem => item !== null),
    snapshot_ref: normalizeArtifactPathValue(value.snapshot_ref),
    full_snapshot_ref: normalizeArtifactPathValue(value.full_snapshot_ref),
    created_at: normalizeNullableString(value.created_at),
    updated_at: normalizeNullableString(value.updated_at),
  };
}

function normalizeSourceUrlList(payload: unknown): SourceUrlListResponse {
  const source = isRecord(payload) ? payload : {};
  const items = getArrayPayload(payload, ["items", "source_urls", "data", "results"])
    .map(normalizeSourceUrl)
    .filter((item): item is SourceUrl => item !== null);

  return {
    ...source,
    items,
    count: normalizeOptionalNumber(source.count) ?? items.length,
  };
}

function normalizeSourceUrlValidation(payload: unknown): SourceUrlValidationResponse {
  const source = isRecord(payload) ? payload : {};
  const item = normalizeSourceUrl(source.item ?? source.source_url ?? payload);
  const validation = isRecord(source.validation)
    ? source.validation
    : isRecord(source.result)
      ? source.result
      : {};

  return {
    ...source,
    item,
    validation: {
      ...validation,
      status: normalizeNullableString(validation.status),
      message: normalizeNullableString(validation.message),
      http_status_code: normalizeOptionalNumber(validation.http_status_code),
    },
  };
}

function normalizeNumberRecord(value: unknown): Record<string, number> {
  if (!isRecord(value)) {
    return {};
  }

  return Object.entries(value).reduce<Record<string, number>>((record, [key, entryValue]) => {
    record[key] = normalizeCounter(entryValue);
    return record;
  }, {});
}

function normalizeMissingSourceUrlProduct(value: unknown): MissingSourceUrlProduct | null {
  if (!isRecord(value)) {
    return null;
  }

  const model = normalizeNullableString(value.model);
  const catalogProductId = normalizeNullableId(
    value.catalog_product_id ?? value.product_id ?? value.id,
  );
  if (!model && catalogProductId === null) {
    return null;
  }

  return {
    ...value,
    catalog_product_id: catalogProductId,
    model,
    mpn: normalizeNullableString(value.mpn),
    manufacturer: normalizeNullableString(value.manufacturer),
    name: normalizeNullableString(value.name ?? value.product_name),
    reason:
      normalizeNullableString(value.reason) ??
      normalizeNullableString(value.monitoring_blocker) ??
      "missing_active_source_url",
  };
}

function normalizeSourceUrlSummary(payload: unknown): SourceUrlSummaryResponse {
  const source = isRecord(payload) ? payload : {};
  const statusCounters = normalizeNumberRecord(source.by_status);
  const typeCounters = normalizeNumberRecord(source.by_type ?? source.by_url_type);
  const sourceCounters = normalizeNumberRecord(source.by_source ?? source.by_source_name);
  const missingProducts = getArrayPayload(
    source.missing_active_source_url_products ??
      source.products_without_active_source_urls_items ??
      source.not_monitorable_products,
    ["items", "products", "data", "results"],
  )
    .map(normalizeMissingSourceUrlProduct)
    .filter((item): item is MissingSourceUrlProduct => item !== null);

  return {
    ...source,
    catalog_source: normalizeNullableString(source.catalog_source),
    catalog_product_count: normalizeCounter(source.catalog_product_count),
    total_count: normalizeCounter(source.total_count ?? source.source_url_count ?? source.total ?? source.count),
    active_count: normalizeCounter(source.active_count ?? statusCounters.active),
    needs_review_count: normalizeCounter(source.needs_review_count ?? statusCounters.needs_review),
    broken_count: normalizeCounter(source.broken_count ?? statusCounters.broken),
    disabled_count: normalizeCounter(source.disabled_count ?? statusCounters.disabled),
    redirected_count: normalizeCounter(source.redirected_count ?? statusCounters.redirected),
    manual_count: normalizeCounter(source.manual_count ?? typeCounters.manual),
    imported_count: normalizeCounter(source.imported_count ?? typeCounters.imported),
    discovered_count: normalizeCounter(source.discovered_count ?? typeCounters.discovered),
    products_with_urls_count: normalizeCounter(
      source.products_with_urls_count ??
        source.products_with_urls ??
        source.products_with_active_source_urls,
    ),
    products_without_urls_count: normalizeCounter(
      source.products_without_urls_count ??
        source.products_without_urls ??
        source.products_without_active_source_urls,
    ),
    coverage_percent: normalizeOptionalNumber(source.coverage_percent),
    by_status: statusCounters,
    by_type: typeCounters,
    by_source: sourceCounters,
    missing_source_url_models: normalizeStringArray(source.missing_source_url_models),
    missing_source_url_catalog_product_ids: Array.isArray(source.missing_source_url_catalog_product_ids)
      ? source.missing_source_url_catalog_product_ids.filter(
          (value): value is number | string => typeof value === "number" || typeof value === "string",
        )
      : [],
    missing_active_source_url_products: missingProducts,
    updated_at: normalizeNullableString(source.updated_at),
  };
}

const SOURCE_URL_IMPORT_COUNTERS = [
  "candidates_found",
  "imported_count",
  "updated_count",
  "skipped_count",
  "active_count",
  "needs_review_count",
  "invalid_url_count",
  "duplicate_count",
  "unresolved_identity_count",
  "ambiguous_identity_count",
] as const;

function normalizeSourceUrlImportSummary(payload: unknown): SourceUrlImportSummary {
  const source = isRecord(payload) ? payload : {};
  const summary = SOURCE_URL_IMPORT_COUNTERS.reduce<SourceUrlImportSummary>(
    (record, key) => {
      record[key] = normalizeCounter(source[key]);
      return record;
    },
    {
      candidates_found: 0,
      imported_count: 0,
      updated_count: 0,
      skipped_count: 0,
      active_count: 0,
      needs_review_count: 0,
      invalid_url_count: 0,
      duplicate_count: 0,
      unresolved_identity_count: 0,
      ambiguous_identity_count: 0,
    },
  );

  const wouldImportCount = normalizeOptionalNumber(source.would_import_count);
  const wouldUpdateCount = normalizeOptionalNumber(source.would_update_count);
  if (wouldImportCount !== null) {
    summary.would_import_count = wouldImportCount;
  }
  if (wouldUpdateCount !== null) {
    summary.would_update_count = wouldUpdateCount;
  }

  return { ...source, ...summary };
}

function normalizeSourceStats(value: unknown): Record<string, Record<string, number>> {
  if (!isRecord(value)) {
    return {};
  }

  return Object.entries(value).reduce<Record<string, Record<string, number>>>((record, [key, stats]) => {
    record[key] = normalizeNumberRecord(stats);
    return record;
  }, {});
}

function normalizeSourceUrlImportReportItem(value: unknown): SourceUrlImportCandidateReport | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    ...value,
    action: normalizeNullableString(value.action),
    status: normalizeNullableString(value.status),
    source_name: normalizeNullableString(value.source_name),
    source_domain: normalizeNullableString(value.source_domain),
    catalog_source: normalizeNullableString(value.catalog_source),
    model: normalizeNullableString(value.model),
    mpn: normalizeNullableString(value.mpn),
    url: normalizeNullableString(value.url),
    url_normalized: normalizeNullableString(value.url_normalized),
    evidence_source: normalizeNullableString(value.evidence_source),
    evidence_detail: normalizeNullableString(value.evidence_detail),
    reason: normalizeNullableString(value.reason),
    confidence: normalizeNullableString(value.confidence),
    catalog_product_id: normalizeNullableId(value.catalog_product_id),
    source_url_id: normalizeNullableId(value.source_url_id),
  };
}

function normalizeSourceUrlImportResponse(payload: unknown): SourceUrlImportResponse {
  const source = isRecord(payload) ? payload : {};
  const rawSummary = isRecord(source.summary) ? source.summary : source;
  const summary = normalizeSourceUrlImportSummary(rawSummary);
  const reportItems = getArrayPayload(source.report_items ?? source.items, ["items", "data", "results"])
    .map(normalizeSourceUrlImportReportItem)
    .filter((item): item is SourceUrlImportCandidateReport => item !== null);
  const mode = normalizeNullableString(source.mode);
  const apply = source.apply === true || source.applied === true || mode === "apply" || mode === "applied";
  const sourceStats = normalizeSourceStats(source.source_stats ?? source.sources);

  return {
    ...source,
    ...summary,
    applied: source.applied === true || apply,
    apply,
    mode,
    summary: {
      ...summary,
      would_import_count:
        summary.would_import_count ?? (!apply ? summary.imported_count : undefined),
      would_update_count:
        summary.would_update_count ?? (!apply ? summary.updated_count : undefined),
    },
    sources: sourceStats,
    items: reportItems,
    sources_processed: normalizeStringArray(
      source.sources_processed ?? (isRecord(source.sources) ? Object.keys(source.sources) : []),
    ),
    warnings: normalizeStringArray(source.warnings),
    skipped_reasons: normalizeNumberRecord(source.skipped_reasons),
    changed_source_urls: Array.isArray(source.changed_source_urls) ? source.changed_source_urls : [],
    source_stats: sourceStats,
    candidate_evidence: Array.isArray(source.candidate_evidence) ? source.candidate_evidence : [],
    report_items: reportItems,
    truncated: source.truncated === true,
    report_truncated: source.report_truncated === true || source.truncated === true,
    handoff_summary: isRecord(source.handoff_summary) ? source.handoff_summary : null,
  };
}

function normalizeJsonLike(value: unknown): unknown {
  if (typeof value !== "string") {
    return value;
  }

  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return null;
  }

  try {
    return JSON.parse(trimmed) as unknown;
  } catch {
    return value;
  }
}

function normalizeSourceUrlCandidate(value: unknown): SourceUrlCandidate | null {
  if (!isRecord(value)) {
    return null;
  }

  const id = normalizeNullableId(value.id ?? value.candidate_id);
  if (id === null) {
    return null;
  }

  return {
    ...value,
    id,
    source_url_id: normalizeNullableId(value.source_url_id),
    run_id: normalizeNullableId(value.run_id),
    catalog_product_id: normalizeNullableId(value.catalog_product_id),
    model: normalizeNullableString(value.model),
    mpn: normalizeNullableString(value.mpn),
    manufacturer: normalizeNullableString(value.manufacturer),
    product_name: normalizeNullableString(value.product_name ?? value.name),
    category: normalizeNullableString(value.category),
    own_price: normalizeNullableId(value.own_price),
    source_name: normalizeNullableString(value.source_name),
    source_domain: normalizeNullableString(value.source_domain),
    source_type: normalizeNullableString(value.source_type),
    expected_listing:
      typeof value.expected_listing === "boolean"
        ? value.expected_listing
        : normalizeNullableString(value.expected_listing),
    candidate_url: normalizeNullableString(value.candidate_url ?? value.url),
    canonical_url: normalizeNullableString(value.canonical_url ?? value.url_normalized),
    candidate_title: normalizeNullableString(value.candidate_title ?? value.title),
    candidate_price: normalizeNullableId(value.candidate_price),
    match_status: normalizeNullableString(value.match_status),
    confidence_score: normalizeNullableId(value.confidence_score ?? value.confidence),
    match_method: normalizeNullableString(value.match_method),
    evidence_json: normalizeJsonLike(value.evidence_json ?? value.evidence),
    competing_candidates_count: normalizeNullableId(value.competing_candidates_count),
    searched_queries_json: normalizeJsonLike(value.searched_queries_json ?? value.searched_queries),
    status: normalizeNullableString(value.status) ?? "needs_review",
    reviewed_by: normalizeNullableString(value.reviewed_by),
    reviewed_at: normalizeNullableString(value.reviewed_at),
    notes: normalizeNullableString(value.notes),
    created_at: normalizeNullableString(value.created_at),
    updated_at: normalizeNullableString(value.updated_at),
  };
}

function normalizeSourceUrlCandidateList(payload: unknown): SourceUrlCandidateListResponse {
  const source = isRecord(payload) ? payload : {};
  const items = getArrayPayload(payload, ["items", "candidates", "data", "results"])
    .map(normalizeSourceUrlCandidate)
    .filter((item): item is SourceUrlCandidate => item !== null);

  return {
    items,
    total: normalizeOptionalNumber(source.total ?? source.count) ?? items.length,
    limit: normalizeOptionalNumber(source.limit) ?? items.length,
    offset: normalizeOptionalNumber(source.offset) ?? 0,
  };
}

function normalizeSourceUrlCandidateDetail(payload: unknown): SourceUrlCandidate {
  const source = isRecord(payload)
    ? payload.candidate ?? payload.item ?? payload.detail ?? payload.data ?? payload.result ?? payload
    : payload;
  return normalizeSourceUrlCandidate(source) ?? { id: "" };
}

function normalizeBooleanFlag(value: unknown): boolean {
  if (typeof value === "boolean") {
    return value;
  }

  if (typeof value === "number") {
    return value !== 0;
  }

  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    return normalized === "true" || normalized === "1" || normalized === "yes" || normalized === "enabled";
  }

  return false;
}

function normalizeVendorSourceCapability(value: unknown): VendorSourceCapability | null {
  if (!isRecord(value)) {
    return null;
  }

  const sourceName = normalizeNullableString(value.source_name ?? value.name ?? value.id);
  if (!sourceName) {
    return null;
  }

  return {
    ...value,
    source_name: sourceName,
    source_domain: normalizeNullableString(value.source_domain ?? value.domain),
    source_type: normalizeNullableString(value.source_type ?? value.type),
    discovery_enabled: normalizeBooleanFlag(value.discovery_enabled),
    capture_enabled: normalizeBooleanFlag(value.capture_enabled),
    capture_implemented: normalizeBooleanFlag(value.capture_implemented),
    supports_search: normalizeBooleanFlag(value.supports_search),
    supports_direct_product_url: normalizeBooleanFlag(value.supports_direct_product_url),
    supports_xhr_capture: normalizeBooleanFlag(value.supports_xhr_capture),
    expected_listing_field: normalizeNullableString(value.expected_listing_field),
    notes: normalizeNullableString(value.notes),
  };
}

function normalizeVendorSourceCapabilityList(payload: unknown): VendorSourceCapability[] {
  return getArrayPayload(payload, ["items", "sources", "capabilities", "data", "results"])
    .map(normalizeVendorSourceCapability)
    .filter((item): item is VendorSourceCapability => item !== null);
}

const SOURCE_URL_AGENT_RUN_COUNTERS = [
  "selected_count",
  "candidate_count",
  "matched_count",
  "needs_review_count",
  "not_found_count",
  "error_count",
  "high_confidence_count",
  "applied_count",
  "skipped_count",
  "task_total_count",
  "task_finished_count",
] as const;

function normalizeSourceUrlAgentRunSummary(payload: unknown): SourceUrlAgentRunSummary {
  const source = isRecord(payload) ? payload : {};

  return SOURCE_URL_AGENT_RUN_COUNTERS.reduce<SourceUrlAgentRunSummary>((summary, key) => {
    summary[key] = normalizeCounter(source[key]);
    return summary;
  }, { task_counts: normalizeNumberRecord(source.task_counts) });
}

function normalizeSourceUrlAgentTask(value: unknown): SourceUrlAgentTask | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    ...value,
    id: normalizeNullableId(value.id),
    run_id: normalizeNullableId(value.run_id),
    catalog_product_id: normalizeNullableId(value.catalog_product_id),
    model: normalizeNullableString(value.model),
    source_name: normalizeNullableString(value.source_name),
    status: normalizeNullableString(value.status) ?? "unknown",
    match_status: normalizeNullableString(value.match_status),
    candidate_count: normalizeCounter(value.candidate_count),
    error_message: normalizeNullableString(value.error_message),
    started_at: normalizeNullableString(value.started_at),
    completed_at: normalizeNullableString(value.completed_at),
    created_at: normalizeNullableString(value.created_at),
    updated_at: normalizeNullableString(value.updated_at),
  };
}

function normalizeSourceUrlAgentRun(value: unknown): SourceUrlAgentRun | null {
  if (!isRecord(value)) {
    return null;
  }

  const source = isRecord(value.run)
    ? value.run
    : isRecord(value.item)
      ? value.item
      : isRecord(value.data)
        ? value.data
        : isRecord(value.result)
          ? value.result
          : value;
  const summarySource = isRecord(source.summary) ? source.summary : source;
  const summary = normalizeSourceUrlAgentRunSummary(summarySource);
  const runId = normalizeNullableId(source.run_id ?? source.id);
  const taskCounts = normalizeNumberRecord(source.task_counts ?? summary.task_counts);
  const tasks = getArrayPayload(source.tasks, ["items", "tasks", "data", "results"])
    .map(normalizeSourceUrlAgentTask)
    .filter((item): item is SourceUrlAgentTask => item !== null);
  const artifacts = getArrayPayload(source.artifacts, ["items", "artifacts", "data", "results"])
    .map(normalizeCommerceArtifact)
    .filter((item): item is ArtifactItem => item !== null);

  return {
    ...source,
    ...summary,
    run_id: runId,
    id: normalizeNullableId(source.id ?? runId),
    source: normalizeNullableString(source.source),
    mode: normalizeNullableString(source.mode),
    status: normalizeNullableString(source.status) ?? "unknown",
    dry_run: typeof source.dry_run === "boolean" ? source.dry_run : null,
    apply_high_confidence:
      typeof source.apply_high_confidence === "boolean" ? source.apply_high_confidence : null,
    missing_only: typeof source.missing_only === "boolean" ? source.missing_only : null,
    active_only: typeof source.active_only === "boolean" ? source.active_only : null,
    limit: normalizeOptionalNumber(source.limit),
    rate_limit_seconds: normalizeOptionalNumber(source.rate_limit_seconds),
    output_dir: normalizeNullableString(source.output_dir),
    task_counts: taskCounts,
    task_total_count: normalizeCounter(source.task_total_count ?? summary.task_total_count),
    task_finished_count: normalizeCounter(source.task_finished_count ?? summary.task_finished_count),
    tasks,
    summary: { ...summary, task_counts: taskCounts },
    artifacts,
    warnings: normalizeStringArray(source.warnings),
    created_at: normalizeNullableString(source.created_at),
    started_at: normalizeNullableString(source.started_at),
    completed_at: normalizeNullableString(source.completed_at),
    updated_at: normalizeNullableString(source.updated_at),
  };
}

function normalizeSourceUrlAgentRunList(payload: unknown): SourceUrlAgentRun[] {
  return getArrayPayload(payload, ["items", "runs", "data", "results"])
    .map(normalizeSourceUrlAgentRun)
    .filter((item): item is SourceUrlAgentRun => item !== null);
}

function normalizeSourceUrlAgentRunArtifacts(
  payload: unknown,
): SourceUrlAgentRunArtifactsResponse {
  return normalizeArtifactList(payload) as SourceUrlAgentRunArtifactsResponse;
}

const VENDOR_SOURCE_CAPTURE_RUN_COUNTERS = [
  "selected_source_url_count",
  "succeeded_count",
  "failed_count",
  "skipped_count",
  "captured_count",
] as const;

function normalizeVendorSourceCaptureRunSummary(payload: unknown): VendorSourceCaptureRunSummary {
  const source = isRecord(payload) ? payload : {};

  return VENDOR_SOURCE_CAPTURE_RUN_COUNTERS.reduce<VendorSourceCaptureRunSummary>((summary, key) => {
    summary[key] = normalizeCounter(source[key]);
    return summary;
  }, {});
}

function normalizeIdArray(value: unknown): Array<number | string> {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter((item): item is number | string => typeof item === "number" || typeof item === "string");
}

function normalizeVendorSourceCaptureRun(value: unknown): VendorSourceCaptureRun | null {
  if (!isRecord(value)) {
    return null;
  }

  const source = isRecord(value.run)
    ? value.run
    : isRecord(value.item)
      ? value.item
      : isRecord(value.data)
        ? value.data
        : isRecord(value.result)
          ? value.result
          : value;
  const summarySource = isRecord(source.summary) ? source.summary : source;
  const summary = normalizeVendorSourceCaptureRunSummary(summarySource);
  const runId = normalizeNullableId(source.run_id ?? source.id);
  const artifacts = getArrayPayload(source.artifacts, ["items", "artifacts", "data", "results"])
    .map(normalizeCommerceArtifact)
    .filter((item): item is ArtifactItem => item !== null);

  return {
    ...source,
    ...summary,
    run_id: runId,
    id: normalizeNullableId(source.id ?? runId),
    source_filter: normalizeNullableString(source.source_filter ?? source.source),
    observation_batch_id: normalizeNullableId(source.observation_batch_id ?? summarySource.observation_batch_id),
    status: normalizeNullableString(source.status) ?? "unknown",
    limit: normalizeOptionalNumber(source.limit),
    include_not_due: typeof source.include_not_due === "boolean" ? source.include_not_due : null,
    refresh_after_minutes: normalizeOptionalNumber(source.refresh_after_minutes),
    catalog_product_ids: normalizeIdArray(source.catalog_product_ids),
    output_dir: normalizeNullableString(source.output_dir),
    summary,
    artifacts,
    warnings: normalizeStringArray(source.warnings),
    created_at: normalizeNullableString(source.created_at),
    started_at: normalizeNullableString(source.started_at),
    completed_at: normalizeNullableString(source.completed_at),
    updated_at: normalizeNullableString(source.updated_at),
  };
}

function normalizeVendorSourceCaptureRunList(payload: unknown): VendorSourceCaptureRun[] {
  return getArrayPayload(payload, ["items", "runs", "data", "results"])
    .map(normalizeVendorSourceCaptureRun)
    .filter((item): item is VendorSourceCaptureRun => item !== null);
}

function normalizeVendorSourceCaptureRunArtifacts(
  payload: unknown,
): VendorSourceCaptureRunArtifactsResponse {
  return normalizeArtifactList(payload) as VendorSourceCaptureRunArtifactsResponse;
}

function normalizeSkroutzNetworkEndpoint(value: unknown): SkroutzNetworkCapturedEndpoint | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    ...value,
    method: normalizeNullableString(value.method),
    url: normalizeNullableString(value.url),
    status: normalizeNullableId(value.status),
    resource_type: normalizeNullableString(value.resource_type),
    content_type: normalizeNullableString(value.content_type),
    body_size: normalizeNullableId(value.body_size),
    parsed_json_valid: typeof value.parsed_json_valid === "boolean" ? value.parsed_json_valid : null,
    json_summary: isRecord(value.json_summary) ? value.json_summary : null,
    classification: normalizeNullableString(value.classification),
    matched_derived_endpoint: normalizeNullableString(value.matched_derived_endpoint),
    body_sample: normalizeNullableString(value.body_sample),
    json_parse_error: normalizeNullableString(value.json_parse_error),
  };
}

function normalizeSkroutzNetworkDiagnosticSummary(payload: unknown): SkroutzNetworkDiagnosticSummary {
  const source = isRecord(payload) ? payload : {};
  return {
    ...source,
    source_url_id: normalizeNullableId(source.source_url_id),
    vendor_slug: normalizeNullableString(source.vendor_slug),
    source_url: normalizeNullableString(source.source_url),
    status: normalizeNullableString(source.status),
    captured_response_count: normalizeCounter(source.captured_response_count),
    derived_endpoints: isRecord(source.derived_endpoints)
      ? Object.fromEntries(
          Object.entries(source.derived_endpoints).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
        )
      : {},
    derived_filter_products_url: normalizeNullableString(source.derived_filter_products_url),
    derived_shops_details_url: normalizeNullableString(source.derived_shops_details_url),
    observed_derived_endpoints: isRecord(source.observed_derived_endpoints)
      ? Object.fromEntries(Object.entries(source.observed_derived_endpoints).map(([key, value]) => [key, normalizeBooleanFlag(value)]))
      : {},
    observed_filter_products_url: normalizeBooleanFlag(source.observed_filter_products_url),
    observed_shops_details_url: normalizeBooleanFlag(source.observed_shops_details_url),
    exact_match_count: normalizeCounter(source.exact_match_count),
    best_product_data_endpoint: normalizeNullableString(source.best_product_data_endpoint),
    product_data_candidate_url: normalizeNullableString(source.product_data_candidate_url ?? source.best_product_data_endpoint),
    product_data_candidate_reason: normalizeNullableString(source.product_data_candidate_reason),
    classifications_summary: normalizeNumberRecord(source.classifications_summary),
    blocked_or_challenge_detected: normalizeBooleanFlag(source.blocked_or_challenge_detected),
    diagnostic_report_id: normalizeNullableId(source.diagnostic_report_id),
    artifact_path: normalizeNullableString(source.artifact_path),
    error_code: normalizeNullableString(source.error_code),
    error_message: normalizeNullableString(source.error_message),
    created_at: normalizeNullableString(source.created_at),
  };
}

function normalizeSkroutzNetworkDiagnosticReport(payload: unknown): SkroutzNetworkDiagnosticReport {
  const source = isRecord(payload) ? payload : {};
  const summary = normalizeSkroutzNetworkDiagnosticSummary(source.summary ?? source);
  return {
    ...source,
    ...summary,
    summary,
    captured_responses: getArrayPayload(source.captured_responses, ["items", "responses", "data", "results"])
      .map(normalizeSkroutzNetworkEndpoint)
      .filter((item): item is SkroutzNetworkCapturedEndpoint => item !== null),
    started_at: normalizeNullableString(source.started_at),
    completed_at: normalizeNullableString(source.completed_at),
    timeout_seconds: normalizeOptionalNumber(source.timeout_seconds),
    headed: typeof source.headed === "boolean" ? source.headed : null,
  };
}

function normalizeLayoutColumn(value: unknown, index: number): SourceUrlCandidateReviewLayoutColumn | null {
  if (!isRecord(value)) {
    return null;
  }

  const key = normalizeNullableString(value.key ?? value.id ?? value.field ?? value.name);
  if (!key) {
    return null;
  }

  return {
    ...value,
    key,
    label: normalizeNullableString(value.label ?? value.title ?? key.replace(/_/g, " ")),
    visible:
      typeof value.visible === "boolean"
        ? value.visible
        : typeof value.table_column_visible === "boolean"
          ? value.table_column_visible
          : true,
    table_column_visible:
      typeof value.table_column_visible === "boolean"
        ? value.table_column_visible
        : typeof value.visible === "boolean"
          ? value.visible
          : true,
    width_px: normalizeOptionalNumber(value.width_px) ?? null,
    order: normalizeOptionalNumber(value.order) ?? index,
  };
}

function normalizeSourceUrlCandidateReviewLayout(payload: unknown): SourceUrlCandidateReviewLayout {
  const source = isRecord(payload)
    ? payload.layout ?? payload.review_layout ?? payload.data ?? payload.result ?? payload
    : {};
  const record = isRecord(source) ? source : {};
  const columns = getArrayPayload(record.columns, ["columns", "items", "data", "results"])
    .map(normalizeLayoutColumn)
    .filter((item): item is SourceUrlCandidateReviewLayoutColumn => item !== null);
  const reviewPanel = isRecord(record.review_panel) ? record.review_panel : {};
  const reviewActions = getArrayPayload(reviewPanel.review_actions, ["review_actions", "actions", "items"]);

  return {
    ...record,
    user_key: normalizeNullableString(record.user_key),
    columns,
    actions: isRecord(record.actions) ? record.actions : null,
    review_panel: {
      ...reviewPanel,
      review_actions: reviewActions.filter(isRecord) as SourceUrlCandidateReviewActionConfig[],
    },
  };
}

function normalizeSourceUrlCoverage(value: unknown): PriceMonitoringSourceUrlCoverage | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    ...value,
    source: normalizeNullableString(value.source),
    selected_count: normalizeOptionalNumber(value.selected_count) ?? undefined,
    products_with_active_source_urls: normalizeOptionalNumber(value.products_with_active_source_urls) ?? undefined,
    products_without_active_source_urls: normalizeOptionalNumber(value.products_without_active_source_urls) ?? undefined,
    coverage_percent: normalizeOptionalNumber(value.coverage_percent),
    active_source_url_count: normalizeOptionalNumber(value.active_source_url_count) ?? undefined,
    needs_review_source_url_count: normalizeOptionalNumber(value.needs_review_source_url_count) ?? undefined,
    broken_source_url_count: normalizeOptionalNumber(value.broken_source_url_count) ?? undefined,
    disabled_source_url_count: normalizeOptionalNumber(value.disabled_source_url_count) ?? undefined,
    redirected_source_url_count: normalizeOptionalNumber(value.redirected_source_url_count) ?? undefined,
    missing_source_url_models: normalizeStringArray(value.missing_source_url_models),
    missing_source_url_catalog_product_ids: Array.isArray(value.missing_source_url_catalog_product_ids)
      ? value.missing_source_url_catalog_product_ids
          .map(normalizeNullableId)
          .filter((item): item is string | number => item !== null)
      : [],
    has_active_source_url:
      typeof value.has_active_source_url === "boolean" ? value.has_active_source_url : undefined,
    status_counts: normalizeNumberRecord(value.status_counts),
    active_source_urls: getArrayPayload(value.active_source_urls, ["items", "source_urls", "data", "results"])
      .map(normalizeSourceUrl)
      .filter((item): item is SourceUrl => item !== null),
    warning: normalizeNullableString(value.warning),
  };
}

function normalizeSelectionItem(value: unknown): PriceMonitoringSelectionItem | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    ...value,
    catalog_product_id: normalizeNullableId(value.catalog_product_id),
    skip_reason:
      normalizeNullableString(value.skip_reason) ??
      normalizeNullableString(value.reason) ??
      normalizeNullableString(value.skipped_reason),
    reason:
      normalizeNullableString(value.reason) ??
      normalizeNullableString(value.skip_reason) ??
      normalizeNullableString(value.skipped_reason),
    source_url_coverage: normalizeSourceUrlCoverage(value.source_url_coverage),
  } as PriceMonitoringSelectionItem;
}

function normalizeSelectionResult(payload: unknown): PriceMonitoringSelectionResult {
  if (!isRecord(payload)) {
    return {};
  }

  const selectedItems = getArrayPayload(payload.selected_items ?? payload.selected ?? payload.items, ["items", "data", "results"])
    .map(normalizeSelectionItem)
    .filter((item): item is PriceMonitoringSelectionItem => item !== null);
  const skippedItems = getArrayPayload(payload.skipped_items ?? payload.skipped, ["items", "data", "results"])
    .map(normalizeSelectionItem)
    .filter((item): item is PriceMonitoringSelectionItem => item !== null);
  const skippedByReason = normalizeNumberRecord(payload.skipped_by_reason ?? payload.skipped_reasons);

  return {
    ...payload,
    run_id: normalizeNullableId(payload.run_id),
    selected_count: normalizeOptionalNumber(payload.selected_count) ?? undefined,
    skipped_count: normalizeOptionalNumber(payload.skipped_count) ?? undefined,
    skipped_by_reason: skippedByReason,
    skipped_reasons: skippedByReason,
    selected_items: selectedItems,
    selected: selectedItems,
    skipped_items: skippedItems,
    source_url_coverage: normalizeSourceUrlCoverage(payload.source_url_coverage),
  };
}

function normalizeFileRoot(value: unknown): FileRoot | null {
  if (!isRecord(value) || typeof value.path !== "string") {
    return null;
  }

  return {
    path: value.path,
    exists: value.exists === true,
  };
}

function normalizeFileRoots(payload: unknown): FileRoot[] {
  return getArrayPayload(payload, ["roots", "items", "data", "results"])
    .map(normalizeFileRoot)
    .filter((root): root is FileRoot => root !== null);
}

function normalizeArtifactRoot(value: unknown): ArtifactRoot | null {
  if (!isRecord(value)) {
    return null;
  }

  const path = value.path ?? value.root;
  if (typeof path !== "string" && typeof path !== "number") {
    return null;
  }

  return {
    path: String(path),
    exists: typeof value.exists === "boolean" ? value.exists : null,
    name: typeof value.name === "string" ? value.name : null,
    source: typeof value.source === "string" ? value.source : null,
    is_default: typeof value.is_default === "boolean" ? value.is_default : null,
    is_configured: typeof value.is_configured === "boolean" ? value.is_configured : null,
  };
}

function normalizeArtifactRoots(payload: unknown): ArtifactRoot[] {
  return getArrayPayload(payload, ["roots", "items", "data", "results"])
    .map(normalizeArtifactRoot)
    .filter((root): root is ArtifactRoot => root !== null);
}

function normalizePathRootsEnv(value: unknown): PathRootsEnv {
  if (!isRecord(value)) {
    return {};
  }

  return Object.entries(value).reduce<PathRootsEnv>((env, [key, envValue]) => {
    env[key] =
      typeof envValue === "string" || envValue === null || envValue === undefined
        ? envValue
        : String(envValue);
    return env;
  }, {});
}

function normalizePathRoots(payload: unknown): PathRootsResponse {
  if (!isRecord(payload)) {
    return {
      artifact_roots: [],
      file_roots: [],
      output_roots: [],
      env: {},
      path_separator: null,
      platform: null,
    };
  }

  return {
    artifact_roots: getArrayPayload(payload.artifact_roots, ["roots", "items", "data", "results"])
      .map(normalizeArtifactRoot)
      .filter((root): root is ArtifactRoot => root !== null),
    file_roots: getArrayPayload(payload.file_roots, ["roots", "items", "data", "results"])
      .map(normalizeArtifactRoot)
      .filter((root): root is ArtifactRoot => root !== null),
    output_roots: getArrayPayload(payload.output_roots, ["roots", "items", "data", "results"])
      .map(normalizeArtifactRoot)
      .filter((root): root is ArtifactRoot => root !== null),
    env: normalizePathRootsEnv(payload.env),
    path_separator: typeof payload.path_separator === "string" ? payload.path_separator : null,
    platform: typeof payload.platform === "string" ? payload.platform : null,
  };
}

function getNameFromPath(path: string): string {
  const parts = path.split(/[\\/]+/).filter(Boolean);
  return parts.length > 0 ? parts[parts.length - 1] : path;
}

export function normalizeCommerceArtifact(value: unknown): ArtifactItem | null {
  if (!isRecord(value)) {
    return null;
  }

  const path = value.path;
  if (typeof path !== "string" && typeof path !== "number") {
    return null;
  }

  const normalizedPath = String(path);
  const name = value.name;

  return {
    ...value,
    name: typeof name === "string" && name.trim().length > 0 ? name : getNameFromPath(normalizedPath),
    path: normalizedPath,
    extension: typeof value.extension === "string" ? value.extension : null,
    size_bytes: typeof value.size_bytes === "number" ? value.size_bytes : null,
    modified_at: typeof value.modified_at === "string" ? value.modified_at : null,
    download_url:
      typeof value.download_url === "string" && value.download_url.trim().length > 0
        ? toCommerceArtifactUrl(value.download_url)
        : null,
    read_url:
      typeof value.read_url === "string" && value.read_url.trim().length > 0
        ? toCommerceArtifactUrl(value.read_url)
        : null,
    is_allowed: value.is_allowed === false ? false : true,
    can_read: value.can_read === false ? false : true,
    can_download: value.can_download === false ? false : true,
    warning: typeof value.warning === "string" && value.warning.trim().length > 0 ? value.warning : null,
  };
}

function normalizeArtifactPathValue(value: unknown): ArtifactPayload | string | null {
  if (typeof value === "string") {
    return value;
  }

  if (typeof value === "number") {
    return String(value);
  }

  return normalizeCommerceArtifact(value);
}

function normalizeArtifactList(payload: unknown): ArtifactListResponse {
  const source = isRecord(payload) ? payload : {};
  return {
    root: typeof source.root === "string" ? source.root : null,
    run_id:
      typeof source.run_id === "string" || typeof source.run_id === "number"
        ? source.run_id
        : null,
    observation_batch_id: normalizeNullableId(source.observation_batch_id),
    items: getArrayPayload(payload, ["items", "artifacts", "data", "results"])
      .map(normalizeCommerceArtifact)
      .filter((item): item is ArtifactItem => item !== null),
  };
}

function normalizeArtifactRead(payload: unknown): ArtifactReadResponse {
  if (typeof payload === "string") {
    return {
      path: "",
      content: payload,
    };
  }

  if (!isRecord(payload)) {
    return {
      path: "",
      content: "",
    };
  }

  return {
    ...payload,
    path: typeof payload.path === "string" ? payload.path : "",
    content:
      typeof payload.content === "string"
        ? payload.content
        : typeof payload.text === "string"
          ? payload.text
          : "",
    truncated: typeof payload.truncated === "boolean" ? payload.truncated : null,
    size_bytes: typeof payload.size_bytes === "number" ? payload.size_bytes : null,
    encoding: typeof payload.encoding === "string" ? payload.encoding : null,
  };
}

function normalizeFileList(payload: unknown): FileListResponse {
  if (!isRecord(payload)) {
    return {
      root: "",
      relative_path: "",
      items: [],
    };
  }

  const items = getArrayPayload(payload.items, [])
    .filter(isRecord)
    .map<FileListItem>((item) => ({
      name: typeof item.name === "string" ? item.name : "",
      path: typeof item.path === "string" ? item.path : "",
      type: item.type === "directory" ? "directory" : "file",
      extension: typeof item.extension === "string" ? item.extension : "",
      size_bytes: typeof item.size_bytes === "number" ? item.size_bytes : null,
      modified_at: typeof item.modified_at === "string" ? item.modified_at : null,
    }))
    .filter((item) => item.name.length > 0 && item.path.length > 0);

  return {
    root: typeof payload.root === "string" ? payload.root : "",
    relative_path: typeof payload.relative_path === "string" ? payload.relative_path : "",
    items,
  };
}

function normalizeCsvValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }

  return String(value);
}

function normalizeCsvRead(payload: unknown): ReadCsvFileResponse {
  if (!isRecord(payload)) {
    return {
      path: "",
      filename: "",
      delimiter: ",",
      encoding: null,
      columns: [],
      rows: [],
      returned_rows: 0,
      total_rows: 0,
      size_bytes: null,
      modified_at: null,
    };
  }

  const columns = Array.isArray(payload.columns)
    ? payload.columns
        .filter((column): column is string | number => typeof column === "string" || typeof column === "number")
        .map((column) => String(column))
    : [];
  const rows = Array.isArray(payload.rows)
    ? payload.rows.filter(isRecord).map((row) =>
        columns.reduce<Record<string, string>>((nextRow, column) => {
          nextRow[column] = normalizeCsvValue(row[column]);
          return nextRow;
        }, {}),
      )
    : [];

  return {
    path: typeof payload.path === "string" ? payload.path : "",
    filename: typeof payload.filename === "string" ? payload.filename : "",
    delimiter: typeof payload.delimiter === "string" ? payload.delimiter : ",",
    encoding: typeof payload.encoding === "string" ? payload.encoding : null,
    columns,
    rows,
    returned_rows: toNumber(payload.returned_rows, rows.length),
    total_rows: toNumber(payload.total_rows, rows.length),
    size_bytes: typeof payload.size_bytes === "number" ? payload.size_bytes : null,
    modified_at: typeof payload.modified_at === "string" ? payload.modified_at : null,
  };
}

function normalizeStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value
        .filter((item): item is string | number => typeof item === "string" || typeof item === "number")
        .map((item) => String(item))
    : [];
}

function normalizeFetchStatus(value: unknown): string | null {
  if (typeof value !== "string" || value.trim().length === 0) {
    return null;
  }

  if (value === "fetch_completed") {
    return "succeeded";
  }

  if (value === "fetch_failed") {
    return "failed";
  }

  return value;
}

function normalizeRun(value: unknown): PriceMonitoringRun | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    ...value,
    source_url_coverage: normalizeSourceUrlCoverage(value.source_url_coverage),
    latest_fetch: isRecord(value.latest_fetch) ? normalizeFetchResult(value.latest_fetch) : null,
  } as PriceMonitoringRun;
}

function normalizeRunList(payload: unknown): PriceMonitoringRun[] {
  return getArrayPayload(payload, ["runs", "items", "data", "results"])
    .map(normalizeRun)
    .filter((run): run is PriceMonitoringRun => run !== null);
}

function normalizeReviewItem(value: unknown): PriceMonitoringReviewItem | null {
  if (!isRecord(value) || typeof value.model !== "string") {
    return null;
  }

  return {
    ...value,
    model: value.model,
    warnings: normalizeStringArray(value.warnings),
  } as PriceMonitoringReviewItem;
}

function normalizeReview(payload: unknown): PriceMonitoringReviewResponse {
  if (!isRecord(payload)) {
    return {
      items: [],
    };
  }

  return {
    ...payload,
    run_id: typeof payload.run_id === "string" || typeof payload.run_id === "number" ? payload.run_id : null,
    items: getArrayPayload(payload.items, [])
      .map(normalizeReviewItem)
      .filter((item): item is PriceMonitoringReviewItem => item !== null),
    summary: isRecord(payload.summary) ? (payload.summary as Record<string, number>) : {},
    review_csv_path: normalizeArtifactPathValue(payload.review_csv_path),
    enriched_csv_path: normalizeArtifactPathValue(payload.enriched_csv_path),
  };
}

function normalizeFetchResult(payload: unknown): FetchPriceMonitoringResult {
  if (!isRecord(payload)) {
    return {};
  }
  return {
    ...payload,
    run_id:
      typeof payload.run_id === "string" || typeof payload.run_id === "number"
        ? payload.run_id
        : null,
    execution_id:
      typeof payload.execution_id === "string" || typeof payload.execution_id === "number"
        ? payload.execution_id
        : null,
    status: normalizeFetchStatus(payload.status),
    source:
      typeof payload.source === "string" || payload.source === null
        ? payload.source
        : null,
    catalog_url:
      typeof payload.catalog_url === "string" || payload.catalog_url === null
        ? payload.catalog_url
        : null,
    fetch_input_mode: normalizeNullableString(payload.fetch_input_mode ?? payload.input_mode),
    queued_at:
      typeof payload.queued_at === "string" || payload.queued_at === null
        ? payload.queued_at
        : null,
    started_at:
      typeof payload.started_at === "string" || payload.started_at === null
        ? payload.started_at
        : null,
    completed_at:
      typeof payload.completed_at === "string" || payload.completed_at === null
        ? payload.completed_at
        : null,
    cancelled_at:
      typeof payload.cancelled_at === "string" || payload.cancelled_at === null
        ? payload.cancelled_at
        : null,
    killed_at:
      typeof payload.killed_at === "string" || payload.killed_at === null
        ? payload.killed_at
        : null,
    cancel_reason:
      typeof payload.cancel_reason === "string" || payload.cancel_reason === null
        ? payload.cancel_reason
        : null,
    killed_reason:
      typeof payload.killed_reason === "string" || payload.killed_reason === null
        ? payload.killed_reason
        : null,
    termination_mode:
      typeof payload.termination_mode === "string" || payload.termination_mode === null
        ? payload.termination_mode
        : null,
    terminate_sent_at:
      typeof payload.terminate_sent_at === "string" || payload.terminate_sent_at === null
        ? payload.terminate_sent_at
        : null,
    kill_sent_at:
      typeof payload.kill_sent_at === "string" || payload.kill_sent_at === null
        ? payload.kill_sent_at
        : null,
    exit_code:
      typeof payload.exit_code === "number" || payload.exit_code === null ? payload.exit_code : null,
    parent_process_id:
      typeof payload.parent_process_id === "number" || payload.parent_process_id === null
        ? payload.parent_process_id
        : null,
    process_id:
      typeof payload.process_id === "number" || payload.process_id === null
        ? payload.process_id
        : null,
    process_group_id:
      typeof payload.process_group_id === "number" || payload.process_group_id === null
        ? payload.process_group_id
        : null,
    command: Array.isArray(payload.command) ? normalizeStringArray(payload.command) : null,
    artifacts_are_diagnostic:
      typeof payload.artifacts_are_diagnostic === "boolean" || payload.artifacts_are_diagnostic === null
        ? payload.artifacts_are_diagnostic
        : null,
    artifact_warning:
      typeof payload.artifact_warning === "string" || payload.artifact_warning === null
        ? payload.artifact_warning
        : null,
    execution_type:
      typeof payload.execution_type === "string" || payload.execution_type === null
        ? payload.execution_type
        : null,
    queue_position:
      typeof payload.queue_position === "number" || payload.queue_position === null
        ? payload.queue_position
        : null,
    stale:
      typeof payload.stale === "boolean" || payload.stale === null
        ? payload.stale
        : null,
    input_csv_path: normalizeArtifactPathValue(payload.input_csv_path),
    enriched_csv_path: normalizeArtifactPathValue(payload.enriched_csv_path),
    fetch_summary_path: normalizeArtifactPathValue(payload.fetch_summary_path),
    fetch_result_path: normalizeArtifactPathValue(payload.fetch_result_path),
    execution_path: normalizeArtifactPathValue(payload.execution_path),
    log_path: normalizeArtifactPathValue(payload.log_path),
    error:
      typeof payload.error === "string" || payload.error === null
        ? payload.error
        : null,
    warnings: normalizeStringArray(payload.warnings),
    observation_count: normalizeOptionalNumber(payload.observation_count) ?? undefined,
    appended_observation_count:
      normalizeOptionalNumber(payload.appended_observation_count ?? payload.observation_count) ?? undefined,
    prior_observation_count:
      normalizeOptionalNumber(
        payload.prior_observation_count ??
          payload.retained_observation_count ??
          payload.previous_observation_count ??
          payload.replaced_observation_count,
      ) ?? undefined,
    retained_observation_count:
      normalizeOptionalNumber(payload.retained_observation_count ?? payload.prior_observation_count) ?? undefined,
    replaced_observation_count: normalizeOptionalNumber(payload.replaced_observation_count) ?? undefined,
    catalog_snapshot_count: normalizeOptionalNumber(payload.catalog_snapshot_count),
    matched_observation_count: normalizeOptionalNumber(payload.matched_observation_count) ?? undefined,
    unmatched_observation_count: normalizeOptionalNumber(payload.unmatched_observation_count) ?? undefined,
    was_refetch: typeof payload.was_refetch === "boolean" ? payload.was_refetch : undefined,
    fetch_attempt: normalizeOptionalNumber(payload.fetch_attempt) ?? undefined,
    observation_batch_id: normalizeNullableId(payload.observation_batch_id),
    observation_history_count: normalizeOptionalNumber(payload.observation_history_count) ?? undefined,
    persistence_warnings: normalizeStringArray(payload.persistence_warnings),
    alert_warnings: normalizeStringArray(payload.alert_warnings),
    artifacts: getArrayPayload(payload.artifacts, ["items", "artifacts", "data", "results"])
      .map(normalizeCommerceArtifact)
      .filter((item): item is ArtifactItem => item !== null),
  };
}

function normalizeFetchLogs(payload: unknown): PriceMonitoringFetchLogsResponse {
  if (!isRecord(payload)) {
    return {
      lines: normalizeStringArray(payload),
    };
  }

  return {
    run_id:
      typeof payload.run_id === "string" || typeof payload.run_id === "number"
        ? payload.run_id
        : null,
    execution_id:
      typeof payload.execution_id === "string" || typeof payload.execution_id === "number"
        ? payload.execution_id
        : null,
    lines: normalizeStringArray(payload.lines ?? payload.logs ?? payload.items),
  };
}

function normalizeDbStatus(payload: unknown): PriceMonitoringDbStatus {
  if (!isRecord(payload)) {
    return {
      configured: false,
      reachable: false,
      price_monitoring_requires_database: true,
      ready_for_price_monitoring: false,
      blocking_reasons: ["Database status response was not an object."],
      non_db_workflows_available: true,
      required_for: ["price-monitoring"],
      dialect: null,
      error: null,
    };
  }

  const configured = payload.configured === true;
  const reachable = payload.reachable === true;
  const requiredTablesPresent =
    typeof payload.required_tables_present === "boolean" || payload.required_tables_present === null
      ? payload.required_tables_present
      : null;
  const alembicUpToDate =
    typeof payload.alembic_up_to_date === "boolean" || payload.alembic_up_to_date === null
      ? payload.alembic_up_to_date
      : null;
  const inferredReady = configured && reachable && requiredTablesPresent !== false && alembicUpToDate !== false;
  const readyForPriceMonitoring =
    typeof payload.ready_for_price_monitoring === "boolean"
      ? payload.ready_for_price_monitoring
      : inferredReady;

  return {
    ...payload,
    configured,
    reachable,
    price_monitoring_requires_database:
      typeof payload.price_monitoring_requires_database === "boolean" ||
      payload.price_monitoring_requires_database === null
        ? payload.price_monitoring_requires_database
        : true,
    ready_for_price_monitoring: readyForPriceMonitoring,
    blocking_reasons:
      Array.isArray(payload.blocking_reasons)
        ? normalizeStringArray(payload.blocking_reasons)
        : payload.blocking_reasons === null
          ? null
          : readyForPriceMonitoring
            ? []
            : undefined,
    non_db_workflows_available:
      typeof payload.non_db_workflows_available === "boolean" || payload.non_db_workflows_available === null
        ? payload.non_db_workflows_available
        : true,
    required_for:
      Array.isArray(payload.required_for)
        ? normalizeStringArray(payload.required_for)
        : payload.required_for === null
          ? null
          : ["price-monitoring"],
    dialect:
      typeof payload.dialect === "string" || payload.dialect === null
        ? payload.dialect
        : null,
    error:
      typeof payload.error === "string" || payload.error === null
        ? payload.error
        : null,
    required_tables_present: requiredTablesPresent,
    alembic_up_to_date: alembicUpToDate,
    alembic_current_revision:
      typeof payload.alembic_current_revision === "string" || payload.alembic_current_revision === null
        ? payload.alembic_current_revision
        : null,
    alembic_head_revision:
      typeof payload.alembic_head_revision === "string" || payload.alembic_head_revision === null
        ? payload.alembic_head_revision
        : null,
    setup_hints:
      Array.isArray(payload.setup_hints)
        ? normalizeStringArray(payload.setup_hints)
        : payload.setup_hints === null
          ? null
          : undefined,
  };
}

function normalizePriceObservation(value: unknown): PriceObservation | null {
  if (!isRecord(value)) {
    return null;
  }

  const rawObservation = isRecord(value.raw_observation) ? value.raw_observation : null;
  const rawPersistence = isRecord(rawObservation?.persistence) ? rawObservation.persistence : {};

  return {
    ...value,
    product_id: normalizeNullableId(value.product_id),
    product_source_id: normalizeNullableId(value.product_source_id),
    source_url_id: normalizeNullableId(value.source_url_id),
    vendor_id: normalizeNullableId(value.vendor_id),
    source_capture_snapshot_id: normalizeNullableId(value.source_capture_snapshot_id),
    execution_id: normalizeNullableId(value.execution_id ?? rawPersistence.execution_id),
    fetch_attempt: normalizeNullableId(value.fetch_attempt ?? rawPersistence.fetch_attempt),
    was_refetch:
      typeof value.was_refetch === "boolean"
        ? value.was_refetch
        : typeof rawPersistence.was_refetch === "boolean"
          ? rawPersistence.was_refetch
          : null,
    observation_batch_id: normalizeNullableId(value.observation_batch_id ?? rawPersistence.observation_batch_id),
    artifact_ref: normalizeArtifactPathValue(value.artifact_ref),
    artifact_refs: getArrayPayload(value.artifact_refs, ["items", "artifacts", "data", "results"])
      .map(normalizeCommerceArtifact)
      .filter((item): item is ArtifactItem => item !== null),
    snapshot_ref: normalizeArtifactPathValue(value.snapshot_ref),
    full_snapshot_ref: normalizeArtifactPathValue(value.full_snapshot_ref),
    raw_observation: rawObservation,
  } as PriceObservation;
}

function normalizePriceObservationsResponse(payload: unknown): PriceObservationsResponse {
  const source = isRecord(payload) ? payload : {};
  const items = getArrayPayload(payload, ["items", "observations", "data", "results"])
    .map(normalizePriceObservation)
    .filter((item): item is PriceObservation => item !== null);

  return {
    items,
    limit: toNumber(source.limit, items.length),
    offset: toNumber(source.offset, 0),
    count: toNumber(source.count, items.length),
  };
}

function normalizeRunPriceObservationsResponse(payload: unknown): RunPriceObservationsResponse {
  const source = isRecord(payload) ? payload : {};
  const response = normalizePriceObservationsResponse(payload);

  return {
    run_id:
      typeof source.run_id === "string" || typeof source.run_id === "number"
        ? source.run_id
        : null,
    items: response.items,
    count: response.count,
    matched_count: toNumber(source.matched_count, response.items.filter((item) => item.is_matched === true).length),
    unmatched_count: toNumber(
      source.unmatched_count,
      response.items.filter((item) => item.is_matched !== true && item.match_status !== "matched").length,
    ),
  };
}

function normalizeCatalogSnapshot(value: unknown): CatalogSnapshot | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    ...value,
    raw_catalog_row: isRecord(value.raw_catalog_row) ? value.raw_catalog_row : null,
  } as CatalogSnapshot;
}

function normalizeCatalogSnapshotResponse(payload: unknown): CatalogSnapshotResponse {
  const source = isRecord(payload) ? payload : {};
  const items = getArrayPayload(payload, ["items", "catalog_snapshot", "data", "results"])
    .map(normalizeCatalogSnapshot)
    .filter((item): item is CatalogSnapshot => item !== null);

  return {
    run_id:
      typeof source.run_id === "string" || typeof source.run_id === "number"
        ? source.run_id
        : null,
    items,
    count: toNumber(source.count, items.length),
  };
}

function normalizePriceHistoryResponse(payload: unknown): PriceHistoryResponse {
  const source = isRecord(payload) ? payload : {};
  const response = normalizePriceObservationsResponse(payload);

  return {
    product_id:
      typeof source.product_id === "string" || typeof source.product_id === "number"
        ? source.product_id
        : null,
    model: typeof source.model === "string" ? source.model : null,
    catalog_source: typeof source.catalog_source === "string" ? source.catalog_source : null,
    items: response.items,
    count: response.count,
  };
}

function normalizeNullableString(value: unknown): string | null {
  return typeof value === "string" || typeof value === "number" ? String(value) : null;
}

function normalizeNullableId(value: unknown): string | number | null {
  return typeof value === "string" || typeof value === "number" ? value : null;
}

function normalizeAlertRule(value: unknown): AlertRule | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    ...value,
    id: typeof value.id === "string" || typeof value.id === "number" ? value.id : undefined,
    name: typeof value.name === "string" || value.name === null ? value.name : null,
    rule_type:
      typeof value.rule_type === "string" ? value.rule_type : "competitor_below_own_price",
    product_id: normalizeNullableId(value.product_id),
    catalog_source: normalizeNullableString(value.catalog_source),
    model: normalizeNullableString(value.model),
    mpn: normalizeNullableString(value.mpn),
    threshold_amount:
      typeof value.threshold_amount === "string" || typeof value.threshold_amount === "number"
        ? value.threshold_amount
        : null,
    threshold_percent:
      typeof value.threshold_percent === "string" || typeof value.threshold_percent === "number"
        ? value.threshold_percent
        : null,
    active: typeof value.active === "boolean" ? value.active : null,
    created_at: normalizeNullableString(value.created_at),
    updated_at: normalizeNullableString(value.updated_at),
  };
}

function normalizeAlertRulesResponse(payload: unknown): AlertRulesResponse {
  const source = isRecord(payload) ? payload : {};
  const items = getArrayPayload(payload, ["items", "rules", "data", "results"])
    .map(normalizeAlertRule)
    .filter((item): item is AlertRule => item !== null);

  return {
    items,
    count: toNumber(source.count, items.length),
    limit: toNumber(source.limit, items.length || 100),
    offset: toNumber(source.offset, 0),
  };
}

function normalizeAlertEvent(value: unknown): AlertEvent | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    ...value,
    id: typeof value.id === "string" || typeof value.id === "number" ? value.id : undefined,
    alert_rule_id: normalizeNullableId(value.alert_rule_id),
    monitoring_run_id: normalizeNullableId(value.monitoring_run_id),
    price_observation_id: normalizeNullableId(value.price_observation_id),
    product_id: normalizeNullableId(value.product_id),
    run_id: normalizeNullableId(value.run_id),
    catalog_source: normalizeNullableString(value.catalog_source),
    model: normalizeNullableString(value.model),
    mpn: normalizeNullableString(value.mpn),
    source: normalizeNullableString(value.source),
    competitor_name: normalizeNullableString(value.competitor_name),
    competitor_price:
      typeof value.competitor_price === "string" || typeof value.competitor_price === "number"
        ? value.competitor_price
        : null,
    own_price:
      typeof value.own_price === "string" || typeof value.own_price === "number"
        ? value.own_price
        : null,
    price_delta:
      typeof value.price_delta === "string" || typeof value.price_delta === "number"
        ? value.price_delta
        : null,
    price_delta_percent:
      typeof value.price_delta_percent === "string" || typeof value.price_delta_percent === "number"
        ? value.price_delta_percent
        : null,
    severity: normalizeNullableString(value.severity),
    status: normalizeNullableString(value.status),
    message: normalizeNullableString(value.message),
    dedupe_key: normalizeNullableString(value.dedupe_key),
    triggered_at: normalizeNullableString(value.triggered_at),
    acknowledged_at: normalizeNullableString(value.acknowledged_at),
    acknowledged_by: normalizeNullableString(value.acknowledged_by),
    resolved_at: normalizeNullableString(value.resolved_at),
    resolved_by: normalizeNullableString(value.resolved_by),
    raw_context: isRecord(value.raw_context) ? value.raw_context : null,
    created_at: normalizeNullableString(value.created_at),
    updated_at: normalizeNullableString(value.updated_at),
  };
}

function normalizeAlertEventsResponse(payload: unknown): AlertEventsResponse {
  const source = isRecord(payload) ? payload : {};
  const items = getArrayPayload(payload, ["items", "events", "data", "results"])
    .map(normalizeAlertEvent)
    .filter((item): item is AlertEvent => item !== null);

  return {
    items,
    count: toNumber(source.count, items.length),
    limit: toNumber(source.limit, items.length || 100),
    offset: toNumber(source.offset, 0),
  };
}

function normalizeEvaluateAlertsResponse(payload: unknown): EvaluateAlertsResponse {
  if (!isRecord(payload)) {
    return {
      warnings: [],
    };
  }

  return {
    ...payload,
    run_id:
      typeof payload.run_id === "string" || typeof payload.run_id === "number"
        ? payload.run_id
        : null,
    status: typeof payload.status === "string" ? payload.status : null,
    evaluated_rule_count: toNumber(payload.evaluated_rule_count, 0),
    evaluated_observation_count: toNumber(payload.evaluated_observation_count, 0),
    created_event_count: toNumber(payload.created_event_count, 0),
    duplicate_event_count: toNumber(payload.duplicate_event_count, 0),
    skipped_count: toNumber(payload.skipped_count, 0),
    warnings: normalizeStringArray(payload.warnings),
  };
}

function normalizeApplyReviewActionsResult(payload: unknown): ApplyPriceMonitoringReviewActionsResult {
  if (!isRecord(payload)) {
    return {};
  }

  return {
    ...payload,
    review_csv_path: normalizeArtifactPathValue(payload.review_csv_path),
    review_actions_path: normalizeArtifactPathValue(payload.review_actions_path),
    summary: isRecord(payload.summary) ? payload.summary : undefined,
  } as ApplyPriceMonitoringReviewActionsResult;
}

function normalizeExportPriceUpdateResult(payload: unknown): ExportPriceMonitoringPriceUpdateResult {
  if (!isRecord(payload)) {
    return {};
  }

  return {
    ...payload,
    output_path: normalizeArtifactPathValue(payload.output_path),
    columns: normalizeStringArray(payload.columns),
  };
}

function isArtifactPathForbidden(path: string, status: number): boolean {
  if (status !== 403) {
    return false;
  }

  return (
    path.startsWith("/artifacts/") ||
    path.includes("/review") ||
    path.includes("/export-price-update")
  );
}

async function request<T>(path: string, options: CommerceRequestOptions = {}): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${commerceApiBaseUrl}${path}`, {
      ...options,
      headers: buildHeaders(options),
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch (error) {
    const rawMessage = error instanceof Error ? error.message : String(error);
    throw new CommerceApiError(
      `Commerce API unreachable at ${path}. Start ecommerce-api on 127.0.0.1:8001.`,
      0,
      rawMessage,
      path,
    );
  }

  const payload = await parseResponse(response);

  if (!response.ok) {
    const backendMessage = getPayloadMessage(payload) ?? response.statusText;
    const pathHint = isArtifactPathForbidden(path, response.status)
      ? " Path is outside configured artifact roots. Add the directory to ECOMMERCE_ARTIFACT_ROOTS and restart the backend."
      : "";
    const setupHint =
      response.status === 404 && path.startsWith("/catalog/")
        ? " If the API is running, check PostgreSQL configuration, run alembic upgrade head, and import sourceCata.csv with python -m ecommerce.jobs.ingest_catalog."
        : "";
    const dbHint =
      response.status === 503 && path.startsWith("/price-monitoring/")
        ? " PostgreSQL is required for Price Monitoring; CSV/Bridge, files, paths, artifacts, and general commerce health may still be available."
        : response.status === 503 && path.startsWith("/catalog/")
          ? " Catalog database/import required. Configure ECOMMERCE_DATABASE_URL, run alembic upgrade head, run python -m ecommerce.jobs.ingest_catalog, then reload the Catalog page. CSV/Bridge, files, paths, artifacts, and general commerce health may still be available."
        : "";
    const message = `Commerce API ${response.status} at ${path}: ${backendMessage}${pathHint}${setupHint}${dbHint}`;
    throw new CommerceApiError(message, response.status, payload, path);
  }

  return payload as T;
}

function normalizeCatalogCategoryOptions(payload: unknown): CatalogCategoryOption[] {
  const list = getArrayPayload(payload, ["items", "categories", "data", "results"]);

  return list
    .map<CatalogCategoryOption | null>((item) => {
      if (typeof item === "string" || typeof item === "number") {
        return { category: String(item), count: null };
      }

      if (!isRecord(item)) {
        return null;
      }

      const category = item.category ?? item.name ?? item.value;
      if (typeof category !== "string" && typeof category !== "number") {
        return null;
      }

      return {
        category: String(category),
        count: typeof item.count === "number" ? item.count : null,
      };
    })
    .filter((item): item is CatalogCategoryOption => item !== null && item.category.length > 0);
}

function normalizeCatalogSubCategoryNode(value: unknown): CatalogSubCategoryNode | null {
  if (!isRecord(value)) {
    return null;
  }

  const subCategory = value.sub_category ?? value.name ?? value.value ?? "";
  if (typeof subCategory !== "string" && typeof subCategory !== "number") {
    return null;
  }

  return {
    sub_category: String(subCategory),
    count: typeof value.count === "number" ? value.count : null,
    raw_categories: normalizeStringArray(value.raw_categories),
  };
}

function normalizeCatalogCategoryNode(value: unknown): CatalogCategoryNode | null {
  if (!isRecord(value)) {
    return null;
  }

  const categoryName = value.category_name ?? value.category ?? value.name ?? value.value;
  if (typeof categoryName !== "string" && typeof categoryName !== "number") {
    return null;
  }

  return {
    category_name: String(categoryName),
    count: typeof value.count === "number" ? value.count : null,
    sub_categories: getArrayPayload(value.sub_categories, ["items", "data", "results"])
      .map(normalizeCatalogSubCategoryNode)
      .filter((item): item is CatalogSubCategoryNode => item !== null),
  };
}

function normalizeCatalogFamilyNode(value: unknown): CatalogFamilyNode | null {
  if (!isRecord(value)) {
    return null;
  }

  const family = value.family ?? value.name ?? value.value;
  if (typeof family !== "string" && typeof family !== "number") {
    return null;
  }

  return {
    family: String(family),
    count: typeof value.count === "number" ? value.count : null,
    categories: getArrayPayload(value.categories, ["items", "data", "results"])
      .map(normalizeCatalogCategoryNode)
      .filter((item): item is CatalogCategoryNode => item !== null),
  };
}

function normalizeCatalogCategoryHierarchy(payload: unknown): CatalogCategoryHierarchyResponse {
  return {
    items: getArrayPayload(payload, ["items", "families", "data", "results"])
      .map(normalizeCatalogFamilyNode)
      .filter((item): item is CatalogFamilyNode => item !== null && item.family.trim().length > 0),
  };
}

function normalizeCatalogBrandOptions(payload: unknown): CatalogBrandOption[] {
  const list = getArrayPayload(payload, ["items", "brands", "manufacturers", "data", "results"]);

  return list
    .map<CatalogBrandOption | null>((item) => {
      if (typeof item === "string" || typeof item === "number") {
        return { manufacturer: String(item), count: null };
      }

      if (!isRecord(item)) {
        return null;
      }

      const manufacturer = item.manufacturer ?? item.brand ?? item.name ?? item.value;
      if (typeof manufacturer !== "string" && typeof manufacturer !== "number") {
        return null;
      }

      return {
        manufacturer: String(manufacturer),
        count: typeof item.count === "number" ? item.count : null,
      };
    })
    .filter((item): item is CatalogBrandOption => item !== null && item.manufacturer.length > 0);
}

export const commerceClient = {
  commerceApiBaseUrl,

  getCommerceHealth(signal?: AbortSignal): Promise<unknown> {
    return request<unknown>("/health", { signal });
  },

  async listCatalogProducts(
    params: CatalogProductsParams = {},
    signal?: AbortSignal,
  ): Promise<CatalogProductsResponse> {
    return normalizeProductsResponse(
      await request<unknown>(appendQuery("/catalog/products", params as QueryParams), { signal }),
    );
  },

  async listCatalogCategories(signal?: AbortSignal): Promise<string[]> {
    const payload = await request<unknown>("/catalog/categories", { signal });
    const options = normalizeCatalogCategoryOptions(payload);
    return options.length > 0 ? options.map((item) => item.category) : normalizeStringList(payload);
  },

  async listCatalogBrands(signal?: AbortSignal): Promise<string[]> {
    const payload = await request<unknown>("/catalog/brands", { signal });
    const options = normalizeCatalogBrandOptions(payload);
    return options.length > 0 ? options.map((item) => item.manufacturer) : normalizeStringList(payload);
  },

  async listCatalogCategoryOptions(signal?: AbortSignal): Promise<CatalogCategoryOption[]> {
    return normalizeCatalogCategoryOptions(await request<unknown>("/catalog/categories", { signal }));
  },

  async getCatalogCategoryHierarchy(signal?: AbortSignal): Promise<CatalogCategoryHierarchyResponse> {
    return normalizeCatalogCategoryHierarchy(
      await request<unknown>("/catalog/category-hierarchy", { signal }),
    );
  },

  async listCatalogBrandOptions(signal?: AbortSignal): Promise<CatalogBrandOption[]> {
    return normalizeCatalogBrandOptions(await request<unknown>("/catalog/brands", { signal }));
  },

  async getCatalogSummary(signal?: AbortSignal): Promise<CatalogSummary> {
    const summary = await request<unknown>("/catalog/summary", { signal });
    return isRecord(summary) ? summary : {};
  },

  async listCatalogProductSourceUrls(
    catalogProductId: string | number,
    signal?: AbortSignal,
  ): Promise<SourceUrlListResponse> {
    return normalizeSourceUrlList(
      await request<unknown>(
        `/catalog/products/${encodeURIComponent(String(catalogProductId))}/source-urls`,
        { signal },
      ),
    );
  },

  async createCatalogProductSourceUrl(
    catalogProductId: string | number,
    body: SourceUrlCreateBody,
    signal?: AbortSignal,
  ): Promise<SourceUrl> {
    return (
      normalizeSourceUrl(
        await request<unknown>(
          `/catalog/products/${encodeURIComponent(String(catalogProductId))}/source-urls`,
          {
            method: "POST",
            body,
            signal,
          },
        ),
      ) ?? {
        url: body.url,
        status: "active",
        url_type: body.url_type ?? "manual",
      }
    );
  },

  async updateCatalogSourceUrl(
    sourceUrlId: string | number,
    body: SourceUrlUpdateBody,
    signal?: AbortSignal,
  ): Promise<SourceUrl> {
    return (
      normalizeSourceUrl(
        await request<unknown>(
          `/catalog/source-urls/${encodeURIComponent(String(sourceUrlId))}`,
          {
            method: "PATCH",
            body,
            signal,
          },
        ),
      ) ?? {
        url: body.url ?? "",
        status: body.status ?? "active",
        url_type: "manual",
      }
    );
  },

  async validateCatalogSourceUrl(
    sourceUrlId: string | number,
    signal?: AbortSignal,
  ): Promise<SourceUrlValidationResponse> {
    return normalizeSourceUrlValidation(
      await request<unknown>(
        `/catalog/source-urls/${encodeURIComponent(String(sourceUrlId))}/validate`,
        {
          method: "POST",
          signal,
        },
      ),
    );
  },

  async getSourceUrlSummary(signal?: AbortSignal): Promise<SourceUrlSummaryResponse> {
    return {
      ...normalizeSourceUrlSummary(
        await request<unknown>("/catalog/source-urls/summary", { signal }),
      ),
      summary_source: "catalog",
    };
  },

  async getVendorSourceUrlSummary(signal?: AbortSignal): Promise<SourceUrlSummaryResponse> {
    return {
      ...normalizeSourceUrlSummary(
        await request<unknown>("/vendor-sources/source-urls/summary", { signal }),
      ),
      summary_source: "vendor-sources",
    };
  },

  async listVendorSources(signal?: AbortSignal): Promise<VendorSourceCapability[]> {
    return normalizeVendorSourceCapabilityList(
      await request<unknown>("/vendor-sources/sources", { signal }),
    );
  },

  async createSourceUrlAgentRun(
    body: SourceUrlAgentRunRequest,
    signal?: AbortSignal,
  ): Promise<SourceUrlAgentRun> {
    return (
      normalizeSourceUrlAgentRun(
        await request<unknown>("/vendor-sources/agent/runs", {
          method: "POST",
          body,
          signal,
        }),
      ) ?? {}
    );
  },

  async listSourceUrlAgentRuns(signal?: AbortSignal): Promise<SourceUrlAgentRun[]> {
    return normalizeSourceUrlAgentRunList(
      await request<unknown>("/vendor-sources/agent/runs", { signal }),
    );
  },

  async getSourceUrlAgentRun(
    runId: string | number,
    signal?: AbortSignal,
  ): Promise<SourceUrlAgentRun> {
    return (
      normalizeSourceUrlAgentRun(
        await request<unknown>(
          `/vendor-sources/agent/runs/${encodeURIComponent(String(runId))}`,
          { signal },
        ),
      ) ?? {}
    );
  },

  async listSourceUrlAgentRunArtifacts(
    runId: string | number,
    signal?: AbortSignal,
  ): Promise<SourceUrlAgentRunArtifactsResponse> {
    return normalizeSourceUrlAgentRunArtifacts(
      await request<unknown>(
        `/vendor-sources/agent/runs/${encodeURIComponent(String(runId))}/artifacts`,
        { signal },
      ),
    );
  },

  async createVendorSourceCaptureRun(
    body: VendorSourceCaptureRunRequest,
    signal?: AbortSignal,
  ): Promise<VendorSourceCaptureRun> {
    return (
      normalizeVendorSourceCaptureRun(
        await request<unknown>("/vendor-sources/captures/runs", {
          method: "POST",
          body,
          signal,
        }),
      ) ?? {}
    );
  },

  async listVendorSourceCaptureRuns(signal?: AbortSignal): Promise<VendorSourceCaptureRun[]> {
    return normalizeVendorSourceCaptureRunList(
      await request<unknown>("/vendor-sources/captures/runs", { signal }),
    );
  },

  async getVendorSourceCaptureRun(
    runId: string | number,
    signal?: AbortSignal,
  ): Promise<VendorSourceCaptureRun> {
    return (
      normalizeVendorSourceCaptureRun(
        await request<unknown>(
          `/vendor-sources/captures/runs/${encodeURIComponent(String(runId))}`,
          { signal },
        ),
      ) ?? {}
    );
  },

  async listVendorSourceCaptureRunArtifacts(
    runId: string | number,
    signal?: AbortSignal,
  ): Promise<VendorSourceCaptureRunArtifactsResponse> {
    return normalizeVendorSourceCaptureRunArtifacts(
      await request<unknown>(
        `/vendor-sources/captures/runs/${encodeURIComponent(String(runId))}/artifacts`,
        { signal },
      ),
    );
  },

  async listSourceUrlCandidates(
    params: SourceUrlCandidateListParams = {},
    signal?: AbortSignal,
  ): Promise<SourceUrlCandidateListResponse> {
    return normalizeSourceUrlCandidateList(
      await request<unknown>(
        appendQuery("/vendor-sources/candidates", params as QueryParams),
        { signal },
      ),
    );
  },

  async getSourceUrlCandidateReviewLayout(
    userKey = "default",
    signal?: AbortSignal,
  ): Promise<SourceUrlCandidateReviewLayout> {
    return normalizeSourceUrlCandidateReviewLayout(
      await request<unknown>(
        appendQuery("/vendor-sources/candidates/review-layout", {
          user_key: userKey,
        }),
        { signal },
      ),
    );
  },

  async updateSourceUrlCandidateReviewLayout(
    body: SourceUrlCandidateReviewLayout,
    signal?: AbortSignal,
  ): Promise<SourceUrlCandidateReviewLayout> {
    return normalizeSourceUrlCandidateReviewLayout(
      await request<unknown>("/vendor-sources/candidates/review-layout", {
        method: "PUT",
        body,
        signal,
      }),
    );
  },

  async resetSourceUrlCandidateReviewLayout(
    userKey = "default",
    signal?: AbortSignal,
  ): Promise<SourceUrlCandidateReviewLayout> {
    return normalizeSourceUrlCandidateReviewLayout(
      await request<unknown>(
        appendQuery("/vendor-sources/candidates/review-layout/reset", {
          user_key: userKey,
        }),
        {
          method: "POST",
          signal,
        },
      ),
    );
  },

  async getSourceUrlCandidate(
    candidateId: string | number,
    signal?: AbortSignal,
  ): Promise<SourceUrlCandidate> {
    return normalizeSourceUrlCandidateDetail(
      await request<unknown>(
        `/vendor-sources/candidates/${encodeURIComponent(String(candidateId))}`,
        { signal },
      ),
    );
  },

  async reviewSourceUrlCandidate(
    candidateId: string | number,
    body: SourceUrlCandidateReviewBody,
    signal?: AbortSignal,
  ): Promise<SourceUrlCandidate> {
    return (
      normalizeSourceUrlCandidate(
        await request<unknown>(
          `/vendor-sources/candidates/${encodeURIComponent(String(candidateId))}/review`,
          {
            method: "PATCH",
            body,
            signal,
          },
        ),
      ) ?? { id: candidateId, status: body.decision === "accept" ? "accepted" : "needs_review" }
    );
  },

  async runSkroutzNetworkDiagnostic(
    sourceUrlId: string | number,
    body: { headed?: boolean; timeout_seconds?: number } = {},
    signal?: AbortSignal,
  ): Promise<SkroutzNetworkDiagnosticSummary> {
    return normalizeSkroutzNetworkDiagnosticSummary(
      await request<unknown>(
        `/vendor-sources/source-urls/${encodeURIComponent(String(sourceUrlId))}/diagnostics/skroutz-network`,
        {
          method: "POST",
          body,
          signal,
        },
      ),
    );
  },

  async getLatestSkroutzNetworkDiagnostic(
    sourceUrlId: string | number,
    signal?: AbortSignal,
  ): Promise<SkroutzNetworkDiagnosticReport> {
    return normalizeSkroutzNetworkDiagnosticReport(
      await request<unknown>(
        `/vendor-sources/source-urls/${encodeURIComponent(String(sourceUrlId))}/diagnostics/skroutz-network/latest`,
        { signal },
      ),
    );
  },

  async previewSourceUrlImport(
    body: SourceUrlImportRequest,
    signal?: AbortSignal,
  ): Promise<SourceUrlImportResponse> {
    return normalizeSourceUrlImportResponse(
      await request<unknown>("/catalog/source-urls/import/preview", {
        method: "POST",
        body,
        signal,
      }),
    );
  },

  async applySourceUrlImport(
    body: SourceUrlImportRequest,
    signal?: AbortSignal,
  ): Promise<SourceUrlImportResponse> {
    return normalizeSourceUrlImportResponse(
      await request<unknown>("/catalog/source-urls/import/apply", {
        method: "POST",
        body,
        signal,
      }),
    );
  },

  async previewProductFactoryHandoffImport(
    body: ProductFactoryHandoffImportRequest,
    signal?: AbortSignal,
  ): Promise<SourceUrlImportResponse> {
    return normalizeSourceUrlImportResponse(
      await request<unknown>("/catalog/source-urls/import/product-factory/preview", {
        method: "POST",
        body,
        signal,
      }),
    );
  },

  async applyProductFactoryHandoffImport(
    body: ProductFactoryHandoffImportRequest,
    signal?: AbortSignal,
  ): Promise<SourceUrlImportResponse> {
    return normalizeSourceUrlImportResponse(
      await request<unknown>("/catalog/source-urls/import/product-factory/apply", {
        method: "POST",
        body,
        signal,
      }),
    );
  },

  async getArtifactRoots(signal?: AbortSignal): Promise<ArtifactRoot[]> {
    return normalizeArtifactRoots(await request<unknown>("/artifacts/roots", { signal }));
  },

  async getPathRoots(signal?: AbortSignal): Promise<PathRootsResponse> {
    return normalizePathRoots(await request<unknown>("/paths/roots", { signal }));
  },

  async listBridgeRunArtifacts(
    runId: string,
    signal?: AbortSignal,
  ): Promise<ArtifactListResponse> {
    return normalizeArtifactList(
      await request<unknown>(`/artifacts/bridge/runs/${encodeURIComponent(runId)}`, {
        signal,
      }),
    );
  },

  async listPriceMonitoringRunArtifacts(
    runId: string,
    signal?: AbortSignal,
  ): Promise<ArtifactListResponse> {
    return normalizeArtifactList(
      await request<unknown>(`/artifacts/price-monitoring/runs/${encodeURIComponent(runId)}`, {
        signal,
      }),
    );
  },

  async readArtifact(
    path: string,
    maxBytes?: number,
    signal?: AbortSignal,
  ): Promise<ArtifactReadResponse> {
    return normalizeArtifactRead(
      await request<unknown>(
        appendQuery("/artifacts/read", {
          path,
          max_bytes: maxBytes,
        }),
        { signal },
      ),
    );
  },

  getArtifactDownloadUrl(path: string): string {
    return toCommerceArtifactUrl(path);
  },

  async previewPriceMonitoringSelection(
    body: PriceMonitoringSelectionBody,
    signal?: AbortSignal,
  ): Promise<PriceMonitoringSelectionResult> {
    return normalizeSelectionResult(
      await request<unknown>("/price-monitoring/selection/preview", {
        method: "POST",
        body,
        signal,
      }),
    );
  },

  async createPriceMonitoringRun(
    body: PriceMonitoringSelectionBody,
    signal?: AbortSignal,
  ): Promise<PriceMonitoringSelectionResult> {
    return normalizeSelectionResult(
      await request<unknown>("/price-monitoring/runs", {
        method: "POST",
        body,
        signal,
      }),
    );
  },

  async listPriceMonitoringRuns(signal?: AbortSignal): Promise<PriceMonitoringRun[]> {
    return normalizeRunList(await request<unknown>("/price-monitoring/runs", { signal }));
  },

  async getPriceMonitoringRun(
    runId: string,
    signal?: AbortSignal,
  ): Promise<PriceMonitoringRun> {
    const run = normalizeRun(
      await request<unknown>(`/price-monitoring/runs/${encodeURIComponent(runId)}`, { signal }),
    );
    return run ?? {};
  },

  async fetchPriceMonitoringRun(
    runId: string,
    body: FetchPriceMonitoringBody,
    signal?: AbortSignal,
  ): Promise<FetchPriceMonitoringResult> {
    return normalizeFetchResult(
      await request<unknown>(`/price-monitoring/runs/${encodeURIComponent(runId)}/fetch`, {
        method: "POST",
        body,
        signal,
      }),
    );
  },

  async getPriceMonitoringFetchResult(
    runId: string,
    signal?: AbortSignal,
  ): Promise<FetchPriceMonitoringResult> {
    return normalizeFetchResult(
      await request<unknown>(`/price-monitoring/runs/${encodeURIComponent(runId)}/fetch`, {
        signal,
      }),
    );
  },

  async getPriceMonitoringFetch(
    runId: string,
    signal?: AbortSignal,
  ): Promise<FetchPriceMonitoringResult> {
    return normalizeFetchResult(
      await request<unknown>(`/price-monitoring/runs/${encodeURIComponent(runId)}/fetch`, {
        signal,
      }),
    );
  },

  async getPriceMonitoringFetchLogs(
    runId: string,
    signal?: AbortSignal,
  ): Promise<PriceMonitoringFetchLogsResponse> {
    return normalizeFetchLogs(
      await request<unknown>(`/price-monitoring/runs/${encodeURIComponent(runId)}/fetch/logs`, {
        signal,
      }),
    );
  },

  async getPriceMonitoringFetchExecution(
    runId: string,
    executionId: string | number,
    signal?: AbortSignal,
  ): Promise<FetchPriceMonitoringResult> {
    return normalizeFetchResult(
      await request<unknown>(
        `/price-monitoring/runs/${encodeURIComponent(runId)}/fetch/${encodeURIComponent(String(executionId))}`,
        { signal },
      ),
    );
  },

  async listPriceMonitoringFetchExecutions(
    runId: string,
    signal?: AbortSignal,
  ): Promise<FetchPriceMonitoringResult[]> {
    return getArrayPayload(
      await request<unknown>(
        `/price-monitoring/runs/${encodeURIComponent(runId)}/fetch/executions`,
        { signal },
      ),
      ["executions", "items", "data", "results"],
    ).map(normalizeFetchResult);
  },

  async getPriceMonitoringFetchExecutionLogs(
    runId: string,
    executionId: string | number,
    signal?: AbortSignal,
  ): Promise<PriceMonitoringFetchLogsResponse> {
    return normalizeFetchLogs(
      await request<unknown>(
        `/price-monitoring/runs/${encodeURIComponent(runId)}/fetch/${encodeURIComponent(String(executionId))}/logs`,
        { signal },
      ),
    );
  },

  async cancelPriceMonitoringFetch(
    runId: string,
    reason?: string | null,
    signal?: AbortSignal,
  ): Promise<FetchPriceMonitoringResult> {
    const body: CancelPriceMonitoringFetchBody | undefined =
      reason === undefined ? undefined : { reason };

    return normalizeFetchResult(
      await request<unknown>(`/price-monitoring/runs/${encodeURIComponent(runId)}/fetch/cancel`, {
        method: "POST",
        body,
        signal,
      }),
    );
  },

  async cancelPriceMonitoringFetchExecution(
    runId: string,
    executionId: string | number,
    reason?: string | null,
    signal?: AbortSignal,
  ): Promise<FetchPriceMonitoringResult> {
    const body: CancelPriceMonitoringFetchBody | undefined =
      reason === undefined ? undefined : { reason };

    return normalizeFetchResult(
      await request<unknown>(
        `/price-monitoring/runs/${encodeURIComponent(runId)}/fetch/${encodeURIComponent(String(executionId))}/cancel`,
        {
          method: "POST",
          body,
          signal,
        },
      ),
    );
  },

  async getPriceMonitoringDbStatus(signal?: AbortSignal): Promise<PriceMonitoringDbStatus> {
    return normalizeDbStatus(
      await request<unknown>("/price-monitoring/db/status", { signal }),
    );
  },

  async listPriceMonitoringObservations(
    params: PriceObservationsParams = {},
    signal?: AbortSignal,
  ): Promise<PriceObservationsResponse> {
    return normalizePriceObservationsResponse(
      await request<unknown>(
        appendQuery("/price-monitoring/observations", params as QueryParams),
        { signal },
      ),
    );
  },

  async getPriceMonitoringRunObservations(
    runId: string,
    params: { include_unmatched?: boolean; limit?: number; offset?: number } = {},
    signal?: AbortSignal,
  ): Promise<RunPriceObservationsResponse> {
    return normalizeRunPriceObservationsResponse(
      await request<unknown>(
        appendQuery(
          `/price-monitoring/runs/${encodeURIComponent(runId)}/observations`,
          params,
        ),
        { signal },
      ),
    );
  },

  async getPriceMonitoringRunCatalogSnapshot(
    runId: string,
    signal?: AbortSignal,
  ): Promise<CatalogSnapshotResponse> {
    return normalizeCatalogSnapshotResponse(
      await request<unknown>(
        `/price-monitoring/runs/${encodeURIComponent(runId)}/catalog-snapshot`,
        { signal },
      ),
    );
  },

  async getPriceMonitoringProductPriceHistory(
    productId: string | number,
    signal?: AbortSignal,
  ): Promise<PriceHistoryResponse> {
    return normalizePriceHistoryResponse(
      await request<unknown>(
        `/price-monitoring/products/${encodeURIComponent(String(productId))}/price-history`,
        { signal },
      ),
    );
  },

  async getPriceMonitoringModelPriceHistory(
    model: string,
    params: { catalog_source?: string | null; include_unmatched?: boolean } = {},
    signal?: AbortSignal,
  ): Promise<PriceHistoryResponse> {
    return normalizePriceHistoryResponse(
      await request<unknown>(
        appendQuery(
          `/price-monitoring/products/by-model/${encodeURIComponent(model)}/price-history`,
          params,
        ),
        { signal },
      ),
    );
  },

  async listPriceMonitoringAlertRules(
    params: { active?: boolean | null; rule_type?: string | null; limit?: number; offset?: number } = {},
    signal?: AbortSignal,
  ): Promise<AlertRulesResponse> {
    return normalizeAlertRulesResponse(
      await request<unknown>(
        appendQuery("/price-monitoring/alerts/rules", params as QueryParams),
        { signal },
      ),
    );
  },

  async createPriceMonitoringAlertRule(
    body: CreateAlertRuleBody,
    signal?: AbortSignal,
  ): Promise<AlertRule> {
    return (
      normalizeAlertRule(
        await request<unknown>("/price-monitoring/alerts/rules", {
          method: "POST",
          body,
          signal,
        }),
      ) ?? {}
    );
  },

  async getPriceMonitoringAlertRule(
    ruleId: string | number,
    signal?: AbortSignal,
  ): Promise<AlertRule> {
    return (
      normalizeAlertRule(
        await request<unknown>(
          `/price-monitoring/alerts/rules/${encodeURIComponent(String(ruleId))}`,
          { signal },
        ),
      ) ?? {}
    );
  },

  async updatePriceMonitoringAlertRule(
    ruleId: string | number,
    body: UpdateAlertRuleBody,
    signal?: AbortSignal,
  ): Promise<AlertRule> {
    return (
      normalizeAlertRule(
        await request<unknown>(
          `/price-monitoring/alerts/rules/${encodeURIComponent(String(ruleId))}`,
          {
            method: "PATCH",
            body,
            signal,
          },
        ),
      ) ?? {}
    );
  },

  async deactivatePriceMonitoringAlertRule(
    ruleId: string | number,
    signal?: AbortSignal,
  ): Promise<AlertRule> {
    return (
      normalizeAlertRule(
        await request<unknown>(
          `/price-monitoring/alerts/rules/${encodeURIComponent(String(ruleId))}/deactivate`,
          {
            method: "POST",
            signal,
          },
        ),
      ) ?? {}
    );
  },

  async listPriceMonitoringAlertEvents(
    params: {
      status?: AlertEventStatus | "all" | null;
      run_id?: string | null;
      product_id?: string | number | null;
      model?: string | null;
      limit?: number;
      offset?: number;
    } = {},
    signal?: AbortSignal,
  ): Promise<AlertEventsResponse> {
    return normalizeAlertEventsResponse(
      await request<unknown>(
        appendQuery("/price-monitoring/alerts/events", params as QueryParams),
        { signal },
      ),
    );
  },

  async acknowledgePriceMonitoringAlertEvent(
    eventId: string | number,
    body: { acknowledged_by?: string | null } = {},
    signal?: AbortSignal,
  ): Promise<AlertEvent> {
    return (
      normalizeAlertEvent(
        await request<unknown>(
          `/price-monitoring/alerts/events/${encodeURIComponent(String(eventId))}/acknowledge`,
          {
            method: "POST",
            body,
            signal,
          },
        ),
      ) ?? {}
    );
  },

  async resolvePriceMonitoringAlertEvent(
    eventId: string | number,
    body: { resolved_by?: string | null } = {},
    signal?: AbortSignal,
  ): Promise<AlertEvent> {
    return (
      normalizeAlertEvent(
        await request<unknown>(
          `/price-monitoring/alerts/events/${encodeURIComponent(String(eventId))}/resolve`,
          {
            method: "POST",
            body,
            signal,
          },
        ),
      ) ?? {}
    );
  },

  async evaluatePriceMonitoringAlertsForRun(
    runId: string,
    signal?: AbortSignal,
  ): Promise<EvaluateAlertsResponse> {
    return normalizeEvaluateAlertsResponse(
      await request<unknown>(
        `/price-monitoring/alerts/evaluate/${encodeURIComponent(runId)}`,
        {
          method: "POST",
          signal,
        },
      ),
    );
  },

  async getPriceMonitoringReview(
    runId: string,
    params: PriceMonitoringReviewParams = {},
    signal?: AbortSignal,
  ): Promise<PriceMonitoringReviewResponse> {
    return normalizeReview(
      await request<unknown>(
        appendQuery(`/price-monitoring/runs/${encodeURIComponent(runId)}/review`, {
          enriched_csv_path: params.enriched_csv_path,
        }),
        { signal },
      ),
    );
  },

  applyPriceMonitoringReviewActions(
    runId: string,
    body: ApplyPriceMonitoringReviewActionsBody,
    signal?: AbortSignal,
  ): Promise<ApplyPriceMonitoringReviewActionsResult> {
    return request<unknown>(
      `/price-monitoring/runs/${encodeURIComponent(runId)}/review/actions`,
      {
        method: "POST",
        body,
        signal,
      },
    ).then(normalizeApplyReviewActionsResult);
  },

  exportPriceMonitoringPriceUpdate(
    runId: string,
    body: ExportPriceMonitoringPriceUpdateBody,
    signal?: AbortSignal,
  ): Promise<ExportPriceMonitoringPriceUpdateResult> {
    return request<unknown>(
      `/price-monitoring/runs/${encodeURIComponent(runId)}/export-price-update`,
      {
        method: "POST",
        body,
        signal,
      },
    ).then(normalizeExportPriceUpdateResult);
  },

  async getFileRoots(signal?: AbortSignal): Promise<FileRoot[]> {
    return normalizeFileRoots(await request<unknown>("/files/roots", { signal }));
  },

  async listFiles(params: FileListParams, signal?: AbortSignal): Promise<FileListResponse> {
    return normalizeFileList(
      await request<unknown>(
        appendQuery("/files/list", {
          root: params.root,
          relative_path: params.relative_path,
        }),
        { signal },
      ),
    );
  },

  async readCsvFile(
    body: ReadCsvFileBody,
    signal?: AbortSignal,
  ): Promise<ReadCsvFileResponse> {
    return normalizeCsvRead(
      await request<unknown>("/files/read", {
        method: "POST",
        body,
        signal,
      }),
    );
  },

  saveCsvFile(body: SaveCsvFileBody, signal?: AbortSignal): Promise<SaveCsvResponse> {
    return request<SaveCsvResponse>("/files/save", {
      method: "POST",
      body,
      signal,
    });
  },

  saveCsvCopy(body: SaveCsvCopyBody, signal?: AbortSignal): Promise<SaveCsvResponse> {
    return request<SaveCsvResponse>("/files/save-copy", {
      method: "POST",
      body,
      signal,
    });
  },

  runBridge(body: BridgeRunBody, signal?: AbortSignal): Promise<BridgeRunResponse> {
    return request<BridgeRunResponse>("/bridge/run", {
      method: "POST",
      body,
      signal,
    });
  },
};
