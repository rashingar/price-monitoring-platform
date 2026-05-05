import { CommerceApiError } from "./commerceClient";

export type CatalogReadinessReason =
  | "database_not_configured"
  | "database_unreachable"
  | "required_tables_missing"
  | "migrations_not_up_to_date"
  | "active_catalog_empty"
  | "unknown";

export interface CatalogReadinessBlock {
  reason: CatalogReadinessReason;
  message: string;
  details: string[];
  setupHints: string[];
}

export const CATALOG_READINESS_REQUIRED_MESSAGE =
  "Catalog database/import required. Configure PostgreSQL, run migrations, and import sourceCata.csv.";

const CATALOG_SETUP_HINTS = [
  "Configure PRICEFETCHER_DATABASE_URL.",
  "Run alembic upgrade head.",
  "Run python -m pricefetcher.jobs.ingest_catalog.",
  "Reload the Catalog page.",
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .filter((item): item is string | number => typeof item === "string" || typeof item === "number")
    .map((item) => String(item).trim())
    .filter((item) => item.length > 0);
}

function getNestedStatus(payload: Record<string, unknown>): Record<string, unknown> {
  for (const key of ["catalog_status", "readiness", "status", "db_status"]) {
    const value = payload[key];
    if (isRecord(value)) {
      return value;
    }
  }

  return {};
}

function getBoolean(payload: Record<string, unknown>, status: Record<string, unknown>, key: string): boolean | null {
  const value = payload[key] ?? status[key];
  return typeof value === "boolean" ? value : null;
}

function getMessageParts(payload: Record<string, unknown>, status: Record<string, unknown>): string[] {
  const parts = new Set<string>();

  for (const source of [payload, status]) {
    for (const key of ["detail", "message", "error", "code"]) {
      const value = source[key];
      if (typeof value === "string" && value.trim().length > 0) {
        parts.add(value.trim());
      }
    }

    toStringList(source.blocking_reasons).forEach((reason) => parts.add(reason));
    toStringList(source.warnings).forEach((warning) => parts.add(warning));
  }

  return Array.from(parts);
}

function includesCatalogRequiredSignal(payload: Record<string, unknown>, status: Record<string, unknown>): boolean {
  const requiredFor = [
    ...toStringList(payload.required_for),
    ...toStringList(status.required_for),
  ].map((item) => item.toLowerCase());
  if (requiredFor.some((item) => item.includes("catalog"))) {
    return true;
  }

  const hasStructuredReadinessField = [
    "configured",
    "reachable",
    "required_tables_present",
    "alembic_up_to_date",
    "ready_for_catalog",
    "active_catalog_empty",
    "catalog_imported",
    "active_catalog_imported",
  ].some((key) => key in payload || key in status);
  if (hasStructuredReadinessField) {
    return true;
  }

  const text = getMessageParts(payload, status).join(" ").toLowerCase();
  return (
    text.includes("catalog database/import required") ||
    text.includes("active catalog is empty") ||
    text.includes("catalog import") ||
    text.includes("ingest_catalog") ||
    text.includes("postgresql") ||
    text.includes("alembic")
  );
}

function classifyCatalogReadiness(
  payload: Record<string, unknown>,
  status: Record<string, unknown>,
  text: string,
): CatalogReadinessReason {
  const configured = getBoolean(payload, status, "configured");
  const reachable = getBoolean(payload, status, "reachable");
  const requiredTablesPresent = getBoolean(payload, status, "required_tables_present");
  const alembicUpToDate = getBoolean(payload, status, "alembic_up_to_date");
  const activeCatalogEmpty = getBoolean(payload, status, "active_catalog_empty");
  const catalogImported =
    getBoolean(payload, status, "catalog_imported") ?? getBoolean(payload, status, "active_catalog_imported");

  if (configured === false || /not configured|database url is not configured|pricefetcher_database_url/.test(text)) {
    return "database_not_configured";
  }

  if (
    (configured === true && reachable === false) ||
    /not reachable|unreachable|connection refused|could not connect|connect failed/.test(text)
  ) {
    return "database_unreachable";
  }

  if (requiredTablesPresent === false || /table.*missing|missing.*table|relation .* does not exist/.test(text)) {
    return "required_tables_missing";
  }

  if (
    activeCatalogEmpty === true ||
    catalogImported === false ||
    /active catalog is empty|active catalog.*empty|catalog import.*missing|import sourcecata|ingest_catalog|no active catalog/.test(
      text,
    )
  ) {
    return "active_catalog_empty";
  }

  if (alembicUpToDate === false || /migration|alembic/.test(text)) {
    return "migrations_not_up_to_date";
  }

  return "unknown";
}

function reasonDetail(reason: CatalogReadinessReason): string {
  switch (reason) {
    case "database_not_configured":
      return "Database is not configured. Set PRICEFETCHER_DATABASE_URL.";
    case "database_unreachable":
      return "Database is configured but not reachable. Check PostgreSQL service, credentials, and network reachability.";
    case "required_tables_missing":
      return "Required Catalog tables are missing.";
    case "migrations_not_up_to_date":
      return "Database migrations are not up to date.";
    case "active_catalog_empty":
      return "Active catalog is empty or the catalog import is missing.";
    case "unknown":
      return "Unknown Catalog readiness/error state.";
  }
}

function makeCatalogReadinessBlock(payload: Record<string, unknown>): CatalogReadinessBlock | null {
  const status = getNestedStatus(payload);
  if (!includesCatalogRequiredSignal(payload, status)) {
    return null;
  }

  const messageParts = getMessageParts(payload, status);
  const classifierText = messageParts
    .filter((part) => !part.startsWith(CATALOG_READINESS_REQUIRED_MESSAGE))
    .join(" ")
    .toLowerCase();
  const reason = classifyCatalogReadiness(payload, status, classifierText);
  const details = new Set<string>([reasonDetail(reason)]);

  messageParts.forEach((part) => {
    if (part !== CATALOG_READINESS_REQUIRED_MESSAGE) {
      details.add(part);
    }
  });

  return {
    reason,
    message: CATALOG_READINESS_REQUIRED_MESSAGE,
    details: Array.from(details),
    setupHints: CATALOG_SETUP_HINTS,
  };
}

export function getCatalogReadinessBlock(error: unknown): CatalogReadinessBlock | null {
  if (!(error instanceof CommerceApiError) || error.status !== 503 || !error.path?.startsWith("/catalog/")) {
    return null;
  }

  return isRecord(error.details) ? makeCatalogReadinessBlock(error.details) : null;
}

export function getCatalogReadinessWarning(warning: unknown): CatalogReadinessBlock | null {
  if (typeof warning !== "string" || warning.trim().length === 0) {
    return null;
  }

  return makeCatalogReadinessBlock({
    detail: warning,
    active_catalog_empty: /active catalog.*empty|ingest_catalog|import/i.test(warning),
    required_for: ["catalog"],
  });
}
