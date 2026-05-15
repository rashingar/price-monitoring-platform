import type { VendorSourceCapability } from "../../api/commerceTypes";
import { capabilityBadges } from "./sourceUrlAgentRunFormatters";

type SourceCapabilityStripProps = {
  sources: VendorSourceCapability[];
  isLoading: boolean;
  error: string | null;
};

export function SourceCapabilityStrip({ sources, isLoading, error }: SourceCapabilityStripProps) {
  return (
    <div className="source-capability-strip" aria-label="Vendor source capabilities">
      {isLoading ? <span className="muted">Loading sources...</span> : null}
      {!isLoading && error ? <span className="form-warning">{error}</span> : null}
      {!isLoading && sources.length > 0
        ? sources.map((source) => (
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
  );
}
