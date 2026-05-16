import { useCallback, useEffect, useMemo, useState } from "react";
import { commerceClient, getCommerceApiErrorMessage } from "../api/commerceClient";
import type { VendorSourceCapability, VendorSourceHealthItem } from "../api/commerceTypes";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";

const KNOWN_HEALTH_REASONS = [
  "firecrawl_api_key_missing",
  "firecrawl_timeout",
  "firecrawl_rate_limited",
  "firecrawl_blocked",
  "firecrawl_http_error",
  "firecrawl_parse_failed",
  "firecrawl_no_offers",
  "firecrawl_unknown_error",
] as const;

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

function formatDate(value: unknown): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    return "-";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function normalizeLabel(value: unknown): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    return "-";
  }
  return value.replace(/_/g, " ");
}

function statusClass(value: unknown): string {
  const normalized = typeof value === "string" ? value.toLowerCase() : "";
  if (["healthy", "success", "ready"].includes(normalized)) {
    return "success";
  }
  if (["failing", "failed", "blocked"].includes(normalized)) {
    return "danger";
  }
  if (["unknown", "warning"].includes(normalized)) {
    return "warning";
  }
  return "neutral";
}

function sourceOptions(sources: VendorSourceCapability[], rows: VendorSourceHealthItem[]): string[] {
  return Array.from(
    new Set([
      ...sources.map((source) => String(source.source_name || "").trim()).filter(Boolean),
      ...rows.map((row) => String(row.vendor || "").trim()).filter(Boolean),
    ]),
  ).sort((left, right) => left.localeCompare(right));
}

function healthReasonOptions(rows: VendorSourceHealthItem[]): string[] {
  return Array.from(
    new Set([
      ...KNOWN_HEALTH_REASONS,
      ...rows.map((row) => String(row.health_reason || "").trim()).filter(Boolean),
    ]),
  ).sort((left, right) => left.localeCompare(right));
}

export function VendorSourceHealthPage() {
  const [rows, setRows] = useState<VendorSourceHealthItem[]>([]);
  const [sources, setSources] = useState<VendorSourceCapability[]>([]);
  const [vendorFilter, setVendorFilter] = useState("");
  const [healthReasonFilter, setHealthReasonFilter] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [recapturingId, setRecapturingId] = useState<string | null>(null);

  const loadPage = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    const [healthResult, sourcesResult] = await Promise.allSettled([
      commerceClient.getVendorSourceHealth({ vendor: vendorFilter, limit: 500 }, signal),
      commerceClient.listVendorSources(signal),
    ]);

    if (signal?.aborted) {
      return;
    }

    if (healthResult.status === "fulfilled") {
      setRows(healthResult.value.items);
      setError(null);
    } else {
      setRows([]);
      setError(getCommerceApiErrorMessage(healthResult.reason));
    }

    if (sourcesResult.status === "fulfilled") {
      setSources(sourcesResult.value);
    }

    setIsLoading(false);
  }, [vendorFilter]);

  useEffect(() => {
    const controller = new AbortController();
    void loadPage(controller.signal);
    return () => controller.abort();
  }, [loadPage]);

  const filteredRows = useMemo(
    () => rows.filter((row) => !healthReasonFilter || row.health_reason === healthReasonFilter),
    [healthReasonFilter, rows],
  );
  const vendors = useMemo(() => sourceOptions(sources, rows), [rows, sources]);
  const reasons = useMemo(() => healthReasonOptions(rows), [rows]);

  const recapture = async (row: VendorSourceHealthItem) => {
    const productSourceId = String(row.product_source_id);
    setRecapturingId(productSourceId);
    setNotice(null);
    try {
      await commerceClient.recaptureVendorSourceHealth(productSourceId);
      await loadPage();
      setNotice(`Recaptured product source ${productSourceId}.`);
    } catch (recaptureError) {
      setNotice(getCommerceApiErrorMessage(recaptureError));
    } finally {
      setRecapturingId(null);
    }
  };

  return (
    <div className="page-stack vendor-source-health-page">
      <header className="page-header">
        <p className="eyebrow">Vendor Sources</p>
        <h2>Source Health</h2>
        <p>Capture diagnostics for active product sources and source URLs.</p>
      </header>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Health</p>
            <h3>Product source capture health</h3>
          </div>
          <button className="button secondary" type="button" onClick={() => void loadPage()}>
            Refresh
          </button>
        </div>

        <div className="filter-grid source-url-agent-form-grid">
          <label>
            Source/vendor
            <select value={vendorFilter} onChange={(event) => setVendorFilter(event.target.value)}>
              <option value="">All sources/vendors</option>
              {vendors.map((vendor) => (
                <option key={vendor} value={vendor}>
                  {vendor}
                </option>
              ))}
            </select>
          </label>
          <label>
            health_reason
            <select value={healthReasonFilter} onChange={(event) => setHealthReasonFilter(event.target.value)}>
              <option value="">All reasons</option>
              {reasons.map((reason) => (
                <option key={reason} value={reason}>
                  {reason}
                </option>
              ))}
            </select>
          </label>
        </div>

        {notice ? <p className="form-warning">{notice}</p> : null}
        {isLoading ? <LoadingState label="Loading vendor source health..." /> : null}
        {error ? <ErrorState message={error} onRetry={() => void loadPage()} /> : null}
        {!isLoading && !error && filteredRows.length === 0 ? (
          <EmptyState title="No source health rows" message="No product source health rows match the current filters." />
        ) : null}

        {!isLoading && !error && filteredRows.length > 0 ? (
          <div className="table-wrap vendor-source-health-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>product_source_id</th>
                  <th>model</th>
                  <th>vendor</th>
                  <th>health</th>
                  <th>health_reason</th>
                  <th>last_error_code</th>
                  <th>consecutive_failures</th>
                  <th>last_success_at</th>
                  <th>source_url</th>
                  <th>action</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => {
                  const productSourceId = String(row.product_source_id);
                  const isRecapturing = recapturingId === productSourceId;
                  return (
                    <tr key={productSourceId}>
                      <td>{productSourceId}</td>
                      <td>{formatValue(row.model)}</td>
                      <td>{formatValue(row.vendor)}</td>
                      <td>
                        <span className={`status-badge ${statusClass(row.health)}`}>
                          {normalizeLabel(row.health)}
                        </span>
                      </td>
                      <td>{row.health_reason ? <span className="status-badge warning">{row.health_reason}</span> : "-"}</td>
                      <td>{formatValue(row.last_error_code)}</td>
                      <td>{formatValue(row.consecutive_failures)}</td>
                      <td>{formatDate(row.last_success_at)}</td>
                      <td className="source-url-cell">{formatValue(row.source_url)}</td>
                      <td>
                        <button
                          className="button secondary compact-button"
                          type="button"
                          disabled={isRecapturing}
                          onClick={() => void recapture(row)}
                        >
                          {isRecapturing ? "Recapturing..." : "Recapture"}
                        </button>
                      </td>
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
