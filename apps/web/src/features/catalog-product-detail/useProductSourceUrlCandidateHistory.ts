import { useCallback, useEffect, useState } from "react";
import { commerceClient, getCommerceApiErrorMessage } from "../../api/commerceClient";
import type { ProductSourceUrlCandidateHistoryResponse } from "./catalogProductDetailTypes";

export function useProductSourceUrlCandidateHistory(catalogProductId: string | undefined) {
  const [data, setData] = useState<ProductSourceUrlCandidateHistoryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(
    async (signal?: AbortSignal) => {
      if (!catalogProductId) {
        setData(null);
        setError(null);
        return;
      }

      setIsLoading(true);
      setError(null);
      try {
        const response = await commerceClient.getCatalogProductSourceUrlCandidateHistory(
          catalogProductId,
          signal,
        );
        if (!signal?.aborted) {
          setData(response);
        }
      } catch (loadError) {
        if (signal?.aborted) {
          return;
        }
        setData(null);
        setError(getCommerceApiErrorMessage(loadError));
      } finally {
        if (!signal?.aborted) {
          setIsLoading(false);
        }
      }
    },
    [catalogProductId],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadHistory(controller.signal);
    return () => controller.abort();
  }, [loadHistory]);

  return {
    data,
    isLoading,
    error,
    refresh: () => loadHistory(),
  };
}
