import {
  formatDateTime,
  getJobStageLabel,
  getJobWorkflow,
  getJobStatus,
  isActiveJob,
} from "../../api/jobUtils";
import { getJobProgress } from "../../api/jobProgress";
import type { Job } from "../../api/types";
import { JobProgressPanel } from "./JobProgressPanel";
import { StatusBadge } from "./StatusBadge";

interface JobSummaryProps {
  job: Job;
  isRefreshing: boolean;
  isPolling: boolean;
  showProgress?: boolean;
  durationLabel?: string;
  message?: string | null;
}

function formatJobLabel(value: string): string {
  const words = value
    .replace(/[-_]+/g, " ")
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
  if (!words) {
    return "Job";
  }

  return `${words.charAt(0).toUpperCase()}${words.slice(1)}`;
}

export function JobSummary({
  job,
  isRefreshing,
  isPolling,
  showProgress = true,
  durationLabel = "-",
  message,
}: JobSummaryProps) {
  const progress = getJobProgress(job);
  const jobTypeLabel = formatJobLabel(getJobWorkflow(job));

  return (
    <section className="panel job-summary-card" aria-labelledby="job-summary-heading">
      <div className="job-summary-topline">
        <StatusBadge status={getJobStatus(job)} />
        <div className="job-summary-main">
          <p className="eyebrow">Job summary</p>
          <h2 id="job-summary-heading">{jobTypeLabel}</h2>
        </div>
        {progress?.steps_completed !== undefined ? (
          <span className="status-badge neutral">{progress.steps_completed} steps completed</span>
        ) : null}
      </div>

      <div className="job-summary-current">
        <span>
          <strong>Type</strong>
          {jobTypeLabel}
        </span>
        {getJobStageLabel(job) !== getJobWorkflow(job) ? (
          <span>
            <strong>Stage</strong>
            {getJobStageLabel(job)}
          </span>
        ) : null}
        <span>
          <strong>Polling</strong>
          {isPolling && isActiveJob(job) ? "Active" : "Stopped"}
        </span>
        {message ? (
          <span className="job-summary-message">
            <strong>Current activity</strong>
            {message}
          </span>
        ) : null}
        {isRefreshing ? <span className="muted">Refreshing job state...</span> : null}
      </div>

      <dl className="summary-grid job-detail-summary-grid">
        <div>
          <dt>Created</dt>
          <dd>{formatDateTime(job.created_at)}</dd>
        </div>
        <div>
          <dt>Started</dt>
          <dd>{formatDateTime(job.started_at)}</dd>
        </div>
        <div>
          <dt>Finished</dt>
          <dd>{formatDateTime(job.finished_at)}</dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>{durationLabel}</dd>
        </div>
      </dl>

      {showProgress ? <JobProgressPanel progress={progress} compact /> : null}
    </section>
  );
}
