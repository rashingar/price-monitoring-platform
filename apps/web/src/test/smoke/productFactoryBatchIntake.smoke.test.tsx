import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderWithRouter } from "../renderWithRouter";
import { installMockFetch, jsonResponse, type MockRoute } from "../mockFetch";

const batch = {
  id: 7,
  filename: "batch.csv",
  status: "uploaded",
  total_rows: 7,
  pending_count: 1,
  auto_selected_count: 1,
  manually_selected_count: 1,
  needs_review_count: 1,
  no_usable_source_count: 1,
  resolution_failed_count: 1,
  skipped_count: 1,
  metadata: { delimiter: ";" },
  created_at: "2026-05-19T10:00:00Z",
  updated_at: "2026-05-19T10:00:00Z",
};

const rows = [
  row(71, 2, "000001", "pending"),
  row(72, 3, "000002", "auto_selected", {
    selected_source: "electronet",
    selected_url: "https://www.electronet.gr/a/b/c/brand-alpha",
    confidence: 92,
  }),
  row(73, 4, "000003", "manually_selected", {
    selected_source: "skroutz",
    selected_url: "https://www.skroutz.gr/s/123/brand-beta.html",
    confidence: 100,
  }),
  row(74, 5, "000004", "needs_review", {
    candidates: [
      {
        source_name: "bestprice",
        url: "https://www.bestprice.gr/item/123/brand-gamma.html",
        title: "Brand Gamma Toaster",
        confidence: 55,
      },
    ],
    queries: ["Brand Gamma Toaster site:bestprice.gr"],
  }),
  row(75, 6, "000005", "no_usable_source"),
  row(76, 7, "000006", "resolution_failed", {
    error_code: "source_resolution_error",
    error_message: "Brave unavailable",
  }),
  row(77, 8, "000007", "skipped"),
];

function row(
  id: number,
  rowNumber: number,
  model: string,
  status: string,
  overrides: Record<string, unknown> = {},
) {
  return {
    id,
    batch_id: 7,
    row_number: rowNumber,
    model,
    brand: "Brand",
    name: `Product ${model}`,
    queries: [],
    status,
    selected_url: null,
    selected_source: null,
    confidence: null,
    candidates: [],
    error_code: null,
    error_message: null,
    selection_metadata: null,
    created_at: "2026-05-19T10:00:00Z",
    updated_at: "2026-05-19T10:00:00Z",
    ...overrides,
  };
}

function baseRoutes(extra: MockRoute[] = []): MockRoute[] {
  return [
    { method: "GET", path: "/commerce-api/product-factory-batches", response: { items: [batch] } },
    { method: "GET", path: "/commerce-api/product-factory-batches/7", response: batch },
    { method: "GET", path: "/commerce-api/product-factory-batches/7/rows", response: { items: rows } },
    ...extra,
  ];
}

