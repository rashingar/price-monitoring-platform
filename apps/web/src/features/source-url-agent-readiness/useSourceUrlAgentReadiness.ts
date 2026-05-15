import { useCallback, useEffect, useRef, useState } from "react";
import { commerceClient, getCommerceApiErrorMessage } from "../../api/commerceClient";
import type { SourceUrlAgentReadiness } from "../../api/commerceTypes";

export function useSourceUrlAgentReadiness() {
  const [readiness, setReadiness] = useState<SourceUrlAgentReadiness | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const loadReadiness = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    try {
      const nextReadiness = await commerceClient.getSourceUrlAgentReadiness(signal);
      if (!signal?.aborted) {
        setReadiness(nextReadiness);
        setError(null);
      }
    } catch (loadError) {
      if (!signal?.aborted) {
        setReadiness(null);
        setError(getCommerceApiErrorMessage(loadError));
      }
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadReadiness(controller.signal);
    return () => {
      controller.abort();
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
    };
  }, [loadReadiness]);

  const refreshReadiness = useCallback(() => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadReadiness(controller.signal);
  }, [loadReadiness]);

  return {
    readiness,
    isLoading,
    error,
    refreshReadiness,
  };
}
