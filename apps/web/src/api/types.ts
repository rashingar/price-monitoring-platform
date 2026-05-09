import type { components as ProductFactoryOpenApi } from "./generated/productFactory";

type ProductFactorySchema<Name extends keyof ProductFactoryOpenApi["schemas"]> =
  ProductFactoryOpenApi["schemas"][Name];
type AssertAssignable<Actual extends Expected, Expected> = true;

export type ProductFactoryContractHealthResponse = ProductFactorySchema<"HealthResponse">;
export type ProductFactoryContractJobResponse = ProductFactorySchema<"JobResponse">;
export type ProductFactoryContractAuthoringIntroJobRequest =
  ProductFactorySchema<"AuthoringIntroJobRequest">;
export type ProductFactoryContractAuthoringSeoJobRequest =
  ProductFactorySchema<"AuthoringSeoJobRequest">;
export type ProductFactoryContractAuthoringStatusResponse =
  ProductFactorySchema<"AuthoringStatusResponse">;
export type ProductFactoryContractFilterCategoryListItem =
  ProductFactorySchema<"FilterCategoryListItem">;
export type ProductFactoryContractFilterCategoryResponse =
  ProductFactorySchema<"FilterCategoryResponse">;
export type ProductFactoryContractPrepareJobRequest =
  ProductFactorySchema<"PrepareJobRequest">;
export type ProductFactoryContractRenderJobRequest = ProductFactorySchema<"RenderJobRequest">;
export type ProductFactoryContractPublishJobRequest = ProductFactorySchema<"PublishJobRequest">;
export type ProductFactoryContractStopJobRequest = ProductFactorySchema<"StopJobRequest">;
export type ProductFactoryContractAddFilterGroupRequest =
  ProductFactorySchema<"AddFilterGroupRequest">;
export type ProductFactoryContractUpdateFilterGroupRequest =
  ProductFactorySchema<"UpdateFilterGroupRequest">;
export type ProductFactoryContractAddFilterValueRequest =
  ProductFactorySchema<"AddFilterValueRequest">;
export type ProductFactoryContractUpdateFilterValueRequest =
  ProductFactorySchema<"UpdateFilterValueRequest">;

export type JobStatus = string;

export type WorkflowType = "prepare" | "authoring" | "filter_review" | "render" | "publish";
export type AuthoringJobSubtype = "intro_text" | "seo_meta";

export type ProductFactoryStageName =
  | "prepare"
  | "authoring_intro"
  | "authoring_seo"
  | "filter_review"
  | "render"
  | "publish";

export type PrepareJobRequest = ProductFactoryContractPrepareJobRequest;

export interface ModelJobRequest {
  model: string;
}

export type AuthoringIntroJobRequest = ProductFactoryContractAuthoringIntroJobRequest;
export type AuthoringSeoJobRequest = ProductFactoryContractAuthoringSeoJobRequest;

export type RenderJobRequest = ModelJobRequest;

export type PublishJobRequest = ModelJobRequest;

export interface StopJobRequest {
  reason?: string | null;
}

export interface HealthResponse {
  status?: string;
  ok?: boolean;
  message?: string;
  [key: string]: unknown;
}

export interface Job {
  job_id?: string | number;
  id?: string | number;
  status?: JobStatus;
  state?: JobStatus;
  stage?: string;
  workflow_stage?: string;
  pipeline_stage?: string;
  client_stage?: WorkflowType;
  job_type?: string;
  type?: string;
  workflow?: string;
  kind?: string;
  created_at?: string;
  updated_at?: string;
  started_at?: string;
  finished_at?: string;
  request?: unknown;
  payload?: unknown;
  request_payload?: unknown;
  input?: unknown;
  result?: unknown;
  error?: unknown;
  error_code?: unknown;
  [key: string]: unknown;
}

export interface ArtifactRecord {
  name?: string;
  path?: string;
  url?: string;
  type?: string;
  kind?: string | null;
  content_type?: string | null;
  content?: string | null;
  size?: number;
  [key: string]: unknown;
}

export type Artifact = string | ArtifactRecord;

export interface LogRecord {
  timestamp?: string;
  level?: string;
  message?: string;
  [key: string]: unknown;
}

export type LogEntry = string | LogRecord;

export interface AuthoringTaskStatus {
  status?: string;
  output_path?: string | null;
  trace_path?: string | null;
  word_count?: number | null;
  min_words?: number | null;
  max_words?: number | null;
  max_attempts?: number | null;
  emphasis_warning_codes?: string[];
  strong_span_count?: number;
  emphasized_word_count?: number;
  visible_word_count?: number;
  emphasized_word_ratio?: number;
  errors?: string[];
  [key: string]: unknown;
}

export interface AuthoringStatus {
  model: string;
  intro_text?: AuthoringTaskStatus | null;
  seo_meta?: AuthoringTaskStatus | null;
  ready_for_render?: boolean;
  render_block_reasons?: string[];
  warnings?: string[];
  [key: string]: unknown;
}

export interface FilterReviewGroup {
  group_id?: string | number | null;
  group_name?: string | null;
  required?: boolean;
  status?: string | null;
  allowed_values?: unknown[];
  resolved_value?: string | null;
  reviewed_value?: string | null;
  effective_value?: string | null;
  effective_value_id?: string | number | null;
  value_status?: string | null;
  source?: string | null;
  missing_required?: boolean;
  outside_allowed?: boolean;
  deprecated_value?: boolean;
  inactive_group?: boolean;
  emitted_if_rendered?: boolean;
  [key: string]: unknown;
}

