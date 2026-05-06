import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";
import {
  commerceClient,
  getCommerceApiErrorMessage,
} from "../api/commerceClient";
import type {
  SourceUrlCandidate,
  SourceUrlCandidateListParams,
  SourceUrlCandidateReviewActionConfig,
  SourceUrlCandidateReviewDecision,
  SourceUrlCandidateReviewLayout,
  SourceUrlCandidateReviewLayoutColumn,
  SourceUrlCandidateStatus,
} from "../api/commerceTypes";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";

const DEFAULT_LIMIT = 50;
const REVIEW_LAYOUT_USER_KEY = "default";
const REVIEW_STATUSES: Array<SourceUrlCandidateStatus | "all"> = [
  "needs_review",
  "accepted",
  "rejected",
  "not_found",
  "error",
  "all",
];

const DEFAULT_COLUMNS: SourceUrlCandidateReviewLayoutColumn[] = [
  { key: "id", label: "Candidate id", visible: true, table_column_visible: true, width_px: 110, order: 0 },
  { key: "run_id", label: "Run id", visible: true, table_column_visible: true, width_px: 130, order: 1 },
  { key: "model", label: "Model", visible: true, table_column_visible: true, width_px: 110, order: 2 },
  { key: "product_name", label: "Product", visible: true, table_column_visible: true, width_px: 220, order: 3 },
  { key: "source_name", label: "Source name", visible: true, table_column_visible: true, width_px: 120, order: 4 },
  { key: "candidate_title", label: "Candidate title", visible: true, table_column_visible: true, width_px: 220, order: 5 },
  { key: "candidate_price", label: "Price", visible: true, table_column_visible: true, width_px: 95, order: 6 },
  { key: "confidence_score", label: "Confidence", visible: true, table_column_visible: true, width_px: 105, order: 7 },
  { key: "status", label: "Review status", visible: true, table_column_visible: true, width_px: 130, order: 8 },
  { key: "created_at", label: "Created", visible: true, table_column_visible: true, width_px: 155, order: 9 },
];

const FALLBACK_REVIEW_ACTIONS: SourceUrlCandidateReviewActionConfig[] = [
  { decision: "accept", label: "Accept", style: "primary" },
  { decision: "reject", label: "Reject", style: "danger" },
  { decision: "not_found", label: "Not found", style: "secondary" },
  { decision: "needs_manual_review", label: "Needs review", style: "secondary" },
  { decision: "replace_url", label: "Replace URL", style: "secondary", requires_url: true },
];

interface CandidateFilters {
  status: SourceUrlCandidateStatus | "all";
  sourceName: string;
  runId: string;
  model: string;
  catalogProductId: string;
  minConfidence: string;
  maxConfidence: string;
  matchMethod: string;
  createdFrom: string;
  createdTo: string;
}

const initialFilters: CandidateFilters = {
  status: "needs_review",
  sourceName: "",
  runId: "",
  model: "",
  catalogProductId: "",
  minConfidence: "",
  maxConfidence: "",
  matchMethod: "",
  createdFrom: "",
  createdTo: "",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

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

function formatMoney(value: unknown): string {
  const numericValue = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  if (!Number.isFinite(numericValue)) {
    return "-";
  }

  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 2,
  }).format(numericValue);
}

function formatConfidence(value: unknown): string {
  const numericValue = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(numericValue) ? numericValue.toFixed(4) : "-";
}

function statusClass(status: string | null | undefined): string {
  switch (status) {
    case "accepted":
      return "success";
    case "needs_review":
      return "warning";
    case "rejected":
    case "error":
      return "danger";
    case "not_found":
      return "neutral";
    default:
      return "neutral";
  }
}

function normalizeLabel(value: string | null | undefined): string {
  return value ? value.replace(/_/g, " ") : "-";
}

function candidateId(candidate: SourceUrlCandidate): string {
  return String(candidate.id);
}

function getJsonSection(source: unknown, keys: string[]): unknown {
  if (!isRecord(source)) {
    return undefined;
  }

  for (const key of keys) {
    if (source[key] !== undefined) {
      return source[key];
    }
  }

  return undefined;
}

