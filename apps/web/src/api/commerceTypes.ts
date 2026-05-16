import type { components as EcommerceOpenApi } from "./generated/ecommerce";

type EcommerceSchema<Name extends keyof EcommerceOpenApi["schemas"]> =
  EcommerceOpenApi["schemas"][Name];
type AssertAssignable<Actual extends Expected, Expected> = true;

export type EcommerceContractAlertRuleCreateRequest =
  EcommerceSchema<"AlertRuleCreateRequest">;
export type EcommerceContractAlertRuleUpdateRequest =
  EcommerceSchema<"AlertRuleUpdateRequest">;
export type EcommerceContractCsvReadRequest = EcommerceSchema<"CsvReadRequest">;
export type EcommerceContractCsvSaveRequest = EcommerceSchema<"CsvSaveRequest">;
export type EcommerceContractCsvSaveCopyRequest = EcommerceSchema<"CsvSaveCopyRequest">;
export type EcommerceContractPriceMonitoringFetchRequest =
  EcommerceSchema<"PriceMonitoringFetchApiRequest">;
export type EcommerceContractPriceMonitoringFetchCancelRequest =
  EcommerceSchema<"PriceMonitoringFetchCancelApiRequest">;
export type EcommerceContractPriceMonitoringSelectionRequest =
  EcommerceSchema<"PriceMonitoringSelectionApiRequest">;
export type EcommerceContractPriceReviewActionsRequest =
  EcommerceSchema<"PriceReviewActionsApiRequest">;
export type EcommerceContractPriceUpdateExportRequest =
  EcommerceSchema<"PriceUpdateExportApiRequest">;
export type EcommerceContractSourceUrlCreateRequest =
  EcommerceSchema<"SourceUrlCreateRequest">;
export type EcommerceContractSourceUrlUpdateRequest =
  EcommerceSchema<"SourceUrlUpdateRequest">;
export type EcommerceContractSourceUrlCandidateReviewRequest =
  EcommerceSchema<"SourceUrlCandidateReviewRequest">;
export type EcommerceContractSourceUrlAgentReadinessResponse =
  EcommerceSchema<"SourceUrlAgentReadinessResponse">;
export type EcommerceContractPlatformHealthResponse =
  EcommerceSchema<"PlatformHealthResponse">;
export type EcommerceContractSourceUrlImportRequest =
  EcommerceSchema<"SourceUrlImportRequest">;
export type EcommerceContractProductFactoryHandoffImportRequest =
  EcommerceSchema<"ProductFactoryHandoffImportRequest">;

export type MarketplaceFilter = "all" | "bestprice" | "skroutz" | "both" | "none";

export type MarketplaceMonitoringSource = "skroutz" | "bestprice";

export type PriceMonitoringSource = SourceName;

export type KnownSourceName =
  | "electronet"
  | "skroutz"
  | "bestprice"
  | "plaisio"
  | "public"
  | "kotsovolos";

export type SourceName = KnownSourceName | (string & {});

export type CandidateSourceName = SourceName;

export interface VendorSourceCapability {
  source_name: SourceName | string;
  source_domain?: string | null;
  source_type?: string | null;
  discovery_enabled: boolean;
  capture_enabled: boolean;
  capture_implemented: boolean;
  supports_search: boolean;
  supports_direct_product_url: boolean;
  supports_xhr_capture: boolean;
  expected_listing_field?: string | null;
  notes?: string | null;
  [key: string]: unknown;
}

export type IgnoredFilter = "exclude" | "include";

export interface CatalogProduct {
  catalog_product_id?: number | string | null;
  model: string;
  mpn?: string | null;
  name?: string | null;
  category?: string | null;
  raw_category?: string | null;
  family?: string | null;
  category_name?: string | null;
  sub_category?: string | null;
  category_levels?: string[] | null;
  manufacturer?: string | null;
  price?: number | null;
  quantity?: number | null;
  status?: number | null;
  bestprice_status?: number | null;
  skroutz_status?: number | null;
  is_atomic_model?: boolean | null;
  automation_eligible?: boolean | null;
  ignored?: boolean | null;
  warnings?: string[] | null;
  source_url_coverage?: PriceMonitoringSourceUrlCoverage | null;
  [key: string]: unknown;
}

export type SourceUrlStatus = "active" | "disabled" | "broken" | "redirected" | "needs_review";

export type SourceUrlType = "manual" | "imported" | "discovered";

export interface SourceUrl {
  id?: number | string | null;
  source_url_id?: number | string | null;
  catalog_product_id?: number | string | null;
  product_source_id?: number | string | null;
  catalog_source?: string | null;
  model?: string | null;
  mpn?: string | null;
  manufacturer?: string | null;
  source_name?: SourceName | null;
  source_domain?: string | null;
  url: string;
  url_normalized?: string | null;
  status: SourceUrlStatus | string;
  url_type: SourceUrlType | string;
  trust_level?: string | null;
  added_by?: string | null;
  notes?: string | null;
  last_seen_at?: string | null;
  last_success_at?: string | null;
  last_failed_at?: string | null;
  failure_count?: number | null;
  last_error?: string | null;
  capture_status?: string | null;
  last_fetch_status?: string | null;
  last_capture_status?: string | null;
  last_capture_strategy?: string | null;
  last_capture_at?: string | null;
  last_fetched_at?: string | null;
  last_capture_snapshot_id?: number | string | null;
  source_capture_snapshot_id?: number | string | null;
  artifact_ref?: ArtifactPayload | string | null;
  artifact_refs?: ArtifactItem[];
  snapshot_ref?: ArtifactPayload | string | null;
  full_snapshot_ref?: ArtifactPayload | string | null;
  created_at?: string | null;
  updated_at?: string | null;
  [key: string]: unknown;
}

