import { useCallback, useEffect, useRef, useState } from "react";
import { commerceClient, getCommerceApiErrorMessage } from "../../api/commerceClient";
import type { PlatformHealthResponse } from "./platformHealthTypes";

export function usePlatformHealth() {
  const [health, setHealth] = useState<PlatformHealthResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const loadHealth = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    try {
      const nextHealth = await commerceClient.getPlatformHealth(signal);
      if (!signal?.aborted) {
        setHealth(nextHealth);
        setError(null);
      }
    } catch (loadError) {
      if (!signal?.aborted) {
        setHealth(null);
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
    void loadHealth(controller.signal);
    return () => {
      controller.abort();
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
    };
  }, [loadHealth]);

  const refreshHealth = useCallback(() => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadHealth(controller.signal);
  }, [loadHealth]);

  return {
    health,
    isLoading,
    error,
    refreshHealth,
  };
}
