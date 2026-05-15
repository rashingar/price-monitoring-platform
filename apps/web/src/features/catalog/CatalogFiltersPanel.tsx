import type { Dispatch, SetStateAction } from "react";
import type {
  CatalogBrandOption,
  MarketplaceFilter,
  PriceMonitoringSource,
} from "../../api/commerceTypes";
import type { HierarchyOption } from "../../utils/categoryHierarchy";
import { formatHierarchyOptionLabel } from "../../utils/categoryHierarchy";
import { formatOptionCount } from "./catalogFormatters";

export function CatalogFiltersPanel({
  q,
  setQ,
  selectedFamily,
  setSelectedFamily,
  selectedCategory,
  setSelectedCategory,
  selectedSubCategory,
  setSelectedSubCategory,
  manufacturer,
  setManufacturer,
  marketplace,
  setMarketplace,
  source,
  setSource,
  pageSize,
  setPageSize,
  sourceUrlsOnly,
  setSourceUrlsOnly,
  hasQuantity,
  setHasQuantity,
  includeIgnored,
  setIncludeIgnored,
  showComposite,
  setShowComposite,
  familyOptions,
  categoryLevelOptions,
  subCategoryOptions,
  brandOptions,
}: {
  q: string;
  setQ: Dispatch<SetStateAction<string>>;
  selectedFamily: string;
  setSelectedFamily: Dispatch<SetStateAction<string>>;
  selectedCategory: string;
  setSelectedCategory: Dispatch<SetStateAction<string>>;
  selectedSubCategory: string;
  setSelectedSubCategory: Dispatch<SetStateAction<string>>;
  manufacturer: string;
  setManufacturer: Dispatch<SetStateAction<string>>;
  marketplace: MarketplaceFilter;
  setMarketplace: Dispatch<SetStateAction<MarketplaceFilter>>;
  source: PriceMonitoringSource;
  setSource: Dispatch<SetStateAction<PriceMonitoringSource>>;
  pageSize: number;
  setPageSize: Dispatch<SetStateAction<number>>;
  sourceUrlsOnly: boolean;
  setSourceUrlsOnly: Dispatch<SetStateAction<boolean>>;
  hasQuantity: boolean;
  setHasQuantity: Dispatch<SetStateAction<boolean>>;
  includeIgnored: boolean;
  setIncludeIgnored: Dispatch<SetStateAction<boolean>>;
  showComposite: boolean;
  setShowComposite: Dispatch<SetStateAction<boolean>>;
  familyOptions: HierarchyOption[];
  categoryLevelOptions: HierarchyOption[];
  subCategoryOptions: HierarchyOption[];
  brandOptions: CatalogBrandOption[];
}) {
  return (
    <>
      <div className="filter-grid">
        <label>
          Search
          <input
            type="search"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Model, MPN, or name"
          />
        </label>

        <label>
          Family
          <select
            value={selectedFamily}
            onChange={(event) => {
              setSelectedFamily(event.target.value);
              setSelectedCategory("");
              setSelectedSubCategory("");
            }}
          >
            <option value="">All families</option>
            {familyOptions.map((item) => (
              <option key={item.value} value={item.value}>
                {formatHierarchyOptionLabel(item)}
              </option>
            ))}
          </select>
        </label>

        <label>
          Category
          <select
            value={selectedCategory}
            onChange={(event) => {
              setSelectedCategory(event.target.value);
              setSelectedSubCategory("");
            }}
            disabled={!selectedFamily}
          >
            <option value="">All categories</option>
            {categoryLevelOptions.map((item) => (
              <option key={item.value} value={item.value}>
                {formatHierarchyOptionLabel(item)}
              </option>
            ))}
          </select>
        </label>

        <label>
          Sub-Category
          <select
            value={selectedSubCategory}
            onChange={(event) => setSelectedSubCategory(event.target.value)}
            disabled={!selectedFamily || !selectedCategory}
          >
            <option value="">All sub-categories</option>
            {subCategoryOptions.map((item) => (
              <option key={item.value} value={item.value}>
                {formatHierarchyOptionLabel(item)}
              </option>
            ))}
          </select>
        </label>

        <label>
          Manufacturer
          <select value={manufacturer} onChange={(event) => setManufacturer(event.target.value.trim())}>
            <option value="">All manufacturers</option>
            {brandOptions.map((item) => (
              <option key={item.manufacturer} value={item.manufacturer}>
                {item.manufacturer}
                {formatOptionCount(item.count)}
              </option>
            ))}
          </select>
        </label>

        <label>
          Marketplace
          <select
            value={marketplace}
            onChange={(event) => setMarketplace(event.target.value as MarketplaceFilter)}
          >
            <option value="all">All</option>
            <option value="bestprice">BestPrice</option>
            <option value="skroutz">Skroutz</option>
            <option value="both">Both</option>
            <option value="none">None</option>
          </select>
        </label>

        <label title="Marketplace monitoring source. Direct vendor source URL capture uses Vendor Sources.">
          Marketplace source (BestPrice / Skroutz)
          <select
            value={source}
            onChange={(event) => setSource(event.target.value as PriceMonitoringSource)}
          >
            <option value="bestprice">BestPrice</option>
            <option value="skroutz">Skroutz</option>
          </select>
        </label>

        <label>
          Page size
          <select
            value={pageSize}
            onChange={(event) => setPageSize(Number(event.target.value))}
          >
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={200}>200</option>
          </select>
        </label>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={sourceUrlsOnly}
            onChange={(event) => setSourceUrlsOnly(event.target.checked)}
          />
          Source URLs
        </label>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={hasQuantity}
            onChange={(event) => setHasQuantity(event.target.checked)}
          />
          Has quantity
        </label>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={includeIgnored}
            onChange={(event) => setIncludeIgnored(event.target.checked)}
          />
          Include ignored
        </label>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={showComposite}
            onChange={(event) => setShowComposite(event.target.checked)}
          />
          Show composite models
        </label>
      </div>

      <p className="muted">
        Family, Category, and Sub-Category use backend-native hierarchy filters. Raw OpenCart
        category data is available in each product row for debugging.
      </p>
    </>
  );
}
