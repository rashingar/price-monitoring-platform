import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  CommerceApiError,
  commerceClient,
  getArtifactPath,
  getCommerceApiErrorMessage,
} from "../api/commerceClient";
import type {
  ApplyPriceMonitoringReviewActionsResult,
  ArtifactItem,
  ArtifactPayload,
  ArtifactRoot,
  CatalogBrandOption,
  CatalogCategoryHierarchyResponse,
  CatalogSnapshot,
  CatalogSnapshotResponse,
  ExportPriceMonitoringPriceUpdateResult,
  FetchPriceMonitoringResult,
  MarketplaceFilter,
  PathRootsResponse,
  PriceMonitoringDbStatus,
  PriceMonitoringFetchLogsResponse,
  PriceObservation,
  PriceObservationMatchStatus,
  PriceMonitoringAction,
  PriceMonitoringReviewAction,
  PriceMonitoringReviewItem,
  PriceMonitoringReviewResponse,
  PriceMonitoringRun,
  PriceMonitoringSelectionBody,
  PriceMonitoringSelectionItem,
  PriceMonitoringSelectionResult,
  PriceMonitoringSourceUrlCoverage,
  PriceMonitoringSource,
  RunPriceObservationsResponse,
  VendorSourceCapability,
} from "../api/commerceTypes";
import {
  initialPriceMonitoringWorkflowState,
  PRICE_MONITORING_STATE_KEY,
  shouldTreatArtifactsAsDiagnostic,
  type PriceMonitoringWorkflowState,
} from "../api/priceMonitoringUtils";
import { ArtifactList } from "../components/ArtifactList";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";
import {
  isPriceMonitoringDbAvailable,
  PriceMonitoringDbStatusBanner,
} from "../components/priceMonitoring/PriceMonitoringDbStatusBanner";
import { getPriceMonitoringDbBlockingMessage } from "../api/priceMonitoringDbGate";
import { usePersistentPageState } from "../hooks/usePersistentPageState";
import {
  CATEGORY_HIERARCHY_UNAVAILABLE_MESSAGE,
  formatHierarchyOptionLabel,
  getCategoryOptions,
  getFamilyOptions,
  getSubCategoryOptions,
  makeHierarchyFilterParams,
} from "../utils/categoryHierarchy";

type SourceOverride = "" | PriceMonitoringSource;
type PriceMonitoringSourceFilter = string;
type StoredObservationMatchFilter = "all" | PriceObservationMatchStatus;
const SOURCE_REQUIRED_MESSAGE = "Choose one source/vendor to monitor.";

function normalizeFetchStatus(status: unknown): string {
  if (typeof status !== "string" || status.trim().length === 0) {
    return "";
  }

  if (status === "fetch_completed") {
    return "succeeded";
  }

  if (status === "fetch_failed") {
    return "failed";
  }

  return status.trim().toLowerCase();
}

function isActiveFetchStatus(status: unknown): boolean {
  const normalized = normalizeFetchStatus(status);
  return normalized === "queued" || normalized === "running";
}

function isSuccessfulFetchStatus(status: unknown): boolean {
  return normalizeFetchStatus(status) === "succeeded";
}

function isFailedFetchStatus(status: unknown): boolean {
  const normalized = normalizeFetchStatus(status);
  return normalized === "failed" || normalized === "killed";
}

function isCancelledFetchStatus(status: unknown): boolean {
  return normalizeFetchStatus(status) === "cancelled";
}

function isTerminalFetchStatus(status: unknown): boolean {
  return (
    isSuccessfulFetchStatus(status) ||
    isFailedFetchStatus(status) ||
    isCancelledFetchStatus(status)
  );
}

function getFetchStatusTone(status: unknown): string {
  const normalized = normalizeFetchStatus(status);
  if (normalized === "queued" || normalized === "running") {
    return "active";
  }

  if (normalized === "succeeded") {
    return "ok";
  }

  if (normalized === "failed" || normalized === "killed") {
    return "danger";
  }

  if (normalized === "cancelled") {
    return "warning";
  }

  return "neutral";
}

function formatFetchStatus(status: unknown): string {
  const normalized = normalizeFetchStatus(status);
  if (!normalized) {
    return "-";
  }

  return normalized.replace(/_/g, " ").replace(/^\w/, (first) => first.toUpperCase());
}

interface RowActionState {
  selected_action: "" | PriceMonitoringAction;
  undercut_amount: string;
  reason: string;
}

function formatValue(value: unknown): string {
  if (isRecord(value) && typeof value.path === "string") {
    return value.path;
  }

  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return String(value);
}

