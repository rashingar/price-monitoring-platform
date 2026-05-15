import { useMemo, useState } from "react";
import { commerceClient } from "../api/commerceClient";
import type { CatalogProduct } from "../api/commerceTypes";
import {
  CatalogSourceUrlManager,
  SourceUrlImportPanel,
} from "../components/CatalogSourceUrls";
import { ErrorState } from "../components/layout/StateBlocks";
import { CatalogActionsPanel } from "../features/catalog/CatalogActionsPanel";
import { CatalogColumnControls } from "../features/catalog/CatalogColumnControls";
import { CatalogFiltersPanel } from "../features/catalog/CatalogFiltersPanel";
import { CatalogHeader } from "../features/catalog/CatalogHeader";
import { CatalogProductsPanel } from "../features/catalog/CatalogProductsPanel";
import { CatalogReadinessBanner } from "../features/catalog/CatalogReadinessBanner";
import { CatalogSummaryPanel } from "../features/catalog/CatalogSummaryPanel";
import { readCatalogLayoutPreferences, useCatalogLayoutPreferences } from "../features/catalog/useCatalogLayoutPreferences";
import { useCatalogData } from "../features/catalog/useCatalogData";
import { useCatalogPageState } from "../features/catalog/useCatalogPageState";
import { useCatalogSelection } from "../features/catalog/useCatalogSelection";
import { usePriceMonitoringSelectionActions } from "../features/catalog/usePriceMonitoringSelectionActions";
import { useSourceUrlDiscoveryRun } from "../features/catalog/useSourceUrlDiscoveryRun";

