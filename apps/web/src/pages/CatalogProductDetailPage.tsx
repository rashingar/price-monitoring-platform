import { useParams } from "react-router-dom";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";
import { CatalogProductDetailHeader } from "../features/catalog-product-detail/CatalogProductDetailHeader";
import { CatalogProductIdentityPanel } from "../features/catalog-product-detail/CatalogProductIdentityPanel";
import { ProductSourceUrlHistoryPanel } from "../features/catalog-product-detail/ProductSourceUrlHistoryPanel";
import { useCatalogProductDetail } from "../features/catalog-product-detail/useCatalogProductDetail";

export function CatalogProductDetailPage() {
  const { catalogProductId } = useParams();
  const { detail, isLoading, error, notFound, reload } = useCatalogProductDetail(catalogProductId);
  const product = detail?.product ?? null;

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
      {!isLoading && !error && product ? (
        <>
          <CatalogProductDetailHeader product={product} />
          <CatalogProductIdentityPanel product={product} />
          <ProductSourceUrlHistoryPanel
            sourceUrls={detail?.source_urls ?? []}
            summary={detail?.source_url_summary ?? {}}
          />
        </>
      ) : null}
    </div>
  );
}

