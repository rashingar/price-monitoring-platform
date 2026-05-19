import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import {
  commerceClient,
  getCommerceApiErrorMessage,
} from "../api/commerceClient";
import { getCatalogReadinessBlock } from "../api/catalogReadinessGate";
import type { CatalogReadinessBlock } from "../api/catalogReadinessGate";
import type {
  CatalogProduct,
  SourceUrl,
  SourceUrlImportRequest,
  SourceUrlImportResponse,
  SourceUrlStatus,
  SourceUrlSummaryResponse,
} from "../api/commerceTypes";
import { ErrorState, LoadingState } from "./layout/StateBlocks";

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

function sourceUrlId(sourceUrl: SourceUrl): string | number | null {
  return sourceUrl.id ?? sourceUrl.source_url_id ?? null;
}

function sourceUrlStatusClass(status: string | null | undefined): string {
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

function hasCaptureMetadata(sourceUrl: SourceUrl): boolean {
  return Boolean(
    sourceUrl.product_source_id ??
      sourceUrl.capture_status ??
      sourceUrl.last_capture_status ??
      sourceUrl.last_fetch_status ??
      sourceUrl.last_capture_strategy ??
      sourceUrl.last_capture_snapshot_id ??
      sourceUrl.source_capture_snapshot_id ??
      sourceUrl.snapshot_ref ??
      sourceUrl.full_snapshot_ref,
  );
}

function formatArtifactReference(value: unknown): string {
  if (typeof value === "string" && value.trim().length > 0) {
    return value;
  }

  if (typeof value === "object" && value !== null && "path" in value) {
    const path = (value as { path?: unknown }).path;
    return typeof path === "string" && path.trim().length > 0 ? path : "-";
  }

  return "-";
}

function normalizeActionLabel(status: string): string {
  return status.replace(/_/g, " ");
}

function readinessMessage(error: unknown): string {
  const block = getCatalogReadinessBlock(error);
  return block ? block.message : getCommerceApiErrorMessage(error);
}

function ImportSummaryCard({
  label,
  value,
}: {
  label: string;
  value: number | null | undefined;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{typeof value === "number" ? value.toLocaleString() : "-"}</dd>
    </div>
  );
}

function SourceUrlSummaryGrid({ summary }: { summary: SourceUrlSummaryResponse | null }) {
  return (
    <dl className="summary-grid source-url-summary-grid">
      <ImportSummaryCard label="Total URLs" value={summary?.total_count} />
      <ImportSummaryCard label="Active" value={summary?.active_count} />
      <ImportSummaryCard label="Needs review" value={summary?.needs_review_count} />
      <ImportSummaryCard label="Broken" value={summary?.broken_count} />
      <ImportSummaryCard label="Disabled" value={summary?.disabled_count} />
      <ImportSummaryCard label="Products covered" value={summary?.products_with_urls_count} />
      <ImportSummaryCard label="Products without URLs" value={summary?.products_without_urls_count} />
      <ImportSummaryCard label="Coverage %" value={summary?.coverage_percent} />
    </dl>
  );
}

function formatPercent(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(1)}%` : "-";
}

function formatCoverageSummary(summary: SourceUrlSummaryResponse | null): string {
  if (!summary) {
    return "Coverage not loaded";
  }

  return [
    `Coverage: ${formatPercent(summary.coverage_percent)}`,
    `Active URLs: ${(summary.active_count ?? 0).toLocaleString()}`,
    `Needs review: ${(summary.needs_review_count ?? 0).toLocaleString()}`,
  ].join(" · ");
}

function importCounters(result: SourceUrlImportResponse | null) {
  return result?.summary ?? result;
}

function SourceUrlImportReport({ result }: { result: SourceUrlImportResponse }) {
  const counters = importCounters(result);

  return (
    <div className="source-url-import-report">
      <dl className="summary-grid source-url-import-summary-grid">
        <ImportSummaryCard label="Candidates" value={counters?.candidates_found} />
        <ImportSummaryCard
          label={result.apply ? "Imported" : "Would import"}
          value={result.apply ? counters?.imported_count : counters?.would_import_count ?? counters?.imported_count}
        />
        <ImportSummaryCard
          label={result.apply ? "Updated" : "Would update"}
          value={result.apply ? counters?.updated_count : counters?.would_update_count ?? counters?.updated_count}
        />
        <ImportSummaryCard label="Skipped" value={counters?.skipped_count} />
        <ImportSummaryCard label="Active" value={counters?.active_count} />
        <ImportSummaryCard label="Needs review" value={counters?.needs_review_count} />
        <ImportSummaryCard label="Invalid URL" value={counters?.invalid_url_count} />
        <ImportSummaryCard label="Duplicates" value={counters?.duplicate_count} />
        <ImportSummaryCard label="Unresolved" value={counters?.unresolved_identity_count} />
        <ImportSummaryCard label="Ambiguous" value={counters?.ambiguous_identity_count} />
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
              <th>Evidence</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {result.report_items.length > 0 ? (
              result.report_items.map((item, index) => (
                <tr key={`${item.url ?? "report"}-${index}`}>
                  <td>{formatValue(item.action)}</td>
                  <td>
                    <span className={`status-badge ${sourceUrlStatusClass(item.status ?? null)}`}>
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
                  <td>{formatValue(item.evidence_detail ?? item.evidence_source)}</td>
                  <td>{formatValue(item.reason)}</td>
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
    </div>
  );
}

export function SourceUrlImportPanel({
  disabled,
  onApplied,
}: {
  disabled: boolean;
  onApplied?: () => void;
}) {
  const [summary, setSummary] = useState<SourceUrlSummaryResponse | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [readinessBlock, setReadinessBlock] = useState<CatalogReadinessBlock | null>(null);
  const [isSummaryLoading, setIsSummaryLoading] = useState(false);
  const [includeObservations, setIncludeObservations] = useState(true);
  const [includeArtifacts, setIncludeArtifacts] = useState(true);
  const [catalogSource, setCatalogSource] = useState("sourceCata");
  const [limit, setLimit] = useState("");
  const [reportItemLimit, setReportItemLimit] = useState("200");
  const [previewResult, setPreviewResult] = useState<SourceUrlImportResponse | null>(null);
  const [applyResult, setApplyResult] = useState<SourceUrlImportResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [isApplyLoading, setIsApplyLoading] = useState(false);
  const [reviewConfirmed, setReviewConfirmed] = useState(false);
  const [previewRequestKey, setPreviewRequestKey] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);

  const loadSummary = useCallback(
    async (signal?: AbortSignal) => {
      if (disabled) {
        return;
      }

      setIsSummaryLoading(true);
      try {
        const nextSummary = await commerceClient.getSourceUrlSummary(signal);
        if (signal?.aborted) {
          return;
        }
        setSummary(nextSummary);
        setSummaryError(null);
        setReadinessBlock(null);
      } catch (error) {
        if (!signal?.aborted) {
          const block = getCatalogReadinessBlock(error);
          setReadinessBlock(block);
          setSummaryError(block ? null : getCommerceApiErrorMessage(error));
        }
      } finally {
        if (!signal?.aborted) {
          setIsSummaryLoading(false);
        }
      }
    },
    [disabled],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadSummary(controller.signal);
    return () => controller.abort();
  }, [loadSummary]);

  const requestBody = useMemo<SourceUrlImportRequest>(() => {
    const parsedLimit = limit.trim().length > 0 ? Number(limit) : null;
    const parsedReportLimit = reportItemLimit.trim().length > 0 ? Number(reportItemLimit) : null;
    return {
      catalog_source: catalogSource.trim() || "sourceCata",
      include_observations: includeObservations,
      include_artifacts: includeArtifacts,
      limit: Number.isFinite(parsedLimit) ? parsedLimit : null,
      report_items_limit:
        parsedReportLimit !== null && Number.isFinite(parsedReportLimit) ? parsedReportLimit : 200,
    };
  }, [catalogSource, includeArtifacts, includeObservations, limit, reportItemLimit]);

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
      const result = await commerceClient.previewSourceUrlImport(requestBody);
      setPreviewResult(result);
      setPreviewRequestKey(requestKey);
    } catch (error) {
      setPreviewError(readinessMessage(error));
      setPreviewRequestKey(null);
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const applyImport = async () => {
    setIsApplyLoading(true);
    setApplyError(null);
    try {
      const result = await commerceClient.applySourceUrlImport(requestBody);
      setApplyResult(result);
      await loadSummary();
      onApplied?.();
    } catch (error) {
      setApplyError(readinessMessage(error));
    } finally {
      setIsApplyLoading(false);
    }
  };

  const canApply =
    !disabled &&
    previewResult !== null &&
    previewRequestKey === requestKey &&
    reviewConfirmed &&
    !isPreviewLoading &&
    !isApplyLoading;

  return (
    <section className={`panel source-url-import-panel ${isExpanded ? "expanded" : "collapsed"}`}>
      <div className="source-url-import-header">
        <div>
          <p className="eyebrow">Source URLs</p>
          <h3>Source URL Import</h3>
          <p className="muted source-url-import-summary-text">{formatCoverageSummary(summary)}</p>
        </div>
        <div className="button-row">
          {isExpanded ? (
            <button
              className="button secondary"
              type="button"
              onClick={() => void loadSummary()}
              disabled={disabled || isSummaryLoading}
            >
              Refresh coverage
            </button>
          ) : null}
          <button
            className="button secondary"
            type="button"
            onClick={() => setIsExpanded((current) => !current)}
            aria-expanded={isExpanded}
          >
            {isExpanded ? "Collapse" : "Expand"}
          </button>
        </div>
      </div>

      {disabled ? (
        <p className="muted">Source URL import is locked until Catalog database/import readiness is restored.</p>
      ) : null}

      {!isExpanded ? null : (
        <>

          {isSummaryLoading ? <LoadingState label="Loading source URL coverage..." /> : null}
          {summaryError ? <ErrorState message={summaryError} onRetry={() => void loadSummary()} /> : null}
          {readinessBlock ? <p className="form-warning">{readinessBlock.message}</p> : null}
          {!summaryError && !readinessBlock ? <SourceUrlSummaryGrid summary={summary} /> : null}

          <div className="filter-grid source-url-import-controls">
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={includeObservations}
            onChange={(event) => setIncludeObservations(event.target.checked)}
            disabled={disabled || isPreviewLoading || isApplyLoading}
          />
          Include DB observations
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={includeArtifacts}
            onChange={(event) => setIncludeArtifacts(event.target.checked)}
            disabled={disabled || isPreviewLoading || isApplyLoading}
          />
          Include enriched artifacts
        </label>
        <label>
          Catalog source
          <input
            type="text"
            value={catalogSource}
            onChange={(event) => setCatalogSource(event.target.value)}
            disabled={disabled || isPreviewLoading || isApplyLoading}
          />
        </label>
        <label>
          Limit
          <input
            type="number"
            min={1}
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
            placeholder="No limit"
            disabled={disabled || isPreviewLoading || isApplyLoading}
          />
        </label>
        <label>
          Report item limit
          <input
            type="number"
            min={1}
            value={reportItemLimit}
            onChange={(event) => setReportItemLimit(event.target.value)}
            disabled={disabled || isPreviewLoading || isApplyLoading}
          />
        </label>
          </div>

          <div className="toolbar">
        <p className="muted">Apply requires a completed dry-run preview and explicit review confirmation.</p>
        <div className="button-row">
          <button
            className="button secondary"
            type="button"
            onClick={() => void previewImport()}
            disabled={disabled || isPreviewLoading || isApplyLoading}
          >
            {isPreviewLoading ? "Previewing..." : "Preview import"}
          </button>
          <button
            className="button primary"
            type="button"
            onClick={() => void applyImport()}
            disabled={!canApply}
          >
            {isApplyLoading ? "Applying..." : "Apply import"}
          </button>
        </div>
          </div>

          <label className="checkbox-row source-url-confirm-row">
        <input
          type="checkbox"
          checked={reviewConfirmed}
          onChange={(event) => setReviewConfirmed(event.target.checked)}
          disabled={disabled || previewResult === null || isApplyLoading}
        />
        I reviewed the dry-run report
          </label>

          {previewError ? <ErrorState message={previewError} /> : null}
          {previewResult ? (
            <div className="state-block source-url-result-block">
              <strong>Dry-run report</strong>
              <SourceUrlImportReport result={previewResult} />
            </div>
          ) : null}

          {applyError ? <ErrorState message={applyError} /> : null}
          {applyResult ? (
            <div className="state-block source-url-result-block">
              <strong>Applied import report</strong>
              <SourceUrlImportReport result={applyResult} />
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}

export function CatalogSourceUrlManager({
  product,
  disabled,
  refreshToken,
  onClose,
}: {
  product: CatalogProduct | null;
  disabled: boolean;
  refreshToken: number;
  onClose: () => void;
}) {
  const catalogProductId = product?.catalog_product_id;
  const [items, setItems] = useState<SourceUrl[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [readinessBlock, setReadinessBlock] = useState<CatalogReadinessBlock | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [pendingActionId, setPendingActionId] = useState<string | number | null>(null);
  const [newUrl, setNewUrl] = useState("");
  const [newSourceName, setNewSourceName] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [validationMessage, setValidationMessage] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | number | null>(null);
  const [editDraft, setEditDraft] = useState({ url: "", source_name: "", notes: "" });
  const [editError, setEditError] = useState<string | null>(null);

  const canLoad = !disabled && catalogProductId !== null && catalogProductId !== undefined && catalogProductId !== "";

  const loadItems = useCallback(
    async (signal?: AbortSignal) => {
      if (!canLoad) {
        setItems([]);
        return;
      }

      setIsLoading(true);
      try {
        const response = await commerceClient.listCatalogProductSourceUrls(catalogProductId, signal);
        if (signal?.aborted) {
          return;
        }
        setItems(response.items);
        setError(null);
        setReadinessBlock(null);
      } catch (loadError) {
        if (!signal?.aborted) {
          const block = getCatalogReadinessBlock(loadError);
          setReadinessBlock(block);
          setError(block ? null : getCommerceApiErrorMessage(loadError));
        }
      } finally {
        if (!signal?.aborted) {
          setIsLoading(false);
        }
      }
    },
    [canLoad, catalogProductId],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadItems(controller.signal);
    return () => controller.abort();
  }, [loadItems, refreshToken]);

  useEffect(() => {
    setEditingId(null);
    setEditError(null);
    setValidationMessage(null);
  }, [catalogProductId]);

  useEffect(() => {
    if (!product) {
      return undefined;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, product]);

  const addUrl = async (event: FormEvent) => {
    event.preventDefault();
    if (!canLoad || newUrl.trim().length === 0) {
      return;
    }

    setIsCreating(true);
    setError(null);
    try {
      const created = await commerceClient.createCatalogProductSourceUrl(catalogProductId, {
        url: newUrl.trim(),
        source_name: newSourceName.trim() || null,
        url_type: "manual",
        trust_level: "manual",
        added_by: "operator",
      });
      setItems((current) => [created, ...current.filter((item) => sourceUrlId(item) !== sourceUrlId(created))]);
      setNewUrl("");
      setNewSourceName("");
    } catch (createError) {
      setError(readinessMessage(createError));
    } finally {
      setIsCreating(false);
    }
  };

  const updateStatus = async (sourceUrl: SourceUrl, status: SourceUrlStatus) => {
    const id = sourceUrlId(sourceUrl);
    if (id === null) {
      return;
    }

    setPendingActionId(id);
    setError(null);
    try {
      const updated = await commerceClient.updateCatalogSourceUrl(id, { status });
      setItems((current) => current.map((item) => (sourceUrlId(item) === id ? updated : item)));
    } catch (updateError) {
      setError(readinessMessage(updateError));
    } finally {
      setPendingActionId(null);
    }
  };

  const validateUrl = async (sourceUrl: SourceUrl) => {
    const id = sourceUrlId(sourceUrl);
    if (id === null) {
      return;
    }

    setPendingActionId(id);
    setValidationMessage(null);
    setError(null);
    try {
      const response = await commerceClient.validateCatalogSourceUrl(id);
      if (response.item) {
        setItems((current) => current.map((item) => (sourceUrlId(item) === id ? response.item ?? item : item)));
      }
      setValidationMessage(response.validation.message ?? response.validation.status ?? "Validation complete.");
    } catch (validateError) {
      setError(readinessMessage(validateError));
    } finally {
      setPendingActionId(null);
    }
  };

  const startEdit = (sourceUrl: SourceUrl) => {
    const id = sourceUrlId(sourceUrl);
    if (id === null) {
      return;
    }

    setEditingId(id);
    setEditError(null);
    setEditDraft({
      url: sourceUrl.url,
      source_name: sourceUrl.source_name ?? "",
      notes: sourceUrl.notes ?? "",
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditError(null);
    setEditDraft({ url: "", source_name: "", notes: "" });
  };

  const saveEdit = async (sourceUrl: SourceUrl) => {
    const id = sourceUrlId(sourceUrl);
    if (id === null || editDraft.url.trim().length === 0) {
      return;
    }

    setPendingActionId(id);
    setEditError(null);
    try {
      const updated = await commerceClient.updateCatalogSourceUrl(id, {
        url: editDraft.url.trim(),
        source_name: editDraft.source_name.trim() || null,
        notes: editDraft.notes.trim() || null,
      });
      setItems((current) => current.map((item) => (sourceUrlId(item) === id ? updated : item)));
      cancelEdit();
    } catch (saveError) {
      setEditError(readinessMessage(saveError));
    } finally {
      setPendingActionId(null);
    }
  };

  if (!product) {
    return null;
  }

  const showCaptureColumns = items.some(hasCaptureMetadata);

  return (
    <div className="source-url-drawer-backdrop" onMouseDown={onClose}>
      <section
        className="source-url-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-url-drawer-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="source-url-drawer-header">
          <div>
            <p className="eyebrow">Catalog product</p>
            <h2 id="source-url-drawer-title">Source URLs</h2>
          </div>
          <button className="button secondary" type="button" onClick={onClose}>
            Close
          </button>
        </header>

        <div className="source-url-drawer-body">
          <dl className="source-url-product-summary">
            <div>
              <dt>Model</dt>
              <dd>{formatValue(product.model)}</dd>
            </div>
            <div>
              <dt>Name</dt>
              <dd>{formatValue(product.name)}</dd>
            </div>
            <div>
              <dt>Manufacturer</dt>
              <dd>{formatValue(product.manufacturer)}</dd>
            </div>
            <div>
              <dt>MPN</dt>
              <dd>{formatValue(product.mpn)}</dd>
            </div>
            <div>
              <dt>Catalog product id</dt>
              <dd>{formatValue(product.catalog_product_id)}</dd>
            </div>
          </dl>

          <div className="toolbar source-url-drawer-toolbar">
            <p className="muted">Manage monitored source URLs attached to this catalog product.</p>
            <button
              className="button secondary"
              type="button"
              onClick={() => void loadItems()}
              disabled={!canLoad || isLoading}
            >
              Refresh URLs
            </button>
          </div>

      {disabled ? (
        <p className="muted">Source URL manager is locked until Catalog database/import readiness is restored.</p>
      ) : null}
      {!disabled && !canLoad ? (
        <p className="form-warning">Catalog product id missing. Re-import catalog or update backend.</p>
      ) : null}
      {readinessBlock ? <p className="form-warning">{readinessBlock.message}</p> : null}
      {isLoading ? <LoadingState label="Loading source URLs..." /> : null}
      {error ? <ErrorState message={error} onRetry={() => void loadItems()} /> : null}
      {editError ? <ErrorState message={editError} /> : null}
      {validationMessage ? <p className="muted">{validationMessage}</p> : null}

      <form className="source-url-add-form" onSubmit={(event) => void addUrl(event)}>
        <label className="inline-field wide">
          Manual URL
          <input
            type="url"
            value={newUrl}
            onChange={(event) => setNewUrl(event.target.value)}
            placeholder="https://example.com/product"
            disabled={!canLoad || isCreating}
          />
        </label>
        <label className="inline-field" title="Source name identifies the vendor or registry source used for source URL capture.">
          Source name
          <input
            type="text"
            value={newSourceName}
            onChange={(event) => setNewSourceName(event.target.value)}
            placeholder="electronet, public, plaisio, kotsovolos"
            disabled={!canLoad || isCreating}
          />
        </label>
        <button className="button primary" type="submit" disabled={!canLoad || isCreating || newUrl.trim().length === 0}>
          {isCreating ? "Adding..." : "Add URL"}
        </button>
      </form>

      <div className="table-wrap source-url-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Source name</th>
              <th>Domain</th>
              <th>URL</th>
              <th>Status</th>
              <th>Type</th>
              <th>Trust</th>
              <th>Failures</th>
              <th>Last success</th>
              <th>Last failed</th>
              <th>Last error</th>
              {showCaptureColumns ? <th>Product source</th> : null}
              {showCaptureColumns ? <th>Capture</th> : null}
              {showCaptureColumns ? <th>Snapshot</th> : null}
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.length > 0 ? (
              items.map((sourceUrl, index) => {
                const id = sourceUrlId(sourceUrl);
                const isPending = pendingActionId !== null && pendingActionId === id;
                const isEditing = editingId !== null && editingId === id;
                return (
                  <tr key={`${id ?? sourceUrl.url}-${index}`}>
                    <td>
                      {isEditing ? (
                        <input
                          className="table-input"
                          type="text"
                          value={editDraft.source_name}
                          onChange={(event) =>
                            setEditDraft((current) => ({ ...current, source_name: event.target.value }))
                          }
                          disabled={isPending}
                          aria-label={`Edit source name for ${sourceUrl.url}`}
                        />
                      ) : (
                        formatValue(sourceUrl.source_name)
                      )}
                    </td>
                    <td>{formatValue(sourceUrl.source_domain)}</td>
                    <td className="source-url-cell">
                      {isEditing ? (
                        <div className="source-url-edit-form">
                          <label>
                            URL
                            <textarea
                              value={editDraft.url}
                              onChange={(event) =>
                                setEditDraft((current) => ({ ...current, url: event.target.value }))
                              }
                              disabled={isPending}
                              aria-label={`Edit URL for ${sourceUrl.url}`}
                            />
                          </label>
                          <label>
                            Notes
                            <textarea
                              value={editDraft.notes}
                              onChange={(event) =>
                                setEditDraft((current) => ({ ...current, notes: event.target.value }))
                              }
                              disabled={isPending}
                              aria-label={`Edit notes for ${sourceUrl.url}`}
                            />
                          </label>
                        </div>
                      ) : (
                        <>
                          <a href={sourceUrl.url} target="_blank" rel="noreferrer">
                            {sourceUrl.url}
                          </a>
                          {sourceUrl.url_normalized && sourceUrl.url_normalized !== sourceUrl.url ? (
                            <span className="artifact-path">Normalized: {sourceUrl.url_normalized}</span>
                          ) : null}
                        </>
                      )}
                    </td>
                    <td>
                      <span className={`status-badge ${sourceUrlStatusClass(sourceUrl.status)}`}>
                        {normalizeActionLabel(sourceUrl.status)}
                      </span>
                    </td>
                    <td>{formatValue(sourceUrl.url_type)}</td>
                    <td>{formatValue(sourceUrl.trust_level)}</td>
                    <td>{formatValue(sourceUrl.failure_count)}</td>
                    <td>{formatDate(sourceUrl.last_success_at)}</td>
                    <td>{formatDate(sourceUrl.last_failed_at)}</td>
                    <td>{formatValue(sourceUrl.last_error)}</td>
                    {showCaptureColumns ? <td>{formatValue(sourceUrl.product_source_id)}</td> : null}
                    {showCaptureColumns ? (
                      <td>
                        <span className={`status-badge ${sourceUrlStatusClass(sourceUrl.capture_status ?? sourceUrl.last_capture_status ?? sourceUrl.last_fetch_status ?? null)}`}>
                          {normalizeActionLabel(
                            sourceUrl.capture_status ?? sourceUrl.last_capture_status ?? sourceUrl.last_fetch_status ?? "-",
                          )}
                        </span>
                        <small className="artifact-path">
                          {formatValue(sourceUrl.last_capture_strategy)} /{" "}
                          {formatDate(sourceUrl.last_capture_at ?? sourceUrl.last_fetched_at ?? sourceUrl.last_success_at)}
                        </small>
                      </td>
                    ) : null}
                    {showCaptureColumns ? (
                      <td>
                        {formatValue(sourceUrl.source_capture_snapshot_id ?? sourceUrl.last_capture_snapshot_id)}
                        <small className="artifact-path">
                          {formatArtifactReference(sourceUrl.full_snapshot_ref ?? sourceUrl.snapshot_ref)}
                        </small>
                      </td>
                    ) : null}
                    <td>
                      <div className="button-row source-url-actions">
                        {isEditing ? (
                          <>
                            <button
                              className="button primary compact-button"
                              type="button"
                              onClick={() => void saveEdit(sourceUrl)}
                              disabled={disabled || isPending || id === null || editDraft.url.trim().length === 0}
                            >
                              Save
                            </button>
                            <button
                              className="button secondary compact-button"
                              type="button"
                              onClick={cancelEdit}
                              disabled={isPending}
                            >
                              Cancel
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              className="button secondary compact-button"
                              type="button"
                              onClick={() => startEdit(sourceUrl)}
                              disabled={disabled || isPending || id === null}
                            >
                              Edit
                            </button>
                            <button
                              className="button secondary compact-button"
                              type="button"
                              onClick={() => void validateUrl(sourceUrl)}
                              disabled={disabled || isPending || id === null}
                            >
                              Validate
                            </button>
                            {sourceUrl.status === "active" ? (
                              <button
                                className="button secondary compact-button"
                                type="button"
                                onClick={() => void updateStatus(sourceUrl, "disabled")}
                                disabled={disabled || isPending || id === null}
                              >
                                Disable
                              </button>
                            ) : (
                              <button
                                className="button secondary compact-button"
                                type="button"
                                onClick={() => void updateStatus(sourceUrl, "active")}
                                disabled={disabled || isPending || id === null}
                              >
                                {sourceUrl.status === "needs_review" ? "Promote to active" : "Reactivate"}
                              </button>
                            )}
                            {sourceUrl.status !== "needs_review" ? (
                              <button
                                className="button secondary compact-button"
                                type="button"
                                onClick={() => void updateStatus(sourceUrl, "needs_review")}
                                disabled={disabled || isPending || id === null}
                              >
                                Mark needs_review
                              </button>
                            ) : null}
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={showCaptureColumns ? 14 : 11}>No source URLs for this product yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
        </div>
      </section>
    </div>
  );
}
