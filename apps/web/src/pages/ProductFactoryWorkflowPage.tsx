import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiClient, ApiError, getApiErrorMessage } from "../api/client";
import {
  canRetryJob,
  compareJobsByUpdatedDesc,
  getJobIdentifier,
  getJobStage,
  getJobStatus,
  isActiveJob,
  isSuccessfulJob,
} from "../api/jobUtils";
import type {
  Artifact,
  AuthoringStatus,
  AuthoringTaskStatus,
  FilterReview,
  FilterReviewGroup,
  FilterReviewSaveRequest,
  HealthResponse,
  Job,
  LogEntry,
  PrepareJobRequest,
  ProductFactorySettings,
} from "../api/types";
import {
  initialPrepareFormState,
  PrepareJobForm,
  type PrepareFormState,
} from "../components/forms/PrepareJobForm";
import { ArtifactList } from "../components/jobs/ArtifactList";
import { LogsPanel } from "../components/jobs/LogsPanel";
import { StatusBadge } from "../components/jobs/StatusBadge";
import { EmptyState, ErrorState } from "../components/layout/StateBlocks";
import { useGlobalJobs } from "../hooks/useGlobalJobs";
import { usePersistentPageState } from "../hooks/usePersistentPageState";

const POLL_INTERVAL_MS = 2500;
const JOB_COMPLETION_TIMEOUT_MS = 30 * 60 * 1000;
const WORKFLOW_STORAGE_KEY = "product-factory-ui:workflow-shell:v1";
const INTRO_EMPHASIS_MISSING_CODE = "llm_intro_text_emphasis_missing";
const HARD_INTRO_EMPHASIS_CODES = new Set([
  "llm_intro_text_emphasis_invalid",
  "llm_intro_text_emphasis_overused",
]);

type ActionKey =
  | "prepare"
  | "authoring_load"
  | "intro_run"
  | "intro_retry"
  | "seo_run"
  | "seo_retry"
  | "filter_load"
  | "filter_save"
  | "filter_approve"
  | "render"
  | "publish"
  | "retry_prepare"
  | "retry_authoring"
  | "retry_filter_review"
  | "retry_render"
  | "retry_publish"
  | "settings_load"
  | "settings_save";

type WorkflowTab = "prepare" | "authoring" | "filter_review" | "render" | "publish";

const WORKFLOW_TABS: { key: WorkflowTab; label: string }[] = [
  { key: "prepare", label: "Prepare" },
  { key: "authoring", label: "Authoring" },
  { key: "filter_review", label: "Filter Review" },
  { key: "render", label: "Render" },
  { key: "publish", label: "Publish" },
];
const WORKFLOW_TAB_INDEX: Record<WorkflowTab, number> = {
  prepare: 0,
  authoring: 1,
  filter_review: 2,
  render: 3,
  publish: 4,
};

interface StageActionState {
  busy: Partial<Record<ActionKey, boolean>>;
  messages: Partial<Record<ActionKey, string>>;
  errors: Partial<Record<ActionKey, string>>;
}

interface JobAssetsState {
  logs: LogEntry[];
  artifacts: Artifact[];
  error: string | null;
  isLoading: boolean;
}

class WorkflowHalted extends Error {
  constructor(message: string) {
    super(message);
    this.name = "WorkflowHalted";
  }
}

interface SettingsFormState {
  introMinWords: string;
  introMaxWords: string;
  introMaxAttempts: string;
  seoMetaDescriptionMaxChars: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isApiHealthy(health: HealthResponse | null, error: string | null): boolean {
  if (error) {
    return false;
  }

  if (!health) {
    return true;
  }

  if (health.ok === false) {
    return false;
  }

  const status = typeof health.status === "string" ? health.status.toLowerCase() : "";
  return !["error", "failed", "down", "unhealthy"].includes(status);
}

function getErrorHint(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.status === 404) {
      return "Run prepare first, then refresh this stage.";
    }

    if (error.status === 409) {
      return `Blocked: ${error.message}`;
    }

    if (error.status === 422) {
      return `Invalid input: ${error.message}`;
    }
  }

  return getApiErrorMessage(error) || fallback;
}

function formatOptional(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  if (Array.isArray(value)) {
    return value.join(" > ");
  }

  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }

  return String(value);
}

function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => (typeof item === "string" ? item : formatOptional(item)))
    .filter((item) => item.trim().length > 0 && item !== "-");
}

function getJobMessage(job: Job): string | null {
  for (const value of [job.message, job.error, job.detail]) {
    if (typeof value === "string" && value.trim().length > 0) {
      return value;
    }

    if (isRecord(value)) {
      for (const key of ["message", "detail", "error"]) {
        const nestedValue = value[key];
        if (typeof nestedValue === "string" && nestedValue.trim().length > 0) {
          return nestedValue;
        }
      }
    }
  }

  return null;
}

function normalizeText(value: unknown): string {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

function getJobIdStage(job: Job, model: string): WorkflowTab | undefined {
  const jobId = getJobIdentifier(job);
  const normalizedModel = model.trim().toLowerCase();
  if (!jobId || normalizedModel.length === 0) {
    return undefined;
  }

  const normalizedJobId = jobId.toLowerCase();
  if (!normalizedJobId.startsWith(`${normalizedModel}-`)) {
    return undefined;
  }

  const remainder = normalizedJobId.slice(normalizedModel.length + 1);
  if (remainder.startsWith("prepare-")) {
    return "prepare";
  }
  if (remainder.startsWith("authoring-") || remainder.startsWith("authoring_intro-") || remainder.startsWith("authoring_seo-")) {
    return "authoring";
  }
  if (remainder.startsWith("filter-review-") || remainder.startsWith("filter_review-")) {
    return "filter_review";
  }
  if (remainder.startsWith("render-")) {
    return "render";
  }
  if (remainder.startsWith("publish-")) {
    return "publish";
  }

  return undefined;
}

function getWorkflowTabForJob(job: Job, model: string): WorkflowTab | undefined {
  const stage = getJobStage(job);
  if (stage) {
    return stage;
  }

  const rawStage = [
    job.stage,
    job.workflow_stage,
    job.pipeline_stage,
    job.workflow,
    job.job_type,
    job.type,
    job.kind,
  ].map(normalizeText);

  if (rawStage.some((value) => value === "authoring" || value === "authoring_intro" || value === "authoring_seo" || value === "intro_text" || value === "seo_meta")) {
    return "authoring";
  }

  if (rawStage.some((value) => value === "filter_review" || value === "filter-review")) {
    return "filter_review";
  }

  return getJobIdStage(job, model);
}

function getLatestJobForTab(jobs: Job[], tab: WorkflowTab, model: string): Job | null {
  return jobs
    .filter((job) => getWorkflowTabForJob(job, model) === tab)
    .sort(compareJobsByUpdatedDesc)[0] ?? null;
}

function getJobWarnings(job: Job | null): string[] {
  if (!job) {
    return [];
  }

  return [
    ...toStringList(job.warnings),
    ...toStringList(isRecord(job.result) ? job.result.warnings : undefined),
  ];
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function upsertJobById(jobs: Job[], job: Job): Job[] {
  const jobId = getJobIdentifier(job);
  if (!jobId) {
    return [job, ...jobs].sort(compareJobsByUpdatedDesc);
  }

  return [
    job,
    ...jobs.filter((candidate) => getJobIdentifier(candidate) !== jobId),
  ].sort(compareJobsByUpdatedDesc);
}

function getJobFailureMessage(job: Job, fallback: string): string {
  const candidates = [
    job.error,
    isRecord(job.error) ? job.error.message : undefined,
    isRecord(job.result) ? job.result.error : undefined,
    isRecord(job.result) && isRecord(job.result.error) ? job.result.error.message : undefined,
    job.error_code,
  ];

  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.trim().length > 0) {
      return candidate;
    }
  }

  return fallback;
}

function getRetryActionKey(tab: WorkflowTab): ActionKey {
  return `retry_${tab}` as ActionKey;
}