function renderJsonValue(value: unknown): string {
  if (value === undefined || value === null || value === "") {
    return "-";
  }

  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  return JSON.stringify(value, null, 2);
}

function JsonDetail({ value }: { value: unknown }) {
  const rendered = renderJsonValue(value);
  if (rendered === "-") {
    return <span className="muted">-</span>;
  }

  if (typeof value === "object" && value !== null) {
    return <pre className="json-block compact-json-block">{rendered}</pre>;
  }

  return <span>{rendered}</span>;
}

function EvidenceSection({
  title,
  value,
}: {
  title: string;
  value: unknown;
}) {
  return (
    <div className="candidate-evidence-section">
      <dt>{title}</dt>
      <dd>
        <JsonDetail value={value} />
      </dd>
    </div>
  );
}

function passesCreatedDateFilter(candidate: SourceUrlCandidate, filters: CandidateFilters): boolean {
  if (!filters.createdFrom && !filters.createdTo) {
    return true;
  }

  if (!candidate.created_at) {
    return false;
  }

  const createdTime = new Date(candidate.created_at).getTime();
  if (Number.isNaN(createdTime)) {
    return true;
  }

  if (filters.createdFrom) {
    const fromTime = new Date(`${filters.createdFrom}T00:00:00`).getTime();
    if (!Number.isNaN(fromTime) && createdTime < fromTime) {
      return false;
    }
  }

  if (filters.createdTo) {
    const toTime = new Date(`${filters.createdTo}T23:59:59.999`).getTime();
    if (!Number.isNaN(toTime) && createdTime > toTime) {
      return false;
    }
  }

  return true;
}

function buildParams(filters: CandidateFilters, offset: number): SourceUrlCandidateListParams {
  return {
    status: filters.status === "all" ? null : filters.status,
    source_name: filters.sourceName.trim() || null,
    run_id: filters.runId.trim() || null,
    model: filters.model.trim() || null,
    catalog_product_id: filters.catalogProductId.trim() || null,
    min_confidence: filters.minConfidence.trim() || null,
    max_confidence: filters.maxConfidence.trim() || null,
    limit: DEFAULT_LIMIT,
    offset,
  };
}

function columnKey(column: SourceUrlCandidateReviewLayoutColumn): string {
  return String(column.key ?? column.id ?? column.field ?? "");
}

function columnLabel(column: SourceUrlCandidateReviewLayoutColumn): string {
  const key = columnKey(column);
  return String(column.label ?? column.title ?? key.replace(/_/g, " "));
}

function isColumnVisible(column: SourceUrlCandidateReviewLayoutColumn): boolean {
  if (columnKey(column) === "actions") {
    return false;
  }

  if (typeof column.visible === "boolean") {
    return column.visible;
  }

  if (typeof column.table_column_visible === "boolean") {
    return column.table_column_visible;
  }

  return true;
}

function normalizeColumns(columns: SourceUrlCandidateReviewLayoutColumn[]): SourceUrlCandidateReviewLayoutColumn[] {
  const source = columns.length > 0 ? columns : DEFAULT_COLUMNS;
  return source
    .filter((column) => columnKey(column).length > 0 && columnKey(column) !== "actions")
    .map((column, index) => ({
      ...column,
      key: columnKey(column),
      label: columnLabel(column),
      visible: isColumnVisible(column),
      table_column_visible: isColumnVisible(column),
      width_px: typeof column.width_px === "number" ? column.width_px : 140,
      order: typeof column.order === "number" ? column.order : index,
    }))
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
}

function makeFallbackLayout(): SourceUrlCandidateReviewLayout {
  return {
    user_key: REVIEW_LAYOUT_USER_KEY,
    columns: normalizeColumns(DEFAULT_COLUMNS),
    actions: { table_column_visible: false, replacement: "drawer_panel" },
    drawer: { review_actions: FALLBACK_REVIEW_ACTIONS },
  };
}

function getColumnWidth(column: SourceUrlCandidateReviewLayoutColumn): number {
  const width = typeof column.width_px === "number" ? column.width_px : 140;
  return Math.min(260, Math.max(72, width));
}

