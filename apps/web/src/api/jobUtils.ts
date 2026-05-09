import type { AuthoringJobSubtype, Job, WorkflowType } from "./types";

const ACTIVE_STATUSES = new Set([
  "queued",
  "pending",
  "running",
  "in_progress",
  "preparing",
  "rendering",
  "publishing",
]);

const SUCCESS_STATUSES = new Set(["succeeded", "success", "completed", "done"]);
const FAILURE_STATUSES = new Set(["failed", "failure", "error", "killed"]);
const CANCELLED_STATUSES = new Set(["cancelled", "canceled"]);
export type JobStatusBucket = "active" | "succeeded" | "failed" | "cancelled" | "unknown";
const WORKFLOW_LABELS: Record<WorkflowType, string> = {
  prepare: "Prepare",
  authoring: "Authoring",
  filter_review: "Filter Review",
  render: "Render",
  publish: "Publish",
};

const STAGE_STATUSES: Record<string, WorkflowType> = {
  preparing: "prepare",
  authoring: "authoring",
  authoring_intro: "authoring",
  authoring_seo: "authoring",
  intro_text: "authoring",
  seo_meta: "authoring",
  filter_review: "filter_review",
  "filter-review": "filter_review",
  rendering: "render",
  publishing: "publish",
};

function normalizeStageValue(value: unknown): WorkflowType | undefined {
  if (typeof value !== "string") {
    return undefined;
  }

  const normalized = value.trim().toLowerCase();
  if (
    normalized === "prepare" ||
    normalized === "authoring" ||
    normalized === "filter_review" ||
    normalized === "render" ||
    normalized === "publish"
  ) {
    return normalized;
  }

  if (normalized === "authoring_intro" || normalized === "authoring_seo" || normalized === "intro_text" || normalized === "seo_meta") {
    return "authoring";
  }
  if (normalized === "filter-review") {
    return "filter_review";
  }

  return undefined;
}

export function getJobIdentifier(job: Job): string | undefined {
  const rawId = job.job_id ?? job.id;
  if (typeof rawId === "string" && rawId.trim().length > 0) {
    return rawId;
  }

  if (typeof rawId === "number") {
    return String(rawId);
  }

  return undefined;
}

export function getJobStatus(job: Job | undefined): string {
  const rawStatus = job?.status ?? job?.state;
  return typeof rawStatus === "string" && rawStatus.trim().length > 0
    ? rawStatus
    : "unknown";
}

export function getNormalizedStatus(job: Job | undefined): string {
  return getJobStatus(job).trim().toLowerCase();
}

export function isActiveJob(job: Job | undefined): boolean {
  return ACTIVE_STATUSES.has(getNormalizedStatus(job));
}

export function isCancelledJob(job: Job | undefined): boolean {
  return CANCELLED_STATUSES.has(getNormalizedStatus(job));
}

export function isSuccessfulJob(job: Job | undefined): boolean {
  return SUCCESS_STATUSES.has(getNormalizedStatus(job));
}

export function isFailedJob(job: Job | undefined): boolean {
  return FAILURE_STATUSES.has(getNormalizedStatus(job));
}

export function canStopJob(job: Job | undefined): boolean {
  return Boolean(job && getJobIdentifier(job) && isActiveJob(job));
}

export function canRetryJob(job: Job | undefined): boolean {
  return Boolean(job && getJobIdentifier(job) && (isFailedJob(job) || isCancelledJob(job)));
}

export function getJobStatusBucket(job: Job | undefined): JobStatusBucket {
  if (isActiveJob(job)) {
    return "active";
  }

  if (isSuccessfulJob(job)) {
    return "succeeded";
  }

  if (isFailedJob(job)) {
    return "failed";
  }

  if (isCancelledJob(job)) {
    return "cancelled";
  }

  return "unknown";
}

function getTimestamp(value: unknown): number | null {
  if (typeof value !== "string" || value.trim().length === 0) {
    return null;
  }

  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? null : parsed;
}

export function compareJobsByUpdatedDesc(a: Job, b: Job): number {
  const aUpdated = getTimestamp(a.updated_at);
  const bUpdated = getTimestamp(b.updated_at);
  if (aUpdated !== null || bUpdated !== null) {
    return (bUpdated ?? Number.NEGATIVE_INFINITY) - (aUpdated ?? Number.NEGATIVE_INFINITY);
  }

  const aCreated = getTimestamp(a.created_at);
  const bCreated = getTimestamp(b.created_at);
  if (aCreated !== null || bCreated !== null) {
    return (bCreated ?? Number.NEGATIVE_INFINITY) - (aCreated ?? Number.NEGATIVE_INFINITY);
  }

  return (getJobIdentifier(a) ?? "").localeCompare(getJobIdentifier(b) ?? "");
}

export function getJobWorkflow(job: Job): string {
  const rawWorkflow = job.workflow ?? job.job_type ?? job.type ?? job.kind;
  return typeof rawWorkflow === "string" && rawWorkflow.trim().length > 0
    ? rawWorkflow
    : "job";
}

export function withJobStage(job: Job, stage: WorkflowType): Job {
  return { ...job, client_stage: stage };
}

export function getJobStage(job: Job): WorkflowType | undefined {
  return (
    normalizeStageValue(job.client_stage) ??
    normalizeStageValue(job.stage) ??
    normalizeStageValue(job.workflow_stage) ??
    normalizeStageValue(job.pipeline_stage) ??
    normalizeStageValue(job.workflow) ??
    normalizeStageValue(job.job_type) ??
    normalizeStageValue(job.type) ??
    normalizeStageValue(job.kind) ??
    STAGE_STATUSES[getNormalizedStatus(job)]
  );
}

export function getJobStageLabel(job: Job): string {
  const stage = getJobStage(job);
  return stage ? WORKFLOW_LABELS[stage] : getJobWorkflow(job);
}

export function getAuthoringJobSubtype(job: Job | undefined): AuthoringJobSubtype | undefined {
  if (!job) {
    return undefined;
  }

  const values = [job.job_type, job.type, job.kind, job.stage, job.workflow_stage, job.pipeline_stage, job.workflow]
    .filter((value): value is string => typeof value === "string")
    .map((value) => value.trim().toLowerCase());
  if (values.some((value) => value === "authoring_intro" || value === "intro_text")) {
    return "intro_text";
  }
  if (values.some((value) => value === "authoring_seo" || value === "seo_meta")) {
    return "seo_meta";
  }

  const jobId = getJobIdentifier(job)?.toLowerCase() ?? "";
  if (jobId.includes("-authoring_intro-")) {
    return "intro_text";
  }
  if (jobId.includes("-authoring_seo-")) {
    return "seo_meta";
  }

  return undefined;
}

export function getRequestPayload(job: Job): unknown {
  return job.request_payload ?? job.request ?? job.payload ?? job.input ?? null;
}

export function formatDateTime(value: unknown): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    return "-";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString();
}
