import { Link } from "react-router-dom";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CommerceApiError,
  commerceClient,
  getArtifactPath,
  getCommerceApiErrorMessage,
} from "../api/commerceClient";
import type {
  ArtifactItem,
  FetchPriceMonitoringResult,
  PriceMonitoringDbStatus,
  PriceMonitoringFetchLogsResponse,
  PriceMonitoringRun,
} from "../api/commerceTypes";
import {
  getPriceMonitoringDbBlockingMessage,
  isPriceMonitoringDbReady,
} from "../api/priceMonitoringDbGate";
import {
  formatFetchStatus,
  getFetchStatusTone,
  initialPriceMonitoringWorkflowState,
  isActiveFetchStatus,
  isCancelledFetchStatus,
  isKilledFetchStatus,
  PRICE_MONITORING_EXECUTIONS_STATE_KEY,
  PRICE_MONITORING_STATE_KEY,
  shouldTreatArtifactsAsDiagnostic,
  type PriceMonitoringWorkflowState,
} from "../api/priceMonitoringUtils";
import { ArtifactList } from "../components/ArtifactList";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";
import { PriceMonitoringDbStatusBanner } from "../components/priceMonitoring/PriceMonitoringDbStatusBanner";
import { usePersistentPageState } from "../hooks/usePersistentPageState";

interface ExecutionsPageState {
  selectedExecutionId: string;
  logsOpen: boolean;
}

const initialExecutionsPageState: ExecutionsPageState = {
  selectedExecutionId: "",
  logsOpen: false,
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return String(value);
}

function formatFetchInputMode(value: unknown): string {
  if (value === "source_urls") {
    return "Source URL monitoring";
  }

  if (value === "legacy_marketplace") {
    return "Deprecated fetch diagnostic";
  }

  return formatValue(value);
}

function executionIdOf(execution: FetchPriceMonitoringResult): string {
  const value = execution.execution_id;
  return value === null || value === undefined ? "" : String(value);
}

function getLastTimestamp(executions: FetchPriceMonitoringResult[]): string {
  for (const key of ["completed_at", "started_at", "queued_at"] as const) {
    const value = executions.find((execution) => execution[key])?.[key];
    if (value) {
      return value;
    }
  }

  return "";
}

function sortExecutions(executions: FetchPriceMonitoringResult[]): FetchPriceMonitoringResult[] {
  return [...executions].sort((first, second) => {
    const firstTime = Date.parse(
      first.queued_at ?? first.started_at ?? first.completed_at ?? first.cancelled_at ?? first.killed_at ?? "",
    );
    const secondTime = Date.parse(
      second.queued_at ?? second.started_at ?? second.completed_at ?? second.cancelled_at ?? second.killed_at ?? "",
    );
    return (Number.isNaN(secondTime) ? 0 : secondTime) - (Number.isNaN(firstTime) ? 0 : firstTime);
  });
}

function artifactValueToItem(value: unknown): ArtifactItem | null {
  if (typeof value !== "string" || value.trim().length === 0) {
    if (
      typeof value === "object" &&
      value !== null &&
      "path" in value &&
      typeof (value as { path?: unknown }).path === "string"
    ) {
      return value as ArtifactItem;
    }
    return null;
  }

  const path = value.trim();
  const parts = path.split(/[\\/]+/).filter(Boolean);
  return {
    name: parts.length > 0 ? parts[parts.length - 1] : path,
    path,
    extension: null,
    size_bytes: null,
    modified_at: null,
    download_url: null,
    read_url: null,
    is_allowed: true,
    can_read: true,
    can_download: true,
    warning: null,
  };
}

function getExecutionArtifacts(execution: FetchPriceMonitoringResult): ArtifactItem[] {
  const fallback = [
    execution.input_csv_path,
    execution.enriched_csv_path,
    execution.fetch_summary_path,
    execution.fetch_result_path,
    execution.execution_path,
    execution.log_path,
  ]
    .map(artifactValueToItem)
    .filter((item): item is ArtifactItem => item !== null);

  return execution.artifacts && execution.artifacts.length > 0 ? execution.artifacts : fallback;
}

