import type { MockRoute } from "../mockFetch";

export const productFactoryFilterRevision = "f1lterrev00112233445566778899";
export const productFactoryFilterWriteRevision = "f1lterrev99112233445566778899";

export const productFactoryHealth = {
  status: "ok",
  service: "product-factory",
  version: "test-fixture",
};

export const productFactoryJobs = [
  {
    job_id: "job-queued-1",
    job_type: "prepare",
    model: "005606",
    status: "queued",
    workflow: "prepare",
    created_at: "2026-05-02T08:00:00Z",
    updated_at: "2026-05-02T08:00:00Z",
    request: { model: "005606" },
  },
  {
    job_id: "job-running-1",
    job_type: "render",
    model: "005606",
    status: "running",
    workflow: "render",
    created_at: "2026-05-02T08:05:00Z",
    updated_at: "2026-05-02T08:06:00Z",
    request: { model: "005606" },
  },
  {
    job_id: "job-succeeded-1",
    job_type: "publish",
    model: "005606",
    status: "succeeded",
    workflow: "publish",
    created_at: "2026-05-02T07:00:00Z",
    updated_at: "2026-05-02T07:10:00Z",
    request: { model: "005606" },
  },
  {
    job_id: "job-full-pipeline-succeeded-1",
    job_type: "full_pipeline",
    model: "233541",
    status: "succeeded",
    workflow: "full_pipeline",
    created_at: "2026-05-02T06:30:00Z",
    updated_at: "2026-05-02T06:40:00Z",
    payload: {
      model: "233541",
      source_url: "https://www.electronet.gr/example",
      bestprice_status: 0,
      skroutz_status: 1,
      boxnow: 1,
      photos: 100,
      sections: 20,
      gallery_mode: "all",
    },
  },
  {
    job_id: "job-failed-1",
    job_type: "prepare",
    model: "AB-123",
    status: "failed",
    workflow: "prepare",
    created_at: "2026-05-02T06:00:00Z",
    updated_at: "2026-05-02T06:10:00Z",
    error: { message: "Image download failed" },
    request: { model: "AB-123" },
  },
  {
    job_id: "job-cancelled-1",
    job_type: "render",
    model: "AB-123",
    status: "cancelled",
    workflow: "render",
    created_at: "2026-05-02T05:00:00Z",
    updated_at: "2026-05-02T05:05:00Z",
    request: { model: "AB-123" },
  },
  {
    job_id: "job-killed-1",
    job_type: "publish",
    model: "AB-123",
    status: "killed",
    workflow: "publish",
    created_at: "2026-05-02T04:00:00Z",
    updated_at: "2026-05-02T04:05:00Z",
    error: { message: "Process killed by operator" },
    request: { model: "AB-123" },
  },
];

export const productFactoryJobDetail = {
  ...productFactoryJobs[2],
};

export const productFactoryJobLogs = {
  job_id: "job-succeeded-1",
  lines: ["Render started", "Render succeeded"],
  logs: [
    { timestamp: "2026-05-02T07:01:00Z", level: "info", message: "Render started" },
    { timestamp: "2026-05-02T07:10:00Z", level: "info", message: "Render succeeded" },
  ],
};

export const productFactoryJobArtifacts = {
  job_id: "job-succeeded-1",
  artifacts: [
    {
      name: "product-page.html",
      path: "runs/job-succeeded-1/product-page.html",
      url: "/api/jobs/job-succeeded-1/artifacts/product-page.html",
      type: "text/html",
      size: 2048,
    },
  ],
};

export const productFactorySettings = {
  schema_version: 1,
  authoring: {
    intro_text: {
      default: {
        min_words: 60,
        max_words: 140,
        max_attempts: 3,
        max_emphasized_words_percent: 35,
      },
    },
    seo_meta: {
      default: {
        meta_description_max_chars: 155,
      },
    },
  },
  settings: {
    schema_version: 1,
    authoring: {
      intro_text: {
        default: {
          min_words: 60,
          max_words: 140,
          max_attempts: 3,
          max_emphasized_words_percent: 35,
        },
      },
      seo_meta: {
        default: {
          meta_description_max_chars: 155,
        },
      },
    },
  },
};

