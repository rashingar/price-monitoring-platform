import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { commerceClient, getCommerceApiErrorMessage } from "../api/commerceClient";
import type {
  MissingSourceUrlProduct,
  SourceUrlSummaryResponse,
  VendorSourceCapability,
} from "../api/commerceTypes";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";

const STATUS_KEYS = ["active", "needs_review", "broken", "disabled", "redirected"] as const;
const URL_TYPE_KEYS = ["manual", "imported", "discovered"] as const;

function parseNumberLike(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  return 0;
}

function formatNumber(value: unknown): string {
  return parseNumberLike(value).toLocaleString();
}

function formatPercent(value: unknown): string {
  const numericValue = parseNumberLike(value);
  return `${numericValue.toFixed(numericValue % 1 === 0 ? 0 : 1)}%`;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return String(value);
}

function normalizeLabel(value: string): string {
  return value.replace(/_/g, " ");
}

function statusClass(status: string): string {
  switch (status) {
    case "active":
      return "success";
    case "needs_review":
    case "redirected":
      return "warning";
    case "broken":
    case "disabled":
      return "danger";
    default:
      return "neutral";
  }
}

function getSummaryCount(summary: SourceUrlSummaryResponse | null, key: string): number {
  if (!summary) {
    return 0;
  }

  switch (key) {
    case "active":
      return parseNumberLike(summary.active_count ?? summary.by_status?.active);
    case "needs_review":
      return parseNumberLike(summary.needs_review_count ?? summary.by_status?.needs_review);
    case "broken":
      return parseNumberLike(summary.broken_count ?? summary.by_status?.broken);
    case "disabled":
      return parseNumberLike(summary.disabled_count ?? summary.by_status?.disabled);
    case "redirected":
      return parseNumberLike(summary.redirected_count ?? summary.by_status?.redirected);
    case "manual":
      return parseNumberLike(summary.manual_count ?? summary.by_type?.manual);
    case "imported":
      return parseNumberLike(summary.imported_count ?? summary.by_type?.imported);
    case "discovered":
      return parseNumberLike(summary.discovered_count ?? summary.by_type?.discovered);
    default:
      return 0;
  }
}

function makeMissingProductRows(summary: SourceUrlSummaryResponse | null): MissingSourceUrlProduct[] {
  if (!summary) {
    return [];
  }

  const explicitRows = summary.missing_active_source_url_products ?? [];
  if (explicitRows.length > 0) {
    return explicitRows;
  }

  const models = summary.missing_source_url_models ?? [];
  const productIds = summary.missing_source_url_catalog_product_ids ?? [];
  const rowCount = Math.max(models.length, productIds.length);
  return Array.from({ length: rowCount }, (_, index) => ({
    model: models[index] ?? null,
    catalog_product_id: productIds[index] ?? null,
    reason: "missing_active_source_url",
  }));
}

function capabilityStatus(source: VendorSourceCapability): string {
  if (source.capture_enabled && source.capture_implemented) {
    return "capture ready";
  }

  if (source.capture_implemented) {
    return "capture implemented";
  }

  if (source.discovery_enabled) {
    return "capture not implemented";
  }

  return "disabled";
}

function capabilityStatusClass(label: string): string {
  if (label === "capture ready" || label === "capture implemented") {
    return "success";
  }

  if (label === "capture not implemented") {
    return "warning";
  }

  return "neutral";
}