export function PriceMonitoringExecutionsPage() {
  const [workflowState, setWorkflowState] =
    usePersistentPageState<PriceMonitoringWorkflowState>(
      PRICE_MONITORING_STATE_KEY,
      initialPriceMonitoringWorkflowState,
      { debounceMs: 250 },
    );
  const [pageState, setPageState, resetPageState] =
    usePersistentPageState<ExecutionsPageState>(
      PRICE_MONITORING_EXECUTIONS_STATE_KEY,
      initialExecutionsPageState,
      { debounceMs: 150 },
    );
  const runId = workflowState.currentRunId.trim();
  const [run, setRun] = useState<PriceMonitoringRun | null>(null);
  const [runWarning, setRunWarning] = useState<string | null>(null);
  const [executions, setExecutions] = useState<FetchPriceMonitoringResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefetching, setIsRefetching] = useState(false);
  const [logs, setLogs] = useState<PriceMonitoringFetchLogsResponse | null>(null);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [isLogsLoading, setIsLogsLoading] = useState(false);
  const [dbStatus, setDbStatus] = useState<PriceMonitoringDbStatus | null>(null);
  const [dbStatusError, setDbStatusError] = useState<string | null>(null);
  const [isDbStatusLoading, setIsDbStatusLoading] = useState(false);

  const sortedExecutions = useMemo(() => sortExecutions(executions), [executions]);
  const selectedExecution =
    sortedExecutions.find((execution) => executionIdOf(execution) === pageState.selectedExecutionId) ??
    sortedExecutions[0] ??
    null;

  const clearSavedRun = useCallback(
    (message: string) => {
      setWorkflowState((current) => ({
        ...current,
        currentRunId: "",
        currentExecutionId: "",
      }));
      setRun(null);
      setExecutions([]);
      setError(message);
    },
    [setWorkflowState],
  );

  const loadDbStatus = useCallback(async (signal?: AbortSignal) => {
    setIsDbStatusLoading(true);
    setDbStatusError(null);
    try {
      const status = await commerceClient.getPriceMonitoringDbStatus(signal);
      if (signal?.aborted) {
        return;
      }
      setDbStatus(status);
    } catch (error) {
      if (!signal?.aborted) {
        setDbStatus(null);
        setDbStatusError(getCommerceApiErrorMessage(error));
      }
    } finally {
      if (!signal?.aborted) {
        setIsDbStatusLoading(false);
      }
    }
  }, []);

  const loadExecutions = useCallback(
    async (signal?: AbortSignal) => {
      if (!runId) {
        setRun(null);
        setExecutions([]);
        return;
      }

      setIsLoading(true);
      setError(null);
      setRunWarning(null);

      try {
        const [runResult, executionResult] = await Promise.allSettled([
          commerceClient.getPriceMonitoringRun(runId, signal),
          commerceClient.listPriceMonitoringFetchExecutions(runId, signal),
        ]);

        if (signal?.aborted) {
          return;
        }

        if (runResult.status === "fulfilled") {
          setRun(runResult.value);
        } else if (runResult.reason instanceof CommerceApiError && runResult.reason.status === 404) {
          clearSavedRun(`Saved Price Monitoring run ${runId} was not found. The saved run selection was cleared.`);
          return;
        } else {
          setRun(null);
          if (runResult.reason instanceof CommerceApiError && runResult.reason.status === 503) {
            setRunWarning(getPriceMonitoringDbBlockingMessage(null));
          } else {
            setRunWarning(`Run details could not be loaded: ${getCommerceApiErrorMessage(runResult.reason)}`);
          }
        }

        if (executionResult.status === "fulfilled") {
          const nextExecutions = executionResult.value;
          setExecutions(nextExecutions);
          const selectedId = pageState.selectedExecutionId;
          if (!selectedId || !nextExecutions.some((execution) => executionIdOf(execution) === selectedId)) {
            const latestId = executionIdOf(sortExecutions(nextExecutions)[0] ?? {});
            setPageState((current) => ({ ...current, selectedExecutionId: latestId }));
          }
        } else if (
          executionResult.reason instanceof CommerceApiError &&
          executionResult.reason.status === 404
        ) {
          clearSavedRun(`Saved Price Monitoring run ${runId} was not found. The saved run selection was cleared.`);
        } else {
          setExecutions([]);
          if (executionResult.reason instanceof CommerceApiError && executionResult.reason.status === 503) {
            setError(null);
            setRunWarning(getPriceMonitoringDbBlockingMessage(null));
          } else {
            setError(getCommerceApiErrorMessage(executionResult.reason));
          }
        }
      } finally {
        if (!signal?.aborted) {
          setIsLoading(false);
        }
      }
    },
    [clearSavedRun, pageState.selectedExecutionId, runId, setPageState],
  );

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([loadDbStatus(controller.signal), loadExecutions(controller.signal)]);
    return () => controller.abort();
  }, [loadDbStatus, loadExecutions]);

  useEffect(() => {
    if (!sortedExecutions.some((execution) => isActiveFetchStatus(execution.status))) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      void loadExecutions();
    }, 2500);

    return () => window.clearInterval(intervalId);
  }, [loadExecutions, sortedExecutions]);

  const loadLogs = async () => {
    if (!runId || !selectedExecution?.execution_id) {
      return;
    }

    if (!isPriceMonitoringDbReady(dbStatus)) {
      setLogsError(getPriceMonitoringDbBlockingMessage(dbStatus));
      return;
    }

    setIsLogsLoading(true);
    setLogsError(null);
    try {
      const nextLogs = await commerceClient.getPriceMonitoringFetchExecutionLogs(
        runId,
        selectedExecution.execution_id,
      );
      setLogs(nextLogs);
      setPageState((current) => ({ ...current, logsOpen: true }));
    } catch (logError) {
      setLogsError(getCommerceApiErrorMessage(logError));
    } finally {
      setIsLogsLoading(false);
    }
  };

  const previewArtifact = async (path: string) => {
    const response = await commerceClient.readArtifact(path, 200_000);
    return response.content;
  };

  const refetchKilledExecution = async () => {
    if (!runId || !selectedExecution || !isKilledFetchStatus(selectedExecution.status)) {
      return;
    }

    if (!isPriceMonitoringDbReady(dbStatus)) {
      setError(getPriceMonitoringDbBlockingMessage(dbStatus));
      return;
    }

    setIsRefetching(true);
    setError(null);
    try {
      const result = await commerceClient.fetchPriceMonitoringRun(runId, {
        source:
          selectedExecution.source === "skroutz" || selectedExecution.source === "bestprice"
            ? selectedExecution.source
            : null,
        catalog_url: selectedExecution.catalog_url ?? null,
      });
      setWorkflowState((current) => ({
        ...current,
        currentExecutionId: executionIdOf(result),
      }));
      await loadExecutions();
    } catch (refetchError) {
      if (refetchError instanceof CommerceApiError && refetchError.status === 409) {
        const latest = await commerceClient.getPriceMonitoringFetch(runId);
        setWorkflowState((current) => ({
          ...current,
          currentExecutionId: executionIdOf(latest),
        }));
        setError("Another fetch is active for this run. Adopted the latest active execution.");
        await loadExecutions();
      } else {
        setError(getCommerceApiErrorMessage(refetchError));
      }
    } finally {
      setIsRefetching(false);
    }
  };

  const latestFetchStatus = run?.latest_fetch?.status ?? sortedExecutions[0]?.status;
  const artifacts = selectedExecution ? getExecutionArtifacts(selectedExecution) : [];
  const diagnosticArtifacts = selectedExecution
    ? shouldTreatArtifactsAsDiagnostic(selectedExecution)
    : false;
  const dbAvailable = isPriceMonitoringDbReady(dbStatus);
  const dbBlockingMessage = getPriceMonitoringDbBlockingMessage(dbStatus);
  const dbActionTitle = dbAvailable ? undefined : dbBlockingMessage;

  return (
    <div className="page-stack">
      <section className="page-header">
        <p className="eyebrow">Price Monitoring</p>
        <h2>Fetch executions</h2>
        <p>Execution history for the current selected Price Monitoring run.</p>
        <button className="text-button" type="button" onClick={resetPageState}>
          Reset saved Executions state
        </button>
      </section>

      <PriceMonitoringDbStatusBanner
        status={dbStatus}
        error={dbStatusError}
        isLoading={isDbStatusLoading}
        onRetry={() => void loadDbStatus()}
      />

      {!runId ? (
        <EmptyState
          title="No run selected"
          message="Select or create a Price Monitoring run from Workflow first."
        />
      ) : (
        <>
          <section className="current-run-header">
            <div>
              <p className="eyebrow">Current run</p>
              <strong>{runId}</strong>
            </div>
            <div>
              <span className="muted">Marketplace source</span>
              <strong>{formatValue(run?.source ?? sortedExecutions[0]?.source)}</strong>
            </div>
            <div>
              <span className="muted">Latest fetch</span>
              <span className={`status-badge ${getFetchStatusTone(latestFetchStatus)}`}>
                {formatFetchStatus(latestFetchStatus)}
              </span>
            </div>
            <div>
              <span className="muted">Executions</span>
              <strong>{executions.length.toLocaleString()}</strong>
            </div>
            <div>
              <span className="muted">Last timestamp</span>
              <strong>{formatValue(getLastTimestamp(sortedExecutions))}</strong>
            </div>
            <Link to="/price-monitoring" className="text-button">
              Back to Workflow
            </Link>
          </section>
          {runWarning ? <p className="form-warning">{runWarning}</p> : null}

          <section className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Executions</p>
                <h3>History for run {runId}</h3>
              </div>
              <button
                className="button secondary"
                type="button"
                disabled={!dbAvailable}
                title={dbActionTitle}
                onClick={() => void loadExecutions()}
              >
                Refresh
              </button>
            </div>

            {isLoading ? <LoadingState label="Loading fetch executions..." /> : null}
            {error ? <ErrorState message={error} onRetry={() => void loadExecutions()} /> : null}
            {!dbAvailable ? (
              <EmptyState
                title="Execution history locked"
                message={dbBlockingMessage}
              />
            ) : null}
            {dbAvailable && !isLoading && !error && sortedExecutions.length === 0 ? (
              <EmptyState title="No executions" message="No fetch executions were returned for this run." />
            ) : null}
            {sortedExecutions.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Execution ID</th>
                      <th>Status</th>
                      <th>Marketplace source</th>
                      <th>Input mode</th>
                      <th>Queued</th>
                      <th>Started</th>
                      <th>Completed</th>
                      <th>Cancelled</th>
                      <th>Killed</th>
                      <th>Queue</th>
                      <th>Stale</th>
                      <th>Exit</th>
                      <th>Termination</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedExecutions.map((execution, index) => {
                      const executionId = executionIdOf(execution);
                      const selected = executionId && executionId === executionIdOf(selectedExecution ?? {});
                      return (
                        <tr
                          key={executionId || index}
                          className={selected ? "selected-row" : undefined}
                        >
                          <td>
                            <button
                              className="text-button"
                              type="button"
                              onClick={() =>
                                setPageState((current) => ({
                                  ...current,
                                  selectedExecutionId: executionId,
                                }))
                              }
                            >
                              {formatValue(executionId)}
                            </button>
                          </td>
                          <td>
                            <span className={`status-badge ${getFetchStatusTone(execution.status)}`}>
                              {formatFetchStatus(execution.status)}
                            </span>
                          </td>
                          <td>{formatValue(execution.source)}</td>
                          <td>{formatFetchInputMode(execution.fetch_input_mode)}</td>
                          <td>{formatValue(execution.queued_at)}</td>
                          <td>{formatValue(execution.started_at)}</td>
                          <td>{formatValue(execution.completed_at)}</td>
                          <td>{formatValue(execution.cancelled_at)}</td>
                          <td>{formatValue(execution.killed_at)}</td>
                          <td>{formatValue(execution.queue_position)}</td>
                          <td>{formatValue(execution.stale)}</td>
                          <td>{formatValue(execution.exit_code)}</td>
                          <td>{formatValue(execution.termination_mode)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>

          {selectedExecution ? (
            <section className="panel">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Execution detail</p>
                  <h3>{formatValue(executionIdOf(selectedExecution))}</h3>
                </div>
                {isKilledFetchStatus(selectedExecution.status) ? (
                  <button
                    className="button secondary"
                    type="button"
                    disabled={isRefetching || !dbAvailable}
                    title={dbActionTitle}
                    onClick={() => void refetchKilledExecution()}
                  >
                    {isRefetching ? "Refetching..." : "Refetch"}
                  </button>
                ) : null}
              </div>

              <dl className="summary-grid">
                <SummaryItem label="Status" value={formatFetchStatus(selectedExecution.status)} />
                <SummaryItem label="Marketplace source" value={selectedExecution.source} />
                <SummaryItem label="Fetch input mode" value={formatFetchInputMode(selectedExecution.fetch_input_mode)} />
                <SummaryItem label="Catalog URL diagnostic" value={selectedExecution.catalog_url} />
                <SummaryItem label="Queued" value={selectedExecution.queued_at} />
                <SummaryItem label="Started" value={selectedExecution.started_at} />
                <SummaryItem label="Completed" value={selectedExecution.completed_at} />
                <SummaryItem label="Cancelled" value={selectedExecution.cancelled_at} />
                <SummaryItem label="Killed" value={selectedExecution.killed_at} />
                <SummaryItem label="Killed reason" value={selectedExecution.killed_reason} />
                <SummaryItem label="Termination mode" value={selectedExecution.termination_mode} />
                <SummaryItem label="Exit code" value={selectedExecution.exit_code} />
                <SummaryItem label="Process ID" value={selectedExecution.process_id} />
                <SummaryItem label="Parent process ID" value={selectedExecution.parent_process_id} />
                <SummaryItem label="Process group ID" value={selectedExecution.process_group_id} />
                <SummaryItem label="Terminate sent" value={selectedExecution.terminate_sent_at} />
                <SummaryItem label="Kill sent" value={selectedExecution.kill_sent_at} />
                <SummaryItem label="Log path" value={getArtifactPath(selectedExecution.log_path)} />
                <SummaryItem label="Diagnostic artifacts" value={selectedExecution.artifacts_are_diagnostic} />
              </dl>
              {selectedExecution.fetch_input_mode === "source_urls" ? (
                <p>
                  <span className="status-badge ok">Source URL monitoring</span>
                </p>
              ) : null}
              {selectedExecution.command && selectedExecution.command.length > 0 ? (
                <pre className="json-block">{JSON.stringify(selectedExecution.command, null, 2)}</pre>
              ) : null}

              <details
                className="state-block fetch-logs-panel"
                open={pageState.logsOpen}
                onToggle={(event) =>
                  setPageState((current) => ({
                    ...current,
                    logsOpen: event.currentTarget.open,
                  }))
                }
              >
                <summary>
                  <strong>Log preview</strong>
                  <span className="muted"> {logs?.lines.length ?? 0} lines loaded</span>
                </summary>
                <button
                  className="button secondary"
                  type="button"
                  disabled={isLogsLoading || !dbAvailable}
                  title={dbActionTitle}
                  onClick={loadLogs}
                >
                  {isLogsLoading ? "Loading logs..." : "Preview logs"}
                </button>
                {logsError ? <p className="form-error">{logsError}</p> : null}
                {logs && logs.lines.length > 0 ? (
                  <pre className="json-block fetch-log-block">{logs.lines.join("\n")}</pre>
                ) : (
                  <p className="muted">Logs are loaded only when previewed.</p>
                )}
              </details>

              {artifacts.length > 0 && diagnosticArtifacts ? (
                <details className="diagnostic-artifacts">
                  <summary>
                    <strong>Diagnostic artifacts</strong>
                    <span className="muted"> {artifacts.length.toLocaleString()} items</span>
                  </summary>
                  {selectedExecution.artifact_warning ? (
                    <p className="form-warning">{selectedExecution.artifact_warning}</p>
                  ) : null}
                  <ArtifactList
                    title="Diagnostic artifacts"
                    items={artifacts}
                    onPreview={previewArtifact}
                    getDownloadUrl={commerceClient.getArtifactDownloadUrl}
                  />
                </details>
              ) : null}
              {artifacts.length > 0 && !diagnosticArtifacts && isCancelledFetchStatus(selectedExecution.status) ? (
                <div className="compact-list">
                  <strong>Cancelled execution artifacts</strong>
                  <ul>
                    {artifacts.map((artifact, index) => (
                      <li key={`${artifact.path}-${index}`}>
                        <span>{artifact.name}</span>
                        <small className="artifact-path">{artifact.path}</small>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {artifacts.length > 0 &&
              !diagnosticArtifacts &&
              !isCancelledFetchStatus(selectedExecution.status) ? (
                <ArtifactList
                  title="Execution artifacts"
                  items={artifacts}
                  onPreview={previewArtifact}
                  getDownloadUrl={commerceClient.getArtifactDownloadUrl}
                />
              ) : null}
              {isActiveFetchStatus(selectedExecution.status) ? (
                <p className="muted">This execution is still active. Refresh to update status.</p>
              ) : null}
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}

function SummaryItem({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{formatValue(value)}</dd>
    </div>
  );
}
