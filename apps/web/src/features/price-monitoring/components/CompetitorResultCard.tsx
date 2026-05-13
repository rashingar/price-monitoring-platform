import type { PriceMonitoringReviewItem, PriceMonitoringTopListing } from "../../../api/commerceTypes";
import { formatMoney, formatNumber, formatValue, parseNumberLike } from "../format";
import { computeTargetPrice, getActionError, getActionState } from "../reviewActions";
import type { RowActionState } from "../types";

function getReviewCompetitorUrl(row: PriceMonitoringReviewItem): string {
  return row.competitor_url || "";
}

function getReviewSourceUrl(row: PriceMonitoringReviewItem): string {
  return row.source_url || "";
}

function getListingsIncompleteText(item: PriceMonitoringReviewItem, topListingsLength: number): string {
  const count = typeof item.captured_listings_count === "number" ? item.captured_listings_count : topListingsLength;
  if (item.listings_incomplete !== true && topListingsLength >= 3) {
    return "";
  }
  if (count <= 0) {
    return "No listings captured";
  }
  if (count === 1) {
    return "Only 1/3 listings captured";
  }
  if (count < 3) {
    return `Only ${count}/3 listings captured`;
  }
  return "";
}

function formatShippingCost(value: unknown): string {
  const parsed = parseNumberLike(value);
  return parsed === null ? "shipping unknown" : formatMoney(parsed);
}

function getListingLandedComparisonPrice(listing: PriceMonitoringTopListing): number | null {
  const landedPrice = parseNumberLike(listing.landed_price);
  if (landedPrice !== null) {
    return landedPrice;
  }

  const itemPrice = parseNumberLike(listing.price);
  const shippingCost = parseNumberLike(listing.shipping_cost);
  if (itemPrice === null || shippingCost === null) {
    return null;
  }

  return itemPrice + shippingCost;
}

function formatLandedPrice(listing: PriceMonitoringTopListing): string {
  const itemPrice = parseNumberLike(listing.price);
  const shippingCost = parseNumberLike(listing.shipping_cost);
  const landedPrice = parseNumberLike(listing.landed_price);
  if (landedPrice === null) {
    return "-";
  }
  if (itemPrice !== null && shippingCost !== null) {
    return `${formatMoney(itemPrice)} + ${formatMoney(shippingCost)} = ${formatMoney(landedPrice)}`;
  }
  return formatMoney(landedPrice);
}