function getCandidateField(candidate: SourceUrlCandidate, key: string): unknown {
  if (key === "candidate_id") {
    return candidate.id;
  }

  return candidate[key];
}

function renderCandidateCell(candidate: SourceUrlCandidate, key: string): ReactNode {
  switch (key) {
    case "id":
    case "candidate_id":
      return formatValue(candidate.id);
    case "status":
    case "review_status":
      return (
        <span className={`status-badge ${statusClass(candidate.status)}`}>
          {normalizeLabel(candidate.status ?? null)}
        </span>
      );
    case "candidate_price":
    case "own_price":
      return formatMoney(getCandidateField(candidate, key));
    case "confidence_score":
    case "confidence":
      return formatConfidence(candidate.confidence_score);
    case "created_at":
    case "updated_at":
    case "reviewed_at":
      return formatDate(getCandidateField(candidate, key));
    case "candidate_url":
    case "canonical_url": {
      const url = getCandidateField(candidate, key);
      return typeof url === "string" && url.trim().length > 0 ? (
        <a href={url} target="_blank" rel="noreferrer">
          Open
        </a>
      ) : (
        "-"
      );
    }
    default:
      return formatValue(getCandidateField(candidate, key));
  }
}

function isInteractiveClick(target: EventTarget | null): boolean {
  return target instanceof Element
    ? Boolean(target.closest("a, button, input, select, textarea, label, summary, [role='button']"))
    : false;
}

function moveColumn(columns: SourceUrlCandidateReviewLayoutColumn[], index: number, direction: -1 | 1) {
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= columns.length) {
    return columns;
  }

  const next = [...columns];
  const [item] = next.splice(index, 1);
  next.splice(nextIndex, 0, item);
  return next.map((column, order) => ({ ...column, order }));
}

function LayoutSettingsCard({
  layout,
  error,
  isSaving,
  onChange,
  onSave,
  onReset,
}: {
  layout: SourceUrlCandidateReviewLayout;
  error: string | null;
  isSaving: boolean;
  onChange: (layout: SourceUrlCandidateReviewLayout) => void;
  onSave: () => void;
  onReset: () => void;
}) {
  const columns = normalizeColumns(layout.columns);

  function updateColumn(index: number, update: Partial<SourceUrlCandidateReviewLayoutColumn>) {
    const nextColumns = columns.map((column, columnIndex) =>
      columnIndex === index ? { ...column, ...update } : column,
    );
    onChange({ ...layout, columns: nextColumns });
  }

  return (
    <details className="panel source-url-layout-card">
      <summary>
        <span>
          <strong>Table settings</strong>
          <small> Columns, order, and widths</small>
        </span>
      </summary>

      {error ? <p className="form-error">{error}</p> : null}
      <div className="source-url-layout-controls">
        {columns.map((column, index) => (
          <div className="source-url-layout-row" key={columnKey(column)}>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={isColumnVisible(column)}
                onChange={(event) =>
                  updateColumn(index, {
                    visible: event.target.checked,
                    table_column_visible: event.target.checked,
                  })
                }
              />
              <span>{columnLabel(column)}</span>
            </label>
            <div className="button-row">
              <button
                className="button secondary compact-button"
                type="button"
                disabled={index === 0}
                onClick={() => onChange({ ...layout, columns: moveColumn(columns, index, -1) })}
              >
                Up
              </button>
              <button
                className="button secondary compact-button"
                type="button"
                disabled={index === columns.length - 1}
                onClick={() => onChange({ ...layout, columns: moveColumn(columns, index, 1) })}
              >
                Down
              </button>
              <label className="source-url-width-field">
                <span>Width</span>
                <input
                  type="number"
                  min={72}
                  max={320}
                  step={8}
                  value={getColumnWidth(column)}
                  onChange={(event) =>
                    updateColumn(index, { width_px: Number(event.target.value) || 140 })
                  }
                />
              </label>
            </div>
          </div>
        ))}
      </div>
      <div className="button-row">
        <button className="button primary" type="button" disabled={isSaving} onClick={onSave}>
          {isSaving ? "Saving..." : "Save layout"}
        </button>
        <button className="button secondary" type="button" disabled={isSaving} onClick={onReset}>
          Reset layout
        </button>
      </div>
    </details>
  );
}

