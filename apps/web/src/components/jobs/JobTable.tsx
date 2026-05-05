import { Link } from "react-router-dom";
import {
  canStopJob,
  formatDateTime,
  getJobIdentifier,
  getJobStageLabel,
  getJobStatus,
} from "../../api/jobUtils";
import type { Job } from "../../api/types";
import { StatusBadge } from "./StatusBadge";

interface JobTableProps {
  jobs: Job[];
  onStopJob?: (job: Job) => void | Promise<void>;
  stoppingJobIds?: string[];
}

export function JobTable({ jobs, onStopJob, stoppingJobIds = [] }: JobTableProps) {
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
            const rowKey = jobId ?? `job-${index}`;
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
                  {onStopJob && canStopJob(job) && jobId ? (
                    <button
                      className="button danger compact-button"
                      type="button"
                      disabled={stoppingJobIds.includes(jobId)}
                      onClick={() => void onStopJob(job)}
                    >
                      {stoppingJobIds.includes(jobId) ? "Stopping..." : "Stop"}
                    </button>
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