function TopListingsPanel({
  currentPrice,
  listings,
}: {
  currentPrice: unknown;
  listings: NonNullable<PriceMonitoringReviewItem["top_listings"]>;
}) {
  const current = parseNumberLike(currentPrice);

  if (listings.length === 0) {
    return <p className="muted price-review-empty-top-listings">No listings captured.</p>;
  }

  return (
    <div className="price-review-top-listings">
      <div className="price-review-top-listings-header">
        <span>Rank</span>
        <span>Store</span>
        <span>Item price</span>
        <span>Shipping</span>
        <span>Landed price</span>
        <span>Difference</span>
        <span>L Difference</span>
        <span>URL</span>
      </div>
      {listings.map((listing, index) => {
        const listingPrice = parseNumberLike(listing.price);
        const difference = current !== null && listingPrice !== null ? current - listingPrice : null;
        const listingLandedComparisonPrice = getListingLandedComparisonPrice(listing);
        const landedDifference =
          current !== null && listingLandedComparisonPrice !== null
            ? current - listingLandedComparisonPrice
            : null;
        return (
          <div className="price-review-top-listing-row" key={`${listing.rank ?? index}-${listing.store ?? ""}`}>
            <span>{formatValue(listing.rank ?? index + 1)}</span>
            <span>{formatValue(listing.store)}</span>
            <span>{formatMoney(listing.price)}</span>
            <span>{formatShippingCost(listing.shipping_cost)}</span>
            <span>{formatLandedPrice(listing)}</span>
            <span>{formatMoney(difference)}</span>
            <span>{formatMoney(landedDifference)}</span>
            <span>
              {listing.url ? (
                <a href={listing.url} target="_blank" rel="noreferrer">
                  Open Store
                </a>
              ) : (
                "-"
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function CompetitorResultCard({
  item,
  isSelected,
  rowActions,
  dbAvailable,
  showTopListings,
  showExtraDetails,
  onSelect,
  onUpdateRowAction,
  onClearRowAction,
  onToggleTopListings,
  onToggleExtraDetails,
}: {
  item: PriceMonitoringReviewItem;
  isSelected: boolean;
  rowActions: Record<string, RowActionState>;
  dbAvailable: boolean;
  showTopListings: boolean;
  showExtraDetails: boolean;
  onSelect: (model: string) => void;
  onUpdateRowAction: (model: string, patch: Partial<RowActionState>) => void;
  onClearRowAction: (model: string) => void;
  onToggleTopListings: (model: string) => void;
  onToggleExtraDetails: (model: string) => void;
}) {
  const state = getActionState(item, rowActions);
  const targetPrice = computeTargetPrice(item, state);
  const actionError = getActionError(item, state);
  const topListings = item.top_listings ?? [];
  const listingWarning = getListingsIncompleteText(item, topListings.length);
  const competitorUrl = getReviewCompetitorUrl(item);
  const sourceUrl = getReviewSourceUrl(item);

  return (
    <section
      className={`price-review-row${isSelected ? " selected" : ""}`}
      role="listitem"
      onClick={() => onSelect(item.model)}
    >
      <div
        className="price-review-row-button"
        role="button"
        tabIndex={0}
        onClick={() => onSelect(item.model)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onSelect(item.model);
          }
        }}
      >
        <div className="price-review-identity-row">
          <span>
            <strong>Model</strong>
            {formatValue(item.model)}
          </span>
          <span>
            <strong>Name</strong>
            {formatValue(item.name)}
          </span>
          <span>
            <strong>MPN</strong>
            {formatValue(item.mpn)}
          </span>
        </div>
        <div className="price-review-operational-row">
          <span>
            <strong>Current price</strong>
            {formatMoney(item.current_price)}
          </span>
          <span>
            <strong>Competitor price</strong>
            {formatMoney(item.competitor_price)}
          </span>
          <span>
            <strong>Store</strong>
            {formatValue(item.competitor_store)}
            {listingWarning ? <small className="price-review-listings-inline-note">{listingWarning}</small> : null}
          </span>
          <span>
            <strong>URL</strong>
            {sourceUrl ? (
              <a href={sourceUrl} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>
                Open
              </a>
            ) : (
              "-"
            )}
          </span>
          <span>
            <strong>Delta vs current item price</strong>
            {formatNumber(item.price_delta)}
          </span>
          <span>
            <strong>Delta %</strong>
            {formatNumber(item.price_delta_percent)}
          </span>
        </div>
      </div>

      {isSelected ? (
        <div className="price-review-inline-panel" onClick={(event) => event.stopPropagation()}>
          <div className="button-row price-review-actions">
            <button
              className="button secondary"
              type="button"
              disabled={!dbAvailable}
              onClick={() => onUpdateRowAction(item.model, { selected_action: "match_price" })}
            >
              Match price
            </button>
            <button
              className="button secondary"
              type="button"
              disabled={!dbAvailable}
              onClick={() =>
                onUpdateRowAction(item.model, {
                  selected_action: "undercut",
                  undercut_amount: state.undercut_amount || "0.01",
                })
              }
            >
              Undercut
            </button>
            <label className="inline-field price-review-undercut-field">
              <input
                aria-label="Undercut amount"
                type="number"
                min="0"
                step="0.01"
                value={state.undercut_amount}
                placeholder="0.01"
                disabled={!dbAvailable}
                onChange={(event) => onUpdateRowAction(item.model, { undercut_amount: event.target.value })}
              />
            </label>
            <button
              className="button secondary"
              type="button"
              disabled={!dbAvailable}
              onClick={() => onUpdateRowAction(item.model, { selected_action: "ignore" })}
            >
              Ignore
            </button>
            <button
              className="button secondary"
              type="button"
              disabled={!dbAvailable}
              onClick={() => onClearRowAction(item.model)}
            >
              Clear row action
            </button>
            {competitorUrl ? (
              <a className="button secondary" href={competitorUrl} target="_blank" rel="noreferrer">
                Open competitor URL
              </a>
            ) : null}
            <button
              className="button secondary"
              type="button"
              aria-expanded={showTopListings}
              onClick={() => onToggleTopListings(item.model)}
            >
              Top 3 listings
            </button>
            <button
              className="button secondary"
              type="button"
              aria-expanded={showExtraDetails}
              onClick={() => onToggleExtraDetails(item.model)}
            >
              Extra
            </button>
          </div>

          {actionError ? <small className="field-error">{actionError}</small> : null}

          {showExtraDetails ? (
            <>
              <dl className="price-review-detail-grid">
                <div>
                  <dt>Status</dt>
                  <dd>{formatValue(item.status)}</dd>
                </div>
                <div>
                  <dt>Warnings</dt>
                  <dd>{item.warnings?.join(", ") || "-"}</dd>
                </div>
                <div>
                  <dt>Recommended action</dt>
                  <dd>{formatValue(item.recommended_action)}</dd>
                </div>
                <div>
                  <dt>Selected action</dt>
                  <dd>{formatValue(state.selected_action || item.selected_action)}</dd>
                </div>
                <div>
                  <dt>Target price</dt>
                  <dd>{formatMoney(targetPrice)}</dd>
                </div>
                <div>
                  <dt>Delta basis</dt>
                  <dd>{formatValue(item.delta_basis)}</dd>
                </div>
                <div>
                  <dt>Next store</dt>
                  <dd>{formatValue(item.next_competitor_store)}</dd>
                </div>
                <div>
                  <dt>Next price</dt>
                  <dd>{formatMoney(item.next_competitor_price)}</dd>
                </div>
                <div>
                  <dt>Captured listings</dt>
                  <dd>{formatValue(item.captured_listings_count ?? topListings.length)}</dd>
                </div>
              </dl>

              {listingWarning ? (
                <p className="muted price-review-listings-detail-note">
                  Top listings are incomplete. Capture returned only {item.captured_listings_count ?? topListings.length} marketplace listing
                  {(item.captured_listings_count ?? topListings.length) === 1 ? "" : "s"}.
                </p>
              ) : null}
            </>
          ) : null}

          {state.selected_action === "ignore" ? (
            <label className="inline-field wide price-review-reason-field">
              <span>Ignore reason</span>
              <input
                value={state.reason}
                disabled={!dbAvailable}
                onChange={(event) => onUpdateRowAction(item.model, { reason: event.target.value })}
                placeholder="Optional"
              />
            </label>
          ) : null}

          {showTopListings ? (
            <TopListingsPanel currentPrice={item.current_price} listings={topListings} />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
