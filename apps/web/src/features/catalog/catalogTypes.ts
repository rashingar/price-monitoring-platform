import type { Dispatch, SetStateAction } from "react";
import type { MarketplaceFilter, PriceMonitoringSource } from "../../api/commerceTypes";

export type CatalogColumnId =
  | "select"
  | "model"
  | "name"
  | "manufacturer"
  | "family"
  | "category_name"
  | "sub_category"
  | "mpn"
  | "price"
  | "quantity"
  | "bestprice_status"
  | "skroutz_status"
  | "ignored"
  | "warnings"
  | "status"
  | "automation_eligible"
  | "is_atomic_model"
  | "raw_category"
  | "category_levels";

export interface CatalogColumnDefinition {
  id: CatalogColumnId;
  label: string;
  required?: boolean;
}

export interface CatalogLayoutPreferences {
  visibleColumnIds: CatalogColumnId[];
  pageSize: number;
}

export interface CatalogPageState {
  q: string;
  selectedFamily: string;
  selectedCategory: string;
  selectedSubCategory: string;
  manufacturer: string;
  marketplace: MarketplaceFilter;
  source: PriceMonitoringSource;
  showComposite: boolean;
  includeIgnored: boolean;
  sourceUrlsOnly: boolean;
  hasQuantity: boolean;
  page: number;
  pageSize: number;
  visibleColumnIds: CatalogColumnId[];
}

export interface CatalogFilterState {
  q: string;
  selectedFamily: string;
  selectedCategory: string;
  selectedSubCategory: string;
  manufacturer: string;
  marketplace: MarketplaceFilter;
  source: PriceMonitoringSource;
  showComposite: boolean;
  includeIgnored: boolean;
  sourceUrlsOnly: boolean;
  hasQuantity: boolean;
}

export interface CatalogPageControls extends CatalogFilterState {
  page: number;
  pageSize: number;
  visibleColumnIds: Set<CatalogColumnId>;
  setQ: Dispatch<SetStateAction<string>>;
  setSelectedFamily: Dispatch<SetStateAction<string>>;
  setSelectedCategory: Dispatch<SetStateAction<string>>;
  setSelectedSubCategory: Dispatch<SetStateAction<string>>;
  setManufacturer: Dispatch<SetStateAction<string>>;
  setMarketplace: Dispatch<SetStateAction<MarketplaceFilter>>;
  setSource: Dispatch<SetStateAction<PriceMonitoringSource>>;
  setShowComposite: Dispatch<SetStateAction<boolean>>;
  setIncludeIgnored: Dispatch<SetStateAction<boolean>>;
  setSourceUrlsOnly: Dispatch<SetStateAction<boolean>>;
  setHasQuantity: Dispatch<SetStateAction<boolean>>;
  setPage: Dispatch<SetStateAction<number>>;
  setPageSize: Dispatch<SetStateAction<number>>;
  setVisibleColumnIds: Dispatch<SetStateAction<Set<CatalogColumnId>>>;
  visibleColumnIdsArray: CatalogColumnId[];
  resetCatalogState: () => void;
}
