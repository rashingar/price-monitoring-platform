import { type ChangeEvent, type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { commerceClient, getCommerceApiErrorMessage } from "../api/commerceClient";
import type {
  ProductFactoryBatchCandidate,
  ProductFactoryBatchResponse,
  ProductFactoryBatchRowResponse,
} from "../api/commerceTypes";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";

const COUNT_FIELDS: Array<{ key: keyof ProductFactoryBatchResponse; label: string }> = [
  { key: "total_rows", label: "Total rows" },
  { key: "pending_count", label: "Pending" },
  { key: "auto_selected_count", label: "Auto-selected" },
  { key: "manually_selected_count", label: "Manually selected" },
  { key: "needs_review_count", label: "Needs review" },
  { key: "no_usable_source_count", label: "No usable source" },
  { key: "resolution_failed_count", label: "Resolution failed" },
  { key: "skipped_count", label: "Skipped" },
];

const STATUS_LABELS: Record<string, string> = {
  pending: "pending",
  resolving_source: "resolving",
  auto_selected: "auto selected",
  manually_selected: "manual",
  needs_review: "needs review",
  no_usable_source: "no usable source",
  resolution_failed: "failed",
  skipped: "skipped",
};

const STATUS_TONES: Record<string, string> = {
  pending: "queued",
  resolving_source: "active",
  auto_selected: "success",
  manually_selected: "success",
  needs_review: "warning",
  no_usable_source: "neutral",
  resolution_failed: "danger",
  skipped: "neutral",
};

const BATCH_SOURCE_OPTIONS = [
  { name: "skroutz", label: "Skroutz" },
  { name: "bestprice", label: "BestPrice" },
  { name: "electronet", label: "Electronet" },
] as const;

type BatchSourceName = (typeof BATCH_SOURCE_OPTIONS)[number]["name"];

const DEFAULT_BATCH_SOURCE_NAMES = BATCH_SOURCE_OPTIONS.map((source) => source.name);

function isBatchSourceName(value: string): value is BatchSourceName {
  return BATCH_SOURCE_OPTIONS.some((source) => source.name === value);
}

function asCandidate(value: unknown): ProductFactoryBatchCandidate {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as ProductFactoryBatchCandidate
    : {};
}

function formatStatus(status: string | null | undefined): string {
  const normalized = (status ?? "pending").trim().toLowerCase();
  return STATUS_LABELS[normalized] ?? normalized.replace(/_/g, " ");
}

function statusTone(status: string | null | undefined): string {
  return STATUS_TONES[(status ?? "").trim().toLowerCase()] ?? "neutral";
}

function StatusBadge({ status }: { status: string | null | undefined }) {
  return <span className={`status-badge ${statusTone(status)}`}>{formatStatus(status)}</span>;
}

function formatOptional(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

function candidateUrl(candidate: ProductFactoryBatchCandidate): string {
  return typeof candidate.url === "string" ? candidate.url : "";
}

function candidateTitle(candidate: ProductFactoryBatchCandidate): string {
  return typeof candidate.title === "string" && candidate.title.trim().length > 0
    ? candidate.title.trim()
    : "Untitled product result";
}

function candidateSource(candidate: ProductFactoryBatchCandidate): string {
  return typeof candidate.source_name === "string" && candidate.source_name.trim().length > 0
    ? candidate.source_name.trim()
    : "unknown";
}

function candidateConfidence(candidate: ProductFactoryBatchCandidate): string {
  if (candidate.confidence === null || candidate.confidence === undefined || candidate.confidence === "") {
    return "-";
  }
  return String(candidate.confidence);
}

function shortUrl(value: string | null | undefined): string {
  const raw = String(value ?? "").trim();
  if (!raw) {
    return "-";
  }

  try {
    const parsed = new URL(raw);
    const path = parsed.pathname.length > 34 ? `${parsed.pathname.slice(0, 34)}...` : parsed.pathname;
    return `${parsed.hostname}${path}`;
  } catch {
    return raw.length > 52 ? `${raw.slice(0, 52)}...` : raw;
  }
}

function sameUrl(left: string | null | undefined, right: string | null | undefined): boolean {
  return String(left ?? "").trim() === String(right ?? "").trim();
}

function batchMetadataSourceNames(batch: ProductFactoryBatchResponse | null): BatchSourceName[] {
  const raw = batch?.metadata && Array.isArray(batch.metadata.selected_source_names)
    ? batch.metadata.selected_source_names
    : null;
  if (!raw) {
    return [...DEFAULT_BATCH_SOURCE_NAMES];
  }
  const normalized = raw
    .map((value) => String(value ?? "").trim().toLowerCase())
    .filter(isBatchSourceName);
  return normalized.length > 0 ? Array.from(new Set(normalized)) : [...DEFAULT_BATCH_SOURCE_NAMES];
}

function sourceNamesLabel(sourceNames: readonly string[]): string {
  const labels: string[] = [];
  for (const name of sourceNames) {
    const label = BATCH_SOURCE_OPTIONS.find((source) => source.name === name)?.label;
    if (label) {
      labels.push(label);
    }
  }
  return labels.length > 0 ? labels.join(", ") : "-";
}

function isResolutionActive(batch: ProductFactoryBatchResponse | null, rows: ProductFactoryBatchRowResponse[]): boolean {
  return batch?.status === "resolving" || rows.some((row) => row.status === "resolving_source");
}

function MetricGrid({ batch }: { batch: ProductFactoryBatchResponse }) {
  return (
    <dl className="summary-grid product-factory-batch-summary-grid">
      {COUNT_FIELDS.map((field) => (
        <div key={field.key}>
          <dt>{field.label}</dt>
          <dd>{Number(batch[field.key] ?? 0)}</dd>
        </div>
      ))}
    </dl>
  );
}

function SourceSelectionControls({
  selectedSourceNames,
  disabled,
  error,
  onToggle,
}: {
  selectedSourceNames: BatchSourceName[];
  disabled: boolean;
  error: string | null;
  onToggle: (sourceName: BatchSourceName) => void;
}) {
  return (
    <fieldset className="batch-source-selection">
      <legend>Search sources</legend>
      <div className="batch-source-options">
        {BATCH_SOURCE_OPTIONS.map((source) => (
          <label className="checkbox-row compact-checkbox" key={source.name}>
            <input
              type="checkbox"
              checked={selectedSourceNames.includes(source.name)}
              disabled={disabled}
              onChange={() => onToggle(source.name)}
            />
            {source.label}
          </label>
        ))}
      </div>
      <p className="muted">Search only selected supported sources.</p>
      {error ? <p className="form-error">{error}</p> : null}
    </fieldset>
  );
}

function BatchRowsTable({
  rows,
  activeReviewRowId,
  rowActionKey,
  onReview,
  onSkip,
}: {
  rows: ProductFactoryBatchRowResponse[];
  activeReviewRowId: number | null;
  rowActionKey: string | null;
  onReview: (row: ProductFactoryBatchRowResponse) => void;
  onSkip: (row: ProductFactoryBatchRowResponse) => void;
}) {
  if (rows.length === 0) {
    return <EmptyState title="No rows loaded" message="Upload a CSV or open a recent batch to review rows." />;
  }

  return (
    <div className="table-wrap product-factory-batch-table-wrap">
      <table>
        <thead>
          <tr>
            <th>Row</th>
            <th>Model</th>
            <th>Brand</th>
            <th>Name</th>
            <th>Status</th>
            <th>Selected source</th>
            <th>Confidence</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className={activeReviewRowId === row.id ? "selected-row" : undefined}>
              <td>{row.row_number}</td>
              <td>{row.model}</td>
              <td>{row.brand || "-"}</td>
              <td>
                <strong>{row.name}</strong>
                {row.error_code || row.error_message ? (
                  <span className="batch-row-error">
                    {row.error_code ? `${row.error_code}: ` : ""}
                    {row.error_message}
                  </span>
                ) : null}
              </td>
              <td><StatusBadge status={row.status} /></td>
              <td>{row.selected_source ?? "-"}</td>
              <td>{row.confidence ?? "-"}</td>
              <td>
                <div className="button-row product-factory-batch-actions">
                  <button className="button secondary compact-button" type="button" onClick={() => onReview(row)}>
                    Review
                  </button>
                  {row.selected_url ? (
                    <a className="button secondary compact-button" href={row.selected_url} target="_blank" rel="noreferrer">
                      Open selected URL
                    </a>
                  ) : null}
                  <button
                    className="button secondary compact-button"
                    type="button"
                    disabled={rowActionKey === `skip:${row.id}`}
                    onClick={() => onSkip(row)}
                  >
                    {rowActionKey === `skip:${row.id}` ? "Skipping..." : "Skip"}
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReviewPanel({
  row,
  manualUrl,
  manualError,
  rowActionKey,
  onManualUrlChange,
  onSelectCandidate,
  onSaveManualUrl,
  onClose,
}: {
  row: ProductFactoryBatchRowResponse;
  manualUrl: string;
  manualError: string | null;
  rowActionKey: string | null;
  onManualUrlChange: (value: string) => void;
  onSelectCandidate: (row: ProductFactoryBatchRowResponse, candidateUrl: string) => void;
  onSaveManualUrl: (row: ProductFactoryBatchRowResponse) => void;
  onClose: () => void;
}) {
  const candidates = (row.candidates ?? []).map(asCandidate);
  return (
    <section className="panel product-factory-batch-review-panel" aria-label="Batch row review">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Row review</p>
          <h3>Row {row.row_number}: {row.model}</h3>
          <p className="muted">{row.brand || "-"} · {row.name}</p>
        </div>
        <div className="button-row">
          <StatusBadge status={row.status} />
          <button className="button secondary compact-button" type="button" onClick={onClose}>Close</button>
        </div>
      </div>

      <dl className="price-review-detail-grid">
        <div>
          <dt>Selected URL</dt>
          <dd title={row.selected_url ?? ""}>{row.selected_url ? shortUrl(row.selected_url) : "-"}</dd>
        </div>
        <div>
          <dt>Selected source</dt>
          <dd>{row.selected_source ?? "-"}</dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd>{row.confidence ?? "-"}</dd>
        </div>
        <div>
          <dt>Error</dt>
          <dd>{row.error_message || row.error_code || "-"}</dd>
        </div>
      </dl>

      <details className="batch-query-details">
        <summary>Queries used ({row.queries?.length ?? 0})</summary>
        {row.queries && row.queries.length > 0 ? (
          <ul>
            {row.queries.map((query) => <li key={query}>{query}</li>)}
          </ul>
        ) : (
          <p className="muted">No queries recorded yet.</p>
        )}
      </details>

      <div className="batch-candidate-list">
        <div className="section-heading">
          <div>
            <h4>Candidates</h4>
            <p className="muted">Supported sources: Skroutz, BestPrice, Electronet.</p>
          </div>
        </div>
        {candidates.length > 0 ? candidates.map((candidate, index) => {
          const url = candidateUrl(candidate);
          const selected = sameUrl(row.selected_url, url);
          return (
            <article className={selected ? "batch-candidate-card selected" : "batch-candidate-card"} key={`${url}-${index}`}>
              <div>
                <div className="batch-candidate-title-row">
                  <strong>{candidateTitle(candidate)}</strong>
                  {selected ? <span className="status-badge success">selected</span> : null}
                </div>
                <p className="muted">
                  {candidateSource(candidate)} · {shortUrl(url)} · confidence {candidateConfidence(candidate)}
                </p>
                <details>
                  <summary>Full URL</summary>
                  <p className="artifact-path">{url || "-"}</p>
                </details>
              </div>
              <div className="button-row product-factory-batch-actions">
                {url ? (
                  <a className="button secondary compact-button" href={url} target="_blank" rel="noreferrer">Open URL</a>
                ) : null}
                <button
                  className="button primary compact-button"
                  type="button"
                  disabled={!url || rowActionKey === `candidate:${row.id}:${url}`}
                  onClick={() => onSelectCandidate(row, url)}
                >
                  {rowActionKey === `candidate:${row.id}:${url}` ? "Selecting..." : "Select"}
                </button>
              </div>
            </article>
          );
        }) : (
          <EmptyState title="No candidates" message="This row has no supported source URL candidates yet." />
        )}
      </div>

      <form className="batch-manual-url-form" onSubmit={(event) => { event.preventDefault(); onSaveManualUrl(row); }}>
        <label className="inline-field wide">
          <span>Manual URL</span>
          <input
            value={manualUrl}
            onChange={(event) => onManualUrlChange(event.target.value)}
            placeholder="https://www.skroutz.gr/s/..."
          />
        </label>
        <button className="button primary" type="submit" disabled={rowActionKey === `manual:${row.id}` || manualUrl.trim().length === 0}>
          {rowActionKey === `manual:${row.id}` ? "Saving..." : "Save manual URL"}
        </button>
        {manualError ? <p className="form-error">{manualError}</p> : null}
      </form>
    </section>
  );
}

export function ProductFactoryBatchIntakePage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [activeBatch, setActiveBatch] = useState<ProductFactoryBatchResponse | null>(null);
  const [rows, setRows] = useState<ProductFactoryBatchRowResponse[]>([]);
  const [recentBatches, setRecentBatches] = useState<ProductFactoryBatchResponse[]>([]);
  const [reviewRowId, setReviewRowId] = useState<number | null>(null);
  const [manualUrl, setManualUrl] = useState("");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [resolveError, setResolveError] = useState<string | null>(null);
  const [sourceSelectionError, setSourceSelectionError] = useState<string | null>(null);
  const [manualError, setManualError] = useState<string | null>(null);
  const [selectedSourceNames, setSelectedSourceNames] = useState<BatchSourceName[]>(() => [...DEFAULT_BATCH_SOURCE_NAMES]);
  const [isUploading, setIsUploading] = useState(false);
  const [isResolving, setIsResolving] = useState(false);
  const [isLoadingRows, setIsLoadingRows] = useState(false);
  const [rowActionKey, setRowActionKey] = useState<string | null>(null);

  const reviewRow = useMemo(
    () => rows.find((row) => row.id === reviewRowId) ?? null,
    [reviewRowId, rows],
  );
  const resolutionActive = isResolutionActive(activeBatch, rows);

  const loadRecentBatches = useCallback(async () => {
    try {
      const response = await commerceClient.listProductFactoryBatches();
      setRecentBatches(response.items.slice(0, 8));
    } catch (error) {
      setLoadError(getCommerceApiErrorMessage(error));
    }
  }, []);

  const refreshBatch = useCallback(async (
    batchId: number,
    options: { showLoading?: boolean; refreshRecent?: boolean } = {},
  ) => {
    const showLoading = options.showLoading ?? true;
    const refreshRecent = options.refreshRecent ?? true;
    if (showLoading) {
      setIsLoadingRows(true);
    }
    try {
      const [batch, rowsResponse] = await Promise.all([
        commerceClient.getProductFactoryBatch(batchId),
        commerceClient.getProductFactoryBatchRows(batchId),
      ]);
      setActiveBatch(batch);
      setRows(rowsResponse.items);
      if (refreshRecent) {
        await loadRecentBatches();
      }
    } finally {
      if (showLoading) {
        setIsLoadingRows(false);
      }
    }
  }, [loadRecentBatches]);

  useEffect(() => {
    void loadRecentBatches();
  }, [loadRecentBatches]);

  useEffect(() => {
    setSelectedSourceNames(batchMetadataSourceNames(activeBatch));
    setSourceSelectionError(null);
  }, [activeBatch?.id]);

  useEffect(() => {
    if (!activeBatch || !resolutionActive) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      void refreshBatch(activeBatch.id, { showLoading: false, refreshRecent: false });
    }, 1750);

    return () => window.clearInterval(intervalId);
  }, [activeBatch?.id, refreshBatch, resolutionActive]);

  useEffect(() => {
    if (reviewRow) {
      setManualUrl(reviewRow.selected_url ?? "");
      setManualError(null);
    }
  }, [reviewRow?.id]);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setSelectedFile(event.target.files?.[0] ?? null);
    setUploadError(null);
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) {
      setUploadError("Choose a CSV file before uploading.");
      return;
    }

    setIsUploading(true);
    setUploadError(null);
    setResolveError(null);
    try {
      const upload = await commerceClient.uploadProductFactoryBatchCsv(selectedFile);
      setActiveBatch(upload);
      setSelectedSourceNames(batchMetadataSourceNames(upload));
      setRows(upload.preview_rows ?? []);
      setReviewRowId(null);
      await refreshBatch(upload.id);
    } catch (error) {
      setUploadError(getCommerceApiErrorMessage(error));
    } finally {
      setIsUploading(false);
    }
  }

  function handleReset() {
    setSelectedFile(null);
    setActiveBatch(null);
    setRows([]);
    setReviewRowId(null);
    setManualUrl("");
    setSelectedSourceNames([...DEFAULT_BATCH_SOURCE_NAMES]);
    setUploadError(null);
    setResolveError(null);
    setSourceSelectionError(null);
    setManualError(null);
  }

  async function handleOpenBatch(batchId: number) {
    setLoadError(null);
    setResolveError(null);
    setReviewRowId(null);
    try {
      await refreshBatch(batchId);
    } catch (error) {
      setLoadError(getCommerceApiErrorMessage(error));
    }
  }

  function handleToggleSource(sourceName: BatchSourceName) {
    setSourceSelectionError(null);
    setSelectedSourceNames((current) => (
      current.includes(sourceName)
        ? current.filter((item) => item !== sourceName)
        : [...current, sourceName]
    ));
  }

  async function handleResolve() {
    if (!activeBatch) {
      return;
    }
    if (selectedSourceNames.length === 0) {
      setSourceSelectionError("Select at least one search source.");
      return;
    }

    setIsResolving(true);
    setResolveError(null);
    setSourceSelectionError(null);
    try {
      const resolved = await commerceClient.resolveProductFactoryBatch(activeBatch.id, {
        source_names: selectedSourceNames,
      });
      setActiveBatch(resolved);
      setSelectedSourceNames(batchMetadataSourceNames(resolved));
      setRows(resolved.rows);
      await loadRecentBatches();
    } catch (error) {
      setResolveError(getCommerceApiErrorMessage(error));
    } finally {
      setIsResolving(false);
    }
  }

  async function handleSelectCandidate(row: ProductFactoryBatchRowResponse, url: string) {
    if (!activeBatch) {
      return;
    }
    const actionKey = `candidate:${row.id}:${url}`;
    setRowActionKey(actionKey);
    setManualError(null);
    try {
      await commerceClient.selectProductFactoryBatchRowSource(activeBatch.id, row.id, { candidate_url: url });
      await refreshBatch(activeBatch.id);
    } catch (error) {
      setManualError(getCommerceApiErrorMessage(error));
    } finally {
      setRowActionKey(null);
    }
  }

  async function handleSaveManualUrl(row: ProductFactoryBatchRowResponse) {
    if (!activeBatch) {
      return;
    }
    const value = manualUrl.trim();
    if (!value) {
      setManualError("Enter a manual URL first.");
      return;
    }
    setRowActionKey(`manual:${row.id}`);
    setManualError(null);
    try {
      await commerceClient.selectProductFactoryBatchRowSource(activeBatch.id, row.id, { manual_url: value });
      await refreshBatch(activeBatch.id);
    } catch (error) {
      setManualError(getCommerceApiErrorMessage(error));
    } finally {
      setRowActionKey(null);
    }
  }

  async function handleSkip(row: ProductFactoryBatchRowResponse) {
    if (!activeBatch) {
      return;
    }
    if (!window.confirm(`Skip row ${row.row_number} (${row.model})?`)) {
      return;
    }
    setRowActionKey(`skip:${row.id}`);
    try {
      await commerceClient.skipProductFactoryBatchRow(activeBatch.id, row.id);
      await refreshBatch(activeBatch.id);
    } catch (error) {
      setResolveError(getCommerceApiErrorMessage(error));
    } finally {
      setRowActionKey(null);
    }
  }

  return (
    <div className="page product-factory-batch-page">
      <header className="page-header">
        <p className="eyebrow">Product Factory</p>
        <h2>Batch Intake</h2>
        <p>Upload product CSVs, resolve supported source URLs, and review low-confidence rows. This version only resolves source URLs.</p>
      </header>

      <div className="split-grid product-factory-batch-top-grid">
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Upload CSV</p>
              <h3>Start a batch</h3>
              <p className="muted">Required columns: model, brand, name. Supports comma or semicolon delimiter.</p>
            </div>
          </div>
          <form className="form" onSubmit={(event) => void handleUpload(event)}>
            <label className="inline-field wide">
              <span>CSV file</span>
              <input type="file" accept=".csv,text/csv" onChange={handleFileChange} />
            </label>
            <p className="state-block">Selected file: {selectedFile?.name ?? "none"}</p>
            <div className="button-row">
              <button className="button primary" type="submit" disabled={!selectedFile || isUploading}>
                {isUploading ? "Uploading..." : "Upload"}
              </button>
              {activeBatch || selectedFile ? (
                <button className="button secondary" type="button" onClick={handleReset}>Clear/reset</button>
              ) : null}
            </div>
            {uploadError ? <p className="form-error">{uploadError}</p> : null}
          </form>
        </section>

        <section className="panel product-factory-batch-recent-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Recent batches</p>
              <h3>Open batch</h3>
            </div>
            <button className="button secondary compact-button" type="button" onClick={() => void loadRecentBatches()}>
              Refresh
            </button>
          </div>
          {loadError ? <p className="form-error">{loadError}</p> : null}
          {recentBatches.length > 0 ? (
            <div className="batch-recent-list">
              {recentBatches.map((batch) => (
                <button
                  className={activeBatch?.id === batch.id ? "batch-recent-item active" : "batch-recent-item"}
                  type="button"
                  key={batch.id}
                  onClick={() => void handleOpenBatch(batch.id)}
                >
                  <span>Batch #{batch.id}</span>
                  <StatusBadge status={batch.status} />
                  <small>{batch.total_rows} rows · {batch.needs_review_count} review</small>
                </button>
              ))}
            </div>
          ) : (
            <p className="muted">No recent batches loaded.</p>
          )}
        </section>
      </div>

      {activeBatch ? (
        <>
          <section className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Active batch</p>
                <h3>{activeBatch.filename ?? `Batch #${activeBatch.id}`}</h3>
                <p className="muted">Batch id #{activeBatch.id} · status {activeBatch.status}</p>
                <p className="muted">Search sources: {sourceNamesLabel(selectedSourceNames)}</p>
              </div>
              <div className="button-row">
                <button className="button primary" type="button" disabled={isResolving || resolutionActive} onClick={() => void handleResolve()}>
                  {isResolving ? "Resolving..." : "Resolve URLs"}
                </button>
              </div>
            </div>
            <p className="state-block">Resolve URLs searches supported source pages only. It does not start Product Factory jobs.</p>
            <SourceSelectionControls
              selectedSourceNames={selectedSourceNames}
              disabled={isResolving || resolutionActive}
              error={sourceSelectionError}
              onToggle={handleToggleSource}
            />
            {resolutionActive ? (
              <p className="state-block">Resolving rows... table refreshes automatically.</p>
            ) : null}
            <MetricGrid batch={activeBatch} />
            {resolveError ? <ErrorState message={resolveError} onRetry={() => void handleResolve()} /> : null}
          </section>

          <section className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Rows</p>
                <h3>Review source resolution</h3>
              </div>
              {isLoadingRows ? <span className="muted">Refreshing rows...</span> : null}
            </div>
            {isLoadingRows && rows.length === 0 ? (
              <LoadingState label="Loading batch rows..." />
            ) : (
              <BatchRowsTable
                rows={rows}
                activeReviewRowId={reviewRowId}
                rowActionKey={rowActionKey}
                onReview={(row) => setReviewRowId(row.id)}
                onSkip={(row) => void handleSkip(row)}
              />
            )}
          </section>

          {reviewRow ? (
            <ReviewPanel
              row={reviewRow}
              manualUrl={manualUrl}
              manualError={manualError}
              rowActionKey={rowActionKey}
              onManualUrlChange={setManualUrl}
              onSelectCandidate={(row, url) => void handleSelectCandidate(row, url)}
              onSaveManualUrl={(row) => void handleSaveManualUrl(row)}
              onClose={() => setReviewRowId(null)}
            />
          ) : null}
        </>
      ) : (
        <EmptyState
          title="No active batch"
          message="Upload a CSV with model, brand, and name columns, or open a recent batch to continue source URL review."
        />
      )}
    </div>
  );
}
