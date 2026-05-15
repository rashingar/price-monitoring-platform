import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { commerceClient, getCommerceApiErrorMessage } from "../api/commerceClient";
import type {
  ArtifactItem,
  SourceUrlAgentRun,
  SourceUrlAgentRunArtifactsResponse,
  SourceUrlAgentReadiness,
  SourceUrlAgentRunRequest,
  VendorSourceCapability,
} from "../api/commerceTypes";
import { ArtifactList } from "../components/ArtifactList";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";
import { SourceUrlAgentReadinessCard } from "../features/source-url-agent-readiness/SourceUrlAgentReadinessCard";
import { launchDisabledReason } from "../features/source-url-agent-readiness/sourceUrlAgentReadinessHelpers";

const DEFAULT_RUN_REQUEST: SourceUrlAgentRunRequest = {
  mode: "catalog",
  source: "all",
  selected_models: [],
  missing_only: true,
  active_only: true,
  dry_run: true,
  apply_high_confidence: false,
  limit: 20,
  rate_limit_seconds: 2,
};

function parseSelectedModelsParam(value: string | null): string[] {
  if (!value) {
    return [];
  }

  const seen = new Set<string>();
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => {
      if (!item || seen.has(item)) {
        return false;
      }
      seen.add(item);
      return true;
    });
}

function buildRunRequestFromHandoff(searchParams: URLSearchParams): SourceUrlAgentRunRequest {
  const selectedModels = parseSelectedModelsParam(searchParams.get("models"));
  const source = searchParams.get("source")?.trim() || DEFAULT_RUN_REQUEST.source;
  const selectedCount = selectedModels.length;

  return {
    ...DEFAULT_RUN_REQUEST,
    source,
    selected_models: selectedModels,
    limit: selectedCount > 0 ? selectedCount : DEFAULT_RUN_REQUEST.limit,
    max_products_per_batch: selectedCount > 0 ? selectedCount : undefined,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getRunId(run: SourceUrlAgentRun): string {
  const value = run.run_id ?? run.id;
  return value === null || value === undefined || value === "" ? "-" : String(value);
}

function normalizeLabel(value: unknown): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    return "-";
  }

  return value.replace(/_/g, " ");
}

function parseNumberLike(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  return 0;
}

function formatNumber(value: unknown): string {
  return parseNumberLike(value).toLocaleString();
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return String(value);
}

function formatDate(value: unknown): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    return "-";
  }

  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function statusClass(status: unknown): string {
  const normalized = typeof status === "string" ? status.toLowerCase() : "";
  if (normalized === "succeeded" || normalized === "completed" || normalized === "success") {
    return "success";
  }

  if (normalized === "running" || normalized === "queued") {
    return "active";
  }

  if (normalized === "failed" || normalized === "error") {
    return "danger";
  }

  if (normalized === "cancelled" || normalized === "canceled") {
    return "warning";
  }

  return "neutral";
}

function isActiveStatus(status: unknown): boolean {
  const normalized = typeof status === "string" ? status.toLowerCase() : "";
  return normalized === "queued" || normalized === "running";
}

function getCounter(run: SourceUrlAgentRun, key: keyof SourceUrlAgentRun): number {
  const summary = isRecord(run.summary) ? run.summary : {};
  return parseNumberLike(run[key] ?? summary[key]);
}

function getTaskProgress(run: SourceUrlAgentRun): { finished: number; total: number } {
  const summary = isRecord(run.summary) ? run.summary : {};
  const total = parseNumberLike(run.task_total_count ?? summary.task_total_count);
  const finished = parseNumberLike(run.task_finished_count ?? summary.task_finished_count);
  return { finished, total };
}

function formatTaskProgress(run: SourceUrlAgentRun): string {
  const { finished, total } = getTaskProgress(run);
  return total > 0 ? `${finished.toLocaleString()} / ${total.toLocaleString()}` : "-";
}

