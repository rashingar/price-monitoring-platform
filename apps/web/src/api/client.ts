import type {
  Artifact,
  AuthoringStatus,
  AuthoringTaskStatus,
  AddFilterGroupRequest,
  AddFilterValueRequest,
  FilterCategoryDetail,
  FilterCategoryListItem,
  FilterManagerStatusResponse,
  FilterReview,
  FilterReviewSaveRequest,
  FilterSyncReport,
  FilterSyncResponse,
  HealthResponse,
  Job,
  LogEntry,
  PrepareJobRequest,
  ProductFactorySettings,
  PublishJobRequest,
  RenderJobRequest,
  StopJobRequest,
  UpdateFilterGroupRequest,
  UpdateFilterValueRequest,
} from "./types";
import { withJobStage } from "./jobUtils";

const DEFAULT_API_BASE_URL = "";

const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, "");
const apiBaseUrl =
  configuredApiBaseUrl && configuredApiBaseUrl.length > 0
    ? configuredApiBaseUrl
    : DEFAULT_API_BASE_URL;

export class ApiError extends Error {
  readonly status: number;
  readonly details: unknown;

  constructor(message: string, status: number, details: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

type ApiRequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getPayloadMessage(payload: unknown): string | null {
  if (typeof payload === "string" && payload.trim().length > 0) {
    return payload;
  }

  if (Array.isArray(payload)) {
    const messages = payload
      .map((item) => getPayloadMessage(item))
      .filter((message): message is string => Boolean(message));
    return messages.length > 0 ? messages.join("; ") : null;
  }

  if (!isRecord(payload)) {
    return null;
  }

  for (const key of ["message", "detail", "error"]) {
    const value = payload[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return value;
    }

    const nestedMessage = getPayloadMessage(value);
    if (nestedMessage) {
      return nestedMessage;
    }
  }

  const validationMessages = Object.entries(payload)
    .flatMap(([key, value]) => {
      const message = getPayloadMessage(value);
      return message ? [`${key}: ${message}`] : [];
    })
    .slice(0, 6);
  if (validationMessages.length > 0) {
    return validationMessages.join("; ");
  }

  return null;
}

export function getApiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Something went wrong while talking to the backend.";
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

function buildHeaders(options: ApiRequestOptions): HeadersInit {
  const headers = new Headers(options.headers);
  if (options.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  return headers;
}

async function request<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...options,
    headers: buildHeaders(options),
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  const payload = await parseResponse(response);

  if (!response.ok) {
    const message = getPayloadMessage(payload) ?? `API request failed with ${response.status}`;
    throw new ApiError(message, response.status, payload);
  }

  return payload as T;
}

function unwrapRecord(payload: unknown, keys: string[]): unknown {
  if (!isRecord(payload)) {
    return payload;
  }

  for (const key of keys) {
    const value = payload[key];
    if (value !== undefined) {
      return value;
    }
  }

  return payload;
}

function looksLikeJob(record: Record<string, unknown>): boolean {
  return [
    "job_id",
    "id",
    "status",
    "state",
    "workflow",
    "job_type",
    "type",
    "kind",
    "created_at",
  ].some((key) => key in record);
}

function normalizeJob(payload: unknown): Job {
  const unwrapped =
    isRecord(payload) && !looksLikeJob(payload)
      ? unwrapRecord(payload, ["job", "data", "result"])
      : payload;
  return isRecord(unwrapped) ? (unwrapped as Job) : { result: unwrapped };
}

function normalizeJobList(payload: unknown): Job[] {
  const unwrapped = unwrapRecord(payload, ["jobs", "items", "data", "results"]);
  const list = Array.isArray(unwrapped)
    ? unwrapped
    : unwrapRecord(unwrapped, ["jobs", "items", "data", "results"]);
  return Array.isArray(list) ? (list.filter(isRecord) as Job[]) : [];
}

function normalizeLogs(payload: unknown): LogEntry[] {
  const unwrapped = unwrapRecord(payload, ["logs", "lines", "items", "data", "results"]);
  const list = Array.isArray(unwrapped)
    ? unwrapped
    : unwrapRecord(unwrapped, ["logs", "lines", "items", "data", "results"]);

  if (typeof list === "string") {
    return list.length > 0 ? [list] : [];
  }

  return Array.isArray(list)
    ? (list.filter((entry) => typeof entry === "string" || isRecord(entry)) as LogEntry[])
    : [];
}

function normalizeArtifacts(payload: unknown): Artifact[] {
  const unwrapped = unwrapRecord(payload, ["artifacts", "items", "data", "results"]);
  const list = Array.isArray(unwrapped)
    ? unwrapped
    : unwrapRecord(unwrapped, ["artifacts", "items", "data", "results"]);
  return Array.isArray(list)
    ? (list.filter((entry) => typeof entry === "string" || isRecord(entry)) as Artifact[])
    : [];
}

function normalizeRecord<T extends Record<string, unknown>>(payload: unknown, keys: string[]): T {
  const unwrapped = unwrapRecord(payload, keys);
  return isRecord(unwrapped) ? (unwrapped as T) : ({} as T);
}

function normalizeRecordList<T extends Record<string, unknown>>(
  payload: unknown,
  keys: string[],
): T[] {
  const unwrapped = unwrapRecord(payload, keys);
  const list = Array.isArray(unwrapped) ? unwrapped : unwrapRecord(unwrapped, keys);
  return Array.isArray(list) ? (list.filter(isRecord) as T[]) : [];
}

function normalizeOptionalNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function normalizeOptionalStringList(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }

  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean);
}

