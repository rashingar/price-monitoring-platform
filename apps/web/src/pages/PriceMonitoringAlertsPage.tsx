import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CommerceApiError, commerceClient, getCommerceApiErrorMessage } from "../api/commerceClient";
import type {
  AlertEvent,
  AlertEventStatus,
  AlertRule,
  CreateAlertRuleBody,
  EvaluateAlertsResponse,
  PriceMonitoringDbStatus,
  UpdateAlertRuleBody,
} from "../api/commerceTypes";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";
import { PriceMonitoringDbStatusBanner } from "../components/priceMonitoring/PriceMonitoringDbStatusBanner";
import {
  getPriceMonitoringDbBlockingMessage,
  isPriceMonitoringDbReady,
} from "../api/priceMonitoringDbGate";
import { usePersistentPageState } from "../hooks/usePersistentPageState";

type AlertStatusFilter = AlertEventStatus | "all";
type RuleTargetMode = "product_id" | "catalog_model" | "catalog_mpn";
const PRICE_ALERTS_STATE_KEY = "product-agent-ui:price-alerts:v1";

interface AlertCounts {
  open: number;
  acknowledged: number;
  resolved: number;
  total: number;
}

interface RuleFormState {
  name: string;
  targetMode: RuleTargetMode;
  product_id: string;
  catalog_source: string;
  model: string;
  mpn: string;
  threshold_amount: string;
  threshold_percent: string;
  active: boolean;
}

interface PriceAlertsPageState {
  statusFilter: AlertStatusFilter;
  modelFilter: string;
  runIdFilter: string;
  productIdFilter: string;
  ruleForm: RuleFormState;
  editingRuleId: string | number | null;
  evaluateRunId: string;
}

const EMPTY_COUNTS: AlertCounts = {
  open: 0,
  acknowledged: 0,
  resolved: 0,
  total: 0,
};

function isDbRequiredError(error: unknown): boolean {
  return error instanceof CommerceApiError && error.status === 503;
}

export function parseNumberLike(value: unknown): number | null {
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

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return String(value);
}

