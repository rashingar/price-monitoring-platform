import {
  formatDateTime,
  getJobIdentifier,
  getJobStageLabel,
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
}

export function JobSummary({ job, isRefreshing, isPolling, showProgress = true }: JobSummaryProps) {
  const progress = getJobProgress(job);

  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Job summary</p>
          <h2>{getJobIdentifier(job) ?? "Unknown job"}</h2>
        </div>
        <StatusBadge status={getJobStatus(job)} />
      </div>

      <dl className="summary-grid">
        <div>
          <dt>Stage</dt>
          <dd>{getJobStageLabel(job)}</dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{formatDateTime(job.created_at)}</dd>
        </div>
        <div>
          <dt>Updated</dt>
          <dd>{formatDateTime(job.updated_at)}</dd>
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
          <dt>Polling</dt>
          <dd>{isPolling && isActiveJob(job) ? "Active" : "Stopped"}</dd>
        </div>
      </dl>

      {showProgress ? <JobProgressPanel progress={progress} compact /> : null}

      {isRefreshing ? <p className="muted">Refreshing job state...</p> : null}
    </section>
  );
}