function getReviewActions(layout: SourceUrlCandidateReviewLayout, candidate: SourceUrlCandidate | null) {
  const candidateDrawer = isRecord(candidate?.drawer) ? candidate?.drawer : null;
  const candidateActions = Array.isArray(candidateDrawer?.review_actions)
    ? candidateDrawer.review_actions
    : [];
  const layoutActions = layout.drawer?.review_actions ?? [];
  const actions = candidateActions.length > 0 ? candidateActions : layoutActions;
  return actions.length > 0 ? actions : FALLBACK_REVIEW_ACTIONS;
}

function getActionDecision(action: SourceUrlCandidateReviewActionConfig): SourceUrlCandidateReviewDecision {
  return (action.decision ?? "needs_manual_review") as SourceUrlCandidateReviewDecision;
}

function getActionLabel(action: SourceUrlCandidateReviewActionConfig): string {
  return action.label ?? normalizeLabel(String(action.decision ?? "needs_manual_review"));
}

function actionRequiresUrl(action: SourceUrlCandidateReviewActionConfig): boolean {
  return action.requires_url === true ||
    action.requires_reviewed_url === true ||
    action.decision === "replace_url";
}

function actionButtonClass(action: SourceUrlCandidateReviewActionConfig): string {
  const decision = action.decision;
  if (action.style === "danger" || decision === "reject") {
    return "button danger";
  }
  if (action.style === "primary" || decision === "accept") {
    return "button primary";
  }
  return "button secondary";
}

