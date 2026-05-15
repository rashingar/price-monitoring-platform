import type { CatalogProduct } from "../../api/commerceTypes";
import {
  formatMoney,
  formatValue,
  getMarketplaceStatus,
} from "./catalogFormatters";
import {
  getSelectionBlocker,
  getSourceUrlEligibility,
  normalizeModel,
} from "./catalogSelection";
import type { CatalogColumnId } from "./catalogTypes";

export function CatalogProductsTable({
  products,
  selectedModels,
  eligibleVisibleModels,
  allVisibleSelected,
  isColumnVisible,
  isCatalogLocked,
  onToggleAllVisible,
  onToggleModel,
  onOpenSourceUrls,
}: {
  products: CatalogProduct[];
  selectedModels: Set<string>;
  eligibleVisibleModels: string[];
  allVisibleSelected: boolean;
  isColumnVisible: (columnId: CatalogColumnId) => boolean;
  isCatalogLocked: boolean;
  onToggleAllVisible: () => void;
  onToggleModel: (model: string) => void;
  onOpenSourceUrls: (product: CatalogProduct) => void;
}) {
  return (
    <div className="table-wrap catalog-table-wrap">
      <table>
        <thead>
          <tr>
            {isColumnVisible("select") ? (
              <th>
                <input
                  type="checkbox"
                  aria-label="Select all visible eligible products"
                  checked={allVisibleSelected}
                  disabled={eligibleVisibleModels.length === 0}
                  onChange={onToggleAllVisible}
                />
              </th>
            ) : null}
            {isColumnVisible("model") ? <th>Model</th> : null}
            {isColumnVisible("name") ? <th>Name</th> : null}
            {isColumnVisible("manufacturer") ? <th>Manufacturer</th> : null}
            {isColumnVisible("family") ? <th>Family</th> : null}
            {isColumnVisible("category_name") ? <th>Category</th> : null}
            {isColumnVisible("sub_category") ? <th>Sub-Category</th> : null}
            {isColumnVisible("mpn") ? <th>MPN</th> : null}
            {isColumnVisible("price") ? <th>Price</th> : null}
            {isColumnVisible("quantity") ? <th>Qty</th> : null}
            {isColumnVisible("bestprice_status") ? <th>BestPrice</th> : null}
            {isColumnVisible("skroutz_status") ? <th>Skroutz</th> : null}
            {isColumnVisible("ignored") ? <th>Ignored</th> : null}
            {isColumnVisible("status") ? <th>Status</th> : null}
            {isColumnVisible("automation_eligible") ? <th>Automation</th> : null}
            {isColumnVisible("is_atomic_model") ? <th>Atomic</th> : null}
            {isColumnVisible("category_levels") ? <th>Category levels</th> : null}
            {isColumnVisible("raw_category") ? <th>Raw category</th> : null}
            {isColumnVisible("warnings") ? <th>Warnings / eligibility</th> : null}
            <th>Source URLs</th>
          </tr>
        </thead>
        <tbody>
          {products.map((product) => {
            const model = normalizeModel(product.model);
            const selectionBlocker = getSelectionBlocker(product);
            const sourceUrlEligibility = getSourceUrlEligibility(product);
            const isSelected = selectedModels.has(model);
            const warnings = Array.isArray(product.warnings) ? product.warnings : [];
            const rawCategory = product.raw_category ?? product.category ?? "";
            const categoryLevels = Array.isArray(product.category_levels)
              ? product.category_levels.join(" > ")
              : "";

            return (
              <tr key={model}>
                {isColumnVisible("select") ? (
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Select ${model}`}
                      checked={isSelected}
                      disabled={selectionBlocker !== null}
                      onChange={() => onToggleModel(model)}
                    />
                  </td>
                ) : null}
                {isColumnVisible("model") ? <td className="nowrap-cell">{model}</td> : null}
                {isColumnVisible("name") ? <td>{formatValue(product.name)}</td> : null}
                {isColumnVisible("manufacturer") ? <td>{formatValue(product.manufacturer)}</td> : null}
                {isColumnVisible("family") ? <td>{formatValue(product.family)}</td> : null}
                {isColumnVisible("category_name") ? <td>{formatValue(product.category_name)}</td> : null}
                {isColumnVisible("sub_category") ? <td>{formatValue(product.sub_category)}</td> : null}
                {isColumnVisible("mpn") ? <td>{formatValue(product.mpn)}</td> : null}
                {isColumnVisible("price") ? (
                  <td className="nowrap-cell">{formatMoney(product.price)}</td>
                ) : null}
                {isColumnVisible("quantity") ? <td>{formatValue(product.quantity)}</td> : null}
                {isColumnVisible("bestprice_status") ? (
                  <td>
                    <span className="status-badge neutral">
                      {getMarketplaceStatus(product.bestprice_status)}
                    </span>
                  </td>
                ) : null}
                {isColumnVisible("skroutz_status") ? (
                  <td>
                    <span className="status-badge neutral">
                      {getMarketplaceStatus(product.skroutz_status)}
                    </span>
                  </td>
                ) : null}
                {isColumnVisible("ignored") ? <td>{product.ignored ? "yes" : "no"}</td> : null}
                {isColumnVisible("status") ? <td>{formatValue(product.status)}</td> : null}
                {isColumnVisible("automation_eligible") ? (
                  <td>
                    {typeof product.automation_eligible === "boolean"
                      ? product.automation_eligible
                        ? "yes"
                        : "no"
                      : "-"}
                  </td>
                ) : null}
                {isColumnVisible("is_atomic_model") ? (
                  <td>
                    {typeof product.is_atomic_model === "boolean"
                      ? product.is_atomic_model
                        ? "yes"
                        : "no"
                      : "-"}
                  </td>
                ) : null}
                {isColumnVisible("category_levels") ? (
                  <td className="compact-debug-cell">{formatValue(categoryLevels)}</td>
                ) : null}
                {isColumnVisible("raw_category") ? (
                  <td>
                    <details className="raw-category-detail">
                      <summary>Raw</summary>
                      <span>{formatValue(rawCategory)}</span>
                    </details>
                  </td>
                ) : null}
                {isColumnVisible("warnings") ? (
                  <td>
                    <div className="eligibility-cell">
                      <span className={`status-badge ${sourceUrlEligibility.className}`}>
                        {sourceUrlEligibility.label}
                      </span>
                      {selectionBlocker && selectionBlocker !== sourceUrlEligibility.blocker ? (
                        <span className="status-badge queued">{selectionBlocker}</span>
                      ) : null}
                      {warnings.length > 0 ? (
                        <span className="muted">{warnings.join(", ")}</span>
                      ) : null}
                    </div>
                  </td>
                ) : null}
                <td>
                  <button
                    className="button secondary compact-button"
                    type="button"
                    onClick={() => onOpenSourceUrls(product)}
                    disabled={isCatalogLocked}
                    aria-label={`Source URLs for ${model}`}
                  >
                    Source URLs
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
