export interface JobProgressStep {
  step?: string;
  label?: string;
  started_at?: string;
  completed_at?: string;
  elapsed_seconds?: number;
}

export interface JobProgress {
  current_step?: string;
  current_step_label?: string;
  steps_completed?: number;
  step_started_at?: string;
  last_progress_at?: string;
  elapsed_seconds?: number;
  current_step_elapsed_seconds?: number;
  completed_steps?: JobProgressStep[];
  details?: Record<string, unknown>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim().length > 0 ? value : undefined;
}

function normalizeCompletedStep(value: unknown): JobProgressStep | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    step: stringValue(value.step),
    label: stringValue(value.label),
    started_at: stringValue(value.started_at),
    completed_at: stringValue(value.completed_at),
    elapsed_seconds: numberValue(value.elapsed_seconds),
  };
}

export function getJobProgress(job: { result?: unknown; progress?: unknown } | null | undefined): JobProgress | null {
  if (!job) {
    return null;
  }

  const result = isRecord(job.result) ? job.result : null;
  const rawProgress = isRecord(result?.progress) ? result.progress : isRecord(job.progress) ? job.progress : null;
  if (!rawProgress) {
    return null;
  }

  const currentStep = stringValue(rawProgress.current_step);
  const currentStepLabel = stringValue(rawProgress.current_step_label);
  const lastProgressAt = stringValue(rawProgress.last_progress_at ?? rawProgress.updated_at);
  const completedSteps = Array.isArray(rawProgress.completed_steps)
    ? rawProgress.completed_steps.map(normalizeCompletedStep).filter((step): step is JobProgressStep => step !== null)
    : [];

  if (!currentStep && !currentStepLabel && !lastProgressAt && completedSteps.length === 0) {
    return null;
  }

  return {
    current_step: currentStep,
    current_step_label: currentStepLabel,
    steps_completed: numberValue(rawProgress.steps_completed),
    step_started_at: stringValue(rawProgress.step_started_at),
    last_progress_at: lastProgressAt,
    elapsed_seconds: numberValue(rawProgress.elapsed_seconds),
    current_step_elapsed_seconds: numberValue(rawProgress.current_step_elapsed_seconds),
    completed_steps: completedSteps,
    details: isRecord(rawProgress.details) ? rawProgress.details : undefined,
  };
}

export function formatDurationSeconds(value: number | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }

  const totalSeconds = Math.max(0, Math.round(value));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes <= 0) {
    return `${seconds}s`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours <= 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${hours}h ${remainingMinutes}m ${seconds}s`;
}