function assignNormalizedNumber(
  target: AuthoringTaskStatus,
  source: Record<string, unknown>,
  key:
    | "strong_span_count"
    | "emphasized_word_count"
    | "visible_word_count"
    | "emphasized_word_ratio",
): void {
  if (!(key in source)) {
    return;
  }

  const normalized = normalizeOptionalNumber(source[key]);
  if (normalized === undefined) {
    delete target[key];
    return;
  }

  target[key] = normalized;
}

function normalizeAuthoringTaskStatus(
  task: AuthoringTaskStatus | null | undefined,
): AuthoringTaskStatus | null | undefined {
  if (task === null || task === undefined) {
    return task;
  }

  if (!isRecord(task)) {
    return undefined;
  }

  const normalized: AuthoringTaskStatus = { ...task };
  if ("emphasis_warning_codes" in task) {
    const warningCodes = normalizeOptionalStringList(task.emphasis_warning_codes);
    if (warningCodes === undefined) {
      delete normalized.emphasis_warning_codes;
    } else {
      normalized.emphasis_warning_codes = warningCodes;
    }
  }

  assignNormalizedNumber(normalized, task, "strong_span_count");
  assignNormalizedNumber(normalized, task, "emphasized_word_count");
  assignNormalizedNumber(normalized, task, "visible_word_count");
  assignNormalizedNumber(normalized, task, "emphasized_word_ratio");

  return normalized;
}

function normalizeAuthoringStatus(payload: unknown): AuthoringStatus {
  const status = normalizeRecord<AuthoringStatus>(payload, ["authoring", "status", "data", "result"]);
  return {
    ...status,
    intro_text: normalizeAuthoringTaskStatus(status.intro_text),
    seo_meta: normalizeAuthoringTaskStatus(status.seo_meta),
  };
}

