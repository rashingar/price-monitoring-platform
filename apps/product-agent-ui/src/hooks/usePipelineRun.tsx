import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";
import { apiClient, getApiErrorMessage } from "../api/client";
import {
  getJobIdentifier,
  getJobStatus,
  isCancelledJob,
  isActiveJob,
  isFailedJob,
  isSuccessfulJob,
  withJobStage,
} from "../api/jobUtils";
import type { Job, LogEntry, PrepareJobRequest, WorkflowType } from "../api/types";
import { useGlobalJobs } from "./useGlobalJobs";

const POLL_INTERVAL_MS = 2500;

type PipelineRunStatus = "idle" | "running" | "succeeded" | "failed" | "cancelled";
type PipelineStageStatus = "pending" | "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface PipelineStageState {
  key: WorkflowType;
  label: string;
  status: PipelineStageStatus;
  job?: Job;
  error?: string;
}

export interface PipelineRunState {
  runId: string;
  status: PipelineRunStatus;
  stages: PipelineStageState[];
  error: string | null;
  startedAt: Date;
  finishedAt: Date | null;
}

interface PipelineRunContextValue {
  currentRun: PipelineRunState | null;
  isRunning: boolean;
  startPipeline: (request: PrepareJobRequest) => Promise<void>;
  stopStageJob: (jobId: string, reason?: string) => Promise<void>;
  stoppingJobIds: string[];
  stopJobError: string | null;
}

const INITIAL_STAGES: PipelineStageState[] = [
  { key: "prepare", label: "Prepare", status: "pending" },
  { key: "render", label: "Render", status: "pending" },
  { key: "publish", label: "Publish", status: "pending" },
];

const PipelineRunContext = createContext<PipelineRunContextValue | null>(null);

class PipelineCancelledError extends Error {
  readonly job: Job;
  readonly stage: PipelineStageState;

