import type { CatalogProduct, CatalogProductsResponse } from "../../api/commerceTypes";
import { CATALOG_READINESS_REQUIRED_MESSAGE } from "../../api/catalogReadinessGate";
import type { CatalogReadinessBlock } from "../../api/catalogReadinessGate";
import { EmptyState, ErrorState, LoadingState } from "../../components/layout/StateBlocks";
import { CatalogSetupHint } from "./CatalogReadinessBanner";
import { CatalogProductsTable } from "./CatalogProductsTable";
import { CatalogPagination } from "./CatalogPagination";
import type { CatalogColumnId } from "./catalogTypes";

export function CatalogProductsPanel({
  productsResponse,
  productsError,
  productsReadinessBlock,
  productsWarningBlock,
  areProductsLoading,
  selectedModels,
  eligibleVisibleModels,
  allVisibleSelected,
  isColumnVisible,
  isCatalogLocked,
  totalPages,
  onLoadProducts,
  onToggleAllVisible,
  onToggleModel,
  onOpenSourceUrls,
  onPreviousPage,
  onNextPage,
}: {
  productsResponse: CatalogProductsResponse;
  productsError: string | null;
  productsReadinessBlock: CatalogReadinessBlock | null;
  productsWarningBlock: CatalogReadinessBlock | null;
  areProductsLoading: boolean;
  selectedModels: Set<string>;
  eligibleVisibleModels: string[];
  allVisibleSelected: boolean;
  isColumnVisible: (columnId: CatalogColumnId) => boolean;
  isCatalogLocked: boolean;
  totalPages: number;
  onLoadProducts: () => void;
  onToggleAllVisible: () => void;
  onToggleModel: (model: string) => void;
  onOpenSourceUrls: (product: CatalogProduct) => void;
  onPreviousPage: () => void;
  onNextPage: () => void;
}) {
  return (
    <>
      {areProductsLoading ? <LoadingState label="Loading catalog products..." /> : null}
      {productsError ? (
        <>
          <ErrorState message={productsError} onRetry={onLoadProducts} />
          <CatalogSetupHint />
        </>
      ) : null}
      {!areProductsLoading && !productsError && !productsReadinessBlock && productsResponse.items.length === 0 ? (
        <EmptyState
          title={productsWarningBlock ? "Catalog database/import required" : "No products found"}
          message={
            productsWarningBlock
              ? CATALOG_READINESS_REQUIRED_MESSAGE
              : "Try broadening the current filters."
          }
        />
      ) : null}
      {!areProductsLoading && !productsError && productsResponse.items.length > 0 ? (
        <>
          <CatalogProductsTable
            products={productsResponse.items}
            selectedModels={selectedModels}
            eligibleVisibleModels={eligibleVisibleModels}
            allVisibleSelected={allVisibleSelected}
            isColumnVisible={isColumnVisible}
            isCatalogLocked={isCatalogLocked}
            onToggleAllVisible={onToggleAllVisible}
            onToggleModel={onToggleModel}
            onOpenSourceUrls={onOpenSourceUrls}
          />

          <CatalogPagination
            page={productsResponse.page}
            totalPages={totalPages}
            isLoading={areProductsLoading}
            onPrevious={onPreviousPage}
            onNext={onNextPage}
          />
        </>
      ) : null}
    </>
  );
}
