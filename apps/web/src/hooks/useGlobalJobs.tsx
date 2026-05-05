import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { apiClient, getApiErrorMessage } from "../api/client";
import {
  compareJobsByUpdatedDesc,
  getJobIdentifier,
  getJobStage,
  isActiveJob,
  withJobStage,
} from "../api/jobUtils";
import type { Job } from "../api/types";

const POLL_INTERVAL_MS = 2500;

interface GlobalJobsState {
  jobs: Job[];
  isLoading: boolean;
  isRefreshing: boolean;
  error: string | null;
  isPolling: boolean;
  lastLoadedAt: Date | null;
  stoppingJobIds: string[];
  stopJobError: string | null;
  clearStopJobError: () => void;
  reload: () => Promise<void>;
  trackJob: (job: Job) => void;
  stopJob: (jobId: string, reason?: string) => Promise<void>;
}

const GlobalJobsContext = createContext<GlobalJobsState | null>(null);

function mergeJob(jobs: Job[], job: Job): Job[] {
  const nextJobId = getJobIdentifier(job);
  if (!nextJobId) {
    return jobs;
  }

  const existingIndex = jobs.findIndex((existingJob) => getJobIdentifier(existingJob) === nextJobId);
  const existingJob = existingIndex === -1 ? undefined : jobs[existingIndex];
  const nextJob =
    !getJobStage(job) && existingJob
      ? withExistingStage(job, existingJob)
      : job;
  if (existingIndex === -1) {
    return [nextJob, ...jobs].sort(compareJobsByUpdatedDesc);
  }

  return jobs
    .map((currentJob, index) => (index === existingIndex ? nextJob : currentJob))
    .sort(compareJobsByUpdatedDesc);
}

function withExistingStage(job: Job, existingJob: Job): Job {
  const existingStage = getJobStage(existingJob);
  return existingStage ? withJobStage(job, existingStage) : job;
}

function preserveKnownStages(currentJobs: Job[], nextJobs: Job[]): Job[] {
  return nextJobs.map((job) => {
    if (getJobStage(job)) {
      return job;
    }

    const jobId = getJobIdentifier(job);
    const existingJob = jobId
      ? currentJobs.find((currentJob) => getJobIdentifier(currentJob) === jobId)
      : undefined;
    return existingJob ? withExistingStage(job, existingJob) : job;
  });
}

export function GlobalJobsProvider({ children }: { children: ReactNode }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stoppingJobIds, setStoppingJobIds] = useState<string[]>([]);
  const [stopJobError, setStopJobError] = useState<string | null>(null);
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null);

  const hasActiveJobs = useMemo(() => jobs.some(isActiveJob), [jobs]);

  const loadJobs = useCallback(async (signal?: AbortSignal, silent = false) => {
    if (silent) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    try {
      const nextJobs = await apiClient.listJobs(signal);
      if (signal?.aborted) {
        return;
      }

      setJobs((currentJobs) =>
        preserveKnownStages(currentJobs, nextJobs).sort(compareJobsByUpdatedDesc),
      );
      setError(null);
      setLastLoadedAt(new Date());
    } catch (loadError) {
      if (!signal?.aborted) {
        setError(getApiErrorMessage(loadError));
      }
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    }
  }, []);

  const trackJob = useCallback((job: Job) => {
    setJobs((currentJobs) => mergeJob(currentJobs, job));
  }, []);

  const stopJob = useCallback(async (jobId: string, reason?: string) => {
    setStoppingJobIds((currentIds) =>
      currentIds.includes(jobId) ? currentIds : [...currentIds, jobId],
    );
    setStopJobError(null);

    try {
      const stoppedJob = await apiClient.stopJob(jobId, reason);
      setJobs((currentJobs) => mergeJob(currentJobs, stoppedJob));
      setStopJobError(null);
    } catch (stopError) {
      setStopJobError(getApiErrorMessage(stopError));
    } finally {
      setStoppingJobIds((currentIds) => currentIds.filter((currentId) => currentId !== jobId));
    }
  }, []);

  const clearStopJobError = useCallback(() => {
    setStopJobError(null);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadJobs(controller.signal);
    return () => controller.abort();
  }, [loadJobs]);

  useEffect(() => {
    if (!hasActiveJobs) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      void loadJobs(undefined, true);
    }, POLL_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [hasActiveJobs, loadJobs]);

  const value = useMemo<GlobalJobsState>(
    () => ({
      jobs,
      isLoading,
      isRefreshing,
      error,
      isPolling: hasActiveJobs,
      lastLoadedAt,
      stoppingJobIds,
      stopJobError,
      clearStopJobError,
      reload: () => loadJobs(undefined, false),
      trackJob,
      stopJob,
    }),
    [
      clearStopJobError,
      error,
      hasActiveJobs,
      isLoading,
      isRefreshing,
      jobs,
      lastLoadedAt,
      loadJobs,
      stopJob,
      stopJobError,
      stoppingJobIds,
      trackJob,
    ],
  );

  return <GlobalJobsContext.Provider value={value}>{children}</GlobalJobsContext.Provider>;
}

export function useGlobalJobs() {
  const context = useContext(GlobalJobsContext);
  if (!context) {
    throw new Error("useGlobalJobs must be used within GlobalJobsProvider.");
  }

  return context;
}
