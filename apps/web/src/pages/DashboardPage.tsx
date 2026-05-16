import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../api/client";
import { commerceClient, getCommerceApiErrorMessage } from "../api/commerceClient";
import { runApiDiagnostics } from "../api/diagnostics";
import { getJobProgress } from "../api/jobProgress";
import type {
  CatalogUpdateJob,
  PathRootsResponse,
  StockSyncLatestResponse,
  StockSyncMode,
  StockSyncReadinessResponse,
} from "../api/commerceTypes";
import type { ApiDiagnostics } from "../api/diagnostics";
import { JobProgressPanel } from "../components/jobs/JobProgressPanel";
import { AdvancedDiagnosticsPanel } from "../features/dashboard/AdvancedDiagnosticsPanel";
import { PlatformHealthPanel } from "../features/platform-health/PlatformHealthPanel";

const CATALOG_UPDATE_POLL_MS = 500;
const ADVANCED_DIAGNOSTICS_STORAGE_KEY =
  "price-monitoring-platform:dashboard:advanced-diagnostics-open:v1";

function isCatalogUpdateActive(job: CatalogUpdateJob | null): boolean {
  const status = job?.status?.toLowerCase();
  return status === "queued" || status === "running";
}

function getCatalogUpdateBadge(job: CatalogUpdateJob | null) {
  const status = job?.status?.toLowerCase();
  if (status === "succeeded") {
    return { label: "Succeeded", className: "success" };
  }
  if (status === "failed") {
    return { label: "Failed", className: "danger" };
  }
  if (status === "cancelled" || status === "canceled") {
    return { label: "Cancelled", className: "warning" };
  }
  if (status === "queued" || status === "running") {
    return { label: "Updating", className: "neutral" };
  }
  return { label: "Idle", className: "neutral" };
}

function getCatalogUpdateImportedCount(job: CatalogUpdateJob | null): number | null {
  const ingest = job?.result?.ingest;
  if (typeof ingest === "object" && ingest !== null && "imported" in ingest) {
    const imported = (ingest as Record<string, unknown>).imported;
    return typeof imported === "number" ? imported : null;
  }
  return null;
}

function getStockSyncBadge(latest: StockSyncLatestResponse | null) {
  if (!latest?.available) {
    return { label: "No review", className: "neutral" };
  }
  if (latest.hard_failures.length > 0) {
    return { label: latest.status ?? "Blocked", className: "danger" };
  }
  if (latest.ok_to_upload === true) {
    return { label: latest.status ?? "Ready", className: "success" };
  }
  if (latest.warnings.length > 0) {
    return { label: latest.status ?? "Warnings", className: "warning" };
  }
  return { label: latest.status ?? "Reviewed", className: "neutral" };
}

