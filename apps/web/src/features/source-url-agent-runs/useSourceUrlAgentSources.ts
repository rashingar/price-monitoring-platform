import { useEffect, useMemo, useState } from "react";
import { commerceClient, getCommerceApiErrorMessage } from "../../api/commerceClient";
import type { VendorSourceCapability } from "../../api/commerceTypes";

export function dedupeCapabilities(sources: VendorSourceCapability[]): VendorSourceCapability[] {
  const seen = new Set<string>();
  return sources.filter((source) => {
    const key = String(source.source_name).toLowerCase();
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

export function useSourceUrlAgentSources() {
  const [vendorSources, setVendorSources] = useState<VendorSourceCapability[]>([]);
  const [isSourcesLoading, setIsSourcesLoading] = useState(true);
  const [sourceError, setSourceError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setIsSourcesLoading(true);
    commerceClient
      .listSourceUrlAgentSources(controller.signal)
      .then((sources) => {
        if (!controller.signal.aborted) {
          setVendorSources(dedupeCapabilities(sources));
          setSourceError(null);
        }
      })
      .catch((loadError) => {
        if (!controller.signal.aborted) {
          setVendorSources([]);
          setSourceError(getCommerceApiErrorMessage(loadError));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsSourcesLoading(false);
        }
      });
    return () => controller.abort();
  }, []);

  const discoverySourceOptions = useMemo(
    () => dedupeCapabilities(vendorSources.filter((source) => source.discovery_enabled)),
    [vendorSources],
  );

  return {
    vendorSources,
    discoverySourceOptions,
    isSourcesLoading,
    sourceError,
  };
}
