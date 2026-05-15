import { useCallback, useEffect, useState } from "react";
import {
  commerceClient,
  getCommerceApiErrorMessage,
} from "../../api/commerceClient";
import type {
  SourceUrlCandidate,
  SourceUrlCandidateListResponse,
} from "../../api/commerceTypes";
import { DEFAULT_LIMIT } from "./sourceUrlCandidateConstants";
import { buildParams, candidateId } from "./sourceUrlCandidateHelpers";
import type { CandidateFilters } from "./sourceUrlCandidateTypes";

const emptyResponse = (offset: number): SourceUrlCandidateListResponse => ({
  items: [],
  total: 0,
  limit: DEFAULT_LIMIT,
  offset,
});

export function useSourceUrlCandidates(filters: CandidateFilters, offset: number) {
  const [response, setResponse] = useState<SourceUrlCandidateListResponse>(() => emptyResponse(0));
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCandidates = useCallback(
    async (signal?: AbortSignal) => {
      setIsLoading(true);
      try {
        const nextResponse = await commerceClient.listSourceUrlCandidates(
          buildParams(filters, offset),
          signal,
        );
        if (signal?.aborted) {
          return;
        }
        setResponse(nextResponse);
        setError(null);
      } catch (loadError) {
        if (!signal?.aborted) {
          setResponse(emptyResponse(offset));
          setError(getCommerceApiErrorMessage(loadError));
        }
      } finally {
        if (!signal?.aborted) {
          setIsLoading(false);
        }
      }
    },
    [filters, offset],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadCandidates(controller.signal);
    return () => controller.abort();
  }, [loadCandidates]);

  const updateCandidateInResponse = useCallback((updated: SourceUrlCandidate) => {
    setResponse((current) => ({
      ...current,
      items: current.items.map((item) => (candidateId(item) === candidateId(updated) ? updated : item)),
    }));
  }, []);

  return {
    response,
    isLoading,
    error,
    refresh: loadCandidates,
    updateCandidateInResponse,
  };
}
