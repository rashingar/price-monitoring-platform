import { formatDateTime } from "../../api/jobUtils";
import { formatDurationSeconds, type JobProgress } from "../../api/jobProgress";

interface JobProgressPanelProps {
  progress: JobProgress | null;
  compact?: boolean;
}

export function JobProgressPanel({ progress, compact = false }: JobProgressPanelProps) {
  if (!progress) {
    return null;
  }

  const currentLabel = progress.current_step_label ?? progress.current_step ?? "In progress";

  if (compact) {
    return (
      <div className="job-progress-inline">
        <span>
          <strong>Step:</strong> {currentLabel}
        </span>
        {progress.elapsed_seconds !== undefined ? (
          <span>
            <strong>Elapsed:</strong> {formatDurationSeconds(progress.elapsed_seconds)}
          </span>
        ) : null}
        {progress.current_step_elapsed_seconds !== undefined ? (
          <span>
            <strong>Step time:</strong> {formatDurationSeconds(progress.current_step_elapsed_seconds)}
          </span>
        ) : null}
        {progress.last_progress_at ? (
          <span>
            <strong>Progress:</strong> {formatDateTime(progress.last_progress_at)}
          </span>
        ) : null}
      </div>
    );
  }

  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Progress</p>
          <h3>{currentLabel}</h3>
        </div>
      </div>

      <dl className="summary-grid job-progress-grid">
        <div>
          <dt>Current step</dt>
          <dd>{currentLabel}</dd>
        </div>
        <div>
          <dt>Last progress</dt>
          <dd>{formatDateTime(progress.last_progress_at)}</dd>
        </div>
        <div>
          <dt>Elapsed</dt>
          <dd>{formatDurationSeconds(progress.elapsed_seconds)}</dd>
        </div>
        <div>
          <dt>Step elapsed</dt>
          <dd>{formatDurationSeconds(progress.current_step_elapsed_seconds)}</dd>
        </div>
        <div>
          <dt>Step started</dt>
          <dd>{formatDateTime(progress.step_started_at)}</dd>
        </div>
        <div>
          <dt>Steps completed</dt>
          <dd>{progress.steps_completed ?? progress.completed_steps?.length ?? "-"}</dd>
        </div>
      </dl>

      {progress.completed_steps && progress.completed_steps.length > 0 ? (
        <div className="job-progress-steps">
          <strong>Completed steps</strong>
          <ol>
            {progress.completed_steps.slice(-8).map((step, index) => (
              <li key={`${step.step ?? step.label ?? "step"}-${index}`}>
                <span>{step.label ?? step.step ?? "Step"}</span>
                <span>{formatDurationSeconds(step.elapsed_seconds)}</span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </section>
  );
}
