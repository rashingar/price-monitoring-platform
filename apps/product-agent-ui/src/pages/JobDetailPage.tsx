import { Link, useParams } from "react-router-dom";
import { canStopJob, getJobIdentifier, getRequestPayload } from "../api/jobUtils";
import { ArtifactList } from "../components/jobs/ArtifactList";
import { JobSummary } from "../components/jobs/JobSummary";
import { JsonBlock } from "../components/jobs/JsonBlock";
import { LogsPanel } from "../components/jobs/LogsPanel";
import { ErrorState, LoadingState } from "../components/layout/StateBlocks";
import { useJobDetail } from "../hooks/useJobDetail";

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
    <div className="page-stack">
      <section className="page-header">
        <Link to="/jobs" className="back-link">
          Back to jobs
        </Link>
        <p className="eyebrow">Job detail</p>
        <h2>{jobId ?? "Unknown job"}</h2>
        <p>
          {isPolling
            ? "Polling this job every 2.5 seconds."
            : "Polling stopped for this job."}
        </p>
      </section>

      <div className="toolbar">
        {lastLoadedAt ? (
          <span className="muted">Last loaded {lastLoadedAt.toLocaleTimeString()}</span>
        ) : null}
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

      {isLoading ? <LoadingState label="Loading job..." /> : null}
      {error ? <ErrorState message={error} onRetry={() => void reload()} /> : null}
      {stopError ? <p className="form-error">{stopError}</p> : null}

      {!isLoading && job ? (
        <>
          <JobSummary job={job} isPolling={isPolling} isRefreshing={isRefreshing} />

          <section className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Request payload</p>
                <h3>Submitted input</h3>
              </div>
            </div>
            <JsonBlock value={getRequestPayload(job)} />
          </section>

          <section className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Logs</p>
                <h3>{logs.length} entries</h3>
              </div>
            </div>
            <LogsPanel logs={logs} />
          </section>

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
