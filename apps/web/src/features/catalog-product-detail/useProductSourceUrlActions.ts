import { useState } from "react";
import { commerceClient, getCommerceApiErrorMessage } from "../../api/commerceClient";
import type { SourceUrl } from "../../api/commerceTypes";
import { sourceUrlId } from "./ProductSourceUrlLifecycleTable";

type ActionNotice = {
  tone: "success" | "error";
  message: string;
} | null;

type UseProductSourceUrlActionsParams = {
  reload: () => Promise<void>;
};

export function useProductSourceUrlActions({ reload }: UseProductSourceUrlActionsParams) {
  const [pendingSourceUrlId, setPendingSourceUrlId] = useState<string | number | null>(null);
  const [pendingActionLabel, setPendingActionLabel] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<ActionNotice>(null);

  const runSourceUrlAction = async (
    sourceUrl: SourceUrl,
    label: string,
    action: (id: string | number) => Promise<string>,
  ) => {
    const id = sourceUrlId(sourceUrl);
    if (id === null) {
      setActionNotice({ tone: "error", message: "Source URL id is missing; action was not sent." });
      return;
    }

    setPendingSourceUrlId(id);
    setPendingActionLabel(label);
    setActionNotice(null);
    try {
      const message = await action(id);
      setActionNotice({ tone: "success", message });
      await reload();
    } catch (actionError) {
      setActionNotice({ tone: "error", message: getCommerceApiErrorMessage(actionError) });
    } finally {
      setPendingSourceUrlId(null);
      setPendingActionLabel(null);
    }
  };

  const validateSourceUrl = (sourceUrl: SourceUrl) =>
    runSourceUrlAction(sourceUrl, "Validate", async (id) => {
      const result = await commerceClient.validateCatalogSourceUrl(id);
      const status = result.validation.status ?? "complete";
      const message = result.validation.message ?? "Validation completed.";
      return `Validation ${status}: ${message}`;
    });

  const updateSourceUrlStatus = (sourceUrl: SourceUrl, status: string, label: string) =>
    runSourceUrlAction(sourceUrl, label, async (id) => {
      await commerceClient.updateCatalogSourceUrl(id, { status });
      return `Source URL updated: ${label}.`;
    });

  const saveSourceUrlNote = (sourceUrl: SourceUrl, notes: string | null) =>
    runSourceUrlAction(sourceUrl, "Save note", async (id) => {
      await commerceClient.updateCatalogSourceUrl(id, { notes });
      return "Source URL note saved.";
    });

  return {
    pendingSourceUrlId,
    pendingActionLabel,
    actionNotice,
    validateSourceUrl,
    updateSourceUrlStatus,
    saveSourceUrlNote,
  };
}
