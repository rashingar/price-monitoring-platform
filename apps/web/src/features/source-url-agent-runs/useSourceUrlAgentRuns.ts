import { useCallback, useEffect, useMemo, useState } from "react";
import { commerceClient, getCommerceApiErrorMessage } from "../../api/commerceClient";
import type { SourceUrlAgentRun } from "../../api/commerceTypes";
import {
  getCounter,
  getRunId,
  isActiveStatus,
} from "./sourceUrlAgentRunFormatters";
import type { SourceUrlAgentRunTotals } from "./sourceUrlAgentRunTypes";

export function mergeSourceUrlAgentRun(
  runs: SourceUrlAgentRun[],
  nextRun: SourceUrlAgentRun,
): SourceUrlAgentRun[] {
  const nextRunId = getRunId(nextRun);
  const existingIndex = runs.findIndex((run) => getRunId(run) === nextRunId);
  if (existingIndex < 0) {
    return [nextRun, ...runs];
  }

  return runs.map((run, index) => (index === existingIndex ? { ...run, ...nextRun } : run));
}

export function useSourceUrlAgentRuns() {
  const [runs, setRuns] = useState<SourceUrlAgentRun[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [refreshingRunId, setRefreshingRunId] = useState<string | null>(null);

  const loadRuns = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    try {
      const nextRuns = await commerceClient.listSourceUrlAgentRuns(signal);
      if (!signal?.aborted) {
        setRuns(nextRuns);
        setError(null);
      }
    } catch (loadError) {
      if (!signal?.aborted) {
        setRuns([]);
        setError(getCommerceApiErrorMessage(loadError));
      }
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
      }
    }
  }, []);

  const mergeRun = useCallback((nextRun: SourceUrlAgentRun) => {
    setRuns((current) => mergeSourceUrlAgentRun(current, nextRun));
  }, []);

  const refreshRun = useCallback(async (run: SourceUrlAgentRun) => {
    const runId = getRunId(run);
    if (runId === "-") {
      return;
    }

    setRefreshingRunId(runId);
    setNotice(null);
    try {
      const nextRun = await commerceClient.getSourceUrlAgentRun(runId);
      mergeRun(nextRun);
    } catch (refreshError) {
      setNotice(getCommerceApiErrorMessage(refreshError));
    } finally {
      setRefreshingRunId(null);
    }
  }, [mergeRun]);

  useEffect(() => {
    const controller = new AbortController();
    void loadRuns(controller.signal);
    return () => controller.abort();
  }, [loadRuns]);

  const hasActiveRuns = useMemo(() => runs.some((run) => isActiveStatus(run.status)), [runs]);

  useEffect(() => {
    if (!hasActiveRuns) {
      return;
    }

    const timer = window.setInterval(() => {
      void loadRuns();
    }, 2_500);
    return () => window.clearInterval(timer);
  }, [hasActiveRuns, loadRuns]);

  const totals = useMemo(
    () =>
      runs.reduce<SourceUrlAgentRunTotals>(
        (summary, run) => ({
          selected_count: summary.selected_count + getCounter(run, "selected_count"),
          candidate_count: summary.candidate_count + getCounter(run, "candidate_count"),
          needs_review_count: summary.needs_review_count + getCounter(run, "needs_review_count"),
          error_count: summary.error_count + getCounter(run, "error_count"),
        }),
        {
          selected_count: 0,
          candidate_count: 0,
          needs_review_count: 0,
          error_count: 0,
        },
      ),
    [runs],
  );

  return {
    runs,
    isLoading,
    error,
    notice,
    refreshingRunId,
    totals,
    loadRuns,
    refreshRun,
    mergeRun,
  };
}