  constructor(job: Job, stage: PipelineStageState) {
    const jobId = getJobIdentifier(job);
    super(`${stage.label} cancelled${jobId ? ` (job ${jobId})` : ""}.`);
    this.name = "PipelineCancelledError";
    this.job = job;
    this.stage = stage;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function getErrorDetail(value: unknown): string | undefined {
  if (typeof value === "string" && value.trim().length > 0) {
    return value.trim();
  }

  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    for (const key of ["message", "detail", "error"]) {
      const detail = getErrorDetail((value as Record<string, unknown>)[key]);
      if (detail) {
        return detail;
      }
    }
  }

  return undefined;
}

function getLogMessage(log: LogEntry): string {
  if (typeof log === "string") {
    return log;
  }

  if (typeof log.message === "string") {
    return log.message;
  }

  return JSON.stringify(log) ?? "Log entry";
}

function getFailureLogDetail(logs: LogEntry[]): string | undefined {
  const warningLines = logs
    .map(getLogMessage)
    .filter((line) => /warning/i.test(line))
    .slice(-2);

  if (warningLines.length > 0) {
    return warningLines.join(" | ");
  }

  const failureLines = logs
    .map(getLogMessage)
    .filter((line) => /error detail|failed/i.test(line))
    .slice(-2);

  return failureLines.length > 0 ? failureLines.join(" | ") : undefined;
}

function buildJobError(job: Job, stageLabel: string, logs: LogEntry[] = []): string {
  const jobId = getJobIdentifier(job);
  const status = getJobStatus(job);
  const context = `${stageLabel} failed${jobId ? ` (job ${jobId}, status ${status})` : ` (status ${status})`}`;
  const detail = getErrorDetail(job.error) ?? getErrorDetail(job.message);
  const errorCode = getErrorDetail(job.error_code);
  const detailWithCode = detail && errorCode ? `${detail} [${errorCode}]` : detail;
  const logDetail = getFailureLogDetail(logs);

  if (detailWithCode && logDetail) {
    return `${context}: ${detailWithCode}. Logs: ${logDetail}`;
  }

  if (detailWithCode) {
    return `${context}: ${detailWithCode}`;
  }

  return logDetail
    ? `${context}. Logs: ${logDetail}`
    : `${context}. No failure reason was returned by the backend. Open the job logs for more details.`;
}

function updateStage(
  stages: PipelineStageState[],
  key: WorkflowType,
  update: Partial<PipelineStageState>,
): PipelineStageState[] {
  return stages.map((stage) => (stage.key === key ? { ...stage, ...update } : stage));
}

export function PipelineRunProvider({ children }: { children: ReactNode }) {
  const { trackJob } = useGlobalJobs();
  const [currentRun, setCurrentRun] = useState<PipelineRunState | null>(null);
  const [stoppingJobIds, setStoppingJobIds] = useState<string[]>([]);
  const [stopJobError, setStopJobError] = useState<string | null>(null);
  const runningRef = useRef(false);

  const waitForTerminalJob = useCallback(
    async (job: Job, stage: PipelineStageState): Promise<Job> => {
      const jobId = getJobIdentifier(job);
      if (!jobId) {
        throw new Error(`${stage.label} response did not include job_id or id.`);
      }

      let nextJob = job;
      while (isActiveJob(nextJob)) {
        setCurrentRun((run) =>
          run
            ? {
                ...run,
                stages: updateStage(run.stages, stage.key, {
                  job: nextJob,
                  status: "running",
                }),
              }
            : run,
        );
        await sleep(POLL_INTERVAL_MS);
        nextJob = withJobStage(await apiClient.getJob(jobId), stage.key);
        trackJob(nextJob);
      }

      if (isCancelledJob(nextJob)) {
        setCurrentRun((run) =>
          run
            ? {
                ...run,
                status: "cancelled",
                error: null,
                finishedAt: new Date(),
                stages: updateStage(run.stages, stage.key, {
                  job: nextJob,
                  status: "cancelled",
                  error: undefined,
                }),
              }
            : run,
        );
        throw new PipelineCancelledError(nextJob, stage);
      }

      if (isFailedJob(nextJob)) {
        let failureLogs: LogEntry[] = [];
        try {
          failureLogs = await apiClient.getJobLogs(jobId);
        } catch {
          failureLogs = [];
        }
        const errorMessage = buildJobError(nextJob, stage.label, failureLogs);
        setCurrentRun((run) =>
          run
            ? {
                ...run,
                stages: updateStage(run.stages, stage.key, {
                  job: nextJob,
                  status: "failed",
                  error: errorMessage,
                }),
              }
            : run,
        );
        throw new Error(errorMessage);
      }

      if (!isSuccessfulJob(nextJob)) {
        throw new Error(`${stage.label} job stopped with status ${getJobStatus(nextJob)}.`);
      }

      return nextJob;
    },
    [trackJob],
  );

  const stopStageJob = useCallback(
    async (jobId: string, reason?: string) => {
      setStoppingJobIds((currentIds) =>
        currentIds.includes(jobId) ? currentIds : [...currentIds, jobId],
      );
      setStopJobError(null);

      try {
        const stoppedJob = await apiClient.stopJob(jobId, reason);
        trackJob(stoppedJob);
        setCurrentRun((run) => {
          if (!run) {
            return run;
          }

          const stoppedStage = run.stages.find((stage) => {
            const stageJobId = stage.job ? getJobIdentifier(stage.job) : undefined;
            return stageJobId === jobId;
          });

          return {
            ...run,
            status: "cancelled",
            error: null,
            finishedAt: run.finishedAt ?? new Date(),
            stages: stoppedStage
              ? updateStage(run.stages, stoppedStage.key, {
                  job: withJobStage(stoppedJob, stoppedStage.key),
                  status: "cancelled",
                  error: undefined,
                })
              : run.stages,
          };
        });
        setStopJobError(null);
      } catch (stopError) {
        setStopJobError(getApiErrorMessage(stopError));
      } finally {
        setStoppingJobIds((currentIds) => currentIds.filter((currentId) => currentId !== jobId));
      }
    },
    [trackJob],
  );

  const runStage = useCallback(
    async (stage: PipelineStageState, createJob: () => Promise<Job>): Promise<Job> => {
      setCurrentRun((run) =>
        run
          ? {
              ...run,
              stages: updateStage(run.stages, stage.key, {
                status: "queued",
                error: undefined,
              }),
            }
          : run,
      );

      const job = await createJob();
      trackJob(job);
      setCurrentRun((run) =>
        run
          ? {
              ...run,
              stages: updateStage(run.stages, stage.key, {
                job,
                status: isActiveJob(job) ? "running" : "queued",
              }),
            }
          : run,
      );

      const completedJob = await waitForTerminalJob(job, stage);
      trackJob(completedJob);
      setCurrentRun((run) =>
        run
          ? {
              ...run,
              stages: updateStage(run.stages, stage.key, {
                job: completedJob,
                status: "succeeded",
              }),
            }
          : run,
      );

      return completedJob;
    },
    [trackJob, waitForTerminalJob],
  );

  const startPipeline = useCallback(
    async (request: PrepareJobRequest) => {
      if (runningRef.current) {
        return;
      }

      runningRef.current = true;
      const runId = `${Date.now()}`;
      setCurrentRun({
        runId,
        status: "running",
        stages: INITIAL_STAGES,
        error: null,
        startedAt: new Date(),
        finishedAt: null,
      });

      try {
        const prepareStage = INITIAL_STAGES[0];
        const renderStage = INITIAL_STAGES[1];
        const publishStage = INITIAL_STAGES[2];

        await runStage(prepareStage, () => apiClient.createPrepareJob(request));
        await runStage(renderStage, () => apiClient.createRenderJob({ model: request.model }));
        await runStage(publishStage, () => apiClient.createPublishJob({ model: request.model }));

        setCurrentRun((run) =>
          run
            ? {
                ...run,
                status: "succeeded",
                error: null,
                finishedAt: new Date(),
              }
            : run,
        );
      } catch (pipelineError) {
        if (pipelineError instanceof PipelineCancelledError) {
          setCurrentRun((run) =>
            run
              ? {
                  ...run,
                  status: "cancelled",
                  error: null,
                  finishedAt: run.finishedAt ?? new Date(),
                  stages: updateStage(run.stages, pipelineError.stage.key, {
                    job: pipelineError.job,
                    status: "cancelled",
                    error: undefined,
                  }),
                }
              : run,
          );
          return;
        }

        const errorMessage = getApiErrorMessage(pipelineError);
        setCurrentRun((run) =>
          run
            ? {
                ...run,
                status: "failed",
                error: errorMessage,
                finishedAt: new Date(),
                stages: run.stages.map((stage) =>
                  stage.status === "running" || stage.status === "queued"
                    ? { ...stage, status: "failed", error: errorMessage }
                    : stage,
                ),
              }
            : run,
        );
      } finally {
        runningRef.current = false;
      }
    },
    [runStage],
  );

  const value = useMemo<PipelineRunContextValue>(
    () => ({
      currentRun,
      isRunning: currentRun?.status === "running",
      startPipeline,
      stopStageJob,
      stoppingJobIds,
      stopJobError,
    }),
    [currentRun, startPipeline, stopJobError, stopStageJob, stoppingJobIds],
  );

  return <PipelineRunContext.Provider value={value}>{children}</PipelineRunContext.Provider>;
}

export function usePipelineRun() {
  const context = useContext(PipelineRunContext);
  if (!context) {
    throw new Error("usePipelineRun must be used within PipelineRunProvider.");
  }

  return context;
}
