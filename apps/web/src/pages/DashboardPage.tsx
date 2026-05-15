import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../api/client";
import { commerceClient, getCommerceApiErrorMessage } from "../api/commerceClient";
import { runApiDiagnostics } from "../api/diagnostics";
import { getJobProgress } from "../api/jobProgress";
import type { CatalogUpdateJob, PathRootsResponse } from "../api/commerceTypes";
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

export function DashboardPage() {
  const [diagnostics, setDiagnostics] = useState<ApiDiagnostics | null>(null);
  const [isDiagnosticsLoading, setIsDiagnosticsLoading] = useState(true);
  const [catalogUpdateJob, setCatalogUpdateJob] = useState<CatalogUpdateJob | null>(null);
  const [catalogUpdateError, setCatalogUpdateError] = useState<string | null>(null);
  const [isCatalogUpdateStarting, setIsCatalogUpdateStarting] = useState(false);
  const [pathRoots, setPathRoots] = useState<PathRootsResponse | null>(null);
  const [pathRootsError, setPathRootsError] = useState<string | null>(null);
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