function parseNumberLike(value: unknown): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }

  if (typeof value !== "string") {
    return null;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatNumber(value: unknown): string {
  const parsed = parseNumberLike(value);
  if (parsed === null) {
    return "-";
  }

  return parsed.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatMoney(value: unknown, currency = "EUR"): string {
  const parsed = parseNumberLike(value);
  if (parsed === null) {
    return "-";
  }

  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(parsed);
}

function parseModelText(value: string): string[] {
  return value
    .split(/[\n,]+/)
    .map((model) => model.trim())
    .filter((model) => model.length > 0);
}

function isAction(value: unknown): value is PriceMonitoringAction {
  return value === "match_price" || value === "undercut" || value === "ignore";
}

function makeSelectionBody({
  source,
  q,
  family,
  categoryName,
  subCategory,
  manufacturer,
  marketplace,
  selectedModelText,
  excludedModelText,
  includeIgnored,
  automationEligibleOnly,
  atomicOnly,
  hasMpn,
  dryRun,
}: {
  source: PriceMonitoringSourceFilter;
  q: string;
  family: string;
  categoryName: string;
  subCategory: string;
  manufacturer: string;
  marketplace: MarketplaceFilter;
  selectedModelText: string;
  excludedModelText: string;
  includeIgnored: boolean;
  automationEligibleOnly: boolean;
  atomicOnly: boolean;
  hasMpn: boolean;
  dryRun: boolean;
}): PriceMonitoringSelectionBody {
  const trimmedQ = q.trim();
  const sourceName = source.trim();

  return {
    source: sourceName,
    source_name: sourceName,
    source_filter: sourceName,
    filters: {
      q: trimmedQ.length > 0 ? trimmedQ : null,
      ...makeHierarchyFilterParams({ family, categoryName, subCategory }),
      manufacturer: manufacturer || null,
      marketplace: marketplace === "all" ? null : marketplace,
      has_mpn: hasMpn,
      atomic_only: atomicOnly,
      automation_eligible_only: automationEligibleOnly,
    },
    selected_models: parseModelText(selectedModelText),
    excluded_models: parseModelText(excludedModelText),
    include_ignored: includeIgnored,
    dry_run: dryRun,
  };
}

function getCategoryHierarchyErrorMessage(error: unknown): string {
  return error instanceof CommerceApiError && error.status === 404
    ? CATEGORY_HIERARCHY_UNAVAILABLE_MESSAGE
    : getCommerceApiErrorMessage(error);
}

function formatOptionCount(count: number | null | undefined): string {
  return typeof count === "number" && Number.isFinite(count) ? ` (${count})` : "";
}

function dedupeVendorSources(sources: VendorSourceCapability[]): VendorSourceCapability[] {
  const seen = new Set<string>();
  return sources.filter((source) => {
    const sourceName = String(source.source_name).trim();
    if (!sourceName) {
      return false;
    }

    const key = sourceName.toLowerCase();
    if (seen.has(key)) {
      return false;
    }

    seen.add(key);
    return true;
  });
}

function formatSourceOptionLabel(source: VendorSourceCapability): string {
  const sourceName = String(source.source_name);
  const vendorSlug = typeof source.vendor_slug === "string" ? source.vendor_slug : null;
  const sourceType = typeof source.source_type === "string" ? source.source_type.replace(/_/g, " ") : null;
  return [sourceName, vendorSlug, sourceType].filter(Boolean).join(" - ");
}

function normalizeSelectedSource(value: string | null | undefined): string {
  const sourceName = typeof value === "string" ? value.trim() : "";
  return sourceName && sourceName.toLowerCase() !== "all" ? sourceName : "";
}

function formatSelectedSource(value: unknown): string {
  const sourceName = typeof value === "string" ? value.trim() : "";
  return sourceName && sourceName.toLowerCase() !== "all" ? sourceName : "-";
}

interface SelectionHierarchyFilters {
  family?: string | null;
  category_name?: string | null;
  sub_category?: string | null;
  category?: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asStringFilter(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function getRecordValue(source: unknown, key: string): unknown {
  return isRecord(source) ? source[key] : undefined;
}

function parseRecord(value: unknown): Record<string, unknown> | null {
  if (isRecord(value)) {
    return value;
  }

  if (typeof value !== "string" || value.trim().length === 0) {
    return null;
  }

  try {
    const parsed = JSON.parse(value) as unknown;
    return isRecord(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function extractSelectionFilters(
  run: PriceMonitoringRun | PriceMonitoringSelectionResult,
): SelectionHierarchyFilters {
  const directFilters = parseRecord(getRecordValue(run, "filters"));
  const selectionSummary = parseRecord(getRecordValue(run, "selection_summary"));
  const summaryFilters = parseRecord(getRecordValue(selectionSummary, "filters"));
  const selectionSummaryJson = parseRecord(getRecordValue(run, "selection_summary_json"));
  const jsonFilters = parseRecord(getRecordValue(selectionSummaryJson, "filters"));
  const filters = summaryFilters
    ? summaryFilters
    : jsonFilters
      ? jsonFilters
      : directFilters
        ? directFilters
        : {};

  return {
    family: asStringFilter(filters.family),
    category_name: asStringFilter(filters.category_name),
    sub_category: asStringFilter(filters.sub_category),
    category: asStringFilter(filters.category),
  };
}

function HierarchyFilterSummary({
  filters,
}: {
  filters: SelectionHierarchyFilters;
}) {
  return (
    <div className="compact-list">
      <strong>Hierarchy filters</strong>
      <dl className="summary-grid">
        <SummaryItem label="Family" value={filters.family || "All"} />
        <SummaryItem label="Category" value={filters.category_name || "All"} />
        <SummaryItem label="Sub-Category" value={filters.sub_category || "All"} />
      </dl>
      {!filters.family && !filters.category_name && !filters.sub_category && filters.category ? (
        <p className="muted">Raw category: {filters.category}</p>
      ) : null}
    </div>
  );
}

function getRunId(run: PriceMonitoringRun | PriceMonitoringSelectionResult | null): string {
  const value = run && ("run_id" in run ? run.run_id : null);
  return value === null || value === undefined ? "" : String(value);
}

function getSelectedItems(result: PriceMonitoringSelectionResult): PriceMonitoringSelectionItem[] {
  return result.selected_items ?? result.selected ?? [];
}

function getSkippedItems(result: PriceMonitoringSelectionResult): PriceMonitoringSelectionItem[] {
  return result.skipped_items ?? [];
}

function getPriorObservationCount(result: FetchPriceMonitoringResult | null | undefined): number | undefined {
  return result?.prior_observation_count ?? result?.retained_observation_count ?? result?.replaced_observation_count;
}

function formatPercent(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(1)}%` : formatValue(value);
}

function hasCoverageDetails(coverage: PriceMonitoringSourceUrlCoverage | null | undefined): boolean {
  return Boolean(
    coverage &&
      (coverage.products_with_active_source_urls !== undefined ||
        coverage.products_without_active_source_urls !== undefined ||
        coverage.active_source_url_count !== undefined ||
        coverage.warning),
  );
}

function getSourceUrlStatusCounts(
  coverage: PriceMonitoringSourceUrlCoverage | null | undefined,
): Record<string, number> {
  return {
    active: coverage?.active_source_url_count ?? coverage?.status_counts?.active ?? 0,
    needs_review: coverage?.needs_review_source_url_count ?? coverage?.status_counts?.needs_review ?? 0,
    broken: coverage?.broken_source_url_count ?? coverage?.status_counts?.broken ?? 0,
    disabled: coverage?.disabled_source_url_count ?? coverage?.status_counts?.disabled ?? 0,
    redirected: coverage?.redirected_source_url_count ?? coverage?.status_counts?.redirected ?? 0,
  };
}

function formatSourceUrlStatusCounts(coverage: PriceMonitoringSourceUrlCoverage | null | undefined): string {
  const counts = getSourceUrlStatusCounts(coverage);
  return Object.entries(counts)
    .filter(([, count]) => count > 0)
    .map(([status, count]) => `${status.replace(/_/g, " ")}: ${count}`)
    .join(", ") || "-";
}

function getActiveSourceUrlCount(coverage: PriceMonitoringSourceUrlCoverage | null | undefined): number {
  return coverage?.active_source_url_count ?? coverage?.status_counts?.active ?? 0;
}

function isSourceUrlEligible(coverage: PriceMonitoringSourceUrlCoverage | null | undefined): boolean {
  if (coverage?.has_active_source_url === true) {
    return true;
  }

  if (coverage?.has_active_source_url === false) {
    return false;
  }

  return getActiveSourceUrlCount(coverage) > 0;
}

function getMissingActiveSourceUrlSkipCount(result: PriceMonitoringSelectionResult): number {
  const byReason = result.skipped_by_reason ?? {};
  const skippedReasons = isRecord(result.skipped_reasons) ? result.skipped_reasons : {};
  const value =
    byReason.missing_active_source_url ??
    byReason.no_active_source_url ??
    skippedReasons.missing_active_source_url ??
    skippedReasons.no_active_source_url;
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function resultHasMissingActiveSourceUrls(result: PriceMonitoringSelectionResult): boolean {
  return (
    getMissingActiveSourceUrlSkipCount(result) > 0 ||
    (result.source_url_coverage?.products_without_active_source_urls ?? 0) > 0 ||
    getSkippedItems(result).some((item) =>
      String(item.skip_reason ?? item.reason ?? "").includes("missing_active_source_url"),
    )
  );
}

function resultHasNoMonitorableProducts(result: PriceMonitoringSelectionResult): boolean {
  return (
    (result.selected_count ?? getSelectedItems(result).length) === 0 &&
    ((result.skipped_count ?? getSkippedItems(result).length) > 0 || resultHasMissingActiveSourceUrls(result))
  );
}

function sanitizeSourceUrlWarning(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  const normalized = value.toLowerCase();
  if (normalized.includes("fallback") || normalized.includes("fall back") || normalized.includes("source search")) {
    return "Products without active source URLs are not eligible for Price Monitoring.";
  }

  return value;
}

function getSourceRequirementErrorMessage(error: unknown): string | null {
  if (!(error instanceof CommerceApiError) || error.status !== 400) {
    return null;
  }

  const details = isRecord(error.details) ? error.details : {};
  const detailText = [
    details.code,
    details.reason,
    details.detail,
    details.message,
    error.message,
  ]
    .filter((value): value is string => typeof value === "string")
    .join(" ")
    .toLowerCase();

  return detailText.includes("source") &&
    (detailText.includes("required") ||
      detailText.includes("missing") ||
      detailText.includes("all") ||
      detailText.includes("one"))
    ? SOURCE_REQUIRED_MESSAGE
    : null;
}

function getMissingActiveSourceUrlErrorMessage(error: unknown, selectedSource: string): string | null {
  if (!(error instanceof CommerceApiError)) {
    return null;
  }

  const details = isRecord(error.details) ? error.details : {};
  const detailText = [
    details.code,
    details.reason,
    details.detail,
    details.message,
    error.message,
  ]
    .filter((value): value is string => typeof value === "string")
    .join(" ")
    .toLowerCase();
  const skippedByReason = isRecord(details.skipped_by_reason) ? details.skipped_by_reason : {};
  const skippedReasons = isRecord(details.skipped_reasons) ? details.skipped_reasons : {};
  const hasMissingReason =
    detailText.includes("missing_active_source_url") ||
    detailText.includes("active source url") ||
    skippedByReason.missing_active_source_url !== undefined ||
    skippedReasons.missing_active_source_url !== undefined;

  if (!hasMissingReason) {
    return null;
  }

  const detailsSource =
    normalizeSelectedSource(
      String(details.source ?? details.source_name ?? details.source_filter ?? ""),
    ) || selectedSource;
  return detailsSource
    ? `This product cannot be monitored until it has an active URL for ${detailsSource}.`
    : "This product cannot be monitored until it has an active URL for the selected source/vendor.";
}

function VendorSourcesActionLink() {
  return (
    <p className="button-row">
      <Link className="button secondary" to="/vendor-sources/source-urls">
        Create/review source URLs in Vendor Sources
      </Link>
      <Link className="button secondary" to="/vendor-sources/runs">
        Run Vendor Sources discovery
      </Link>
    </p>
  );
}

function NoMonitorableProductsActionCard({ source }: { source?: string | null }) {
  const selectedSource = normalizeSelectedSource(source ?? "");
  return (
    <div className="state-block">
      <strong>No products can be monitored until active source URLs exist.</strong>
      <p className="form-error">
        {selectedSource
          ? `This product cannot be monitored until it has an active URL for ${selectedSource}.`
          : "This product cannot be monitored until it has an active URL for the selected source/vendor."}
      </p>
      <VendorSourcesActionLink />
    </div>
  );
}

function SourceUrlCoverageSummary({
  coverage,
}: {
  coverage: PriceMonitoringSourceUrlCoverage | null | undefined;
}) {
  if (!hasCoverageDetails(coverage)) {
    return null;
  }

  return (
    <div className="compact-list">
      <strong>Monitoring URL eligibility</strong>
      <dl className="summary-grid">
        <SummaryItem label="Source/vendor" value={formatSelectedSource(coverage?.source)} />
        <SummaryItem label="Products with active URLs" value={coverage?.products_with_active_source_urls} />
        <SummaryItem label="Products without active URLs" value={coverage?.products_without_active_source_urls} />
        <SummaryItem label="Eligibility" value={formatPercent(coverage?.coverage_percent)} />
        <SummaryItem label="Active URLs" value={coverage?.active_source_url_count} />
        <SummaryItem label="Needs review URLs" value={coverage?.needs_review_source_url_count} />
        <SummaryItem label="Broken URLs" value={coverage?.broken_source_url_count} />
        <SummaryItem label="Disabled URLs" value={coverage?.disabled_source_url_count} />
      </dl>
      {sanitizeSourceUrlWarning(coverage?.warning) ? (
        <p className="form-warning">{sanitizeSourceUrlWarning(coverage?.warning)}</p>
      ) : null}
      {coverage?.missing_source_url_models && coverage.missing_source_url_models.length > 0 ? (
        <>
          <p className="form-warning">
            Missing active source URLs: {coverage.missing_source_url_models.join(", ")}
          </p>
          <VendorSourcesActionLink />
        </>
      ) : null}
    </div>
  );
}

function SourceUrlEligibilityRows({
  items,
  title,
  emptyMessage,
  showReason = false,
}: {
  items: PriceMonitoringSelectionItem[];
  title: string;
  emptyMessage?: string;
  showReason?: boolean;
}) {
  if (items.length === 0) {
    return emptyMessage ? <p className="muted">{emptyMessage}</p> : null;
  }

  return (
    <div className="compact-list">
      <strong>{title}</strong>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th>Name</th>
              <th>MPN</th>
              <th>Family</th>
              <th>Category</th>
              <th>Sub-Category</th>
              <th>Manufacturer</th>
              <th>Source/vendor</th>
              <th>Active source URLs</th>
              <th>Source URL status counts</th>
              <th>Monitoring eligibility</th>
              {showReason ? <th>Skip reason</th> : null}
            </tr>
          </thead>
          <tbody>
            {items.slice(0, 25).map((item, index) => {
              const activeUrlCount = getActiveSourceUrlCount(item.source_url_coverage);
              const eligible = isSourceUrlEligible(item.source_url_coverage);
              return (
                <tr key={`${item.model ?? "item"}-${index}`}>
                  <td>{formatValue(item.model)}</td>
                  <td>{formatValue(item.name)}</td>
                  <td>{formatValue(item.mpn)}</td>
                  <td>{formatValue(item.family)}</td>
                  <td>{formatValue(item.category_name)}</td>
                  <td>{formatValue(item.sub_category)}</td>
                  <td>{formatValue(item.manufacturer)}</td>
                  <td>{formatSelectedSource(item.source_url_coverage?.source)}</td>
                  <td>{formatValue(activeUrlCount)}</td>
                  <td>{formatSourceUrlStatusCounts(item.source_url_coverage)}</td>
                  <td>
                    <span className={`status-badge ${eligible ? "ok" : "danger"}`}>
                      {eligible ? "Monitorable" : "Not monitorable"}
                    </span>
                  </td>
                  {showReason ? (
                    <td>{formatValue(item.skip_reason ?? item.reason ?? "missing_active_source_url")}</td>
                  ) : null}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {items.length > 25 ? (
        <p className="muted">Showing 25 of {items.length} returned products.</p>
      ) : null}
    </div>
  );
}

function getActionState(
  row: PriceMonitoringReviewItem,
  actionState: Record<string, RowActionState>,
): RowActionState {
  return (
    actionState[row.model] ?? {
      selected_action: isAction(row.selected_action) ? row.selected_action : "",
      undercut_amount:
        typeof row.undercut_amount === "number" && Number.isFinite(row.undercut_amount)
          ? String(row.undercut_amount)
          : "",
      reason: "",
    }
  );
}

function computeTargetPrice(row: PriceMonitoringReviewItem, state: RowActionState): number | null {
  if (state.selected_action === "match_price") {
    return typeof row.competitor_price === "number" ? row.competitor_price : null;
  }

  if (state.selected_action === "undercut") {
    const undercutAmount = Number(state.undercut_amount);
    return typeof row.competitor_price === "number" &&
      Number.isFinite(row.competitor_price) &&
      Number.isFinite(undercutAmount)
      ? row.competitor_price - undercutAmount
      : null;
  }

  return typeof row.target_price === "number" ? row.target_price : null;
}

function getActionError(row: PriceMonitoringReviewItem, state: RowActionState): string | null {
  if (state.selected_action === "") {
    return null;
  }

  if (state.selected_action === "ignore") {
    return null;
  }

  if (typeof row.competitor_price !== "number" || !Number.isFinite(row.competitor_price)) {
    return "Competitor price is required.";
  }

  if (state.selected_action === "undercut") {
    const undercutAmount = Number(state.undercut_amount);
    if (!Number.isFinite(undercutAmount) || undercutAmount <= 0) {
      return "Undercut amount must be greater than 0.";
    }
  }

  return null;
}

function SelectionResultBlock({
  result,
  filters,
}: {
  result: PriceMonitoringSelectionResult;
  filters?: SelectionHierarchyFilters | null;
}) {
  const selectedItems = getSelectedItems(result);
  const skippedItems = getSkippedItems(result);
  const hierarchyFilters = filters ?? extractSelectionFilters(result);
  const missingActiveSourceUrlSkipCount = getMissingActiveSourceUrlSkipCount(result);
  const hasMissingActiveSourceUrls = resultHasMissingActiveSourceUrls(result);
  const hasNoMonitorableProducts = resultHasNoMonitorableProducts(result);

  return (
    <div className="state-block">
      <strong>Selection result</strong>
      <dl className="summary-grid">
        <SummaryItem label="Run ID" value={result.run_id} />
        <SummaryItem label="Status" value={result.status} />
        <SummaryItem label="Source/vendor" value={formatSelectedSource(result.source)} />
        <SummaryItem label="Output dir" value={result.output_dir} />
        <SummaryItem label="Input CSV" value={result.input_csv_path} />
        <SummaryItem label="Selection summary" value={result.selection_summary_path} />
        <SummaryItem label="Selected" value={result.selected_count} />
        <SummaryItem label="Skipped" value={result.skipped_count} />
        <SummaryItem label="Skipped missing active URL" value={missingActiveSourceUrlSkipCount} />
      </dl>

      <HierarchyFilterSummary filters={hierarchyFilters} />
      <SourceUrlCoverageSummary coverage={result.source_url_coverage} />

      {hasNoMonitorableProducts ? (
        <NoMonitorableProductsActionCard source={formatSelectedSource(result.source)} />
      ) : hasMissingActiveSourceUrls ? (
        <div className="compact-list">
          <p className="form-warning">
            Products missing active source URLs were skipped. Price Monitoring consumes only
            existing active source URLs.
          </p>
          <VendorSourcesActionLink />
        </div>
      ) : null}

      {result.skipped_by_reason && Object.keys(result.skipped_by_reason).length > 0 ? (
        <div className="compact-list">
          <strong>Skipped by reason</strong>
          <ul>
            {Object.entries(result.skipped_by_reason).map(([reason, count]) => (
              <li key={reason}>
                {reason}: {count}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <SourceUrlEligibilityRows
        title="Monitorable products"
        items={selectedItems}
        emptyMessage="No products with active source URLs were selected."
      />
      <SourceUrlEligibilityRows
        title="Skipped products"
        items={skippedItems}
        showReason
      />
    </div>
  );
}

function RunSummaryBlock({
  run,
  filters,
}: {
  run: PriceMonitoringRun | PriceMonitoringSelectionResult;
  filters?: SelectionHierarchyFilters | null;
}) {
  const hierarchyFilters = filters ?? extractSelectionFilters(run);
  const latestFetch = isRecord(run.latest_fetch) ? (run.latest_fetch as FetchPriceMonitoringResult) : null;

  return (
    <div className="state-block">
      <strong>Current run</strong>
      <dl className="summary-grid">
        <SummaryItem label="Run ID" value={getRunId(run)} />
        <SummaryItem label="Status" value={run.status} />
        <SummaryItem label="Source/vendor" value={formatSelectedSource(run.source)} />
        <SummaryItem label="Output dir" value={run.output_dir} />
        <SummaryItem label="Input CSV" value={run.input_csv_path} />
        <SummaryItem label="Selection summary" value={run.selection_summary_path} />
        <SummaryItem label="Selected" value={run.selected_count} />
        <SummaryItem label="Skipped" value={run.skipped_count} />
        <SummaryItem
          label="Skipped missing active URL"
          value={getMissingActiveSourceUrlSkipCount(run as PriceMonitoringSelectionResult)}
        />
        <SummaryItem label="Latest fetch execution" value={latestFetch?.execution_id} />
        <SummaryItem label="Latest fetch status" value={formatFetchStatus(latestFetch?.status)} />
        <SummaryItem label="Latest fetch queued" value={latestFetch?.queued_at} />
        <SummaryItem label="Latest fetch started" value={latestFetch?.started_at} />
        <SummaryItem label="Latest fetch completed" value={latestFetch?.completed_at} />
        <SummaryItem label="Latest fetch cancelled" value={latestFetch?.cancelled_at} />
        <SummaryItem label="Latest fetch killed" value={latestFetch?.killed_at} />
      </dl>
      {latestFetch?.status ? (
        <p>
          <span className={`status-badge ${getFetchStatusTone(latestFetch.status)}`}>
            {formatFetchStatus(latestFetch.status)}
          </span>
        </p>
      ) : null}
      {latestFetch?.error ? <p className="form-error">{latestFetch.error}</p> : null}
      <HierarchyFilterSummary filters={hierarchyFilters} />
      <SourceUrlCoverageSummary coverage={run.source_url_coverage} />
      {resultHasNoMonitorableProducts(run as PriceMonitoringSelectionResult) ? (
        <NoMonitorableProductsActionCard source={formatSelectedSource(run.source)} />
      ) : resultHasMissingActiveSourceUrls(run as PriceMonitoringSelectionResult) ? (
        <div className="compact-list">
          <p className="form-warning">
            Products missing active source URLs were skipped. Price Monitoring consumes only
            existing active source URLs.
          </p>
          <VendorSourcesActionLink />
        </div>
      ) : null}
      {run.skipped_by_reason ? (
        <div className="compact-list">
          <strong>Skipped by reason</strong>
          <ul>
            {Object.entries(run.skipped_by_reason).map(([reason, count]) => (
              <li key={reason}>
                {reason}: {count}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function formatBoolean(value: unknown): string {
  if (typeof value !== "boolean") {
    return "-";
  }

  return value ? "Yes" : "No";
}

function formatPersistenceStatus(status: string): string {
  if (status === "not_configured") {
    return "DB not configured";
  }

  if (status === "persisted") {
    return "Persisted";
  }

  if (status === "failed") {
    return "Persistence failed";
  }

  return status;
}

function formatFetchInputMode(value: unknown): string {
  if (value === "source_urls") {
    return "Source URL monitoring";
  }

  if (value === "legacy_marketplace") {
    return "Deprecated fetch diagnostic";
  }

  return formatValue(value);
}

function getPersistenceStatusClass(status: string): string {
  if (status === "persisted") {
    return "ok";
  }

  if (status === "not_configured") {
    return "warning";
  }

  if (status === "failed") {
    return "danger";
  }

  return "neutral";
}

function FetchResultBlock({
  result,
  onPreview,
}: {
  result: FetchPriceMonitoringResult;
  onPreview: (path: string) => Promise<string>;
}) {
  const fallbackArtifacts = artifactValuesToItems([
    result.input_csv_path,
    result.enriched_csv_path,
    result.fetch_summary_path,
    result.fetch_result_path,
    result.execution_path,
    result.log_path,
  ]);
  const artifacts = result.artifacts && result.artifacts.length > 0 ? result.artifacts : fallbackArtifacts;
  const artifactsAreDiagnostic = shouldTreatArtifactsAsDiagnostic(result);

  return (
    <div className="state-block">
      <strong>Fetch result</strong>
      {result.status ? (
        <p>
          <span className={`status-badge ${getFetchStatusTone(result.status)}`}>
            {formatFetchStatus(result.status)}
          </span>
        </p>
      ) : null}
      <dl className="summary-grid">
        <SummaryItem label="Run ID" value={result.run_id} />
        <SummaryItem label="Execution ID" value={result.execution_id} />
        <SummaryItem label="Status" value={formatFetchStatus(result.status)} />
        <SummaryItem label="Source/vendor" value={formatSelectedSource(result.source)} />
        <SummaryItem label="Fetch input mode" value={formatFetchInputMode(result.fetch_input_mode)} />
        <SummaryItem label="Catalog URL diagnostic" value={result.catalog_url} />
        <SummaryItem label="Queued" value={result.queued_at} />
        <SummaryItem label="Started" value={result.started_at} />
        <SummaryItem label="Completed" value={result.completed_at} />
        <SummaryItem label="Cancelled" value={result.cancelled_at} />
        <SummaryItem label="Killed" value={result.killed_at} />
        <SummaryItem label="Cancel reason" value={result.cancel_reason} />
        <SummaryItem label="Termination mode" value={result.termination_mode} />
        <SummaryItem label="Exit code" value={result.exit_code} />
        <SummaryItem label="Input CSV" value={getArtifactPath(result.input_csv_path)} />
        <SummaryItem label="Enriched CSV" value={getArtifactPath(result.enriched_csv_path)} />
        <SummaryItem label="Fetch summary" value={getArtifactPath(result.fetch_summary_path)} />
        <SummaryItem label="Fetch result" value={getArtifactPath(result.fetch_result_path)} />
        <SummaryItem label="Execution metadata" value={getArtifactPath(result.execution_path)} />
        <SummaryItem label="Log path" value={getArtifactPath(result.log_path)} />
        <SummaryItem label="Stored observations" value={result.observation_count} />
        <SummaryItem label="Appended observations" value={result.appended_observation_count} />
        <SummaryItem label="Prior observations" value={getPriorObservationCount(result)} />
        <SummaryItem label="Catalog snapshot" value={result.catalog_snapshot_count} />
        <SummaryItem label="Matched observations" value={result.matched_observation_count} />
        <SummaryItem label="Unmatched observations" value={result.unmatched_observation_count} />
        <SummaryItem label="Fetch attempt" value={result.fetch_attempt} />
        <SummaryItem label="Was refetch" value={formatBoolean(result.was_refetch)} />
        <SummaryItem label="Observation batch" value={result.observation_batch_id} />
        <SummaryItem label="Observation history" value={result.observation_history_count} />
        <SummaryItem label="Persistence" value={result.persistence_status} />
        <SummaryItem label="Alert evaluation status" value={result.alert_evaluation_status} />
        <SummaryItem label="Alert events created" value={result.alert_event_count} />
        <SummaryItem label="Alert duplicate count" value={result.alert_duplicate_count} />
        <SummaryItem label="Error" value={result.error} />
      </dl>
      {result.fetch_input_mode === "source_urls" ? (
        <p>
          <span className="status-badge ok">Source URL monitoring</span>
        </p>
      ) : null}
      {result.legacy_marketplace_fetch_used === true ? (
        <details className="state-block">
          <summary>Deprecated diagnostics</summary>
          <dl className="summary-grid">
            <SummaryItem label="legacy_marketplace_fetch_used" value="true" />
          </dl>
        </details>
      ) : null}
      {result.persistence_status ? (
        <p>
          <span className={`status-badge ${getPersistenceStatusClass(result.persistence_status)}`}>
            {formatPersistenceStatus(result.persistence_status)}
          </span>
        </p>
      ) : null}
      {result.persistence_status === "not_configured" ? (
        <p className="form-warning">PostgreSQL was not ready when this fetch result was produced, so observations were not stored.</p>
      ) : null}
      {result.was_refetch ? (
        <p className="muted">Refetch completed. Previous observations remain in history; this fetch is shown as another observation batch.</p>
      ) : null}
      {artifacts.length > 0 && artifactsAreDiagnostic ? (
        <DiagnosticArtifactsBlock
          warning={result.artifact_warning}
          artifacts={artifacts}
          onPreview={onPreview}
        />
      ) : null}
      {artifacts.length > 0 && !artifactsAreDiagnostic && isCancelledFetchStatus(result.status) ? (
        <CompactArtifactLinks title="Cancelled execution artifacts" artifacts={artifacts} />
      ) : null}
      {artifacts.length > 0 && !artifactsAreDiagnostic && !isCancelledFetchStatus(result.status) ? (
        <ArtifactList
          title="Fetch artifacts"
          items={artifacts}
          onPreview={onPreview}
          getDownloadUrl={commerceClient.getArtifactDownloadUrl}
        />
      ) : null}
      {result.warnings && result.warnings.length > 0 ? (
        <div className="compact-list">
          <strong>Warnings</strong>
          <ul>
            {result.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {result.persistence_warnings && result.persistence_warnings.length > 0 ? (
        <div className="compact-list">
          <strong>Persistence warnings</strong>
          <ul>
            {result.persistence_warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {result.alert_warnings && result.alert_warnings.length > 0 ? (
        <div className="compact-list">
          <strong>Alert warnings</strong>
          <ul>
            {result.alert_warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {result.error ? <p className="form-error">{result.error}</p> : null}
    </div>
  );
}

function CompactArtifactLinks({
  title,
  artifacts,
}: {
  title: string;
  artifacts: ArtifactItem[];
}) {
  return (
    <div className="compact-list">
      <strong>{title}</strong>
      <ul>
        {artifacts.map((artifact, index) => (
          <li key={`${artifact.path}-${index}`}>
            <span>{artifact.name}</span>
            <small className="artifact-path">{artifact.path}</small>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DiagnosticArtifactsBlock({
  warning,
  artifacts,
  onPreview,
}: {
  warning?: string | null;
  artifacts: ArtifactItem[];
  onPreview: (path: string) => Promise<string>;
}) {
  return (
    <details className="diagnostic-artifacts">
      <summary>
        <strong>Diagnostic artifacts</strong>
        <span className="muted"> {artifacts.length.toLocaleString()} items</span>
      </summary>
      {warning ? <p className="form-warning">{warning}</p> : null}
      <p className="muted">
        These artifacts came from a diagnostic execution path and are not treated as successful outputs.
      </p>
      <ArtifactList
        title="Diagnostic artifacts"
        items={artifacts}
        onPreview={onPreview}
        getDownloadUrl={commerceClient.getArtifactDownloadUrl}
      />
    </details>
  );
}

function FetchLogsPanel({
  logs,
  error,
  isLoading,
  onRefresh,
}: {
  logs: PriceMonitoringFetchLogsResponse | null;
  error: string | null;
  isLoading: boolean;
  onRefresh: () => void;
}) {
  const lines = logs?.lines ?? [];

  return (
    <details className="state-block fetch-logs-panel" open={lines.length > 0 || Boolean(error)}>
      <summary>
        <strong>Fetch logs</strong>
        <span className="muted"> {lines.length.toLocaleString()} lines</span>
      </summary>
      <div className="section-heading">
        <div>
          <span className="muted">Latest fetch execution logs</span>
        </div>
        <button className="button secondary" type="button" disabled={isLoading} onClick={onRefresh}>
          {isLoading ? "Refreshing..." : "Refresh logs"}
        </button>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
      {!error && lines.length === 0 ? <p className="muted">No fetch logs yet.</p> : null}
      {lines.length > 0 ? (
        <pre className="json-block fetch-log-block">{lines.join("\n")}</pre>
      ) : null}
    </details>
  );
}

function ReviewArtifactsBlock({
  review,
  onPreview,
}: {
  review: PriceMonitoringReviewResponse;
  onPreview: (path: string) => Promise<string>;
}) {
  const artifacts = artifactValuesToItems([
    review.review_csv_path,
    review.enriched_csv_path,
  ]);

  return artifacts.length > 0 ? (
    <ArtifactList
      title="Review artifacts"
      items={artifacts}
      onPreview={onPreview}
      getDownloadUrl={commerceClient.getArtifactDownloadUrl}
    />
  ) : null;
}

function ApplyActionsResultBlock({
  result,
  onPreview,
}: {
  result: ApplyPriceMonitoringReviewActionsResult;
  onPreview: (path: string) => Promise<string>;
}) {
  const artifacts = artifactValuesToItems([
    result.review_csv_path,
    result.review_actions_path,
  ]);

  return (
    <div className="state-block">
      <strong>Actions applied</strong>
      <dl className="summary-grid">
        <SummaryItem label="Status" value={result.status} />
        <SummaryItem label="Review CSV" value={getArtifactPath(result.review_csv_path)} />
        <SummaryItem label="Actions path" value={getArtifactPath(result.review_actions_path)} />
        <SummaryItem label="Actions" value={result.summary?.actions_count} />
        <SummaryItem label="Exportable" value={result.summary?.exportable_count} />
        <SummaryItem label="Ignored" value={result.summary?.ignored_count} />
        <SummaryItem label="Not exportable" value={result.summary?.not_exportable_count} />
      </dl>
      {artifacts.length > 0 ? (
        <ArtifactList
          title="Review action artifacts"
          items={artifacts}
          onPreview={onPreview}
          getDownloadUrl={commerceClient.getArtifactDownloadUrl}
        />
      ) : null}
    </div>
  );
}

function ExportResultBlock({
  result,
  onPreview,
}: {
  result: ExportPriceMonitoringPriceUpdateResult;
  onPreview: (path: string) => Promise<string>;
}) {
  const artifacts = artifactValuesToItems([result.output_path]);

  return (
    <div className="state-block">
      <strong>Export result</strong>
      <dl className="summary-grid">
        <SummaryItem label="Status" value={result.status} />
        <SummaryItem label="Output path" value={getArtifactPath(result.output_path)} />
        <SummaryItem label="Rows exported" value={result.rows_exported} />
        <SummaryItem label="Columns" value={result.columns?.join(", ")} />
      </dl>
      {artifacts.length > 0 ? (
        <ArtifactList
          title="Export artifact"
          items={artifacts}
          onPreview={onPreview}
          getDownloadUrl={commerceClient.getArtifactDownloadUrl}
        />
      ) : null}
      <p className="muted">This exports CSV only. OpenCart is not updated automatically.</p>
    </div>
  );
}

function getCurrency(value: unknown): string {
  return typeof value === "string" && /^[A-Z]{3}$/.test(value) ? value : "EUR";
}

function isObservationMatched(item: PriceObservation): boolean {
  return item.is_matched === true || item.match_status === "matched";
}

function getStoredObservationKey(item: PriceObservation, index: number): string {
  const id = item.id ?? `${item.run_id ?? "run"}-${item.model ?? "model"}-${item.source ?? "source"}`;
  return `${id}-${index}`;
}

function getCreateAlertLink(item: PriceObservation): string {
  const params = new URLSearchParams();
  const model = typeof item.model === "string" ? item.model.trim() : "";
  const mpn = typeof item.mpn === "string" ? item.mpn.trim() : "";
  const catalogSource =
    typeof item.catalog_source === "string" && item.catalog_source.trim().length > 0
      ? item.catalog_source.trim()
      : typeof item.source === "string"
        ? item.source.trim()
        : "";

  if (item.product_id !== null && item.product_id !== undefined && item.product_id !== "") {
    params.set("product_id", String(item.product_id));
  } else if (catalogSource && model) {
    params.set("catalog_source", catalogSource);
    params.set("model", model);
  } else if (catalogSource && mpn) {
    params.set("catalog_source", catalogSource);
    params.set("mpn", mpn);
  }

  if (model) {
    params.set("name", `Competitor below own price - ${model}`);
  }

  const query = params.toString();
  return query ? `/price-monitoring/alerts?${query}` : "/price-monitoring/alerts";
}

function filterStoredObservations(
  items: PriceObservation[],
  matchStatus: StoredObservationMatchFilter,
  model: string,
  mpn: string,
): PriceObservation[] {
  const modelFilter = model.trim().toLowerCase();
  const mpnFilter = mpn.trim().toLowerCase();

  return items.filter((item) => {
    if (matchStatus === "matched" && !isObservationMatched(item)) {
      return false;
    }

    if (matchStatus === "unmatched" && isObservationMatched(item)) {
      return false;
    }

    if (modelFilter && !String(item.model ?? "").toLowerCase().includes(modelFilter)) {
      return false;
    }

    if (mpnFilter && !String(item.mpn ?? "").toLowerCase().includes(mpnFilter)) {
      return false;
    }

    return true;
  });
}

function hasObservationHistoryMetadata(item: PriceObservation): boolean {
  return Boolean(
    item.execution_id ??
      item.fetch_attempt ??
      item.observation_batch_id ??
      item.product_source_id ??
      item.source_capture_snapshot_id ??
      item.created_at,
  );
}

function ObservationTable({
  items,
  isDbAvailable,
}: {
  items: PriceObservation[];
  isDbAvailable: boolean;
}) {
  if (items.length === 0) {
    return <EmptyState title="No stored observations" message="No observations matched the current filters." />;
  }

  const showHistoryColumns = items.some(hasObservationHistoryMetadata);

  return (
    <div className="table-wrap observation-table-wrap">
      <table>
        <thead>
          <tr>
            <th>Match</th>
            <th>Model</th>
            <th>MPN</th>
            <th>Product name</th>
            <th>Source</th>
            <th>Competitor / Store</th>
            <th>Competitor price</th>
            <th>Own price</th>
            <th>Delta</th>
            <th>Delta %</th>
            <th>Availability</th>
            <th>Product URL</th>
            <th>Observed at</th>
            {showHistoryColumns ? <th>Attempt</th> : null}
            {showHistoryColumns ? <th>Batch/source</th> : null}
            {showHistoryColumns ? <th>Stored at</th> : null}
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => {
            const matched = isObservationMatched(item);
            const currency = getCurrency(item.currency);

            return (
              <tr key={getStoredObservationKey(item, index)}>
                <td>
                  <span className={`status-badge ${matched ? "ok" : "warning"}`}>
                    {matched ? "Matched" : "Unmatched"}
                  </span>
                </td>
                <td className="nowrap-cell">{formatValue(item.model)}</td>
                <td className="nowrap-cell">{formatValue(item.mpn)}</td>
                <td>{formatValue(item.product_name)}</td>
                <td>{formatValue(item.source)}</td>
                <td>{formatValue(item.competitor_name)}</td>
                <td className="nowrap-cell">{formatMoney(item.competitor_price, currency)}</td>
                <td className="nowrap-cell">{formatMoney(item.own_price, currency)}</td>
                <td className="nowrap-cell">{formatNumber(item.price_delta)}</td>
                <td className="nowrap-cell">{formatNumber(item.price_delta_percent)}</td>
                <td>{formatValue(item.availability)}</td>
                <td>
                  {item.product_url ? (
                    <a href={item.product_url} target="_blank" rel="noreferrer">
                      Open
                    </a>
                  ) : (
                    "-"
                  )}
                </td>
                <td className="nowrap-cell">{formatValue(item.observed_at)}</td>
                {showHistoryColumns ? (
                  <td>
                    {formatValue(item.fetch_attempt)}
                    {item.was_refetch === true ? <small className="artifact-path">Refetch</small> : null}
                  </td>
                ) : null}
                {showHistoryColumns ? (
                  <td>
                    {formatValue(item.observation_batch_id ?? item.execution_id)}
                    <small className="artifact-path">
                      {formatValue(item.product_source_id ?? item.source_capture_snapshot_id)}
                    </small>
                  </td>
                ) : null}
                {showHistoryColumns ? <td className="nowrap-cell">{formatValue(item.created_at)}</td> : null}
                <td>
                  {isDbAvailable ? (
                    <Link className="button secondary" to={getCreateAlertLink(item)}>
                      Create alert
                    </Link>
                  ) : (
                    <span
                      className="button secondary disabled-link"
                      aria-disabled="true"
                      title="Database is unavailable. Alert write actions are disabled."
                    >
                      Create alert
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CatalogSnapshotTable({ snapshot }: { snapshot: CatalogSnapshotResponse | null }) {
  const items = snapshot?.items ?? [];

  return (
    <details className="state-block catalog-snapshot-block" open>
      <summary>
        <strong>Catalog Snapshot</strong>
        <span className="muted"> {formatValue(snapshot?.count ?? items.length)} rows</span>
      </summary>
      {items.length === 0 ? (
        <EmptyState title="No catalog snapshot" message="No catalog snapshot rows were returned for this run." />
      ) : (
        <div className="table-wrap catalog-snapshot-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Match/Product ID</th>
                <th>Model</th>
                <th>MPN</th>
                <th>Name</th>
                <th>Manufacturer</th>
                <th>Family</th>
                <th>Category</th>
                <th>Sub-Category</th>
                <th>Marketplace</th>
                <th>Own price</th>
                <th>Created at</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={`${item.id ?? item.product_id ?? item.model ?? "catalog"}-${index}`}>
                  <td>
                    {item.product_id ? (
                      formatValue(item.product_id)
                    ) : (
                      <span className="status-badge warning">Missing</span>
                    )}
                  </td>
                  <td className="nowrap-cell">{formatValue(item.model)}</td>
                  <td className="nowrap-cell">{formatValue(item.mpn)}</td>
                  <td>{formatValue(item.name)}</td>
                  <td>{formatValue(item.manufacturer)}</td>
                  <td>{formatValue(item.family)}</td>
                  <td>{formatValue(item.category_name)}</td>
                  <td>{formatValue(item.sub_category)}</td>
                  <td>{formatValue(item.marketplace)}</td>
                  <td className="nowrap-cell">{formatMoney(item.own_price, getCurrency(item.currency))}</td>
                  <td className="nowrap-cell">{formatValue(item.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  );
}

function StoredObservationsSection({
  runId,
  dbStatus,
  dbStatusError,
  isDbStatusLoading,
  isLoading,
  observations,
  catalogSnapshot,
  observationError,
  catalogSnapshotError,
  fetchResult,
  matchStatus,
  includeUnmatched,
  modelFilter,
  mpnFilter,
  onMatchStatusChange,
  onIncludeUnmatchedChange,
  onModelFilterChange,
  onMpnFilterChange,
  onRefresh,
  onRetryDbStatus,
}: {
  runId: string;
  dbStatus: PriceMonitoringDbStatus | null;
  dbStatusError: string | null;
  isDbStatusLoading: boolean;
  isLoading: boolean;
  observations: RunPriceObservationsResponse | null;
  catalogSnapshot: CatalogSnapshotResponse | null;
  observationError: string | null;
  catalogSnapshotError: string | null;
  fetchResult: FetchPriceMonitoringResult | null;
  matchStatus: StoredObservationMatchFilter;
  includeUnmatched: boolean;
  modelFilter: string;
  mpnFilter: string;
  onMatchStatusChange: (value: StoredObservationMatchFilter) => void;
  onIncludeUnmatchedChange: (value: boolean) => void;
  onModelFilterChange: (value: string) => void;
  onMpnFilterChange: (value: string) => void;
  onRefresh: () => void;
  onRetryDbStatus: () => void;
}) {
  const filteredItems = filterStoredObservations(
    observations?.items ?? [],
    matchStatus,
    modelFilter,
    mpnFilter,
  );
  const dbAvailable = isPriceMonitoringDbAvailable(dbStatus);

  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Stored Observations</p>
          <h3>Stored Observations</h3>
        </div>
        <button
          className="button secondary"
          type="button"
          disabled={isLoading || !dbAvailable}
          title={dbAvailable ? undefined : getPriceMonitoringDbBlockingMessage(dbStatus)}
          onClick={onRefresh}
        >
          {isLoading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      <PriceMonitoringDbStatusBanner
        status={dbStatus}
        error={dbStatusError}
        isLoading={isDbStatusLoading}
        onRetry={onRetryDbStatus}
      />

      {!runId ? (
        <EmptyState title="No run selected" message="Select or create a run to view stored observations." />
      ) : (
        <>
          <dl className="summary-grid">
            <SummaryItem label="Run ID" value={observations?.run_id ?? runId} />
            <SummaryItem label="Total observations" value={observations?.count ?? fetchResult?.observation_count} />
            <SummaryItem
              label="Matched"
              value={observations?.matched_count ?? fetchResult?.matched_observation_count}
            />
            <SummaryItem
              label="Unmatched"
              value={observations?.unmatched_count ?? fetchResult?.unmatched_observation_count}
            />
            <SummaryItem label="Fetch attempt" value={fetchResult?.fetch_attempt} />
            <SummaryItem label="Was refetch" value={formatBoolean(fetchResult?.was_refetch)} />
            <SummaryItem label="Prior observations" value={getPriorObservationCount(fetchResult)} />
            <SummaryItem label="Observation batch" value={fetchResult?.observation_batch_id} />
            <SummaryItem label="Observation history" value={fetchResult?.observation_history_count} />
            <SummaryItem label="Persistence status" value={fetchResult?.persistence_status} />
          </dl>

          {fetchResult?.persistence_warnings && fetchResult.persistence_warnings.length > 0 ? (
            <div className="compact-list">
              <strong>Persistence warnings</strong>
              <ul>
                {fetchResult.persistence_warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="filter-grid">
            <label>
              Match status
              <select
                value={matchStatus}
                onChange={(event) => onMatchStatusChange(event.target.value as StoredObservationMatchFilter)}
              >
                <option value="all">All</option>
                <option value="matched">Matched</option>
                <option value="unmatched">Unmatched</option>
              </select>
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={includeUnmatched}
                onChange={(event) => onIncludeUnmatchedChange(event.target.checked)}
              />
              Include unmatched
            </label>
            <label>
              Model
              <input
                value={modelFilter}
                onChange={(event) => onModelFilterChange(event.target.value)}
                placeholder="Filter current run"
              />
            </label>
            <label>
              MPN
              <input
                value={mpnFilter}
                onChange={(event) => onMpnFilterChange(event.target.value)}
                placeholder="Filter current run"
              />
            </label>
          </div>

          {isLoading ? <LoadingState label="Loading stored observations..." /> : null}
          {observationError ? <ErrorState message={observationError} onRetry={onRefresh} /> : null}
          {!observationError && !isLoading ? (
            <ObservationTable items={filteredItems} isDbAvailable={dbAvailable} />
          ) : null}
          {catalogSnapshotError ? <ErrorState message={catalogSnapshotError} onRetry={onRefresh} /> : null}
          {!catalogSnapshotError && !isLoading ? <CatalogSnapshotTable snapshot={catalogSnapshot} /> : null}
        </>
      )}
    </section>
  );
}

function SummaryItem({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{formatValue(value)}</dd>
    </div>
  );
}

function getNameFromPath(path: string): string {
  const parts = path.split(/[\\/]+/).filter(Boolean);
  return parts.length > 0 ? parts[parts.length - 1] : path;
}

function artifactValueToItem(
  value: ArtifactPayload | string | null | undefined,
): ArtifactItem | null {
  if (!value) {
    return null;
  }

  if (typeof value !== "string") {
    return value;
  }

  const path = value.trim();
  if (!path) {
    return null;
  }

  return {
    name: getNameFromPath(path),
    path,
    extension: null,
    size_bytes: null,
    modified_at: null,
    download_url: null,
    read_url: null,
    is_allowed: true,
    can_read: true,
    can_download: true,
    warning: null,
  };
}

function artifactValuesToItems(
  values: Array<ArtifactPayload | string | null | undefined>,
): ArtifactItem[] {
  return values
    .map(artifactValueToItem)
    .filter((item): item is ArtifactItem => item !== null);
}

function normalizeWindowsPath(path: string): string {
  return path.trim().replace(/\//g, "\\").replace(/\\+$/g, "").toLowerCase();
}

function isPathUnderRoot(path: string, root: string): boolean {
  const normalizedPath = normalizeWindowsPath(path);
  const normalizedRoot = normalizeWindowsPath(root);

  return (
    normalizedPath === normalizedRoot ||
    normalizedPath.startsWith(`${normalizedRoot}\\`)
  );
}

function PriceMonitoringSetupHint() {
  return (
    <div className="setup-hint compact">
      <strong>Price Monitoring setup check</strong>
      <ul>
        <li>Confirm the run exists or create a new selection run.</li>
        <li>Confirm the selection run created <code>input.csv</code>.</li>
        <li>Confirm fetch created an enriched CSV before loading review.</li>
      </ul>
    </div>
  );
}

function RootList({ title, roots }: { title: string; roots: ArtifactRoot[] }) {
  return (
    <div className="diagnostic-card">
      <strong>{title}</strong>
      {roots.length === 0 ? (
        <p className="muted">No roots reported.</p>
      ) : (
        <ul className="root-list">
          {roots.map((root, index) => (
            <li key={`${root.path}-${index}`}>
              <code>{root.path}</code>
              <span className={`status-badge ${root.exists ? "ok" : "neutral"}`}>
                {root.exists ? "Exists" : "Missing"}
              </span>
              {root.is_default ? <span className="status-badge active">Default</span> : null}
              {root.is_configured ? (
                <span className="status-badge ok">Configured</span>
              ) : null}
              {root.source ? <small className="muted">{root.source}</small> : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function BackendPathsPanel({
  roots,
  isLoading,
  error,
  onRefresh,
}: {
  roots: PathRootsResponse | null;
  isLoading: boolean;
  error: string | null;
  onRefresh: () => void;
}) {
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Diagnostics</p>
          <h3>Backend Paths</h3>
        </div>
        <button className="button secondary" type="button" onClick={onRefresh}>
          Refresh paths
        </button>
      </div>

      {isLoading ? <LoadingState label="Loading backend path roots..." /> : null}
      {error ? <ErrorState message={error} /> : null}
      {roots ? (
        <>
          <div className="diagnostics-list">
            <RootList title="Artifact roots" roots={roots.artifact_roots} />
            <RootList title="File/editor roots" roots={roots.file_roots} />
            <RootList title="Output roots" roots={roots.output_roots} />
          </div>
          <div className="diagnostic-card">
            <strong>Environment</strong>
            <dl className="summary-grid diagnostics-summary-grid">
              <SummaryItem
                label="PRICEFETCHER_ARTIFACT_ROOTS"
                value={roots.env.PRICEFETCHER_ARTIFACT_ROOTS ?? "not_reported"}
              />
              <SummaryItem
                label="PRICEFETCHER_FILE_ROOTS"
                value={roots.env.PRICEFETCHER_FILE_ROOTS ?? "not_reported"}
              />
              <SummaryItem label="Platform" value={roots.platform} />
              <SummaryItem label="Separator" value={roots.path_separator} />
            </dl>
          </div>
        </>
      ) : null}
    </section>
  );
}

export function PriceMonitoringPage() {
  const fetchPollIntervalRef = useRef<number | null>(null);
  const fetchPollControllerRef = useRef<AbortController | null>(null);
  const restoredRunLoadedRef = useRef(false);
  const [persistedState, setPersistedState, resetPersistedState] =
    usePersistentPageState<PriceMonitoringWorkflowState>(
      PRICE_MONITORING_STATE_KEY,
      initialPriceMonitoringWorkflowState,
      { debounceMs: 250 },
    );
  const [categoryHierarchy, setCategoryHierarchy] =
    useState<CatalogCategoryHierarchyResponse | null>(null);
  const [brands, setBrands] = useState<CatalogBrandOption[]>([]);
  const [filterError, setFilterError] = useState<string | null>(null);
  const [areFiltersLoading, setAreFiltersLoading] = useState(true);
  const [vendorSources, setVendorSources] = useState<VendorSourceCapability[]>([]);
  const [vendorSourceError, setVendorSourceError] = useState<string | null>(null);

  const [source, setSource] = useState<PriceMonitoringSourceFilter>(
    normalizeSelectedSource(persistedState.source),
  );
  const [selectedFamily, setSelectedFamily] = useState(persistedState.selectedFamily);
  const [selectedCategory, setSelectedCategory] = useState(persistedState.selectedCategory);
  const [selectedSubCategory, setSelectedSubCategory] = useState(persistedState.selectedSubCategory);
  const [manufacturer, setManufacturer] = useState(persistedState.manufacturer);
  const [marketplace, setMarketplace] = useState<MarketplaceFilter>(persistedState.marketplace);
  const [q, setQ] = useState(persistedState.q);
  const [selectedModelText, setSelectedModelText] = useState(persistedState.selectedModelText);
  const [excludedModelText, setExcludedModelText] = useState(persistedState.excludedModelText);
  const [includeIgnored, setIncludeIgnored] = useState(persistedState.includeIgnored);
  const [automationEligibleOnly, setAutomationEligibleOnly] = useState(
    persistedState.automationEligibleOnly,
  );
  const [atomicOnly, setAtomicOnly] = useState(persistedState.atomicOnly);
  const [hasMpn, setHasMpn] = useState(persistedState.hasMpn);

  const [previewResult, setPreviewResult] = useState<PriceMonitoringSelectionResult | null>(null);
  const [previewFilters, setPreviewFilters] = useState<SelectionHierarchyFilters | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewNeedsSourceUrls, setPreviewNeedsSourceUrls] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  const [createResult, setCreateResult] = useState<PriceMonitoringSelectionResult | null>(null);
  const [createFilters, setCreateFilters] = useState<SelectionHierarchyFilters | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createNeedsSourceUrls, setCreateNeedsSourceUrls] = useState(false);
  const [isCreateLoading, setIsCreateLoading] = useState(false);

  const [currentRunId, setCurrentRunId] = useState(persistedState.currentRunId);
  const [currentRun, setCurrentRun] = useState<PriceMonitoringRun | PriceMonitoringSelectionResult | null>(null);
  const [currentRunFilters, setCurrentRunFilters] = useState<SelectionHierarchyFilters | null>(null);
  const [runs, setRuns] = useState<PriceMonitoringRun[]>([]);
  const [runListMessage, setRunListMessage] = useState<string | null>(null);
  const [isRunsLoading, setIsRunsLoading] = useState(false);
  const [loadRunError, setLoadRunError] = useState<string | null>(null);
  const [isLoadRunLoading, setIsLoadRunLoading] = useState(false);
  const [runArtifacts, setRunArtifacts] = useState<ArtifactItem[]>([]);
  const [artifactWarning, setArtifactWarning] = useState<string | null>(null);
  const [isArtifactsLoading, setIsArtifactsLoading] = useState(false);

  const [fetchSource, setFetchSource] = useState<SourceOverride>(persistedState.fetchSource);
  const [catalogUrl, setCatalogUrl] = useState(persistedState.catalogUrl);
  const [fetchResult, setFetchResult] = useState<FetchPriceMonitoringResult | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [isFetchLoading, setIsFetchLoading] = useState(false);
  const [fetchLogs, setFetchLogs] = useState<PriceMonitoringFetchLogsResponse | null>(null);
  const [fetchLogsError, setFetchLogsError] = useState<string | null>(null);
  const [isFetchLogsLoading, setIsFetchLogsLoading] = useState(false);
  const [isCancelFetchLoading, setIsCancelFetchLoading] = useState(false);

  const [enrichedCsvPath, setEnrichedCsvPath] = useState(persistedState.enrichedCsvPath);
  const [review, setReview] = useState<PriceMonitoringReviewResponse | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [isReviewLoading, setIsReviewLoading] = useState(false);
  const [rowActions, setRowActions] = useState<Record<string, RowActionState>>(() =>
    persistedState.reviewActionDrafts.reduce<Record<string, RowActionState>>((drafts, draft) => {
      if (draft.run_id === persistedState.currentRunId) {
        drafts[draft.model] = {
          selected_action: draft.selected_action,
          undercut_amount: draft.undercut_amount,
          reason: draft.reason,
        };
      }
      return drafts;
    }, {}),
  );

  const [applyResult, setApplyResult] =
    useState<ApplyPriceMonitoringReviewActionsResult | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [isApplyLoading, setIsApplyLoading] = useState(false);

  const [reviewCsvPath, setReviewCsvPath] = useState(persistedState.reviewCsvPath);
  const [useCustomExportPath, setUseCustomExportPath] = useState(
    persistedState.useCustomExportPath,
  );
  const [selectedExportArtifactRoot, setSelectedExportArtifactRoot] = useState(
    persistedState.selectedExportArtifactRoot,
  );
  const [exportOutputPath, setExportOutputPath] = useState(persistedState.exportOutputPath);
  const [exportResult, setExportResult] =
    useState<ExportPriceMonitoringPriceUpdateResult | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [isExportLoading, setIsExportLoading] = useState(false);

  const [pathRoots, setPathRoots] = useState<PathRootsResponse | null>(null);
  const [pathRootsError, setPathRootsError] = useState<string | null>(null);
  const [isPathRootsLoading, setIsPathRootsLoading] = useState(false);
  const [dbStatus, setDbStatus] = useState<PriceMonitoringDbStatus | null>(null);
  const [dbStatusError, setDbStatusError] = useState<string | null>(null);
  const [isDbStatusLoading, setIsDbStatusLoading] = useState(false);
  const [storedObservations, setStoredObservations] =
    useState<RunPriceObservationsResponse | null>(null);
  const [catalogSnapshot, setCatalogSnapshot] = useState<CatalogSnapshotResponse | null>(null);
  const [storedObservationError, setStoredObservationError] = useState<string | null>(null);
  const [catalogSnapshotError, setCatalogSnapshotError] = useState<string | null>(null);
  const [isStoredObservationLoading, setIsStoredObservationLoading] = useState(false);
  const [storedMatchStatus, setStoredMatchStatus] =
    useState<StoredObservationMatchFilter>(persistedState.storedMatchStatus);
  const [includeUnmatchedObservations, setIncludeUnmatchedObservations] = useState(
    persistedState.includeUnmatchedObservations,
  );
  const [storedModelFilter, setStoredModelFilter] = useState(persistedState.storedModelFilter);
  const [storedMpnFilter, setStoredMpnFilter] = useState(persistedState.storedMpnFilter);

  const loadFilters = useCallback(async (signal?: AbortSignal) => {
    setAreFiltersLoading(true);
    const [nextHierarchy, nextBrands, nextVendorSources] = await Promise.allSettled([
      commerceClient.getCatalogCategoryHierarchy(signal),
      commerceClient.listCatalogBrandOptions(signal),
      commerceClient.listVendorSources(signal),
    ]);
    if (signal?.aborted) {
      return;
    }

    const errors: string[] = [];
    if (nextHierarchy.status === "fulfilled") {
      setCategoryHierarchy(nextHierarchy.value);
    } else {
      setCategoryHierarchy(null);
      errors.push(getCategoryHierarchyErrorMessage(nextHierarchy.reason));
    }

    if (nextBrands.status === "fulfilled") {
      setBrands(
        nextBrands.value
          .filter((option) => option.manufacturer.trim().length > 0)
          .map((option) => ({
            manufacturer: option.manufacturer.trim(),
            count: option.count,
          })),
      );
    } else {
      setBrands([]);
      errors.push(`Could not load manufacturers: ${getCommerceApiErrorMessage(nextBrands.reason)}`);
    }

    if (nextVendorSources.status === "fulfilled") {
      setVendorSources(dedupeVendorSources(nextVendorSources.value));
      setVendorSourceError(null);
    } else {
      setVendorSources([]);
      setVendorSourceError(getCommerceApiErrorMessage(nextVendorSources.reason));
    }

    setFilterError(errors.length > 0 ? errors.join(" ") : null);
    setAreFiltersLoading(false);
  }, []);

  const loadRuns = useCallback(async (signal?: AbortSignal) => {
    setIsRunsLoading(true);
    try {
      const nextRuns = await commerceClient.listPriceMonitoringRuns(signal);
      if (signal?.aborted) {
        return;
      }

      setRuns(nextRuns);
      setRunListMessage(null);
    } catch (error) {
      if (!signal?.aborted) {
        const message =
          error instanceof CommerceApiError && error.status === 404
            ? "Run listing is not available from this backend. Manual run ID workflow is still available."
            : getCommerceApiErrorMessage(error);
        setRuns([]);
        setRunListMessage(message);
      }
    } finally {
      if (!signal?.aborted) {
        setIsRunsLoading(false);
      }
    }
  }, []);

  const loadPathRoots = useCallback(async (signal?: AbortSignal) => {
    setIsPathRootsLoading(true);
    setPathRootsError(null);
    try {
      const roots = await commerceClient.getPathRoots(signal);
      if (signal?.aborted) {
        return;
      }

      setPathRoots(roots);
    } catch {
      if (!signal?.aborted) {
        setPathRoots(null);
        setPathRootsError(
          "Could not load backend path roots. Check that price-fetcher is running.",
        );
      }
    } finally {
      if (!signal?.aborted) {
        setIsPathRootsLoading(false);
      }
    }
  }, []);

  const loadDbStatus = useCallback(async (signal?: AbortSignal) => {
    setIsDbStatusLoading(true);
    setDbStatusError(null);
    try {
      const status = await commerceClient.getPriceMonitoringDbStatus(signal);
      if (signal?.aborted) {
        return null;
      }

      setDbStatus(status);
      return status;
    } catch (error) {
      if (!signal?.aborted) {
        setDbStatus(null);
        setDbStatusError(getCommerceApiErrorMessage(error));
      }
      return null;
    } finally {
      if (!signal?.aborted) {
        setIsDbStatusLoading(false);
      }
    }
  }, []);

  const loadStoredObservations = useCallback(
    async (runId = currentRunId.trim(), signal?: AbortSignal) => {
      setIsStoredObservationLoading(true);
      setStoredObservationError(null);
      setCatalogSnapshotError(null);

      const statusPromise = loadDbStatus(signal);

      if (!runId) {
        setStoredObservations(null);
        setCatalogSnapshot(null);
        await statusPromise;
        if (!signal?.aborted) {
          setIsStoredObservationLoading(false);
        }
        return;
      }

      const [observationResult, snapshotResult] = await Promise.allSettled([
        commerceClient.getPriceMonitoringRunObservations(
          runId,
          {
            include_unmatched: includeUnmatchedObservations,
            limit: 1000,
            offset: 0,
          },
          signal,
        ),
        commerceClient.getPriceMonitoringRunCatalogSnapshot(runId, signal),
      ]);
      await statusPromise;

      if (signal?.aborted) {
        return;
      }

      if (observationResult.status === "fulfilled") {
        setStoredObservations(observationResult.value);
      } else {
        setStoredObservations(null);
        setStoredObservationError(getCommerceApiErrorMessage(observationResult.reason));
      }

      if (snapshotResult.status === "fulfilled") {
        setCatalogSnapshot(snapshotResult.value);
      } else {
        setCatalogSnapshot(null);
        setCatalogSnapshotError(
          `Catalog snapshot failed: ${getCommerceApiErrorMessage(snapshotResult.reason)}`,
        );
      }

      setIsStoredObservationLoading(false);
    },
    [currentRunId, includeUnmatchedObservations, loadDbStatus],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadFilters(controller.signal);
    void loadRuns(controller.signal);
    void loadPathRoots(controller.signal);
    void loadDbStatus(controller.signal);
    return () => controller.abort();
  }, [loadDbStatus, loadFilters, loadPathRoots, loadRuns]);

  useEffect(() => {
    const controller = new AbortController();
    void loadStoredObservations(currentRunId.trim(), controller.signal);
    return () => controller.abort();
  }, [currentRunId, includeUnmatchedObservations, loadStoredObservations]);

  useEffect(() => {
    const runId = currentRunId.trim();
    setPersistedState({
      source,
      q,
      selectedFamily,
      selectedCategory,
      selectedSubCategory,
      manufacturer,
      marketplace,
      selectedModelText,
      excludedModelText,
      includeIgnored,
      automationEligibleOnly,
      atomicOnly,
      hasMpn,
      currentRunId: runId,
      currentExecutionId:
        fetchResult?.execution_id === null || fetchResult?.execution_id === undefined
          ? persistedState.currentExecutionId
          : String(fetchResult.execution_id),
      fetchSource,
      catalogUrl,
      enrichedCsvPath,
      storedMatchStatus,
      includeUnmatchedObservations,
      storedModelFilter,
      storedMpnFilter,
      reviewCsvPath,
      useCustomExportPath,
      selectedExportArtifactRoot,
      exportOutputPath,
      reviewActionDrafts: Object.entries(rowActions)
        .filter(
          ([, action]) =>
            action.selected_action || action.undercut_amount.trim() || action.reason.trim(),
        )
        .map(([model, action]) => ({
          run_id: runId,
          model,
          selected_action: action.selected_action,
          undercut_amount: action.undercut_amount,
          reason: action.reason,
        })),
    });
  }, [
    atomicOnly,
    automationEligibleOnly,
    catalogUrl,
    currentRunId,
    enrichedCsvPath,
    excludedModelText,
    exportOutputPath,
    fetchResult?.execution_id,
    fetchSource,
    hasMpn,
    includeIgnored,
    includeUnmatchedObservations,
    manufacturer,
    marketplace,
    persistedState.currentExecutionId,
    q,
    reviewCsvPath,
    rowActions,
    selectedCategory,
    selectedExportArtifactRoot,
    selectedFamily,
    selectedModelText,
    selectedSubCategory,
    setPersistedState,
    source,
    storedMatchStatus,
    storedModelFilter,
    storedMpnFilter,
    useCustomExportPath,
  ]);

  const buildSelectionBody = (dryRun: boolean) =>
    makeSelectionBody({
      source,
      q,
      family: selectedFamily,
      categoryName: selectedCategory,
      subCategory: selectedSubCategory,
      manufacturer,
      marketplace,
      selectedModelText,
      excludedModelText,
      includeIgnored,
      automationEligibleOnly,
      atomicOnly,
      hasMpn,
      dryRun,
    });

  const refreshRunArtifacts = async (runId = currentRunId.trim()) => {
    if (!runId) {
      setRunArtifacts([]);
      return;
    }

    setIsArtifactsLoading(true);
    setArtifactWarning(null);
    try {
      const artifactList = await commerceClient.listPriceMonitoringRunArtifacts(runId);
      setRunArtifacts(artifactList.items);
    } catch (error) {
      setArtifactWarning(
        `Artifact listing failed: ${getCommerceApiErrorMessage(error)}`,
      );
    } finally {
      setIsArtifactsLoading(false);
    }
  };

  const stopFetchPolling = useCallback(() => {
    if (fetchPollIntervalRef.current !== null) {
      window.clearInterval(fetchPollIntervalRef.current);
      fetchPollIntervalRef.current = null;
    }

    fetchPollControllerRef.current?.abort();
    fetchPollControllerRef.current = null;
  }, []);

  const updateFetchResultState = useCallback((result: FetchPriceMonitoringResult) => {
    setFetchResult(result);
    const nextEnrichedCsvPath = getArtifactPath(result.enriched_csv_path);
    if (nextEnrichedCsvPath) {
      setEnrichedCsvPath(nextEnrichedCsvPath);
    }
  }, []);

  const loadFetchLogs = useCallback(
    async (runId = currentRunId.trim(), signal?: AbortSignal, showLoading = true) => {
      if (!runId) {
        setFetchLogs(null);
        return null;
      }

      if (showLoading) {
        setIsFetchLogsLoading(true);
      }
      setFetchLogsError(null);

      try {
        const logs = await commerceClient.getPriceMonitoringFetchLogs(runId, signal);
        if (signal?.aborted) {
          return null;
        }

        setFetchLogs(logs);
        return logs;
      } catch (error) {
        if (!signal?.aborted) {
          setFetchLogsError(getCommerceApiErrorMessage(error));
        }
        return null;
      } finally {
        if (!signal?.aborted && showLoading) {
          setIsFetchLogsLoading(false);
        }
      }
    },
    [currentRunId],
  );

  const finishTerminalFetch = useCallback(
    async (runId: string, result: FetchPriceMonitoringResult, signal?: AbortSignal) => {
      if (isSuccessfulFetchStatus(result.status)) {
        await Promise.allSettled([
          commerceClient.getPriceMonitoringRun(runId, signal).then((run) => {
            setCurrentRun(run);
            setCurrentRunFilters(null);
          }),
          refreshRunArtifacts(runId),
          result.persistence_status === "persisted" && isPriceMonitoringDbAvailable(dbStatus)
            ? loadStoredObservations(runId, signal)
            : Promise.resolve(),
        ]);
      }

      if (isFailedFetchStatus(result.status) && result.error) {
        setFetchError(result.error);
      }
    },
    [dbStatus, loadStoredObservations],
  );

  const pollFetchOnce = useCallback(
    async (runId: string, signal?: AbortSignal) => {
      try {
        const result = await commerceClient.getPriceMonitoringFetch(runId, signal);
        if (signal?.aborted) {
          return;
        }

        updateFetchResultState(result);
        await loadFetchLogs(runId, signal, false);

        if (isTerminalFetchStatus(result.status)) {
          if (fetchPollIntervalRef.current !== null) {
            window.clearInterval(fetchPollIntervalRef.current);
            fetchPollIntervalRef.current = null;
          }
          await finishTerminalFetch(runId, result);
          stopFetchPolling();
        }
      } catch (error) {
        if (!signal?.aborted) {
          setFetchError(getCommerceApiErrorMessage(error));
        }
      }
    },
    [finishTerminalFetch, loadFetchLogs, stopFetchPolling, updateFetchResultState],
  );

  const startFetchPolling = useCallback(
    (runId: string) => {
      stopFetchPolling();
      const controller = new AbortController();
      fetchPollControllerRef.current = controller;
      fetchPollIntervalRef.current = window.setInterval(() => {
        void pollFetchOnce(runId, controller.signal);
      }, 2500);
    },
    [pollFetchOnce, stopFetchPolling],
  );

  useEffect(() => stopFetchPolling, [stopFetchPolling]);

  const previewArtifact = async (path: string) => {
    const response = await commerceClient.readArtifact(path, 200_000);
    return response.content;
  };

  const selectedHierarchyFilters = useMemo<SelectionHierarchyFilters>(
    () => ({
      family: selectedFamily || null,
      category_name: selectedCategory || null,
      sub_category: selectedSubCategory || null,
    }),
    [selectedCategory, selectedFamily, selectedSubCategory],
  );

  const familyOptions = useMemo(
    () => getFamilyOptions(categoryHierarchy),
    [categoryHierarchy],
  );

  const categoryOptions = useMemo(
    () => getCategoryOptions(categoryHierarchy, selectedFamily),
    [categoryHierarchy, selectedFamily],
  );

  const subCategoryOptions = useMemo(
    () => getSubCategoryOptions(categoryHierarchy, selectedFamily, selectedCategory),
    [categoryHierarchy, selectedCategory, selectedFamily],
  );

  const sourceUrlFilterOptions = useMemo(
    () =>
      dedupeVendorSources(
        vendorSources.filter((option) => normalizeSelectedSource(String(option.source_name))),
      ),
    [vendorSources],
  );
  const selectedSourceName = normalizeSelectedSource(source);
  const sourceRequired = selectedSourceName.length === 0;

  const previewSelection = async () => {
    if (sourceRequired) {
      setPreviewError(SOURCE_REQUIRED_MESSAGE);
      setPreviewNeedsSourceUrls(false);
      return;
    }

    if (!isPriceMonitoringDbAvailable(dbStatus)) {
      setPreviewError(getPriceMonitoringDbBlockingMessage(dbStatus));
      return;
    }

    const hierarchyFilterSnapshot = selectedHierarchyFilters;
    setIsPreviewLoading(true);
    setPreviewError(null);
    setPreviewNeedsSourceUrls(false);
    setPreviewResult(null);
    setPreviewFilters(null);
    try {
      const result = await commerceClient.previewPriceMonitoringSelection(buildSelectionBody(true));
      setPreviewResult(result);
      setPreviewFilters(hierarchyFilterSnapshot);
    } catch (error) {
      const sourceRequirementMessage = getSourceRequirementErrorMessage(error);
      const missingUrlMessage = getMissingActiveSourceUrlErrorMessage(error, selectedSourceName);
      setPreviewNeedsSourceUrls(missingUrlMessage !== null);
      setPreviewError(sourceRequirementMessage ?? missingUrlMessage ?? getCommerceApiErrorMessage(error));
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const createRun = async () => {
    if (sourceRequired) {
      setCreateError(SOURCE_REQUIRED_MESSAGE);
      setCreateNeedsSourceUrls(false);
      return;
    }

    if (!isPriceMonitoringDbAvailable(dbStatus)) {
      setCreateError(getPriceMonitoringDbBlockingMessage(dbStatus));
      return;
    }

    const hierarchyFilterSnapshot = selectedHierarchyFilters;
    setIsCreateLoading(true);
    setCreateError(null);
    setCreateNeedsSourceUrls(false);
    setCreateResult(null);
    setCreateFilters(null);
    try {
      const result = await commerceClient.createPriceMonitoringRun(buildSelectionBody(false));
      const runId = result.run_id === null || result.run_id === undefined ? "" : String(result.run_id);
      setCreateResult(result);
      setCreateFilters(hierarchyFilterSnapshot);
      setCurrentRun(result);
      setCurrentRunFilters(hierarchyFilterSnapshot);
      stopFetchPolling();
      setFetchResult(null);
      setFetchLogs(null);
      if (runId) {
        setCurrentRunId(runId);
        await refreshRunArtifacts(runId);
      }
    } catch (error) {
      const sourceRequirementMessage = getSourceRequirementErrorMessage(error);
      const missingUrlMessage = getMissingActiveSourceUrlErrorMessage(error, selectedSourceName);
      setCreateNeedsSourceUrls(missingUrlMessage !== null);
      setCreateError(sourceRequirementMessage ?? missingUrlMessage ?? getCommerceApiErrorMessage(error));
    } finally {
      setIsCreateLoading(false);
    }
  };

  const loadRun = async (runId = currentRunId.trim()) => {
    if (!runId) {
      setLoadRunError("Enter a run ID first.");
      return;
    }

    setIsLoadRunLoading(true);
    setLoadRunError(null);
    stopFetchPolling();
    setFetchResult(null);
    setFetchLogs(null);
    try {
      const run = await commerceClient.getPriceMonitoringRun(runId);
      setCurrentRun(run);
      setCurrentRunFilters(null);
      setCurrentRunId(runId);
      if (run.latest_fetch) {
        updateFetchResultState(run.latest_fetch);
        await loadFetchLogs(runId);
        if (isActiveFetchStatus(run.latest_fetch.status)) {
          startFetchPolling(runId);
        }
      }
      await refreshRunArtifacts(runId);
    } catch (error) {
      const isMissingRun = error instanceof CommerceApiError && error.status === 404;
      const message = isMissingRun
        ? `Saved Price Monitoring run ${runId} was not found. The saved run selection was cleared.`
        : getCommerceApiErrorMessage(error);
      if (isMissingRun) {
        setCurrentRunId("");
        setCurrentRun(null);
        setCurrentRunFilters(null);
        setFetchResult(null);
        setFetchLogs(null);
        setRunArtifacts([]);
        setPersistedState((current) => ({
          ...current,
          currentRunId: "",
          currentExecutionId: "",
        }));
      } else {
        setCurrentRunId(runId);
        await refreshRunArtifacts(runId);
      }
      setLoadRunError(message);
    } finally {
      setIsLoadRunLoading(false);
    }
  };

  const fetchPrices = async () => {
    const runId = currentRunId.trim();
    if (!runId) {
      setFetchError("Enter or create a run ID first.");
      return;
    }

    if (!isPriceMonitoringDbAvailable(dbStatus)) {
      setFetchError(getPriceMonitoringDbBlockingMessage(dbStatus));
      return;
    }

    setIsFetchLoading(true);
    setFetchError(null);
    setFetchResult(null);
    setFetchLogs(null);
    stopFetchPolling();
    try {
      const result = await commerceClient.fetchPriceMonitoringRun(runId, {
        source: fetchSource || null,
        catalog_url: catalogUrl.trim() || null,
      });
      updateFetchResultState(result);
      await loadFetchLogs(runId);
      if (isActiveFetchStatus(result.status)) {
        startFetchPolling(runId);
      } else if (isTerminalFetchStatus(result.status)) {
        await finishTerminalFetch(runId, result);
      }
    } catch (error) {
      if (error instanceof CommerceApiError && error.status === 409) {
        setFetchError("A fetch is already queued or running for this run. Adopting the active execution.");
        try {
          const latest = await commerceClient.getPriceMonitoringFetch(runId);
          updateFetchResultState(latest);
          await loadFetchLogs(runId);
          if (isActiveFetchStatus(latest.status)) {
            startFetchPolling(runId);
          }
        } catch (latestError) {
          setFetchError(
            `A fetch is already active, but the latest execution could not be loaded: ${getCommerceApiErrorMessage(latestError)}`,
          );
        }
      } else {
        setFetchError(getCommerceApiErrorMessage(error));
      }
    } finally {
      setIsFetchLoading(false);
    }
  };

  const cancelFetch = async () => {
    const runId = currentRunId.trim();
    if (!runId) {
      setFetchError("Enter or create a run ID first.");
      return;
    }

    if (!isPriceMonitoringDbAvailable(dbStatus)) {
      setFetchError(getPriceMonitoringDbBlockingMessage(dbStatus));
      return;
    }

    const confirmed = window.confirm(
      `Cancel monitoring for run ${runId}? This marks the source URL monitoring execution as cancelled. Active in-process work may finish in the background.`,
    );
    if (!confirmed) {
      return;
    }

    setIsCancelFetchLoading(true);
    setFetchError(null);
    try {
      const result = await commerceClient.cancelPriceMonitoringFetch(
        runId,
        "cancelled from Price Monitoring page",
      );
      updateFetchResultState(result);
      await loadFetchLogs(runId);
      if (isCancelledFetchStatus(result.status) || isTerminalFetchStatus(result.status)) {
        stopFetchPolling();
      }
    } catch (error) {
      setFetchError(getCommerceApiErrorMessage(error));
    } finally {
      setIsCancelFetchLoading(false);
    }
  };

  useEffect(() => {
    const runId = currentRunId.trim();
    if (restoredRunLoadedRef.current || !runId) {
      return;
    }

    restoredRunLoadedRef.current = true;
    void loadRun(runId);
  });

  const loadReview = async () => {
    const runId = currentRunId.trim();
    if (!runId) {
      setReviewError("Enter or create a run ID first.");
      return;
    }

    if (!isPriceMonitoringDbAvailable(dbStatus)) {
      setReviewError(getPriceMonitoringDbBlockingMessage(dbStatus));
      return;
    }

    if (isActiveFetchStatus(fetchResult?.status)) {
      setReviewError("Fetch is queued or running. Load review after the fetch reaches a terminal status.");
      return;
    }

    setIsReviewLoading(true);
    setReviewError(null);
    setReview(null);
    try {
      const nextReview = await commerceClient.getPriceMonitoringReview(runId, {
        enriched_csv_path: enrichedCsvPath.trim() || null,
      });
      setReview(nextReview);
      const nextReviewCsvPath = getArtifactPath(nextReview.review_csv_path);
      if (nextReviewCsvPath) {
        setReviewCsvPath(nextReviewCsvPath);
      }
      const nextEnrichedCsvPath = getArtifactPath(nextReview.enriched_csv_path);
      if (nextEnrichedCsvPath) {
        setEnrichedCsvPath(nextEnrichedCsvPath);
      }
      setRowActions(
        nextReview.items.reduce<Record<string, RowActionState>>((nextActions, item) => {
          nextActions[item.model] = getActionState(item, {});
          return nextActions;
        }, {}),
      );
      await refreshRunArtifacts(runId);
    } catch (error) {
      setReviewError(getCommerceApiErrorMessage(error));
    } finally {
      setIsReviewLoading(false);
    }
  };

  const updateRowAction = (model: string, patch: Partial<RowActionState>) => {
    setRowActions((currentActions) => {
      const currentAction = currentActions[model] ?? {
        selected_action: "",
        undercut_amount: "",
        reason: "",
      };

      return {
        ...currentActions,
        [model]: {
          ...currentAction,
          ...patch,
        },
      };
    });
  };

  const applyRecommendedActions = () => {
    if (!review) {
      return;
    }

    setRowActions(
      review.items.reduce<Record<string, RowActionState>>((nextActions, item) => {
        const recommendedAction = isAction(item.recommended_action) ? item.recommended_action : "";
        const isNotExportable = item.status === "not_exportable";
        nextActions[item.model] =
          recommendedAction && (!isNotExportable || recommendedAction === "ignore")
            ? {
                selected_action: recommendedAction,
                undercut_amount:
                  recommendedAction === "undercut" &&
                  typeof item.undercut_amount === "number" &&
                  Number.isFinite(item.undercut_amount)
                    ? String(item.undercut_amount)
                    : "",
                reason: recommendedAction === "ignore" ? "manual ignore from price review" : "",
              }
            : {
                selected_action: "",
                undercut_amount: "",
                reason: "",
              };
        return nextActions;
      }, {}),
    );
  };

  const clearActions = () => {
    setRowActions({});
  };

  const actionRows = useMemo(() => review?.items ?? [], [review?.items]);
  const actionErrors = useMemo(
    () =>
      actionRows
        .map((row) => {
          const state = getActionState(row, rowActions);
          const error = getActionError(row, state);
          return error ? `${row.model}: ${error}` : null;
        })
        .filter((error): error is string => error !== null),
    [actionRows, rowActions],
  );

  const actionPayload = useMemo<PriceMonitoringReviewAction[]>(
    () =>
      actionRows
        .map((row) => {
          const state = getActionState(row, rowActions);
          if (!state.selected_action) {
            return null;
          }

          const action: PriceMonitoringReviewAction = {
            model: row.model,
            selected_action: state.selected_action,
          };

          if (state.selected_action === "undercut") {
            action.undercut_amount = Number(state.undercut_amount);
          }

          if (state.selected_action === "ignore" && state.reason.trim().length > 0) {
            action.reason = state.reason.trim();
          }

          return action;
        })
        .filter((action): action is PriceMonitoringReviewAction => action !== null),
    [actionRows, rowActions],
  );

  const configuredArtifactRoots = useMemo(
    () => (pathRoots?.artifact_roots ?? []).filter((root) => root.is_configured),
    [pathRoots?.artifact_roots],
  );

  const customExportPathWarning = useMemo(() => {
    if (!useCustomExportPath) {
      return null;
    }

    const outputPath = exportOutputPath.trim();
    if (!outputPath) {
      return "Enter a custom export path or turn off custom export path.";
    }

    if (configuredArtifactRoots.length === 0) {
      return "No configured artifact roots were reported. Set PRICEFETCHER_ARTIFACT_ROOTS before using custom export paths.";
    }

    if (!selectedExportArtifactRoot) {
      return "Choose a configured artifact root before using a custom export path.";
    }

    if (!isPathUnderRoot(outputPath, selectedExportArtifactRoot)) {
      return "Custom export path does not appear to be inside the selected PRICEFETCHER_ARTIFACT_ROOTS directory.";
    }

    return null;
  }, [
    configuredArtifactRoots.length,
    exportOutputPath,
    selectedExportArtifactRoot,
    useCustomExportPath,
  ]);

  const isFetchActive = isActiveFetchStatus(fetchResult?.status);
  const isReviewBlockedByFetch = isFetchActive;
  const dbAvailable = isPriceMonitoringDbAvailable(dbStatus);
  const dbBlockingMessage = getPriceMonitoringDbBlockingMessage(dbStatus);
  const dbActionTitle = dbAvailable ? undefined : dbBlockingMessage;
  const sourceActionTitle = sourceRequired ? SOURCE_REQUIRED_MESSAGE : dbActionTitle;
  const fetchButtonLabel = isFetchLoading
    ? "Starting monitoring..."
    : isFetchActive
      ? "Monitoring running..."
      : "Monitor prices";

  const applyActions = async () => {
    const runId = currentRunId.trim();
    if (!runId) {
      setApplyError("Enter or create a run ID first.");
      return;
    }

    if (!isPriceMonitoringDbAvailable(dbStatus)) {
      setApplyError(getPriceMonitoringDbBlockingMessage(dbStatus));
      return;
    }

    if (isActiveFetchStatus(fetchResult?.status)) {
      setApplyError("Fetch is queued or running. Apply review actions after the fetch reaches a terminal status.");
      return;
    }

    if (actionPayload.length === 0) {
      setApplyError("Choose at least one action before applying.");
      return;
    }

    if (actionErrors.length > 0) {
      setApplyError(actionErrors[0]);
      return;
    }

    setIsApplyLoading(true);
    setApplyError(null);
    setApplyResult(null);
    try {
      const result = await commerceClient.applyPriceMonitoringReviewActions(runId, {
        enriched_csv_path: enrichedCsvPath.trim() || null,
        actions: actionPayload,
      });
      setApplyResult(result);
      const nextReviewCsvPath = getArtifactPath(result.review_csv_path);
      if (nextReviewCsvPath) {
        setReviewCsvPath(nextReviewCsvPath);
      }
      await refreshRunArtifacts(runId);
    } catch (error) {
      setApplyError(getCommerceApiErrorMessage(error));
    } finally {
      setIsApplyLoading(false);
    }
  };

  const exportPriceUpdate = async () => {
    const runId = currentRunId.trim();
    if (!runId) {
      setExportError("Enter or create a run ID first.");
      return;
    }

    if (!isPriceMonitoringDbAvailable(dbStatus)) {
      setExportError(getPriceMonitoringDbBlockingMessage(dbStatus));
      return;
    }

    if (isActiveFetchStatus(fetchResult?.status)) {
      setExportError("Fetch is queued or running. Export after the fetch reaches a terminal status.");
      return;
    }

    if (useCustomExportPath && customExportPathWarning) {
      setExportError(customExportPathWarning);
      return;
    }

    setIsExportLoading(true);
    setExportError(null);
    setExportResult(null);
    try {
      const result = await commerceClient.exportPriceMonitoringPriceUpdate(runId, {
        review_csv_path: reviewCsvPath.trim() || null,
        output_path: useCustomExportPath ? exportOutputPath.trim() || null : null,
      });
      setExportResult(result);
      await refreshRunArtifacts(runId);
    } catch (error) {
      setExportError(getCommerceApiErrorMessage(error));
    } finally {
      setIsExportLoading(false);
    }
  };

  const resetSavedWorkflowState = () => {
    resetPersistedState();
    const initial = initialPriceMonitoringWorkflowState;
    setSource(initial.source);
    setQ(initial.q);
    setSelectedFamily(initial.selectedFamily);
    setSelectedCategory(initial.selectedCategory);
    setSelectedSubCategory(initial.selectedSubCategory);
    setManufacturer(initial.manufacturer);
    setMarketplace(initial.marketplace);
    setSelectedModelText(initial.selectedModelText);
    setExcludedModelText(initial.excludedModelText);
    setIncludeIgnored(initial.includeIgnored);
    setAutomationEligibleOnly(initial.automationEligibleOnly);
    setAtomicOnly(initial.atomicOnly);
    setHasMpn(initial.hasMpn);
    setCurrentRunId(initial.currentRunId);
    setCurrentRun(null);
    setCurrentRunFilters(null);
    setFetchSource(initial.fetchSource);
    setCatalogUrl(initial.catalogUrl);
    setFetchResult(null);
    setFetchLogs(null);
    setEnrichedCsvPath(initial.enrichedCsvPath);
    setStoredMatchStatus(initial.storedMatchStatus);
    setIncludeUnmatchedObservations(initial.includeUnmatchedObservations);
    setStoredModelFilter(initial.storedModelFilter);
    setStoredMpnFilter(initial.storedMpnFilter);
    setReviewCsvPath(initial.reviewCsvPath);
    setUseCustomExportPath(initial.useCustomExportPath);
    setSelectedExportArtifactRoot(initial.selectedExportArtifactRoot);
    setExportOutputPath(initial.exportOutputPath);
    setRowActions({});
    setReview(null);
    setRunArtifacts([]);
    stopFetchPolling();
    restoredRunLoadedRef.current = true;
  };

  return (
    <div className="page-stack price-monitoring-page">
      <section className="page-header">
        <p className="eyebrow">Price Monitoring</p>
        <h2>Competitor price workflow</h2>
        <p>Monitor catalog products that already have active source URLs, review actions, and export CSV only.</p>
        <p>Vendor Sources is where source URLs are discovered, reviewed, imported, and captured.</p>
        <button className="text-button" type="button" onClick={resetSavedWorkflowState}>
          Reset saved Price Monitoring state
        </button>
      </section>

      <PriceMonitoringDbStatusBanner
        status={dbStatus}
        error={dbStatusError}
        isLoading={isDbStatusLoading}
        onRetry={() => void loadDbStatus()}
      />

      <BackendPathsPanel
        roots={pathRoots}
        isLoading={isPathRootsLoading}
        error={pathRootsError}
        onRefresh={() => void loadPathRoots()}
      />

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Create / Preview Run</p>
            <h3>Selection</h3>
          </div>
          <button className="button secondary" type="button" onClick={() => void loadFilters()}>
            Refresh filters
          </button>
        </div>

        {areFiltersLoading ? <LoadingState label="Loading categories and brands..." /> : null}
        {filterError ? <ErrorState message={filterError} onRetry={() => void loadFilters()} /> : null}

        <div className="filter-grid">
          <label title="Choose one Vendor Sources source/vendor. Products need an active URL for this source to be monitored.">
            Source/vendor
            <select value={source} onChange={(event) => setSource(normalizeSelectedSource(event.target.value))}>
              <option value="">Choose one source/vendor</option>
              {sourceUrlFilterOptions.map((option) => (
                <option key={String(option.source_name)} value={String(option.source_name)}>
                  {formatSourceOptionLabel(option)}
                </option>
              ))}
            </select>
          </label>
          {vendorSourceError ? <p className="form-warning">{vendorSourceError}</p> : null}
          {sourceRequired ? <p className="form-warning">{SOURCE_REQUIRED_MESSAGE}</p> : null}
          <label>
            Family
            <select
              value={selectedFamily}
              onChange={(event) => {
                setSelectedFamily(event.target.value);
                setSelectedCategory("");
                setSelectedSubCategory("");
              }}
            >
              <option value="">All families</option>
              {familyOptions.map((item) => (
                <option key={item.value} value={item.value}>
                  {formatHierarchyOptionLabel(item)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Category
            <select
              value={selectedCategory}
              onChange={(event) => {
                setSelectedCategory(event.target.value);
                setSelectedSubCategory("");
              }}
              disabled={!selectedFamily}
            >
              <option value="">All categories</option>
              {categoryOptions.map((item) => (
                <option key={item.value} value={item.value}>
                  {formatHierarchyOptionLabel(item)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Sub-Category
            <select
              value={selectedSubCategory}
              onChange={(event) => setSelectedSubCategory(event.target.value)}
              disabled={!selectedFamily || !selectedCategory}
            >
              <option value="">All sub-categories</option>
              {subCategoryOptions.map((item) => (
                <option key={item.value} value={item.value}>
                  {formatHierarchyOptionLabel(item)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Manufacturer
            <select value={manufacturer} onChange={(event) => setManufacturer(event.target.value)}>
              <option value="">All manufacturers</option>
              {brands.map((item) => (
                <option key={item.manufacturer} value={item.manufacturer}>
                  {item.manufacturer}
                  {formatOptionCount(item.count)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Catalog listing flag
            <select value={marketplace} onChange={(event) => setMarketplace(event.target.value as MarketplaceFilter)}>
              <option value="all">All</option>
              <option value="bestprice">BestPrice</option>
              <option value="skroutz">Skroutz</option>
              <option value="both">Both</option>
              <option value="none">None</option>
            </select>
          </label>
          <label>
            Catalog text filter
            <input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Model or product name" />
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={includeIgnored}
              onChange={(event) => setIncludeIgnored(event.target.checked)}
            />
            Include ignored
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={automationEligibleOnly}
              onChange={(event) => setAutomationEligibleOnly(event.target.checked)}
            />
            Automation eligible only
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={atomicOnly}
              onChange={(event) => setAtomicOnly(event.target.checked)}
            />
            Atomic only
          </label>
          <label className="checkbox-row">
            <input type="checkbox" checked={hasMpn} onChange={(event) => setHasMpn(event.target.checked)} />
            Has MPN
          </label>
        </div>

        <div className="split-grid">
          <label>
            Selected models
            <textarea
              value={selectedModelText}
              onChange={(event) => setSelectedModelText(event.target.value)}
              rows={5}
              placeholder={"005606\n123456"}
            />
          </label>
          <label>
            Excluded models
            <textarea
              value={excludedModelText}
              onChange={(event) => setExcludedModelText(event.target.value)}
              rows={5}
              placeholder="One model per line or comma-separated"
            />
          </label>
        </div>

        <div className="button-row">
          <button
            className="button secondary"
            type="button"
            disabled={isPreviewLoading || isCreateLoading || !dbAvailable || sourceRequired}
            title={sourceActionTitle}
            onClick={() => void previewSelection()}
          >
            {isPreviewLoading ? "Previewing..." : "Preview"}
          </button>
          <button
            className="button primary"
            type="button"
            disabled={isCreateLoading || isPreviewLoading || !dbAvailable || sourceRequired}
            title={sourceActionTitle}
            onClick={() => void createRun()}
          >
            {isCreateLoading ? "Creating..." : "Create run"}
          </button>
        </div>

        {previewError ? (
          <>
            <ErrorState message={previewError} />
            {previewNeedsSourceUrls ? <NoMonitorableProductsActionCard source={selectedSourceName} /> : null}
            <PriceMonitoringSetupHint />
          </>
        ) : null}
        {previewResult ? (
          <SelectionResultBlock result={previewResult} filters={previewFilters} />
        ) : null}
        {createError ? (
          <>
            <ErrorState message={createError} />
            {createNeedsSourceUrls ? <NoMonitorableProductsActionCard source={selectedSourceName} /> : null}
            <PriceMonitoringSetupHint />
          </>
        ) : null}
        {createResult ? (
          <SelectionResultBlock result={createResult} filters={createFilters} />
        ) : null}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Existing Run / Run Status</p>
            <h3>Current run</h3>
          </div>
          <button
            className="button secondary"
            type="button"
            onClick={() => void Promise.all([loadRuns(), loadDbStatus()])}
          >
            Refresh runs
          </button>
        </div>

        <div className="toolbar">
          <label className="inline-field">
            Run ID
            <input value={currentRunId} onChange={(event) => setCurrentRunId(event.target.value)} />
          </label>
          <button
            className="button secondary"
            type="button"
            disabled={isLoadRunLoading}
            onClick={() => void loadRun()}
          >
            {isLoadRunLoading ? "Loading..." : "Load run"}
          </button>
        </div>

        {isRunsLoading ? <LoadingState label="Loading run list..." /> : null}
        {runListMessage ? <p className="state-block">{runListMessage}</p> : null}
        {loadRunError ? (
          <>
            <ErrorState message={loadRunError} />
            <PriceMonitoringSetupHint />
          </>
        ) : null}

        {runs.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Status</th>
                  <th>Source/vendor</th>
                  <th>Selected</th>
                  <th>Latest fetch</th>
                  <th>Execution</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.slice(0, 10).map((run, index) => {
                  const runId = String(run.run_id ?? run.id ?? "");
                  const latestFetch = run.latest_fetch;
                  return (
                    <tr key={runId || index}>
                      <td>{formatValue(runId)}</td>
                      <td>{formatValue(run.status)}</td>
                      <td>{formatSelectedSource(run.source)}</td>
                      <td>{formatValue(run.selected_count)}</td>
                      <td>
                        {latestFetch?.status ? (
                          <span className={`status-badge ${getFetchStatusTone(latestFetch.status)}`}>
                            {formatFetchStatus(latestFetch.status)}
                          </span>
                        ) : (
                          "-"
                        )}
                      </td>
                      <td>{formatValue(latestFetch?.execution_id)}</td>
                      <td>{formatValue(run.created_at)}</td>
                      <td>
                        <button className="button secondary" type="button" onClick={() => void loadRun(runId)}>
                          Use
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}

        {currentRun ? <RunSummaryBlock run={currentRun} filters={currentRunFilters} /> : null}
        {currentRunId.trim() ? (
          <div className="state-block">
            <div className="section-heading">
              <strong>Run artifacts</strong>
              <button
                className="button secondary"
                type="button"
                disabled={isArtifactsLoading}
                onClick={() => void refreshRunArtifacts()}
              >
                {isArtifactsLoading ? "Refreshing..." : "Refresh artifacts"}
              </button>
            </div>
            {artifactWarning ? <p className="muted">{artifactWarning}</p> : null}
            {isArtifactsLoading ? <LoadingState label="Loading artifacts..." /> : null}
            <ArtifactList
              title="Price monitoring run artifacts"
              items={runArtifacts}
              onPreview={previewArtifact}
              getDownloadUrl={commerceClient.getArtifactDownloadUrl}
            />
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Source URL Monitoring</p>
            <h3>Monitor active source URLs</h3>
          </div>
        </div>

        <div className="filter-grid">
          <label title="Compatibility override for older backends. The default uses the run source/vendor.">
            Source/vendor override
            <select value={fetchSource} onChange={(event) => setFetchSource(event.target.value as SourceOverride)}>
              <option value="">Default from run</option>
              {sourceUrlFilterOptions.map((option) => (
                <option key={String(option.source_name)} value={String(option.source_name)}>
                  {formatSourceOptionLabel(option)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Catalog URL diagnostic
            <input
              value={catalogUrl}
              onChange={(event) => setCatalogUrl(event.target.value)}
              placeholder="Optional backend diagnostic hint"
            />
          </label>
        </div>

        <div className="button-row">
          <button
            className="button primary"
            type="button"
            disabled={isFetchLoading || isFetchActive || !dbAvailable}
            title={dbActionTitle}
            onClick={() => void fetchPrices()}
          >
            {fetchButtonLabel}
          </button>
          {isFetchActive ? (
            <button
              className="button danger"
              type="button"
              disabled={isCancelFetchLoading || !dbAvailable}
              title={dbActionTitle}
              onClick={() => void cancelFetch()}
            >
              {isCancelFetchLoading ? "Cancelling..." : "Cancel monitoring"}
            </button>
          ) : null}
        </div>

        {fetchResult?.status ? (
          <p className="state-block">
            <span className={`status-badge ${getFetchStatusTone(fetchResult.status)}`}>
              {formatFetchStatus(fetchResult.status)}
            </span>
          </p>
        ) : null}

        {fetchError ? (
          <>
            <ErrorState message={fetchError} />
            <PriceMonitoringSetupHint />
          </>
        ) : null}
        {fetchResult ? <FetchResultBlock result={fetchResult} onPreview={previewArtifact} /> : null}
        <FetchLogsPanel
          logs={fetchLogs}
          error={fetchLogsError}
          isLoading={isFetchLogsLoading}
          onRefresh={() => void loadFetchLogs(currentRunId.trim())}
        />
      </section>

      <StoredObservationsSection
        runId={currentRunId.trim()}
        dbStatus={dbStatus}
        dbStatusError={dbStatusError}
        isDbStatusLoading={isDbStatusLoading}
        isLoading={isStoredObservationLoading}
        observations={storedObservations}
        catalogSnapshot={catalogSnapshot}
        observationError={storedObservationError}
        catalogSnapshotError={catalogSnapshotError}
        fetchResult={fetchResult}
        matchStatus={storedMatchStatus}
        includeUnmatched={includeUnmatchedObservations}
        modelFilter={storedModelFilter}
        mpnFilter={storedMpnFilter}
        onMatchStatusChange={setStoredMatchStatus}
        onIncludeUnmatchedChange={setIncludeUnmatchedObservations}
        onModelFilterChange={setStoredModelFilter}
        onMpnFilterChange={setStoredMpnFilter}
        onRefresh={() => void loadStoredObservations(currentRunId.trim())}
        onRetryDbStatus={() => void loadDbStatus()}
      />

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Review & Actions</p>
            <h3>Competitor results</h3>
          </div>
          <div className="button-row">
            <button
              className="button secondary"
              type="button"
              onClick={applyRecommendedActions}
              disabled={!review || isReviewBlockedByFetch || !dbAvailable}
              title={isReviewBlockedByFetch ? "Fetch is queued or running." : dbActionTitle}
            >
              Apply recommended actions
            </button>
            <button className="button secondary" type="button" onClick={clearActions} disabled={!review}>
              Clear actions
            </button>
          </div>
        </div>

        <div className="toolbar">
          <label className="inline-field wide">
            Enriched CSV path
            <input
              value={enrichedCsvPath}
              onChange={(event) => setEnrichedCsvPath(event.target.value)}
              placeholder="Leave empty for backend discovery"
            />
          </label>
          <button
            className="button primary"
            type="button"
            disabled={isReviewLoading || isReviewBlockedByFetch || !dbAvailable}
            title={isReviewBlockedByFetch ? "Fetch is queued or running." : dbActionTitle}
            onClick={() => void loadReview()}
          >
            {isReviewLoading ? "Loading review..." : "Load review"}
          </button>
        </div>

        {reviewError ? (
          <>
            <ErrorState message={reviewError} />
            <PriceMonitoringSetupHint />
          </>
        ) : null}
        {review ? (
          <>
            <dl className="summary-grid">
              <SummaryItem label="Run ID" value={review.run_id} />
              {Object.entries(review.summary ?? {}).map(([key, value]) => (
                <SummaryItem key={key} label={key} value={value} />
              ))}
            </dl>
            <ReviewArtifactsBlock review={review} onPreview={previewArtifact} />

            {review.items.length === 0 ? (
              <EmptyState title="No review rows" message="The backend returned an empty review." />
            ) : (
              <div className="table-wrap review-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Model</th>
                      <th>Name</th>
                      <th>MPN</th>
                      <th>Current</th>
                      <th>Competitor</th>
                      <th>Store</th>
                      <th>URL</th>
                      <th>Delta</th>
                      <th>Delta %</th>
                      <th>Recommended</th>
                      <th>Action</th>
                      <th>Undercut</th>
                      <th>Target</th>
                      <th>Reason</th>
                      <th>Status</th>
                      <th>Warnings</th>
                    </tr>
                  </thead>
                  <tbody>
                    {review.items.map((item) => {
                      const state = getActionState(item, rowActions);
                      const targetPrice = computeTargetPrice(item, state);
                      const actionError = getActionError(item, state);

                      return (
                        <tr key={item.model}>
                          <td className="nowrap-cell">{item.model}</td>
                          <td>{formatValue(item.name)}</td>
                          <td>{formatValue(item.mpn)}</td>
                          <td className="nowrap-cell">{formatMoney(item.current_price)}</td>
                          <td className="nowrap-cell">{formatMoney(item.competitor_price)}</td>
                          <td>{formatValue(item.competitor_store)}</td>
                          <td className="review-url-cell">
                            {item.competitor_url ? (
                              <a href={item.competitor_url} target="_blank" rel="noreferrer">
                                Open
                              </a>
                            ) : (
                              "-"
                            )}
                          </td>
                          <td>{formatNumber(item.price_delta)}</td>
                          <td>{formatNumber(item.price_delta_percent)}</td>
                          <td>{formatValue(item.recommended_action)}</td>
                          <td>
                            <select
                              value={state.selected_action}
                              disabled={!dbAvailable}
                              onChange={(event) =>
                                updateRowAction(item.model, {
                                  selected_action: event.target.value as "" | PriceMonitoringAction,
                                })
                              }
                            >
                              <option value="">No action</option>
                              <option value="match_price">match_price</option>
                              <option value="undercut">undercut</option>
                              <option value="ignore">ignore</option>
                            </select>
                            {actionError ? <small className="field-error">{actionError}</small> : null}
                          </td>
                          <td>
                            <input
                              className="table-input small-input"
                              type="number"
                              min="0"
                              step="0.01"
                              value={state.undercut_amount}
                              disabled={state.selected_action !== "undercut" || !dbAvailable}
                              onChange={(event) =>
                                updateRowAction(item.model, { undercut_amount: event.target.value })
                              }
                            />
                          </td>
                          <td className="nowrap-cell">{formatMoney(targetPrice)}</td>
                          <td>
                            <input
                              className="table-input"
                              value={state.reason}
                              disabled={state.selected_action !== "ignore" || !dbAvailable}
                              onChange={(event) => updateRowAction(item.model, { reason: event.target.value })}
                              placeholder="Optional"
                            />
                          </td>
                          <td>{formatValue(item.status)}</td>
                          <td>{item.warnings?.join(", ") || "-"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {actionErrors.length > 0 ? (
              <div className="form-error">
                <strong>Action validation</strong>
                <ul>
                  {actionErrors.slice(0, 5).map((error) => (
                    <li key={error}>{error}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            <button
              className="button primary inline-button"
              type="button"
              disabled={isApplyLoading || isReviewBlockedByFetch || !dbAvailable}
              title={isReviewBlockedByFetch ? "Fetch is queued or running." : dbActionTitle}
              onClick={() => void applyActions()}
            >
              {isApplyLoading ? "Applying actions..." : "Apply actions"}
            </button>
          </>
        ) : null}

        {applyError ? (
          <>
            <ErrorState message={applyError} />
            <PriceMonitoringSetupHint />
          </>
        ) : null}
        {applyResult ? (
          <ApplyActionsResultBlock result={applyResult} onPreview={previewArtifact} />
        ) : null}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Export Price Update CSV</p>
            <h3>OpenCart CSV export</h3>
          </div>
        </div>
        <p className="state-block">
          This only exports an OpenCart price update CSV. It does not update OpenCart automatically.
        </p>
        <div className="filter-grid">
          <label>
            Review CSV path
            <input
              value={reviewCsvPath}
              onChange={(event) => setReviewCsvPath(event.target.value)}
              placeholder="Leave empty for backend default"
            />
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={useCustomExportPath}
              onChange={(event) => setUseCustomExportPath(event.target.checked)}
            />
            Use custom export path
          </label>
        </div>
        {useCustomExportPath ? (
          <div className="state-block">
            <strong>Custom export path</strong>
            <p className="muted">
              Custom export paths must be inside PRICEFETCHER_ARTIFACT_ROOTS.
            </p>
            <div className="filter-grid">
              <label>
                Configured artifact root
                <select
                  value={selectedExportArtifactRoot}
                  onChange={(event) => setSelectedExportArtifactRoot(event.target.value)}
                >
                  <option value="">Choose configured root</option>
                  {configuredArtifactRoots.map((root) => (
                    <option key={root.path} value={root.path}>
                      {root.path}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Output path
                <input
                  value={exportOutputPath}
                  onChange={(event) => setExportOutputPath(event.target.value)}
                  placeholder="D:\\PriceFetcher\\output\\custom\\opencart_price_update.csv"
                />
              </label>
            </div>
            {configuredArtifactRoots.length > 0 ? (
              <div className="compact-list">
                <strong>Configured artifact roots</strong>
                <ul>
                  {configuredArtifactRoots.map((root) => (
                    <li key={root.path}>
                      <code>{root.path}</code>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="form-error">
                No configured artifact roots were reported by the backend.
              </p>
            )}
            {customExportPathWarning ? (
              <p className="form-error">{customExportPathWarning}</p>
            ) : null}
          </div>
        ) : (
          <p className="muted">
            Output path is omitted so the backend writes to the run folder.
          </p>
        )}
        <button
          className="button primary inline-button"
          type="button"
          disabled={isExportLoading || isReviewBlockedByFetch || !dbAvailable}
          title={isReviewBlockedByFetch ? "Fetch is queued or running." : dbActionTitle}
          onClick={() => void exportPriceUpdate()}
        >
          {isExportLoading ? "Exporting..." : "Export OpenCart price update CSV"}
        </button>
        {exportError ? (
          <>
            <ErrorState message={exportError} />
            <PriceMonitoringSetupHint />
          </>
        ) : null}
        {exportResult ? <ExportResultBlock result={exportResult} onPreview={previewArtifact} /> : null}
      </section>
    </div>
  );
}