function makeRunRequest(form: SourceUrlAgentRunRequest): SourceUrlAgentRunRequest {
  const selectedModels = Array.isArray(form.selected_models)
    ? parseSelectedModelsParam(form.selected_models.join(","))
    : [];
  const selectedCount = selectedModels.length;

  return {
    ...form,
    mode: String(form.mode || "catalog"),
    source: String(form.source || "all"),
    selected_models: selectedModels,
    limit:
      form.limit === null
        ? null
        : Math.max(selectedCount || 1, Number(form.limit) || DEFAULT_RUN_REQUEST.limit || 20),
    max_products_per_batch:
      selectedCount > 0
        ? Math.max(selectedCount, Number(form.max_products_per_batch) || selectedCount)
        : form.max_products_per_batch,
    rate_limit_seconds:
      form.rate_limit_seconds === null
        ? null
        : Math.max(0, Number(form.rate_limit_seconds) || DEFAULT_RUN_REQUEST.rate_limit_seconds || 2),
  };
}

function mergeRun(runs: SourceUrlAgentRun[], nextRun: SourceUrlAgentRun): SourceUrlAgentRun[] {
  const nextRunId = getRunId(nextRun);
  const existingIndex = runs.findIndex((run) => getRunId(run) === nextRunId);
  if (existingIndex < 0) {
    return [nextRun, ...runs];
  }

  return runs.map((run, index) => (index === existingIndex ? { ...run, ...nextRun } : run));
}

function normalizeSourceType(value: unknown): string {
  return typeof value === "string" && value.trim().length > 0
    ? value.trim().toLowerCase().replace(/[_-]/g, " ")
    : "source";
}

function sourceTypeLabel(source: VendorSourceCapability): string {
  const type = normalizeSourceType(source.source_type);
  if (type === "direct vendor" || type === "vendor" || type === "direct") {
    return "direct vendor";
  }

  return type;
}

function capabilityBadges(source: VendorSourceCapability): string[] {
  const badges = [sourceTypeLabel(source)];
  if (source.capture_enabled && source.capture_implemented) {
    badges.push("capture ready");
  } else if (source.discovery_enabled) {
    badges.push("discovery only");
  }

  return badges;
}

