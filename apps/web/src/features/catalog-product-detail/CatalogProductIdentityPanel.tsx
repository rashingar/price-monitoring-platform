import type { CatalogProduct } from "./catalogProductDetailTypes";
import { formatDetailValue, formatMoney, statusTone } from "./catalogProductDetailFormatters";

const MARKETPLACE_FIELDS = [
  ["BestPrice", "bestprice_status"],
  ["Skroutz", "skroutz_status"],
] as const;

export function CatalogProductIdentityPanel({ product }: { product: CatalogProduct }) {
  const categoryLevels = Array.isArray(product.category_levels) && product.category_levels.length > 0
    ? product.category_levels.join(" > ")
    : product.raw_category ?? product.category ?? "";
  const coverage = product.source_url_coverage;

  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Identity</p>
          <h3>Catalog fields</h3>
        </div>
      </div>
      <dl className="catalog-product-detail-grid">
        <Field label="Catalog product ID" value={product.catalog_product_id} />
        <Field label="Model" value={product.model} />
        <Field label="MPN" value={product.mpn} />
        <Field label="Name" value={product.name} wide />
        <Field label="Manufacturer" value={product.manufacturer} />
        <Field label="Family" value={product.family} />
        <Field label="Category" value={product.category_name} />
        <Field label="Sub-category" value={product.sub_category} />
        <Field label="Category hierarchy" value={categoryLevels} wide />
        <Field label="Raw category" value={product.raw_category ?? product.category} wide />
        <Field label="Price" value={formatMoney(product.price)} />
        <Field label="Quantity" value={product.quantity} />
        <Field label="Status" value={product.status} />
        <Field label="Atomic model" value={product.is_atomic_model ? "yes" : "no"} />
      </dl>
      <div className="catalog-product-marketplace-row">
        {MARKETPLACE_FIELDS.map(([label, key]) => (
          <span className={`status-badge ${statusTone(product[key])}`} key={key}>
            {label} {formatDetailValue(product[key])}
          </span>
        ))}
        <span className={`status-badge ${coverage?.has_active_source_url ? "success" : "warning"}`}>
          Active URLs {formatDetailValue(coverage?.active_source_url_count ?? 0)}
        </span>
        <span className="status-badge neutral">
          Needs review {formatDetailValue(coverage?.needs_review_source_url_count ?? 0)}
        </span>
      </div>
    </section>
  );
}

function Field({ label, value, wide = false }: { label: string; value: unknown; wide?: boolean }) {
  return (
    <div className={wide ? "wide" : undefined}>
      <dt>{label}</dt>
      <dd>{typeof value === "string" && value !== "-" ? value : formatDetailValue(value)}</dd>
    </div>
  );
}

