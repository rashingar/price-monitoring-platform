const SOURCE_REQUIRED_MESSAGE = "Choose one source/vendor to monitor.";

export function normalizeFetchStatus(status: unknown): string {
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

export function isActiveFetchStatus(status: unknown): boolean {
  const normalized = normalizeFetchStatus(status);
  return normalized === "queued" || normalized === "running";
}

export function isSuccessfulFetchStatus(status: unknown): boolean {
  return normalizeFetchStatus(status) === "succeeded";
}

export function isFailedFetchStatus(status: unknown): boolean {
  const normalized = normalizeFetchStatus(status);
  return normalized === "failed" || normalized === "killed";
}

export function isCancelledFetchStatus(status: unknown): boolean {
  return normalizeFetchStatus(status) === "cancelled";
}

export function isTerminalFetchStatus(status: unknown): boolean {
  return (
    isSuccessfulFetchStatus(status) ||
    isFailedFetchStatus(status) ||
    isCancelledFetchStatus(status)
  );
}

export function getFetchStatusTone(status: unknown): string {
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

export function formatFetchStatus(status: unknown): string {
  const normalized = normalizeFetchStatus(status);
  if (!normalized) {
    return "-";
  }

  return normalized.replace(/_/g, " ").replace(/^\w/, (first) => first.toUpperCase());
}

export function usePriceMonitoringRun({
  fetchStatus,
  isFetchLoading,
  dbAvailable,
  dbBlockingMessage,
  sourceRequired,
}: {
  fetchStatus: unknown;
  isFetchLoading: boolean;
  dbAvailable: boolean;
  dbBlockingMessage: string;
  sourceRequired: boolean;
}) {
  const isFetchActive = isActiveFetchStatus(fetchStatus);
  const dbActionTitle = dbAvailable ? undefined : dbBlockingMessage;
  const sourceActionTitle = sourceRequired ? SOURCE_REQUIRED_MESSAGE : dbActionTitle;
  const fetchButtonLabel = isFetchLoading
    ? "Starting monitoring..."
    : isFetchActive
      ? "Monitoring running..."
      : "Monitor prices";

  return {
    isFetchActive,
    isReviewBlockedByFetch: isFetchActive,
    dbActionTitle,
    sourceActionTitle,
    fetchButtonLabel,
  };
}
