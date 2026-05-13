import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { PriceMonitoringAction, PriceMonitoringReviewItem } from "../../api/commerceTypes";
import { ReviewResultsTable } from "../../pages/PriceMonitoringPage";

type TestRowActionState = {
  selected_action: "" | PriceMonitoringAction;
  undercut_amount: string;
  reason: string;
};

const baseItems: PriceMonitoringReviewItem[] = [
  {
    model: "111111",
    name: "First product",
    mpn: "MPN-1",
    current_price: 20,
    competitor_price: 18,
    competitor_store: "Store A",
    competitor_url: "https://competitor.example/products/111111",
    source_url: "https://catalog.example/products/111111",
    price_delta: 2,
    price_delta_percent: 10,
    recommended_action: "match_price",
    selected_action: "",
    undercut_amount: 0.01,
    status: "needs_review",
    warnings: ["price changed"],
    target_price: 18,
    delta_basis: "item_price",
    next_competitor_store: "Store B",
    next_competitor_price: 19,
    captured_listings_count: 2,
    listings_incomplete: true,
    top_listings: [
      {
        rank: 1,
        store: "Store A",
        price: 18,
        shipping_cost: 2,
        landed_price: 20,
        url: "https://competitor.example/products/111111",
      },
    ],
  },
  {
    model: "222222",
    name: "Second product",
    mpn: "MPN-2",
    current_price: 30,
    competitor_price: 28,
    competitor_store: "Store C",
    competitor_url: "https://competitor.example/products/222222",
    price_delta: 2,
    price_delta_percent: 6.67,
    recommended_action: "undercut",
    selected_action: "",
    status: "needs_review",
    warnings: ["new listing"],
  },
];

function TestReviewResultsTable({
  items = baseItems,
}: {
  items?: PriceMonitoringReviewItem[];
}) {
  const [rowActions, setRowActions] = useState<Record<string, TestRowActionState>>({});

  return (
    <ReviewResultsTable
      items={items}
      rowActions={rowActions}
      dbAvailable={true}
      onUpdateRowAction={(model, patch) =>
        setRowActions((current) => ({
          ...current,
          [model]: {
            selected_action: "",
            undercut_amount: "",
            reason: "",
            ...current[model],
            ...patch,
          },
        }))
      }
    />
  );
}

describe("Price monitoring review results selected row", () => {
  it("hides secondary details until Extra is toggled", () => {
    render(<TestReviewResultsTable />);

    expect(screen.queryByText("Status")).not.toBeInTheDocument();
    expect(screen.queryByText("Warnings")).not.toBeInTheDocument();
    expect(screen.queryByText("Recommended action")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Extra" }));

    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("Warnings")).toBeInTheDocument();
    expect(screen.getByText("Recommended action")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Extra" }));

    expect(screen.queryByText("Status")).not.toBeInTheDocument();
    expect(screen.queryByText("Warnings")).not.toBeInTheDocument();
    expect(screen.queryByText("Recommended action")).not.toBeInTheDocument();
  });

  it("keeps the undercut input accessible without rendering the label text", () => {
    render(<TestReviewResultsTable />);

    expect(screen.queryByText("Undercut amount")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Undercut amount")).toBeInTheDocument();
  });

  it("uses the competitor URL for the selected-row store link", () => {
    render(<TestReviewResultsTable />);

    expect(screen.getByRole("link", { name: "Open Store URL" })).toHaveAttribute(
      "href",
      "https://competitor.example/products/111111",
    );
  });

  it("uses the source product URL for the top-level row URL link", () => {
    render(<TestReviewResultsTable />);

    expect(screen.getAllByRole("link", { name: "Open" })[0]).toHaveAttribute(
      "href",
      "https://catalog.example/products/111111",
    );
  });

  it("shows item and landed differences in top listings", () => {
    render(<TestReviewResultsTable />);

    fireEvent.click(screen.getByRole("button", { name: "Top 3 listings" }));

    expect(screen.getByText("Difference")).toBeInTheDocument();
    expect(screen.getByText("L Difference")).toBeInTheDocument();
    const listingRow = screen.getByRole("link", { name: "Open Store" }).closest(".price-review-top-listing-row");
    expect(listingRow).not.toBeNull();
    const listingCells = Array.from((listingRow as HTMLElement).querySelectorAll(":scope > span")).map((cell) =>
      (cell.textContent ?? "").replace(/\s+/g, " ").trim(),
    );
    expect(listingCells[4]).toBe("18,00 € + 2,00 € = 20,00 €");
    expect(listingCells[5]).toBe("2,00 €");
    expect(listingCells[6]).toBe("0,00 €");
    expect(screen.getByRole("link", { name: "Open Store" })).toHaveAttribute(
      "href",
      "https://competitor.example/products/111111",
    );
  });

  it("hides the selected-row competitor link when competitor_url is missing", () => {
    render(
      <TestReviewResultsTable
        items={[
          {
            ...baseItems[0],
            competitor_url: "",
            source_url: "https://catalog.example/products/111111",
          },
        ]}
      />,
    );

    expect(screen.queryByRole("link", { name: "Open Store URL" })).not.toBeInTheDocument();
  });

  it("collapses Extra details when the selected row changes", () => {
    render(<TestReviewResultsTable />);

    fireEvent.click(screen.getByRole("button", { name: "Extra" }));
    expect(screen.getByText("Status")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("listitem")[1]);

    expect(screen.queryByText("Status")).not.toBeInTheDocument();
  });
});