function getStockSyncCount(
  latest: StockSyncLatestResponse | null,
  keys: string[],
): number | null {
  const counts = latest?.counts;
  if (!counts) {
    return null;
  }

  for (const key of keys) {
    const value = counts[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === "string" && value.trim().length > 0) {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }
  return null;
}

function formatStockSyncValue(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? "-" : String(value);
}

export function DashboardPage() {
  const [diagnostics, setDiagnostics] = useState<ApiDiagnostics | null>(null);
  const [isDiagnosticsLoading, setIsDiagnosticsLoading] = useState(true);
  const [catalogUpdateJob, setCatalogUpdateJob] = useState<CatalogUpdateJob | null>(null);
  const [catalogUpdateError, setCatalogUpdateError] = useState<string | null>(null);
  const [isCatalogUpdateStarting, setIsCatalogUpdateStarting] = useState(false);
  const [pathRoots, setPathRoots] = useState<PathRootsResponse | null>(null);
  const [pathRootsError, setPathRootsError] = useState<string | null>(null);
  const [stockSyncReadiness, setStockSyncReadiness] = useState<StockSyncReadinessResponse | null>(null);
  const [stockSyncLatest, setStockSyncLatest] = useState<StockSyncLatestResponse | null>(null);
  const [stockSyncError, setStockSyncError] = useState<string | null>(null);
  const [stockSyncMessage, setStockSyncMessage] = useState<string | null>(null);
  const [stockSyncTriggerMode, setStockSyncTriggerMode] = useState<StockSyncMode | null>(null);
  const [isStockSyncImportConfirmOpen, setIsStockSyncImportConfirmOpen] = useState(false);
  const [stockSyncImportConfirmation, setStockSyncImportConfirmation] = useState("");
  const [isAdvancedDiagnosticsOpen, setIsAdvancedDiagnosticsOpen] = useState(() => {
    return window.localStorage.getItem(ADVANCED_DIAGNOSTICS_STORAGE_KEY) === "true";
  });

  const loadDiagnostics = useCallback(async () => {
    setIsDiagnosticsLoading(true);
    try {
      const nextDiagnostics = await runApiDiagnostics();
      setDiagnostics(nextDiagnostics);
    } finally {
      setIsDiagnosticsLoading(false);
    }
  }, []);

  const loadLatestCatalogUpdate = useCallback(async (signal?: AbortSignal) => {
    try {
      const latest = await commerceClient.getLatestCatalogUpdate(signal);
      if (signal?.aborted) {
        return;
      }
      setCatalogUpdateJob(latest);
      setCatalogUpdateError(null);
    } catch (updateError) {
      if (!signal?.aborted) {
        setCatalogUpdateError(getCommerceApiErrorMessage(updateError));
      }
    }
  }, []);

  const loadPathRoots = useCallback(async (signal?: AbortSignal) => {
    try {
      const roots = await commerceClient.getPathRoots(signal);
      if (signal?.aborted) {
        return;
      }
      setPathRoots(roots);
      setPathRootsError(null);
    } catch (rootsError) {
      if (!signal?.aborted) {
        setPathRoots(null);
        setPathRootsError(getCommerceApiErrorMessage(rootsError));
      }
    }
  }, []);

  const loadStockSync = useCallback(async (signal?: AbortSignal) => {
    try {
      const [readiness, latest] = await Promise.all([
        commerceClient.getStockSyncReadiness(signal),
        commerceClient.getLatestStockSync(signal),
      ]);
      if (signal?.aborted) {
        return;
      }
      setStockSyncReadiness(readiness);
      setStockSyncLatest(latest);
      setStockSyncError(null);
    } catch (stockSyncLoadError) {
      if (!signal?.aborted) {
        setStockSyncError(getCommerceApiErrorMessage(stockSyncLoadError));
      }
    }
  }, []);

  const pollCatalogUpdateJob = useCallback(async (jobId: string, signal?: AbortSignal) => {
    try {
      const nextJob = await commerceClient.getCatalogUpdateJob(jobId, signal);
      if (signal?.aborted) {
        return;
      }
      setCatalogUpdateJob(nextJob);
      setCatalogUpdateError(null);
    } catch (updateError) {
      if (!signal?.aborted) {
        setCatalogUpdateError(getCommerceApiErrorMessage(updateError));
      }
    }
  }, []);

  const startCatalogUpdate = useCallback(async () => {
    setIsCatalogUpdateStarting(true);
    setCatalogUpdateError(null);
    try {
      const job = await commerceClient.startCatalogUpdate();
      setCatalogUpdateJob(job);
      if (isCatalogUpdateActive(job)) {
        void pollCatalogUpdateJob(job.job_id);
      }
    } catch (updateError) {
      setCatalogUpdateError(getCommerceApiErrorMessage(updateError));
    } finally {
      setIsCatalogUpdateStarting(false);
    }
  }, [pollCatalogUpdateJob]);

  const triggerStockSyncRun = useCallback(
    async (mode: StockSyncMode, confirmation?: string) => {
      setStockSyncTriggerMode(mode);
      setStockSyncError(null);
      setStockSyncMessage(null);
      try {
        const result = await commerceClient.triggerStockSyncRun({ mode, confirmation });
        setStockSyncMessage(result.message || "Scheduled task triggered. Check email for the final report.");
        if (mode === "import") {
          setIsStockSyncImportConfirmOpen(false);
          setStockSyncImportConfirmation("");
        }
        await loadStockSync();
      } catch (stockSyncRunError) {
        setStockSyncError(getCommerceApiErrorMessage(stockSyncRunError));
      } finally {
        setStockSyncTriggerMode(null);
      }
    },
    [loadStockSync],
  );

  useEffect(() => {
    void loadDiagnostics();
  }, [loadDiagnostics]);

  useEffect(() => {
    const controller = new AbortController();
    void loadLatestCatalogUpdate(controller.signal);
    return () => controller.abort();
  }, [loadLatestCatalogUpdate]);

  useEffect(() => {
    const controller = new AbortController();
    void loadPathRoots(controller.signal);
    return () => controller.abort();
  }, [loadPathRoots]);

  useEffect(() => {
    const controller = new AbortController();
    void loadStockSync(controller.signal);
    return () => controller.abort();
  }, [loadStockSync]);

  useEffect(() => {
    if (!isCatalogUpdateActive(catalogUpdateJob)) {
      return;
    }

    const jobId = catalogUpdateJob?.job_id;
    if (!jobId) {
      return;
    }

    const controller = new AbortController();
    const intervalId = window.setInterval(() => {
      void pollCatalogUpdateJob(jobId, controller.signal);
    }, CATALOG_UPDATE_POLL_MS);
    return () => {
      controller.abort();
      window.clearInterval(intervalId);
    };
  }, [catalogUpdateJob, pollCatalogUpdateJob]);

  const toggleAdvancedDiagnostics = useCallback(() => {
    setIsAdvancedDiagnosticsOpen((current) => {
      const next = !current;
      window.localStorage.setItem(ADVANCED_DIAGNOSTICS_STORAGE_KEY, String(next));
      return next;
    });
  }, []);

  const catalogUpdateBadge = getCatalogUpdateBadge(catalogUpdateJob);
  const catalogUpdateActive = isCatalogUpdateActive(catalogUpdateJob);
  const importedCount = getCatalogUpdateImportedCount(catalogUpdateJob);
  const catalogUpdateProgress = getJobProgress(catalogUpdateJob);
  const stockSyncBadge = getStockSyncBadge(stockSyncLatest);
  const stockSyncTriggerInFlight = stockSyncTriggerMode !== null;
  const stockSyncConfigReady = stockSyncReadiness?.enabled === true && stockSyncReadiness.schtasks_available === true;
  const stockSyncButtonsDisabled = stockSyncTriggerInFlight || !stockSyncConfigReady;
  const stockSyncOutputRows = getStockSyncCount(stockSyncLatest, [
    "output_rows",
    "output_row_count",
    "rows",
    "row_count",
  ]);
  const stockSyncDisabledCount = getStockSyncCount(stockSyncLatest, [
    "disabled_count",
    "disabled_rows",
  ]);
  const stockSyncPriceZeroForcedDisabledCount = getStockSyncCount(stockSyncLatest, [
    "price_zero_forced_disabled_count",
    "price_zero_disabled_count",
    "forced_disabled_price_zero_count",
  ]);
  const stockSyncWarningCount =
    getStockSyncCount(stockSyncLatest, ["warning_count", "warnings_count"]) ??
    stockSyncLatest?.warnings.length ??
    null;

  return (
    <div className="page-stack">
      <section className="page-header">
        <p className="eyebrow">Dashboard</p>
        <h2>Local backend control surface</h2>
        <p>API base URL: {apiClient.apiBaseUrl}</p>
      </section>

      <PlatformHealthPanel />

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Catalog</p>
            <h3>OpenCart DB update</h3>
          </div>
          <div className="section-heading-actions">
            <span className={`status-badge ${catalogUpdateBadge.className}`}>
              {catalogUpdateBadge.label}
            </span>
            <button
              className="button primary"
              type="button"
              disabled={isCatalogUpdateStarting || catalogUpdateActive}
              onClick={() => void startCatalogUpdate()}
            >
              Update DB
            </button>
          </div>
        </div>

        {catalogUpdateJob ? (
          <>
            <dl className="summary-grid diagnostics-summary-grid">
              <div>
                <dt>Job</dt>
                <dd>{catalogUpdateJob.job_id}</dd>
              </div>
              <div>
                <dt>Type</dt>
                <dd>{catalogUpdateJob.job_type}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{catalogUpdateJob.status}</dd>
              </div>
              <div>
                <dt>Imported</dt>
                <dd>{importedCount ?? "-"}</dd>
              </div>
            </dl>
            <JobProgressPanel progress={catalogUpdateProgress} compact />
          </>
        ) : (
          <p className="muted">No catalog update job has been recorded yet.</p>
        )}

        {catalogUpdateError ? <p className="form-error">{catalogUpdateError}</p> : null}
        {catalogUpdateJob?.status?.toLowerCase() === "failed" && catalogUpdateJob.error_message ? (
          <p className="form-error">{catalogUpdateJob.error_message}</p>
        ) : null}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Catalog</p>
            <h3>OpenCart Stock Sync</h3>
          </div>
          <div className="section-heading-actions">
            <span className={`status-badge ${stockSyncBadge.className}`}>
              {stockSyncBadge.label}
            </span>
            <button
              className="button"
              type="button"
              disabled={stockSyncButtonsDisabled}
              onClick={() => void triggerStockSyncRun("review")}
            >
              {stockSyncTriggerMode === "review" ? "Triggering..." : "Run Review Only"}
            </button>
            <button
              className="button"
              type="button"
              disabled={stockSyncButtonsDisabled}
              onClick={() => void triggerStockSyncRun("dry_run")}
            >
              {stockSyncTriggerMode === "dry_run" ? "Triggering..." : "Run Dry-run Import"}
            </button>
            <button
              className="button danger"
              type="button"
              disabled={stockSyncButtonsDisabled}
              onClick={() => {
                setStockSyncError(null);
                setStockSyncMessage(null);
                setIsStockSyncImportConfirmOpen(true);
              }}
            >
              Run Real Import
            </button>
          </div>
        </div>

        {stockSyncLatest?.available ? (
          <dl className="summary-grid diagnostics-summary-grid">
            <div>
              <dt>Status</dt>
              <dd>{formatStockSyncValue(stockSyncLatest.status)}</dd>
            </div>
            <div>
              <dt>Run id</dt>
              <dd>{formatStockSyncValue(stockSyncLatest.run_id)}</dd>
            </div>
            <div>
              <dt>Output rows</dt>
              <dd>{formatStockSyncValue(stockSyncOutputRows)}</dd>
            </div>
            <div>
              <dt>Disabled</dt>
              <dd>{formatStockSyncValue(stockSyncDisabledCount)}</dd>
            </div>
            <div>
              <dt>Price-zero disabled</dt>
              <dd>{formatStockSyncValue(stockSyncPriceZeroForcedDisabledCount)}</dd>
            </div>
            <div>
              <dt>Warnings</dt>
              <dd>{formatStockSyncValue(stockSyncWarningCount)}</dd>
            </div>
          </dl>
        ) : (
          <p className="muted">
            {stockSyncLatest?.message ?? "Latest stock sync status has not been loaded yet."}
          </p>
        )}

        {stockSyncReadiness && !stockSyncReadiness.enabled ? (
          <p className="form-error">
            OpenCart Stock Sync API is disabled. Set ECOMMERCE_STOCK_SYNC_ENABLED=true to enable it.
          </p>
        ) : null}
        {stockSyncReadiness && !stockSyncReadiness.schtasks_available ? (
          <p className="form-error">schtasks is not available on this machine.</p>
        ) : null}
        {stockSyncReadiness?.latest_review_error ? (
          <p className="form-error">{stockSyncReadiness.latest_review_error}</p>
        ) : null}
        {stockSyncMessage ? <p className="muted">{stockSyncMessage}</p> : null}
        {stockSyncError ? <p className="form-error">{stockSyncError}</p> : null}

        {isStockSyncImportConfirmOpen ? (
          <div className="inline-field">
            <label htmlFor="stock-sync-import-confirmation">Confirm real import</label>
            <input
              id="stock-sync-import-confirmation"
              value={stockSyncImportConfirmation}
              onChange={(event) => setStockSyncImportConfirmation(event.target.value)}
              placeholder="RUN IMPORT"
              disabled={stockSyncTriggerInFlight}
            />
            <button
              className="button danger"
              type="button"
              disabled={
                stockSyncTriggerInFlight ||
                !stockSyncConfigReady ||
                stockSyncImportConfirmation !== "RUN IMPORT"
              }
              onClick={() => void triggerStockSyncRun("import", stockSyncImportConfirmation)}
            >
              {stockSyncTriggerMode === "import" ? "Triggering..." : "Confirm Real Import"}
            </button>
            <button
              className="button"
              type="button"
              disabled={stockSyncTriggerInFlight}
              onClick={() => {
                setIsStockSyncImportConfirmOpen(false);
                setStockSyncImportConfirmation("");
              }}
            >
              Cancel
            </button>
          </div>
        ) : null}
      </section>

      <AdvancedDiagnosticsPanel
        diagnostics={diagnostics}
        isDiagnosticsLoading={isDiagnosticsLoading}
        isOpen={isAdvancedDiagnosticsOpen}
        onRefresh={() => {
          void loadDiagnostics();
          void loadPathRoots();
        }}
        onToggle={toggleAdvancedDiagnostics}
        pathRoots={pathRoots}
        pathRootsError={pathRootsError}
      />

      <section className="quick-links" aria-label="Quick links">
        <Link className="quick-link" to="/prepare">
          <strong>Prepare</strong>
          <span>Create a prepare job</span>
        </Link>
        <Link className="quick-link" to="/render">
          <strong>Render</strong>
          <span>Create a render job</span>
        </Link>
        <Link className="quick-link" to="/publish">
          <strong>Publish</strong>
          <span>Create a publish job</span>
        </Link>
        <Link className="quick-link" to="/jobs">
          <strong>Jobs</strong>
          <span>Review recent jobs</span>
        </Link>
      </section>
    </div>
  );
}