export const productFactoryFilterStatus = {
  filter_map_base_path: "fixtures/base-filter-map.json",
  filter_map_manual_overrides_path: "fixtures/manual-filter-overrides.json",
  filter_map_path: "fixtures/filter-map.json",
  revision: productFactoryFilterRevision,
  sync_report_path: "fixtures/filter-sync-report.json",
  valid_statuses: ["active", "inactive", "deprecated"],
  status: "ready",
  category_count: 2,
  group_count: 3,
  value_count: 6,
  filters: {
    filter_map_base_path: "fixtures/base-filter-map.json",
    filter_map_manual_overrides_path: "fixtures/manual-filter-overrides.json",
    filter_map_path: "fixtures/filter-map.json",
    revision: productFactoryFilterRevision,
    sync_report_path: "fixtures/filter-sync-report.json",
    valid_statuses: ["active", "inactive", "deprecated"],
    status: "ready",
    category_count: 2,
    group_count: 3,
    value_count: 6,
  },
};

export const productFactoryFilterCategories = {
  categories: [
    {
      category_id: 310,
      path: ["Σπίτι", "Κλιματισμός", "Αφυγραντήρες"],
      parent_category: "Κλιματισμός",
      leaf_category: "Αφυγραντήρες",
      sub_category: "Αφυγραντήρες",
      key: "climate/dehumidifiers",
      group_count: 2,
      active_group_count: 2,
      required_group_count: 1,
      inactive_group_count: 0,
      deprecated_group_count: 0,
      source: "merged",
    },
    {
      category_id: 311,
      path: ["Τεχνολογία", "Περιφερειακά", "Πληκτρολόγια"],
      parent_category: "Περιφερειακά",
      leaf_category: "Πληκτρολόγια",
      sub_category: "Πληκτρολόγια",
      key: "tech/keyboards",
      group_count: 1,
      active_group_count: 1,
      required_group_count: 0,
      inactive_group_count: 0,
      deprecated_group_count: 0,
      source: "base",
    },
  ],
};

export const productFactoryFilterCategoryDetail = {
  category_id: 310,
  path: ["Σπίτι", "Κλιματισμός", "Αφυγραντήρες"],
  parent_category: "Κλιματισμός",
  leaf_category: "Αφυγραντήρες",
  sub_category: "Αφυγραντήρες",
  key: "climate/dehumidifiers",
  revision: productFactoryFilterRevision,
  source: "merged",
  groups: [
    {
      group_id: "grp-capacity",
      name: "Χωρητικότητα",
      required: true,
      status: "active",
      source: "base",
      values: [
        { value_id: "val-12l", value: "12L", status: "active", source: "base" },
        { value_id: "val-20l", value: "20L", status: "active", source: "manual" },
      ],
    },
    {
      group_id: "grp-wifi",
      name: "Wi-Fi",
      required: false,
      status: "active",
      source: "manual",
      values: [
        { value_id: "val-yes", value: "Ναι", status: "active", source: "manual" },
        { value_id: "val-no", value: "Όχι", status: "active", source: "manual" },
      ],
    },
  ],
  category: {
    category_id: 310,
    path: ["Σπίτι", "Κλιματισμός", "Αφυγραντήρες"],
    parent_category: "Κλιματισμός",
    leaf_category: "Αφυγραντήρες",
    sub_category: "Αφυγραντήρες",
    key: "climate/dehumidifiers",
    revision: productFactoryFilterRevision,
    source: "merged",
    groups: [
      {
        group_id: "grp-capacity",
        name: "Χωρητικότητα",
        required: true,
        status: "active",
        source: "base",
        values: [
          { value_id: "val-12l", value: "12L", status: "active", source: "base" },
          { value_id: "val-20l", value: "20L", status: "active", source: "manual" },
        ],
      },
      {
        group_id: "grp-wifi",
        name: "Wi-Fi",
        required: false,
        status: "active",
        source: "manual",
        values: [
          { value_id: "val-yes", value: "Ναι", status: "active", source: "manual" },
          { value_id: "val-no", value: "Όχι", status: "active", source: "manual" },
        ],
      },
    ],
  },
};

