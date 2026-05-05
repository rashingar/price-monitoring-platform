export type JobStatus = string;

export type WorkflowType = "prepare" | "render" | "publish";

export type ProductAgentStageName =
  | "prepare"
  | "authoring_intro"
  | "authoring_seo"
  | "filter_review"
  | "render"
  | "publish";

export interface PrepareJobRequest {
  model: string;
  url: string;
  photos: number;
  sections: number;
  skroutz_status: number;
  boxnow: number;
  price: number | null;
}

export interface ModelJobRequest {
  model: string;
}

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
  missing_required_groups?: string[];
  groups?: FilterReviewGroup[];
  warnings?: string[];
  review_artifact_path?: string | null;
  [key: string]: unknown;
}

export interface ProductAgentSettings {
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
