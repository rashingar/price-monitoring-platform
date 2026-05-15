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

export function formatMoney(value: unknown): string {
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

export function formatConfidence(value: unknown): string {
  const numericValue = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(numericValue) ? numericValue.toFixed(4) : "-";
}

export function statusClass(status: string | null | undefined): string {
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

export function normalizeLabel(value: string | null | undefined): string {
  return value ? value.replace(/_/g, " ") : "-";
}