function getFilterReviewWarnings(filterReview: FilterReview | null): string[] {
  if (!filterReview) {
    return [];
  }

  const warnings = new Set<string>(
    toStringList(filterReview.warnings).filter(
      (warning) => warning !== "category_filter_review_not_approved",
    ),
  );
  toStringList(filterReview.render_block_reasons).forEach((reason) => {
    warnings.add(reason);
  });
  toStringList(filterReview.missing_required_groups).forEach((group) => {
    warnings.add(`Missing required filter: ${group}`);
  });
  (filterReview.groups ?? []).forEach((group) => {
    getGroupWarnings(group).forEach((warning) => {
      warnings.add(`${formatOptional(group.group_name)}: ${warning}`);
    });
  });

  return Array.from(warnings);
}

function makeFilterReviewSavePayload(filterReview: FilterReview): FilterReviewSaveRequest {
  const groups = filterReview.groups ?? [];
  return {
    values: groups
      .map((group) => {
        const reviewedValue = group.reviewed_value ?? "";
        return {
          group_id: group.group_id,
          group_name: group.group_name,
          value: reviewedValue,
          reviewed_value: reviewedValue,
        };
      })
      .filter((value) => String(value.reviewed_value ?? "").trim().length > 0),
    group_updates: groups
      .filter((group) => group.group_id !== null && group.group_id !== undefined)
      .map((group) => ({
        group_id: group.group_id,
        group_name: group.group_name,
        required: group.required === true,
        status: group.status ?? "active",
      })),
    new_groups: Array.isArray(filterReview.new_groups) ? filterReview.new_groups : [],
  };
}

function getTaskStatus(task: AuthoringTaskStatus | null | undefined): string {
  return task?.status && task.status.trim().length > 0 ? task.status : "not loaded";
}

function isAuthoringTaskValid(task: AuthoringTaskStatus | null | undefined): boolean {
  const status = getTaskStatus(task).trim().toLowerCase();
  return ["valid", "ready", "succeeded", "success", "completed", "done"].includes(status);
}

function isAuthoringReadyForRender(status: AuthoringStatus | null): boolean {
  if (!status) {
    return false;
  }

  return (
    status.ready_for_render === true ||
    (isAuthoringTaskValid(status.intro_text) && isAuthoringTaskValid(status.seo_meta))
  );
}

function hasBlockingFilterReviewWork(review: FilterReview | null): boolean {
  if (!review) {
    return true;
  }

  if (review.render_blocked === true || toStringList(review.missing_required_groups).length > 0) {
    return true;
  }

  const warnings = getFilterReviewWarnings(review);
  return review.approved !== true && warnings.length > 0;
}

function isFilterReviewReadyForRender(review: FilterReview | null): boolean {
  return Boolean(review && (review.approved === true || !hasBlockingFilterReviewWork(review)));
}

function hasHardIntroEmphasisError(task: AuthoringTaskStatus | null | undefined): boolean {
  const codes = [
    getTaskStatus(task),
    ...toStringList(task?.errors),
    ...toStringList(task?.emphasis_warning_codes),
  ];
  return codes.some((code) => HARD_INTRO_EMPHASIS_CODES.has(code));
}

function shouldShowIntroEmphasisMissingWarning(
  task: AuthoringTaskStatus | null | undefined,
): boolean {
  return (
    isAuthoringTaskValid(task) &&
    !hasHardIntroEmphasisError(task) &&
    toStringList(task?.emphasis_warning_codes).includes(INTRO_EMPHASIS_MISSING_CODE)
  );
}

function hasIntroEmphasisDiagnostics(task: AuthoringTaskStatus | null | undefined): boolean {
  return (
    toStringList(task?.emphasis_warning_codes).length > 0 ||
    task?.strong_span_count !== undefined ||
    task?.emphasized_word_count !== undefined ||
    task?.visible_word_count !== undefined ||
    task?.emphasized_word_ratio !== undefined
  );
}

function getStageStatus(status: string | null | undefined, fallback = "not loaded"): string {
  return status && status.trim().length > 0 ? status : fallback;
}

function getGroupWarnings(group: FilterReviewGroup): string[] {
  const warnings: string[] = [];
  if (group.missing_required) {
    warnings.push("Missing required");
  }
  if (group.outside_allowed) {
    warnings.push("Outside allowed");
  }
  if (group.deprecated_value) {
    warnings.push("Deprecated");
  }
  if (group.inactive_group) {
    warnings.push("Inactive group");
  }
  if (group.emitted_if_rendered === false) {
    warnings.push("Not emitted");
  }
  return warnings;
}

function allowedValueLabel(value: unknown): string {
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }

  if (isRecord(value)) {
    for (const key of ["label", "name", "value", "id"]) {
      const item = value[key];
      if (typeof item === "string" || typeof item === "number") {
        return String(item);
      }
    }
  }

  return "";
}

function makeSettingsForm(settings: ProductFactorySettings | null): SettingsFormState {
  const introDefaults = settings?.authoring?.intro_text?.default;
  const seoDefaults = settings?.authoring?.seo_meta?.default;
  return {
    introMinWords: formatOptional(introDefaults?.min_words).replace("-", ""),
    introMaxWords: formatOptional(introDefaults?.max_words).replace("-", ""),
    introMaxAttempts: formatOptional(introDefaults?.max_attempts).replace("-", ""),
    seoMetaDescriptionMaxChars: formatOptional(seoDefaults?.meta_description_max_chars).replace("-", ""),
  };
}

function parseSettingsNumber(value: string): number | null {
  const parsed = Number(value.trim());
  return Number.isInteger(parsed) ? parsed : null;
}

function makeSettingsPayload(form: SettingsFormState): {
  payload: ProductFactorySettings | null;
  error: string | null;
} {
  const minWords = parseSettingsNumber(form.introMinWords);
  const maxWords = parseSettingsNumber(form.introMaxWords);
  const maxAttempts = parseSettingsNumber(form.introMaxAttempts);
  const seoMaxChars = parseSettingsNumber(form.seoMetaDescriptionMaxChars);

  if (minWords === null || minWords <= 0) {
    return { payload: null, error: "Intro min words must be greater than 0." };
  }

  if (maxWords === null || maxWords < minWords || maxWords > 500) {
    return { payload: null, error: "Intro max words must be at least min words and no more than 500." };
  }

  if (maxAttempts === null || maxAttempts < 1 || maxAttempts > 10) {
    return { payload: null, error: "Intro max attempts must be between 1 and 10." };
  }

  if (seoMaxChars === null || seoMaxChars <= 0) {
    return { payload: null, error: "SEO meta description max chars must be a positive whole number." };
  }

  return {
    payload: {
      authoring: {
        intro_text: {
          default: {
            min_words: minWords,
            max_words: maxWords,
            max_attempts: maxAttempts,
          },
        },
        seo_meta: {
          default: {
            meta_description_max_chars: seoMaxChars,
          },
        },
      },
    },
    error: null,
  };
}

function WorkflowStage({
  title,
  status,
  description,
  children,
}: {
  title: string;
  status: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="panel workflow-stage">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Stage</p>
          <h3>{title}</h3>
          <p className="muted">{description}</p>
        </div>
        <StatusBadge status={status} />
      </div>
      {children}
    </section>
  );
}

function MessageBlock({ message, error }: { message?: string; error?: string }) {
  if (error) {
    return <p className="form-error">{error}</p>;
  }

  if (message) {
    return <p className="state-block">{message}</p>;
  }

  return null;
}