export interface SourceUrlCreateBody {
  url: string;
  source_name?: SourceName | null;
  url_type?: SourceUrlType | string | null;
  trust_level?: string | null;
  added_by?: string | null;
  notes?: string | null;
}

export interface SourceUrlUpdateBody {
  url?: string | null;
  source_name?: SourceName | null;
  status?: SourceUrlStatus | string | null;
  trust_level?: string | null;
  notes?: string | null;
}

export interface SourceUrlValidationResponse {
  item: SourceUrl | null;
  validation: {
    status?: string | null;
    message?: string | null;
    http_status_code?: number | null;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface SourceUrlListResponse {
  items: SourceUrl[];
  count?: number;
  [key: string]: unknown;
}

export interface CatalogProductSourceUrlSummary {
  total_count?: number;
  by_status?: Record<string, number>;
  by_source?: Record<string, number>;
  by_type?: Record<string, number>;
  [key: string]: unknown;
}

export interface CatalogProductDetailResponse {
  product: CatalogProduct | null;
  source_urls: SourceUrl[];
  source_url_summary: CatalogProductSourceUrlSummary;
  warnings: string[];
  [key: string]: unknown;
}

export interface MissingSourceUrlProduct {
  catalog_product_id?: number | string | null;
  model?: string | null;
  mpn?: string | null;
  manufacturer?: string | null;
  name?: string | null;
  reason?: string | null;
  [key: string]: unknown;
}

export interface SourceUrlSummaryResponse {
  catalog_source?: string | null;
  catalog_product_count?: number;
  total_count?: number;
  active_count?: number;
  needs_review_count?: number;
  broken_count?: number;
  disabled_count?: number;
  redirected_count?: number;
  manual_count?: number;
  imported_count?: number;
  discovered_count?: number;
  products_with_urls_count?: number;
  products_without_urls_count?: number;
  coverage_percent?: number | null;
  by_status?: Record<string, number>;
  by_type?: Record<string, number>;
  by_source?: Record<SourceName, number>;
  missing_source_url_models?: string[];
  missing_source_url_catalog_product_ids?: Array<number | string>;
  missing_active_source_url_products?: MissingSourceUrlProduct[];
  summary_source?: "vendor-sources" | "catalog";
  updated_at?: string | null;
  [key: string]: unknown;
}

export interface SourceUrlImportRequest {
  catalog_source?: string | null;
  include_observations?: boolean;
  include_artifacts?: boolean;
  limit?: number | null;
  report_items_limit?: number | null;
  report_item_limit?: number | null;
  [key: string]: unknown;
}

export interface ProductFactoryHandoffImportRequest {
  handoff_path: string;
  catalog_source?: string | null;
  persist_initial_capture: boolean;
  limit?: number | null;
  report_items_limit?: number | null;
  [key: string]: unknown;
}

export interface SourceUrlImportSummary {
  candidates_found: number;
  imported_count: number;
  updated_count: number;
  skipped_count: number;
  active_count: number;
  needs_review_count: number;
  invalid_url_count: number;
  duplicate_count: number;
  unresolved_identity_count: number;
  ambiguous_identity_count: number;
  would_import_count?: number;
  would_update_count?: number;
  [key: string]: unknown;
}

export interface SourceUrlImportCandidateReport {
  action?: string | null;
  status?: string | null;
  source_name?: SourceName | null;
  source_domain?: string | null;
  catalog_source?: string | null;
  model?: string | null;
  mpn?: string | null;
  url?: string | null;
  url_normalized?: string | null;
  evidence_source?: string | null;
  evidence_detail?: string | null;
  reason?: string | null;
  confidence?: string | null;
  catalog_product_id?: number | string | null;
  source_url_id?: number | string | null;
  [key: string]: unknown;
}

export interface SourceUrlImportResponse extends SourceUrlImportSummary {
  applied?: boolean;
  apply: boolean;
  mode?: string | null;
  summary: SourceUrlImportSummary;
  sources?: Record<string, Record<string, number>>;
  items?: SourceUrlImportCandidateReport[];
  sources_processed: string[];
  warnings: string[];
  skipped_reasons: Record<string, number>;
  changed_source_urls: unknown[];
  source_stats: Record<string, Record<string, number>>;
  candidate_evidence: unknown[];
  report_items: SourceUrlImportCandidateReport[];
  truncated?: boolean;
  report_truncated?: boolean;
  handoff_summary?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface SourceUrlImportOptionsResponse {
  catalog_sources: string[];
  default_catalog_source?: string | null;
  [key: string]: unknown;
}

export type SourceUrlCandidateStatus =
  | "pending"
  | "needs_review"
  | "accepted"
  | "rejected"
  | "not_found"
  | "error";

export type SourceUrlCandidateReviewDecision =
  | "accept"
  | "reject"
  | "replace_url";

export interface SourceUrlCandidate {
  id: number | string;
  source_url_id?: number | string | null;
  run_id?: number | string | null;
  catalog_product_id?: number | string | null;
  model?: string | null;
  mpn?: string | null;
  manufacturer?: string | null;
  product_name?: string | null;
  category?: string | null;
  own_price?: number | string | null;
  source_name?: CandidateSourceName | null;
  source_domain?: string | null;
  source_type?: string | null;
  expected_listing?: string | boolean | null;
  candidate_url?: string | null;
  canonical_url?: string | null;
  candidate_title?: string | null;
  candidate_price?: number | string | null;
  match_status?: string | null;
  confidence_score?: number | string | null;
  match_method?: string | null;
  evidence_json?: unknown;
  competing_candidates_count?: number | string | null;
  searched_queries_json?: unknown;
  status?: SourceUrlCandidateStatus | string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  review_panel?: {
    mode?: string | null;
    open_on?: string | null;
    review_actions?: SourceUrlCandidateReviewActionConfig[];
    [key: string]: unknown;
  } | null;
  [key: string]: unknown;
}

export interface SkroutzNetworkJsonSummary {
  top_level_type?: string | null;
  top_level_keys?: string[];
  top_level_key_count?: number | null;
  has_product_cards?: boolean | null;
  product_cards_count?: number | null;
  array_length?: number | null;
  first_item_keys?: string[];
  [key: string]: unknown;
}

export interface SkroutzNetworkCapturedEndpoint {
  method?: string | null;
  url?: string | null;
  status?: number | string | null;
  resource_type?: string | null;
  content_type?: string | null;
  body_size?: number | string | null;
  parsed_json_valid?: boolean | null;
  json_summary?: SkroutzNetworkJsonSummary | null;
  classification?: string | null;
  matched_derived_endpoint?: string | null;
  body_sample?: string | null;
  json_parse_error?: string | null;
  [key: string]: unknown;
}

export interface SkroutzNetworkDiagnosticSummary {
  source_url_id?: number | string | null;
  vendor_slug?: string | null;
  source_url?: string | null;
  status?: string | null;
  captured_response_count?: number;
  derived_endpoints?: Record<string, string>;
  derived_filter_products_url?: string | null;
  derived_shops_details_url?: string | null;
  observed_derived_endpoints?: Record<string, boolean>;
  observed_filter_products_url?: boolean;
  observed_shops_details_url?: boolean;
  exact_match_count?: number;
  best_product_data_endpoint?: string | null;
  product_data_candidate_url?: string | null;
  product_data_candidate_reason?: string | null;
  classifications_summary?: Record<string, number>;
  blocked_or_challenge_detected?: boolean;
  diagnostic_report_id?: number | string | null;
  artifact_path?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  [key: string]: unknown;
}

export interface SkroutzNetworkDiagnosticReport extends SkroutzNetworkDiagnosticSummary {
  summary?: SkroutzNetworkDiagnosticSummary;
  captured_responses?: SkroutzNetworkCapturedEndpoint[];
  started_at?: string | null;
  completed_at?: string | null;
  timeout_seconds?: number | null;
  headed?: boolean | null;
}

export interface SourceUrlCandidateListParams {
  status?: SourceUrlCandidateStatus | "all" | string | null;
  source_name?: SourceName | null;
  run_id?: string | number | null;
  model?: string | null;
  catalog_product_id?: string | number | null;
  min_confidence?: string | number | null;
  max_confidence?: string | number | null;
  limit?: number;
  offset?: number;
}

export interface SourceUrlCandidateListResponse {
  items: SourceUrlCandidate[];
  total: number;
  limit: number;
  offset: number;
}

export interface ProductSourceUrlCandidateRunGroup {
  run_id: string | number | null;
  run: SourceUrlAgentRun;
  counts: Record<string, number>;
  candidates: SourceUrlCandidate[];
  [key: string]: unknown;
}

export interface ProductSourceUrlCandidateHistoryResponse {
  catalog_product_id: string | number | null;
  items: ProductSourceUrlCandidateRunGroup[];
  total_candidates: number;
  warnings: string[];
  [key: string]: unknown;
}

export interface SourceUrlAgentRunRequest {
  mode: "catalog" | string;
  source: "all" | SourceName | string;
  selected_models?: string[];
  missing_only: boolean;
  active_only: boolean;
  dry_run: boolean;
  apply_high_confidence: boolean;
  limit: number | null;
  rate_limit_seconds: number | null;
  [key: string]: unknown;
}

export interface SourceUrlAgentRunSummary {
  selected_count?: number;
  candidate_count?: number;
  matched_count?: number;
  needs_review_count?: number;
  not_found_count?: number;
  error_count?: number;
  high_confidence_count?: number;
  applied_count?: number;
  skipped_count?: number;
  task_total_count?: number;
  task_finished_count?: number;
  task_counts?: Record<string, number>;
  [key: string]: unknown;
}

export interface SourceUrlAgentTask {
  id?: string | number | null;
  run_id?: string | number | null;
  catalog_product_id?: string | number | null;
  model?: string | null;
  source_name?: string | null;
  status?: string | null;
  match_status?: string | null;
  candidate_count?: number;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  [key: string]: unknown;
}

export interface SourceUrlAgentRun extends SourceUrlAgentRunSummary {
  run_id?: string | number | null;
  id?: string | number | null;
  source?: "all" | SourceName | string | null;
  mode?: "catalog" | string | null;
  status?: string | null;
  dry_run?: boolean | null;
  apply_high_confidence?: boolean | null;
  missing_only?: boolean | null;
  active_only?: boolean | null;
  limit?: number | null;
  rate_limit_seconds?: number | null;
  output_dir?: string | null;
  summary?: SourceUrlAgentRunSummary | null;
  task_counts?: Record<string, number>;
  task_total_count?: number;
  task_finished_count?: number;
  tasks?: SourceUrlAgentTask[];
  artifacts?: ArtifactItem[];
  warnings?: string[];
  created_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  updated_at?: string | null;
  [key: string]: unknown;
}

export interface SourceUrlAgentRunArtifactsResponse extends ArtifactListResponse {
  run_id?: string | number | null;
  items: ArtifactItem[];
}

export type SourceUrlAgentReadinessStatus = "ready" | "warning" | "blocked";

export interface SourceUrlAgentProviderReadiness {
  provider_name: string;
  provider_type: string;
  enabled: boolean;
  configured: boolean;
  required_env_keys: string[];
  missing_env_keys: string[];
  allow_high_confidence_auto_apply: boolean;
  notes: string;
}

export interface SourceUrlAgentReadiness {
  status: SourceUrlAgentReadinessStatus;
  providers: SourceUrlAgentProviderReadiness[];
  default_provider_order: string[];
  source_cascades: Record<string, string[]>;
  warnings: string[];
  blocking_reasons: string[];
}

export type PlatformHealthStatus = "ready" | "warning" | "blocked" | "unknown";

export interface PlatformHealthLink {
  label: string;
  url: string;
}

export interface PlatformHealthGroup {
  id: string;
  label: string;
  status: PlatformHealthStatus;
  summary: string;
  details: string[];
  blocking_reasons: string[];
  warnings: string[];
  links: PlatformHealthLink[];
}

export interface PlatformHealthResponse {
  status: PlatformHealthStatus;
  groups: PlatformHealthGroup[];
  updated_at: string;
}

export interface VendorSourceCaptureRunRequest {
  source_filter?: SourceName | string | null;
  limit?: number | null;
  include_not_due?: boolean;
  refresh_after_minutes?: number | null;
  catalog_product_ids?: Array<number | string>;
  [key: string]: unknown;
}

export interface VendorSourceCaptureRunSummary {
  selected_source_url_count?: number;
  succeeded_count?: number;
  failed_count?: number;
  skipped_count?: number;
  captured_count?: number;
  [key: string]: unknown;
}

export interface VendorSourceCaptureRun extends VendorSourceCaptureRunSummary {
  run_id?: string | number | null;
  id?: string | number | null;
  source_filter?: SourceName | string | null;
  observation_batch_id?: string | number | null;
  status?: string | null;
  limit?: number | null;
  include_not_due?: boolean | null;
  refresh_after_minutes?: number | null;
  catalog_product_ids?: Array<number | string>;
  output_dir?: string | null;
  summary?: VendorSourceCaptureRunSummary | null;
  artifacts?: ArtifactItem[];
  warnings?: string[];
  created_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  updated_at?: string | null;
  [key: string]: unknown;
}

export interface VendorSourceCaptureRunArtifactsResponse extends ArtifactListResponse {
  run_id?: string | number | null;
  observation_batch_id?: string | number | null;
  items: ArtifactItem[];
}

export type FirecrawlHealthReason =
  | "firecrawl_api_key_missing"
  | "firecrawl_timeout"
  | "firecrawl_rate_limited"
  | "firecrawl_blocked"
  | "firecrawl_http_error"
  | "firecrawl_parse_failed"
  | "firecrawl_no_offers"
  | "firecrawl_unknown_error";

export interface VendorSourceHealthItem {
  product_source_id: number | string;
  product_id?: number | string | null;
  model?: string | null;
  mpn?: string | null;
  vendor?: SourceName | string | null;
  source_url?: string | null;
  canonical_url?: string | null;
  active?: boolean | null;
  health?: string | null;
  last_fetch_status?: string | null;
  last_success_at?: string | null;
  last_error_at?: string | null;
  last_error_code?: string | null;
  last_error_message?: string | null;
  health_reason?: FirecrawlHealthReason | string | null;
  consecutive_failures?: number;
  data_quality_flags?: string[];
  updated_at?: string | null;
  [key: string]: unknown;
}

export interface VendorSourceHealthResponse {
  items: VendorSourceHealthItem[];
  limit?: number;
  offset?: number;
  count: number;
  [key: string]: unknown;
}

export interface VendorSourceRecaptureResponse {
  product_source_id: number | string;
  vendor?: string | null;
  status?: string | null;
  snapshot_id?: number | string | null;
  error_code?: string | null;
  health_reason?: FirecrawlHealthReason | string | null;
  capture_run_id?: string | number | null;
  observation_batch_id?: string | number | null;
  [key: string]: unknown;
}

export interface SourceUrlCandidateReviewLayoutColumn {
  key?: string | null;
  id?: string | null;
  field?: string | null;
  label?: string | null;
  title?: string | null;
  visible?: boolean | null;
  table_column_visible?: boolean | null;
  width_px?: number | null;
  order?: number | null;
  [key: string]: unknown;
}

export interface SourceUrlCandidateReviewActionConfig {
  decision?: SourceUrlCandidateReviewDecision | string | null;
  label?: string | null;
  requires_url?: boolean | null;
  requires_reviewed_url?: boolean | null;
  style?: string | null;
  [key: string]: unknown;
}

export interface SourceUrlCandidateReviewLayout {
  user_key?: string | null;
  columns: SourceUrlCandidateReviewLayoutColumn[];
  actions?: {
    table_column_visible?: boolean | null;
    replacement?: string | null;
    [key: string]: unknown;
  } | null;
  review_panel?: {
    mode?: string | null;
    open_on?: string | null;
    review_actions?: SourceUrlCandidateReviewActionConfig[];
    [key: string]: unknown;
  } | null;
  [key: string]: unknown;
}

export interface SourceUrlCandidateReviewBody {
  decision: SourceUrlCandidateReviewDecision;
  reviewed_url: string | null;
  review_notes: string | null;
  reviewed_by: string | null;
}

export interface CatalogProductsResponse {
  items: CatalogProduct[];
  page: number;
  page_size: number;
  total: number;
  filtered_total: number;
  warning?: string | null;
}

export interface CatalogProductsParams {
  q?: string | null;
  category?: string | null;
  family?: string | null;
  category_name?: string | null;
  sub_category?: string | null;
  manufacturer?: string | null;
  marketplace?: MarketplaceFilter | null;
  source_name?: PriceMonitoringSource | string | null;
  page?: number;
  page_size?: number;
  atomic_only?: boolean;
  has_source_url?: boolean;
  has_quantity?: boolean;
  ignored?: IgnoredFilter;
  automation_eligible_only?: boolean;
}

export interface CatalogSummary {
  total_products?: number;
  total?: number;
  active_products?: number;
  active?: number;
  atomic_products?: number;
  atomic?: number;
  composite_or_invalid_models?: number;
  composite_products?: number;
  composite_invalid_models?: number;
  non_atomic_products?: number;
  bestprice_products?: number;
  bestprice?: number;
  skroutz_products?: number;
  skroutz?: number;
  missing_mpn?: number;
  missing_mpn_products?: number;
  [key: string]: unknown;
}

export interface CatalogCategoryOption {
  category: string;
  count?: number | null;
}

export interface CatalogSubCategoryNode {
  sub_category: string;
  count?: number | null;
  raw_categories?: string[] | null;
}

export interface CatalogCategoryNode {
  category_name: string;
  count?: number | null;
  sub_categories?: CatalogSubCategoryNode[] | null;
}

export interface CatalogFamilyNode {
  family: string;
  count?: number | null;
  categories?: CatalogCategoryNode[] | null;
}

export interface CatalogCategoryHierarchyResponse {
  items: CatalogFamilyNode[];
}

export interface CatalogBrandOption {
  manufacturer: string;
  count?: number | null;
}

export interface PriceMonitoringSelectionFilters {
  q: string | null;
  category?: string | null;
  family?: string | null;
  category_name?: string | null;
  sub_category?: string | null;
  manufacturer: string | null;
  marketplace: Exclude<MarketplaceFilter, "all"> | null;
  has_mpn: boolean;
  atomic_only: boolean;
  automation_eligible_only: boolean;
}

export interface PriceMonitoringSelectionBody {
  source: PriceMonitoringSource | SourceName | string;
  source_name?: SourceName | string;
  source_filter?: SourceName | string;
  filters: PriceMonitoringSelectionFilters;
  selected_models: string[];
  excluded_models: string[];
  include_ignored: boolean;
  dry_run: boolean;
}

export interface PriceMonitoringSelectionItem {
  model?: string;
  name?: string;
  mpn?: string | null;
  catalog_product_id?: number | string | null;
  category?: string | null;
  raw_category?: string | null;
  family?: string | null;
  category_name?: string | null;
  sub_category?: string | null;
  manufacturer?: string | null;
  skip_reason?: string | null;
  reason?: string | null;
  source_url_coverage?: PriceMonitoringSourceUrlCoverage | null;
  [key: string]: unknown;
}

export interface PriceMonitoringSourceUrlCoverage {
  source?: SourceName | PriceMonitoringSource | string | null;
  selected_count?: number;
  products_with_active_source_urls?: number;
  products_without_active_source_urls?: number;
  coverage_percent?: number | null;
  active_source_url_count?: number;
  needs_review_source_url_count?: number;
  broken_source_url_count?: number;
  disabled_source_url_count?: number;
  redirected_source_url_count?: number;
  missing_source_url_models?: string[];
  missing_source_url_catalog_product_ids?: Array<number | string>;
  has_active_source_url?: boolean;
  status_counts?: Record<string, number>;
  active_source_urls?: SourceUrl[];
  warning?: string | null;
  [key: string]: unknown;
}

export interface PriceMonitoringSelectionResult {
  run_id?: string | number | null;
  status?: string | null;
  source?: PriceMonitoringSource | string | null;
  output_dir?: string | null;
  input_csv_path?: string | null;
  selection_summary_path?: string | null;
  selected_count?: number;
  skipped_count?: number;
  skipped_by_reason?: Record<string, number>;
  selected_items?: PriceMonitoringSelectionItem[];
  selected?: PriceMonitoringSelectionItem[];
  skipped_reasons?: Record<string, unknown>;
  skipped_items?: PriceMonitoringSelectionItem[];
  source_url_coverage?: PriceMonitoringSourceUrlCoverage | null;
  [key: string]: unknown;
}

export type PriceMonitoringAction = "match_price" | "undercut" | "ignore";

export interface PriceMonitoringRun {
  run_id?: string | number | null;
  id?: string | number | null;
  status?: string | null;
  source?: PriceMonitoringSource | string | null;
  output_dir?: string | null;
  input_csv_path?: string | null;
  selection_summary_path?: string | null;
  selected_count?: number;
  skipped_count?: number;
  skipped_by_reason?: Record<string, number>;
  source_url_coverage?: PriceMonitoringSourceUrlCoverage | null;
  created_at?: string | null;
  updated_at?: string | null;
  latest_fetch?: FetchPriceMonitoringResult | null;
  [key: string]: unknown;
}

export interface FetchPriceMonitoringBody {
  source: PriceMonitoringSource | null;
  catalog_url: string | null;
}

export interface FetchPriceMonitoringResult {
  run_id?: string | number | null;
  execution_id?: string | number | null;
  status?: "queued" | "running" | "succeeded" | "failed" | "killed" | "cancelled" | string | null;
  source?: PriceMonitoringSource | string | null;
  catalog_url?: string | null;
  fetch_input_mode?: "source_urls" | string | null;
  queued_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  cancelled_at?: string | null;
  killed_at?: string | null;
  cancel_reason?: string | null;
  killed_reason?: string | null;
  termination_mode?: string | null;
  terminate_sent_at?: string | null;
  kill_sent_at?: string | null;
  exit_code?: number | null;
  parent_process_id?: number | null;
  process_id?: number | null;
  process_group_id?: number | null;
  command?: string[] | null;
  artifacts_are_diagnostic?: boolean | null;
  artifact_warning?: string | null;
  execution_type?: string | null;
  queue_position?: number | null;
  stale?: boolean | null;
  input_csv_path?: ArtifactPayload | string | null;
  enriched_csv_path?: ArtifactPayload | string | null;
  fetch_summary_path?: ArtifactPayload | string | null;
  fetch_result_path?: ArtifactPayload | string | null;
  execution_path?: ArtifactPayload | string | null;
  log_path?: ArtifactPayload | string | null;
  warnings?: string[];
  error?: string | null;
  observation_count?: number;
  appended_observation_count?: number;
  prior_observation_count?: number;
  retained_observation_count?: number;
  replaced_observation_count?: number;
  catalog_snapshot_count?: number | null;
  matched_observation_count?: number;
  unmatched_observation_count?: number;
  was_refetch?: boolean;
  fetch_attempt?: number;
  observation_batch_id?: string | number | null;
  observation_history_count?: number;
  persistence_status?: "not_configured" | "persisted" | "failed" | "unknown" | string | null;
  persistence_warnings?: string[];
  alert_evaluation_status?: string | null;
  alert_event_count?: number;
  alert_duplicate_count?: number;
  alert_warnings?: string[];
  artifacts?: ArtifactItem[];
  [key: string]: unknown;
}

export interface PriceMonitoringFetchLogsResponse {
  run_id?: string | number | null;
  execution_id?: string | number | null;
  lines: string[];
}

export interface CancelPriceMonitoringFetchBody {
  reason?: string | null;
}

export interface PriceMonitoringDbStatus {
  configured: boolean;
  reachable: boolean;
  price_monitoring_requires_database?: boolean | null;
  ready_for_price_monitoring?: boolean | null;
  blocking_reasons?: string[] | null;
  non_db_workflows_available?: boolean | null;
  required_for?: string[] | null;
  dialect?: string | null;
  error?: string | null;
  required_tables_present?: boolean | null;
  alembic_up_to_date?: boolean | null;
  alembic_current_revision?: string | null;
  alembic_head_revision?: string | null;
  setup_hints?: string[] | null;
  [key: string]: unknown;
}

export type PriceObservationMatchStatus = "matched" | "unmatched";

export interface PriceObservation {
  id?: number | string;
  product_id?: number | string | null;
  product_source_id?: number | string | null;
  source_url_id?: number | string | null;
  vendor_id?: number | string | null;
  source_capture_snapshot_id?: number | string | null;
  run_id?: string | number | null;
  execution_id?: string | number | null;
  fetch_attempt?: number | string | null;
  was_refetch?: boolean | null;
  observation_batch_id?: string | number | null;
  catalog_source?: string | null;
  source?: string | null;
  model?: string | null;
  mpn?: string | null;
  product_name?: string | null;
  competitor_name?: string | null;
  seller_name?: string | null;
  competitor_price?: number | string | null;
  original_price?: number | string | null;
  discount_percent?: number | string | null;
  own_price?: number | string | null;
  price_delta?: number | string | null;
  price_delta_percent?: number | string | null;
  currency?: string | null;
  availability?: string | null;
  stock_status?: string | null;
  shipping_cost?: number | string | null;
  delivery_text?: string | null;
  product_url?: string | null;
  matched_by?: "model" | "mpn" | string | null;
  match_status?: PriceObservationMatchStatus | string | null;
  is_matched?: boolean | null;
  observed_at?: string | null;
  fetched_at?: string | null;
  parsed_at?: string | null;
  timestamp_source?: string | null;
  timestamp_quality?: string | null;
  created_at?: string | null;
  artifact_ref?: ArtifactPayload | string | null;
  artifact_refs?: ArtifactItem[];
  snapshot_ref?: ArtifactPayload | string | null;
  full_snapshot_ref?: ArtifactPayload | string | null;
  raw_observation?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface PriceObservationsParams {
  run_id?: string | null;
  source?: string | null;
  catalog_source?: string | null;
  model?: string | null;
  mpn?: string | null;
  product_id?: string | number | null;
  match_status?: PriceObservationMatchStatus | "all" | null;
  include_unmatched?: boolean;
  limit?: number;
  offset?: number;
}

export interface PriceObservationsResponse {
  items: PriceObservation[];
  limit?: number;
  offset?: number;
  count: number;
}

export interface RunPriceObservationsResponse {
  run_id?: string | number | null;
  items: PriceObservation[];
  count: number;
  matched_count?: number;
  unmatched_count?: number;
}

export interface CatalogSnapshot {
  id?: number | string;
  product_id?: number | string | null;
  run_id?: string | number | null;
  catalog_source?: string | null;
  model?: string | null;
  mpn?: string | null;
  name?: string | null;
  manufacturer?: string | null;
  family?: string | null;
  category_name?: string | null;
  sub_category?: string | null;
  marketplace?: string | null;
  own_price?: number | string | null;
  currency?: string | null;
  raw_catalog_row?: Record<string, unknown> | null;
  created_at?: string | null;
  [key: string]: unknown;
}

export interface CatalogSnapshotResponse {
  run_id?: string | number | null;
  items: CatalogSnapshot[];
  count: number;
}

export interface PriceHistoryResponse {
  product_id?: string | number | null;
  model?: string | null;
  catalog_source?: string | null;
  items: PriceObservation[];
  count: number;
}

export type AlertRuleType = "competitor_below_own_price";

export type AlertEventStatus = "open" | "acknowledged" | "resolved";

export interface AlertRule {
  id?: number | string;
  name?: string | null;
  rule_type?: AlertRuleType | string;
  product_id?: number | string | null;
  catalog_source?: string | null;
  model?: string | null;
  mpn?: string | null;
  threshold_amount?: number | string | null;
  threshold_percent?: number | string | null;
  active?: boolean | null;
  created_at?: string | null;
  updated_at?: string | null;
  [key: string]: unknown;
}

export interface AlertEvent {
  id?: number | string;
  alert_rule_id?: number | string | null;
  monitoring_run_id?: number | string | null;
  price_observation_id?: number | string | null;
  product_id?: number | string | null;
  run_id?: string | number | null;
  catalog_source?: string | null;
  model?: string | null;
  mpn?: string | null;
  source?: string | null;
  competitor_name?: string | null;
  competitor_price?: number | string | null;
  own_price?: number | string | null;
  price_delta?: number | string | null;
  price_delta_percent?: number | string | null;
  severity?: string | null;
  status?: AlertEventStatus | string | null;
  message?: string | null;
  dedupe_key?: string | null;
  triggered_at?: string | null;
  acknowledged_at?: string | null;
  acknowledged_by?: string | null;
  resolved_at?: string | null;
  resolved_by?: string | null;
  raw_context?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
  [key: string]: unknown;
}

export interface AlertRulesResponse {
  items: AlertRule[];
  count: number;
  limit?: number;
  offset?: number;
}

export interface AlertEventsResponse {
  items: AlertEvent[];
  count: number;
  limit?: number;
  offset?: number;
}

export interface CreateAlertRuleBody {
  name: string | null;
  rule_type: "competitor_below_own_price";
  product_id: number | null;
  catalog_source: string | null;
  model: string | null;
  mpn: string | null;
  threshold_amount: number | string | null;
  threshold_percent: number | string | null;
  active: boolean;
}

export type UpdateAlertRuleBody = Partial<CreateAlertRuleBody>;

export interface EvaluateAlertsResponse {
  run_id?: string | number | null;
  status?: string | null;
  evaluated_rule_count?: number;
  evaluated_observation_count?: number;
  created_event_count?: number;
  duplicate_event_count?: number;
  skipped_count?: number;
  warnings?: string[];
}

export interface PriceMonitoringReviewParams {
  enriched_csv_path?: string | null;
}

export interface PriceMonitoringTopListing {
  rank?: number | null;
  store?: string | null;
  price?: number | null;
  shipping_cost?: number | null;
  landed_price?: number | null;
  landed_price_source?: "explicit" | "computed" | "missing" | string | null;
  url?: string | null;
  source?: PriceMonitoringSource | string | null;
  raw_source?: string | null;
  evidence_source?: string | null;
  [key: string]: unknown;
}

export interface PriceMonitoringReviewItem {
  model: string;
  mpn?: string | null;
  name?: string | null;
  current_price?: number | null;
  source?: PriceMonitoringSource | string | null;
  competitor_price?: number | null;
  competitor_store?: string | null;
  competitor_url?: string | null;
  source_url?: string | null;
  price_delta?: number | null;
  price_delta_percent?: number | null;
  recommended_action?: PriceMonitoringAction | "" | string | null;
  selected_action?: PriceMonitoringAction | "" | string | null;
  undercut_amount?: number | null;
  target_price?: number | null;
  status?: string | null;
  warnings?: string[];
  competitor_rank?: number | null;
  next_competitor_price?: number | null;
  next_competitor_store?: string | null;
  next_competitor_url?: string | null;
  next_store_delta?: number | null;
  next_store_delta_percent?: number | null;
  top_listings?: PriceMonitoringTopListing[];
  captured_listings_count?: number | null;
  listings_incomplete?: boolean | null;
  all_listings?: PriceMonitoringTopListing[];
  delta_basis?: string | null;
  [key: string]: unknown;
}

export interface PriceMonitoringReviewResponse {
  run_id?: string | number | null;
  items: PriceMonitoringReviewItem[];
  summary?: Record<string, number>;
  review_csv_path?: ArtifactPayload | string | null;
  enriched_csv_path?: ArtifactPayload | string | null;
  [key: string]: unknown;
}

export interface PriceMonitoringReviewAction {
  model: string;
  selected_action: PriceMonitoringAction;
  undercut_amount?: number | null;
  reason?: string;
}

export interface ApplyPriceMonitoringReviewActionsBody {
  enriched_csv_path: string | null;
  actions: PriceMonitoringReviewAction[];
}

export interface ApplyPriceMonitoringReviewActionsResult {
  status?: string | null;
  review_csv_path?: ArtifactPayload | string | null;
  review_actions_path?: ArtifactPayload | string | null;
  summary?: {
    actions_count?: number;
    exportable_count?: number;
    ignored_count?: number;
    not_exportable_count?: number;
    [key: string]: number | undefined;
  };
  [key: string]: unknown;
}

export interface ExportPriceMonitoringPriceUpdateBody {
  review_csv_path: string | null;
  output_path: string | null;
}

export interface ExportPriceMonitoringPriceUpdateResult {
  status?: string | null;
  output_path?: ArtifactPayload | string | null;
  rows_exported?: number;
  columns?: string[];
  [key: string]: unknown;
}

export interface FileRoot {
  path: string;
  exists: boolean;
}

export interface FileRootsResponse {
  roots: FileRoot[];
}

export type FileListItemType = "file" | "directory";

export interface FileListItem {
  name: string;
  path: string;
  type: FileListItemType;
  extension?: string | null;
  size_bytes?: number | null;
  modified_at?: string | null;
}

export interface FileListParams {
  root: string;
  relative_path?: string | null;
}

export interface FileListResponse {
  root: string;
  relative_path: string;
  items: FileListItem[];
}

export interface ReadCsvFileBody {
  path: string;
  delimiter: string | null;
  max_rows: number;
}

export type CsvRow = Record<string, string>;

export interface ReadCsvFileResponse {
  path: string;
  filename: string;
  delimiter: string;
  encoding?: string | null;
  columns: string[];
  rows: CsvRow[];
  returned_rows: number;
  total_rows: number;
  size_bytes?: number | null;
  modified_at?: string | null;
}

export interface SaveCsvFileBody {
  path: string;
  columns: string[];
  rows: CsvRow[];
  delimiter: string;
}

export interface SaveCsvCopyBody {
  source_path: string;
  target_path: string;
  columns: string[];
  rows: CsvRow[];
  delimiter: string;
}

export interface SaveCsvResponse {
  path?: string;
  target_path?: string;
  source_path?: string;
  rows?: number;
  row_count?: number;
  columns?: string[];
  size_bytes?: number | null;
  modified_at?: string | null;
  [key: string]: unknown;
}

export interface ArtifactRoot {
  path: string;
  exists?: boolean | null;
  name?: string | null;
  source?: string | null;
  is_default?: boolean | null;
  is_configured?: boolean | null;
}

export interface ArtifactPayload {
  name: string;
  path: string;
  extension?: string | null;
  size_bytes?: number | null;
  modified_at?: string | null;
  download_url?: string | null;
  read_url?: string | null;
  is_allowed: boolean;
  can_read: boolean;
  can_download: boolean;
  warning?: string | null;
  [key: string]: unknown;
}

export type ArtifactItem = ArtifactPayload;

export interface ArtifactListResponse {
  items: ArtifactItem[];
  root?: string | null;
  run_id?: string | number | null;
  observation_batch_id?: string | number | null;
}

export interface ArtifactReadResponse {
  path: string;
  content: string;
  truncated?: boolean | null;
  size_bytes?: number | null;
  encoding?: string | null;
  [key: string]: unknown;
}

export interface PathRootsEnv {
  ECOMMERCE_ARTIFACT_ROOTS?: string | null;
  ECOMMERCE_FILE_ROOTS?: string | null;
  [key: string]: string | null | undefined;
}

export interface EnvReadinessGroup {
  name: string;
  status: "configured" | "missing" | string;
  configured_keys: string[];
  missing_keys: string[];
}

export interface LocalEnvStatus {
  root_env_loaded?: boolean | null;
  deprecated_app_env_detected?: boolean | null;
  keys_loaded?: string[];
  keys_skipped_existing?: string[];
  keys_skipped_deprecated_duplicate?: string[];
  warnings?: string[];
}

export interface PathRootsResponse {
  artifact_roots: ArtifactRoot[];
  file_roots: ArtifactRoot[];
  output_roots: ArtifactRoot[];
  env: PathRootsEnv;
  env_readiness: EnvReadinessGroup[];
  local_env?: LocalEnvStatus | null;
  path_separator?: string | null;
  platform?: string | null;
}

export interface CatalogUpdateJob {
  job_id: string;
  job_type: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled" | string;
  payload?: Record<string, unknown> | null;
  result?: Record<string, unknown> | null;
  error_message?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  heartbeat_at?: string | null;
  completed_at?: string | null;
  attempt_count?: number;
  cancel_requested?: boolean;
  updated_at?: string | null;
  status_url?: string | null;
  [key: string]: unknown;
}

type _EcommerceGeneratedContractChecks = [
  AssertAssignable<SourceUrlCreateBody, EcommerceContractSourceUrlCreateRequest>,
  AssertAssignable<SourceUrlUpdateBody, EcommerceContractSourceUrlUpdateRequest>,
  AssertAssignable<SourceUrlCandidateReviewBody, EcommerceContractSourceUrlCandidateReviewRequest>,
  AssertAssignable<SourceUrlAgentReadiness, EcommerceContractSourceUrlAgentReadinessResponse>,
  AssertAssignable<PlatformHealthResponse, EcommerceContractPlatformHealthResponse>,
  AssertAssignable<PriceMonitoringSelectionBody, EcommerceContractPriceMonitoringSelectionRequest>,
  AssertAssignable<FetchPriceMonitoringBody, EcommerceContractPriceMonitoringFetchRequest>,
  AssertAssignable<CancelPriceMonitoringFetchBody, EcommerceContractPriceMonitoringFetchCancelRequest>,
  AssertAssignable<CreateAlertRuleBody, EcommerceContractAlertRuleCreateRequest>,
  AssertAssignable<UpdateAlertRuleBody, EcommerceContractAlertRuleUpdateRequest>,
  AssertAssignable<PriceMonitoringReviewAction, EcommerceSchema<"PriceActionApiInput">>,
  AssertAssignable<ApplyPriceMonitoringReviewActionsBody, EcommerceContractPriceReviewActionsRequest>,
  AssertAssignable<ExportPriceMonitoringPriceUpdateBody, EcommerceContractPriceUpdateExportRequest>,
  AssertAssignable<ReadCsvFileBody, EcommerceContractCsvReadRequest>,
  AssertAssignable<SaveCsvFileBody, EcommerceContractCsvSaveRequest>,
  AssertAssignable<SaveCsvCopyBody, EcommerceContractCsvSaveCopyRequest>,
];
