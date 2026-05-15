import type { CatalogReadinessBlock } from "../../api/catalogReadinessGate";

export function CatalogSetupHint() {
  return (
    <div className="setup-hint compact">
      <strong>Catalog setup check</strong>
      <ul>
        <li>Commerce API must be running: <code>ecommerce-api</code></li>
        <li>Database URL: <code>ECOMMERCE_DATABASE_URL</code></li>
        <li>Run migrations: <code>alembic upgrade head</code></li>
        <li>Import catalog input: <code>python -m ecommerce.jobs.ingest_catalog</code></li>
        <li>UI endpoint: <code>/commerce-api/catalog/summary</code></li>
        <li>Backend endpoint: <code>http://127.0.0.1:8001/api/catalog/summary</code></li>
      </ul>
    </div>
  );
}

export function CatalogReadinessBanner({
  block,
  onRetry,
}: {
  block: CatalogReadinessBlock;
  onRetry?: () => void;
}) {
  return (
    <div className="db-status-banner warning" role="alert">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Catalog</p>
          <h3>Catalog database/import required</h3>
        </div>
        {onRetry ? (
          <button className="button secondary" type="button" onClick={onRetry}>
            Retry Catalog
          </button>
        ) : null}
      </div>
      <p>{block.message}</p>
      <p className="muted">
        Catalog browsing reads from PostgreSQL after sourceCata.csv has been imported. This does not
        mean files, paths, artifacts, or general commerce health are unavailable when their endpoints
        are running.
      </p>
      {block.details.length > 0 ? (
        <ul className="db-status-hints">
          {block.details.map((detail) => (
            <li key={detail}>{detail}</li>
          ))}
        </ul>
      ) : null}
      <ul className="db-status-hints">
        {block.setupHints.map((hint) => (
          <li key={hint}>{hint}</li>
        ))}
      </ul>
    </div>
  );
}
