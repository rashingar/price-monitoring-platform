import { useEffect, useMemo, useRef, useState } from "react";
import { commerceClient, getCommerceApiErrorMessage } from "../../api/commerceClient";
import type {
  PriceMonitoringSelectionResult,
  PriceMonitoringSource,
  SourceUrlAgentRun,
  SourceUrlAgentRunRequest,
} from "../../api/commerceTypes";
import { getSkippedMissingSourceUrlModels } from "./catalogSelection";
import {
  getSourceUrlAgentRunId,
  isActiveSourceUrlAgentRun,
} from "./sourceUrlDiscovery";

export function useSourceUrlDiscoveryRun({
  source,
  previewResult,
  previewForDiscovery,
}: {
  source: PriceMonitoringSource;
  previewResult: PriceMonitoringSelectionResult | null;
  previewForDiscovery: () => Promise<PriceMonitoringSelectionResult | null>;
}) {
  const discoveryPollIntervalRef = useRef<number | null>(null);
  const [discoveryRunError, setDiscoveryRunError] = useState<string | null>(null);
  const [discoveryRun, setDiscoveryRun] = useState<SourceUrlAgentRun | null>(null);
  const [isDiscoveryLaunching, setIsDiscoveryLaunching] = useState(false);

  const stopDiscoveryPolling = () => {
    if (discoveryPollIntervalRef.current !== null) {
      window.clearInterval(discoveryPollIntervalRef.current);
      discoveryPollIntervalRef.current = null;
    }
  };

  const pollDiscoveryRun = (runId: string) => {
    stopDiscoveryPolling();
    const refresh = () => {
      commerceClient
        .getSourceUrlAgentRun(runId)
        .then((nextRun) => {
          setDiscoveryRun(nextRun);
          if (!isActiveSourceUrlAgentRun(nextRun)) {
            stopDiscoveryPolling();
          }
        })
        .catch((error) => {
          setDiscoveryRunError(getCommerceApiErrorMessage(error));
          stopDiscoveryPolling();
        });
    };

    refresh();
    discoveryPollIntervalRef.current = window.setInterval(refresh, 2_500);
  };

  useEffect(
    () => () => {
      stopDiscoveryPolling();
    },
    [],
  );

  const createVendorSourceDiscoveryRun = async () => {
    let result = previewResult;
    if (!result) {
      result = await previewForDiscovery();
      if (!result) {
        return;
      }
    }

    const missingModels = getSkippedMissingSourceUrlModels(result);
    if (missingModels.length === 0) {
      setDiscoveryRunError("No skipped products with missing active source URLs were found in the selection preview.");
      return;
    }

    setDiscoveryRunError(null);
    setIsDiscoveryLaunching(true);
    stopDiscoveryPolling();
    try {
      const request: SourceUrlAgentRunRequest = {
        mode: "catalog",
        source,
        selected_models: missingModels,
        missing_only: true,
        active_only: true,
        dry_run: true,
        apply_high_confidence: false,
        limit: missingModels.length,
        max_products_per_batch: missingModels.length,
        rate_limit_seconds: 2,
      };
      const createdRun = await commerceClient.createSourceUrlAgentRun(request);
      setDiscoveryRun(createdRun);
      const runId = getSourceUrlAgentRunId(createdRun);
      if (runId && isActiveSourceUrlAgentRun(createdRun)) {
        pollDiscoveryRun(runId);
      }
    } catch (error) {
      setDiscoveryRunError(getCommerceApiErrorMessage(error));
    } finally {
      setIsDiscoveryLaunching(false);
    }
  };

  const missingSourceUrlModelCount = useMemo(
    () => getSkippedMissingSourceUrlModels(previewResult).length,
    [previewResult],
  );
  const isDiscoveryPolling = isActiveSourceUrlAgentRun(discoveryRun);
  const discoveryRunId = getSourceUrlAgentRunId(discoveryRun);
  const discoveryReviewLink = discoveryRunId
    ? `/find-source/candidates?${new URLSearchParams({ run_id: discoveryRunId }).toString()}`
    : "/find-source/candidates";

  return {
    discoveryRunError,
    setDiscoveryRunError,
    discoveryRun,
    isDiscoveryLaunching,
    missingSourceUrlModelCount,
    isDiscoveryPolling,
    discoveryRunId,
    discoveryReviewLink,
    createVendorSourceDiscoveryRun,
  };
}
