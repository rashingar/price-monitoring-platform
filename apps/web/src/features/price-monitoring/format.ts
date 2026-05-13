export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function formatValue(value: unknown): string {
  if (isRecord(value) && typeof value.path === "string") {
    return value.path;
  }

  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return String(value);
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

  return new Intl.NumberFormat("el-GR", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(parsed);
}
