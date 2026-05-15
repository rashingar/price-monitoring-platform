import type { SourceUrlAgentRun, VendorSourceCapability } from "../../api/commerceTypes";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function getRunId(run: SourceUrlAgentRun): string {
  const value = run.run_id ?? run.id;
  return value === null || value === undefined || value === "" ? "-" : String(value);
}

export function normalizeLabel(value: unknown): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    return "-";
  }

  return value.replace(/_/g, " ");
}

export function parseNumberLike(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  return 0;
}

export function formatNumber(value: unknown): string {
  return parseNumberLike(value).toLocaleString();
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return String(value);
}

export function formatDate(value: unknown): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    return "-";
  }

  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function statusClass(status: unknown): string {
  const normalized = typeof status === "string" ? status.toLowerCase() : "";
  if (normalized === "succeeded" || normalized === "completed" || normalized === "success") {
    return "success";
  }

  if (normalized === "running" || normalized === "queued") {
    return "active";
  }

  if (normalized === "failed" || normalized === "error") {
    return "danger";
  }

  if (normalized === "cancelled" || normalized === "canceled") {
    return "warning";
  }

  return "neutral";
}

export function isActiveStatus(status: unknown): boolean {
  const normalized = typeof status === "string" ? status.toLowerCase() : "";
  return normalized === "queued" || normalized === "running";
}

export function getCounter(run: SourceUrlAgentRun, key: keyof SourceUrlAgentRun): number {
  const summary = isRecord(run.summary) ? run.summary : {};
  return parseNumberLike(run[key] ?? summary[key]);
}

export function getTaskProgress(run: SourceUrlAgentRun): { finished: number; total: number } {
  const summary = isRecord(run.summary) ? run.summary : {};
  const total = parseNumberLike(run.task_total_count ?? summary.task_total_count);
  const finished = parseNumberLike(run.task_finished_count ?? summary.task_finished_count);
  return { finished, total };
}

export function formatTaskProgress(run: SourceUrlAgentRun): string {
  const { finished, total } = getTaskProgress(run);
  return total > 0 ? `${finished.toLocaleString()} / ${total.toLocaleString()}` : "-";
}

function normalizeSourceType(value: unknown): string {
  return typeof value === "string" && value.trim().length > 0
    ? value.trim().toLowerCase().replace(/[_-]/g, " ")
    : "source";
}

export function sourceTypeLabel(source: VendorSourceCapability): string {
  const type = normalizeSourceType(source.source_type);
  if (type === "direct vendor" || type === "vendor" || type === "direct") {
    return "direct vendor";
  }

  return type;
}

export function capabilityBadges(source: VendorSourceCapability): string[] {
  const badges = [sourceTypeLabel(source)];
  if (source.capture_enabled && source.capture_implemented) {
    badges.push("capture ready");
  } else if (source.discovery_enabled) {
    badges.push("discovery only");
  }

  return badges;
}

export function activeTaskCount(runs: SourceUrlAgentRun[]): number {
  return runs.reduce((count, run) => {
    const taskCounts = isRecord(run.task_counts) ? run.task_counts : {};
    return count + parseNumberLike(taskCounts.queued) + parseNumberLike(taskCounts.running);
  }, 0);
}