export function formatNumber(value: unknown): string {
  const parsed = parseNumberLike(value);
  if (parsed === null) {
    return "-";
  }

  return parsed.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function formatMoney(value: unknown, currency = "EUR"): string {
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

export function formatPercent(value: unknown): string {
  const parsed = parseNumberLike(value);
  if (parsed === null) {
    return "-";
  }

  return `${parsed.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
}

export function formatDateTime(value: unknown): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    return "-";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString();
}

export function formatAlertStatus(value: unknown): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    return "-";
  }

  return value.replace(/_/g, " ");
}

export function formatRuleType(value: unknown): string {
  if (value === "competitor_below_own_price") {
    return "Competitor below own price";
  }

  return formatValue(value).replace(/_/g, " ");
}

function getStatusTone(status: unknown): string {
  if (status === "open") {
    return "danger";
  }

  if (status === "acknowledged") {
    return "warning";
  }

  if (status === "resolved") {
    return "ok";
  }

  return "neutral";
}

function getInitialRuleForm(searchParams: URLSearchParams): RuleFormState {
  const productId = searchParams.get("product_id") ?? "";
  const catalogSource = searchParams.get("catalog_source") ?? "";
  const model = searchParams.get("model") ?? "";
  const mpn = searchParams.get("mpn") ?? "";
  const targetMode: RuleTargetMode = productId
    ? "product_id"
    : model && catalogSource
      ? "catalog_model"
      : "catalog_mpn";

  return {
    name: searchParams.get("name") ?? "",
    targetMode,
    product_id: productId,
    catalog_source: catalogSource,
    model,
    mpn,
    threshold_amount: "",
    threshold_percent: "",
    active: true,
  };
}

function trimToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function getPositiveNumber(value: string, label: string): { value: number | null; error: string | null } {
  if (value.trim().length === 0) {
    return { value: null, error: null };
  }

  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return { value: null, error: `${label} must be a positive number.` };
  }

  return { value: parsed, error: null };
}

function buildRuleBody(form: RuleFormState): { body: CreateAlertRuleBody; error: string | null } {
  const amount = getPositiveNumber(form.threshold_amount, "Threshold amount");
  if (amount.error) {
    return { body: makeEmptyRuleBody(), error: amount.error };
  }

  const percent = getPositiveNumber(form.threshold_percent, "Threshold percent");
  if (percent.error) {
    return { body: makeEmptyRuleBody(), error: percent.error };
  }

  const productIdText = form.product_id.trim();
  const productId = productIdText ? Number(productIdText) : null;
  if (form.targetMode === "product_id") {
    if (!productIdText || !Number.isFinite(productId) || productId === null || productId <= 0) {
      return { body: makeEmptyRuleBody(), error: "Product ID must be a positive number." };
    }
  }

  if (form.targetMode === "catalog_model" && (!form.catalog_source.trim() || !form.model.trim())) {
    return {
      body: makeEmptyRuleBody(),
      error: "Catalog source and model are required for a catalog/model target.",
    };
  }

  if (form.targetMode === "catalog_mpn" && (!form.catalog_source.trim() || !form.mpn.trim())) {
    return {
      body: makeEmptyRuleBody(),
      error: "Catalog source and MPN are required for a catalog/MPN target.",
    };
  }

  return {
    body: {
      name: trimToNull(form.name),
      rule_type: "competitor_below_own_price",
      product_id: form.targetMode === "product_id" ? productId : null,
      catalog_source: form.targetMode === "product_id" ? null : trimToNull(form.catalog_source),
      model: form.targetMode === "catalog_model" ? trimToNull(form.model) : null,
      mpn: form.targetMode === "catalog_mpn" ? trimToNull(form.mpn) : null,
      threshold_amount: amount.value,
      threshold_percent: percent.value,
      active: form.active,
    },
    error: null,
  };
}

function makeEmptyRuleBody(): CreateAlertRuleBody {
  return {
    name: null,
    rule_type: "competitor_below_own_price",
    product_id: null,
    catalog_source: null,
    model: null,
    mpn: null,
    threshold_amount: null,
    threshold_percent: null,
    active: true,
  };
}

function makeFormFromRule(rule: AlertRule): RuleFormState {
  const hasProductId = rule.product_id !== null && rule.product_id !== undefined && rule.product_id !== "";
  const hasModel = typeof rule.model === "string" && rule.model.trim().length > 0;
  const targetMode: RuleTargetMode = hasProductId ? "product_id" : hasModel ? "catalog_model" : "catalog_mpn";

  return {
    name: typeof rule.name === "string" ? rule.name : "",
    targetMode,
    product_id: hasProductId ? String(rule.product_id) : "",
    catalog_source: typeof rule.catalog_source === "string" ? rule.catalog_source : "",
    model: typeof rule.model === "string" ? rule.model : "",
    mpn: typeof rule.mpn === "string" ? rule.mpn : "",
    threshold_amount:
      rule.threshold_amount !== null && rule.threshold_amount !== undefined ? String(rule.threshold_amount) : "",
    threshold_percent:
      rule.threshold_percent !== null && rule.threshold_percent !== undefined ? String(rule.threshold_percent) : "",
    active: rule.active !== false,
  };
}

function getRuleTarget(rule: AlertRule): string {
  if (rule.product_id !== null && rule.product_id !== undefined && rule.product_id !== "") {
    return `Product ID ${rule.product_id}`;
  }

  if (rule.catalog_source && rule.model) {
    return `${rule.catalog_source} / ${rule.model}`;
  }

  if (rule.catalog_source && rule.mpn) {
    return `${rule.catalog_source} / MPN ${rule.mpn}`;
  }

  return "-";
}

function getEventId(event: AlertEvent): string | number | null {
  return event.id ?? null;
}

function getRunId(event: AlertEvent): string {
  const value = event.run_id ?? event.monitoring_run_id;
  return value === null || value === undefined ? "" : String(value);
}

function SummaryItem({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{formatValue(value)}</dd>
    </div>
  );
}

function ProductCell({ event }: { event: AlertEvent }) {
  return (
    <div className="compact-list">
      <strong>{formatValue(event.model)}</strong>
      {event.mpn ? <span className="muted">MPN {event.mpn}</span> : null}
      {event.product_id ? <span className="muted">Product ID {event.product_id}</span> : null}
    </div>
  );
}

function EvaluateResultBlock({ result }: { result: EvaluateAlertsResponse }) {
  return (
    <div className="state-block">
      <strong>Evaluation result</strong>
      <dl className="summary-grid">
        <SummaryItem label="Run ID" value={result.run_id} />
        <SummaryItem label="Status" value={result.status} />
        <SummaryItem label="Rules evaluated" value={result.evaluated_rule_count} />
        <SummaryItem label="Observations evaluated" value={result.evaluated_observation_count} />
        <SummaryItem label="Created events" value={result.created_event_count} />
        <SummaryItem label="Duplicate events" value={result.duplicate_event_count} />
        <SummaryItem label="Skipped" value={result.skipped_count} />
      </dl>
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
    </div>
  );
}

export function PriceMonitoringAlertsPage() {
  const [searchParams] = useSearchParams();
  const searchText = searchParams.toString();
  const initialRuleForm = useMemo(() => getInitialRuleForm(new URLSearchParams(searchText)), [searchText]);
  const initialPersistedAlertsState = useMemo<PriceAlertsPageState>(
    () => ({
      statusFilter: "open",
      modelFilter: "",
      runIdFilter: "",
      productIdFilter: "",
      ruleForm: initialRuleForm,
      editingRuleId: null,
      evaluateRunId: "",
    }),
    [initialRuleForm],
  );
  const [persistedState, setPersistedState, resetPersistedState] =
    usePersistentPageState<PriceAlertsPageState>(
      PRICE_ALERTS_STATE_KEY,
      initialPersistedAlertsState,
    );

  const [counts, setCounts] = useState<AlertCounts>(EMPTY_COUNTS);
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [eventCount, setEventCount] = useState(0);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [statusFilter, setStatusFilter] = useState<AlertStatusFilter>(persistedState.statusFilter);
  const [modelFilter, setModelFilter] = useState(persistedState.modelFilter);
  const [runIdFilter, setRunIdFilter] = useState(persistedState.runIdFilter);
  const [productIdFilter, setProductIdFilter] = useState(persistedState.productIdFilter);
  const [isEventsLoading, setIsEventsLoading] = useState(false);
  const [isCountsLoading, setIsCountsLoading] = useState(false);
  const [isRulesLoading, setIsRulesLoading] = useState(false);
  const [eventsError, setEventsError] = useState<string | null>(null);
  const [countsError, setCountsError] = useState<string | null>(null);
  const [rulesError, setRulesError] = useState<string | null>(null);
  const [actionEventId, setActionEventId] = useState<string | number | null>(null);
  const [ruleActionId, setRuleActionId] = useState<string | number | null>(null);
  const [ruleForm, setRuleForm] = useState<RuleFormState>(persistedState.ruleForm);
  const [editingRuleId, setEditingRuleId] = useState<string | number | null>(
    persistedState.editingRuleId,
  );
  const [formError, setFormError] = useState<string | null>(null);
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [isSavingRule, setIsSavingRule] = useState(false);
  const [evaluateRunId, setEvaluateRunId] = useState(persistedState.evaluateRunId);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [evaluateError, setEvaluateError] = useState<string | null>(null);
  const [evaluateResult, setEvaluateResult] = useState<EvaluateAlertsResponse | null>(null);
  const [dbStatus, setDbStatus] = useState<PriceMonitoringDbStatus | null>(null);
  const [dbStatusError, setDbStatusError] = useState<string | null>(null);
  const [isDbStatusLoading, setIsDbStatusLoading] = useState(false);

  useEffect(() => {
    if (searchText) {
      setRuleForm(initialRuleForm);
    }
  }, [initialRuleForm, searchText]);

  useEffect(() => {
    setPersistedState({
      statusFilter,
      modelFilter,
      runIdFilter,
      productIdFilter,
      ruleForm,
      editingRuleId,
      evaluateRunId,
    });
  }, [
    editingRuleId,
    evaluateRunId,
    modelFilter,
    productIdFilter,
    ruleForm,
    runIdFilter,
    setPersistedState,
    statusFilter,
  ]);

  const loadCounts = useCallback(async (signal?: AbortSignal) => {
    setIsCountsLoading(true);
    try {
      const [open, acknowledged, resolved] = await Promise.all([
        commerceClient.listPriceMonitoringAlertEvents({ status: "open", limit: 1, offset: 0 }, signal),
        commerceClient.listPriceMonitoringAlertEvents({ status: "acknowledged", limit: 1, offset: 0 }, signal),
        commerceClient.listPriceMonitoringAlertEvents({ status: "resolved", limit: 1, offset: 0 }, signal),
      ]);

      if (signal?.aborted) {
        return;
      }

      setCounts({
        open: open.count,
        acknowledged: acknowledged.count,
        resolved: resolved.count,
        total: open.count + acknowledged.count + resolved.count,
      });
      setCountsError(null);
    } catch (error) {
      if (!signal?.aborted) {
        setCountsError(isDbRequiredError(error) ? null : getCommerceApiErrorMessage(error));
        setCounts(EMPTY_COUNTS);
      }
    } finally {
      if (!signal?.aborted) {
        setIsCountsLoading(false);
      }
    }
  }, []);

  const loadEvents = useCallback(
    async (signal?: AbortSignal) => {
      setIsEventsLoading(true);
      try {
        const response = await commerceClient.listPriceMonitoringAlertEvents(
          {
            status: statusFilter,
            model: trimToNull(modelFilter),
            run_id: trimToNull(runIdFilter),
            product_id: trimToNull(productIdFilter),
            limit: 100,
            offset: 0,
          },
          signal,
        );

        if (signal?.aborted) {
          return;
        }

        setEvents(response.items);
        setEventCount(response.count);
        setEventsError(null);
      } catch (error) {
        if (!signal?.aborted) {
          setEventsError(isDbRequiredError(error) ? null : getCommerceApiErrorMessage(error));
          setEvents([]);
          setEventCount(0);
        }
      } finally {
        if (!signal?.aborted) {
          setIsEventsLoading(false);
        }
      }
    },
    [modelFilter, productIdFilter, runIdFilter, statusFilter],
  );

  const loadRules = useCallback(async (signal?: AbortSignal) => {
    setIsRulesLoading(true);
    try {
      const response = await commerceClient.listPriceMonitoringAlertRules({ limit: 100, offset: 0 }, signal);
      if (signal?.aborted) {
        return;
      }

      setRules(response.items);
      setRulesError(null);
    } catch (error) {
      if (!signal?.aborted) {
        setRulesError(isDbRequiredError(error) ? null : getCommerceApiErrorMessage(error));
        setRules([]);
      }
    } finally {
      if (!signal?.aborted) {
        setIsRulesLoading(false);
      }
    }
  }, []);

  const loadDbStatus = useCallback(async (signal?: AbortSignal) => {
    setIsDbStatusLoading(true);
    setDbStatusError(null);
    try {
      const status = await commerceClient.getPriceMonitoringDbStatus(signal);
      if (signal?.aborted) {
        return;
      }

      setDbStatus(status);
    } catch (error) {
      if (!signal?.aborted) {
        setDbStatus(null);
        setDbStatusError(getCommerceApiErrorMessage(error));
      }
    } finally {
      if (!signal?.aborted) {
        setIsDbStatusLoading(false);
      }
    }
  }, []);

  const refreshDashboard = useCallback(
    async (signal?: AbortSignal) => {
      await Promise.all([loadCounts(signal), loadEvents(signal), loadRules(signal), loadDbStatus(signal)]);
    },
    [loadCounts, loadDbStatus, loadEvents, loadRules],
  );

  useEffect(() => {
    const controller = new AbortController();
    void refreshDashboard(controller.signal);
    return () => controller.abort();
  }, [refreshDashboard]);

  const refreshEventsAndCounts = async () => {
    await Promise.all([loadCounts(), loadEvents()]);
  };

  const acknowledgeEvent = async (event: AlertEvent) => {
    if (!isPriceMonitoringDbReady(dbStatus)) {
      setEventsError(getPriceMonitoringDbBlockingMessage(dbStatus));
      return;
    }

    const eventId = getEventId(event);
    if (eventId === null) {
      return;
    }

    setActionEventId(eventId);
    try {
      await commerceClient.acknowledgePriceMonitoringAlertEvent(eventId, { acknowledged_by: null });
      await refreshEventsAndCounts();
    } catch (error) {
      setEventsError(getCommerceApiErrorMessage(error));
    } finally {
      setActionEventId(null);
    }
  };

  const resolveEvent = async (event: AlertEvent) => {
    if (!isPriceMonitoringDbReady(dbStatus)) {
      setEventsError(getPriceMonitoringDbBlockingMessage(dbStatus));
      return;
    }

    const eventId = getEventId(event);
    if (eventId === null) {
      return;
    }

    setActionEventId(eventId);
    try {
      await commerceClient.resolvePriceMonitoringAlertEvent(eventId, { resolved_by: null });
      await refreshEventsAndCounts();
    } catch (error) {
      setEventsError(getCommerceApiErrorMessage(error));
    } finally {
      setActionEventId(null);
    }
  };

  const submitRule = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    setFormMessage(null);

    if (!isPriceMonitoringDbReady(dbStatus)) {
      setFormError(getPriceMonitoringDbBlockingMessage(dbStatus));
      return;
    }

    const { body, error } = buildRuleBody(ruleForm);
    if (error) {
      setFormError(error);
      return;
    }

    setIsSavingRule(true);
    try {
      if (editingRuleId !== null) {
        const updateBody: UpdateAlertRuleBody = body;
        await commerceClient.updatePriceMonitoringAlertRule(editingRuleId, updateBody);
        setFormMessage("Alert rule updated.");
      } else {
        await commerceClient.createPriceMonitoringAlertRule(body);
        setFormMessage("Alert rule created.");
      }

      setEditingRuleId(null);
      setRuleForm(getInitialRuleForm(new URLSearchParams()));
      await loadRules();
    } catch (saveError) {
      setFormError(getCommerceApiErrorMessage(saveError));
    } finally {
      setIsSavingRule(false);
    }
  };

  const editRule = (rule: AlertRule) => {
    if (rule.id === undefined) {
      setFormError("Cannot edit this rule because it has no ID.");
      return;
    }

    setEditingRuleId(rule.id);
    setRuleForm(makeFormFromRule(rule));
    setFormError(null);
    setFormMessage(null);
  };

  const deactivateRule = async (rule: AlertRule) => {
    if (!isPriceMonitoringDbReady(dbStatus)) {
      setRulesError(getPriceMonitoringDbBlockingMessage(dbStatus));
      return;
    }

    if (rule.id === undefined) {
      setRulesError("Cannot deactivate this rule because it has no ID.");
      return;
    }

    setRuleActionId(rule.id);
    try {
      await commerceClient.deactivatePriceMonitoringAlertRule(rule.id);
      await loadRules();
    } catch (error) {
      setRulesError(getCommerceApiErrorMessage(error));
    } finally {
      setRuleActionId(null);
    }
  };

  const cancelEdit = () => {
    setEditingRuleId(null);
    setRuleForm(getInitialRuleForm(new URLSearchParams()));
    setFormError(null);
    setFormMessage(null);
  };

  const submitEvaluate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!isPriceMonitoringDbReady(dbStatus)) {
      setEvaluateError(getPriceMonitoringDbBlockingMessage(dbStatus));
      return;
    }

    const runId = evaluateRunId.trim();
    if (!runId) {
      setEvaluateError("Run ID is required.");
      return;
    }

    setIsEvaluating(true);
    setEvaluateError(null);
    setEvaluateResult(null);
    try {
      const result = await commerceClient.evaluatePriceMonitoringAlertsForRun(runId);
      setEvaluateResult(result);
      await refreshEventsAndCounts();
    } catch (error) {
      setEvaluateError(getCommerceApiErrorMessage(error));
    } finally {
      setIsEvaluating(false);
    }
  };

  const thresholdsEmpty = !ruleForm.threshold_amount.trim() && !ruleForm.threshold_percent.trim();
  const dbAvailable = isPriceMonitoringDbReady(dbStatus);
  const dbUnavailableTitle = dbAvailable
    ? undefined
    : getPriceMonitoringDbBlockingMessage(dbStatus);

  const resetSavedAlertsState = () => {
    resetPersistedState();
    setStatusFilter(initialPersistedAlertsState.statusFilter);
    setModelFilter(initialPersistedAlertsState.modelFilter);
    setRunIdFilter(initialPersistedAlertsState.runIdFilter);
    setProductIdFilter(initialPersistedAlertsState.productIdFilter);
    setRuleForm(initialPersistedAlertsState.ruleForm);
    setEditingRuleId(initialPersistedAlertsState.editingRuleId);
    setEvaluateRunId(initialPersistedAlertsState.evaluateRunId);
    setFormError(null);
    setFormMessage(null);
    setEvaluateError(null);
    setEvaluateResult(null);
  };

  return (
    <div className="page-stack">
      <section className="page-header">
        <p className="eyebrow">Price Alerts</p>
        <h2>Price Monitoring Alerts</h2>
        <p>Dashboard-only records for competitor prices below your own price.</p>
        <button className="text-button" type="button" onClick={resetSavedAlertsState}>
          Reset saved Alerts state
        </button>
      </section>

      <PriceMonitoringDbStatusBanner
        status={dbStatus}
        error={dbStatusError}
        isLoading={isDbStatusLoading}
        onRetry={() => void loadDbStatus()}
      />

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Alert Summary</p>
            <h3>Dashboard totals</h3>
          </div>
          <button className="button secondary" type="button" onClick={() => void refreshDashboard()}>
            Refresh
          </button>
        </div>

        {isCountsLoading ? <LoadingState label="Loading alert totals..." /> : null}
        {countsError ? <ErrorState message={countsError} onRetry={() => void loadCounts()} /> : null}
        {!dbAvailable ? (
          <EmptyState title="Alert totals locked" message={dbUnavailableTitle ?? ""} />
        ) : null}
        {!countsError && dbAvailable ? (
          <dl className="summary-grid alert-summary-grid">
            <SummaryItem label="Open alerts" value={counts.open} />
            <SummaryItem label="Acknowledged alerts" value={counts.acknowledged} />
            <SummaryItem label="Resolved alerts" value={counts.resolved} />
            <SummaryItem label="Total alerts" value={counts.total} />
          </dl>
        ) : null}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Alert Events</p>
            <h3>Events</h3>
          </div>
          <button className="button secondary" type="button" onClick={() => void loadEvents()}>
            Refresh events
          </button>
        </div>

        <div className="filter-grid">
          <label>
            Status
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as AlertStatusFilter)}>
              <option value="open">Open</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="resolved">Resolved</option>
              <option value="all">All</option>
            </select>
          </label>
          <label>
            Model
            <input value={modelFilter} onChange={(event) => setModelFilter(event.target.value)} />
          </label>
          <label>
            Run ID
            <input value={runIdFilter} onChange={(event) => setRunIdFilter(event.target.value)} />
          </label>
          <label>
            Product ID
            <input value={productIdFilter} onChange={(event) => setProductIdFilter(event.target.value)} />
          </label>
        </div>

        {isEventsLoading ? <LoadingState label="Loading alert events..." /> : null}
        {eventsError ? <ErrorState message={eventsError} onRetry={() => void loadEvents()} /> : null}
        {!dbAvailable ? (
          <EmptyState title="Alert events locked" message={dbUnavailableTitle ?? ""} />
        ) : null}
        {dbAvailable && !isEventsLoading && !eventsError && events.length === 0 ? (
          <EmptyState
            title="No alerts found"
            message="Create a rule and evaluate a run to generate dashboard alert records."
          />
        ) : null}
        {!eventsError && events.length > 0 ? (
          <>
            <p className="muted">Showing {events.length} of {eventCount} returned events.</p>
            <div className="table-wrap alert-events-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Severity</th>
                    <th>Product</th>
                    <th>Source</th>
                    <th>Competitor / Store</th>
                    <th>Own price</th>
                    <th>Competitor price</th>
                    <th>Delta</th>
                    <th>Delta %</th>
                    <th>Message</th>
                    <th>Run ID</th>
                    <th>Triggered at</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((event, index) => {
                    const eventId = getEventId(event);
                    const status = event.status ?? "open";
                    const busy = eventId !== null && actionEventId === eventId;

                    return (
                      <tr key={`${eventId ?? "event"}-${index}`}>
                        <td>
                          <span className={`status-badge ${getStatusTone(status)}`}>
                            {formatAlertStatus(status)}
                          </span>
                        </td>
                        <td>{formatValue(event.severity)}</td>
                        <td>
                          <ProductCell event={event} />
                        </td>
                        <td>{formatValue(event.source ?? event.catalog_source)}</td>
                        <td>{formatValue(event.competitor_name)}</td>
                        <td className="nowrap-cell">{formatMoney(event.own_price)}</td>
                        <td className="nowrap-cell">{formatMoney(event.competitor_price)}</td>
                        <td className="nowrap-cell">{formatMoney(event.price_delta)}</td>
                        <td className="nowrap-cell">{formatPercent(event.price_delta_percent)}</td>
                        <td>{formatValue(event.message)}</td>
                        <td className="nowrap-cell">{formatValue(getRunId(event))}</td>
                        <td className="nowrap-cell">{formatDateTime(event.triggered_at ?? event.created_at)}</td>
                        <td>
                          <div className="button-row">
                            {status === "open" ? (
                              <button
                                className="button secondary"
                                type="button"
                                disabled={busy || !dbAvailable}
                                title={dbUnavailableTitle}
                                onClick={() => void acknowledgeEvent(event)}
                              >
                                Acknowledge
                              </button>
                            ) : null}
                            {status === "open" || status === "acknowledged" ? (
                              <button
                                className="button secondary"
                                type="button"
                                disabled={busy || !dbAvailable}
                                title={dbUnavailableTitle}
                                onClick={() => void resolveEvent(event)}
                              >
                                Resolve
                              </button>
                            ) : (
                              <span className="muted">No action</span>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Alert Rules</p>
            <h3>Rules</h3>
          </div>
          <button className="button secondary" type="button" onClick={() => void loadRules()}>
            Refresh rules
          </button>
        </div>

        {isRulesLoading ? <LoadingState label="Loading alert rules..." /> : null}
        {rulesError ? <ErrorState message={rulesError} onRetry={() => void loadRules()} /> : null}
        {!dbAvailable ? (
          <EmptyState title="Alert rules locked" message={dbUnavailableTitle ?? ""} />
        ) : null}
        {dbAvailable && !isRulesLoading && !rulesError && rules.length === 0 ? (
          <EmptyState title="No alert rules" message="Create a competitor-below-own-price rule to start monitoring." />
        ) : null}
        {!rulesError && rules.length > 0 ? (
          <div className="table-wrap alert-rules-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Active</th>
                  <th>Name</th>
                  <th>Rule type</th>
                  <th>Target</th>
                  <th>Threshold amount</th>
                  <th>Threshold %</th>
                  <th>Created</th>
                  <th>Updated</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((rule, index) => {
                  const ruleId = rule.id ?? `rule-${index}`;
                  const busy = rule.id !== undefined && ruleActionId === rule.id;

                  return (
                    <tr key={String(ruleId)}>
                      <td>
                        <span className={`status-badge ${rule.active === false ? "neutral" : "ok"}`}>
                          {rule.active === false ? "Inactive" : "Active"}
                        </span>
                      </td>
                      <td>{formatValue(rule.name)}</td>
                      <td>{formatRuleType(rule.rule_type)}</td>
                      <td>{getRuleTarget(rule)}</td>
                      <td>{formatMoney(rule.threshold_amount)}</td>
                      <td>{formatPercent(rule.threshold_percent)}</td>
                      <td className="nowrap-cell">{formatDateTime(rule.created_at)}</td>
                      <td className="nowrap-cell">{formatDateTime(rule.updated_at)}</td>
                      <td>
                        <div className="button-row">
                          <button className="button secondary" type="button" onClick={() => editRule(rule)}>
                            Edit
                          </button>
                          <button
                            className="button secondary"
                            type="button"
                            disabled={busy || rule.active === false || !dbAvailable}
                            title={dbUnavailableTitle}
                            onClick={() => void deactivateRule(rule)}
                          >
                            Deactivate
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Rule Form</p>
            <h3>{editingRuleId === null ? "Create alert rule" : "Edit alert rule"}</h3>
          </div>
          {editingRuleId !== null ? (
            <button className="button secondary" type="button" onClick={cancelEdit}>
              Cancel edit
            </button>
          ) : null}
        </div>

        <form className="form" onSubmit={(event) => void submitRule(event)}>
          <div className="filter-grid">
            <label>
              Name
              <input
                value={ruleForm.name}
                onChange={(event) => setRuleForm((form) => ({ ...form, name: event.target.value }))}
                placeholder="Optional"
              />
            </label>
            <label>
              Target mode
              <select
                value={ruleForm.targetMode}
                onChange={(event) =>
                  setRuleForm((form) => ({ ...form, targetMode: event.target.value as RuleTargetMode }))
                }
              >
                <option value="product_id">Product ID</option>
                <option value="catalog_model">Catalog source + model</option>
                <option value="catalog_mpn">Catalog source + MPN</option>
              </select>
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={ruleForm.active}
                onChange={(event) => setRuleForm((form) => ({ ...form, active: event.target.checked }))}
              />
              Active
            </label>
          </div>

          <div className="filter-grid">
            <label>
              Product ID
              <input
                value={ruleForm.product_id}
                disabled={ruleForm.targetMode !== "product_id"}
                onChange={(event) => setRuleForm((form) => ({ ...form, product_id: event.target.value }))}
              />
            </label>
            <label>
              Catalog source
              <input
                value={ruleForm.catalog_source}
                disabled={ruleForm.targetMode === "product_id"}
                onChange={(event) => setRuleForm((form) => ({ ...form, catalog_source: event.target.value }))}
              />
            </label>
            <label>
              Model
              <input
                value={ruleForm.model}
                disabled={ruleForm.targetMode !== "catalog_model"}
                onChange={(event) => setRuleForm((form) => ({ ...form, model: event.target.value }))}
              />
            </label>
            <label>
              MPN
              <input
                value={ruleForm.mpn}
                disabled={ruleForm.targetMode !== "catalog_mpn"}
                onChange={(event) => setRuleForm((form) => ({ ...form, mpn: event.target.value }))}
              />
            </label>
          </div>

          <div className="filter-grid">
            <label>
              Threshold amount
              <input
                type="number"
                min="0"
                step="0.01"
                value={ruleForm.threshold_amount}
                onChange={(event) => setRuleForm((form) => ({ ...form, threshold_amount: event.target.value }))}
                placeholder="Optional"
              />
            </label>
            <label>
              Threshold %
              <input
                type="number"
                min="0"
                step="0.01"
                value={ruleForm.threshold_percent}
                onChange={(event) => setRuleForm((form) => ({ ...form, threshold_percent: event.target.value }))}
                placeholder="Optional"
              />
            </label>
          </div>

          {thresholdsEmpty ? (
            <p className="muted">
              Leave thresholds empty to trigger whenever a competitor price is below your own price.
            </p>
          ) : null}
          {formError ? <p className="form-error">{formError}</p> : null}
          {formMessage ? <p className="state-block">{formMessage}</p> : null}
          {!dbAvailable ? (
            <p className="form-warning">{dbUnavailableTitle}</p>
          ) : null}

          <button
            className="button primary inline-button"
            type="submit"
            disabled={isSavingRule || !dbAvailable}
            title={dbUnavailableTitle}
          >
            {isSavingRule ? "Saving..." : editingRuleId === null ? "Create rule" : "Update rule"}
          </button>
        </form>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Manual Evaluation</p>
            <h3>Evaluate alerts for run</h3>
          </div>
        </div>

        <form className="toolbar" onSubmit={(event) => void submitEvaluate(event)}>
          <label className="inline-field wide">
            Run ID
            <input value={evaluateRunId} onChange={(event) => setEvaluateRunId(event.target.value)} />
          </label>
          <button
            className="button primary"
            type="submit"
            disabled={isEvaluating || !dbAvailable}
            title={dbUnavailableTitle}
          >
            {isEvaluating ? "Evaluating..." : "Evaluate alerts for run"}
          </button>
        </form>

        {evaluateError ? <ErrorState message={evaluateError} /> : null}
        {evaluateResult ? <EvaluateResultBlock result={evaluateResult} /> : null}
      </section>
    </div>
  );
}
