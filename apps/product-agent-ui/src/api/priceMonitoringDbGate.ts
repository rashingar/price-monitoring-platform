import type { PriceMonitoringDbStatus } from "./commerceTypes";

export const PRICE_MONITORING_DB_REQUIRED_MESSAGE =
  "PostgreSQL is required for Price Monitoring. CSV/Bridge, files, paths, artifacts, and general commerce health may still be available.";

export function isPriceMonitoringDbReady(status: PriceMonitoringDbStatus | null): boolean {
  return status?.ready_for_price_monitoring === true;
}

export function getPriceMonitoringDbWarnings(status: PriceMonitoringDbStatus | null): string[] {
  if (!status) {
    return ["Database readiness is unknown."];
  }

  const warnings = new Set<string>();

  for (const reason of status.blocking_reasons ?? []) {
    if (reason.trim().length > 0) {
      warnings.add(reason);
    }
  }

  if (!status.configured) {
    warnings.add("PostgreSQL is not configured.");
  }

  if (status.configured && !status.reachable) {
    warnings.add("PostgreSQL is configured but not reachable.");
  }

  if (status.required_tables_present === false) {
    warnings.add("Required Price Monitoring tables are missing.");
  }

  if (status.alembic_up_to_date === false) {
    warnings.add("Database migrations are not up to date.");
  }

  if (status.error) {
    warnings.add(status.error);
  }

  return Array.from(warnings);
}

export function getPriceMonitoringDbBlockingMessage(status: PriceMonitoringDbStatus | null): string {
  const warnings = getPriceMonitoringDbWarnings(status);
  return warnings.length > 0
    ? `${PRICE_MONITORING_DB_REQUIRED_MESSAGE} ${warnings[0]}`
    : PRICE_MONITORING_DB_REQUIRED_MESSAGE;
}
