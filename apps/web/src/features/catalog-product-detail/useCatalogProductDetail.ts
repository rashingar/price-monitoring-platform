import { useCallback, useEffect, useState } from "react";
import { CommerceApiError, commerceClient, getCommerceApiErrorMessage } from "../../api/commerceClient";
import type { CatalogProductDetailResponse } from "./catalogProductDetailTypes";

export function useCatalogProductDetail(catalogProductId: string | undefined) {
  const [detail, setDetail] = useState<CatalogProductDetailResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const loadDetail = useCallback(
    async (signal?: AbortSignal) => {
      if (!catalogProductId) {
        setDetail(null);
        setNotFound(true);
        setError(null);
        return;
      }

      setIsLoading(true);
      setError(null);
      setNotFound(false);
      try {
        const response = await commerceClient.getCatalogProductDetail(catalogProductId, signal);
        if (!signal?.aborted) {
          setDetail(response);
        }
      } catch (loadError) {
        if (signal?.aborted) {
          return;
        }
        setDetail(null);
        setNotFound(loadError instanceof CommerceApiError && loadError.status === 404);
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
    void loadDetail(controller.signal);
    return () => controller.abort();
  }, [loadDetail]);

  return {
    detail,
    isLoading,
    error,
    notFound,
    reload: () => loadDetail(),
  };
}
