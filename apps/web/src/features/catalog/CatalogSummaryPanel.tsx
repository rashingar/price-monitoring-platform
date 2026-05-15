import type { CatalogSummary } from "../../api/commerceTypes";
import { ErrorState, LoadingState } from "../../components/layout/StateBlocks";
import { getSummaryNumber } from "./catalogFormatters";
import { CatalogSetupHint } from "./CatalogReadinessBanner";

function SummaryCard({
  label,
  value,
}: {
  label: string;
  value: number | null;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value === null ? "-" : value.toLocaleString()}</dd>
    </div>
  );
}

export function CatalogSummaryPanel({
  summary,
  isLoading,
  error,
  hasReadinessBlock,
  onRefresh,
}: {
  summary: CatalogSummary | null;
  isLoading: boolean;
  error: string | null;
  hasReadinessBlock: boolean;
  onRefresh: () => void;
}) {
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Summary</p>
          <h3>Catalog health</h3>
        </div>
        <button className="button secondary" type="button" onClick={onRefresh}>
          Refresh
        </button>
      </div>
      {isLoading ? <LoadingState label="Loading catalog summary..." /> : null}
      {error ? (
        <>
          <ErrorState message={error} onRetry={onRefresh} />
          <CatalogSetupHint />
        </>
      ) : null}
      {!isLoading && !error && !hasReadinessBlock ? (
        <dl className="summary-grid catalog-summary-grid">
          <SummaryCard label="Total products" value={getSummaryNumber(summary, ["total_products", "total"])} />
          <SummaryCard label="Active products" value={getSummaryNumber(summary, ["active_products", "active"])} />
          <SummaryCard label="Atomic products" value={getSummaryNumber(summary, ["atomic_products", "atomic"])} />
          <SummaryCard
            label="Composite/invalid"
            value={getSummaryNumber(summary, [
              "composite_or_invalid_models",
              "composite_invalid_models",
              "composite_products",
              "non_atomic_products",
            ])}
          />
          <SummaryCard
            label="BestPrice products"
            value={getSummaryNumber(summary, ["bestprice_products", "bestprice"])}
          />
          <SummaryCard
            label="Skroutz products"
            value={getSummaryNumber(summary, ["skroutz_products", "skroutz"])}
          />
          <SummaryCard
            label="Missing MPN"
            value={getSummaryNumber(summary, ["missing_mpn", "missing_mpn_products"])}
          />
        </dl>
      ) : null}
    </section>
  );
}
