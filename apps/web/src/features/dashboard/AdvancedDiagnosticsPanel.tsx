import { LoadingState } from "../../components/layout/StateBlocks";
import type { PathRootsResponse } from "../../api/commerceTypes";
import type { ApiDiagnostics } from "../../api/diagnostics";

type AdvancedDiagnosticsPanelProps = {
  diagnostics: ApiDiagnostics | null;
  isDiagnosticsLoading: boolean;
  isOpen: boolean;
  onRefresh: () => void;
  onToggle: () => void;
  pathRoots: PathRootsResponse | null;
  pathRootsError: string | null;
};

function formatMissingKeys(keys: string[]): string {
  return keys.length > 0 ? keys.join(", ") : "-";
}

export function AdvancedDiagnosticsPanel({
  diagnostics,
  isDiagnosticsLoading,
  isOpen,
  onRefresh,
  onToggle,
  pathRoots,
  pathRootsError,
}: AdvancedDiagnosticsPanelProps) {
  return (
    <section className="panel" aria-labelledby="advanced-diagnostics-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Operations</p>
          <h3 id="advanced-diagnostics-heading">Advanced diagnostics</h3>
        </div>
        <button
          className="button secondary"
          type="button"
          aria-expanded={isOpen}
          aria-controls="advanced-diagnostics-content"
          onClick={onToggle}
        >
          {isOpen ? "Hide diagnostics" : "Show diagnostics"}
        </button>
      </div>

      {isOpen ? (
        <div id="advanced-diagnostics-content">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Local API diagnostics</p>
              <h4>Proxy and environment details</h4>
            </div>
            <button className="button secondary" type="button" onClick={onRefresh}>
              Refresh diagnostics
            </button>
          </div>

          {diagnostics ? (
            <>
              <dl className="summary-grid diagnostics-summary-grid">
                <div>
                  <dt>Product Factory base</dt>
                  <dd>{diagnostics.productFactoryBaseUrl}</dd>
                </div>
                <div>
                  <dt>Commerce base</dt>
                  <dd>{diagnostics.commerceBaseUrl}</dd>
                </div>
                <div>
                  <dt>/api proxy</dt>
                  <dd>{diagnostics.productFactoryProxyTarget}</dd>
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
                <strong>Environment readiness</strong>
                {pathRootsError ? <p className="form-error">{pathRootsError}</p> : null}
                {pathRoots?.env_readiness?.length ? (
                  <dl className="summary-grid diagnostics-summary-grid">
                    {pathRoots.env_readiness.map((group) => (
                      <div key={group.name}>
                        <dt>{group.name}</dt>
                        <dd>
                          {group.status === "configured"
                            ? "configured"
                            : `missing ${formatMissingKeys(group.missing_keys)}`}
                        </dd>
                      </div>
                    ))}
                  </dl>
                ) : null}
                {pathRoots?.local_env?.deprecated_app_env_detected ? (
                  <p className="muted">
                    Deprecated app-local .env detected. Move values to repo-root .env.
                  </p>
                ) : null}
                {pathRoots?.local_env?.warnings?.map((warning) => (
                  <p className="muted" key={warning}>
                    {warning}
                  </p>
                ))}

                <strong>Commerce setup checklist</strong>
                <ul>
                  <li>
                    Start commerce backend: <code>ecommerce-api</code>
                  </li>
                  <li>
                    Reinstall/update backend package: <code>python -m pip install -e .</code>
                  </li>
                  <li>
                    Configure Catalog database: <code>ECOMMERCE_DATABASE_URL</code>
                  </li>
                  <li>
                    Run Catalog migrations: <code>alembic upgrade head</code>
                  </li>
                  <li>
                    Import catalog input: <code>python -m ecommerce.jobs.ingest_catalog</code>
                  </li>
                  <li>
                    Run UI through Vite: <code>npm run dev</code>
                  </li>
                  <li>
                    Start local platform: <code>scripts\windows\start-all.cmd</code>
                  </li>
                  <li>
                    Terminal diagnostics: <code>scripts\windows\diagnose.cmd</code>
                  </li>
                  <li>
                    Confirm proxy target:{" "}
                    <code>VITE_COMMERCE_API_PROXY_TARGET=http://127.0.0.1:8001</code>
                  </li>
                </ul>
              </div>
            </>
          ) : null}

          {isDiagnosticsLoading ? <LoadingState label="Running diagnostics..." /> : null}
        </div>
      ) : null}
    </section>
  );
}