export function CatalogPage() {
  const initialLayoutPreferences = useMemo(() => readCatalogLayoutPreferences(), []);
  const catalogState = useCatalogPageState(initialLayoutPreferences);
  const [sourceUrlProduct, setSourceUrlProduct] = useState<CatalogProduct | null>(null);
  const [sourceUrlRefreshToken, setSourceUrlRefreshToken] = useState(0);

  const catalogData = useCatalogData({
    q: catalogState.q,
    selectedFamily: catalogState.selectedFamily,
    selectedCategory: catalogState.selectedCategory,
    selectedSubCategory: catalogState.selectedSubCategory,
    manufacturer: catalogState.manufacturer,
    marketplace: catalogState.marketplace,
    source: catalogState.source,
    showComposite: catalogState.showComposite,
    includeIgnored: catalogState.includeIgnored,
    sourceUrlsOnly: catalogState.sourceUrlsOnly,
    hasQuantity: catalogState.hasQuantity,
    page: catalogState.page,
    pageSize: catalogState.pageSize,
  });

  const layoutPreferences = useCatalogLayoutPreferences({
    visibleColumnIds: catalogState.visibleColumnIds,
    visibleColumnIdsArray: catalogState.visibleColumnIdsArray,
    setVisibleColumnIds: catalogState.setVisibleColumnIds,
    pageSize: catalogState.pageSize,
    setPageSize: catalogState.setPageSize,
  });

  const priceMonitoring = usePriceMonitoringSelectionActions();
  const selection = useCatalogSelection({
    products: catalogData.productsResponse.items,
    filters: {
      q: catalogState.q,
      selectedFamily: catalogState.selectedFamily,
      selectedCategory: catalogState.selectedCategory,
      selectedSubCategory: catalogState.selectedSubCategory,
      manufacturer: catalogState.manufacturer,
      marketplace: catalogState.marketplace,
      source: catalogState.source,
      showComposite: catalogState.showComposite,
      includeIgnored: catalogState.includeIgnored,
      sourceUrlsOnly: catalogState.sourceUrlsOnly,
      hasQuantity: catalogState.hasQuantity,
    },
    pageSize: catalogState.pageSize,
    setPage: catalogState.setPage,
    onSelectionScopeChange: priceMonitoring.clearResults,
  });

  const sourceUrlDiscovery = useSourceUrlDiscoveryRun({
    source: catalogState.source,
    previewResult: priceMonitoring.previewResult,
    previewForDiscovery: () =>
      priceMonitoring.previewForDiscovery(selection.buildSelectionBody(catalogState.source, true)),
  });

  const resetSavedCatalogState = () => {
    catalogState.resetCatalogState();
    selection.setSelectedModels(new Set());
    setSourceUrlProduct(null);
    priceMonitoring.setPreviewResult(null);
    priceMonitoring.setRunResult(null);
    sourceUrlDiscovery.setDiscoveryRunError(null);
  };

  const refreshCatalog = () => {
    void catalogData.loadSummary();
    void catalogData.loadFilterOptions();
    void catalogData.loadProducts();
  };

  return (
    <div className="page-stack catalog-page">
      <CatalogHeader
        commerceApiBaseUrl={commerceClient.commerceApiBaseUrl}
        onReset={resetSavedCatalogState}
      />

      {catalogData.catalogReadinessBlock ? (
        <CatalogReadinessBanner
          block={catalogData.catalogReadinessBlock}
          onRetry={refreshCatalog}
        />
      ) : null}

      <CatalogSummaryPanel
        summary={catalogData.summary}
        isLoading={catalogData.isSummaryLoading}
        error={catalogData.summaryError}
        hasReadinessBlock={catalogData.summaryReadinessBlock !== null}
        onRefresh={() => void catalogData.loadSummary()}
      />

      <SourceUrlImportPanel
        disabled={catalogData.isCatalogLocked}
        onApplied={() => {
          setSourceUrlRefreshToken((value) => value + 1);
        }}
      />

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Filters</p>
            <h3>Catalog products</h3>
          </div>
          <button className="button secondary" type="button" onClick={() => void catalogData.loadProducts()}>
            Refresh
          </button>
        </div>

        {catalogData.areFiltersLoading ? <p className="muted">Loading categories and brands...</p> : null}
        {catalogData.filtersError ? (
          <ErrorState message={catalogData.filtersError} onRetry={() => void catalogData.loadFilterOptions()} />
        ) : null}

        <CatalogFiltersPanel
          q={catalogState.q}
          setQ={catalogState.setQ}
          selectedFamily={catalogState.selectedFamily}
          setSelectedFamily={catalogState.setSelectedFamily}
          selectedCategory={catalogState.selectedCategory}
          setSelectedCategory={catalogState.setSelectedCategory}
          selectedSubCategory={catalogState.selectedSubCategory}
          setSelectedSubCategory={catalogState.setSelectedSubCategory}
          manufacturer={catalogState.manufacturer}
          setManufacturer={catalogState.setManufacturer}
          marketplace={catalogState.marketplace}
          setMarketplace={catalogState.setMarketplace}
          source={catalogState.source}
          setSource={catalogState.setSource}
          pageSize={catalogState.pageSize}
          setPageSize={catalogState.setPageSize}
          sourceUrlsOnly={catalogState.sourceUrlsOnly}
          setSourceUrlsOnly={catalogState.setSourceUrlsOnly}
          hasQuantity={catalogState.hasQuantity}
          setHasQuantity={catalogState.setHasQuantity}
          includeIgnored={catalogState.includeIgnored}
          setIncludeIgnored={catalogState.setIncludeIgnored}
          showComposite={catalogState.showComposite}
          setShowComposite={catalogState.setShowComposite}
          familyOptions={catalogData.familyOptions}
          categoryLevelOptions={catalogData.categoryLevelOptions}
          subCategoryOptions={catalogData.subCategoryOptions}
          brandOptions={catalogData.brandOptions}
        />

        <CatalogColumnControls
          visibleColumnIds={catalogState.visibleColumnIds}
          onToggleColumn={layoutPreferences.toggleColumn}
          onResetColumns={layoutPreferences.resetColumns}
        />

        <CatalogActionsPanel
          filteredTotal={catalogData.productsResponse.filtered_total}
          selectedCount={selection.selectedModels.size}
          previewResult={priceMonitoring.previewResult}
          previewError={priceMonitoring.previewError}
          isPreviewLoading={priceMonitoring.isPreviewLoading}
          runResult={priceMonitoring.runResult}
          runError={priceMonitoring.runError}
          isRunLoading={priceMonitoring.isRunLoading}
          discoveryRun={sourceUrlDiscovery.discoveryRun}
          discoveryRunError={sourceUrlDiscovery.discoveryRunError}
          discoveryRunId={sourceUrlDiscovery.discoveryRunId}
          discoveryReviewLink={sourceUrlDiscovery.discoveryReviewLink}
          isDiscoveryLaunching={sourceUrlDiscovery.isDiscoveryLaunching}
          isDiscoveryPolling={sourceUrlDiscovery.isDiscoveryPolling}
          missingSourceUrlModelCount={sourceUrlDiscovery.missingSourceUrlModelCount}
          isCatalogLocked={catalogData.isCatalogLocked}
          onPreview={() => void priceMonitoring.previewSelection(selection.buildSelectionBody(catalogState.source, true))}
          onCreateRun={() => void priceMonitoring.createRun(selection.buildSelectionBody(catalogState.source, false))}
          onFindMore={() => void sourceUrlDiscovery.createVendorSourceDiscoveryRun()}
        />

        <CatalogProductsPanel
          productsResponse={catalogData.productsResponse}
          productsError={catalogData.productsError}
          productsReadinessBlock={catalogData.productsReadinessBlock}
          productsWarningBlock={catalogData.productsWarningBlock}
          areProductsLoading={catalogData.areProductsLoading}
          selectedModels={selection.selectedModels}
          eligibleVisibleModels={selection.eligibleVisibleModels}
          allVisibleSelected={selection.allVisibleSelected}
          isColumnVisible={layoutPreferences.isColumnVisible}
          isCatalogLocked={catalogData.isCatalogLocked}
          totalPages={catalogData.totalPages}
          onLoadProducts={() => void catalogData.loadProducts()}
          onToggleAllVisible={selection.toggleAllVisible}
          onToggleModel={selection.toggleModel}
          onOpenSourceUrls={setSourceUrlProduct}
          onPreviousPage={() => catalogState.setPage((currentPage) => Math.max(1, currentPage - 1))}
          onNextPage={() => catalogState.setPage((currentPage) => currentPage + 1)}
        />
      </section>

      <CatalogSourceUrlManager
        product={sourceUrlProduct}
        disabled={catalogData.isCatalogLocked}
        refreshToken={sourceUrlRefreshToken}
        onClose={() => setSourceUrlProduct(null)}
      />
    </div>
  );
}