function SummaryItem({ label, value, detail }: { label: string; value: string | number; detail?: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}

function CountTable({
  title,
  label,
  rows,
}: {
  title: string;
  label: string;
  rows: Array<{ key: string; count: number; tone?: string }>;
}) {
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">{label}</p>
          <h3>{title}</h3>
        </div>
      </div>
      <div className="table-wrap vendor-source-count-table-wrap">
        <table>
          <thead>
            <tr>
              <th>{label}</th>
              <th>count</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <td>
                  {row.tone ? (
                    <span className={`status-badge ${row.tone}`}>{normalizeLabel(row.key)}</span>
                  ) : (
                    normalizeLabel(row.key)
                  )}
                </td>
                <td>{formatNumber(row.count)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function VendorSourceUrlsPage() {
  const [summary, setSummary] = useState<SourceUrlSummaryResponse | null>(null);
  const [sources, setSources] = useState<VendorSourceCapability[]>([]);
  const [sourceFilter, setSourceFilter] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [sourceError, setSourceError] = useState<string | null>(null);

  const loadPage = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    const [summaryResult, sourcesResult] = await Promise.allSettled([
      commerceClient.getVendorSourceUrlSummary(signal, sourceFilter),
      commerceClient.listVendorSources(signal),
    ]);

    if (signal?.aborted) {
      return;
    }

    if (summaryResult.status === "fulfilled") {
      setSummary(summaryResult.value);
      setSummaryError(null);
    } else {
      setSummary(null);
      setSummaryError(getCommerceApiErrorMessage(summaryResult.reason));
    }

    if (sourcesResult.status === "fulfilled") {
      setSources(sourcesResult.value);
      setSourceError(null);
    } else {
      setSources([]);
      setSourceError(getCommerceApiErrorMessage(sourcesResult.reason));
    }

    setIsLoading(false);
  }, [sourceFilter]);

  useEffect(() => {
    const controller = new AbortController();
    void loadPage(controller.signal);
    return () => controller.abort();
  }, [loadPage]);

  const missingProducts = useMemo(() => makeMissingProductRows(summary), [summary]);
  const sourceRows = useMemo(
    () =>
      Object.entries(summary?.by_source ?? {})
        .filter(([sourceName]) => !sourceFilter || sourceName === sourceFilter)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, count]) => ({ key, count })),
    [sourceFilter, summary],
  );
  const filteredSources = useMemo(
    () => sources.filter((source) => !sourceFilter || source.source_name === sourceFilter),
    [sourceFilter, sources],
  );
  const statusRows = STATUS_KEYS.map((key) => ({
    key,
    count: getSummaryCount(summary, key),
    tone: statusClass(key),
  }));
  const typeRows = URL_TYPE_KEYS.map((key) => ({
    key,
    count: getSummaryCount(summary, key),
  }));
  const productsWithoutActive = parseNumberLike(summary?.products_without_urls_count);

  return (
    <div className="page-stack vendor-source-urls-page">
      <header className="page-header">
        <p className="eyebrow">Vendor Sources</p>
        <h2>Source URLs / Coverage</h2>
        <p>Price Monitoring requires at least one active source URL.</p>
        <p>Price Monitoring requires an active URL for the selected source/vendor.</p>
        <p>Use Find Source to discover and review candidate URLs before capture.</p>
        <p>Broken, disabled, redirected, and needs-review URLs are not monitorable.</p>
      </header>

      {isLoading ? <LoadingState label="Loading vendor source URL coverage..." /> : null}
      {summaryError && !isLoading ? (
        <ErrorState message={summaryError} onRetry={() => void loadPage()} />
      ) : null}

      {!isLoading && summary ? (
        <>
          <section className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Coverage</p>
                <h3>Catalog monitorability</h3>
              </div>
              <button className="button secondary" type="button" onClick={() => void loadPage()}>
                Refresh
              </button>
            </div>
            <label className="inline-field">
              Source/vendor
              <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}>
                <option value="">All sources/vendors</option>
                {sources.map((source) => (
                  <option key={String(source.source_name)} value={String(source.source_name)}>
                    {String(source.source_name)}
                  </option>
                ))}
              </select>
            </label>
            <dl className="summary-grid vendor-source-coverage-grid">
              <SummaryItem
                label="Total catalog products"
                value={formatNumber(summary.catalog_product_count)}
              />
              <SummaryItem
                label="Products with active source URLs"
                value={formatNumber(summary.products_with_urls_count)}
                detail="Eligible for monitoring"
              />
              <SummaryItem
                label="Products without active source URLs"
                value={formatNumber(productsWithoutActive)}
                detail="Not monitorable"
              />
              <SummaryItem
                label="Coverage percent"
                value={formatPercent(summary.coverage_percent)}
              />
            </dl>
          </section>

          <div className="vendor-source-count-grid">
            <CountTable title="Counts by status" label="status" rows={statusRows} />
            <CountTable title="Counts by source_name" label="source_name" rows={sourceRows} />
            <CountTable title="Counts by url_type" label="url_type" rows={typeRows} />
          </div>

          <section className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Monitorability</p>
                <h3>Products without active source URLs</h3>
              </div>
              <Link className="button secondary" to="/find-source/candidates">
                Find Source
              </Link>
            </div>
            {productsWithoutActive > 0 ? (
              <>
                <p className="form-warning">
                  Products without active source URLs for the selected source/vendor are not monitorable by Price Monitoring.
                </p>
                {missingProducts.length > 0 ? (
                  <div className="table-wrap vendor-source-missing-table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>catalog_product_id</th>
                          <th>model</th>
                          <th>mpn</th>
                          <th>manufacturer</th>
                          <th>product</th>
                          <th>monitoring status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {missingProducts.map((product, index) => (
                          <tr key={`${formatValue(product.catalog_product_id)}-${formatValue(product.model)}-${index}`}>
                            <td>{formatValue(product.catalog_product_id)}</td>
                            <td>{formatValue(product.model)}</td>
                            <td>{formatValue(product.mpn)}</td>
                            <td>{formatValue(product.manufacturer)}</td>
                            <td>{formatValue(product.name)}</td>
                            <td>
                              <span className="status-badge danger">not monitorable</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyState
                    title="Missing product details unavailable"
                    message="The summary reports products without active source URLs, but the backend did not include product identifiers."
                  />
                )}
              </>
            ) : (
              <EmptyState
                title="All catalog products have active source URLs"
                message="Every catalog product in this summary is eligible for Price Monitoring."
              />
            )}
          </section>
        </>
      ) : null}

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Capabilities</p>
            <h3>Source capability table</h3>
          </div>
          <Link className="button secondary" to="/find-source/runs">
            Discovery runs
          </Link>
        </div>
        {sourceError ? <p className="form-warning">{sourceError}</p> : null}
        {!isLoading && !sourceError && filteredSources.length === 0 ? (
          <EmptyState
            title="No vendor sources"
            message="The backend returned no source capabilities."
          />
        ) : null}
        {filteredSources.length > 0 ? (
          <div className="table-wrap vendor-source-capability-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>source_name</th>
                  <th>source_type</th>
                  <th>discovery_enabled</th>
                  <th>capture_implemented</th>
                  <th>supports_xhr_capture</th>
                  <th>notes</th>
                </tr>
              </thead>
              <tbody>
                {filteredSources.map((source) => {
                  const captureStatus = capabilityStatus(source);
                  return (
                    <tr key={String(source.source_name)}>
                      <td>{formatValue(source.source_name)}</td>
                      <td>{formatValue(source.source_type)}</td>
                      <td>
                        <span className={`status-badge ${source.discovery_enabled ? "success" : "neutral"}`}>
                          {source.discovery_enabled ? "discovery enabled" : "discovery disabled"}
                        </span>
                      </td>
                      <td>
                        <span className={`status-badge ${capabilityStatusClass(captureStatus)}`}>
                          {captureStatus}
                        </span>
                      </td>
                      <td>
                        <span className={`status-badge ${source.supports_xhr_capture ? "success" : "neutral"}`}>
                          {source.supports_xhr_capture ? "yes" : "no"}
                        </span>
                      </td>
                      <td>{formatValue(source.notes)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}
