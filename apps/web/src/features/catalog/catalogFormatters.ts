import type { CatalogSummary } from "../../api/commerceTypes";

export function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return String(value);
}

export function formatMoney(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }

  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 2,
  }).format(value);
}

export function getSummaryNumber(summary: CatalogSummary | null, keys: string[]): number | null {
  if (!summary) {
    return null;
  }

  for (const key of keys) {
    const value = summary[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
  }

  return null;
}

export function getMarketplaceStatus(value: number | null | undefined): string {
  if (value === 1) {
    return "active";
  }

  if (value === 0) {
    return "inactive";
  }

  return formatValue(value);
}

export function formatOptionCount(count: number | null | undefined): string {
  return typeof count === "number" && Number.isFinite(count) ? ` (${count})` : "";
}
