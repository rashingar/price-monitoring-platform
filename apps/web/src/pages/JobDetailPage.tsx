import { type MouseEvent, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getJobProgress } from "../api/jobProgress";
import {
  canStopJob,
  getJobIdentifier,
  getJobStageLabel,
  getJobStatus,
  getJobWorkflow,
  getRequestPayload,
  isActiveJob,
  isFailedJob,
} from "../api/jobUtils";
import type { Job, LogEntry } from "../api/types";
import { ArtifactList } from "../components/jobs/ArtifactList";
import { JobProgressPanel } from "../components/jobs/JobProgressPanel";
import { JobSummary } from "../components/jobs/JobSummary";
import { JsonBlock } from "../components/jobs/JsonBlock";
import { formatLogsForCopy, LogsPanel } from "../components/jobs/LogsPanel";
import { StatusBadge } from "../components/jobs/StatusBadge";
import { ErrorState, LoadingState } from "../components/layout/StateBlocks";
import { useJobDetail } from "../hooks/useJobDetail";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatJson(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }

  try {
    return JSON.stringify(value, null, 2) ?? String(value);
  } catch {
    return String(value);
  }
}

function hasPayload(value: unknown): boolean {
  if (value === null || value === undefined) {
    return false;
  }

  if (typeof value === "string") {
    return value.trim().length > 0;
  }

  if (Array.isArray(value)) {
    return value.length > 0;
  }

  if (isRecord(value)) {
    return Object.keys(value).length > 0;
  }

  return true;
}

function shortenIdentifier(value: string): string {
  if (value.length <= 22) {
    return value;
  }

  return `${value.slice(0, 6)}...${value.slice(-7)}`;
}

function titleFromJob(job: Job | null, fallbackId: string | undefined): string {
  if (!job) {
    return fallbackId ? "Job" : "Unknown job";
  }

  const rawType = getJobWorkflow(job);
  const words = rawType
    .replace(/[-_]+/g, " ")
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
  if (!words || words === "job") {
    return `${getJobStageLabel(job)} job`;
  }

  return `${words.charAt(0).toUpperCase()}${words.slice(1)} job`;
}

function parseTimestamp(value: unknown): number | null {
  if (typeof value !== "string" || value.trim().length === 0) {
    return null;
  }

  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? null : parsed;
}

function formatDurationMs(value: number): string {
  const totalSeconds = Math.max(0, Math.round(value / 1000));
  const seconds = totalSeconds % 60;
  const totalMinutes = Math.floor(totalSeconds / 60);
  const minutes = totalMinutes % 60;
  const hours = Math.floor(totalMinutes / 60);

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }

  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }

  return `${seconds}s`;
}

function getDurationLabel(job: Job | null): string {
  if (!job?.started_at) {
    return "-";
  }

  const started = parseTimestamp(job.started_at);
  if (started === null) {
    return "-";
  }

  const finished = parseTimestamp(job.finished_at);
  if (finished !== null) {
    return formatDurationMs(finished - started);
  }

  if (isActiveJob(job)) {
    return formatDurationMs(Date.now() - started);
  }

  return "-";
}

function getMessage(value: unknown): string | null {
  if (typeof value === "string" && value.trim().length > 0) {
    return value;
  }

  if (!isRecord(value)) {
    return null;
  }

  for (const key of ["message", "detail", "error", "latest_message"]) {
    const message = getMessage(value[key]);
    if (message) {
      return message;
    }
  }

  return null;
}

function getCurrentActivity(job: Job | null): string | null {
  if (!job) {
    return null;
  }

  const progress = getJobProgress(job);
  const progressMessage =
    typeof progress?.details?.message === "string"
      ? progress.details.message
      : typeof progress?.details?.latest_message === "string"
        ? progress.details.latest_message
        : null;

  return getMessage(job.message) ?? progressMessage ?? progress?.current_step_label ?? progress?.current_step ?? null;
}

function getErrorSummary(job: Job): string {
  return (
    getMessage(job.error) ??
    getMessage(job.message) ??
    "This job failed, but the backend did not return a concise error message."
  );
}

function getErrorDetails(job: Job): unknown | null {
  const details: Record<string, unknown> = {};
  if (job.error_code) {
    details.error_code = job.error_code;
  }
  if (job.error) {
    details.error = job.error;
  }
  for (const key of ["error_type", "exception_type", "traceback", "details", "stage"]) {
    if (job[key] !== undefined && job[key] !== null) {
      details[key] = job[key];
    }
  }

  return Object.keys(details).length > 0 ? details : null;
}

function CopyButton({
  label,
  text,
}: {
  label: string;
  text: string;
}) {
  const [copied, setCopied] = useState(false);

  async function handleCopy(event: MouseEvent<HTMLButtonElement>) {
    event.preventDefault();
    event.stopPropagation();
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    }
  }

  return (
    <button className="button secondary compact-button" type="button" onClick={(event) => void handleCopy(event)}>
      {copied ? "Copied" : label}
    </button>
  );
}

