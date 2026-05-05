interface StatusBadgeProps {
  status: string;
}

function getStatusTone(status: string): string {
  const normalized = status.trim().toLowerCase();
  if (["succeeded", "success", "completed", "done"].includes(normalized)) {
    return "success";
  }

  if (["failed", "failure", "error", "killed"].includes(normalized)) {
    return "danger";
  }

  if (["cancelled", "canceled", "stopped"].includes(normalized)) {
    return "warning";
  }

  if (["queued", "pending"].includes(normalized)) {
    return "queued";
  }

  if (["running", "in_progress", "preparing", "rendering", "publishing"].includes(normalized)) {
    return "active";
  }

  return "neutral";
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const normalized = status.trim().toLowerCase();
  const label = ["cancelled", "canceled", "stopped"].includes(normalized) ? "cancelled" : status;
  return <span className={`status-badge ${getStatusTone(status)}`}>{label}</span>;
}
