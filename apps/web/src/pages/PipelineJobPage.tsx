import { Link } from "react-router-dom";
import { canStopJob, getJobIdentifier, getJobStatus } from "../api/jobUtils";
import {
  initialPrepareFormState,
  PrepareJobForm,
  type PrepareFormState,
} from "../components/forms/PrepareJobForm";
import { StatusBadge } from "../components/jobs/StatusBadge";
import { ErrorState } from "../components/layout/StateBlocks";
import { usePersistentPageState } from "../hooks/usePersistentPageState";
import { usePipelineRun } from "../hooks/usePipelineRun";

export function PipelineJobPage() {
  const { currentRun, isRunning, startPipeline, stopJobError, stopStageJob, stoppingJobIds } =
    usePipelineRun();
  const [form, setForm, resetForm] = usePersistentPageState<PrepareFormState>(
    "product-agent-ui:pipeline:v1",
    initialPrepareFormState,
  );

  const handleStopStageJob = async (jobId: string) => {
    const confirmed = window.confirm(
      `Stop pipeline job ${jobId}? This marks the job as cancelled and the current pipeline run will stop.`,
    );
    if (!confirmed) {
      return;
    }

    await stopStageJob(jobId, "cancelled from pipeline page");
  };

  return (
    <div className="page-stack narrow">
      <section className="page-header">
        <p className="eyebrow">Pipeline</p>
        <h2>Run full pipeline</h2>
        <p>Queues prepare, waits for success, then queues render and publish.</p>
        <button className="text-button" type="button" onClick={resetForm}>
          Reset saved Pipeline state
        </button>
      </section>

      {currentRun ? (
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Current run</p>
              <h3>{currentRun.status}</h3>
            </div>
            <span className="muted">Started {currentRun.startedAt.toLocaleTimeString()}</span>
          </div>

          {currentRun.error ? <ErrorState message={currentRun.error} /> : null}
          {stopJobError ? <p className="form-error">{stopJobError}</p> : null}

          <ol className="pipeline-stage-list">
            {currentRun.stages.map((stage) => {
              const jobId = stage.job ? getJobIdentifier(stage.job) : undefined;
              return (
                <li key={stage.key} className="pipeline-stage-item">
                  <div className="pipeline-stage-main">
                    <strong>{stage.label}</strong>
                    {jobId ? (
                      <Link to={`/jobs/${encodeURIComponent(jobId)}`}>{jobId}</Link>
                    ) : (
                      <span className="muted">No job yet</span>
                    )}
                  </div>
                  <div className="pipeline-stage-actions">
                    <StatusBadge status={stage.job ? getJobStatus(stage.job) : stage.status} />
                    {stage.job && jobId && canStopJob(stage.job) ? (
                      <button
                        className="button danger compact-button"
                        type="button"
                        disabled={stoppingJobIds.includes(jobId)}
                        onClick={() => void handleStopStageJob(jobId)}
                      >
                        {stoppingJobIds.includes(jobId) ? "Stopping..." : "Stop"}
                      </button>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
      ) : null}

      <section className="panel">
        <PrepareJobForm
          actionLabel="Run full pipeline"
          busyLabel="Pipeline is running..."
          error={currentRun?.status === "failed" ? currentRun.error : null}
          isSubmitting={isRunning}
          initialForm={form}
          onFormChange={setForm}
          onSubmit={(request) => void startPipeline(request)}
        />
      </section>
    </div>
  );
}
