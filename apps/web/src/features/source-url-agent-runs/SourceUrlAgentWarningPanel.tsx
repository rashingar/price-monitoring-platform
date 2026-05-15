export function SourceUrlAgentWarningPanel() {
  return (
    <section className="panel source-url-agent-warning-panel" aria-label="Find Source warnings">
      <ul className="source-url-warning-list">
        <li>Dry-run does not activate URLs.</li>
        <li>Apply-high-confidence writes DB rows.</li>
        <li>Do not run full catalog until a 5-product dry-run is verified.</li>
      </ul>
    </section>
  );
}
