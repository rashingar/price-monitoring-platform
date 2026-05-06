import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { commerceClient, getCommerceApiErrorMessage } from "../api/commerceClient";
import type {
  ArtifactItem,
  SourceUrlAgentRun,
  SourceUrlAgentRunArtifactsResponse,
  SourceUrlAgentRunRequest,
  VendorSourceCapability,
} from "../api/commerceTypes";
import { ArtifactList } from "../components/ArtifactList";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";

const DEFAULT_RUN_REQUEST: SourceUrlAgentRunRequest = {
  mode: "catalog",
  source: "all",
  missing_only: true,
  active_only: true,
  dry_run: true,
  apply_high_confidence: false,
  limit: 20,
  rate_limit_seconds: 2,
};

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

function getCounter(run: SourceUrlAgentRun, key: keyof SourceUrlAgentRun): number {
  const summary = isRecord(run.summary) ? run.summary : {};
  return parseNumberLike(run[key] ?? summary[key]);
}

function makeRunRequest(form: SourceUrlAgentRunRequest): SourceUrlAgentRunRequest {
  return {
    ...form,
    mode: String(form.mode || "catalog"),
    source: String(form.source || "all"),
    limit: form.limit === null ? null : Math.max(1, Number(form.limit) || DEFAULT_RUN_REQUEST.limit || 20),
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
  const [form, setForm] = useState<SourceUrlAgentRunRequest>(DEFAULT_RUN_REQUEST);
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
      .listVendorSources(controller.signal)
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

  const launchRun = async () => {
    setIsLaunching(true);
    setNotice(null);
    try {
      const createdRun = await commerceClient.createSourceUrlAgentRun(makeRunRequest(form));
      setRuns((current) => mergeRun(current, createdRun));
      setNotice(`Vendor source discovery run ${getRunId(createdRun)} launched.`);
    } catch (launchError) {
      setNotice(getCommerceApiErrorMessage(launchError));
    } finally {
      setIsLaunching(false);
    }
  };

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

  return (
    <div className="page-stack source-url-agent-page">
      <header className="page-header">
        <p className="eyebrow">Vendor Sources</p>
        <h2>Vendor Source Discovery Runs</h2>
        <p>Launch bounded vendor source discovery runs and review the candidates they produce.</p>
      </header>

      <section className="panel source-url-agent-warning-panel" aria-label="Vendor Sources warnings">
        <ul className="source-url-warning-list">
          <li>Dry-run does not activate URLs.</li>
          <li>Apply-high-confidence writes DB rows.</li>
          <li>Do not run full catalog until a 5-product dry-run is verified.</li>
        </ul>
      </section>

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
              Vendor source filter
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
            {isSourcesLoading ? <span className="muted">Loading vendor sources...</span> : null}
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

          <div className="button-row">
            <button className="button primary" type="submit" disabled={isLaunching}>
              {isLaunching ? "Launching..." : "Launch run"}
            </button>
          </div>
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
        </dl>

        {notice ? <p className="form-warning">{notice}</p> : null}
        {isLoading ? <LoadingState label="Loading vendor source discovery runs..." /> : null}
        {error ? <ErrorState message={error} onRetry={() => void loadRuns()} /> : null}
        {!isLoading && !error && runs.length === 0 ? (
          <EmptyState
            title="No vendor source discovery runs"
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
                            to={`/vendor-sources/candidates?run_id=${encodeURIComponent(runId)}`}
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
              title={`Vendor source discovery artifacts for ${artifactRunId}`}
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
