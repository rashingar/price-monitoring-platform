import { useCallback, useMemo, useState } from "react";
import { commerceClient, getCommerceApiErrorMessage } from "../../api/commerceClient";
import type { SourceUrlAgentRun, SourceUrlAgentRunArtifactsResponse } from "../../api/commerceTypes";
import { getRunId } from "./sourceUrlAgentRunFormatters";

export function useSourceUrlAgentArtifacts() {
  const [artifactRunId, setArtifactRunId] = useState<string | null>(null);
  const [artifactResponse, setArtifactResponse] = useState<SourceUrlAgentRunArtifactsResponse | null>(null);
  const [isArtifactsLoading, setIsArtifactsLoading] = useState(false);
  const [artifactError, setArtifactError] = useState<string | null>(null);

  const openArtifacts = useCallback(async (run: SourceUrlAgentRun) => {
    const runId = getRunId(run);
    if (runId === "-") {
      return;
    }

    setArtifactRunId(runId);
    setArtifactResponse(null);
    setArtifactError(null);
    setIsArtifactsLoading(true);
    try {
      const response = await commerceClient.listSourceUrlAgentRunArtifacts(runId);
      setArtifactResponse(response);
    } catch (artifactsError) {
      const inlineArtifacts = Array.isArray(run.artifacts) ? run.artifacts : [];
      setArtifactResponse({ run_id: runId, items: inlineArtifacts });
      setArtifactError(getCommerceApiErrorMessage(artifactsError));
    } finally {
      setIsArtifactsLoading(false);
    }
  }, []);

  const closeArtifacts = useCallback(() => {
    setArtifactRunId(null);
    setArtifactResponse(null);
    setArtifactError(null);
  }, []);

  const previewArtifact = useCallback(async (path: string) => {
    const response = await commerceClient.readArtifact(path, 200_000);
    return response.content;
  }, []);

  const artifacts = useMemo(() => artifactResponse?.items ?? [], [artifactResponse]);

  return {
    artifactRunId,
    artifactResponse,
    artifacts,
    isArtifactsLoading,
    artifactError,
    openArtifacts,
    closeArtifacts,
    previewArtifact,
  };
}