function DetailDrawer({
  candidate,
  layout,
  isLoading,
  isPending,
  onClose,
  onReview,
}: {
  candidate: SourceUrlCandidate | null;
  layout: SourceUrlCandidateReviewLayout;
  isLoading: boolean;
  isPending: boolean;
  onClose: () => void;
  onReview: (
    candidate: SourceUrlCandidate,
    decision: SourceUrlCandidateReviewDecision,
    reviewedUrl: string,
    notes: string,
  ) => void;
}) {
  const [replacementUrl, setReplacementUrl] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    setReplacementUrl("");
    setNotes(candidate?.notes ?? "");
  }, [candidate?.id, candidate?.notes]);

  useEffect(() => {
    if (!candidate) {
      return undefined;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [candidate, onClose]);

  if (!candidate) {
    return null;
  }

  const evidence = candidate.evidence_json;
  const searchedQueries = candidate.searched_queries_json;
  const errorValue =
    getJsonSection(evidence, ["error", "error_message", "message", "error_code"]) ??
    getJsonSection(candidate, ["error", "error_message", "error_code"]);
  const reviewActions = getReviewActions(layout, candidate);

  return (
    <div className="source-url-drawer-backdrop" onMouseDown={onClose}>
      <section
        className="source-url-drawer source-url-candidate-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-url-candidate-drawer-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="source-url-drawer-header">
          <div>
            <p className="eyebrow">Review candidate</p>
            <h2 id="source-url-candidate-drawer-title">Vendor source candidate {candidate.id}</h2>
          </div>
          <button className="button secondary" type="button" onClick={onClose}>
            Close
          </button>
        </header>

        <div className="source-url-drawer-body">
          {isLoading ? <LoadingState label="Loading candidate details..." /> : null}

          <section className="candidate-detail-card">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Decision</p>
                <h3>Review actions</h3>
              </div>
              <span className={`status-badge ${statusClass(candidate.status)}`}>
                {normalizeLabel(candidate.status ?? null)}
              </span>
            </div>
            <label className="inline-field wide">
              <span>Replacement URL</span>
              <input
                type="url"
                value={replacementUrl}
                onChange={(event) => setReplacementUrl(event.target.value)}
                placeholder="https://example.com/product"
              />
            </label>
            <label className="inline-field wide">
              <span>Review notes</span>
              <textarea
                rows={3}
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
              />
            </label>
            <div className="button-row">
              {reviewActions.map((action) => {
                const decision = getActionDecision(action);
                return (
                  <button
                    className={actionButtonClass(action)}
                    type="button"
                    key={String(decision)}
                    disabled={isPending || (actionRequiresUrl(action) && replacementUrl.trim().length === 0)}
                    onClick={() => onReview(candidate, decision, replacementUrl, notes)}
                  >
                    {isPending ? "Submitting..." : getActionLabel(action)}
                  </button>
                );
              })}
            </div>
          </section>

          <dl className="source-url-product-summary candidate-product-summary">
            <div>
              <dt>Catalog product id</dt>
              <dd>{formatValue(candidate.catalog_product_id)}</dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd>{formatValue(candidate.model)}</dd>
            </div>
            <div>
              <dt>MPN</dt>
              <dd>{formatValue(candidate.mpn)}</dd>
            </div>
            <div>
              <dt>Manufacturer</dt>
              <dd>{formatValue(candidate.manufacturer)}</dd>
            </div>
            <div>
              <dt>Product</dt>
              <dd>{formatValue(candidate.product_name)}</dd>
            </div>
          </dl>

          <section className="candidate-detail-card">
            <h3>Candidate</h3>
            <dl className="candidate-detail-list">
              <div>
                <dt>Candidate URL</dt>
                <dd className="source-url-cell">
                  {candidate.candidate_url ? (
                    <a href={candidate.candidate_url} target="_blank" rel="noreferrer">
                      {candidate.candidate_url}
                    </a>
                  ) : (
                    "-"
                  )}
                </dd>
              </div>
              <div>
                <dt>Canonical URL</dt>
                <dd className="source-url-cell">{formatValue(candidate.canonical_url)}</dd>
              </div>
              <div>
                <dt>Title</dt>
                <dd>{formatValue(candidate.candidate_title)}</dd>
              </div>
              <div>
                <dt>Price</dt>
                <dd>{formatMoney(candidate.candidate_price)}</dd>
              </div>
              <div>
                <dt>Source name / domain</dt>
                <dd>{formatValue(candidate.source_name ?? candidate.source_domain)}</dd>
              </div>
              <div>
                <dt>Notes</dt>
                <dd>{formatValue(candidate.notes)}</dd>
              </div>
            </dl>
          </section>

          <section className="candidate-detail-card">
            <h3>Searched queries</h3>
            <JsonDetail value={searchedQueries} />
          </section>

          <section className="candidate-detail-card">
            <h3>Evidence</h3>
            <dl className="candidate-evidence-grid">
              <EvidenceSection
                title="MPN evidence"
                value={getJsonSection(evidence, ["mpn_evidence", "mpn", "mpn_match"])}
              />
              <EvidenceSection
                title="Model evidence"
                value={getJsonSection(evidence, ["model_evidence", "model", "model_match"])}
              />
              <EvidenceSection
                title="Brand evidence"
                value={getJsonSection(evidence, ["brand_evidence", "brand", "manufacturer"])}
              />
              <EvidenceSection
                title="Category evidence"
                value={getJsonSection(evidence, ["category_evidence", "category"])}
              />
              <EvidenceSection
                title="Price evidence"
                value={getJsonSection(evidence, ["price_evidence", "price"])}
              />
              <EvidenceSection
                title="Title similarity"
                value={getJsonSection(evidence, ["title_similarity", "similarity"])}
              />
              <EvidenceSection
                title="Title-only flag"
                value={getJsonSection(evidence, ["title_only", "title_only_match"])}
              />
              <EvidenceSection title="Error" value={errorValue} />
            </dl>
            <details className="candidate-raw-evidence">
              <summary>Raw evidence JSON</summary>
              <JsonDetail value={evidence} />
            </details>
          </section>
        </div>
      </section>
    </div>
  );
}

export function SourceUrlCandidatesPage() {
  const location = useLocation();
  const initialRunId = useMemo(() => new URLSearchParams(location.search).get("run_id") ?? "", []);
  const [filters, setFilters] = useState<CandidateFilters>({
    ...initialFilters,
    runId: initialRunId,
  });
  const [offset, setOffset] = useState(0);
  const [response, setResponse] = useState({
    items: [] as SourceUrlCandidate[],
    total: 0,
    limit: DEFAULT_LIMIT,
    offset: 0,
  });
  const [layout, setLayout] = useState<SourceUrlCandidateReviewLayout>(makeFallbackLayout());
  const [isLayoutSaving, setIsLayoutSaving] = useState(false);
  const [layoutError, setLayoutError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingCandidateId, setPendingCandidateId] = useState<string | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<SourceUrlCandidate | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const runId = new URLSearchParams(location.search).get("run_id") ?? "";
    if (!runId) {
      return;
    }

    setFilters((current) => (current.runId === runId ? current : { ...current, runId }));
    setOffset(0);
  }, [location.search]);

  const loadCandidates = useCallback(
    async (signal?: AbortSignal) => {
      setIsLoading(true);
      try {
        const nextResponse = await commerceClient.listSourceUrlCandidates(
          buildParams(filters, offset),
          signal,
        );
        if (signal?.aborted) {
          return;
        }
        setResponse(nextResponse);
        setError(null);
      } catch (loadError) {
        if (!signal?.aborted) {
          setResponse({ items: [], total: 0, limit: DEFAULT_LIMIT, offset });
          setError(getCommerceApiErrorMessage(loadError));
        }
      } finally {
        if (!signal?.aborted) {
          setIsLoading(false);
        }
      }
    },
    [filters, offset],
  );

  const loadLayout = useCallback(async (signal?: AbortSignal) => {
    try {
      const nextLayout = await commerceClient.getSourceUrlCandidateReviewLayout(
        REVIEW_LAYOUT_USER_KEY,
        signal,
      );
      if (!signal?.aborted) {
        setLayout({ ...nextLayout, columns: normalizeColumns(nextLayout.columns) });
        setLayoutError(null);
      }
    } catch (loadError) {
      if (!signal?.aborted) {
        setLayout(makeFallbackLayout());
        setLayoutError(getCommerceApiErrorMessage(loadError));
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadCandidates(controller.signal);
    return () => controller.abort();
  }, [loadCandidates]);

  useEffect(() => {
    const controller = new AbortController();
    void loadLayout(controller.signal);
    return () => controller.abort();
  }, [loadLayout]);

  const visibleCandidates = useMemo(
    () =>
      response.items.filter((candidate) => {
        const matchesMethod =
          filters.matchMethod.trim().length === 0 ||
          (candidate.match_method ?? "")
            .toLowerCase()
            .includes(filters.matchMethod.trim().toLowerCase());
        return matchesMethod && passesCreatedDateFilter(candidate, filters);
      }),
    [filters, response.items],
  );

  const tableColumns = useMemo(
    () => normalizeColumns(layout.columns).filter(isColumnVisible),
    [layout.columns],
  );
  const totalPages = Math.max(1, Math.ceil(response.total / DEFAULT_LIMIT));
  const currentPage = Math.floor(offset / DEFAULT_LIMIT) + 1;

  const setFilter = <Key extends keyof CandidateFilters>(key: Key, value: CandidateFilters[Key]) => {
    setFilters((current) => ({ ...current, [key]: value }));
    setOffset(0);
  };

  const updateCandidateInState = (updated: SourceUrlCandidate) => {
    setResponse((current) => ({
      ...current,
      items: current.items.map((item) => (candidateId(item) === candidateId(updated) ? updated : item)),
    }));
    setSelectedCandidate((current) =>
      current && candidateId(current) === candidateId(updated) ? { ...current, ...updated } : current,
    );
  };

  const saveLayout = async () => {
    setIsLayoutSaving(true);
    setLayoutError(null);
    try {
      const nextLayout = await commerceClient.updateSourceUrlCandidateReviewLayout({
        ...layout,
        user_key: layout.user_key ?? REVIEW_LAYOUT_USER_KEY,
        columns: normalizeColumns(layout.columns),
        actions: { ...(layout.actions ?? {}), table_column_visible: false, replacement: "drawer_panel" },
      });
      setLayout({ ...nextLayout, columns: normalizeColumns(nextLayout.columns) });
      setNotice("Review table layout saved.");
    } catch (saveError) {
      setLayoutError(getCommerceApiErrorMessage(saveError));
    } finally {
      setIsLayoutSaving(false);
    }
  };

  const resetLayout = async () => {
    setIsLayoutSaving(true);
    setLayoutError(null);
    try {
      const nextLayout = await commerceClient.resetSourceUrlCandidateReviewLayout(REVIEW_LAYOUT_USER_KEY);
      setLayout({ ...nextLayout, columns: normalizeColumns(nextLayout.columns) });
      setNotice("Review table layout reset.");
    } catch (resetError) {
      setLayoutError(getCommerceApiErrorMessage(resetError));
    } finally {
      setIsLayoutSaving(false);
    }
  };

  const openCandidateDrawer = async (candidate: SourceUrlCandidate) => {
    const id = candidateId(candidate);
    setSelectedCandidateId(id);
    setSelectedCandidate(candidate);
    setIsDetailLoading(true);
    setNotice(null);
    try {
      const detail = await commerceClient.getSourceUrlCandidate(candidate.id);
      setSelectedCandidate((current) =>
        current && candidateId(current) === id ? { ...current, ...detail } : current,
      );
    } catch (detailError) {
      setNotice(getCommerceApiErrorMessage(detailError));
    } finally {
      setIsDetailLoading(false);
    }
  };

  const reviewCandidate = async (
    candidate: SourceUrlCandidate,
    decision: SourceUrlCandidateReviewDecision,
    reviewedUrl: string,
    reviewNotes: string,
  ) => {
    const id = candidateId(candidate);
    if (decision === "replace_url" && reviewedUrl.trim().length === 0) {
      setNotice("Enter a corrected URL before replacing.");
      return;
    }

    setPendingCandidateId(id);
    setNotice(null);
    try {
      const updated = await commerceClient.reviewSourceUrlCandidate(candidate.id, {
        decision,
        reviewed_url: decision === "replace_url" ? reviewedUrl.trim() : null,
        review_notes: reviewNotes.trim() || null,
        reviewed_by: "operator",
      });
      updateCandidateInState(updated);
      setNotice(`Candidate ${id} marked ${normalizeLabel(updated.status)}.`);
    } catch (reviewError) {
      setNotice(getCommerceApiErrorMessage(reviewError));
    } finally {
      setPendingCandidateId(null);
    }
  };

  return (
    <div className="page-stack source-url-candidates-page">
      <header className="page-header">
        <p className="eyebrow">Vendor Sources</p>
        <h2>Vendor Source Candidate Review</h2>
        <p>Review discovered product URLs before explicit promotion into monitored source URLs.</p>
      </header>

      <LayoutSettingsCard
        layout={layout}
        error={layoutError}
        isSaving={isLayoutSaving}
        onChange={setLayout}
        onSave={() => void saveLayout()}
        onReset={() => void resetLayout()}
      />

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Filters</p>
            <h3>Candidate queue</h3>
          </div>
          <button className="button secondary" type="button" onClick={() => void loadCandidates()}>
            Refresh
          </button>
        </div>

        <div className="filter-grid source-url-candidate-filters">
          <label>
            Status
            <select
              value={filters.status}
              onChange={(event) => setFilter("status", event.target.value as CandidateFilters["status"])}
            >
              {REVIEW_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {normalizeLabel(status)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Candidate source name
            <input
              type="search"
              value={filters.sourceName}
              onChange={(event) => setFilter("sourceName", event.target.value)}
              placeholder="electronet, public, plaisio, kotsovolos"
              title="Filters candidate source_name/source_domain values from the vendor/source registry."
            />
          </label>
          <label>
            Run id filter
            <input
              type="search"
              value={filters.runId}
              onChange={(event) => setFilter("runId", event.target.value)}
            />
          </label>
          <label>
            Model
            <input
              type="search"
              value={filters.model}
              onChange={(event) => setFilter("model", event.target.value)}
            />
          </label>
          <label>
            Catalog product id
            <input
              type="search"
              value={filters.catalogProductId}
              onChange={(event) => setFilter("catalogProductId", event.target.value)}
            />
          </label>
          <label>
            Min confidence
            <input
              type="number"
              min={0}
              max={1}
              step={0.0001}
              value={filters.minConfidence}
              onChange={(event) => setFilter("minConfidence", event.target.value)}
            />
          </label>
          <label>
            Max confidence
            <input
              type="number"
              min={0}
              max={1}
              step={0.0001}
              value={filters.maxConfidence}
              onChange={(event) => setFilter("maxConfidence", event.target.value)}
            />
          </label>
          <label>
            Match method
            <input
              type="search"
              value={filters.matchMethod}
              onChange={(event) => setFilter("matchMethod", event.target.value)}
              placeholder="mpn, model, title"
            />
          </label>
          <label>
            Created from
            <input
              type="date"
              value={filters.createdFrom}
              onChange={(event) => setFilter("createdFrom", event.target.value)}
            />
          </label>
          <label>
            Created to
            <input
              type="date"
              value={filters.createdTo}
              onChange={(event) => setFilter("createdTo", event.target.value)}
            />
          </label>
        </div>

        <div className="toolbar">
          <p className="muted">
            Showing {visibleCandidates.length.toLocaleString()} of {response.total.toLocaleString()} candidates.
            Match method and created date are narrowed in the UI for the loaded page.
          </p>
          <button className="button secondary" type="button" onClick={() => setFilters(initialFilters)}>
            Reset filters
          </button>
        </div>

        {notice ? <p className="form-warning">{notice}</p> : null}
        {isLoading ? <LoadingState label="Loading vendor source candidates..." /> : null}
        {error ? <ErrorState message={error} onRetry={() => void loadCandidates()} /> : null}
        {!isLoading && !error && visibleCandidates.length === 0 ? (
          <EmptyState
            title="No vendor source candidates"
            message="There are no candidates for the active filters."
          />
        ) : null}

        {!isLoading && !error && visibleCandidates.length > 0 ? (
          <>
            <div className="table-wrap source-url-candidates-table-wrap">
              <table>
                <colgroup>
                  {tableColumns.map((column) => (
                    <col key={columnKey(column)} style={{ width: `${getColumnWidth(column)}px` }} />
                  ))}
                </colgroup>
                <thead>
                  <tr>
                    {tableColumns.map((column) => (
                      <th key={columnKey(column)}>{columnLabel(column)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visibleCandidates.map((candidate) => {
                    const id = candidateId(candidate);
                    const isSelected = selectedCandidateId === id;
                    return (
                      <tr
                        key={id}
                        className={isSelected ? "selected-row" : undefined}
                        onClick={(event) => {
                          if (!isInteractiveClick(event.target)) {
                            void openCandidateDrawer(candidate);
                          }
                        }}
                      >
                        {tableColumns.map((column) => {
                          const key = columnKey(column);
                          return (
                            <td key={key} className="source-url-candidate-cell">
                              <span className="source-url-candidate-cell-content">
                                {renderCandidateCell(candidate, key)}
                              </span>
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="pagination-row">
              <button
                className="button secondary"
                type="button"
                disabled={offset <= 0 || isLoading}
                onClick={() => setOffset((current) => Math.max(0, current - DEFAULT_LIMIT))}
              >
                Previous
              </button>
              <span className="muted">
                Page {currentPage} of {totalPages}
              </span>
              <button
                className="button secondary"
                type="button"
                disabled={offset + DEFAULT_LIMIT >= response.total || isLoading}
                onClick={() => setOffset((current) => current + DEFAULT_LIMIT)}
              >
                Next
              </button>
            </div>
          </>
        ) : null}
      </section>

      <DetailDrawer
        candidate={selectedCandidate}
        layout={layout}
        isLoading={isDetailLoading}
        isPending={Boolean(selectedCandidateId && pendingCandidateId === selectedCandidateId)}
        onClose={() => {
          setSelectedCandidate(null);
          setSelectedCandidateId(null);
        }}
        onReview={(candidate, decision, reviewedUrl, notes) =>
          void reviewCandidate(candidate, decision, reviewedUrl, notes)
        }
      />
    </div>
  );
}