function dedupeCapabilities(sources: VendorSourceCapability[]): VendorSourceCapability[] {
  const seen = new Set<string>();
  return sources.filter((source) => {
    const key = String(source.source_name).toLowerCase();
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function SummaryItem({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{formatNumber(value)}</dd>
    </div>
  );
}

export function SourceUrlAgentRunsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const handoffModels = useMemo(() => parseSelectedModelsParam(searchParams.get("models")), [searchParams]);
  const shouldAutoLaunch = searchParams.get("auto_launch") === "1";
  const autoLaunchKey = searchParams.toString();
  const autoLaunchStartedRef = useRef<string | null>(null);
  const [form, setForm] = useState<SourceUrlAgentRunRequest>(() => buildRunRequestFromHandoff(searchParams));
  const [runs, setRuns] = useState<SourceUrlAgentRun[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLaunching, setIsLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [refreshingRunId, setRefreshingRunId] = useState<string | null>(null);
  const [artifactRunId, setArtifactRunId] = useState<string | null>(null);
  const [artifactResponse, setArtifactResponse] = useState<SourceUrlAgentRunArtifactsResponse | null>(null);
  const [isArtifactsLoading, setIsArtifactsLoading] = useState(false);
  const [artifactError, setArtifactError] = useState<string | null>(null);
  const [vendorSources, setVendorSources] = useState<VendorSourceCapability[]>([]);
  const [isSourcesLoading, setIsSourcesLoading] = useState(true);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [readinessState, setReadinessState] = useState<{
    readiness: SourceUrlAgentReadiness | null;
    isLoading: boolean;
    error: string | null;
  }>({ readiness: null, isLoading: true, error: null });

  const loadRuns = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    try {
      const nextRuns = await commerceClient.listSourceUrlAgentRuns(signal);
      if (!signal?.aborted) {
        setRuns(nextRuns);
        setError(null);
      }
    } catch (loadError) {
      if (!signal?.aborted) {
        setRuns([]);
        setError(getCommerceApiErrorMessage(loadError));
      }
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadRuns(controller.signal);
    return () => controller.abort();
  }, [loadRuns]);

  useEffect(() => {
    const controller = new AbortController();
    setIsSourcesLoading(true);
    commerceClient
      .listSourceUrlAgentSources(controller.signal)
      .then((sources) => {
        if (!controller.signal.aborted) {
          setVendorSources(dedupeCapabilities(sources));
          setSourceError(null);
        }
      })
      .catch((loadError) => {
        if (!controller.signal.aborted) {
          setVendorSources([]);
          setSourceError(getCommerceApiErrorMessage(loadError));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsSourcesLoading(false);
        }
      });
    return () => controller.abort();
  }, []);

  const totals = useMemo(
    () =>
      runs.reduce<{
        selected_count: number;
        candidate_count: number;
        needs_review_count: number;
        error_count: number;
      }>(
        (summary, run) => ({
          selected_count: summary.selected_count + getCounter(run, "selected_count"),
          candidate_count: summary.candidate_count + getCounter(run, "candidate_count"),
          needs_review_count: summary.needs_review_count + getCounter(run, "needs_review_count"),
          error_count: summary.error_count + getCounter(run, "error_count"),
        }),
        {
          selected_count: 0,
          candidate_count: 0,
          needs_review_count: 0,
          error_count: 0,
        },
      ),
    [runs],
  );

  const updateForm = <Key extends keyof SourceUrlAgentRunRequest>(
    key: Key,
    value: SourceUrlAgentRunRequest[Key],
  ) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const discoverySourceOptions = useMemo(
    () => dedupeCapabilities(vendorSources.filter((source) => source.discovery_enabled)),
    [vendorSources],
  );

  const launchRun = async (requestOverride?: SourceUrlAgentRunRequest) => {
    const disabledReason = launchDisabledReason(
      readinessState.readiness,
      readinessState.isLoading,
      readinessState.error,
    );
    if (disabledReason) {
      setNotice(disabledReason);
      return;
    }

    setIsLaunching(true);
    setNotice(null);
    try {
      const createdRun = await commerceClient.createSourceUrlAgentRun(makeRunRequest(requestOverride ?? form));
      setRuns((current) => mergeRun(current, createdRun));
      setNotice(`Find Source run ${getRunId(createdRun)} launched.`);
    } catch (launchError) {
      setNotice(getCommerceApiErrorMessage(launchError));
    } finally {
      setIsLaunching(false);
    }
  };

  useEffect(() => {
    const nextRequest = buildRunRequestFromHandoff(searchParams);
    setForm(nextRequest);
  }, [searchParams]);

  useEffect(() => {
    if (!shouldAutoLaunch || handoffModels.length === 0 || autoLaunchStartedRef.current === autoLaunchKey) {
      return;
    }
    if (readinessState.isLoading) {
      return;
    }

    autoLaunchStartedRef.current = autoLaunchKey;
    void launchRun(buildRunRequestFromHandoff(searchParams)).finally(() => {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.delete("auto_launch");
      setSearchParams(nextParams, { replace: true });
    });
  }, [
    autoLaunchKey,
    handoffModels.length,
    readinessState.isLoading,
    searchParams,
    setSearchParams,
    shouldAutoLaunch,
  ]);

  const refreshRun = async (run: SourceUrlAgentRun) => {
    const runId = getRunId(run);
    if (runId === "-") {
      return;
    }

    setRefreshingRunId(runId);
    setNotice(null);
    try {
      const nextRun = await commerceClient.getSourceUrlAgentRun(runId);
      setRuns((current) => mergeRun(current, nextRun));
    } catch (refreshError) {
      setNotice(getCommerceApiErrorMessage(refreshError));
    } finally {
      setRefreshingRunId(null);
    }
  };

  const openArtifacts = async (run: SourceUrlAgentRun) => {
    const runId = getRunId(run);
    if (runId === "-") {
      return;
    }

    setArtifactRunId(runId);
    setArtifactResponse(null);
    setArtifactError(null);
    setIsArtifactsLoading(true);
    try {
      const response = await commerceClient.listSourceUrlAgentRunArtifacts(runId);
      setArtifactResponse(response);
    } catch (artifactsError) {
      const inlineArtifacts = Array.isArray(run.artifacts) ? run.artifacts : [];
      setArtifactResponse({ run_id: runId, items: inlineArtifacts });
      setArtifactError(getCommerceApiErrorMessage(artifactsError));
    } finally {
      setIsArtifactsLoading(false);
    }
  };

  const previewArtifact = async (path: string) => {
    const response = await commerceClient.readArtifact(path, 200_000);
    return response.content;
  };

  const artifacts = artifactResponse?.items ?? [];
  const hasActiveRuns = runs.some((run) => isActiveStatus(run.status));
  const launchBlockReason = launchDisabledReason(
    readinessState.readiness,
    readinessState.isLoading,
    readinessState.error,
  );
  const isLaunchDisabled = isLaunching || Boolean(launchBlockReason);
  const handleReadinessStateChange = useCallback(
    (state: { readiness: SourceUrlAgentReadiness | null; isLoading: boolean; error: string | null }) => {
      setReadinessState(state);
    },
    [],
  );

  useEffect(() => {
    if (!hasActiveRuns) {
      return;
    }

    const timer = window.setInterval(() => {
      void loadRuns();
    }, 2_500);
    return () => window.clearInterval(timer);
  }, [hasActiveRuns, loadRuns]);

  return (
    <div className="page-stack source-url-agent-page">
      <header className="page-header">
        <p className="eyebrow">Find Source</p>
        <h2>Find Source</h2>
        <p>Launch bounded source discovery runs and review the candidates they produce.</p>
      </header>

      <section className="panel source-url-agent-warning-panel" aria-label="Find Source warnings">
        <ul className="source-url-warning-list">
          <li>Dry-run does not activate URLs.</li>
          <li>Apply-high-confidence writes DB rows.</li>
          <li>Do not run full catalog until a 5-product dry-run is verified.</li>
        </ul>
      </section>

      {handoffModels.length > 0 ? (
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Catalog handoff</p>
              <h3>
                {handoffModels.length.toLocaleString()} selected{" "}
                {handoffModels.length === 1 ? "model" : "models"}
              </h3>
            </div>
            <button
              className="button secondary"
              type="button"
              onClick={() => setSearchParams(new URLSearchParams(), { replace: true })}
              disabled={isLaunching}
            >
              Clear handoff
            </button>
          </div>
          <p className="muted">
            Discovery is scoped to the selected Catalog models and existing missing-only defaults.
          </p>
          <p className="muted">{handoffModels.slice(0, 40).join(", ")}</p>
          {handoffModels.length > 40 ? (
            <p className="muted">Showing 40 of {handoffModels.length.toLocaleString()} selected models.</p>
          ) : null}
        </section>
      ) : null}

      <SourceUrlAgentReadinessCard
        blockLaunch
        className="source-url-readiness-launch-card"
        onReadinessStateChange={handleReadinessStateChange}
      />

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Launch</p>
            <h3>Bounded dry-run from DB catalog</h3>
          </div>
          <button
            className="button secondary"
            type="button"
            onClick={() => setForm(DEFAULT_RUN_REQUEST)}
            disabled={isLaunching}
          >
            Reset defaults
          </button>
        </div>

        <form
          className="form"
          onSubmit={(event) => {
            event.preventDefault();
            void launchRun();
          }}
        >
          <div className="filter-grid source-url-agent-form-grid">
            <label>
              Mode
              <select
                value={String(form.mode)}
                onChange={(event) => updateForm("mode", event.target.value)}
              >
                <option value="catalog">catalog</option>
              </select>
            </label>
            <label title="Vendor source_name filter. Direct vendors appear when the backend reports discovery_enabled=true.">
              Source filter
              <select
                value={String(form.source)}
                onChange={(event) => updateForm("source", event.target.value)}
              >
                <option value="all">all supported sources</option>
                {discoverySourceOptions.map((source) => (
                  <option key={String(source.source_name)} value={String(source.source_name)}>
                    {String(source.source_name)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Limit
              <input
                type="number"
                min={1}
                step={1}
                value={form.limit ?? ""}
                onChange={(event) => updateForm("limit", Number(event.target.value) || 1)}
              />
            </label>
            <label>
              Rate limit seconds
              <input
                type="number"
                min={0}
                step={0.25}
                value={form.rate_limit_seconds ?? ""}
                onChange={(event) =>
                  updateForm("rate_limit_seconds", Number(event.target.value) || 0)
                }
              />
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={form.missing_only}
                onChange={(event) => updateForm("missing_only", event.target.checked)}
              />
              Missing only
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={form.active_only}
                onChange={(event) => updateForm("active_only", event.target.checked)}
              />
              Active only
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={form.dry_run}
                onChange={(event) => updateForm("dry_run", event.target.checked)}
              />
              Dry-run
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={form.apply_high_confidence}
                onChange={(event) => updateForm("apply_high_confidence", event.target.checked)}
              />
              Apply high confidence
            </label>
          </div>

          <div className="source-capability-strip" aria-label="Vendor source capabilities">
            {isSourcesLoading ? <span className="muted">Loading sources...</span> : null}
            {!isSourcesLoading && sourceError ? <span className="form-warning">{sourceError}</span> : null}
            {!isSourcesLoading && discoverySourceOptions.length > 0
              ? discoverySourceOptions.map((source) => (
                  <div className="source-capability-card" key={String(source.source_name)}>
                    <strong>{String(source.source_name)}</strong>
                    <span className="muted">{source.source_domain ?? "-"}</span>
                    <span className="source-capability-badges">
                      {capabilityBadges(source).map((badge) => (
                        <span className="status-badge neutral" key={badge}>
                          {badge}
                        </span>
                      ))}
                    </span>
                  </div>
                ))
              : null}
          </div>

          {form.apply_high_confidence ? (
            <p className="form-warning">Apply-high-confidence writes DB rows for accepted matches.</p>
          ) : null}
          {!form.dry_run ? (
            <p className="form-warning">This is not a dry-run. Verify a 5-product dry-run first.</p>
          ) : null}
          {isLaunching ? (
            <LoadingState label="Running browser-based Find Source discovery. This can take several minutes for multi-model selections..." />
          ) : null}

          <div className="button-row">
            <button className="button primary" type="submit" disabled={isLaunchDisabled}>
              {isLaunching ? "Launching..." : "Launch run"}
            </button>
          </div>
          {launchBlockReason ? <p className="form-warning">{launchBlockReason}</p> : null}
        </form>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">History</p>
            <h3>Run history</h3>
          </div>
          <button className="button secondary" type="button" onClick={() => void loadRuns()}>
            Refresh
          </button>
        </div>

        <dl className="summary-grid source-url-agent-summary-grid">
          <SummaryItem label="Runs" value={runs.length} />
          <SummaryItem label="Selected" value={totals.selected_count} />
          <SummaryItem label="Candidates" value={totals.candidate_count} />
          <SummaryItem label="Needs review" value={totals.needs_review_count} />
          <SummaryItem label="Errors" value={totals.error_count} />
          <SummaryItem
            label="Active tasks"
            value={runs.reduce((count, run) => {
              const taskCounts = isRecord(run.task_counts) ? run.task_counts : {};
              return count + parseNumberLike(taskCounts.queued) + parseNumberLike(taskCounts.running);
            }, 0)}
          />
        </dl>

        {notice ? <p className="form-warning">{notice}</p> : null}
        {isLoading ? <LoadingState label="Loading Find Source runs..." /> : null}
        {error ? <ErrorState message={error} onRetry={() => void loadRuns()} /> : null}
        {!isLoading && !error && runs.length === 0 ? (
          <EmptyState
            title="No Find Source runs"
            message="Launch a bounded dry-run to create candidate URLs for review."
          />
        ) : null}

        {!isLoading && !error && runs.length > 0 ? (
          <div className="table-wrap source-url-agent-runs-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>run_id</th>
                  <th>source</th>
                  <th>mode</th>
                  <th>status</th>
                  <th>selected_count</th>
                  <th>candidate_count</th>
                  <th>task progress</th>
                  <th>matched_count</th>
                  <th>needs_review_count</th>
                  <th>not_found_count</th>
                  <th>error_count</th>
                  <th>created</th>
                  <th>started</th>
                  <th>completed</th>
                  <th>actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run, index) => {
                  const runId = getRunId(run);
                  const isRefreshing = refreshingRunId === runId;
                  return (
                    <tr key={`${runId}-${index}`}>
                      <td className="source-url-agent-run-id">{runId}</td>
                      <td>{formatValue(run.source)}</td>
                      <td>{formatValue(run.mode)}</td>
                      <td>
                        <span className={`status-badge ${statusClass(run.status)}`}>
                          {normalizeLabel(run.status)}
                        </span>
                      </td>
                      <td>{formatNumber(getCounter(run, "selected_count"))}</td>
                      <td>{formatNumber(getCounter(run, "candidate_count"))}</td>
                      <td>{formatTaskProgress(run)}</td>
                      <td>{formatNumber(getCounter(run, "matched_count"))}</td>
                      <td>{formatNumber(getCounter(run, "needs_review_count"))}</td>
                      <td>{formatNumber(getCounter(run, "not_found_count"))}</td>
                      <td>{formatNumber(getCounter(run, "error_count"))}</td>
                      <td>{formatDate(run.created_at)}</td>
                      <td>{formatDate(run.started_at)}</td>
                      <td>{formatDate(run.completed_at)}</td>
                      <td>
                        <div className="source-url-agent-actions">
                          <button
                            className="button secondary compact-button"
                            type="button"
                            disabled={isRefreshing || runId === "-"}
                            onClick={() => void refreshRun(run)}
                          >
                            {isRefreshing ? "Refreshing..." : "Refresh"}
                          </button>
                          <Link
                            className="button secondary compact-button"
                            to={`/find-source/candidates?run_id=${encodeURIComponent(runId)}`}
                          >
                            Review candidates
                          </Link>
                          <button
                            className="button secondary compact-button"
                            type="button"
                            disabled={runId === "-"}
                            onClick={() => void openArtifacts(run)}
                          >
                            Open artifacts
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      {artifactRunId ? (
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Artifacts</p>
              <h3>Run {artifactRunId}</h3>
            </div>
            <button
              className="button secondary"
              type="button"
              onClick={() => {
                setArtifactRunId(null);
                setArtifactResponse(null);
                setArtifactError(null);
              }}
            >
              Close
            </button>
          </div>
          {isArtifactsLoading ? <LoadingState label="Loading run artifacts..." /> : null}
          {artifactError ? <p className="form-warning">{artifactError}</p> : null}
          {!isArtifactsLoading ? (
            <ArtifactList
              title={`Find Source artifacts for ${artifactRunId}`}
              items={artifacts as ArtifactItem[]}
              onPreview={previewArtifact}
              getDownloadUrl={commerceClient.getArtifactDownloadUrl}
            />
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
