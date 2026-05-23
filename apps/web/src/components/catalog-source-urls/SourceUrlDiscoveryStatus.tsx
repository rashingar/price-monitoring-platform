import type { SourceUrlAgentRun } from "../../api/commerceTypes";
import {
  formatDate,
  formatValue,
  runMessage,
  sourceUrlAgentRunId,
  sourceUrlStatusClass,
} from "./sourceUrlDrawerUtils";

export function SourceUrlDiscoveryStatus({
  run,
  isLoading,
}: {
  run: SourceUrlAgentRun | null;
  isLoading: boolean;
}) {
  if (!run && !isLoading) {
    return null;
  }

  const message = runMessage(run);
  return (
    <section className="source-url-discovery-block" aria-label="Latest discovery job">
      <div className="source-url-discovery-block-header">
        <strong>Latest discovery job</strong>
        {isLoading ? <span className="muted">Refreshing...</span> : null}
      </div>
      {run ? (
        <dl className="source-url-discovery-meta">
          <div>
            <dt>Run id</dt>
            <dd>{formatValue(sourceUrlAgentRunId(run))}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>
              <span className={`status-badge ${sourceUrlStatusClass(run.status)}`}>
                {formatValue(run.status)}
              </span>
            </dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>{formatValue(run.source ?? run.source_name)}</dd>
          </div>
          <div>
            <dt>Created</dt>
            <dd>{formatDate(run.created_at)}</dd>
          </div>
          <div>
            <dt>Completed</dt>
            <dd>{formatDate(run.completed_at)}</dd>
          </div>
        </dl>
      ) : (
        <p className="muted">No discovery job yet.</p>
      )}
      {message ? <p className="form-warning">{message}</p> : null}
    </section>
  );
}