describe("Product Factory Batch Intake", () => {
  it("renders the route, Product Factory nav entry, upload guidance, and recent batches", async () => {
    installMockFetch(baseRoutes());

    renderWithRouter("/product-factory/batch-intake");

    await expect(screen.findByRole("heading", { name: "Batch Intake" })).resolves.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Batch Intake" })).toBeInTheDocument();
    expect(screen.getByText("Required columns: model, brand, name. Supports comma or semicolon delimiter.")).toBeInTheDocument();
    await expect(screen.findByText("Batch #7")).resolves.toBeInTheDocument();
  });

  it("uploads CSV, displays summary metrics, and shows preview/refreshed rows", async () => {
    const mockFetch = installMockFetch(baseRoutes([
      {
        method: "POST",
        path: "/commerce-api/product-factory-batches/upload",
        response: (request) => {
          expect(request.body).toBeInstanceOf(FormData);
          return {
            ...batch,
            preview_rows: rows.slice(0, 2),
          };
        },
      },
    ]));
    renderWithRouter("/product-factory/batch-intake");

    await screen.findByRole("heading", { name: "Batch Intake" });
    fireEvent.change(screen.getByLabelText("CSV file"), {
      target: { files: [new File(["model,brand,name\n000001,Brand,Name"], "batch.csv", { type: "text/csv" })] },
    });
    expect(screen.getByText("Selected file: batch.csv")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));

    await expect(screen.findByText("Total rows")).resolves.toBeInTheDocument();
    expect(screen.getByText("Auto-selected").closest("div")).toHaveTextContent("1");
    expect(screen.getByRole("cell", { name: "000001" })).toBeInTheDocument();
    expect(mockFetch.requests.some((request) => request.method === "POST" && request.pathname.endsWith("/upload"))).toBe(true);
  });

  it("opens a recent batch, resolves URLs, refreshes rows, and renders all row states", async () => {
    const resolvedBatch = { ...batch, status: "resolved", pending_count: 0 };
    const mockFetch = installMockFetch(baseRoutes([
      {
        method: "POST",
        path: "/commerce-api/product-factory-batches/7/resolve",
        response: { ...resolvedBatch, rows },
      },
    ]));
    renderWithRouter("/product-factory/batch-intake");

    fireEvent.click(await screen.findByRole("button", { name: /Batch #7/ }));
    await expect(screen.findByRole("cell", { name: "000004" })).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Resolve URLs" }));

    await waitFor(() => expect(mockFetch.requests.some((request) => request.pathname === "/commerce-api/product-factory-batches/7/resolve")).toBe(true));
    for (const label of ["pending", "auto selected", "manual", "needs review", "no usable source", "failed", "skipped"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText("source_resolution_error: Brave unavailable")).toBeInTheDocument();
  });

  it("shows candidate review details and selects an existing candidate URL", async () => {
    const mockFetch = installMockFetch(baseRoutes([
      {
        method: "POST",
        path: "/commerce-api/product-factory-batches/7/rows/74/select-source",
        response: (request) => {
          expect(request.body).toEqual({ candidate_url: "https://www.bestprice.gr/item/123/brand-gamma.html" });
          return {
            ...rows[3],
            status: "manually_selected",
            selected_source: "bestprice",
            selected_url: "https://www.bestprice.gr/item/123/brand-gamma.html",
            confidence: 55,
          };
        },
      },
    ]));
    renderWithRouter("/product-factory/batch-intake");
    fireEvent.click(await screen.findByRole("button", { name: /Batch #7/ }));

    const rowEl = (await screen.findByRole("cell", { name: "000004" })).closest("tr");
    expect(rowEl).not.toBeNull();
    fireEvent.click(within(rowEl as HTMLElement).getByRole("button", { name: "Review" }));

    await expect(screen.findByRole("heading", { name: "Row 5: 000004" })).resolves.toBeInTheDocument();
    expect(screen.getByText("Brand Gamma Toaster")).toBeInTheDocument();
    expect(screen.getByText("Queries used (1)")).toBeInTheDocument();
    const candidateCard = screen.getByText("Brand Gamma Toaster").closest("article");
    expect(candidateCard).not.toBeNull();
    fireEvent.click(within(candidateCard as HTMLElement).getByRole("button", { name: "Select" }));

    await waitFor(() => expect(mockFetch.requests.some((request) => request.method === "POST" && request.pathname.endsWith("/select-source"))).toBe(true));
  });

  it("saves manual URLs, displays backend validation errors, and skips rows", async () => {
    const mutableRows = [...rows];
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const mockFetch = installMockFetch([
      { method: "GET", path: "/commerce-api/product-factory-batches", response: { items: [batch] } },
      { method: "GET", path: "/commerce-api/product-factory-batches/7", response: batch },
      { method: "GET", path: "/commerce-api/product-factory-batches/7/rows", response: () => ({ items: mutableRows }) },
      {
        method: "POST",
        path: "/commerce-api/product-factory-batches/7/rows/74/select-source",
        response: (request) => {
          if ((request.body as { manual_url?: string }).manual_url === "https://example.com/not-supported") {
            return jsonResponse({ detail: { code: "unsupported_source_url", message: "Manual URL is not supported." } }, 400);
          }
          expect(request.body).toEqual({ manual_url: "https://www.skroutz.gr/s/123/manual.html" });
          mutableRows[3] = {
            ...mutableRows[3],
            status: "manually_selected",
            selected_url: "https://www.skroutz.gr/s/123/manual.html",
            selected_source: "skroutz",
          };
          return mutableRows[3];
        },
      },
      {
        method: "POST",
        path: "/commerce-api/product-factory-batches/7/rows/71/skip",
        response: () => {
          mutableRows[0] = { ...mutableRows[0], status: "skipped" };
          return mutableRows[0];
        },
      },
    ]);
    renderWithRouter("/product-factory/batch-intake");
    fireEvent.click(await screen.findByRole("button", { name: /Batch #7/ }));
    const reviewRow = (await screen.findByRole("cell", { name: "000004" })).closest("tr") as HTMLElement;
    fireEvent.click(within(reviewRow).getByRole("button", { name: "Review" }));

    const manualInput = await screen.findByLabelText("Manual URL");
    fireEvent.change(manualInput, { target: { value: "https://example.com/not-supported" } });
    fireEvent.click(screen.getByRole("button", { name: "Save manual URL" }));
    await expect(screen.findByText(/Manual URL is not supported/)).resolves.toBeInTheDocument();

    fireEvent.change(manualInput, { target: { value: "https://www.skroutz.gr/s/123/manual.html" } });
    fireEvent.click(screen.getByRole("button", { name: "Save manual URL" }));
    await waitFor(() => expect(mockFetch.requests.some((request) => JSON.stringify(request.body).includes("manual.html"))).toBe(true));

    fireEvent.click(within(screen.getByRole("cell", { name: "000001" }).closest("tr") as HTMLElement).getByRole("button", { name: "Skip" }));
    await waitFor(() => expect(mockFetch.requests.some((request) => request.pathname === "/commerce-api/product-factory-batches/7/rows/71/skip")).toBe(true));
    expect(confirmSpy).toHaveBeenCalled();
  });
});