export const productFactoryFilterCategoryWriteDetail = {
  ...productFactoryFilterCategoryDetail,
  revision: productFactoryFilterWriteRevision,
  category: {
    ...productFactoryFilterCategoryDetail.category,
    revision: productFactoryFilterWriteRevision,
  },
};

export const productFactoryFilterSyncResponse = {
  status: "synced",
  revision: productFactoryFilterWriteRevision,
  filter_map_path: "fixtures/filter-map.json",
  sync_report_path: "fixtures/filter-sync-report.json",
  category_count: 2,
  group_count: 3,
  value_count: 6,
  warning_count: 1,
  overridden_group_count: 1,
  overridden_value_count: 1,
};

export const productFactoryFilterSyncReport = {
  mode: "mocked",
  warnings: [{ category_id: 310, message: "Manual value overrides base value" }],
  overridden_groups: [{ category_id: 310, group_id: "grp-wifi" }],
  overridden_values: [{ category_id: 310, value_id: "val-20l" }],
  report: {
    mode: "mocked",
    base_path: "fixtures/base-filter-map.json",
    manual_overrides_path: "fixtures/manual-filter-overrides.json",
    filter_map_path: "fixtures/filter-map.json",
    warnings: [{ category_id: 310, message: "Manual value overrides base value" }],
    overridden_groups: [{ category_id: 310, group_id: "grp-wifi" }],
    overridden_values: [{ category_id: 310, value_id: "val-20l" }],
  },
};

export const productFactoryFilterReview = {
  model: "005606",
  category_id: 310,
  taxonomy_path: ["Σπίτι", "Κλιματισμός", "Αφυγραντήρες"],
  filter_category_found: true,
  approved: false,
  render_blocked: false,
  groups: [
    {
      group_id: "grp-capacity",
      group_name: "Χωρητικότητα",
      required: true,
      status: "active",
      allowed_values: ["12L", "20L"],
      resolved_value: "20L",
      reviewed_value: "20L",
      effective_value: "20L",
      effective_value_id: "val-20l",
      source: "manual",
    },
  ],
  warnings: ["Review before render"],
  review_artifact_path: "runs/005606/filter-review.json",
  review: {
    model: "005606",
    category_id: 310,
    taxonomy_path: ["Σπίτι", "Κλιματισμός", "Αφυγραντήρες"],
    filter_category_found: true,
    approved: false,
    render_blocked: false,
    groups: [
      {
        group_id: "grp-capacity",
        group_name: "Χωρητικότητα",
        required: true,
        status: "active",
        allowed_values: ["12L", "20L"],
        resolved_value: "20L",
        reviewed_value: "20L",
        effective_value: "20L",
        effective_value_id: "val-20l",
        source: "manual",
      },
    ],
    warnings: ["Review before render"],
    review_artifact_path: "runs/005606/filter-review.json",
  },
};

export const productFactoryAuthoring = {
  model: "005606",
  llm_dir: "runs/005606/llm",
  intro_text: {
    status: "succeeded",
    output_path: "runs/005606/intro.txt",
    word_count: 112,
    min_words: 60,
    max_words: 140,
    max_attempts: 3,
    errors: [],
  },
  seo_meta: {
    status: "succeeded",
    output_path: "runs/005606/seo.json",
    max_attempts: 3,
    errors: [],
  },
  ready_for_render: true,
  render_block_reasons: [],
  warnings: [],
  authoring: {
    model: "005606",
    llm_dir: "runs/005606/llm",
    intro_text: {
      status: "succeeded",
      output_path: "runs/005606/intro.txt",
      word_count: 112,
      min_words: 60,
      max_words: 140,
      max_attempts: 3,
      errors: [],
    },
    seo_meta: {
      status: "succeeded",
      output_path: "runs/005606/seo.json",
      max_attempts: 3,
      errors: [],
    },
    ready_for_render: true,
    render_block_reasons: [],
    warnings: [],
  },
};

