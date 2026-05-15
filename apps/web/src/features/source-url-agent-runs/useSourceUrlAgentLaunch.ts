import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { commerceClient, getCommerceApiErrorMessage } from "../../api/commerceClient";
import type { SourceUrlAgentReadiness, SourceUrlAgentRun, SourceUrlAgentRunRequest } from "../../api/commerceTypes";
import { launchDisabledReason } from "../source-url-agent-readiness/sourceUrlAgentReadinessHelpers";
import { DEFAULT_RUN_REQUEST } from "./sourceUrlAgentRunConstants";
import { getRunId } from "./sourceUrlAgentRunFormatters";
import {
  buildRunRequestFromHandoff,
  clearAutoLaunchParam,
  makeRunRequest,
} from "./sourceUrlAgentRunHandoff";
import type { SourceUrlAgentReadinessState } from "./sourceUrlAgentRunTypes";

type UseSourceUrlAgentLaunchParams = {
  searchParams: URLSearchParams;
  setSearchParams: (nextInit: URLSearchParams, navigateOptions?: { replace?: boolean }) => void;
  handoffModelCount: number;
  onRunCreated: (run: SourceUrlAgentRun) => void;
};

export function useSourceUrlAgentLaunch({
  searchParams,
  setSearchParams,
  handoffModelCount,
  onRunCreated,
}: UseSourceUrlAgentLaunchParams) {
  const shouldAutoLaunch = searchParams.get("auto_launch") === "1";
  const autoLaunchKey = searchParams.toString();
  const autoLaunchStartedRef = useRef<string | null>(null);
  const [form, setForm] = useState<SourceUrlAgentRunRequest>(() => buildRunRequestFromHandoff(searchParams));
  const [isLaunching, setIsLaunching] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [readinessState, setReadinessState] = useState<SourceUrlAgentReadinessState>({
    readiness: null,
    isLoading: true,
    error: null,
  });

  const updateForm = useCallback(
    <Key extends keyof SourceUrlAgentRunRequest>(key: Key, value: SourceUrlAgentRunRequest[Key]) => {
      setForm((current) => ({ ...current, [key]: value }));
    },
    [],
  );

  const resetDefaults = useCallback(() => {
    setForm(DEFAULT_RUN_REQUEST);
  }, []);

  const launchBlockReason = launchDisabledReason(
    readinessState.readiness,
    readinessState.isLoading,
    readinessState.error,
  );
  const isLaunchDisabled = isLaunching || Boolean(launchBlockReason);

  const launchRun = useCallback(async (requestOverride?: SourceUrlAgentRunRequest) => {
    const disabledReason = launchDisabledReason(
      readinessState.readiness,
      readinessState.isLoading,
      readinessState.error,
    );
    if (disabledReason) {
      setNotice(disabledReason);
      return;
    }

    setIsLaunching(true);
    setNotice(null);
    try {
      const createdRun = await commerceClient.createSourceUrlAgentRun(makeRunRequest(requestOverride ?? form));
      onRunCreated(createdRun);
      setNotice(`Find Source run ${getRunId(createdRun)} launched.`);
    } catch (launchError) {
      setNotice(getCommerceApiErrorMessage(launchError));
    } finally {
      setIsLaunching(false);
    }
  }, [form, onRunCreated, readinessState.error, readinessState.isLoading, readinessState.readiness]);

  useEffect(() => {
    setForm(buildRunRequestFromHandoff(searchParams));
  }, [searchParams]);

  useEffect(() => {
    if (!shouldAutoLaunch || handoffModelCount === 0 || autoLaunchStartedRef.current === autoLaunchKey) {
      return;
    }
    if (readinessState.isLoading) {
      return;
    }

    autoLaunchStartedRef.current = autoLaunchKey;
    void launchRun(buildRunRequestFromHandoff(searchParams)).finally(() => {
      setSearchParams(clearAutoLaunchParam(searchParams), { replace: true });
    });
  }, [
    autoLaunchKey,
    handoffModelCount,
    launchRun,
    readinessState.isLoading,
    searchParams,
    setSearchParams,
    shouldAutoLaunch,
  ]);

  const handleReadinessStateChange = useCallback(
    (state: { readiness: SourceUrlAgentReadiness | null; isLoading: boolean; error: string | null }) => {
      setReadinessState(state);
    },
    [],
  );

  return useMemo(
    () => ({
      form,
      updateForm,
      resetDefaults,
      launchRun,
      isLaunching,
      notice,
      launchBlockReason,
      isLaunchDisabled,
      readinessState,
      handleReadinessStateChange,
    }),
    [
      form,
      handleReadinessStateChange,
      isLaunchDisabled,
      isLaunching,
      launchBlockReason,
      launchRun,
      notice,
      readinessState,
      resetDefaults,
      updateForm,
    ],
  );
}
