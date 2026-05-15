import { useEffect } from "react";
import type { SourceUrlAgentReadiness } from "../../api/commerceTypes";
import {
  providerConfiguredLabel,
  providerConfiguredStatusClass,
  providerEnabledLabel,
  readinessStatusClass,
  readinessStatusLabel,
} from "./sourceUrlAgentReadinessHelpers";
import { useSourceUrlAgentReadiness } from "./useSourceUrlAgentReadiness";

interface SourceUrlAgentReadinessCardProps {
  compact?: boolean;
  blockLaunch?: boolean;
  showLaunchImpact?: boolean;
  className?: string;
  onReadinessStateChange?: (state: {
    readiness: SourceUrlAgentReadiness | null;
    isLoading: boolean;
    error: string | null;
  }) => void;
}

export function SourceUrlAgentReadinessCard({
  compact = false,
  blockLaunch = false,
  showLaunchImpact = blockLaunch,
  className = "",
  onReadinessStateChange,
}: SourceUrlAgentReadinessCardProps) {
  const { readiness, isLoading, error, refreshReadiness } = useSourceUrlAgentReadiness();
  const status = readiness?.status ?? "blocked";
  const statusLabel = readiness ? readinessStatusLabel(status) : isLoading ? "Checking" : "Blocked";
  const classNames = [
    "panel",
    "source-url-readiness-card",
    compact ? "compact" : "",
    `source-url-readiness-card-${readinessStatusClass(status)}`,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  useEffect(() => {
    onReadinessStateChange?.({ readiness, isLoading, error });
  }, [error, isLoading, onReadinessStateChange, readiness]);

  return (
    <section className={classNames} aria-label="Source URL Agent provider readiness">
      <div className="section-heading source-url-readiness-heading">
        <div>
          <p className="eyebrow">Provider readiness</p>
          <h3>Search provider status</h3>
        </div>
        <div className="source-url-readiness-actions">
          <span className={`status-badge ${readiness ? readinessStatusClass(status) : "neutral"}`}>
            {statusLabel}
          </span>
          <button
            className="button secondary compact-button"
            type="button"
            onClick={refreshReadiness}
            disabled={isLoading}
          >
            {isLoading ? "Refreshing..." : "Refresh readiness"}
          </button>
        </div>
      </div>

      {isLoading ? <p className="muted">Checking configured Source URL Agent providers...</p> : null}
      {error ? <p className="form-warning">Readiness check failed: {error}</p> : null}

      {!isLoading && !error && readiness ? (
        <>
          {showLaunchImpact ? (
            <p className="muted">
              {status === "blocked"
                ? "Launch is blocked until a configured provider is available."
                : status === "warning"
                  ? "Launch is available, but review the provider warning before broad runs."
                  : "Launch is available for configured Source URL Agent providers."}
            </p>
          ) : (
            <p className="muted">
              Provider readiness can explain why new Find Source candidates are not appearing.
            </p>
          )}

          <div className="source-url-readiness-meta">
            <span>Default provider order</span>
            <strong>
              {readiness.default_provider_order.length > 0
                ? readiness.default_provider_order.join(" -> ")
                : "-"}
            </strong>
          </div>

          <div className="source-url-readiness-provider-grid">
            {readiness.providers.map((provider) => (
              <article className="source-url-readiness-provider" key={provider.provider_name}>
                <div className="source-url-readiness-provider-header">
                  <div>
                    <strong>{provider.provider_name}</strong>
                    <span className="muted">{provider.provider_type}</span>
                  </div>
                  <span className={`status-badge ${providerConfiguredStatusClass(provider)}`}>
                    {providerConfiguredLabel(provider)}
                  </span>
                </div>
                <dl className="source-url-readiness-provider-details">
                  <div>
                    <dt>Enabled</dt>
                    <dd>{providerEnabledLabel(provider.enabled)}</dd>
                  </div>
                  <div>
                    <dt>Configured</dt>
                    <dd>{provider.configured ? "Yes" : "No"}</dd>
                  </div>
                  {!compact ? (
                    <div>
                      <dt>Auto-apply</dt>
                      <dd>{provider.allow_high_confidence_auto_apply ? "Allowed" : "Off"}</dd>
                    </div>
                  ) : null}
                </dl>
                {provider.missing_env_keys.length > 0 ? (
                  <p className="source-url-readiness-missing">
                    Missing configuration: {provider.missing_env_keys.join(", ")}
                  </p>
                ) : null}
                {!compact && provider.required_env_keys.length > 0 ? (
                  <p className="muted">Required keys: {provider.required_env_keys.join(", ")}</p>
                ) : null}
                {!compact && provider.notes ? <p className="muted">{provider.notes}</p> : null}
              </article>
            ))}
          </div>

          {readiness.warnings.length > 0 ? (
            <div className="source-url-readiness-message-list">
              <strong>Warnings</strong>
              <ul>
                {readiness.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {readiness.blocking_reasons.length > 0 ? (
            <div className="source-url-readiness-message-list danger">
              <strong>Blocking reasons</strong>
              <ul>
                {readiness.blocking_reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
