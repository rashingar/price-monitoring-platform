import type { FormEvent } from "react";
import type { SourceUrlAgentRunRequest, VendorSourceCapability } from "../../api/commerceTypes";
import { LoadingState } from "../../components/layout/StateBlocks";
import { DEFAULT_RUN_REQUEST } from "./sourceUrlAgentRunConstants";
import { SourceCapabilityStrip } from "./SourceCapabilityStrip";

type SourceUrlAgentLaunchPanelProps = {
  form: SourceUrlAgentRunRequest;
  discoverySourceOptions: VendorSourceCapability[];
  isSourcesLoading: boolean;
  sourceError: string | null;
  isLaunching: boolean;
  isLaunchDisabled: boolean;
  launchBlockReason: string | null;
  updateForm: <Key extends keyof SourceUrlAgentRunRequest>(
    key: Key,
    value: SourceUrlAgentRunRequest[Key],
  ) => void;
  onResetDefaults: () => void;
  onLaunch: () => void;
};

export function SourceUrlAgentLaunchPanel({
  form,
  discoverySourceOptions,
  isSourcesLoading,
  sourceError,
  isLaunching,
  isLaunchDisabled,
  launchBlockReason,
  updateForm,
  onResetDefaults,
  onLaunch,
}: SourceUrlAgentLaunchPanelProps) {
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onLaunch();
  };

  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Launch</p>
          <h3>Bounded dry-run from DB catalog</h3>
        </div>
        <button
          className="button secondary"
          type="button"
          onClick={onResetDefaults}
          disabled={isLaunching}
        >
          Reset defaults
        </button>
      </div>

      <form className="form" onSubmit={handleSubmit}>
        <div className="filter-grid source-url-agent-form-grid">
          <label>
            Mode
            <select
              value={String(form.mode)}
              onChange={(event) => updateForm("mode", event.target.value)}
            >
              <option value={DEFAULT_RUN_REQUEST.mode}>catalog</option>
            </select>
          </label>
          <label title="Vendor source_name filter. Direct vendors appear when the backend reports discovery_enabled=true.">
            Source filter
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
              onChange={(event) => updateForm("rate_limit_seconds", Number(event.target.value) || 0)}
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

        <SourceCapabilityStrip
          sources={discoverySourceOptions}
          isLoading={isSourcesLoading}
          error={sourceError}
        />

        {form.apply_high_confidence ? (
          <p className="form-warning">Apply-high-confidence writes DB rows for accepted matches.</p>
        ) : null}
        {!form.dry_run ? (
          <p className="form-warning">This is not a dry-run. Verify a 5-product dry-run first.</p>
        ) : null}
        {isLaunching ? (
          <LoadingState label="Running browser-based Find Source discovery. This can take several minutes for multi-model selections..." />
        ) : null}

        <div className="button-row">
          <button className="button primary" type="submit" disabled={isLaunchDisabled}>
            {isLaunching ? "Launching..." : "Launch run"}
          </button>
        </div>
        {launchBlockReason ? <p className="form-warning">{launchBlockReason}</p> : null}
      </form>
    </section>
  );
}
