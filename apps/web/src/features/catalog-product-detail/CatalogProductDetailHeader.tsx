import { Link } from "react-router-dom";
import type { CatalogProduct } from "./catalogProductDetailTypes";
import { formatDetailValue, statusTone } from "./catalogProductDetailFormatters";

export function CatalogProductDetailHeader({ product }: { product: CatalogProduct }) {
  const title = product.name || product.model || "Catalog product";
  return (
    <header className="page-header catalog-product-detail-header">
      <Link className="text-button" to="/catalog">
        Back to Catalog
      </Link>
      <div className="catalog-product-detail-title-row">
        <div>
          <p className="eyebrow">Catalog product</p>
          <h2>{title}</h2>
        </div>
        <div className="catalog-product-detail-badges">
          <span className="status-badge neutral">ID {formatDetailValue(product.catalog_product_id)}</span>
          <span className={`status-badge ${statusTone(product.status)}`}>
            Status {formatDetailValue(product.status)}
          </span>
          <span className={`status-badge ${product.automation_eligible ? "success" : "neutral"}`}>
            {product.automation_eligible ? "Automation eligible" : "Automation blocked"}
          </span>
          <span className={`status-badge ${product.ignored ? "warning" : "neutral"}`}>
            {product.ignored ? "Ignored" : "Not ignored"}
          </span>
        </div>
      </div>
      <div className="catalog-product-detail-meta">
        <span>Model {formatDetailValue(product.model)}</span>
        <span>Manufacturer {formatDetailValue(product.manufacturer)}</span>
        <span>MPN {formatDetailValue(product.mpn)}</span>
      </div>
    </header>
  );
}

