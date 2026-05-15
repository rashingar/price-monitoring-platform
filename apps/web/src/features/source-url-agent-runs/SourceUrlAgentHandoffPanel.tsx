type SourceUrlAgentHandoffPanelProps = {
  handoffModels: string[];
  isLaunching: boolean;
  onClear: () => void;
};

export function SourceUrlAgentHandoffPanel({
  handoffModels,
  isLaunching,
  onClear,
}: SourceUrlAgentHandoffPanelProps) {
  if (handoffModels.length === 0) {
    return null;
  }

  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Catalog handoff</p>
          <h3>
            {handoffModels.length.toLocaleString()} selected{" "}
            {handoffModels.length === 1 ? "model" : "models"}
          </h3>
        </div>
        <button className="button secondary" type="button" onClick={onClear} disabled={isLaunching}>
          Clear handoff
        </button>
      </div>
      <p className="muted">
        Discovery is scoped to the selected Catalog models and existing missing-only defaults.
      </p>
      <p className="muted">{handoffModels.slice(0, 40).join(", ")}</p>
      {handoffModels.length > 40 ? (
        <p className="muted">Showing 40 of {handoffModels.length.toLocaleString()} selected models.</p>
      ) : null}
    </section>
  );
}
