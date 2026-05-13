export function normalizePriceMonitoringFetchStatus(value: unknown): string | null {
  if (typeof value !== "string" || value.trim().length === 0) {
    return null;
  }

  if (value === "fetch_completed") {
    return "succeeded";
  }

  if (value === "fetch_failed") {
    return "failed";
  }

  return value;
}
