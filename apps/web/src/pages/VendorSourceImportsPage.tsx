import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { commerceClient, getCommerceApiErrorMessage } from "../api/commerceClient";
import type {
  ProductFactoryHandoffImportRequest,
  SourceUrlImportResponse,
} from "../api/commerceTypes";
import { ErrorState } from "../components/layout/StateBlocks";

const DEFAULT_HANDOFF_PATH = "work/{model}/integrations/ecommerce_source_handoff.json";

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return String(value);
}

function formatNumber(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString() : "-";
}

function statusClass(status: string | null | undefined): string {
  switch (status) {
    case "active":
    case "success":
    case "succeeded":
      return "success";
    case "needs_review":
    case "warning":
      return "warning";
    case "broken":
    case "failed":
    case "error":
      return "danger";
    case "disabled":
      return "neutral";
    case "redirected":
      return "queued";
    default:
      return "neutral";
  }
}

function counters(result: SourceUrlImportResponse | null) {
  return result?.summary ?? result;
}

function CounterCard({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{formatNumber(value)}</dd>
    </div>
  );
}

function ImportResultReport({
  title,
  result,
}: {
  title: string;
  result: SourceUrlImportResponse;
}) {
  const summary = counters(result);

  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Product Factory handoff</p>
          <h3>{title}</h3>
        </div>
        <div className="button-row">
          <Link className="button secondary" to="/vendor-sources/source-urls">
            Source URL coverage
          </Link>
          <Link className="button secondary" to="/find-source/candidates">
            Find Source
          </Link>
        </div>
      </div>

      <dl className="summary-grid source-url-import-summary-grid">
        <CounterCard label="Candidates" value={summary?.candidates_found} />
        <CounterCard label={result.apply ? "Imported" : "Would import"} value={result.apply ? summary?.imported_count : summary?.would_import_count ?? summary?.imported_count} />
        <CounterCard label={result.apply ? "Updated" : "Would update"} value={result.apply ? summary?.updated_count : summary?.would_update_count ?? summary?.updated_count} />
        <CounterCard label="Skipped" value={summary?.skipped_count} />
        <CounterCard label="Active" value={summary?.active_count} />
        <CounterCard label="Needs review" value={summary?.needs_review_count} />
        <CounterCard label="Invalid URL" value={summary?.invalid_url_count} />
        <CounterCard label="Duplicates" value={summary?.duplicate_count} />
      </dl>

      {result.warnings.length > 0 ? (
        <div className="form-warning">
          <strong>Warnings</strong>
          <ul className="source-url-warning-list">
            {result.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {Object.keys(result.skipped_reasons).length > 0 ? (
        <div className="compact-list">
          <strong>Skipped reasons</strong>
          <ul>
            {Object.entries(result.skipped_reasons).map(([reason, count]) => (
              <li key={reason}>
                {reason}: {count}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="table-wrap source-url-import-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Action</th>
              <th>Status</th>
              <th>Source name</th>
              <th>Model</th>
              <th>MPN</th>
              <th>URL</th>
              <th>Reason</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {result.report_items.length > 0 ? (
              result.report_items.map((item, index) => (
                <tr key={`${item.url ?? item.model ?? "handoff"}-${index}`}>
                  <td>{formatValue(item.action)}</td>
                  <td>
                    <span className={`status-badge ${statusClass(item.status ?? null)}`}>
                      {formatValue(item.status)}
                    </span>
                  </td>
                  <td>{formatValue(item.source_name ?? item.source_domain)}</td>
                  <td>{formatValue(item.model)}</td>
                  <td>{formatValue(item.mpn)}</td>
                  <td className="source-url-cell">
                    {item.url ? (
                      <a href={item.url} target="_blank" rel="noreferrer">
                        {item.url}
                      </a>
                    ) : (
                      "-"
                    )}
                  </td>
                  <td>{formatValue(item.reason)}</td>
                  <td>{formatValue(item.confidence)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={8}>No report rows returned.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {result.report_truncated || result.truncated ? (
        <p className="muted">Report was truncated by the backend or the requested report item limit.</p>
      ) : null}
    </section>
  );
}

export function VendorSourceImportsPage() {
  const [handoffPath, setHandoffPath] = useState(DEFAULT_HANDOFF_PATH);
  const [catalogSource, setCatalogSource] = useState("sourceCata");
  const persistInitialCapture = false;
  const [limit, setLimit] = useState("");
  const [reportItemsLimit, setReportItemsLimit] = useState("200");
  const [previewResult, setPreviewResult] = useState<SourceUrlImportResponse | null>(null);
  const [applyResult, setApplyResult] = useState<SourceUrlImportResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [isApplyLoading, setIsApplyLoading] = useState(false);
  const [reviewConfirmed, setReviewConfirmed] = useState(false);
  const [previewRequestKey, setPreviewRequestKey] = useState<string | null>(null);

  const requestBody = useMemo<ProductFactoryHandoffImportRequest>(() => {
    const parsedLimit = limit.trim().length > 0 ? Number(limit) : null;
    const parsedReportLimit = reportItemsLimit.trim().length > 0 ? Number(reportItemsLimit) : null;
    return {
      file_path: handoffPath.trim(),
      catalog_source: catalogSource.trim() || "sourceCata",
      persist_initial_capture: persistInitialCapture,
      limit: Number.isFinite(parsedLimit) ? parsedLimit : null,
      report_items_limit: Number.isFinite(parsedReportLimit) ? parsedReportLimit : 200,
    };
  }, [catalogSource, handoffPath, limit, persistInitialCapture, reportItemsLimit]);

  const requestKey = useMemo(() => JSON.stringify(requestBody), [requestBody]);

  useEffect(() => {
    if (previewRequestKey !== null && previewRequestKey !== requestKey) {
      setReviewConfirmed(false);
    }
  }, [previewRequestKey, requestKey]);

  const previewImport = async () => {
    setIsPreviewLoading(true);
    setPreviewError(null);
    setApplyError(null);
    setApplyResult(null);
    setReviewConfirmed(false);
    try {
      const result = await commerceClient.previewProductFactoryHandoffImport(requestBody);
      setPreviewResult(result);
      setPreviewRequestKey(requestKey);
    } catch (error) {
      setPreviewResult(null);
      setPreviewRequestKey(null);
      setPreviewError(getCommerceApiErrorMessage(error));
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const applyImport = async () => {
    setIsApplyLoading(true);
    setApplyError(null);
    try {
      const result = await commerceClient.applyProductFactoryHandoffImport(requestBody);
      setApplyResult(result);
    } catch (error) {
      setApplyError(getCommerceApiErrorMessage(error));
    } finally {
      setIsApplyLoading(false);
    }
  };

  const canApply =
    previewResult !== null &&
    previewRequestKey === requestKey &&
    reviewConfirmed &&
    !isPreviewLoading &&
    !isApplyLoading;

  return (
    <div className="page-stack vendor-source-imports-page">
      <header className="page-header">
        <p className="eyebrow">Vendor Sources</p>
        <h2>Product Factory Handoff Imports</h2>
        <p>Import source URL handoff artifacts produced by Product Factory through ecommerce-api.</p>
      </header>

      <section className="panel source-url-agent-warning-panel" aria-label="Product Factory handoff import safety">
        <ul className="source-url-warning-list">
          <li>Preview does not write database rows.</li>
          <li>Apply writes source URLs only; capture runs are launched separately.</li>
          <li>Only import handoff files produced by Product Factory.</li>
        </ul>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Import</p>
            <h3>Handoff artifact</h3>
          </div>
        </div>

        <form
          className="form"
          onSubmit={(event) => {
            event.preventDefault();
            void previewImport();
          }}
        >
          <div className="filter-grid source-url-agent-form-grid">
            <label>
              Handoff file path
              <input
                value={handoffPath}
                onChange={(event) => setHandoffPath(event.target.value)}
                placeholder={DEFAULT_HANDOFF_PATH}
                disabled={isPreviewLoading || isApplyLoading}
              />
            </label>
            <label>
              catalog_source
              <input
                value={catalogSource}
                onChange={(event) => setCatalogSource(event.target.value)}
                disabled={isPreviewLoading || isApplyLoading}
              />
            </label>
            <label>
              Limit
              <input
                type="number"
                min={1}
                step={1}
                value={limit}
                onChange={(event) => setLimit(event.target.value)}
                placeholder="Optional"
                disabled={isPreviewLoading || isApplyLoading}
              />
            </label>
            <label>
              report_items_limit
              <input
                type="number"
                min={1}
                step={1}
                value={reportItemsLimit}
                onChange={(event) => setReportItemsLimit(event.target.value)}
                disabled={isPreviewLoading || isApplyLoading}
              />
            </label>
          </div>

          <label className="checkbox-row source-url-confirm-row">
            <input
              type="checkbox"
              checked={reviewConfirmed}
              onChange={(event) => setReviewConfirmed(event.target.checked)}
              disabled={previewResult === null || previewRequestKey !== requestKey || isPreviewLoading || isApplyLoading}
            />
            I reviewed the preview report
          </label>

          <div className="button-row">
            <button
              className="button secondary"
              type="submit"
              disabled={isPreviewLoading || isApplyLoading || requestBody.file_path.length === 0}
            >
              {isPreviewLoading ? "Previewing..." : "Preview"}
            </button>
            <button
              className="button primary"
              type="button"
              disabled={!canApply}
              onClick={() => void applyImport()}
            >
              {isApplyLoading ? "Applying..." : "Apply"}
            </button>
          </div>
        </form>

        {previewError ? <ErrorState message={previewError} /> : null}
        {applyError ? <ErrorState message={applyError} /> : null}
      </section>

      {previewResult ? <ImportResultReport title="Preview report" result={previewResult} /> : null}
      {applyResult ? <ImportResultReport title="Applied import report" result={applyResult} /> : null}
    </div>
  );
}
