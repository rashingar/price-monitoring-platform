import { useCallback, useEffect, useMemo, useState } from "react";
import { commerceClient, getCommerceApiErrorMessage } from "../api/commerceClient";
import type {
  ArtifactItem,
  VendorSourceCapability,
  VendorSourceCaptureRun,
  VendorSourceCaptureRunArtifactsResponse,
  VendorSourceCaptureRunRequest,
} from "../api/commerceTypes";
import { ArtifactList } from "../components/ArtifactList";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";

const DEFAULT_CAPTURE_REQUEST: VendorSourceCaptureRunRequest = {
  source_filter: "",
  limit: 50,
  include_not_due: false,
  refresh_after_minutes: 1440,
  catalog_product_ids: [],
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getRunId(run: VendorSourceCaptureRun): string {
  const value = run.run_id ?? run.id;
  return value === null || value === undefined || value === "" ? "-" : String(value);
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

function normalizeLabel(value: unknown): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    return "-";
  }

  return value.replace(/_/g, " ");
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

function getCounter(run: VendorSourceCaptureRun, key: keyof VendorSourceCaptureRun): number {
  const summary = isRecord(run.summary) ? run.summary : {};
  return parseNumberLike(run[key] ?? summary[key]);
}

function sourceTypeLabel(source: VendorSourceCapability): string {
  const raw = typeof source.source_type === "string" ? source.source_type : "source";
  const normalized = raw.trim().toLowerCase().replace(/[_-]/g, " ");
  if (normalized === "direct vendor" || normalized === "vendor" || normalized === "direct") {
    return "direct vendor";
  }

  return normalized || "source";
}

function capabilityBadges(source: VendorSourceCapability): string[] {
  const badges = [sourceTypeLabel(source)];
  if (source.capture_enabled && source.capture_implemented) {
    badges.push("capture ready");
  } else if (source.capture_implemented) {
    badges.push("capture implemented");
  } else if (source.discovery_enabled) {
    badges.push("discovery only");
  } else {
    badges.push("disabled");
  }

  if (source.supports_xhr_capture) {
    badges.push("XHR capture");
  }

  return badges;
}

function formatSourceOptionLabel(source: VendorSourceCapability): string {
  const sourceName = String(source.source_name);
  const type = sourceTypeLabel(source);
  const captureLabel =
    source.capture_enabled && source.capture_implemented
      ? "capture ready"
      : source.capture_implemented
        ? "capture implemented"
        : source.discovery_enabled
          ? "discovery only"
          : "disabled";
  return `${sourceName} - ${type} - ${captureLabel}`;
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

function parseCatalogProductIds(value: string): Array<number | string> {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
    .map((item) => {
      const parsed = Number(item);
      return Number.isFinite(parsed) ? parsed : item;
    });
}

function makeRunRequest(form: VendorSourceCaptureRunRequest, catalogProductIdsText: string): VendorSourceCaptureRunRequest {
  const sourceFilter = typeof form.source_filter === "string" ? form.source_filter.trim() : "";
  return {
    source_filter: sourceFilter,
    limit: form.limit === null ? null : Math.max(1, Number(form.limit) || 50),
    include_not_due: form.include_not_due === true,
    refresh_after_minutes:
      form.refresh_after_minutes === null
        ? null
        : Math.max(0, Number(form.refresh_after_minutes) || 0),
    catalog_product_ids: parseCatalogProductIds(catalogProductIdsText),
  };
}

function mergeRun(runs: VendorSourceCaptureRun[], nextRun: VendorSourceCaptureRun): VendorSourceCaptureRun[] {
  const nextRunId = getRunId(nextRun);
  const existingIndex = runs.findIndex((run) => getRunId(run) === nextRunId);
  if (existingIndex < 0) {
    return [nextRun, ...runs];
  }

  return runs.map((run, index) => (index === existingIndex ? { ...run, ...nextRun } : run));
}

function SummaryItem({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{formatNumber(value)}</dd>
    </div>
  );
}

export function VendorSourceCaptureRunsPage() {
  const [form, setForm] = useState<VendorSourceCaptureRunRequest>(DEFAULT_CAPTURE_REQUEST);
  const [catalogProductIdsText, setCatalogProductIdsText] = useState("");
  const [runs, setRuns] = useState<VendorSourceCaptureRun[]>([]);
  const [sources, setSources] = useState<VendorSourceCapability[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSourcesLoading, setIsSourcesLoading] = useState(true);
  const [isLaunching, setIsLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [refreshingRunId, setRefreshingRunId] = useState<string | null>(null);
  const [artifactRunId, setArtifactRunId] = useState<string | null>(null);
  const [artifactResponse, setArtifactResponse] = useState<VendorSourceCaptureRunArtifactsResponse | null>(null);
  const [isArtifactsLoading, setIsArtifactsLoading] = useState(false);
  const [artifactError, setArtifactError] = useState<string | null>(null);

  const loadRuns = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    try {
      const nextRuns = await commerceClient.listVendorSourceCaptureRuns(signal);
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
      .then((nextSources) => {
        if (!controller.signal.aborted) {
          setSources(dedupeCapabilities(nextSources));
          setSourceError(null);
        }
      })
      .catch((loadError) => {
        if (!controller.signal.aborted) {
          setSources([]);
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

  const captureSourceOptions = useMemo(
    () => dedupeCapabilities(sources.filter((source) => source.capture_enabled && source.capture_implemented)),
    [sources],
  );

  const totals = useMemo(
    () =>
      runs.reduce<{
        selected: number;
        succeeded: number;
        failed: number;
        skipped: number;
      }>(
        (summary, run) => ({
          selected: summary.selected + getCounter(run, "selected_source_url_count"),
          succeeded: summary.succeeded + getCounter(run, "succeeded_count"),
          failed: summary.failed + getCounter(run, "failed_count"),
          skipped: summary.skipped + getCounter(run, "skipped_count"),
        }),
        { selected: 0, succeeded: 0, failed: 0, skipped: 0 },
      ),
    [runs],
  );

  const updateForm = <Key extends keyof VendorSourceCaptureRunRequest>(
    key: Key,
    value: VendorSourceCaptureRunRequest[Key],
  ) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const launchRun = async () => {
    if (typeof form.source_filter !== "string" || form.source_filter.trim().length === 0) {
      setNotice("Choose one source/vendor to capture.");
      return;
    }

    setIsLaunching(true);
    setNotice(null);
    try {
      const requestBody = makeRunRequest(form, catalogProductIdsText);
      const createdRun = await commerceClient.createVendorSourceCaptureRun(requestBody);
      setRuns((current) => mergeRun(current, createdRun));
      setNotice(`Vendor source capture run ${getRunId(createdRun)} launched.`);
    } catch (launchError) {
      setNotice(getCommerceApiErrorMessage(launchError));
    } finally {
      setIsLaunching(false);
    }
  };

  const refreshRun = async (run: VendorSourceCaptureRun) => {
    const runId = getRunId(run);
    if (runId === "-") {
      return;
    }

    setRefreshingRunId(runId);
    setNotice(null);
    try {
      const nextRun = await commerceClient.getVendorSourceCaptureRun(runId);
      setRuns((current) => mergeRun(current, nextRun));
    } catch (refreshError) {
      setNotice(getCommerceApiErrorMessage(refreshError));
    } finally {
      setRefreshingRunId(null);
    }
  };

  const openArtifacts = async (run: VendorSourceCaptureRun) => {
    const runId = getRunId(run);
    if (runId === "-") {
      return;
    }

    setArtifactRunId(runId);
    setArtifactResponse(null);
    setArtifactError(null);
    setIsArtifactsLoading(true);
    try {
      const response = await commerceClient.listVendorSourceCaptureRunArtifacts(runId);
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
  const sourceRequired = typeof form.source_filter !== "string" || form.source_filter.trim().length === 0;

  return (
    <div className="page-stack vendor-source-captures-page">
      <header className="page-header">
        <p className="eyebrow">Vendor Sources</p>
        <h2>Vendor Source Capture Runs</h2>
        <p>Capture runs monitor existing active source URLs. Price Monitoring does not discover URLs.</p>
        <p>One capture run writes one observation batch.</p>
      </header>

      <section className="panel source-url-agent-warning-panel" aria-label="Vendor source capture guidance">
        <ul className="source-url-warning-list">
          <li>Choose one concrete source/vendor per capture run.</li>
          <li>One capture run writes one observation batch.</li>
          <li>Products without active source URLs are not eligible for Price Monitoring.</li>
          <li>Use discovery, candidate review, or imports before capture when URLs are missing.</li>
        </ul>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Launch</p>
            <h3>Capture active source URLs</h3>
          </div>
          <button
            className="button secondary"
            type="button"
            onClick={() => {
              setForm(DEFAULT_CAPTURE_REQUEST);
              setCatalogProductIdsText("");
            }}
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
            <label title="Choose one capture-ready Vendor Sources source/vendor.">
              Source/vendor
              <select
                value={String(form.source_filter)}
                onChange={(event) => updateForm("source_filter", event.target.value)}
              >
                <option value="">Choose one source/vendor</option>
                {captureSourceOptions.map((source) => (
                  <option key={String(source.source_name)} value={String(source.source_name)}>
                    {formatSourceOptionLabel(source)}
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
              Refresh after minutes
              <input
                type="number"
                min={0}
                step={1}
                value={form.refresh_after_minutes ?? ""}
                onChange={(event) => updateForm("refresh_after_minutes", Number(event.target.value) || 0)}
              />
            </label>
            <label>
              catalog_product_ids
              <input
                value={catalogProductIdsText}
                onChange={(event) => setCatalogProductIdsText(event.target.value)}
                placeholder="Optional comma-separated ids"
              />
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={form.include_not_due === true}
                onChange={(event) => updateForm("include_not_due", event.target.checked)}
              />
              Include not due
            </label>
          </div>

          <div className="source-capability-strip" aria-label="Vendor source capture capabilities">
            {isSourcesLoading ? <span className="muted">Loading vendor sources...</span> : null}
            {!isSourcesLoading && sourceError ? <span className="form-warning">{sourceError}</span> : null}
            {!isSourcesLoading && sources.length > 0
              ? sources.map((source) => (
                  <div className="source-capability-card" key={String(source.source_name)}>
                    <strong>{String(source.source_name)}</strong>
                    <span className="muted">{source.source_domain ?? "-"}</span>
                    <span className="source-capability-badges">
                      {capabilityBadges(source).map((badge) => (
                        <span
                          className={`status-badge ${badge === "capture ready" ? "success" : "neutral"}`}
                          key={badge}
                        >
                          {badge}
                        </span>
                      ))}
                    </span>
                  </div>
                ))
              : null}
          </div>

          <div className="button-row">
            <button
              className="button primary"
              type="submit"
              disabled={isLaunching || sourceRequired}
              title={sourceRequired ? "Choose one source/vendor to capture." : undefined}
            >
              {isLaunching ? "Launching..." : "Launch capture run"}
            </button>
            {sourceRequired ? <span className="form-warning">Choose one source/vendor to capture.</span> : null}
          </div>
        </form>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">History</p>
            <h3>Capture run history</h3>
          </div>
          <button className="button secondary" type="button" onClick={() => void loadRuns()}>
            Refresh
          </button>
        </div>

        <dl className="summary-grid source-url-agent-summary-grid">
          <SummaryItem label="Runs" value={runs.length} />
          <SummaryItem label="Selected source URLs" value={totals.selected} />
          <SummaryItem label="Succeeded" value={totals.succeeded} />
          <SummaryItem label="Failed" value={totals.failed} />
          <SummaryItem label="Skipped" value={totals.skipped} />
        </dl>

        {notice ? <p className="form-warning">{notice}</p> : null}
        {isLoading ? <LoadingState label="Loading vendor source capture runs..." /> : null}
        {error ? <ErrorState message={error} onRetry={() => void loadRuns()} /> : null}
        {!isLoading && !error && runs.length === 0 ? (
          <EmptyState
            title="No vendor source capture runs"
            message="Launch a capture run to fetch current data from active source URLs."
          />
        ) : null}

        {!isLoading && !error && runs.length > 0 ? (
          <div className="table-wrap source-url-agent-runs-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>run_id</th>
                  <th>source_filter</th>
                  <th>observation_batch_id</th>
                  <th>status</th>
                  <th>selected_source_url_count</th>
                  <th>succeeded_count</th>
                  <th>failed_count</th>
                  <th>started_at</th>
                  <th>completed_at</th>
                  <th>actions/artifacts</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run, index) => {
                  const runId = getRunId(run);
                  const isRefreshing = refreshingRunId === runId;
                  return (
                    <tr key={`${runId}-${index}`}>
                      <td className="source-url-agent-run-id">{runId}</td>
                      <td>{formatValue(run.source_filter)}</td>
                      <td>{formatValue(run.observation_batch_id)}</td>
                      <td>
                        <span className={`status-badge ${statusClass(run.status)}`}>
                          {normalizeLabel(run.status)}
                        </span>
                      </td>
                      <td>{formatNumber(getCounter(run, "selected_source_url_count"))}</td>
                      <td>{formatNumber(getCounter(run, "succeeded_count"))}</td>
                      <td>{formatNumber(getCounter(run, "failed_count"))}</td>
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
              <h3>Capture run {artifactRunId}</h3>
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
          {isArtifactsLoading ? <LoadingState label="Loading capture run artifacts..." /> : null}
          {artifactError ? <p className="form-warning">{artifactError}</p> : null}
          {artifactResponse ? (
            <dl className="summary-grid">
              <div>
                <dt>observation_batch_id</dt>
                <dd>
                  {formatValue(
                    artifactResponse.observation_batch_id ??
                      runs.find((run) => getRunId(run) === artifactRunId)?.observation_batch_id,
                  )}
                </dd>
              </div>
            </dl>
          ) : null}
          {!isArtifactsLoading ? (
            <ArtifactList
              title={`Vendor source capture artifacts for ${artifactRunId}`}
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
