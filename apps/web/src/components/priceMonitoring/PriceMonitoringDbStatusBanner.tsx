import type { PriceMonitoringDbStatus } from "../../api/commerceTypes";
import {
  getPriceMonitoringDbWarnings,
  isPriceMonitoringDbReady,
  PRICE_MONITORING_DB_REQUIRED_MESSAGE,
} from "../../api/priceMonitoringDbGate";

interface PriceMonitoringDbStatusBannerProps {
  status: PriceMonitoringDbStatus | null;
  error: string | null;
  isLoading?: boolean;
  onRetry?: () => void;
}

export function isPriceMonitoringDbAvailable(status: PriceMonitoringDbStatus | null): boolean {
  return isPriceMonitoringDbReady(status);
}

function getStatusTone(status: PriceMonitoringDbStatus | null, error: string | null): string {
  if (error) {
    return "danger";
  }

  if (!status) {
    return "warning";
  }

  return isPriceMonitoringDbAvailable(status) ? "ok" : "warning";
}

function getStatusLabel(status: PriceMonitoringDbStatus | null, error: string | null): string {
  if (error) {
    return "Database status failed";
  }

  if (!status) {
    return "Database status unknown";
  }

  return isPriceMonitoringDbAvailable(status) ? "Database ready" : "Database not ready";
}

function getSetupHints(status: PriceMonitoringDbStatus | null): string[] {
  if (!status) {
    return [];
  }

  const hints = new Set<string>(status.setup_hints ?? []);

  if (!status.configured) {
    hints.add("Set PRICEFETCHER_DATABASE_URL.");
    hints.add("Run alembic upgrade head from the price-fetcher backend repo.");
    hints.add("Restart pricefetcher-api.");
  }

  if (status.configured && !status.reachable) {
    hints.add("Check the PostgreSQL service, database URL, user credentials, and network reachability.");
  }

  if (status.required_tables_present === false || status.alembic_up_to_date === false) {
    hints.add("Run alembic upgrade head.");
  }

  return Array.from(hints);
}

export function PriceMonitoringDbStatusBanner({
  status,
  error,
  isLoading = false,
  onRetry,
}: PriceMonitoringDbStatusBannerProps) {
  const tone = getStatusTone(status, error);
  const hints = getSetupHints(status);
  const warnings = getPriceMonitoringDbWarnings(status);

  return (
    <div className={`db-status-banner ${tone}`}>
      <div className="section-heading">
        <div>
          <p className="eyebrow">Database</p>
          <h3>Price Monitoring database</h3>
        </div>
        {onRetry ? (
          <button className="button secondary" type="button" disabled={isLoading} onClick={onRetry}>
            {isLoading ? "Checking..." : "Retry DB status"}
          </button>
        ) : null}
      </div>

      <div className="button-row">
        <span className={`status-badge ${tone}`}>{getStatusLabel(status, error)}</span>
        {status ? (
          <>
            <span className={`status-badge ${status.configured ? "ok" : "warning"}`}>
              {status.configured ? "Configured" : "Not configured"}
            </span>
            <span className={`status-badge ${status.reachable ? "ok" : "warning"}`}>
              {status.reachable ? "Reachable" : "Not reachable"}
            </span>
            {status.required_tables_present === false ? (
              <span className="status-badge danger">Tables missing</span>
            ) : null}
            {status.alembic_up_to_date === false ? (
              <span className="status-badge warning">Migration needed</span>
            ) : null}
            {status.dialect ? <span className="status-badge neutral">{status.dialect}</span> : null}
          </>
        ) : null}
      </div>

      {error ? <p className="form-error">{error}</p> : null}
      {!error && !isPriceMonitoringDbAvailable(status) ? (
        <div className="form-warning">
          <p>{PRICE_MONITORING_DB_REQUIRED_MESSAGE}</p>
          {warnings.length > 0 ? (
            <ul>
              {warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {status?.error ? <p className="muted">{status.error}</p> : null}
      {status?.alembic_current_revision || status?.alembic_head_revision ? (
        <p className="muted">
          Revision {status.alembic_current_revision ?? "-"} / head {status.alembic_head_revision ?? "-"}
        </p>
      ) : null}
      {hints.length > 0 ? (
        <ul className="db-status-hints">
          {hints.map((hint) => (
            <li key={hint}>{hint}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
