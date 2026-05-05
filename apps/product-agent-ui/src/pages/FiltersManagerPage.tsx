import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ApiError, apiClient, getApiErrorMessage } from "../api/client";
import type {
  AddFilterGroupRequest,
  AddFilterValueRequest,
  FilterCategoryDetail,
  FilterCategoryListItem,
  FilterGroup,
  FilterManagerStatus,
  FilterManagerStatusResponse,
  FilterSyncReport,
  FilterSyncResponse,
  FilterValue,
  HealthResponse,
  UpdateFilterGroupRequest,
  UpdateFilterValueRequest,
} from "../api/types";
import { JsonBlock } from "../components/jobs/JsonBlock";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";
import { usePersistentPageState } from "../hooks/usePersistentPageState";

const VALID_STATUSES: FilterManagerStatus[] = ["active", "inactive", "deprecated"];
const SOURCE_FILTERS = ["all", "base", "manual", "merged"] as const;
const FILTERS_MANAGER_STORAGE_KEY = "product-agent-ui:filters-manager:v1";
const STALE_REVISION_MESSAGE =
  "This filter category changed since you loaded it. Reload the category before saving.";

type SourceFilter = (typeof SOURCE_FILTERS)[number];
type BusyAction =
  | "load"
  | "detail"
  | "sync"
  | "report"
  | `group:${string | number}`
  | `value:${string | number}`
  | `add-value:${string | number}`;

interface FiltersManagerState {
  search: string;
  sourceFilter: SourceFilter;
  selectedCategoryId: string;
}

interface AddGroupFormState {
  name: string;
  required: boolean;
  status: FilterManagerStatus;
}

interface AddValueFormState {
  value: string;
  status: FilterManagerStatus;
}

interface GroupEditState {
  name: string;
  required: boolean;
  status: FilterManagerStatus;
}

interface ValueEditState {
  value: string;
  status: FilterManagerStatus;
}

const initialManagerState: FiltersManagerState = {
  search: "",
  sourceFilter: "all",
  selectedCategoryId: "",
};

const initialAddGroupForm: AddGroupFormState = {
  name: "",
  required: true,
  status: "active",
};

const initialAddValueForm: AddValueFormState = {
  value: "",
  status: "active",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isValidStatus(value: unknown): value is FilterManagerStatus {
  return typeof value === "string" && VALID_STATUSES.includes(value as FilterManagerStatus);
}

function normalizeStatus(value: unknown): FilterManagerStatus {
  return isValidStatus(value) ? value : "active";
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.status === 404) {
      return `Not found: ${error.message}`;
    }
    if (error.status === 409) {
      return `Conflict: ${error.message}`;
    }
    if (error.status === 422) {
      return `Validation error: ${error.message}`;
    }
  }

  return getApiErrorMessage(error) || fallback;
}

function isBackendHealthy(health: HealthResponse | null, healthError: string | null): boolean {
  if (healthError) {
    return false;
  }
  if (!health) {
    return true;
  }
  if (health.ok === false) {
    return false;
  }
  const status = typeof health.status === "string" ? health.status.trim().toLowerCase() : "";
  return !["error", "failed", "down", "unhealthy"].includes(status);
}

function formatPath(path: unknown): string {
  if (Array.isArray(path)) {
    return path.map((item) => String(item)).join(" > ");
  }
  if (typeof path === "string" && path.trim().length > 0) {
    return path;
  }
  return "-";
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  return String(value);
}

function getRevision(value: { revision?: string | null } | null | undefined): string | null {
  return typeof value?.revision === "string" && value.revision.trim().length > 0
    ? value.revision
    : null;
}

function formatRevision(revision: string | null): string {
  return revision ? revision.slice(0, 12) : "-";
}

function getCategoryId(category: Pick<FilterCategoryListItem, "category_id">): string {
  return String(category.category_id);
}

function countGroupsByStatus(groups: FilterGroup[] | undefined, status: FilterManagerStatus): number {
  return (groups ?? []).filter((group) => group.status === status).length;
}

function getWarningsCount(report: FilterSyncReport | null): number {
  return Array.isArray(report?.warnings) ? report.warnings.length : 0;
}

