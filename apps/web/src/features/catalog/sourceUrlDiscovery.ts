import type { SourceUrlAgentRun } from "../../api/commerceTypes";

export function getSourceUrlAgentRunId(run: SourceUrlAgentRun | null): string | null {
  const value = run?.run_id ?? run?.id;
  return value === null || value === undefined || value === "" ? null : String(value);
}

export function isActiveSourceUrlAgentRun(run: SourceUrlAgentRun | null): boolean {
  const status = typeof run?.status === "string" ? run.status.toLowerCase() : "";
  return status === "queued" || status === "running";
}

export function getSourceUrlAgentRunCount(run: SourceUrlAgentRun | null, key: keyof SourceUrlAgentRun): number {
  const summary = typeof run?.summary === "object" && run.summary !== null ? run.summary : {};
  const value = run?.[key] ?? summary[key];
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  return 0;
}

export function getSourceUrlAgentTaskProgress(run: SourceUrlAgentRun | null): string {
  const total = getSourceUrlAgentRunCount(run, "task_total_count");
  const finished = getSourceUrlAgentRunCount(run, "task_finished_count");
  return total > 0 ? `${finished.toLocaleString()} / ${total.toLocaleString()}` : "-";
}