export interface FilterReviewValueUpdate {
  group_id?: string | number | null;
  group_name?: string | null;
  value?: string | null;
  reviewed_value?: string | null;
  [key: string]: unknown;
}

export interface FilterReviewGroupUpdate {
  group_id?: string | number | null;
  group_name?: string | null;
  required?: boolean;
  status?: string | null;
  [key: string]: unknown;
}

export interface FilterReviewSaveRequest {
  values: FilterReviewValueUpdate[];
  group_updates: FilterReviewGroupUpdate[];
  new_groups?: unknown[];
  [key: string]: unknown;
}

export interface FilterReview {
  model: string;
  category_id?: string | number | null;
  taxonomy_path?: string | string[] | null;
  filter_category_found?: boolean;
  approved?: boolean;
  approved_at?: string | null;
  render_blocked?: boolean;
  render_block_reasons?: string[];
  missing_required_groups?: FilterReviewGroup[];
  groups?: FilterReviewGroup[];
  warnings?: string[];
  review_artifact_path?: string | null;
  [key: string]: unknown;
}

export interface ProductFactorySettings {
  authoring?: {
    intro_text?: {
      default?: {
        min_words?: number;
        max_words?: number;
        max_attempts?: number;
        [key: string]: unknown;
      };
      [key: string]: unknown;
    };
    seo_meta?: {
      default?: {
        meta_description_max_chars?: number;
        [key: string]: unknown;
      };
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export type FilterManagerStatus = "active" | "inactive" | "deprecated";
export type FilterManagerSource = "base" | "manual" | "merged" | string;

export interface FilterCategoryListItem {
  category_id: string | number;
  path?: string | string[] | null;
  parent_category?: string | null;
  leaf_category?: string | null;
  sub_category?: string | null;
  key?: string | null;
  group_count?: number | null;
  active_group_count?: number | null;
  required_group_count?: number | null;
  inactive_group_count?: number | null;
  deprecated_group_count?: number | null;
  source?: FilterManagerSource | null;
  [key: string]: unknown;
}

export interface FilterCategoryDetail {
  category_id: string | number;
  path?: string | string[] | null;
  parent_category?: string | null;
  leaf_category?: string | null;
  sub_category?: string | null;
  key?: string | null;
  revision?: string | null;
  source?: FilterManagerSource | null;
  groups?: FilterGroup[];
  [key: string]: unknown;
}

export interface FilterGroup {
  group_id: string | number;
  name?: string | null;
  required?: boolean;
  status?: FilterManagerStatus | string | null;
  source?: FilterManagerSource | null;
  values?: FilterValue[];
  [key: string]: unknown;
}

export interface FilterValue {
  value_id: string | number;
  value?: string | null;
  status?: FilterManagerStatus | string | null;
  source?: FilterManagerSource | null;
  [key: string]: unknown;
}

export interface AddFilterGroupRequest {
  expected_revision?: string | null;
  name: string;
  required: boolean;
  status: FilterManagerStatus;
}

export interface UpdateFilterGroupRequest {
  expected_revision?: string | null;
  name?: string;
  required?: boolean;
  status?: FilterManagerStatus;
}

export interface AddFilterValueRequest {
  expected_revision?: string | null;
  value: string;
  status: FilterManagerStatus;
}

export interface UpdateFilterValueRequest {
  expected_revision?: string | null;
  value?: string;
  status?: FilterManagerStatus;
}

export interface FilterSyncResponse {
  status?: string;
  revision?: string | null;
  filter_map_path?: string | null;
  sync_report_path?: string | null;
  category_count?: number | null;
  group_count?: number | null;
  value_count?: number | null;
  warning_count?: number | null;
  overridden_group_count?: number | null;
  overridden_value_count?: number | null;
  [key: string]: unknown;
}

export interface FilterSyncReport {
  mode?: string | null;
  base_path?: string | null;
  manual_overrides_path?: string | null;
  filter_map_path?: string | null;
  warnings?: unknown[];
  overridden_groups?: unknown[];
  overridden_values?: unknown[];
  [key: string]: unknown;
}

export interface FilterManagerStatusResponse {
  status?: string;
  revision?: string | null;
  [key: string]: unknown;
}

type _ProductFactoryGeneratedContractChecks = [
  AssertAssignable<HealthResponse, ProductFactoryContractHealthResponse>,
  AssertAssignable<PrepareJobRequest, ProductFactoryContractPrepareJobRequest>,
  AssertAssignable<ProductFactoryContractFilterCategoryListItem, FilterCategoryListItem>,
  AssertAssignable<ProductFactoryContractFilterCategoryResponse, FilterCategoryDetail>,
  AssertAssignable<AuthoringIntroJobRequest, ProductFactoryContractAuthoringIntroJobRequest>,
  AssertAssignable<AuthoringSeoJobRequest, ProductFactoryContractAuthoringSeoJobRequest>,
  AssertAssignable<RenderJobRequest, ProductFactoryContractRenderJobRequest>,
  AssertAssignable<PublishJobRequest, ProductFactoryContractPublishJobRequest>,
  AssertAssignable<StopJobRequest, ProductFactoryContractStopJobRequest>,
  AssertAssignable<AddFilterGroupRequest, ProductFactoryContractAddFilterGroupRequest>,
  AssertAssignable<UpdateFilterGroupRequest, ProductFactoryContractUpdateFilterGroupRequest>,
  AssertAssignable<AddFilterValueRequest, ProductFactoryContractAddFilterValueRequest>,
  AssertAssignable<UpdateFilterValueRequest, ProductFactoryContractUpdateFilterValueRequest>,
];
