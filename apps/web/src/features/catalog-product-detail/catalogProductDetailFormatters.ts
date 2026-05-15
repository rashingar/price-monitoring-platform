import type { SourceUrl } from "./catalogProductDetailTypes";

export function formatDetailValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function formatMoney(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 2,
  }).format(value);
}

export function statusTone(value: string | number | null | undefined): string {
  const status = String(value ?? "").toLowerCase();
  if (["active", "success", "succeeded", "ready", "1", "yes", "true"].includes(status)) {
    return "success";
  }
  if (["needs_review", "queued", "pending", "warning"].includes(status)) {
    return "warning";
  }
  if (["broken", "failed", "error", "disabled", "0", "false"].includes(status)) {
    return "danger";
  }
  if (status === "redirected") {
    return "active";
  }
  return "neutral";
}

export function sourceUrlCaptureStatus(sourceUrl: SourceUrl): string | null {
  return (
    sourceUrl.capture_status ??
    sourceUrl.last_capture_status ??
    sourceUrl.last_fetch_status ??
    null
  );
}

export function recordEntries(record: Record<string, number> | null | undefined) {
  return Object.entries(record ?? {}).sort(([left], [right]) => left.localeCompare(right));
}