export const productFactoryConflictError = {
  status: 409,
  body: { detail: "A job is already running for model 005606." },
};

export const productFactoryFilterStaleRevisionError = {
  status: 409,
  body: { detail: "Filter map revision mismatch. Reload category before saving." },
};

export const productFactoryValidationError = {
  status: 422,
  body: {
    detail: [
      { loc: ["body", "model"], msg: "Model is required" },
      { loc: ["body", "url"], msg: "URL is invalid" },
    ],
  },
};

export const productFactoryFixtureRoutes: MockRoute[] = [
  { method: "GET", path: "/api/health", response: productFactoryHealth },
  { method: "GET", path: "/api/jobs", response: { jobs: productFactoryJobs } },
  {
    method: "GET",
    path: "/api/jobs/by-model/005606",
    response: { jobs: productFactoryJobs.filter((job) => job.model === "005606") },
  },
  {
    method: "GET",
    path: "/api/jobs/by-model/AB-123",
    response: { jobs: productFactoryJobs.filter((job) => job.model === "AB-123") },
  },
  { method: "GET", path: "/api/jobs/job-succeeded-1", response: productFactoryJobDetail },
  { method: "GET", path: "/api/jobs/job-succeeded-1/logs", response: productFactoryJobLogs },
  { method: "GET", path: "/api/jobs/job-succeeded-1/artifacts", response: productFactoryJobArtifacts },
  { method: "GET", path: "/api/settings", response: productFactorySettings },
  { method: "GET", path: "/api/filters/status", response: productFactoryFilterStatus },
  { method: "GET", path: "/api/filters/categories", response: productFactoryFilterCategories },
  {
    method: "GET",
    path: "/api/filters/categories/310",
    response: productFactoryFilterCategoryDetail,
  },
  {
    method: "PUT",
    path: "/api/filters/categories/310/groups",
    requestExample: {
      expected_revision: productFactoryFilterRevision,
      name: "Ενεργειακή κλάση",
      required: false,
      status: "active",
    },
    response: productFactoryFilterCategoryWriteDetail,
  },
  {
    method: "PATCH",
    path: "/api/filters/categories/310/groups/grp-capacity",
    requestExample: {
      expected_revision: productFactoryFilterRevision,
      name: "Χωρητικότητα",
      required: true,
      status: "active",
    },
    response: productFactoryFilterCategoryWriteDetail,
  },
  {
    method: "PUT",
    path: "/api/filters/categories/310/groups/grp-wifi/values",
    requestExample: {
      expected_revision: productFactoryFilterRevision,
      value: "Μερικώς",
      status: "active",
    },
    response: productFactoryFilterCategoryWriteDetail,
  },
  {
    method: "PATCH",
    path: "/api/filters/categories/310/groups/grp-wifi/values/val-yes",
    requestExample: {
      expected_revision: productFactoryFilterRevision,
      value: "Ναι",
      status: "active",
    },
    response: productFactoryFilterCategoryWriteDetail,
  },
  { method: "POST", path: "/api/filters/sync", response: productFactoryFilterSyncResponse },
  { method: "GET", path: "/api/filters/sync-report", response: productFactoryFilterSyncReport },
  { method: "GET", path: "/api/filter-review/005606", response: productFactoryFilterReview },
  { method: "PUT", path: "/api/filter-review/005606", response: productFactoryFilterReview },
  { method: "POST", path: "/api/filter-review/005606/approve", response: productFactoryFilterReview },
  {
    method: "POST",
    path: /\/api\/jobs\/[^/]+\/retry$/,
    contractPath: "/api/jobs/{job_id}/retry",
    response: { job: { ...productFactoryJobs[3], job_id: "233541-full_pipeline-retry", status: "queued" } },
  },
  {
    method: "POST",
    path: /\/api\/jobs\/[^/]+\/start$/,
    contractPath: "/api/jobs/{job_id}/start",
    response: { job: { ...productFactoryJobs[3], job_id: "233541-full_pipeline-start", status: "queued" } },
  },
  { method: "GET", path: "/api/authoring/005606", response: productFactoryAuthoring },
];