function PayloadSection({ payload }: { payload: unknown }) {
  const payloadText = useMemo(() => formatJson(payload), [payload]);
  const isEmpty = !hasPayload(payload);
  const isLarge = payloadText.length > 700 || payloadText.split("\n").length > 18;

  return (
    <details className="panel collapsible-panel" open={!isLarge}>
      <summary>
        <span>
          <span className="eyebrow">Request payload</span>
          <strong>Submitted input</strong>
        </span>
        {!isEmpty ? <CopyButton label="Copy payload" text={payloadText} /> : null}
      </summary>
      {isEmpty ? (
        <p className="compact-empty-state">No request payload was stored for this job.</p>
      ) : (
        <JsonBlock value={payload} className="json-block-wrap" />
      )}
    </details>
  );
}

function LogsSection({ logs }: { logs: LogEntry[] }) {
  const logsText = useMemo(() => formatLogsForCopy(logs), [logs]);

  return (
    <section className="panel job-logs-section" aria-labelledby="job-logs-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Logs</p>
          <h3 id="job-logs-heading">{logs.length} entries</h3>
        </div>
        {logs.length > 0 ? <CopyButton label="Copy logs" text={logsText} /> : null}
      </div>
      <LogsPanel logs={logs} />
    </section>
  );
}

function ErrorPanel({ job }: { job: Job }) {
  const details = getErrorDetails(job);

  return (
    <section className="panel job-error-panel" aria-labelledby="job-error-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Error</p>
          <h3 id="job-error-heading">Job failed</h3>
        </div>
        <StatusBadge status={getJobStatus(job)} />
      </div>
      <p className="job-error-message">{getErrorSummary(job)}</p>
      <dl className="summary-grid compact-detail-grid">
        <div>
          <dt>Failing stage</dt>
          <dd>{getJobStageLabel(job)}</dd>
        </div>
        <div>
          <dt>Error code</dt>
          <dd>{job.error_code ? String(job.error_code) : "-"}</dd>
        </div>
      </dl>
      {details ? (
        <details className="technical-details">
          <summary>Technical details</summary>
          <JsonBlock value={details} className="json-block-wrap" />
        </details>
      ) : null}
    </section>
  );
}

export function JobDetailPage() {
  const { jobId } = useParams();
  const {
    artifacts,
    error,
    isLoading,
    isPolling,
    isRefreshing,
    isStopping,
    job,
    lastLoadedAt,
    logs,
    reload,
    stopError,
    stopJob,
  } = useJobDetail(jobId);
  const fullJobId = job ? getJobIdentifier(job) : jobId;
  const progress = getJobProgress(job);
  const requestPayload = job ? getRequestPayload(job) : null;
  const pageTitle = titleFromJob(job, jobId);
  const currentActivity = getCurrentActivity(job);
  const durationLabel = getDurationLabel(job);

  const handleStopJob = async () => {
    if (!job) {
      return;
    }

    const id = getJobIdentifier(job);
    if (!id) {
      return;
    }

    const confirmed = window.confirm(
      `Stop job ${id}? This marks the job as cancelled. Active in-process work may need the backend service to finish before resources are fully released.`,
    );
    if (!confirmed) {
      return;
    }

    await stopJob("cancelled from job detail page");
  };

  return (
    <div className="page-stack job-detail-page">
      <section className="page-header job-detail-header">
        <Link to="/jobs" className="back-link">
          Back to jobs
        </Link>
        <p className="eyebrow">Job detail</p>
        <div className="job-detail-title-row">
          <h2>{pageTitle}</h2>
          {job ? <StatusBadge status={getJobStatus(job)} /> : null}
        </div>
        {fullJobId ? (
          <div className="job-id-row">
            <code title={fullJobId}>{shortenIdentifier(fullJobId)}</code>
            <CopyButton label="Copy job ID" text={fullJobId} />
          </div>
        ) : null}
        <div className="job-detail-meta-row">
          <span>
            {isPolling
              ? "Refreshing every 2.5 seconds"
              : "Polling stopped"}
          </span>
          {lastLoadedAt ? <span>Last updated {lastLoadedAt.toLocaleTimeString()}</span> : null}
          {isRefreshing ? <span>Refreshing now</span> : null}
        </div>
        <div className="button-row">
          <button className="button secondary" type="button" onClick={() => void reload()}>
            Refresh
          </button>
          {canStopJob(job ?? undefined) ? (
            <button
              className="button danger"
              type="button"
              disabled={isStopping}
              onClick={() => void handleStopJob()}
            >
              {isStopping ? "Stopping..." : "Stop Job"}
            </button>
          ) : null}
        </div>
      </section>

      {isLoading ? <LoadingState label="Loading job..." /> : null}
      {error ? <ErrorState message={error} onRetry={() => void reload()} /> : null}
      {stopError ? <p className="form-error">{stopError}</p> : null}

      {!isLoading && job ? (
        <>
          <JobSummary
            job={job}
            isPolling={isPolling}
            isRefreshing={isRefreshing}
            showProgress={false}
            durationLabel={durationLabel}
            message={currentActivity}
          />
          <JobProgressPanel progress={progress} />

          {isFailedJob(job) ? <ErrorPanel job={job} /> : null}
          <PayloadSection payload={requestPayload} />
          <LogsSection logs={logs} />

          <section className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Artifacts</p>
                <h3>{artifacts.length} items</h3>
              </div>
            </div>
            <ArtifactList artifacts={artifacts} />
          </section>
        </>
      ) : null}
    </div>
  );
}
