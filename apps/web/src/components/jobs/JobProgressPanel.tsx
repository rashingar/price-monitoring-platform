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
  const completedCount = progress.steps_completed ?? progress.completed_steps?.length;
  const latestMessage =
    typeof progress.details?.message === "string"
      ? progress.details.message
      : typeof progress.details?.latest_message === "string"
        ? progress.details.latest_message
        : undefined;
  const currentModel =
    typeof progress.details?.model === "string"
      ? progress.details.model
      : typeof progress.details?.current_model === "string"
        ? progress.details.current_model
        : undefined;

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
    <section className="panel job-progress-panel" aria-labelledby="job-progress-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Progress</p>
          <h3 id="job-progress-heading">{currentLabel}</h3>
        </div>
      </div>

      {completedCount !== undefined ? (
        <div className="job-progress-meter" aria-label={`${completedCount} steps completed`}>
          <span style={{ width: `${Math.min(100, Math.max(8, completedCount * 12))}%` }} />
        </div>
      ) : null}

      <dl className="summary-grid job-progress-grid">
        {currentModel ? (
          <div>
            <dt>Current model</dt>
            <dd>{currentModel}</dd>
          </div>
        ) : null}
        <div>
          <dt>Pipeline step</dt>
          <dd>{currentLabel}</dd>
        </div>
        {completedCount !== undefined ? (
          <div>
            <dt>Steps completed</dt>
            <dd>{completedCount}</dd>
          </div>
        ) : null}
        {progress.elapsed_seconds !== undefined ? (
          <div>
            <dt>Elapsed</dt>
            <dd>{formatDurationSeconds(progress.elapsed_seconds)}</dd>
          </div>
        ) : null}
        {progress.current_step_elapsed_seconds !== undefined ? (
          <div>
            <dt>Step elapsed</dt>
            <dd>{formatDurationSeconds(progress.current_step_elapsed_seconds)}</dd>
          </div>
        ) : null}
        {progress.step_started_at ? (
          <div>
            <dt>Step started</dt>
            <dd>{formatDateTime(progress.step_started_at)}</dd>
          </div>
        ) : null}
        {progress.last_progress_at ? (
          <div>
            <dt>Last progress</dt>
            <dd>{formatDateTime(progress.last_progress_at)}</dd>
          </div>
        ) : null}
      </dl>

      {latestMessage ? <p className="job-progress-message">{latestMessage}</p> : null}

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
