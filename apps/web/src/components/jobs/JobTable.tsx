import { Link } from "react-router-dom";
import {
  canRetryWithoutScraping,
  canStartFromScratch,
  canStopJob,
  formatDateTime,
  getJobIdentifier,
  getJobStageLabel,
  getJobStatus,
} from "../../api/jobUtils";
import type { Job } from "../../api/types";
import { StatusBadge } from "./StatusBadge";

const RETRY_ICON = "\u21bb";
const START_ICON = "\u25b6";

interface JobTableProps {
  jobs: Job[];
  onStopJob?: (job: Job) => void | Promise<void>;
  onRetryJob?: (job: Job) => void | Promise<void>;
  onStartJob?: (job: Job) => void | Promise<void>;
  stoppingJobIds?: string[];
  retryingJobIds?: string[];
  startingJobIds?: string[];
}

export function JobTable({
  jobs,
  onStopJob,
  onRetryJob,
  onStartJob,
  stoppingJobIds = [],
  retryingJobIds = [],
  startingJobIds = [],
}: JobTableProps) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Job</th>
            <th>Stage</th>
            <th>Status</th>
            <th>Created</th>
            <th>Updated</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job, index) => {
            const jobId = getJobIdentifier(job);
            const jobIdKey = jobId ?? "";
            const rowKey = jobId ?? `job-${index}`;
            const showStop = Boolean(onStopJob && canStopJob(job) && jobId);
            const showRetry = Boolean(onRetryJob && canRetryWithoutScraping(job) && jobId);
            const showStart = Boolean(onStartJob && canStartFromScratch(job) && jobId);
            return (
              <tr key={rowKey}>
                <td>
                  {jobId ? (
                    <Link to={`/jobs/${encodeURIComponent(jobId)}`}>{jobId}</Link>
                  ) : (
                    <span className="muted">Missing id</span>
                  )}
                </td>
                <td>{getJobStageLabel(job)}</td>
                <td>
                  <StatusBadge status={getJobStatus(job)} />
                </td>
                <td>{formatDateTime(job.created_at)}</td>
                <td>{formatDateTime(job.updated_at)}</td>
                <td>
                  {showStop || showRetry || showStart ? (
                    <div className="jobs-action-row">
                      {showStop ? (
                        <button
                          className="button danger compact-button"
                          type="button"
                          disabled={stoppingJobIds.includes(jobIdKey)}
                          onClick={() => void onStopJob?.(job)}
                        >
                          {stoppingJobIds.includes(jobIdKey) ? "Stopping..." : "Stop"}
                        </button>
                      ) : null}
                      {showRetry ? (
                        <button
                          className="button warning compact-button"
                          type="button"
                          disabled={retryingJobIds.includes(jobIdKey)}
                          onClick={() => void onRetryJob?.(job)}
                        >
                          {retryingJobIds.includes(jobIdKey)
                            ? `${RETRY_ICON} Retrying...`
                            : `${RETRY_ICON} Retry`}
                        </button>
                      ) : null}
                      {showStart ? (
                        <button
                          className="button secondary compact-button"
                          type="button"
                          disabled={startingJobIds.includes(jobIdKey)}
                          onClick={() => void onStartJob?.(job)}
                        >
                          {startingJobIds.includes(jobIdKey)
                            ? `${START_ICON} Starting...`
                            : `${START_ICON} Start`}
                        </button>
                      ) : null}
                    </div>
                  ) : (
                    <span className="muted">-</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
