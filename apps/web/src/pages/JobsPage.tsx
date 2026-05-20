import { useMemo } from "react";
import {
  getJobIdentifier,
  getJobStatusBucket,
  type JobStatusBucket,
} from "../api/jobUtils";
import type { Job } from "../api/types";
import { JobTable } from "../components/jobs/JobTable";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";
import { useJobs } from "../hooks/useJobs";
import { usePersistentPageState } from "../hooks/usePersistentPageState";

type StatusFilter = "all" | JobStatusBucket;

const FILTERS: Array<{ key: StatusFilter; label: string }> = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "succeeded", label: "Succeeded" },
  { key: "failed", label: "Failed" },
  { key: "cancelled", label: "Cancelled" },
];

export function JobsPage() {
  const {
    error,
    isLoading,
    isPolling,
    isRefreshing,
    jobs,
    lastLoadedAt,
    reload,
    retryJob,
    retryJobError,
    retryingJobIds,
    startJob,
    startJobError,
    startingJobIds,
    stopJob,
    stopJobError,
    stoppingJobIds,
  } = useJobs();
  const [statusFilter, setStatusFilter, resetJobsState] = usePersistentPageState<StatusFilter>(
    "product-factory-ui:jobs:v1",
    "all",
  );

  const filterCounts = useMemo(() => {
    const counts: Record<StatusFilter, number> = {
      all: jobs.length,
      active: 0,
      succeeded: 0,
      failed: 0,
      cancelled: 0,
      unknown: 0,
    };

    for (const job of jobs) {
      counts[getJobStatusBucket(job)] += 1;
    }

    return counts;
  }, [jobs]);

  const visibleJobs = useMemo(
    () =>
      statusFilter === "all"
        ? jobs
        : jobs.filter((job) => getJobStatusBucket(job) === statusFilter),
    [jobs, statusFilter],
  );

  const handleStopJob = async (job: Job) => {
    const jobId = getJobIdentifier(job);
    if (!jobId) {
      return;
    }

    const confirmed = window.confirm(
      `Stop job ${jobId}? This marks the job as cancelled. Active in-process work may need the backend service to finish before resources are fully released.`,
    );
    if (!confirmed) {
      return;
    }

    await stopJob(jobId, "cancelled from jobs page");
  };

  const handleRetryJob = async (job: Job) => {
    const jobId = getJobIdentifier(job);
    if (!jobId) {
      return;
    }

    const confirmed = window.confirm(
      `Retry job ${jobId} without scraping again? This reuses prepared artifacts and reruns authoring/render/publish.`,
    );
    if (!confirmed) {
      return;
    }

    await retryJob(jobId);
  };

  const handleStartJob = async (job: Job) => {
    const jobId = getJobIdentifier(job);
    if (!jobId) {
      return;
    }

    const confirmed = window.confirm(
      `Start job ${jobId} from the beginning? This will scrape the source URL again.`,
    );
    if (!confirmed) {
      return;
    }

    await startJob(jobId);
  };

  return (
    <div className="page-stack">
      <section className="page-header">
        <p className="eyebrow">Jobs</p>
        <h2>Recent jobs</h2>
        <p>
          {isPolling
            ? "Polling active jobs every 2.5 seconds."
            : "Polling stops when no queued or running jobs are present."}
        </p>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Job list</p>
            <h3>{jobs.length} jobs</h3>
          </div>
          <button className="button secondary" type="button" onClick={() => void reload()}>
            Refresh
          </button>
          <button className="text-button" type="button" onClick={resetJobsState}>
            Reset saved Jobs state
          </button>
        </div>

        {lastLoadedAt ? (
          <p className="muted">Last loaded {lastLoadedAt.toLocaleTimeString()}</p>
        ) : null}
        {isRefreshing ? <p className="muted">Refreshing active jobs...</p> : null}
        {stopJobError ? <p className="form-error">{stopJobError}</p> : null}
        {retryJobError ? <p className="form-error">{retryJobError}</p> : null}
        {startJobError ? <p className="form-error">{startJobError}</p> : null}

        <div className="filter-button-row" aria-label="Job status filters">
          {FILTERS.map((filter) => (
            <button
              key={filter.key}
              className={`button filter-button ${statusFilter === filter.key ? "active" : ""}`}
              type="button"
              onClick={() => setStatusFilter(filter.key)}
            >
              {filter.label} {filterCounts[filter.key]}
            </button>
          ))}
        </div>

        {isLoading ? <LoadingState label="Loading jobs..." /> : null}
        {error ? <ErrorState message={error} onRetry={() => void reload()} /> : null}
        {!isLoading && !error && jobs.length === 0 ? (
          <EmptyState title="No jobs found" message="The backend returned an empty job list." />
        ) : null}
        {!isLoading && !error && jobs.length > 0 && visibleJobs.length === 0 ? (
          <EmptyState title="No matching jobs" message="No jobs match the selected status filter." />
        ) : null}
        {!isLoading && !error && visibleJobs.length > 0 ? (
          <JobTable
            jobs={visibleJobs}
            onStopJob={handleStopJob}
            onRetryJob={handleRetryJob}
            onStartJob={handleStartJob}
            stoppingJobIds={stoppingJobIds}
            retryingJobIds={retryingJobIds}
            startingJobIds={startingJobIds}
          />
        ) : null}
      </section>
    </div>
  );
}
