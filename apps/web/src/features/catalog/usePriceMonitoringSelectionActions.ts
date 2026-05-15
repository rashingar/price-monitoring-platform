import { useCallback, useState } from "react";
import { commerceClient, getCommerceApiErrorMessage } from "../../api/commerceClient";
import type { PriceMonitoringSelectionBody, PriceMonitoringSelectionResult } from "../../api/commerceTypes";

export function usePriceMonitoringSelectionActions() {
  const [previewResult, setPreviewResult] = useState<PriceMonitoringSelectionResult | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  const [runResult, setRunResult] = useState<PriceMonitoringSelectionResult | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [isRunLoading, setIsRunLoading] = useState(false);

  const previewSelection = useCallback(async (body: PriceMonitoringSelectionBody) => {
    setIsPreviewLoading(true);
    setPreviewError(null);
    setPreviewResult(null);
    try {
      const result = await commerceClient.previewPriceMonitoringSelection(body);
      setPreviewResult(result);
      return result;
    } catch (error) {
      setPreviewError(getCommerceApiErrorMessage(error));
      return null;
    } finally {
      setIsPreviewLoading(false);
    }
  }, []);

  const previewForDiscovery = useCallback(async (body: PriceMonitoringSelectionBody) => {
    setIsPreviewLoading(true);
    setPreviewError(null);
    try {
      const result = await commerceClient.previewPriceMonitoringSelection(body);
      setPreviewResult(result);
      return result;
    } catch (error) {
      setPreviewError(getCommerceApiErrorMessage(error));
      return null;
    } finally {
      setIsPreviewLoading(false);
    }
  }, []);

  const createRun = useCallback(async (body: PriceMonitoringSelectionBody) => {
    setIsRunLoading(true);
    setRunError(null);
    setRunResult(null);
    try {
      const result = await commerceClient.createPriceMonitoringRun(body);
      setRunResult(result);
    } catch (error) {
      setRunError(getCommerceApiErrorMessage(error));
    } finally {
      setIsRunLoading(false);
    }
  }, []);

  const clearResults = useCallback(() => {
    setPreviewResult(null);
    setRunResult(null);
  }, []);

  return {
    previewResult,
    previewError,
    isPreviewLoading,
    runResult,
    runError,
    isRunLoading,
    previewSelection,
    previewForDiscovery,
    createRun,
    clearResults,
    setPreviewResult,
    setRunResult,
  };
}
