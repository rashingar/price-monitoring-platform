import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
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
  SkroutzNetworkCapturedEndpoint,
  SkroutzNetworkDiagnosticReport,
  SkroutzNetworkDiagnosticSummary,
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
  { key: "status", label: "Status", visible: true, table_column_visible: true, width_px: 112, order: 0 },
  { key: "confidence_score", label: "Confidence", visible: true, table_column_visible: true, width_px: 104, order: 1 },
  { key: "model", label: "Model", visible: true, table_column_visible: true, width_px: 96, order: 2 },
  { key: "mpn", label: "MPN", visible: true, table_column_visible: true, width_px: 110, order: 3 },
  { key: "manufacturer", label: "Manufacturer", visible: true, table_column_visible: true, width_px: 130, order: 4 },
  { key: "source_name", label: "Source", visible: true, table_column_visible: true, width_px: 116, order: 5 },
  { key: "candidate_price", label: "Candidate price", visible: true, table_column_visible: true, width_px: 116, order: 6 },
  { key: "own_price", label: "Own price", visible: true, table_column_visible: true, width_px: 104, order: 7 },
  { key: "candidate_title", label: "Candidate title", visible: true, table_column_visible: true, width_px: 250, order: 8 },
];

const FALLBACK_REVIEW_ACTIONS: SourceUrlCandidateReviewActionConfig[] = [
  { decision: "accept", label: "Accept", style: "primary" },
  { decision: "reject", label: "Reject", style: "danger" },
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

function isSkroutzCandidate(candidate: SourceUrlCandidate): boolean {
  const sourceName = String(candidate.source_name ?? "").toLowerCase();
  const domain = String(candidate.source_domain ?? "").toLowerCase();
  const url = String(candidate.candidate_url ?? candidate.canonical_url ?? "").toLowerCase();
  return sourceName === "skroutz" || domain.includes("skroutz.gr") || url.includes("skroutz.gr");
}

function diagnosticSourceUrlId(candidate: SourceUrlCandidate): string | number | null {
  const value = candidate.source_url_id;
  return typeof value === "string" || typeof value === "number" ? value : null;
}

function yesNo(value: unknown): string {
  return value === true ? "yes" : "no";
}

function endpointKeySummary(endpoint: SkroutzNetworkCapturedEndpoint): string {
  const summary = endpoint.json_summary;
  const keys = Array.isArray(summary?.top_level_keys) ? summary.top_level_keys : [];
  if (keys.length > 0) {
    return keys.slice(0, 6).join(", ");
  }

  if (Array.isArray(summary?.first_item_keys) && summary.first_item_keys.length > 0) {
    return `first item: ${summary.first_item_keys.slice(0, 6).join(", ")}`;
  }

  return formatValue(summary?.top_level_type);
}

function diagnosticTone(classification: string | null | undefined): string {
  switch (classification) {
    case "PRIMARY_CANDIDATE_PRODUCT_OFFERS":
      return "success";
    case "SECONDARY_CANDIDATE_SHOP_DETAILS":
      return "active";
    case "BLOCKED_OR_CHALLENGE":
      return "danger";
    default:
      return "neutral";
  }
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
  const sourceByKey = new Map(
    columns
      .filter((column) => columnKey(column).length > 0)
      .map((column) => [columnKey(column), column]),
  );
  const source = DEFAULT_COLUMNS.map((defaultColumn) => {
    const sourceColumn = sourceByKey.get(columnKey(defaultColumn));
    return sourceColumn
      ? {
          ...sourceColumn,
          key: columnKey(defaultColumn),
          label: defaultColumn.label,
          visible: typeof sourceColumn.visible === "boolean" ? sourceColumn.visible : true,
          table_column_visible:
            typeof sourceColumn.table_column_visible === "boolean" ? sourceColumn.table_column_visible : true,
          order: defaultColumn.order,
          width_px: typeof sourceColumn.width_px === "number" ? sourceColumn.width_px : defaultColumn.width_px,
        }
      : defaultColumn;
  });

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
    actions: { table_column_visible: false, replacement: "inline_panel" },
    review_panel: { mode: "inline_row", open_on: "row_single_click", review_actions: FALLBACK_REVIEW_ACTIONS },
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
    case "source_name":
      return formatValue(candidate.source_name);
    case "source_domain":
      return formatValue(candidate.source_domain);
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
  const candidateReviewPanel = isRecord(candidate?.review_panel) ? candidate?.review_panel : null;
  const candidateActions = Array.isArray(candidateReviewPanel?.review_actions)
    ? candidateReviewPanel.review_actions
    : [];
  const layoutActions = layout.review_panel?.review_actions ?? [];
  const actions = candidateActions.length > 0 ? candidateActions : layoutActions;
  return actions.length > 0 ? actions : FALLBACK_REVIEW_ACTIONS;
}

function getActionDecision(action: SourceUrlCandidateReviewActionConfig): SourceUrlCandidateReviewDecision {
  return (action.decision ?? "reject") as SourceUrlCandidateReviewDecision;
}

function getActionLabel(action: SourceUrlCandidateReviewActionConfig): string {
  return action.label ?? normalizeLabel(String(action.decision ?? "reject"));
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

function SkroutzNetworkDiagnosticPanel({ candidate }: { candidate: SourceUrlCandidate }) {
  const sourceUrlId = diagnosticSourceUrlId(candidate);
  const [summary, setSummary] = useState<SkroutzNetworkDiagnosticSummary | null>(null);
  const [detail, setDetail] = useState<SkroutzNetworkDiagnosticReport | null>(null);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSummary(null);
    setDetail(null);
    setExpandedIndex(null);
    setError(null);
    setIsRunning(false);
    setIsLoadingDetail(false);
  }, [candidate.id]);

  if (!isSkroutzCandidate(candidate)) {
    return null;
  }

  const runDiagnostic = async () => {
    if (sourceUrlId === null) {
      setError("This candidate is not linked to an active Skroutz source URL yet.");
      return;
    }

    setIsRunning(true);
    setError(null);
    setDetail(null);
    setExpandedIndex(null);
    try {
      const nextSummary = await commerceClient.runSkroutzNetworkDiagnostic(sourceUrlId, {
        headed: false,
        timeout_seconds: 60,
      });
      setSummary(nextSummary);
    } catch (diagnosticError) {
      setSummary(null);
      setError(getCommerceApiErrorMessage(diagnosticError));
    } finally {
      setIsRunning(false);
    }
  };

  const loadDetails = async () => {
    if (sourceUrlId === null) {
      return;
    }

    setIsLoadingDetail(true);
    setError(null);
    try {
      const report = await commerceClient.getLatestSkroutzNetworkDiagnostic(sourceUrlId);
      setDetail(report);
    } catch (detailError) {
      setError(getCommerceApiErrorMessage(detailError));
    } finally {
      setIsLoadingDetail(false);
    }
  };

  const activeSummary = summary ?? detail?.summary ?? null;
  const endpoints = detail?.captured_responses ?? [];
  const blocked = activeSummary?.blocked_or_challenge_detected === true;
  const noProductEndpoint = activeSummary && !activeSummary.best_product_data_endpoint && !activeSummary.product_data_candidate_url;

  return (
    <section className="candidate-detail-card skroutz-network-diagnostic-panel">
      <div className="section-heading compact-section-heading">
        <div>
          <p className="eyebrow">Skroutz</p>
          <h4>Browser network diagnostic</h4>
        </div>
        <button
          className="button secondary compact-button"
          type="button"
          disabled={isRunning || sourceUrlId === null}
          onClick={() => void runDiagnostic()}
        >
          {isRunning ? "Running..." : "Run browser diagnostic"}
        </button>
      </div>
      {sourceUrlId === null ? (
        <p className="form-warning">Diagnostics require an existing active Skroutz source URL.</p>
      ) : null}
      {error ? <p className="form-warning">{error}</p> : null}
      {activeSummary ? (
        <>
          <dl className="candidate-evidence-grid skroutz-diagnostic-summary-grid">
            <div>
              <dt>Best endpoint</dt>
              <dd>{formatValue(activeSummary.best_product_data_endpoint ?? activeSummary.product_data_candidate_url)}</dd>
            </div>
            <div>
              <dt>filter_products.json</dt>
              <dd>{yesNo(activeSummary.observed_filter_products_url)}</dd>
            </div>
            <div>
              <dt>shops_details.json</dt>
              <dd>{yesNo(activeSummary.observed_shops_details_url)}</dd>
            </div>
            <div>
              <dt>Captured</dt>
              <dd>{formatValue(activeSummary.captured_response_count)}</dd>
            </div>
          </dl>
          {blocked ? <p className="form-warning">Blocked or challenge-like response detected.</p> : null}
          {noProductEndpoint ? <p className="form-warning">No likely product or offer endpoint was found.</p> : null}
          {activeSummary.product_data_candidate_reason ? (
            <p className="muted">{activeSummary.product_data_candidate_reason}</p>
          ) : null}
          <button
            className="button secondary compact-button"
            type="button"
            disabled={isLoadingDetail || sourceUrlId === null}
            onClick={() => void loadDetails()}
          >
            {isLoadingDetail ? "Loading details..." : "View captured endpoint details"}
          </button>
        </>
      ) : null}
      {detail ? (
        <div className="table-wrap skroutz-diagnostic-table-wrap">
          <table>
            <thead>
              <tr>
                <th>classification</th>
                <th>status</th>
                <th>method</th>
                <th>URL</th>
                <th>content type</th>
                <th>body size</th>
                <th>derived</th>
                <th>JSON</th>
                <th>keys</th>
              </tr>
            </thead>
            <tbody>
              {endpoints.map((endpoint, index) => (
                <Fragment key={`${endpoint.url ?? "endpoint"}-${index}`}>
                  <tr>
                    <td>
                      <span className={`status-badge ${diagnosticTone(endpoint.classification)}`}>
                        {formatValue(endpoint.classification)}
                      </span>
                    </td>
                    <td>{formatValue(endpoint.status)}</td>
                    <td>{formatValue(endpoint.method)}</td>
                    <td className="source-url-candidate-cell">
                      <span className="source-url-candidate-cell-content">{formatValue(endpoint.url)}</span>
                    </td>
                    <td>{formatValue(endpoint.content_type)}</td>
                    <td>{formatValue(endpoint.body_size)}</td>
                    <td>{formatValue(endpoint.matched_derived_endpoint)}</td>
                    <td>{yesNo(endpoint.parsed_json_valid)}</td>
                    <td>
                      <button
                        className="button secondary compact-button"
                        type="button"
                        onClick={() => setExpandedIndex((current) => (current === index ? null : index))}
                      >
                        {endpointKeySummary(endpoint)}
                      </button>
                    </td>
                  </tr>
                  {expandedIndex === index ? (
                    <tr className="source-url-expanded-row">
                      <td colSpan={9}>
                        <dl className="candidate-evidence-grid">
                          <EvidenceSection title="Top-level keys" value={endpoint.json_summary?.top_level_keys ?? []} />
                          <EvidenceSection title="Body sample" value={endpoint.body_sample} />
                          <EvidenceSection title="Parse error" value={endpoint.json_parse_error} />
                        </dl>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

function CandidateReviewPanel({
  candidate,
  layout,
  isLoading,
  isPending,
  onReview,
}: {
  candidate: SourceUrlCandidate | null;
  layout: SourceUrlCandidateReviewLayout;
  isLoading: boolean;
  isPending: boolean;
  onReview: (
    candidate: SourceUrlCandidate,
    decision: SourceUrlCandidateReviewDecision,
    reviewedUrl: string,
    notes: string,
  ) => void;
}) {
  const [replacementUrl, setReplacementUrl] = useState("");
  const [isReplaceOpen, setIsReplaceOpen] = useState(false);
  const [isDebugOpen, setIsDebugOpen] = useState(false);

  useEffect(() => {
    setReplacementUrl("");
    setIsReplaceOpen(false);
    setIsDebugOpen(false);
  }, [candidate?.id, candidate?.notes]);

  if (!candidate) {
    return null;
  }

  const reviewActions = getReviewActions(layout, candidate);
  const acceptAction = reviewActions.find((action) => getActionDecision(action) === "accept");
  const rejectAction = reviewActions.find((action) => getActionDecision(action) === "reject");
  const replaceAction = reviewActions.find((action) => getActionDecision(action) === "replace_url");
  const reviewNotes = typeof candidate.notes === "string" ? candidate.notes : "";
  const evidence = candidate.evidence_json;
  const searchedQueries = candidate.searched_queries_json;
  const errorValue =
    getJsonSection(evidence, ["error", "error_message", "message", "error_code"]) ??
    getJsonSection(candidate, ["error", "error_message", "error_code"]);

  return (
    <section
      className="source-url-inline-review-panel"
      role="region"
      aria-label={`Vendor source candidate ${candidate.id} review`}
    >
      {isLoading ? <LoadingState label="Loading candidate details..." /> : null}

      <div className="source-url-inline-review-grid">
        <section className="candidate-detail-card source-url-review-decision-card">
          <div className="button-row source-url-review-actions">
            {candidate.candidate_url ? (
              <a
                className="button secondary"
                href={candidate.candidate_url}
                target="_blank"
                rel="noreferrer noopener"
              >
                Open candidate URL
              </a>
            ) : null}
            {acceptAction ? (
              <button
                className={actionButtonClass(acceptAction)}
                type="button"
                disabled={isPending}
                onClick={() => onReview(candidate, "accept", "", reviewNotes)}
              >
                {isPending ? "Submitting..." : getActionLabel(acceptAction)}
              </button>
            ) : null}
            {rejectAction ? (
              <button
                className={actionButtonClass(rejectAction)}
                type="button"
                disabled={isPending}
                onClick={() => onReview(candidate, "reject", "", reviewNotes)}
              >
                {isPending ? "Submitting..." : getActionLabel(rejectAction)}
              </button>
            ) : null}
            {replaceAction ? (
              <button
                className="button secondary"
                type="button"
                aria-expanded={isReplaceOpen}
                onClick={() => setIsReplaceOpen((current) => !current)}
              >
                {getActionLabel(replaceAction)}
              </button>
            ) : null}
            <button
              className="button secondary"
              type="button"
              aria-expanded={isDebugOpen}
              onClick={() => setIsDebugOpen((current) => !current)}
            >
              Debug
            </button>
          </div>
          {isReplaceOpen && replaceAction ? (
            <div className="source-url-replace-inline-row">
              <label className="inline-field wide">
                <span>Replacement URL</span>
                <input
                  type="url"
                  value={replacementUrl}
                  onChange={(event) => setReplacementUrl(event.target.value)}
                  placeholder="https://example.com/product"
                />
              </label>
              <button
                className="button secondary"
                type="button"
                disabled={isPending || (actionRequiresUrl(replaceAction) && replacementUrl.trim().length === 0)}
                onClick={() => onReview(candidate, "replace_url", replacementUrl, reviewNotes)}
              >
                {isPending ? "Submitting..." : "Submit replacement"}
              </button>
            </div>
          ) : null}
          {isDebugOpen ? (
            <div className="source-url-debug-panel">
              <dl className="candidate-detail-list source-url-debug-detail-list">
                <div>
                  <dt>Status</dt>
                  <dd>
                    <span className={`status-badge ${statusClass(candidate.status)}`}>
                      {normalizeLabel(candidate.status ?? null)}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>Candidate URL</dt>
                  <dd className="source-url-cell">{formatValue(candidate.candidate_url)}</dd>
                </div>
                <div>
                  <dt>Canonical URL</dt>
                  <dd className="source-url-cell">{formatValue(candidate.canonical_url)}</dd>
                </div>
                <div>
                  <dt>Review notes</dt>
                  <dd>{formatValue(candidate.notes)}</dd>
                </div>
                <div>
                  <dt>Match method</dt>
                  <dd>{formatValue(candidate.match_method)}</dd>
                </div>
                <div>
                  <dt>Confidence</dt>
                  <dd>{formatConfidence(candidate.confidence_score)}</dd>
                </div>
                <div>
                  <dt>Created</dt>
                  <dd>{formatDate(candidate.created_at)}</dd>
                </div>
                <div>
                  <dt>Run id</dt>
                  <dd>{formatValue(candidate.run_id)}</dd>
                </div>
                <div>
                  <dt>Source candidate id</dt>
                  <dd>{formatValue(candidate.id)}</dd>
                </div>
              </dl>
              <section className="source-url-debug-json-section">
                <h4>Searched queries</h4>
                <JsonDetail value={searchedQueries} />
              </section>
              <section className="source-url-debug-json-section">
                <h4>Matching details</h4>
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
              </section>
              <section className="source-url-debug-json-section">
                <h4>Raw evidence JSON</h4>
                <JsonDetail value={evidence} />
              </section>
            </div>
          ) : null}
        </section>
        <SkroutzNetworkDiagnosticPanel candidate={candidate} />
      </div>
    </section>
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
        actions: { ...(layout.actions ?? {}), table_column_visible: false, replacement: "inline_panel" },
        review_panel: { ...(layout.review_panel ?? {}), mode: "inline_row", open_on: "row_single_click" },
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

  const toggleCandidateReview = async (candidate: SourceUrlCandidate) => {
    const id = candidateId(candidate);
    if (selectedCandidateId === id) {
      setSelectedCandidateId(null);
      setSelectedCandidate(null);
      setIsDetailLoading(false);
      return;
    }

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
            Review status
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
                      <Fragment key={id}>
                        <tr
                          className={isSelected ? "selected-row" : undefined}
                          aria-expanded={isSelected}
                          onClick={(event) => {
                            if (!isInteractiveClick(event.target)) {
                              void toggleCandidateReview(candidate);
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
                        {isSelected ? (
                          <tr className="source-url-expanded-row">
                            <td colSpan={tableColumns.length}>
                              <CandidateReviewPanel
                                candidate={selectedCandidate}
                                layout={layout}
                                isLoading={isDetailLoading}
                                isPending={pendingCandidateId === id}
                                onReview={(reviewCandidateValue, decision, reviewedUrl, notes) =>
                                  void reviewCandidate(reviewCandidateValue, decision, reviewedUrl, notes)
                                }
                              />
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
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

    </div>
  );
}
