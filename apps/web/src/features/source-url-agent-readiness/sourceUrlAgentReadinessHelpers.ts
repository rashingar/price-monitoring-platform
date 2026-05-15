import type {
  SourceUrlAgentProviderReadiness,
  SourceUrlAgentReadiness,
} from "../../api/commerceTypes";
import type { SourceUrlAgentReadinessStatus } from "./sourceUrlAgentReadinessTypes";

export function readinessStatusLabel(status: SourceUrlAgentReadinessStatus | string | null | undefined): string {
  const normalized = normalizeReadinessStatus(status);
  if (normalized === "ready") {
    return "Ready";
  }
  if (normalized === "warning") {
    return "Warning";
  }
  return "Blocked";
}

export function normalizeReadinessStatus(
  status: SourceUrlAgentReadinessStatus | string | null | undefined,
): SourceUrlAgentReadinessStatus {
  return status === "ready" || status === "warning" ? status : "blocked";
}

export function readinessStatusClass(status: SourceUrlAgentReadinessStatus | string | null | undefined): string {
  const normalized = normalizeReadinessStatus(status);
  if (normalized === "ready") {
    return "success";
  }
  if (normalized === "warning") {
    return "warning";
  }
  return "danger";
}

export function providerConfiguredLabel(provider: SourceUrlAgentProviderReadiness): string {
  if (!provider.enabled) {
    return "Disabled";
  }
  return provider.configured ? "Provider configured" : "Missing configuration";
}

export function providerConfiguredStatusClass(provider: SourceUrlAgentProviderReadiness): string {
  if (!provider.enabled) {
    return "neutral";
  }
  return provider.configured ? "success" : "danger";
}

export function providerEnabledLabel(enabled: boolean): string {
  return enabled ? "Enabled" : "Disabled";
}

export function launchDisabledReason(
  readiness: SourceUrlAgentReadiness | null,
  isLoading: boolean,
  error: string | null,
): string | null {
  if (isLoading) {
    return "Launch disabled: checking provider readiness.";
  }
  if (error) {
    return "Launch disabled: readiness check failed. Refresh readiness before launching.";
  }
  if (!readiness) {
    return "Launch disabled: provider readiness is unavailable.";
  }
  if (readiness.status !== "blocked") {
    return null;
  }

  const reason = readiness.blocking_reasons[0] ?? missingEnvLaunchReason(readiness);
  return `Launch disabled: ${reason}`;
}

function missingEnvLaunchReason(readiness: SourceUrlAgentReadiness): string {
  const missingKeys = readiness.providers.flatMap((provider) => provider.missing_env_keys);
  return missingKeys.length > 0
    ? `${missingKeys[0]} is missing.`
    : "no configured Source URL Agent search provider is available.";
}