function BlockingReasons({ reasons }: { reasons: string[] }) {
  if (reasons.length === 0) {
    return null;
  }

  return (
    <div className="form-warning">
      <strong>Blocking reasons</strong>
      <ul>
        {reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
    </div>
  );
}

function PathValue({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  return (
    <div>
      <dt>{label}</dt>
      <dd>{formatOptional(value)}</dd>
    </div>
  );
}

function AuthoringTaskCard({
  title,
  task,
  onRun,
  onRetry,
  isRunBusy,
  isRetryBusy,
  runLabel,
  retryLabel,
  disabled,
  showIntroEmphasisDiagnostics = false,
}: {
  title: string;
  task: AuthoringTaskStatus | null | undefined;
  onRun: () => void;
  onRetry: () => void;
  isRunBusy: boolean;
  isRetryBusy: boolean;
  runLabel: string;
  retryLabel: string;
  disabled: boolean;
  showIntroEmphasisDiagnostics?: boolean;
}) {
  const baseErrors = toStringList(task?.errors);
  const normalizedTaskStatus = task?.status?.trim();
  const statusError =
    showIntroEmphasisDiagnostics &&
    normalizedTaskStatus &&
    HARD_INTRO_EMPHASIS_CODES.has(normalizedTaskStatus)
      ? [normalizedTaskStatus]
      : [];
  const errors = Array.from(new Set([...statusError, ...baseErrors]));
  const emphasisWarningCodes = toStringList(task?.emphasis_warning_codes);
  const showEmphasisWarning =
    showIntroEmphasisDiagnostics && shouldShowIntroEmphasisMissingWarning(task);
  const showEmphasisDiagnostics =
    showIntroEmphasisDiagnostics && hasIntroEmphasisDiagnostics(task);
  return (
    <div className="stage-card">
      <div className="section-heading">
        <div>
          <h4>{title}</h4>
          <div className="status-row">
            <StatusBadge status={getTaskStatus(task)} />
            {showEmphasisWarning ? (
              <span
                className="status-badge warning"
                title="Intro Text is valid, but no key facts are bolded yet."
              >
                Intro emphasis missing
              </span>
            ) : null}
          </div>
        </div>
        <div className="button-row">
          <button className="button primary compact-button" type="button" disabled={disabled || isRunBusy} onClick={onRun}>
            {isRunBusy ? "Running..." : runLabel}
          </button>
          <button className="button secondary compact-button" type="button" disabled={disabled || isRetryBusy} onClick={onRetry}>
            {isRetryBusy ? "Retrying..." : retryLabel}
          </button>
        </div>
      </div>

      <dl className="summary-grid workflow-summary-grid">
        <PathValue label="Word count" value={task?.word_count} />
        <PathValue label="Min words" value={task?.min_words} />
        <PathValue label="Max words" value={task?.max_words} />
        <PathValue label="Max attempts" value={task?.max_attempts} />
        <PathValue label="Output path" value={task?.output_path} />
        <PathValue label="Trace path" value={task?.trace_path} />
      </dl>

      {showEmphasisDiagnostics ? (
        <details className="diagnostic-details">
          <summary>Intro emphasis diagnostics</summary>
          <dl className="summary-grid workflow-summary-grid">
            <PathValue label="Strong span count" value={task?.strong_span_count} />
            <PathValue label="Emphasized word count" value={task?.emphasized_word_count} />
            <PathValue label="Emphasized word ratio" value={task?.emphasized_word_ratio} />
            <PathValue label="Visible word count" value={task?.visible_word_count} />
            <PathValue label="Warning codes" value={emphasisWarningCodes.join(", ")} />
          </dl>
        </details>
      ) : null}

      {errors.length > 0 ? (
        <div className="form-error">
          <strong>Validation errors</strong>
          <ul>
            {errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function JobAssets({ jobId, isJobActive }: { jobId: string; isJobActive: boolean }) {
  const [assets, setAssets] = useState<JobAssetsState>({
    logs: [],
    artifacts: [],
    error: null,
    isLoading: true,
  });

  const loadAssets = useCallback(
    async (signal?: AbortSignal) => {
      setAssets((current) => ({ ...current, isLoading: true }));
      try {
        const [logs, artifacts] = await Promise.all([
          apiClient.getJobLogs(jobId, signal),
          apiClient.getJobArtifacts(jobId, signal),
        ]);
        if (signal?.aborted) {
          return;
        }

        setAssets({ logs, artifacts, error: null, isLoading: false });
      } catch (error) {
        if (!signal?.aborted) {
          setAssets((current) => ({
            ...current,
            error: getApiErrorMessage(error),
            isLoading: false,
          }));
        }
      }
    },
    [jobId],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadAssets(controller.signal);
    return () => controller.abort();
  }, [loadAssets]);

  useEffect(() => {
    if (!isJobActive) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      void loadAssets();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [isJobActive, loadAssets]);

  return (
    <div className="stage-job-assets">
      {assets.isLoading ? <p className="muted">Loading job logs and artifacts...</p> : null}
      {assets.error ? <ErrorState message={assets.error} onRetry={() => void loadAssets()} /> : null}
      <details>
        <summary>Logs ({assets.logs.length})</summary>
        <LogsPanel logs={assets.logs} />
      </details>
      <details>
        <summary>Artifacts ({assets.artifacts.length})</summary>
        <ArtifactList artifacts={assets.artifacts} />
      </details>
    </div>
  );
}

function StageJobPanel({
  job,
  label,
  warnings,
  onRetry,
  isRetrying,
  retryError,
  retryMessage,
}: {
  job: Job | null;
  label: string;
  warnings?: string[];
  onRetry?: () => void;
  isRetrying?: boolean;
  retryError?: string;
  retryMessage?: string;
}) {
  const jobId = job ? getJobIdentifier(job) : undefined;
  if (!job || !jobId) {
    return <EmptyState title={`No ${label} job for this model`} message="Run this stage to create one." />;
  }

  const message = getJobMessage(job);
  const allWarnings = [...getJobWarnings(job), ...(warnings ?? [])];
  return (
    <div className="stage-job-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Latest {label} job</p>
          <h4>
            <Link to={`/jobs/${encodeURIComponent(jobId)}`}>{jobId}</Link>
          </h4>
        </div>
        <div className="pipeline-stage-actions">
          <StatusBadge status={getJobStatus(job)} />
          {onRetry && canRetryJob(job) ? (
            <button
              className="button secondary compact-button"
              type="button"
              disabled={Boolean(isRetrying)}
              onClick={onRetry}
            >
              {isRetrying ? "Retrying..." : "Retry stage"}
            </button>
          ) : null}
        </div>
      </div>
      {message ? <p className="muted">{message}</p> : null}
      {allWarnings.length > 0 ? (
        <div className="form-warning">
          <strong>Warnings</strong>
          <ul>
            {allWarnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <MessageBlock message={retryMessage} error={retryError} />
      <JobAssets jobId={jobId} isJobActive={isActiveJob(job)} />
    </div>
  );
}

function SettingsPanel({
  disabled,
  state,
  setActionState,
}: {
  disabled: boolean;
  state: StageActionState;
  setActionState: React.Dispatch<React.SetStateAction<StageActionState>>;
}) {
  const [settings, setSettings] = useState<ProductFactorySettings | null>(null);
  const [form, setForm] = useState<SettingsFormState>(makeSettingsForm(null));
  const [localError, setLocalError] = useState<string | null>(null);

  const loadSettings = useCallback(
    async (signal?: AbortSignal) => {
      setActionState((current) => ({
        ...current,
        busy: { ...current.busy, settings_load: true },
        errors: { ...current.errors, settings_load: undefined },
      }));
      try {
        const nextSettings = await apiClient.getSettings(signal);
        if (signal?.aborted) {
          return;
        }
        setSettings(nextSettings);
        setForm(makeSettingsForm(nextSettings));
        setActionState((current) => ({
          ...current,
          messages: { ...current.messages, settings_load: "Settings loaded." },
        }));
      } catch (error) {
        if (!signal?.aborted) {
          setActionState((current) => ({
            ...current,
            errors: { ...current.errors, settings_load: getErrorHint(error, "Could not load settings.") },
          }));
        }
      } finally {
        if (!signal?.aborted) {
          setActionState((current) => ({
            ...current,
            busy: { ...current.busy, settings_load: false },
          }));
        }
      }
    },
    [setActionState],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadSettings(controller.signal);
    return () => controller.abort();
  }, [loadSettings]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const { payload, error } = makeSettingsPayload(form);
    setLocalError(error);
    if (!payload) {
      return;
    }

    setActionState((current) => ({
      ...current,
      busy: { ...current.busy, settings_save: true },
      errors: { ...current.errors, settings_save: undefined },
      messages: { ...current.messages, settings_save: undefined },
    }));

    try {
      const nextSettings = await apiClient.patchSettings(payload);
      setSettings(nextSettings);
      setForm(makeSettingsForm(nextSettings));
      setActionState((current) => ({
        ...current,
        messages: { ...current.messages, settings_save: "Settings saved." },
      }));
    } catch (errorValue) {
      setActionState((current) => ({
        ...current,
        errors: { ...current.errors, settings_save: getErrorHint(errorValue, "Could not save settings.") },
      }));
    } finally {
      setActionState((current) => ({
        ...current,
        busy: { ...current.busy, settings_save: false },
      }));
    }
  }

  function updateField(key: keyof SettingsFormState, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Settings</p>
          <h3>Authoring defaults</h3>
          <p className="muted">Compact defaults only; category and source-specific settings stay hidden here.</p>
        </div>
        <button
          className="button secondary compact-button"
          type="button"
          disabled={disabled || state.busy.settings_load}
          onClick={() => void loadSettings()}
        >
          {state.busy.settings_load ? "Loading..." : "Load settings"}
        </button>
      </div>

      <form className="form settings-mini-form" onSubmit={handleSubmit}>
        {(localError ?? state.errors.settings_save ?? state.errors.settings_load) ? (
          <div className="form-error">{localError ?? state.errors.settings_save ?? state.errors.settings_load}</div>
        ) : null}
        {state.messages.settings_save ? <p className="state-block">{state.messages.settings_save}</p> : null}

        <div className="filter-grid">
          <label>
            <span>Intro min words</span>
            <input
              inputMode="numeric"
              type="number"
              min="1"
              value={form.introMinWords}
              onChange={(event) => updateField("introMinWords", event.target.value)}
            />
          </label>
          <label>
            <span>Intro max words</span>
            <input
              inputMode="numeric"
              type="number"
              min="1"
              max="500"
              value={form.introMaxWords}
              onChange={(event) => updateField("introMaxWords", event.target.value)}
            />
          </label>
          <label>
            <span>Intro max attempts</span>
            <input
              inputMode="numeric"
              type="number"
              min="1"
              max="10"
              value={form.introMaxAttempts}
              onChange={(event) => updateField("introMaxAttempts", event.target.value)}
            />
          </label>
          <label>
            <span>SEO meta max chars</span>
            <input
              inputMode="numeric"
              type="number"
              min="1"
              value={form.seoMetaDescriptionMaxChars}
              onChange={(event) => updateField("seoMetaDescriptionMaxChars", event.target.value)}
            />
          </label>
        </div>

        <button className="button primary inline-button" type="submit" disabled={disabled || state.busy.settings_save || !settings}>
          {state.busy.settings_save ? "Saving..." : "Save settings"}
        </button>
      </form>
    </section>
  );
}

export function ProductFactoryWorkflowPage() {
  const { model: routeModel } = useParams<{ model?: string }>();
  const { trackJob } = useGlobalJobs();
  const operatorStartedStagesRef = useRef<Set<WorkflowTab>>(new Set());
  const previousStageReadyRef = useRef<Partial<Record<WorkflowTab, boolean>>>({});
  const [form, setForm, resetForm] = usePersistentPageState<PrepareFormState>(
    WORKFLOW_STORAGE_KEY,
    initialPrepareFormState,
  );
  const [activeTab, setActiveTab] = useState<WorkflowTab>("prepare");
  const [autoAdvanceMessage, setAutoAdvanceMessage] = useState<string | null>(null);
  const [modelJobs, setModelJobs] = useState<Job[]>([]);
  const [isModelJobsLoading, setIsModelJobsLoading] = useState(false);
  const [modelJobsError, setModelJobsError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [isHealthLoading, setIsHealthLoading] = useState(true);
  const [authoringStatus, setAuthoringStatus] = useState<AuthoringStatus | null>(null);
  const [filterReview, setFilterReview] = useState<FilterReview | null>(null);
  const [renderOverride, setRenderOverride] = useState(false);
  const [resetSeq, setResetSeq] = useState(0);
  const [actionState, setActionState] = useState<StageActionState>({
    busy: {},
    messages: {},
    errors: {},
  });

  const model = form.model.trim();
  const isBackendAvailable = isApiHealthy(health, healthError);
  const latestPrepareJob = useMemo(() => getLatestJobForTab(modelJobs, "prepare", model), [modelJobs, model]);
  const latestAuthoringJob = useMemo(() => getLatestJobForTab(modelJobs, "authoring", model), [modelJobs, model]);
  const latestFilterReviewJob = useMemo(() => getLatestJobForTab(modelJobs, "filter_review", model), [modelJobs, model]);
  const latestRenderJob = useMemo(() => getLatestJobForTab(modelJobs, "render", model), [modelJobs, model]);
  const latestPublishJob = useMemo(() => getLatestJobForTab(modelJobs, "publish", model), [modelJobs, model]);

  const authoringBlockReasons = toStringList(authoringStatus?.render_block_reasons);
  const filterWarnings = getFilterReviewWarnings(filterReview);
  const visibleFilterReviewWarnings = toStringList(filterReview?.warnings).filter(
    (warning) => warning !== "category_filter_review_not_approved",
  );
  const renderWarnings = filterWarnings;
  const renderBlockReasons = authoringBlockReasons;
  const renderBlocked =
    authoringStatus?.ready_for_render === false ||
    renderBlockReasons.length > 0;

  const loadHealth = useCallback(async (signal?: AbortSignal) => {
    setIsHealthLoading(true);
    try {
      const nextHealth = await apiClient.getHealth(signal);
      if (signal?.aborted) {
        return;
      }
      setHealth(nextHealth);
      setHealthError(null);
    } catch (error) {
      if (!signal?.aborted) {
        setHealth(null);
        setHealthError(getApiErrorMessage(error));
      }
    } finally {
      if (!signal?.aborted) {
        setIsHealthLoading(false);
      }
    }
  }, []);

  const loadModelJobs = useCallback(
    async (signal?: AbortSignal, silent = false) => {
      if (!model) {
        setModelJobs([]);
        setModelJobsError(null);
        return;
      }

      if (!silent) {
        setIsModelJobsLoading(true);
      }
      setModelJobsError(null);

      try {
        const nextJobs = await apiClient.listJobsByModel(model, signal);
        if (signal?.aborted) {
          return;
        }
        setModelJobs(nextJobs.sort(compareJobsByUpdatedDesc));
      } catch (error) {
        if (!signal?.aborted) {
          setModelJobsError(getApiErrorMessage(error));
        }
      } finally {
        if (!signal?.aborted && !silent) {
          setIsModelJobsLoading(false);
        }
      }
    },
    [model],
  );

  useEffect(() => {
    const nextRouteModel = routeModel?.trim();
    if (!nextRouteModel) {
      return;
    }

    setForm((current) =>
      current.model.trim() === nextRouteModel ? current : { ...current, model: nextRouteModel },
    );
  }, [routeModel, setForm]);

  useEffect(() => {
    const controller = new AbortController();
    void loadHealth(controller.signal);
    return () => controller.abort();
  }, [loadHealth]);

  useEffect(() => {
    const controller = new AbortController();
    void loadModelJobs(controller.signal);
    return () => controller.abort();
  }, [loadModelJobs]);

  useEffect(() => {
    if (!modelJobs.some(isActiveJob)) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      void loadModelJobs(undefined, true);
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [loadModelJobs, modelJobs]);

  const runAction = useCallback(
    async (
      key: ActionKey,
      action: () => Promise<void>,
      successMessage: string,
      fallbackError: string,
    ) => {
      setActionState((current) => ({
        ...current,
        busy: { ...current.busy, [key]: true },
        errors: { ...current.errors, [key]: undefined },
        messages: { ...current.messages, [key]: undefined },
      }));

      try {
        await action();
        setActionState((current) => ({
          ...current,
          messages: { ...current.messages, [key]: successMessage },
        }));
      } catch (error) {
        setActionState((current) => ({
          ...current,
          errors: { ...current.errors, [key]: getErrorHint(error, fallbackError) },
        }));
      } finally {
        setActionState((current) => ({
          ...current,
          busy: { ...current.busy, [key]: false },
        }));
      }
    },
    [],
  );

  const markOperatorStageStarted = useCallback((stage: WorkflowTab) => {
    operatorStartedStagesRef.current.add(stage);
  }, []);

  const selectWorkflowTab = useCallback((tab: WorkflowTab) => {
    setAutoAdvanceMessage(null);
    setActiveTab(tab);
  }, []);

  function setActionBusy(key: ActionKey, busy: boolean) {
    setActionState((current) => ({
      ...current,
      busy: { ...current.busy, [key]: busy },
    }));
  }

  function setActionMessage(key: ActionKey, message: string | undefined) {
    setActionState((current) => ({
      ...current,
      messages: { ...current.messages, [key]: message },
    }));
  }

  function setActionError(key: ActionKey, error: string | undefined) {
    setActionState((current) => ({
      ...current,
      errors: { ...current.errors, [key]: error },
    }));
  }

  function recordJob(job: Job) {
    trackJob(job);
    setModelJobs((current) => upsertJobById(current, job));
  }

  async function waitForTerminalJob(initialJob: Job, tab: WorkflowTab, targetModel: string): Promise<Job> {
    let currentJob = initialJob;
    recordJob(currentJob);

    if (!isActiveJob(currentJob)) {
      return currentJob;
    }

    const jobId = getJobIdentifier(currentJob);
    const startedAt = Date.now();

    while (Date.now() - startedAt < JOB_COMPLETION_TIMEOUT_MS) {
      await delay(POLL_INTERVAL_MS);
      if (jobId) {
        currentJob = await apiClient.getJob(jobId);
        recordJob(currentJob);
      } else {
        const nextJobs = (await apiClient.listJobsByModel(targetModel)).sort(compareJobsByUpdatedDesc);
        setModelJobs(nextJobs);
        currentJob = getLatestJobForTab(nextJobs, tab, targetModel) ?? currentJob;
      }

      if (!isActiveJob(currentJob)) {
        return currentJob;
      }
    }

    throw new Error("Timed out waiting for the job to finish.");
  }

  async function runQueuedWorkflowJob(
    tab: WorkflowTab,
    actionKey: ActionKey,
    targetModel: string,
    createJob: () => Promise<Job>,
    successMessage: string,
  ): Promise<Job> {
    setActiveTab(tab);
    setActionBusy(actionKey, true);
    setActionError(actionKey, undefined);
    setActionMessage(actionKey, undefined);
    try {
      const queuedJob = await createJob();
      const completedJob = await waitForTerminalJob(queuedJob, tab, targetModel);
      if (!isSuccessfulJob(completedJob)) {
        throw new Error(getJobFailureMessage(completedJob, `${WORKFLOW_TABS.find((stage) => stage.key === tab)?.label ?? "Stage"} failed.`));
      }
      setActionMessage(actionKey, successMessage);
      return completedJob;
    } catch (error) {
      const message = getApiErrorMessage(error) || getErrorHint(error, "Workflow stage failed.");
      setActionError(actionKey, message);
      throw new WorkflowHalted(message);
    } finally {
      setActionBusy(actionKey, false);
    }
  }

  async function runAuthoringWorkflow(targetModel: string): Promise<AuthoringStatus> {
    setActiveTab("authoring");
    setAutoAdvanceMessage("Prepare succeeded. Running Authoring.");
    setActionBusy("authoring_load", true);
    setActionError("authoring_load", undefined);
    setActionError("intro_run", undefined);
    setActionError("seo_run", undefined);

    let status: AuthoringStatus;
    try {
      status = await apiClient.getAuthoringStatus(targetModel);
      setAuthoringStatus(status);
      setActionMessage("authoring_load", "Authoring status loaded.");
    } catch (error) {
      const message = getErrorHint(error, "Could not load authoring status.");
      setActionError("authoring_load", message);
      throw new WorkflowHalted(message);
    } finally {
      setActionBusy("authoring_load", false);
    }

    if (!isAuthoringTaskValid(status.intro_text)) {
      setActionBusy("intro_run", true);
      try {
        status = await apiClient.runIntroText(targetModel);
        setAuthoringStatus(status);
        setActionMessage("intro_run", "Intro text run completed.");
      } catch (error) {
        const message = getErrorHint(error, "Could not run intro text.");
        setActionError("intro_run", message);
        throw new WorkflowHalted(message);
      } finally {
        setActionBusy("intro_run", false);
      }
    }

    if (!isAuthoringTaskValid(status.seo_meta)) {
      setActionBusy("seo_run", true);
      try {
        status = await apiClient.runSeoMeta(targetModel);
        setAuthoringStatus(status);
        setActionMessage("seo_run", "SEO meta run completed.");
      } catch (error) {
        const message = getErrorHint(error, "Could not run SEO meta.");
        setActionError("seo_run", message);
        throw new WorkflowHalted(message);
      } finally {
        setActionBusy("seo_run", false);
      }
    }

    if (!isAuthoringReadyForRender(status)) {
      const reasons = toStringList(status.render_block_reasons);
      const message = reasons.length > 0
        ? `Authoring blocked: ${reasons.join("; ")}`
        : "Authoring blocked: intro text and SEO metadata must be valid.";
      setActionError("authoring_load", message);
      throw new WorkflowHalted(message);
    }

    setActionMessage("authoring_load", "Authoring completed.");
    return status;
  }

  async function runFilterReviewWorkflow(targetModel: string): Promise<FilterReview> {
    setActiveTab("filter_review");
    setAutoAdvanceMessage("Authoring succeeded. Running Filter Review.");
    setActionBusy("filter_load", true);
    setActionError("filter_load", undefined);

    try {
      const review = await apiClient.getFilterReview(targetModel);
      setFilterReview(review);
      if (hasBlockingFilterReviewWork(review)) {
        const missing = toStringList(review.missing_required_groups);
        const message = missing.length > 0
          ? `Filter Review requires manual review: missing required filters: ${missing.join(", ")}.`
          : "Filter Review requires manual review before render.";
        setActionError("filter_load", message);
        throw new WorkflowHalted(message);
      }

      setActionMessage("filter_load", "Filter review loaded with no render blockers.");
      return review;
    } catch (error) {
      if (error instanceof WorkflowHalted) {
        throw error;
      }
      const message = getErrorHint(error, "Could not load filter review.");
      setActionError("filter_load", message);
      throw new WorkflowHalted(message);
    } finally {
      setActionBusy("filter_load", false);
    }
  }

  async function runEndToEndWorkflow(request: PrepareJobRequest) {
    const targetModel = request.model;
    setAutoAdvanceMessage("Prepare queued. Waiting for completion.");
    const prepareJob = await apiClient.createPrepareJob(request);
    const completedPrepare = await waitForTerminalJob(prepareJob, "prepare", targetModel);
    if (!isSuccessfulJob(completedPrepare)) {
      throw new Error(getJobFailureMessage(completedPrepare, "Prepare failed."));
    }
    setActionMessage("prepare", "Prepare completed.");

    await runAuthoringWorkflow(targetModel);
    await runFilterReviewWorkflow(targetModel);
    setAutoAdvanceMessage("Filter Review has no blockers. Running Render.");
    await runQueuedWorkflowJob("render", "render", targetModel, () => apiClient.createRenderJob({ model: targetModel }), "Render completed.");
    setAutoAdvanceMessage("Render succeeded. Running Publish.");
    await runQueuedWorkflowJob("publish", "publish", targetModel, () => apiClient.createPublishJob({ model: targetModel }), "Publish completed.");
    setAutoAdvanceMessage("Workflow completed end to end.");
  }

  const loadAuthoring = useCallback(
    async (actionKey: ActionKey = "authoring_load") => {
      markOperatorStageStarted("authoring");
      if (!model) {
        setActionState((current) => ({
          ...current,
          errors: { ...current.errors, [actionKey]: "Model is required." },
        }));
        return;
      }

      await runAction(
        actionKey,
        async () => {
          setAuthoringStatus(await apiClient.getAuthoringStatus(model));
        },
        "Authoring status loaded.",
        "Could not load authoring status.",
      );
    },
    [markOperatorStageStarted, model, runAction],
  );

  const loadFilterReview = useCallback(
    async (actionKey: ActionKey = "filter_load") => {
      markOperatorStageStarted("filter_review");
      if (!model) {
        setActionState((current) => ({
          ...current,
          errors: { ...current.errors, [actionKey]: "Model is required." },
        }));
        return;
      }

      await runAction(
        actionKey,
        async () => {
          setFilterReview(await apiClient.getFilterReview(model));
        },
        "Filter review loaded.",
        "Could not load filter review.",
      );
    },
    [markOperatorStageStarted, model, runAction],
  );

  async function handlePrepareSubmit(request: PrepareJobRequest) {
    markOperatorStageStarted("prepare");
    setForm((current) => ({ ...current, model: request.model }));
    setActiveTab("prepare");
    setActionState((current) => ({
      ...current,
      busy: { ...current.busy, prepare: true },
      errors: {},
      messages: {},
    }));

    try {
      await runEndToEndWorkflow(request);
    } catch (error) {
      if (!(error instanceof WorkflowHalted)) {
        setActionError("prepare", getErrorHint(error, "Could not run Product Factory workflow."));
      }
    } finally {
      setActionBusy("prepare", false);
    }
  }

  async function handleRender() {
    markOperatorStageStarted("render");
    if (!model) {
      setActionState((current) => ({
        ...current,
        errors: { ...current.errors, render: "Model is required." },
      }));
      return;
    }

    await runAction(
      "render",
      async () => {
        const job = await apiClient.createRenderJob({ model });
        trackJob(job);
        await loadModelJobs();
      },
      "Render job started.",
      "Could not start render job.",
    );
  }

  async function handlePublish() {
    if (!model) {
      setActionState((current) => ({
        ...current,
        errors: { ...current.errors, publish: "Model is required." },
      }));
      return;
    }

    await runAction(
      "publish",
      async () => {
        const job = await apiClient.createPublishJob({ model });
        trackJob(job);
        await loadModelJobs();
      },
      "Publish job started.",
      "Could not start publish job.",
    );
  }

  async function handleSaveFilterReview() {
    markOperatorStageStarted("filter_review");
    if (!model || !filterReview) {
      setActionState((current) => ({
        ...current,
        errors: { ...current.errors, filter_save: "Load filter review before saving." },
      }));
      return;
    }

    await runAction(
      "filter_save",
      async () => {
        await apiClient.saveFilterReview(model, makeFilterReviewSavePayload(filterReview));
        setFilterReview(await apiClient.getFilterReview(model));
      },
      "Filter review saved.",
      "Could not save filter review.",
    );
  }

  async function handleApproveFilterReview() {
    markOperatorStageStarted("filter_review");
    if (!model) {
      setActionState((current) => ({
        ...current,
        errors: { ...current.errors, filter_approve: "Model is required." },
      }));
      return;
    }

    await runAction(
      "filter_approve",
      async () => {
        await apiClient.approveFilterReview(model);
        setFilterReview(await apiClient.getFilterReview(model));
      },
      "Filter review approval requested.",
      "Could not approve filter review.",
    );
  }

  async function handleRetryStage(tab: WorkflowTab, job: Job | null) {
    markOperatorStageStarted(tab);
    const jobId = job ? getJobIdentifier(job) : undefined;
    const actionKey = getRetryActionKey(tab);
    if (!jobId || !canRetryJob(job ?? undefined)) {
      setActionState((current) => ({
        ...current,
        errors: { ...current.errors, [actionKey]: "Only terminal failed, cancelled, or killed jobs can be retried." },
      }));
      return;
    }

    await runAction(
      actionKey,
      async () => {
        const retryJob = await apiClient.retryJob(jobId);
        trackJob(retryJob);
        await loadModelJobs();
      },
      "Stage retry started.",
      "Could not retry stage.",
    );
  }

  function updateReviewedValue(index: number, value: string) {
    setFilterReview((current) => {
      if (!current) {
        return current;
      }

      const groups = [...(current.groups ?? [])];
      groups[index] = { ...groups[index], reviewed_value: value };
      return { ...current, groups };
    });
  }

  function updateGroupRequired(index: number, required: boolean) {
    setFilterReview((current) => {
      if (!current) {
        return current;
      }

      const groups = [...(current.groups ?? [])];
      groups[index] = { ...groups[index], required };
      return { ...current, groups };
    });
  }

  function updateGroupStatus(index: number, status: string) {
    setFilterReview((current) => {
      if (!current) {
        return current;
      }

      const groups = [...(current.groups ?? [])];
      groups[index] = { ...groups[index], status };
      return { ...current, groups };
    });
  }

  function handleResetForm() {
    resetForm();
    setAuthoringStatus(null);
    setFilterReview(null);
    setRenderOverride(false);
    setAutoAdvanceMessage(null);
    operatorStartedStagesRef.current.clear();
    previousStageReadyRef.current = {};
    setResetSeq((current) => current + 1);
    setActionState({ busy: {}, messages: {}, errors: {} });
  }

  const writeDisabled = !isBackendAvailable || isHealthLoading;
  const modelRequiredDisabled = writeDisabled || model.length === 0;
  const renderDisabled = modelRequiredDisabled || (renderBlocked && !renderOverride);
  const activeJobsByTab: Record<WorkflowTab, Job | null> = {
    prepare: latestPrepareJob,
    authoring: latestAuthoringJob,
    filter_review: latestFilterReviewJob,
    render: latestRenderJob,
    publish: latestPublishJob,
  };
  const workflowStageReady = useMemo(
    () => ({
      prepare: isSuccessfulJob(latestPrepareJob ?? undefined),
      authoring: isAuthoringReadyForRender(authoringStatus),
      filter_review: isFilterReviewReadyForRender(filterReview),
      render: isSuccessfulJob(latestRenderJob ?? undefined),
      publish: isSuccessfulJob(latestPublishJob ?? undefined),
    }),
    [authoringStatus, filterReview, latestPrepareJob, latestPublishJob, latestRenderJob],
  );
  const authoringHasError = Boolean(
    actionState.errors.authoring_load ?? actionState.errors.intro_run ?? actionState.errors.seo_run,
  );
  const filterReviewHasError = Boolean(
    actionState.errors.filter_load ?? actionState.errors.filter_save ?? actionState.errors.filter_approve,
  );
  const filterReviewHasUnapprovedWarnings = Boolean(
    filterReview && getFilterReviewWarnings(filterReview).length > 0 && filterReview.approved !== true,
  );
  const derivedTabStatuses: Record<WorkflowTab, string> = {
    prepare: latestPrepareJob ? getJobStatus(latestPrepareJob) : "pending",
    authoring: latestAuthoringJob
      ? getJobStatus(latestAuthoringJob)
      : authoringHasError
        ? "failed"
        : isAuthoringReadyForRender(authoringStatus)
          ? "succeeded"
          : authoringStatus
            ? "blocked"
            : "pending",
    filter_review: latestFilterReviewJob
      ? getJobStatus(latestFilterReviewJob)
      : filterReviewHasError
        ? "warning"
        : filterReview
          ? filterReviewHasUnapprovedWarnings
            ? "warning"
            : "succeeded"
          : "pending",
    render: latestRenderJob ? getJobStatus(latestRenderJob) : "pending",
    publish: latestPublishJob ? getJobStatus(latestPublishJob) : "pending",
  };

  useEffect(() => {
    const transitions: Array<{ from: WorkflowTab; to: WorkflowTab; message: string }> = [
      { from: "prepare", to: "authoring", message: "Prepare succeeded. Advanced to Authoring." },
      { from: "authoring", to: "filter_review", message: "Authoring is ready. Advanced to Filter Review." },
      { from: "filter_review", to: "render", message: "Filter Review is ready. Advanced to Render." },
      { from: "render", to: "publish", message: "Render succeeded. Advanced to Publish." },
    ];

    const previous = previousStageReadyRef.current;
    for (const transition of transitions) {
      const isReady = workflowStageReady[transition.from];
      const justBecameReady = isReady && previous[transition.from] !== true;
      previous[transition.from] = isReady;

      if (
        justBecameReady &&
        operatorStartedStagesRef.current.has(transition.from) &&
        activeTab === transition.from &&
        WORKFLOW_TAB_INDEX[transition.to] > WORKFLOW_TAB_INDEX[transition.from]
      ) {
        operatorStartedStagesRef.current.delete(transition.from);
        setActiveTab(transition.to);
        setAutoAdvanceMessage(transition.message);
        break;
      }
    }
  }, [activeTab, workflowStageReady]);

  return (
    <div className="page-stack">
      <section className="page-header">
        <p className="eyebrow">Product Factory</p>
        <h2>Pipeline</h2>
        <p>{"Prepare -> Authoring -> Filter Review -> Render -> Publish"}</p>
        <button className="text-button" type="button" onClick={handleResetForm}>
          Reset saved Workflow state
        </button>
      </section>

      <section className={`db-status-banner ${isBackendAvailable ? "ok" : "danger"}`}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">API health</p>
            <h3>{isHealthLoading ? "Checking Product Factory API" : isBackendAvailable ? "Product Factory API available" : "Product Factory API unavailable"}</h3>
          </div>
          <button className="button secondary compact-button" type="button" onClick={() => void loadHealth()}>
            Retry health
          </button>
        </div>
        {healthError ? <p className="form-error">{healthError}</p> : null}
        {!isBackendAvailable ? <p className="muted">Write actions are disabled until the backend health check succeeds.</p> : null}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Workflow</p>
            <h3>Model history</h3>
            <p className="muted">Loads newest jobs from /api/jobs/by-model/{model || "model"}.</p>
          </div>
          <button
            className="button secondary compact-button"
            type="button"
            disabled={modelRequiredDisabled || isModelJobsLoading}
            onClick={() => void loadModelJobs()}
          >
            {isModelJobsLoading ? "Loading..." : "Refresh history"}
          </button>
        </div>
        <label className="inline-field wide">
          <span>Model</span>
          <input
            value={form.model}
            onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))}
            placeholder="product-model"
          />
        </label>
        {modelJobsError ? <ErrorState message={modelJobsError} onRetry={() => void loadModelJobs()} /> : null}
        <div className="workflow-tabs" role="tablist" aria-label="Workflow stages">
          {WORKFLOW_TABS.map((tab) => {
            return (
              <button
                key={tab.key}
                className={activeTab === tab.key ? "workflow-tab active" : "workflow-tab"}
                type="button"
                role="tab"
                aria-selected={activeTab === tab.key}
                onClick={() => selectWorkflowTab(tab.key)}
              >
                <span>{tab.label}</span>
                <StatusBadge status={derivedTabStatuses[tab.key]} />
              </button>
            );
          })}
        </div>
        {autoAdvanceMessage ? <p className="state-block">{autoAdvanceMessage}</p> : null}
      </section>

      {activeTab === "prepare" ? (
      <WorkflowStage
        title="Prepare"
        status={latestPrepareJob ? getJobStatus(latestPrepareJob) : "pending"}
        description="Collect source input and queue the existing prepare job endpoint."
      >
        <PrepareJobForm
          key={resetSeq}
          actionLabel="Run Prepare"
          busyLabel={writeDisabled ? "Backend unavailable" : "Running workflow..."}
          error={actionState.errors.prepare ?? null}
          isSubmitting={Boolean(actionState.busy.prepare) || writeDisabled}
          initialForm={form}
          onFormChange={setForm}
          onSubmit={(request) => void handlePrepareSubmit(request)}
        />
        <MessageBlock message={actionState.messages.prepare} error={actionState.errors.prepare} />
        <StageJobPanel
          job={latestPrepareJob}
          label="prepare"
          onRetry={() => void handleRetryStage("prepare", latestPrepareJob)}
          isRetrying={Boolean(actionState.busy.retry_prepare)}
          retryMessage={actionState.messages.retry_prepare}
          retryError={actionState.errors.retry_prepare}
        />
      </WorkflowStage>
      ) : null}

      {activeTab === "authoring" ? (
      <WorkflowStage
        title="Authoring"
        status={derivedTabStatuses.authoring}
        description="Load authoring state, run intro text, and run SEO metadata separately."
      >
        <div className="button-row">
          <button className="button secondary" type="button" disabled={modelRequiredDisabled || actionState.busy.authoring_load} onClick={() => void loadAuthoring()}>
            {actionState.busy.authoring_load ? "Loading..." : "Refresh Authoring"}
          </button>
        </div>
        <MessageBlock message={actionState.messages.authoring_load} error={actionState.errors.authoring_load} />
        {model.length === 0 ? <p className="form-warning">Enter a model before loading authoring status.</p> : null}

        <div className="split-grid">
          <AuthoringTaskCard
            title="Intro Text"
            task={authoringStatus?.intro_text}
            onRun={() =>
              void runAction(
                "intro_run",
                async () => {
                  await apiClient.runIntroText(model);
                  await loadAuthoring("intro_run");
                },
                "Intro text run completed.",
                "Could not run intro text.",
              )
            }
            onRetry={() =>
              void runAction(
                "intro_retry",
                async () => {
                  await apiClient.retryIntroText(model);
                  await loadAuthoring("intro_retry");
                },
                "Intro text retry completed.",
                "Could not retry intro text.",
              )
            }
            isRunBusy={Boolean(actionState.busy.intro_run)}
            isRetryBusy={Boolean(actionState.busy.intro_retry)}
            runLabel="Run Intro Text"
            retryLabel="Retry Intro Text"
            disabled={modelRequiredDisabled}
            showIntroEmphasisDiagnostics
          />
          <AuthoringTaskCard
            title="SEO Meta"
            task={authoringStatus?.seo_meta}
            onRun={() =>
              void runAction(
                "seo_run",
                async () => {
                  await apiClient.runSeoMeta(model);
                  await loadAuthoring("seo_run");
                },
                "SEO meta run completed.",
                "Could not run SEO meta.",
              )
            }
            onRetry={() =>
              void runAction(
                "seo_retry",
                async () => {
                  await apiClient.retrySeoMeta(model);
                  await loadAuthoring("seo_retry");
                },
                "SEO meta retry completed.",
                "Could not retry SEO meta.",
              )
            }
            isRunBusy={Boolean(actionState.busy.seo_run)}
            isRetryBusy={Boolean(actionState.busy.seo_retry)}
            runLabel="Run SEO Meta"
            retryLabel="Retry SEO Meta"
            disabled={modelRequiredDisabled}
          />
        </div>
        <MessageBlock error={actionState.errors.intro_run ?? actionState.errors.intro_retry ?? actionState.errors.seo_run ?? actionState.errors.seo_retry} />
        {authoringStatus ? (
          <>
            <dl className="summary-grid workflow-summary-grid">
              <PathValue label="Ready for render" value={authoringStatus.ready_for_render} />
              <PathValue label="Model" value={authoringStatus.model} />
            </dl>
            <BlockingReasons reasons={authoringBlockReasons} />
            {toStringList(authoringStatus.warnings).length > 0 ? (
              <p className="form-warning">{toStringList(authoringStatus.warnings).join("; ")}</p>
            ) : null}
          </>
        ) : null}
        <StageJobPanel
          job={latestAuthoringJob}
          label="authoring"
          onRetry={() => void handleRetryStage("authoring", latestAuthoringJob)}
          isRetrying={Boolean(actionState.busy.retry_authoring)}
          retryMessage={actionState.messages.retry_authoring}
          retryError={actionState.errors.retry_authoring}
        />
      </WorkflowStage>
      ) : null}

      {activeTab === "filter_review" ? (
      <WorkflowStage
        title="Filter Review"
        status={derivedTabStatuses.filter_review}
        description="Review product-specific filter values before render."
      >
        <div className="button-row">
          <button className="button secondary" type="button" disabled={modelRequiredDisabled || actionState.busy.filter_load} onClick={() => void loadFilterReview()}>
            {actionState.busy.filter_load ? "Loading..." : "Load Filter Review"}
          </button>
          <button className="button primary" type="button" disabled={modelRequiredDisabled || !filterReview || actionState.busy.filter_save} onClick={() => void handleSaveFilterReview()}>
            {actionState.busy.filter_save ? "Saving..." : "Save Filter Review"}
          </button>
          <button className="button secondary" type="button" disabled={modelRequiredDisabled || !filterReview || actionState.busy.filter_approve} onClick={() => void handleApproveFilterReview()}>
            {actionState.busy.filter_approve ? "Approving..." : "Approve Filter Review"}
          </button>
        </div>
        <MessageBlock
          message={actionState.messages.filter_load ?? actionState.messages.filter_save ?? actionState.messages.filter_approve}
          error={actionState.errors.filter_load ?? actionState.errors.filter_save ?? actionState.errors.filter_approve}
        />

        {filterReview ? (
          <>
            <dl className="summary-grid workflow-summary-grid">
              <PathValue label="Category path" value={filterReview.taxonomy_path} />
              <PathValue label="Category ID" value={filterReview.category_id} />
              <PathValue label="Filter category found" value={filterReview.filter_category_found} />
              <PathValue label="Approved" value={filterReview.approved} />
              <PathValue label="Approved at" value={filterReview.approved_at} />
              <PathValue label="Render blocked" value={filterReview.render_blocked} />
              <PathValue label="Review artifact" value={filterReview.review_artifact_path} />
            </dl>
            {filterWarnings.length > 0 ? (
              <div className="form-warning">
                <strong>Filter warnings</strong>
                <ul>
                  {filterWarnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {toStringList(filterReview.missing_required_groups).length > 0 ? (
              <div className="form-warning">
                <strong>Missing required groups</strong>
                <ul>
                  {toStringList(filterReview.missing_required_groups).map((group) => (
                    <li key={group}>{group}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {visibleFilterReviewWarnings.length > 0 ? <p className="form-warning">{visibleFilterReviewWarnings.join("; ")}</p> : null}
            <div className="table-wrap filter-review-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Required</th>
                    <th>Group</th>
                    <th>Status</th>
                    <th>Resolved value</th>
                    <th>Reviewed value input</th>
                    <th>Effective value</th>
                    <th>Source</th>
                    <th>Warnings</th>
                  </tr>
                </thead>
                <tbody>
                  {(filterReview.groups ?? []).map((group, index) => {
                    const warnings = getGroupWarnings(group);
                    const inputClass = group.missing_required ? "table-input missing-required-input" : "table-input";
                    return (
                      <tr key={`${formatOptional(group.group_id)}-${index}`}>
                        <td>
                          <label className="table-toggle">
                            <input
                              type="checkbox"
                              checked={group.required === true}
                              onChange={(event) => updateGroupRequired(index, event.target.checked)}
                            />
                            <span>{group.required ? "Required" : "Optional"}</span>
                          </label>
                        </td>
                        <td>
                          <strong>{formatOptional(group.group_name)}</strong>
                          <span className="artifact-path">{formatOptional(group.group_id)}</span>
                        </td>
                        <td>
                          <select
                            className="table-input"
                            value={group.status ?? "active"}
                            onChange={(event) => updateGroupStatus(index, event.target.value)}
                          >
                            <option value="active">active</option>
                            <option value="inactive">inactive</option>
                            <option value="deprecated">deprecated</option>
                          </select>
                        </td>
                        <td>{formatOptional(group.resolved_value)}</td>
                        <td>
                          <input
                            className={inputClass}
                            list={`filter-review-values-${index}`}
                            value={group.reviewed_value ?? ""}
                            onChange={(event) => updateReviewedValue(index, event.target.value)}
                            placeholder={group.missing_required ? "Required value" : "Reviewed value"}
                          />
                          {Array.isArray(group.allowed_values) ? (
                            <datalist id={`filter-review-values-${index}`}>
                              {group.allowed_values
                                .map(allowedValueLabel)
                                .filter(Boolean)
                                .map((value) => (
                                  <option key={value} value={value} />
                                ))}
                            </datalist>
                          ) : null}
                        </td>
                        <td>
                          {formatOptional(group.effective_value)}
                          <span className="artifact-path">{formatOptional(group.effective_value_id)}</span>
                          <span className="artifact-path">{formatOptional(group.value_status)}</span>
                        </td>
                        <td>{formatOptional(group.source)}</td>
                        <td>{warnings.length > 0 ? warnings.join("; ") : "-"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <EmptyState title="No filter review loaded" message="Load filter review after prepare has produced product artifacts." />
        )}
        <StageJobPanel
          job={latestFilterReviewJob}
          label="filter review"
          warnings={filterWarnings}
          onRetry={() => void handleRetryStage("filter_review", latestFilterReviewJob)}
          isRetrying={Boolean(actionState.busy.retry_filter_review)}
          retryMessage={actionState.messages.retry_filter_review}
          retryError={actionState.errors.retry_filter_review}
        />
      </WorkflowStage>
      ) : null}

      {activeTab === "render" ? (
      <WorkflowStage
        title="Render"
        status={latestRenderJob ? derivedTabStatuses.render : renderBlocked ? "blocked" : derivedTabStatuses.render}
        description="Queue render after authoring is ready; filter review issues are warnings unless the render job fails."
      >
        <BlockingReasons reasons={renderBlockReasons} />
        {renderWarnings.length > 0 ? (
          <div className="form-warning">
            <strong>Filter warnings</strong>
            <ul>
              {renderWarnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {renderBlocked ? (
          <label className="checkbox-row workflow-checkbox-row">
            <input type="checkbox" checked={renderOverride} onChange={(event) => setRenderOverride(event.target.checked)} />
            <span>Allow render despite known blockers</span>
          </label>
        ) : null}
        <div className="button-row">
          <button className="button primary" type="button" disabled={renderDisabled || actionState.busy.render} onClick={() => void handleRender()}>
            {actionState.busy.render ? "Starting render..." : "Render"}
          </button>
          {filterReview && filterReview.approved !== true ? (
            <button className="button secondary" type="button" disabled={modelRequiredDisabled || actionState.busy.filter_approve} onClick={() => void handleApproveFilterReview()}>
              {actionState.busy.filter_approve ? "Approving..." : "Approve Filter Review"}
            </button>
          ) : null}
          {renderDisabled ? <span className="muted">Render requires model, backend health, and authoring readiness unless override is checked.</span> : null}
        </div>
        <MessageBlock
          message={actionState.messages.render ?? actionState.messages.filter_approve}
          error={actionState.errors.render ?? actionState.errors.filter_approve}
        />
        <StageJobPanel
          job={latestRenderJob}
          label="render"
          warnings={renderWarnings}
          onRetry={() => void handleRetryStage("render", latestRenderJob)}
          isRetrying={Boolean(actionState.busy.retry_render)}
          retryMessage={actionState.messages.retry_render}
          retryError={actionState.errors.retry_render}
        />
      </WorkflowStage>
      ) : null}

      {activeTab === "publish" ? (
      <WorkflowStage
        title="Publish"
        status={derivedTabStatuses.publish}
        description="Queue publish as a separate operator action after render."
      >
        <div className="button-row">
          <button className="button primary" type="button" disabled={modelRequiredDisabled || actionState.busy.publish} onClick={() => void handlePublish()}>
            {actionState.busy.publish ? "Starting publish..." : "Publish"}
          </button>
          {modelRequiredDisabled ? <span className="muted">Publish requires model and backend health.</span> : null}
        </div>
        <MessageBlock message={actionState.messages.publish} error={actionState.errors.publish} />
        <StageJobPanel
          job={latestPublishJob}
          label="publish"
          onRetry={() => void handleRetryStage("publish", latestPublishJob)}
          isRetrying={Boolean(actionState.busy.retry_publish)}
          retryMessage={actionState.messages.retry_publish}
          retryError={actionState.errors.retry_publish}
        />
      </WorkflowStage>
      ) : null}

      <SettingsPanel disabled={writeDisabled} state={actionState} setActionState={setActionState} />

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Execution history</p>
            <h3>Latest jobs for {model || "selected model"}</h3>
          </div>
          <Link className="button secondary compact-button" to="/jobs">
            Open Jobs
          </Link>
        </div>
        <div className="pipeline-stage-list">
          {WORKFLOW_TABS.map((stage) => {
            const job = activeJobsByTab[stage.key];
            const jobId = job ? getJobIdentifier(job) : undefined;
            return (
              <div className="pipeline-stage-item" key={stage.key}>
                <div className="pipeline-stage-main">
                  <strong>{stage.label}</strong>
                  {jobId ? <Link to={`/jobs/${encodeURIComponent(jobId)}`}>{jobId}</Link> : <span className="muted">No job found</span>}
                </div>
                <StatusBadge status={derivedTabStatuses[stage.key]} />
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
