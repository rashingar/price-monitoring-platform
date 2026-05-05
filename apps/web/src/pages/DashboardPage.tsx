import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, getApiErrorMessage } from "../api/client";
import { runApiDiagnostics } from "../api/diagnostics";
import type { ApiDiagnostics } from "../api/diagnostics";
import type { HealthResponse } from "../api/types";
import { ErrorState, LoadingState } from "../components/layout/StateBlocks";
import { JsonBlock } from "../components/jobs/JsonBlock";

function getHealthStatus(health: HealthResponse | null): string {
  if (!health) {
    return "unknown";
  }

  if (typeof health.status === "string") {
    return health.status;
  }

  if (typeof health.ok === "boolean") {
    return health.ok ? "ok" : "not ok";
  }

  return "unknown";
}

export function DashboardPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [diagnostics, setDiagnostics] = useState<ApiDiagnostics | null>(null);
  const [isDiagnosticsLoading, setIsDiagnosticsLoading] = useState(true);

  const loadHealth = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    try {
      const nextHealth = await apiClient.getHealth(signal);
      if (signal?.aborted) {
        return;
      }

      setHealth(nextHealth);
      setError(null);
    } catch (healthError) {
      if (!signal?.aborted) {
        setError(getApiErrorMessage(healthError));
      }
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
      }
    }
  }, []);

  const loadDiagnostics = useCallback(async () => {
    setIsDiagnosticsLoading(true);
    try {
      const nextDiagnostics = await runApiDiagnostics();
      setDiagnostics(nextDiagnostics);
    } finally {
      setIsDiagnosticsLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadHealth(controller.signal);
    return () => controller.abort();
  }, [loadHealth]);

  useEffect(() => {
    void loadDiagnostics();
  }, [loadDiagnostics]);

  return (
    <div className="page-stack">
      <section className="page-header">
        <p className="eyebrow">Dashboard</p>
        <h2>Local backend control surface</h2>
        <p>API base URL: {apiClient.apiBaseUrl}</p>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Backend health</p>
            <h3>{getHealthStatus(health)}</h3>
          </div>
          <button className="button secondary" type="button" onClick={() => void loadHealth()}>
            Refresh
          </button>
        </div>
        {isLoading ? <LoadingState label="Checking backend health..." /> : null}
        {error ? <ErrorState message={error} onRetry={() => void loadHealth()} /> : null}
        {!isLoading && !error ? <JsonBlock value={health} /> : null}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Operations</p>
            <h3>Local API diagnostics</h3>
          </div>
          <button
            className="button secondary"
            type="button"
            onClick={() => void loadDiagnostics()}
          >
            Refresh diagnostics
          </button>
        </div>

        {diagnostics ? (
          <>
            <dl className="summary-grid diagnostics-summary-grid">
              <div>
                <dt>Product-Agent base</dt>
                <dd>{diagnostics.productAgentBaseUrl}</dd>
              </div>
              <div>
                <dt>Commerce base</dt>
                <dd>{diagnostics.commerceBaseUrl}</dd>
              </div>
              <div>
                <dt>/api proxy</dt>
                <dd>{diagnostics.productAgentProxyTarget}</dd>
              </div>
              <div>
                <dt>/commerce-api proxy</dt>
                <dd>{diagnostics.commerceProxyTarget}</dd>
              </div>
            </dl>

            <div className="diagnostics-list">
              {diagnostics.results.map((result) => (
                <div className="diagnostic-card" key={`${result.service}-${result.requestUrl}`}>
                  <div className="diagnostic-heading">
                    <strong>{result.service}</strong>
                    <span className={`status-badge ${result.status}`}>{result.status}</span>
                  </div>
                  <p>
                    <span className="muted">Browser request:</span> {result.requestUrl}
                  </p>
                  <p>
                    <span className="muted">Result:</span>{" "}
                    {result.httpStatus ? `HTTP ${result.httpStatus}. ` : ""}
                    {result.message}
                  </p>
                  {result.rawError ? (
                    <p>
                      <span className="muted">Raw error:</span> {result.rawError}
                    </p>
                  ) : null}
                  <p>
                    <span className="muted">Suggested fix:</span> {result.suggestedFix}
                  </p>
                </div>
              ))}
            </div>

            <div className="setup-hint">
              <strong>Commerce setup checklist</strong>
              <ul>
                <li>Start commerce backend: <code>pricefetcher-api</code></li>
                <li>Reinstall/update backend package: <code>python -m pip install -e .</code></li>
                <li>Configure Catalog database: <code>PRICEFETCHER_DATABASE_URL</code></li>
                <li>Run Catalog migrations: <code>alembic upgrade head</code></li>
                <li>Import catalog input: <code>python -m pricefetcher.jobs.ingest_catalog</code></li>
                <li>Run UI through Vite: <code>npm run dev</code></li>
                <li>Start local platform: <code>scripts\windows\start-all.cmd</code></li>
                <li>Terminal diagnostics: <code>scripts\windows\diagnose.cmd</code></li>
                <li>Confirm proxy target: <code>VITE_COMMERCE_API_PROXY_TARGET=http://127.0.0.1:8001</code></li>
              </ul>
            </div>
          </>
        ) : null}

        {isDiagnosticsLoading ? <LoadingState label="Running diagnostics..." /> : null}
      </section>

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