function getArrayCount(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

function isStaleRevisionConflict(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409;
}

function StatusBadge({ status }: { status: unknown }) {
  const normalized = typeof status === "string" ? status : "unknown";
  const className =
    normalized === "active"
      ? "ok"
      : normalized === "deprecated"
        ? "warning"
        : normalized === "inactive"
          ? "neutral"
          : "neutral";
  return <span className={`status-badge ${className}`}>{normalized}</span>;
}

function SourceBadge({ source }: { source: unknown }) {
  const normalized = typeof source === "string" && source.trim().length > 0 ? source : "unknown";
  const className = normalized === "manual" || normalized === "merged" ? "active" : "neutral";
  return <span className={`status-badge ${className}`}>{normalized}</span>;
}

function RequiredBadge({ required, status }: { required: boolean | undefined; status: unknown }) {
  if (!required) {
    return <span className="status-badge neutral">optional</span>;
  }

  if (status === "active") {
    return <span className="status-badge warning">required</span>;
  }

  return <span className="status-badge danger">required but inactive/deprecated</span>;
}

function SummaryItem({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{formatValue(value)}</dd>
    </div>
  );
}

function StatusSelect({
  value,
  onChange,
  disabled,
}: {
  value: FilterManagerStatus;
  onChange: (value: FilterManagerStatus) => void;
  disabled?: boolean;
}) {
  return (
    <select
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(normalizeStatus(event.target.value))}
    >
      {VALID_STATUSES.map((status) => (
        <option key={status} value={status}>
          {status}
        </option>
      ))}
    </select>
  );
}

function SyncReportPanel({ report }: { report: FilterSyncReport | null }) {
  if (!report) {
    return <EmptyState title="No sync report loaded" message="Load the report or run sync to view summary details." />;
  }

  const warnings = Array.isArray(report.warnings) ? report.warnings : [];
  const overriddenGroups = Array.isArray(report.overridden_groups) ? report.overridden_groups : [];
  const overriddenValues = Array.isArray(report.overridden_values) ? report.overridden_values : [];

  return (
    <div className="result-block">
      <dl className="summary-grid filters-summary-grid">
        <SummaryItem label="Mode" value={report.mode} />
        <SummaryItem label="Filter map" value={report.filter_map_path} />
        <SummaryItem label="Manual overrides" value={report.manual_overrides_path} />
        <SummaryItem label="Warnings" value={warnings.length} />
        <SummaryItem label="Overridden groups" value={overriddenGroups.length} />
        <SummaryItem label="Overridden values" value={overriddenValues.length} />
      </dl>
      <details className="column-controls">
        <summary>Warnings ({warnings.length})</summary>
        <JsonBlock value={warnings} />
      </details>
      <details className="column-controls">
        <summary>Overridden groups ({overriddenGroups.length})</summary>
        <JsonBlock value={overriddenGroups} />
      </details>
      <details className="column-controls">
        <summary>Overridden values ({overriddenValues.length})</summary>
        <JsonBlock value={overriddenValues} />
      </details>
    </div>
  );
}

