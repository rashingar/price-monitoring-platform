import { useCallback, useEffect, useMemo, useState } from "react";
import { apiClient, getApiErrorMessage } from "../api/client";
import { isActiveJob } from "../api/jobUtils";
import type { Artifact, Job, LogEntry } from "../api/types";

const POLL_INTERVAL_MS = 2500;

export function useJobDetail(jobId: string | undefined) {
  const [job, setJob] = useState<Job | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [isLoading, setIsLoading] = useState(Boolean(jobId));
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stopError, setStopError] = useState<string | null>(null);
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null);

  const shouldPoll = useMemo(() => isActiveJob(job ?? undefined), [job]);

  const loadJobAssets = useCallback(
    async (signal?: AbortSignal) => {
      if (!jobId) {
        return;
      }

      const [nextLogs, nextArtifacts] = await Promise.all([
        apiClient.getJobLogs(jobId, signal),
        apiClient.getJobArtifacts(jobId, signal),
      ]);
      if (signal?.aborted) {
        return;
      }

      setLogs(nextLogs);
      setArtifacts(nextArtifacts);
    },
    [jobId],
  );

  const loadJob = useCallback(
    async (signal?: AbortSignal, silent = false) => {
      if (!jobId) {
        setError("Missing job id.");
        setIsLoading(false);
        return;
      }

      if (silent) {
        setIsRefreshing(true);
      } else {
        setIsLoading(true);
      }

      try {
        const nextJob = await apiClient.getJob(jobId, signal);
        if (signal?.aborted) {
          return;
        }
        setJob(nextJob);

        await loadJobAssets(signal);
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
    },
    [jobId, loadJobAssets],
  );

  const stopJob = useCallback(
    async (reason?: string) => {
      if (!jobId) {
        setStopError("Missing job id.");
        return;
      }

      setIsStopping(true);
      setStopError(null);

      try {
        const stoppedJob = await apiClient.stopJob(jobId, reason);
        setJob(stoppedJob);
        await loadJobAssets();
        setStopError(null);
        setLastLoadedAt(new Date());
      } catch (stopErrorValue) {
        setStopError(getApiErrorMessage(stopErrorValue));
      } finally {
        setIsStopping(false);
      }
    },
    [jobId, loadJobAssets],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadJob(controller.signal);
    return () => controller.abort();
  }, [loadJob]);

  useEffect(() => {
    if (!shouldPoll) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      void loadJob(undefined, true);
    }, POLL_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [loadJob, shouldPoll]);

  return {
    job,
    logs,
    artifacts,
    isLoading,
    isRefreshing,
    isStopping,
    error,
    stopError,
    isPolling: shouldPoll,
    lastLoadedAt,
    reload: () => loadJob(undefined, false),
    stopJob,
  };
}
