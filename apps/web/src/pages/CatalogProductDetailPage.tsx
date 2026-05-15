import { useParams } from "react-router-dom";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";
import { CatalogProductDetailHeader } from "../features/catalog-product-detail/CatalogProductDetailHeader";
import { CatalogProductIdentityPanel } from "../features/catalog-product-detail/CatalogProductIdentityPanel";
import { ProductSourceUrlCandidateHistoryPanel } from "../features/catalog-product-detail/ProductSourceUrlCandidateHistoryPanel";
import { ProductSourceUrlHistoryPanel } from "../features/catalog-product-detail/ProductSourceUrlHistoryPanel";
import { useCatalogProductDetail } from "../features/catalog-product-detail/useCatalogProductDetail";
import { useProductSourceUrlActions } from "../features/catalog-product-detail/useProductSourceUrlActions";
import { useProductSourceUrlCandidateHistory } from "../features/catalog-product-detail/useProductSourceUrlCandidateHistory";

export function CatalogProductDetailPage() {
  const { catalogProductId } = useParams();
  const { detail, isLoading, error, notFound, reload } = useCatalogProductDetail(catalogProductId);
  const candidateHistory = useProductSourceUrlCandidateHistory(catalogProductId);
  const product = detail?.product ?? null;
  const sourceUrlActions = useProductSourceUrlActions({ reload });

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
      {sourceUrlActions.actionNotice ? (
        <div
          className={`state-block ${sourceUrlActions.actionNotice.tone === "error" ? "error-state" : "success-state"}`}
          role={sourceUrlActions.actionNotice.tone === "error" ? "alert" : "status"}
        >
          {sourceUrlActions.actionNotice.message}
        </div>
      ) : null}
      {!error && product ? (
        <>
          <CatalogProductDetailHeader product={product} />
          <CatalogProductIdentityPanel product={product} />
          <ProductSourceUrlHistoryPanel
            sourceUrls={detail?.source_urls ?? []}
            summary={detail?.source_url_summary ?? {}}
            pendingSourceUrlId={sourceUrlActions.pendingSourceUrlId}
            pendingActionLabel={sourceUrlActions.pendingActionLabel}
            onValidate={sourceUrlActions.validateSourceUrl}
            onUpdateStatus={sourceUrlActions.updateSourceUrlStatus}
            onSaveNote={sourceUrlActions.saveSourceUrlNote}
          />
          <ProductSourceUrlCandidateHistoryPanel
            data={candidateHistory.data}
            isLoading={candidateHistory.isLoading}
            error={candidateHistory.error}
            onRetry={candidateHistory.refresh}
          />
        </>
      ) : null}
    </div>
  );
}