function CategoryBrowser({
  categories,
  selectedCategoryId,
  search,
  sourceFilter,
  onSearchChange,
  onSourceFilterChange,
  onSelectCategory,
}: {
  categories: FilterCategoryListItem[];
  selectedCategoryId: string;
  search: string;
  sourceFilter: SourceFilter;
  onSearchChange: (search: string) => void;
  onSourceFilterChange: (source: SourceFilter) => void;
  onSelectCategory: (categoryId: string) => void;
}) {
  const normalizedSearch = search.trim().toLowerCase();
  const visibleCategories = useMemo(
    () =>
      categories.filter((category) => {
        const source = typeof category.source === "string" ? category.source : "";
        if (sourceFilter !== "all" && source !== sourceFilter) {
          return false;
        }
        if (!normalizedSearch) {
          return true;
        }
        return [
          getCategoryId(category),
          formatPath(category.path),
          category.key,
          category.parent_category,
          category.leaf_category,
          category.sub_category,
        ]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(normalizedSearch));
      }),
    [categories, normalizedSearch, sourceFilter],
  );

  return (
    <section className="panel filters-browser-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Category browser</p>
          <h3>{visibleCategories.length} categories</h3>
        </div>
      </div>

      <div className="filter-grid filters-manager-filter-grid">
        <label>
          <span>Search</span>
          <input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="path, key, category_id"
          />
        </label>
        <label>
          <span>Source</span>
          <select value={sourceFilter} onChange={(event) => onSourceFilterChange(event.target.value as SourceFilter)}>
            {SOURCE_FILTERS.map((source) => (
              <option key={source} value={source}>
                {source}
              </option>
            ))}
          </select>
        </label>
      </div>

      {visibleCategories.length === 0 ? (
        <EmptyState title="No matching categories" message="Adjust search or source filters." />
      ) : (
        <ul className="filters-category-list">
          {visibleCategories.map((category) => {
            const categoryId = getCategoryId(category);
            const inactiveDeprecated =
              (category.inactive_group_count ?? 0) + (category.deprecated_group_count ?? 0);
            return (
              <li key={categoryId}>
                <button
                  className={`file-list-button filters-category-button ${selectedCategoryId === categoryId ? "active" : ""}`}
                  type="button"
                  onClick={() => onSelectCategory(categoryId)}
                >
                  <strong>{formatPath(category.path)}</strong>
                  <span>{categoryId}</span>
                  <span>{formatValue(category.key)}</span>
                  <span className="filters-category-counts">
                    groups {formatValue(category.group_count)} | active {formatValue(category.active_group_count)} | required{" "}
                    {formatValue(category.required_group_count)} | inactive/deprecated {inactiveDeprecated}
                  </span>
                  <span>
                    <SourceBadge source={category.source} />
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function AddGroupForm({
  disabled,
  error,
  onSubmit,
}: {
  disabled: boolean;
  error: string | null;
  onSubmit: (payload: AddFilterGroupRequest) => Promise<boolean>;
}) {
  const [form, setForm] = useState<AddGroupFormState>(initialAddGroupForm);
  const [localError, setLocalError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = form.name.trim();
    if (!name) {
      setLocalError("Group name is required.");
      return;
    }
    if (!isValidStatus(form.status)) {
      setLocalError("Select a valid status.");
      return;
    }

    setLocalError(null);
    const didSave = await onSubmit({ name, required: form.required, status: form.status });
    if (didSave) {
      setForm(initialAddGroupForm);
    }
  }

  return (
    <form className="form filters-inline-form" onSubmit={handleSubmit}>
      {(localError ?? error) ? <p className="form-error">{localError ?? error}</p> : null}
      <div className="filter-grid filters-manager-filter-grid">
        <label>
          <span>Group name</span>
          <input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} />
        </label>
        <label>
          <span>Status</span>
          <StatusSelect value={form.status} disabled={disabled} onChange={(status) => setForm((current) => ({ ...current, status }))} />
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={form.required}
            disabled={disabled}
            onChange={(event) => setForm((current) => ({ ...current, required: event.target.checked }))}
          />
          <span>Required</span>
        </label>
      </div>
      <button className="button primary inline-button" type="submit" disabled={disabled}>
        Add Group
      </button>
    </form>
  );
}

function AddValueForm({
  disabled,
  error,
  groupId,
  onSubmit,
}: {
  disabled: boolean;
  error: string | null;
  groupId: string | number;
  onSubmit: (groupId: string | number, payload: AddFilterValueRequest) => Promise<boolean>;
}) {
  const [form, setForm] = useState<AddValueFormState>(initialAddValueForm);
  const [localError, setLocalError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (form.value.trim().length === 0) {
      setLocalError("Value is required.");
      return;
    }
    if (!isValidStatus(form.status)) {
      setLocalError("Select a valid status.");
      return;
    }

    setLocalError(null);
    const didSave = await onSubmit(groupId, { value: form.value, status: form.status });
    if (didSave) {
      setForm(initialAddValueForm);
    }
  }

  return (
    <form className="form filters-value-form" onSubmit={handleSubmit}>
      {(localError ?? error) ? <p className="form-error">{localError ?? error}</p> : null}
      <label>
        <span>New value</span>
        <input value={form.value} onChange={(event) => setForm((current) => ({ ...current, value: event.target.value }))} />
      </label>
      <label>
        <span>Status</span>
        <StatusSelect value={form.status} disabled={disabled} onChange={(status) => setForm((current) => ({ ...current, status }))} />
      </label>
      <button className="button primary compact-button" type="submit" disabled={disabled}>
        Add Value
      </button>
    </form>
  );
}

function ValueEditor({
  value,
  disabled,
  error,
  onSave,
}: {
  value: FilterValue;
  disabled: boolean;
  error: string | null;
  onSave: (valueId: string | number, payload: UpdateFilterValueRequest) => Promise<void>;
}) {
  const [form, setForm] = useState<ValueEditState>({
    value: value.value ?? "",
    status: normalizeStatus(value.status),
  });

  useEffect(() => {
    setForm({ value: value.value ?? "", status: normalizeStatus(value.status) });
  }, [value.value, value.status]);

  async function handleSave() {
    if (form.value.trim().length === 0) {
      return;
    }
    await onSave(value.value_id, { value: form.value, status: form.status });
  }

  const isSubdued = value.status === "inactive" || value.status === "deprecated";

  return (
    <tr className={isSubdued ? "filters-subdued-row" : undefined}>
      <td>
        <input
          className="table-input"
          value={form.value}
          disabled={disabled}
          onChange={(event) => setForm((current) => ({ ...current, value: event.target.value }))}
        />
        <span className="artifact-path">{formatValue(value.value_id)}</span>
        {form.value.trim().length === 0 ? <span className="field-error">Value is required.</span> : null}
      </td>
      <td>
        <StatusSelect value={form.status} disabled={disabled} onChange={(status) => setForm((current) => ({ ...current, status }))} />
      </td>
      <td>
        <SourceBadge source={value.source} />
      </td>
      <td>
        <button className="button secondary compact-button" type="button" disabled={disabled || form.value.trim().length === 0} onClick={() => void handleSave()}>
          Save
        </button>
        {error ? <span className="field-error">{error}</span> : null}
      </td>
    </tr>
  );
}

function GroupEditor({
  categoryId,
  group,
  disabled,
  groupError,
  addValueError,
  valueErrors,
  onSaveGroup,
  onAddValue,
  onSaveValue,
}: {
  categoryId: string | number;
  group: FilterGroup;
  disabled: boolean;
  groupError: string | null;
  addValueError: string | null;
  valueErrors: Record<string, string>;
  onSaveGroup: (groupId: string | number, payload: UpdateFilterGroupRequest) => Promise<void>;
  onAddValue: (groupId: string | number, payload: AddFilterValueRequest) => Promise<boolean>;
  onSaveValue: (groupId: string | number, valueId: string | number, payload: UpdateFilterValueRequest) => Promise<void>;
}) {
  const [form, setForm] = useState<GroupEditState>({
    name: group.name ?? "",
    required: Boolean(group.required),
    status: normalizeStatus(group.status),
  });

  useEffect(() => {
    setForm({
      name: group.name ?? "",
      required: Boolean(group.required),
      status: normalizeStatus(group.status),
    });
  }, [group.name, group.required, group.status]);

  async function handleSave() {
    const name = form.name.trim();
    if (!name) {
      return;
    }
    await onSaveGroup(group.group_id, { name, required: form.required, status: form.status });
  }

  const isSubdued = group.status === "inactive" || group.status === "deprecated";

  return (
    <article className={`stage-card filters-group-card ${isSubdued ? "filters-subdued-card" : ""}`}>
      <div className="section-heading">
        <div>
          <p className="eyebrow">Group {formatValue(group.group_id)}</p>
          <h4>{formatValue(group.name)}</h4>
        </div>
        <div className="button-row">
          <RequiredBadge required={group.required} status={group.status} />
          <StatusBadge status={group.status} />
          <SourceBadge source={group.source} />
        </div>
      </div>

      {groupError ? <p className="form-error">{groupError}</p> : null}
      <div className="filter-grid filters-group-edit-grid">
        <label>
          <span>Group name</span>
          <input value={form.name} disabled={disabled} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} />
          {form.name.trim().length === 0 ? <span className="field-error">Group name is required.</span> : null}
        </label>
        <label>
          <span>Status</span>
          <StatusSelect value={form.status} disabled={disabled} onChange={(status) => setForm((current) => ({ ...current, status }))} />
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={form.required}
            disabled={disabled}
            onChange={(event) => setForm((current) => ({ ...current, required: event.target.checked }))}
          />
          <span>Required</span>
        </label>
        <button className="button secondary inline-button" type="button" disabled={disabled || form.name.trim().length === 0} onClick={() => void handleSave()}>
          Save group
        </button>
      </div>

      <div className="filters-values-block">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Values</p>
            <h4>{group.values?.length ?? 0} values</h4>
          </div>
        </div>

        <AddValueForm
          disabled={disabled}
          groupId={group.group_id}
          error={addValueError}
          onSubmit={onAddValue}
        />

        {(group.values ?? []).length === 0 ? (
          <EmptyState title="No values" message="Add allowed values for this group." />
        ) : (
          <div className="table-wrap filters-values-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Value</th>
                  <th>Status</th>
                  <th>Source</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {(group.values ?? []).map((value) => (
                  <ValueEditor
                    key={String(value.value_id)}
                    value={value}
                    disabled={disabled}
                    error={valueErrors[`${categoryId}:${group.group_id}:${value.value_id}`] ?? null}
                    onSave={(valueId, payload) => onSaveValue(group.group_id, valueId, payload)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </article>
  );
}

function CategoryDetailEditor({
  category,
  disabled,
  addGroupError,
  groupErrors,
  addValueErrors,
  valueErrors,
  onAddGroup,
  onSaveGroup,
  onAddValue,
  onSaveValue,
}: {
  category: FilterCategoryDetail;
  disabled: boolean;
  addGroupError: string | null;
  groupErrors: Record<string, string>;
  addValueErrors: Record<string, string>;
  valueErrors: Record<string, string>;
  onAddGroup: (payload: AddFilterGroupRequest) => Promise<boolean>;
  onSaveGroup: (groupId: string | number, payload: UpdateFilterGroupRequest) => Promise<void>;
  onAddValue: (groupId: string | number, payload: AddFilterValueRequest) => Promise<boolean>;
  onSaveValue: (groupId: string | number, valueId: string | number, payload: UpdateFilterValueRequest) => Promise<void>;
}) {
  const groups = category.groups ?? [];
  return (
    <section className="panel filters-detail-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Category detail</p>
          <h3>{formatPath(category.path)}</h3>
        </div>
        <SourceBadge source={category.source} />
      </div>

      <dl className="summary-grid filters-summary-grid">
        <SummaryItem label="Category ID" value={category.category_id} />
        <SummaryItem label="Parent" value={category.parent_category} />
        <SummaryItem label="Leaf" value={category.leaf_category} />
        <SummaryItem label="Sub" value={category.sub_category} />
        <SummaryItem label="Key" value={category.key} />
        <SummaryItem label="Groups" value={groups.length} />
        <SummaryItem label="Active groups" value={countGroupsByStatus(groups, "active")} />
        <SummaryItem label="Required groups" value={groups.filter((group) => group.required).length} />
        <SummaryItem label="Inactive groups" value={countGroupsByStatus(groups, "inactive")} />
        <SummaryItem label="Deprecated groups" value={countGroupsByStatus(groups, "deprecated")} />
      </dl>

      <section className="stage-card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Add group</p>
            <h4>Manual override group</h4>
          </div>
        </div>
        <AddGroupForm disabled={disabled} error={addGroupError} onSubmit={onAddGroup} />
      </section>

      <div className="filters-groups-list">
        {groups.length === 0 ? (
          <EmptyState title="No groups" message="This category does not have filter groups yet." />
        ) : (
          groups.map((group) => (
            <GroupEditor
              key={String(group.group_id)}
              categoryId={category.category_id}
              group={group}
              disabled={disabled}
              groupError={groupErrors[`${category.category_id}:${group.group_id}`] ?? null}
              addValueError={addValueErrors[`${category.category_id}:${group.group_id}`] ?? null}
              valueErrors={valueErrors}
              onSaveGroup={onSaveGroup}
              onAddValue={onAddValue}
              onSaveValue={onSaveValue}
            />
          ))
        )}
      </div>
    </section>
  );
}

export function FiltersManagerPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryCategoryId = searchParams.get("category_id") ?? "";
  const [managerState, setManagerState, resetManagerState] =
    usePersistentPageState<FiltersManagerState>(FILTERS_MANAGER_STORAGE_KEY, initialManagerState);
  const selectedCategoryId = queryCategoryId || managerState.selectedCategoryId;

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [filterStatus, setFilterStatus] = useState<FilterManagerStatusResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [categories, setCategories] = useState<FilterCategoryListItem[]>([]);
  const [categoryDetail, setCategoryDetail] = useState<FilterCategoryDetail | null>(null);
  const [syncResponse, setSyncResponse] = useState<FilterSyncResponse | null>(null);
  const [syncReport, setSyncReport] = useState<FilterSyncReport | null>(null);
  const [backendRevision, setBackendRevision] = useState<string | null>(null);
  const [revisionConflict, setRevisionConflict] = useState<string | null>(null);
  const [busyActions, setBusyActions] = useState<Set<BusyAction>>(new Set());
  const [loadError, setLoadError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [addGroupError, setAddGroupError] = useState<string | null>(null);
  const [groupErrors, setGroupErrors] = useState<Record<string, string>>({});
  const [addValueErrors, setAddValueErrors] = useState<Record<string, string>>({});
  const [valueErrors, setValueErrors] = useState<Record<string, string>>({});
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null);

  const backendAvailable = isBackendHealthy(health, healthError);
  const writeDisabled = !backendAvailable || busyActions.has("sync");
  const currentRevision = getRevision(categoryDetail) ?? backendRevision;

  function setBusy(action: BusyAction, busy: boolean) {
    setBusyActions((current) => {
      const next = new Set(current);
      if (busy) {
        next.add(action);
      } else {
        next.delete(action);
      }
      return next;
    });
  }

  const loadHealth = useCallback(async (signal?: AbortSignal) => {
    try {
      const nextHealth = await apiClient.getHealth(signal);
      if (signal?.aborted) {
        return;
      }
      setHealth(nextHealth);
      setHealthError(null);
    } catch (error) {
      if (!signal?.aborted) {
        setHealth(null);
        setHealthError(getApiErrorMessage(error));
      }
    }

    try {
      const nextFilterStatus = await apiClient.getFilterStatus(signal);
      if (!signal?.aborted) {
        setFilterStatus(nextFilterStatus);
        setBackendRevision((current) => getRevision(nextFilterStatus) ?? current);
      }
    } catch (error) {
      if (!signal?.aborted && !(error instanceof ApiError && error.status === 404)) {
        setFilterStatus({ status: getApiErrorMessage(error) });
      }
    }
  }, []);

  const loadCategories = useCallback(async (signal?: AbortSignal) => {
    setBusy("load", true);
    try {
      const nextCategories = await apiClient.listFilterCategories(signal);
      if (signal?.aborted) {
        return;
      }
      setCategories(nextCategories);
      setLoadError(null);
      setLastLoadedAt(new Date());
    } catch (error) {
      if (!signal?.aborted) {
        setLoadError(getErrorMessage(error, "Could not load filter categories."));
      }
    } finally {
      if (!signal?.aborted) {
        setBusy("load", false);
      }
    }
  }, []);

  const loadCategoryDetail = useCallback(async (categoryId: string, signal?: AbortSignal) => {
    if (!categoryId) {
      setCategoryDetail(null);
      return;
    }

    setBusy("detail", true);
    try {
      const nextCategory = await apiClient.getFilterCategory(categoryId, signal);
      if (signal?.aborted) {
        return;
      }
      setCategoryDetail(nextCategory);
      setBackendRevision((current) => getRevision(nextCategory) ?? current);
      setRevisionConflict(null);
      setDetailError(null);
    } catch (error) {
      if (!signal?.aborted) {
        setCategoryDetail(null);
        setDetailError(getErrorMessage(error, "Could not load filter category."));
      }
    } finally {
      if (!signal?.aborted) {
        setBusy("detail", false);
      }
    }
  }, []);

  const loadSyncReport = useCallback(async (signal?: AbortSignal) => {
    setBusy("report", true);
    try {
      const nextReport = await apiClient.getFilterSyncReport(signal);
      if (signal?.aborted) {
        return;
      }
      setSyncReport(nextReport);
      setReportError(null);
    } catch (error) {
      if (!signal?.aborted) {
        setReportError(getErrorMessage(error, "Could not load filter sync report."));
      }
    } finally {
      if (!signal?.aborted) {
        setBusy("report", false);
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadHealth(controller.signal);
    void loadCategories(controller.signal);
    void loadSyncReport(controller.signal);
    return () => controller.abort();
  }, [loadCategories, loadHealth, loadSyncReport]);

  useEffect(() => {
    const controller = new AbortController();
    void loadCategoryDetail(selectedCategoryId, controller.signal);
    return () => controller.abort();
  }, [loadCategoryDetail, selectedCategoryId]);

  function updateManagerState(update: Partial<FiltersManagerState>) {
    setManagerState((current) => ({ ...current, ...update }));
  }

  function selectCategory(categoryId: string) {
    updateManagerState({ selectedCategoryId: categoryId });
    setCategoryDetail(null);
    setRevisionConflict(null);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("category_id", categoryId);
    setSearchParams(nextParams, { replace: false });
  }

  async function refreshAll() {
    await loadHealth();
    await loadCategories();
    if (selectedCategoryId) {
      await loadCategoryDetail(selectedCategoryId);
    }
  }

  async function handleSync() {
    setBusy("sync", true);
    setSyncError(null);
    try {
      const nextSync = await apiClient.syncFilterMap();
      setSyncResponse(nextSync);
      setBackendRevision((current) => getRevision(nextSync) ?? current);
      await loadCategories();
      if (selectedCategoryId) {
        await loadCategoryDetail(selectedCategoryId);
      }
      await loadSyncReport();
    } catch (error) {
      setSyncError(getErrorMessage(error, "Could not sync filter map."));
    } finally {
      setBusy("sync", false);
    }
  }

  function withExpectedRevision<
    T extends
      | AddFilterGroupRequest
      | UpdateFilterGroupRequest
      | AddFilterValueRequest
      | UpdateFilterValueRequest,
  >(payload: T): T {
    return currentRevision ? { ...payload, expected_revision: currentRevision } : payload;
  }

  function applyCategoryWriteResult(nextCategory: FilterCategoryDetail) {
    setCategoryDetail(nextCategory);
    setBackendRevision((current) => getRevision(nextCategory) ?? current);
    setRevisionConflict(null);
    setDetailError(null);
  }

  async function reloadSelectedCategory() {
    if (!selectedCategoryId) {
      return;
    }
    await loadCategoryDetail(selectedCategoryId);
  }

  async function handleAddGroup(payload: AddFilterGroupRequest) {
    if (!selectedCategoryId) {
      setAddGroupError("Select a category first.");
      return false;
    }

    setAddGroupError(null);
    try {
      const nextCategory = await apiClient.addFilterGroup(
        selectedCategoryId,
        withExpectedRevision(payload),
      );
      applyCategoryWriteResult(nextCategory);
      await loadCategories();
      return true;
    } catch (error) {
      if (isStaleRevisionConflict(error)) {
        setRevisionConflict(STALE_REVISION_MESSAGE);
        setAddGroupError(STALE_REVISION_MESSAGE);
      } else {
        setAddGroupError(getErrorMessage(error, "Could not add filter group."));
      }
      return false;
    }
  }

  async function handleSaveGroup(groupId: string | number, payload: UpdateFilterGroupRequest) {
    if (!selectedCategoryId) {
      return;
    }

    const errorKey = `${selectedCategoryId}:${groupId}`;
    setBusy(`group:${groupId}`, true);
    setGroupErrors((current) => ({ ...current, [errorKey]: "" }));
    try {
      const nextCategory = await apiClient.updateFilterGroup(
        selectedCategoryId,
        groupId,
        withExpectedRevision(payload),
      );
      applyCategoryWriteResult(nextCategory);
      await loadCategories();
    } catch (error) {
      if (isStaleRevisionConflict(error)) {
        setRevisionConflict(STALE_REVISION_MESSAGE);
        setGroupErrors((current) => ({
          ...current,
          [errorKey]: STALE_REVISION_MESSAGE,
        }));
        return;
      }
      setGroupErrors((current) => ({
        ...current,
        [errorKey]: getErrorMessage(error, "Could not update filter group."),
      }));
    } finally {
      setBusy(`group:${groupId}`, false);
    }
  }

  async function handleAddValue(groupId: string | number, payload: AddFilterValueRequest) {
    if (!selectedCategoryId) {
      return false;
    }

    const errorKey = `${selectedCategoryId}:${groupId}`;
    setBusy(`add-value:${groupId}`, true);
    setAddValueErrors((current) => ({ ...current, [errorKey]: "" }));
    try {
      const nextCategory = await apiClient.addFilterValue(
        selectedCategoryId,
        groupId,
        withExpectedRevision(payload),
      );
      applyCategoryWriteResult(nextCategory);
      await loadCategories();
      return true;
    } catch (error) {
      if (isStaleRevisionConflict(error)) {
        setRevisionConflict(STALE_REVISION_MESSAGE);
        setAddValueErrors((current) => ({
          ...current,
          [errorKey]: STALE_REVISION_MESSAGE,
        }));
        return false;
      }
      setAddValueErrors((current) => ({
        ...current,
        [errorKey]: getErrorMessage(error, "Could not add filter value."),
      }));
      return false;
    } finally {
      setBusy(`add-value:${groupId}`, false);
    }
  }

  async function handleSaveValue(
    groupId: string | number,
    valueId: string | number,
    payload: UpdateFilterValueRequest,
  ) {
    if (!selectedCategoryId) {
      return;
    }

    const errorKey = `${selectedCategoryId}:${groupId}:${valueId}`;
    setBusy(`value:${valueId}`, true);
    setValueErrors((current) => ({ ...current, [errorKey]: "" }));
    try {
      const nextCategory = await apiClient.updateFilterValue(
        selectedCategoryId,
        groupId,
        valueId,
        withExpectedRevision(payload),
      );
      applyCategoryWriteResult(nextCategory);
      await loadCategories();
    } catch (error) {
      if (isStaleRevisionConflict(error)) {
        setRevisionConflict(STALE_REVISION_MESSAGE);
        setValueErrors((current) => ({
          ...current,
          [errorKey]: STALE_REVISION_MESSAGE,
        }));
        return;
      }
      setValueErrors((current) => ({
        ...current,
        [errorKey]: getErrorMessage(error, "Could not update filter value."),
      }));
    } finally {
      setBusy(`value:${valueId}`, false);
    }
  }

  function handleResetState() {
    resetManagerState();
    setSearchParams({}, { replace: true });
    setCategoryDetail(null);
    setRevisionConflict(null);
  }

  const statusText =
    typeof filterStatus?.status === "string" && filterStatus.status.trim().length > 0
      ? filterStatus.status
      : backendAvailable
        ? "available"
        : "unavailable";

  return (
    <div className="page-stack">
      <section className="page-header">
        <p className="eyebrow">Product-Agent</p>
        <h2>Filters Manager</h2>
        <p>Manage global category filter groups and values by stable backend IDs.</p>
        <button className="text-button" type="button" onClick={handleResetState}>
          Reset saved Filters Manager state
        </button>
      </section>

      <section className={`db-status-banner ${backendAvailable ? "ok" : "danger"}`}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Backend status</p>
            <h3>Filters API {statusText}</h3>
          </div>
          <div className="button-row">
            <button className="button secondary compact-button" type="button" onClick={() => void refreshAll()}>
              Refresh
            </button>
            <button className="button primary compact-button" type="button" disabled={!backendAvailable || busyActions.has("sync")} onClick={() => void handleSync()}>
              {busyActions.has("sync") ? "Syncing..." : "Sync Filter Map"}
            </button>
            <button className="button secondary compact-button" type="button" disabled={busyActions.has("report")} onClick={() => void loadSyncReport()}>
              {busyActions.has("report") ? "Loading report..." : "Load Sync Report"}
            </button>
          </div>
        </div>
        {healthError ? <p className="form-error">{healthError}</p> : null}
        {syncError ? <p className="form-error">{syncError}</p> : null}
        {!backendAvailable ? <p className="muted">Write and sync actions are disabled until the Product-Agent API is reachable.</p> : null}
        {lastLoadedAt ? <p className="muted">Last loaded {lastLoadedAt.toLocaleTimeString()}</p> : null}
        <p className="muted">Revision {formatRevision(currentRevision)}</p>
      </section>

      {revisionConflict ? (
        <div className="state-block error-state" role="alert">
          <span>{revisionConflict}</span>
          <button
            className="button secondary"
            type="button"
            disabled={!selectedCategoryId || busyActions.has("detail")}
            onClick={() => void reloadSelectedCategory()}
          >
            Reload category
          </button>
        </div>
      ) : null}

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Sync report</p>
            <h3>Latest filter map summary</h3>
          </div>
        </div>
        {syncResponse ? (
          <dl className="summary-grid filters-summary-grid">
            <SummaryItem label="Status" value={syncResponse.status} />
            <SummaryItem label="Revision" value={formatRevision(getRevision(syncResponse))} />
            <SummaryItem label="Filter map" value={syncResponse.filter_map_path} />
            <SummaryItem label="Sync report" value={syncResponse.sync_report_path} />
            <SummaryItem label="Categories" value={syncResponse.category_count} />
            <SummaryItem label="Groups" value={syncResponse.group_count} />
            <SummaryItem label="Values" value={syncResponse.value_count} />
            <SummaryItem label="Warnings" value={syncResponse.warning_count} />
            <SummaryItem label="Overridden groups" value={syncResponse.overridden_group_count} />
            <SummaryItem label="Overridden values" value={syncResponse.overridden_value_count} />
          </dl>
        ) : null}
        {reportError ? <ErrorState message={reportError} onRetry={() => void loadSyncReport()} /> : null}
        {syncReport ? (
          <p className="muted">
            Report warnings {getWarningsCount(syncReport)}, overridden groups {getArrayCount(syncReport.overridden_groups)}, overridden values{" "}
            {getArrayCount(syncReport.overridden_values)}.
          </p>
        ) : null}
        <SyncReportPanel report={syncReport} />
      </section>

      <div className="filters-manager-layout">
        <div className="page-stack">
          {busyActions.has("load") ? <LoadingState label="Loading filter categories..." /> : null}
          {loadError ? <ErrorState message={loadError} onRetry={() => void loadCategories()} /> : null}
          {!busyActions.has("load") && !loadError && categories.length === 0 ? (
            <EmptyState title="No categories" message="The backend returned an empty category list." />
          ) : null}
          {categories.length > 0 ? (
            <CategoryBrowser
              categories={categories}
              selectedCategoryId={selectedCategoryId}
              search={managerState.search}
              sourceFilter={managerState.sourceFilter}
              onSearchChange={(search) => updateManagerState({ search })}
              onSourceFilterChange={(sourceFilter) => updateManagerState({ sourceFilter })}
              onSelectCategory={selectCategory}
            />
          ) : null}
        </div>

        <div className="page-stack">
          {busyActions.has("detail") ? <LoadingState label="Loading category detail..." /> : null}
          {detailError ? (
            <ErrorState
              message={detailError}
              onRetry={() => selectedCategoryId && void loadCategoryDetail(selectedCategoryId)}
            />
          ) : null}
          {!selectedCategoryId ? (
            <EmptyState title="Select a category" message="Choose a category by stable category_id from the browser." />
          ) : null}
          {selectedCategoryId && !busyActions.has("detail") && !detailError && categoryDetail ? (
            <CategoryDetailEditor
              category={categoryDetail}
              disabled={writeDisabled}
              addGroupError={addGroupError}
              groupErrors={groupErrors}
              addValueErrors={addValueErrors}
              valueErrors={valueErrors}
              onAddGroup={handleAddGroup}
              onSaveGroup={handleSaveGroup}
              onAddValue={handleAddValue}
              onSaveValue={handleSaveValue}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}
