import { ErrorState, LoadingState } from "../../components/layout/StateBlocks";
import {
  platformHealthStatusClass,
  platformHealthStatusLabel,
  platformHealthUpdatedAtLabel,
} from "./platformHealthFormatters";
import { PlatformHealthGroupCard } from "./PlatformHealthGroupCard";
import { usePlatformHealth } from "./usePlatformHealth";

export function PlatformHealthPanel() {
  const { health, isLoading, error, refreshHealth } = usePlatformHealth();
  const status = health?.status ?? "unknown";

  return (
    <section className="panel platform-health-panel" aria-label="Platform health">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Platform health</p>
          <h3>Operator readiness</h3>
        </div>
        <div className="section-heading-actions">
          <span className={`status-badge ${platformHealthStatusClass(status)}`}>
            {platformHealthStatusLabel(status)}
          </span>
          <button
            className="button secondary"
            type="button"
            onClick={refreshHealth}
            disabled={isLoading}
          >
            {isLoading ? "Refreshing..." : "Refresh platform health"}
          </button>
        </div>
      </div>

      <p className="muted">
        Last checked: {platformHealthUpdatedAtLabel(health?.updated_at ?? null)}
      </p>

      {isLoading ? <LoadingState label="Checking platform health..." /> : null}
      {error ? <ErrorState message={error} onRetry={refreshHealth} /> : null}

      {!isLoading && !error && health ? (
        <div className="platform-health-grid">
          {health.groups.map((group) => (
            <PlatformHealthGroupCard key={group.id} group={group} />
          ))}
        </div>
      ) : null}
    </section>
  );
}