export const apiClient = {
  apiBaseUrl,

  getHealth(signal?: AbortSignal): Promise<HealthResponse> {
    return request<HealthResponse>("/api/health", { signal });
  },

  async createPrepareJob(body: PrepareJobRequest): Promise<Job> {
    return withJobStage(
      normalizeJob(await request<unknown>("/api/jobs/prepare", { method: "POST", body })),
      "prepare",
    );
  },

  async createRenderJob(body: RenderJobRequest): Promise<Job> {
    return withJobStage(
      normalizeJob(await request<unknown>("/api/jobs/render", { method: "POST", body })),
      "render",
    );
  },

  async createPublishJob(body: PublishJobRequest): Promise<Job> {
    return withJobStage(
      normalizeJob(await request<unknown>("/api/jobs/publish", { method: "POST", body })),
      "publish",
    );
  },

  async listJobs(signal?: AbortSignal): Promise<Job[]> {
    return normalizeJobList(await request<unknown>("/api/jobs", { signal }));
  },

  async listJobsByModel(model: string, signal?: AbortSignal): Promise<Job[]> {
    return normalizeJobList(
      await request<unknown>(`/api/jobs/by-model/${encodeURIComponent(model)}`, { signal }),
    );
  },

  async getJob(jobId: string, signal?: AbortSignal): Promise<Job> {
    return normalizeJob(
      await request<unknown>(`/api/jobs/${encodeURIComponent(jobId)}`, { signal }),
    );
  },

  async stopJob(jobId: string, reason?: string): Promise<Job> {
    const body: StopJobRequest = reason === undefined ? {} : { reason };
    return normalizeJob(
      await request<unknown>(`/api/jobs/${encodeURIComponent(jobId)}/stop`, {
        method: "POST",
        body,
      }),
    );
  },

  async retryJob(jobId: string): Promise<Job> {
    return normalizeJob(
      await request<unknown>(`/api/jobs/${encodeURIComponent(jobId)}/retry`, {
        method: "POST",
      }),
    );
  },

  async getJobLogs(jobId: string, signal?: AbortSignal): Promise<LogEntry[]> {
    return normalizeLogs(
      await request<unknown>(`/api/jobs/${encodeURIComponent(jobId)}/logs`, { signal }),
    );
  },

  async getJobArtifacts(jobId: string, signal?: AbortSignal): Promise<Artifact[]> {
    return normalizeArtifacts(
      await request<unknown>(`/api/jobs/${encodeURIComponent(jobId)}/artifacts`, { signal }),
    );
  },

  async getAuthoringStatus(model: string, signal?: AbortSignal): Promise<AuthoringStatus> {
    return normalizeAuthoringStatus(
      await request<unknown>(`/api/authoring/${encodeURIComponent(model)}`, { signal }),
    );
  },

  async runIntroText(model: string): Promise<AuthoringStatus> {
    return normalizeAuthoringStatus(
      await request<unknown>(`/api/authoring/${encodeURIComponent(model)}/intro-text`, {
        method: "POST",
      }),
    );
  },

  async retryIntroText(model: string): Promise<AuthoringStatus> {
    return normalizeAuthoringStatus(
      await request<unknown>(`/api/authoring/${encodeURIComponent(model)}/intro-text/retry`, {
        method: "POST",
      }),
    );
  },

  async runSeoMeta(model: string): Promise<AuthoringStatus> {
    return normalizeAuthoringStatus(
      await request<unknown>(`/api/authoring/${encodeURIComponent(model)}/seo-meta`, {
        method: "POST",
      }),
    );
  },

  async retrySeoMeta(model: string): Promise<AuthoringStatus> {
    return normalizeAuthoringStatus(
      await request<unknown>(`/api/authoring/${encodeURIComponent(model)}/seo-meta/retry`, {
        method: "POST",
      }),
    );
  },

  async getFilterReview(model: string, signal?: AbortSignal): Promise<FilterReview> {
    return normalizeRecord<FilterReview>(
      await request<unknown>(`/api/filter-review/${encodeURIComponent(model)}`, { signal }),
      ["review", "filter_review", "data", "result"],
    );
  },

  async saveFilterReview(
    model: string,
    body: FilterReviewSaveRequest | FilterReview,
  ): Promise<FilterReview> {
    return normalizeRecord<FilterReview>(
      await request<unknown>(`/api/filter-review/${encodeURIComponent(model)}`, {
        method: "PUT",
        body,
      }),
      ["review", "filter_review", "data", "result"],
    );
  },

  async approveFilterReview(model: string): Promise<FilterReview> {
    return normalizeRecord<FilterReview>(
      await request<unknown>(`/api/filter-review/${encodeURIComponent(model)}/approve`, {
        method: "POST",
      }),
      ["review", "filter_review", "data", "result"],
    );
  },

  async getSettings(signal?: AbortSignal): Promise<ProductFactorySettings> {
    return normalizeRecord<ProductFactorySettings>(
      await request<unknown>("/api/settings", { signal }),
      ["settings", "data", "result"],
    );
  },

  async patchSettings(body: ProductFactorySettings): Promise<ProductFactorySettings> {
    return normalizeRecord<ProductFactorySettings>(
      await request<unknown>("/api/settings", { method: "PATCH", body }),
      ["settings", "data", "result"],
    );
  },

  async listFilterCategories(signal?: AbortSignal): Promise<FilterCategoryListItem[]> {
    return normalizeRecordList<FilterCategoryListItem>(
      await request<unknown>("/api/filters/categories", { signal }),
      ["categories", "items", "data", "results"],
    );
  },

  async getFilterCategory(
    categoryId: string | number,
    signal?: AbortSignal,
  ): Promise<FilterCategoryDetail> {
    return normalizeRecord<FilterCategoryDetail>(
      await request<unknown>(`/api/filters/categories/${encodeURIComponent(String(categoryId))}`, {
        signal,
      }),
      ["category", "data", "result"],
    );
  },

  async addFilterGroup(
    categoryId: string | number,
    body: AddFilterGroupRequest,
  ): Promise<FilterCategoryDetail> {
    return normalizeRecord<FilterCategoryDetail>(
      await request<unknown>(
        `/api/filters/categories/${encodeURIComponent(String(categoryId))}/groups`,
        {
          method: "PUT",
          body,
        },
      ),
      ["category", "group", "data", "result"],
    );
  },

  async updateFilterGroup(
    categoryId: string | number,
    groupId: string | number,
    body: UpdateFilterGroupRequest,
  ): Promise<FilterCategoryDetail> {
    return normalizeRecord<FilterCategoryDetail>(
      await request<unknown>(
        `/api/filters/categories/${encodeURIComponent(String(categoryId))}/groups/${encodeURIComponent(String(groupId))}`,
        {
          method: "PATCH",
          body,
        },
      ),
      ["category", "group", "data", "result"],
    );
  },

  async addFilterValue(
    categoryId: string | number,
    groupId: string | number,
    body: AddFilterValueRequest,
  ): Promise<FilterCategoryDetail> {
    return normalizeRecord<FilterCategoryDetail>(
      await request<unknown>(
        `/api/filters/categories/${encodeURIComponent(String(categoryId))}/groups/${encodeURIComponent(String(groupId))}/values`,
        {
          method: "PUT",
          body,
        },
      ),
      ["category", "value", "data", "result"],
    );
  },

  async updateFilterValue(
    categoryId: string | number,
    groupId: string | number,
    valueId: string | number,
    body: UpdateFilterValueRequest,
  ): Promise<FilterCategoryDetail> {
    return normalizeRecord<FilterCategoryDetail>(
      await request<unknown>(
        `/api/filters/categories/${encodeURIComponent(String(categoryId))}/groups/${encodeURIComponent(String(groupId))}/values/${encodeURIComponent(String(valueId))}`,
        {
          method: "PATCH",
          body,
        },
      ),
      ["category", "value", "data", "result"],
    );
  },

  async syncFilterMap(): Promise<FilterSyncResponse> {
    return normalizeRecord<FilterSyncResponse>(
      await request<unknown>("/api/filters/sync", { method: "POST" }),
      ["sync", "report", "data", "result"],
    );
  },

  async getFilterSyncReport(signal?: AbortSignal): Promise<FilterSyncReport> {
    return normalizeRecord<FilterSyncReport>(
      await request<unknown>("/api/filters/sync-report", { signal }),
      ["report", "sync_report", "data", "result"],
    );
  },

  async getFilterStatus(signal?: AbortSignal): Promise<FilterManagerStatusResponse> {
    return normalizeRecord<FilterManagerStatusResponse>(
      await request<unknown>("/api/filters/status", { signal }),
      ["filters", "status", "data", "result"],
    );
  },
};
