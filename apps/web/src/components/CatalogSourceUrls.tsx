import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  commerceClient,
  getCommerceApiErrorMessage,
} from "../api/commerceClient";
import { getCatalogReadinessBlock } from "../api/catalogReadinessGate";
import type { CatalogReadinessBlock } from "../api/catalogReadinessGate";
import type {
  CatalogProduct,
  MarketplaceFilter,
  PriceMonitoringSource,
  ProductSourceUrlCandidateHistoryResponse,
  SourceUrlAgentRun,
  SourceUrlAgentRunRequest,
  SourceUrlCandidate,
  SourceUrlCandidateReviewDecision,
  SourceUrl,
  SourceUrlImportRequest,
  SourceUrlImportResponse,
  SourceUrlStatus,
  SourceUrlSummaryResponse,
} from "../api/commerceTypes";
import { getAutomationBlockerBadges } from "../features/catalog/catalogSelection";
import {
  getSourceUrlAgentRunId,
  isActiveSourceUrlAgentRun,
} from "../features/catalog/sourceUrlDiscovery";
import { submitSourceUrlCandidateReview } from "../features/source-url-candidates/sourceUrlCandidateReviewActions";
import { SourceUrlCandidateReview } from "./catalog-source-urls/SourceUrlCandidateReview";
import { SourceUrlDiscoveryStatus } from "./catalog-source-urls/SourceUrlDiscoveryStatus";
import { SourceUrlDrawerActions } from "./catalog-source-urls/SourceUrlDrawerActions";
import { SourceUrlManualForm } from "./catalog-source-urls/SourceUrlManualForm";
import { SourceUrlTable } from "./catalog-source-urls/SourceUrlTable";
import {
  candidateKey,
  discoverySourceForDrawer,
  formatValue,
  isSuccessfulDiscoveryRun,
  isTerminalDiscoveryRun,
  reviewableCandidates,
  sourceUrlId,
  sourceUrlStatusClass,
} from "./catalog-source-urls/sourceUrlDrawerUtils";
import { ErrorState, LoadingState } from "./layout/StateBlocks";

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
  marketplace,
  source,
  onDiscoveryStatusChange,
  onClose,
}: {
  product: CatalogProduct | null;
  disabled: boolean;
  refreshToken: number;
  marketplace: MarketplaceFilter;
  source: PriceMonitoringSource;
  onDiscoveryStatusChange?: () => void;
  onClose: () => void;
}) {
  const catalogProductId = product?.catalog_product_id;
  const discoveryPollIntervalRef = useRef<number | null>(null);
  const discoveryExtraRefreshTimeoutRef = useRef<number | null>(null);
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
  const [latestDiscoveryRun, setLatestDiscoveryRun] = useState<SourceUrlAgentRun | null>(null);
  const [candidateHistory, setCandidateHistory] = useState<ProductSourceUrlCandidateHistoryResponse | null>(null);
  const [isDiscoveryStarting, setIsDiscoveryStarting] = useState(false);
  const [isDiscoveryStatusLoading, setIsDiscoveryStatusLoading] = useState(false);
  const [discoveryMessage, setDiscoveryMessage] = useState<string | null>(null);
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);
  const [isCandidateReviewExpanded, setIsCandidateReviewExpanded] = useState(false);
  const [pendingCandidateId, setPendingCandidateId] = useState<string | null>(null);

  const canLoad = !disabled && catalogProductId !== null && catalogProductId !== undefined && catalogProductId !== "";
  const discoverySource = discoverySourceForDrawer(marketplace, source);
  const automationBlocker = product ? getAutomationBlockerBadges(product)[0]?.label ?? null : null;
  const canFindUrl = canLoad && product?.automation_eligible === true;

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

  const loadCandidateHistory = useCallback(
    async (signal?: AbortSignal) => {
      if (!canLoad) {
        setCandidateHistory(null);
        return null;
      }

      const response = await commerceClient.getCatalogProductSourceUrlCandidateHistory(catalogProductId, signal);
      if (!signal?.aborted) {
        setCandidateHistory(response);
      }
      return response;
    },
    [canLoad, catalogProductId],
  );

  const stopDiscoveryPolling = useCallback(() => {
    if (discoveryPollIntervalRef.current !== null) {
      window.clearInterval(discoveryPollIntervalRef.current);
      discoveryPollIntervalRef.current = null;
    }
    if (discoveryExtraRefreshTimeoutRef.current !== null) {
      window.clearTimeout(discoveryExtraRefreshTimeoutRef.current);
      discoveryExtraRefreshTimeoutRef.current = null;
    }
  }, [discoveryExtraRefreshTimeoutRef, discoveryPollIntervalRef]);

  const refreshDiscoveryOutputs = useCallback(async () => {
    await Promise.all([loadItems(), loadCandidateHistory().catch(() => null)]);
  }, [loadCandidateHistory, loadItems]);

  const pollDiscoveryRun = useCallback(
    (runId: string) => {
      stopDiscoveryPolling();
      let extraRefreshScheduled = false;
      const refresh = () => {
        setIsDiscoveryStatusLoading(true);
        commerceClient
          .getSourceUrlAgentRun(runId)
          .then((nextRun) => {
            setLatestDiscoveryRun(nextRun);
            setDiscoveryError(null);
            void loadCandidateHistory().catch(() => null);
            if (isTerminalDiscoveryRun(nextRun)) {
              stopDiscoveryPolling();
              onDiscoveryStatusChange?.();
              void refreshDiscoveryOutputs();
              if (isSuccessfulDiscoveryRun(nextRun) && !extraRefreshScheduled) {
                extraRefreshScheduled = true;
                window.setTimeout(() => {
                  void refreshDiscoveryOutputs();
                  onDiscoveryStatusChange?.();
                }, 1_500);
              }
            }
          })
          .catch((pollError) => {
            setDiscoveryError(getCommerceApiErrorMessage(pollError));
            stopDiscoveryPolling();
          })
          .finally(() => {
            setIsDiscoveryStatusLoading(false);
          });
      };

      refresh();
      discoveryPollIntervalRef.current = window.setInterval(refresh, 4_000);
    },
    [
      discoveryExtraRefreshTimeoutRef,
      discoveryPollIntervalRef,
      loadCandidateHistory,
      refreshDiscoveryOutputs,
      onDiscoveryStatusChange,
      stopDiscoveryPolling,
    ],
  );

  const loadLatestDiscoveryRun = useCallback(
    async (signal?: AbortSignal) => {
      if (!canLoad) {
        setLatestDiscoveryRun(null);
        return null;
      }

      setIsDiscoveryStatusLoading(true);
      try {
        const response = await commerceClient.getLatestSourceUrlAgentRunForCatalogProduct(
          catalogProductId,
          discoverySource,
          signal,
        );
        if (signal?.aborted) {
          return null;
        }
        setLatestDiscoveryRun(response.run);
        setDiscoveryError(null);
        const runId = getSourceUrlAgentRunId(response.run);
        if (runId && isActiveSourceUrlAgentRun(response.run)) {
          pollDiscoveryRun(runId);
        }
        return response.run;
      } catch (loadError) {
        if (!signal?.aborted) {
          setDiscoveryError(getCommerceApiErrorMessage(loadError));
        }
        return null;
      } finally {
        if (!signal?.aborted) {
          setIsDiscoveryStatusLoading(false);
        }
      }
    },
    [canLoad, catalogProductId, discoverySource, pollDiscoveryRun],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadItems(controller.signal);
    return () => controller.abort();
  }, [loadItems, refreshToken]);

  useEffect(() => {
    const controller = new AbortController();
    stopDiscoveryPolling();
    void loadLatestDiscoveryRun(controller.signal);
    void loadCandidateHistory(controller.signal).catch((loadError) => {
      if (!controller.signal.aborted) {
        setDiscoveryError(getCommerceApiErrorMessage(loadError));
      }
    });
    return () => {
      controller.abort();
      stopDiscoveryPolling();
    };
  }, [loadCandidateHistory, loadLatestDiscoveryRun, stopDiscoveryPolling]);

  useEffect(() => {
    setEditingId(null);
    setEditError(null);
    setValidationMessage(null);
    setDiscoveryMessage(null);
    setDiscoveryError(null);
    setCandidateHistory(null);
    setLatestDiscoveryRun(null);
    setIsCandidateReviewExpanded(false);
    setPendingCandidateId(null);
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

  const startDiscovery = async () => {
    if (!canFindUrl || !product || isDiscoveryStarting) {
      return;
    }

    setIsDiscoveryStarting(true);
    setDiscoveryError(null);
    setDiscoveryMessage(null);
    stopDiscoveryPolling();
    try {
      const request: SourceUrlAgentRunRequest = {
        mode: "catalog",
        source: discoverySource,
        catalog_product_id: Number(catalogProductId),
        selected_models: [String(product.model ?? "").trim()].filter(Boolean),
        missing_only: false,
        active_only: true,
        dry_run: true,
        apply_high_confidence: false,
        limit: 1,
        max_products_per_batch: 1,
        rate_limit_seconds: 2,
      };
      const createdRun = await commerceClient.createSourceUrlAgentRun(request);
      setLatestDiscoveryRun(createdRun);
      const runId = getSourceUrlAgentRunId(createdRun);
      setDiscoveryMessage(runId ? `Find URL run started: ${runId}` : "Find URL run started.");
      onDiscoveryStatusChange?.();
      await loadCandidateHistory().catch(() => null);
      if (runId && isActiveSourceUrlAgentRun(createdRun)) {
        pollDiscoveryRun(runId);
      } else {
        await refreshDiscoveryOutputs();
      }
    } catch (startError) {
      setDiscoveryError(getCommerceApiErrorMessage(startError));
    } finally {
      setIsDiscoveryStarting(false);
    }
  };

  const reviewCandidate = async (
    candidate: SourceUrlCandidate,
    decision: SourceUrlCandidateReviewDecision,
  ) => {
    const id = candidateKey(candidate);
    setPendingCandidateId(id);
    setDiscoveryError(null);
    setDiscoveryMessage(null);
    if (decision === "reject") {
      setCandidateHistory((current) =>
        current
          ? {
              ...current,
              items: current.items.map((item) => ({
                ...item,
                candidates: item.candidates.filter((row) => candidateKey(row) !== id),
              })),
            }
          : current,
      );
    }
    try {
      const updated = await submitSourceUrlCandidateReview({
        candidateId: candidate.id,
        decision,
        reviewNotes: candidate.notes ?? null,
      });
      setDiscoveryMessage(`Candidate ${id} ${decision === "accept" ? "accepted" : "rejected"}.`);
      setCandidateHistory((current) =>
        current
          ? {
              ...current,
              items: current.items.map((item) => ({
                ...item,
                candidates: item.candidates
                  .map((row) => (candidateKey(row) === id ? { ...row, ...updated } : row))
                  .filter((row) => {
                    const status = String(row.status ?? "").toLowerCase();
                    return status !== "rejected" && status !== "accepted";
                  }),
              })),
            }
          : current,
      );
      setIsCandidateReviewExpanded(false);
      await Promise.all([
        loadCandidateHistory().catch(() => null),
        loadLatestDiscoveryRun().catch(() => null),
        loadItems(),
      ]);
    } catch (reviewError) {
      setDiscoveryError(getCommerceApiErrorMessage(reviewError));
      await loadCandidateHistory().catch(() => null);
    } finally {
      setPendingCandidateId(null);
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

  const pendingCandidates = reviewableCandidates(candidateHistory);
  const findUrlDisabledReason =
    !canLoad
      ? "Catalog product id missing"
      : canFindUrl
        ? null
        : automationBlocker ?? "Automation blocked";

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

          <SourceUrlDrawerActions
            canLoad={canLoad}
            isLoading={isLoading}
            canFindUrl={canFindUrl}
            isDiscoveryStarting={isDiscoveryStarting}
            findUrlDisabledReason={findUrlDisabledReason}
            discoverySource={discoverySource}
            onRefresh={() => void loadItems()}
            onFindUrl={() => void startDiscovery()}
          />

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
      {findUrlDisabledReason && canLoad ? <p className="muted">Find URL disabled: {findUrlDisabledReason}.</p> : null}
      {discoveryMessage ? <p className="muted">{discoveryMessage}</p> : null}
      {discoveryError ? <ErrorState message={discoveryError} /> : null}

      <SourceUrlDiscoveryStatus run={latestDiscoveryRun} isLoading={isDiscoveryStatusLoading} />
      <SourceUrlCandidateReview
        candidates={pendingCandidates}
        expanded={isCandidateReviewExpanded}
        pendingCandidateId={pendingCandidateId}
        onToggleExpanded={() => setIsCandidateReviewExpanded((current) => !current)}
        onReview={(candidate, decision) => void reviewCandidate(candidate, decision)}
      />

      <SourceUrlManualForm
        canLoad={canLoad}
        isCreating={isCreating}
        newUrl={newUrl}
        newSourceName={newSourceName}
        onNewUrlChange={setNewUrl}
        onNewSourceNameChange={setNewSourceName}
        onSubmit={(event) => void addUrl(event)}
      />

      <SourceUrlTable
        items={items}
        disabled={disabled}
        pendingActionId={pendingActionId}
        editingId={editingId}
        editDraft={editDraft}
        onEditDraftChange={setEditDraft}
        onStartEdit={startEdit}
        onCancelEdit={cancelEdit}
        onSaveEdit={(sourceUrl) => void saveEdit(sourceUrl)}
        onValidate={(sourceUrl) => void validateUrl(sourceUrl)}
        onUpdateStatus={(sourceUrl, status) => void updateStatus(sourceUrl, status)}
      />
        </div>
      </section>
    </div>
  );
}
