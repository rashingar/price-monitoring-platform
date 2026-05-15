import type { PlatformHealthStatus } from "./platformHealthTypes";

export function platformHealthStatusLabel(status: PlatformHealthStatus): string {
  if (status === "ready") {
    return "Ready";
  }
  if (status === "warning") {
    return "Warning";
  }
  if (status === "blocked") {
    return "Blocked";
  }
  return "Unknown";
}

export function platformHealthStatusClass(status: PlatformHealthStatus): string {
  if (status === "ready") {
    return "success";
  }
  if (status === "blocked") {
    return "danger";
  }
  if (status === "warning") {
    return "warning";
  }
  return "neutral";
}

export function platformHealthUpdatedAtLabel(value: string | null): string {
  if (!value) {
    return "Not checked";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}
