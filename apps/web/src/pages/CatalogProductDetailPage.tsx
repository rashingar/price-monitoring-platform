import { useState } from "react";
import { useParams } from "react-router-dom";
import { commerceClient, getCommerceApiErrorMessage } from "../api/commerceClient";
import type { SourceUrl } from "../api/commerceTypes";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";
import { CatalogProductDetailHeader } from "../features/catalog-product-detail/CatalogProductDetailHeader";
import { CatalogProductIdentityPanel } from "../features/catalog-product-detail/CatalogProductIdentityPanel";
import { ProductSourceUrlHistoryPanel } from "../features/catalog-product-detail/ProductSourceUrlHistoryPanel";
import { sourceUrlId } from "../features/catalog-product-detail/ProductSourceUrlLifecycleTable";
import { useCatalogProductDetail } from "../features/catalog-product-detail/useCatalogProductDetail";

type ActionNotice = {
  tone: "success" | "error";
  message: string;
} | null;

export function CatalogProductDetailPage() {
  const { catalogProductId } = useParams();
  const { detail, isLoading, error, notFound, reload } = useCatalogProductDetail(catalogProductId);
  const product = detail?.product ?? null;
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

  return (
    <div className="page-stack catalog-product-detail-page">
      {isLoading ? <LoadingState label="Loading catalog product detail..." /> : null}
      {notFound ? (
        <EmptyState
          title="Catalog product not found"
          message="The catalog product ID does not exist in the active catalog."
        />
      ) : null}
      {error && !notFound ? <ErrorState message={error} onRetry={reload} /> : null}
      {actionNotice ? (
        <div
          className={`state-block ${actionNotice.tone === "error" ? "error-state" : "success-state"}`}
          role={actionNotice.tone === "error" ? "alert" : "status"}
        >
          {actionNotice.message}
        </div>
      ) : null}
      {!error && product ? (
        <>
          <CatalogProductDetailHeader product={product} />
          <CatalogProductIdentityPanel product={product} />
          <ProductSourceUrlHistoryPanel
            sourceUrls={detail?.source_urls ?? []}
            summary={detail?.source_url_summary ?? {}}
            pendingSourceUrlId={pendingSourceUrlId}
            pendingActionLabel={pendingActionLabel}
            onValidate={validateSourceUrl}
            onUpdateStatus={updateSourceUrlStatus}
            onSaveNote={saveSourceUrlNote}
          />
        </>
      ) : null}
    </div>
  );
}
