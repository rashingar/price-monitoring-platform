import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderWithRouter } from "../renderWithRouter";
import { installMockFetch, jsonResponse, type MockRoute } from "../mockFetch";

const stylesCss = readFileSync("src/styles.css", "utf8");

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

const resolvingRows = [
  row(71, 2, "000001", "resolving_source"),
  ...rows.slice(1),
];

const resolvedRows = [
  row(71, 2, "000001", "auto_selected", {
    selected_source: "skroutz",
    selected_url: "https://www.skroutz.gr/s/123/brand-alpha.html",
    confidence: 91,
  }),
  ...rows.slice(1),
];

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolver) => {
    resolve = resolver;
  });
  return { promise, resolve };
}

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
    ...extra,
    { method: "GET", path: "/commerce-api/product-factory-batches", response: { items: [batch] } },
    { method: "GET", path: "/commerce-api/product-factory-batches/7", response: batch },
    { method: "GET", path: "/commerce-api/product-factory-batches/7/rows", response: { items: rows } },
  ];
}

describe("Product Factory Batch Intake", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the route, Product Factory nav entry, upload guidance, and recent batches", async () => {
    installMockFetch(baseRoutes());

    renderWithRouter("/product-factory/batch-intake");

    await expect(screen.findByRole("heading", { name: "Batch Intake" })).resolves.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Batch Intake" })).toBeInTheDocument();
    expect(screen.getByText("Required columns: model, brand, name. Supports comma or semicolon delimiter.")).toBeInTheDocument();
    await expect(screen.findByText("Batch #7")).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Batch #7/ }));
    await screen.findByRole("checkbox", { name: "Skroutz" });
    expect(screen.getByRole("checkbox", { name: "Skroutz" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "BestPrice" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Electronet" })).toBeChecked();
    expect(screen.getByText("Search only selected supported sources.")).toBeInTheDocument();
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
    expect(screen.getByText("Resolved").closest("div")).toHaveTextContent("6 / 7");
    expect(screen.getByText("Auto-selected").closest("div")).toHaveTextContent("1");
    expect(screen.getByRole("cell", { name: "000001" })).toBeInTheDocument();
    expect(mockFetch.requests.some((request) => request.method === "POST" && request.pathname.endsWith("/upload"))).toBe(true);
  });

  it("uses the compact Batch Intake metric card layout", async () => {
    installMockFetch(baseRoutes());
    renderWithRouter("/product-factory/batch-intake");

    fireEvent.click(await screen.findByRole("button", { name: /Batch #7/ }));

    expect((await screen.findByText("Resolved")).closest("dl")).toHaveClass("product-factory-batch-summary-grid");
    expect(stylesCss).toContain("repeat(auto-fit, minmax(140px, 180px))");
  });

  it("opens a recent batch with saved source settings restored", async () => {
    const skroutzBatch = {
      ...batch,
      metadata: { delimiter: ";", selected_source_names: ["skroutz"], selected_source_labels: ["Skroutz"] },
    };
    installMockFetch([
      { method: "GET", path: "/commerce-api/product-factory-batches", response: { items: [skroutzBatch] } },
      { method: "GET", path: "/commerce-api/product-factory-batches/7", response: skroutzBatch },
      { method: "GET", path: "/commerce-api/product-factory-batches/7/rows", response: { items: rows } },
    ]);
    renderWithRouter("/product-factory/batch-intake");

    fireEvent.click(await screen.findByRole("button", { name: /Batch #7/ }));

    await screen.findByRole("checkbox", { name: "Skroutz" });
    expect(screen.getByRole("checkbox", { name: "Skroutz" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "BestPrice" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Electronet" })).not.toBeChecked();
    expect(screen.getByText("Search sources: Skroutz")).toBeInTheDocument();
  });

  it("blocks resolving when no source is selected", async () => {
    const mockFetch = installMockFetch(baseRoutes());
    renderWithRouter("/product-factory/batch-intake");

    fireEvent.click(await screen.findByRole("button", { name: /Batch #7/ }));
    await screen.findByRole("checkbox", { name: "Skroutz" });
    fireEvent.click(screen.getByRole("checkbox", { name: "Skroutz" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "BestPrice" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Electronet" }));
    fireEvent.click(screen.getByRole("button", { name: "Resolve URLs" }));

    expect(screen.getByText("Select at least one search source.")).toBeInTheDocument();
    expect(mockFetch.requests.some((request) => request.pathname.endsWith("/resolve"))).toBe(false);
  });

  it("opens a recent batch, resolves URLs, refreshes rows, and renders all row states", async () => {
    const resolvingBatch = {
      ...batch,
      status: "resolving",
      metadata: { selected_source_names: ["skroutz"], selected_source_labels: ["Skroutz"] },
    };
    const resolvedBatch = { ...resolvingBatch, status: "resolved", pending_count: 0, auto_selected_count: 2 };
    let resolveStarted = false;
    let pollCount = 0;
    const mockFetch = installMockFetch(baseRoutes([
      {
        method: "GET",
        path: "/commerce-api/product-factory-batches/7",
        response: () => (resolveStarted && pollCount > 0 ? resolvedBatch : batch),
      },
      {
        method: "GET",
        path: "/commerce-api/product-factory-batches/7/rows",
        response: () => {
          if (!resolveStarted) {
            return { items: rows };
          }
          pollCount += 1;
          return { items: pollCount === 1 ? resolvingRows : resolvedRows };
        },
      },
      {
        method: "POST",
        path: "/commerce-api/product-factory-batches/7/resolve",
        response: (request) => {
          expect(request.body).toEqual({ source_names: ["skroutz"] });
          resolveStarted = true;
          return { ...resolvingBatch, rows: resolvingRows };
        },
      },
    ]));
    renderWithRouter("/product-factory/batch-intake");

    fireEvent.click(await screen.findByRole("button", { name: /Batch #7/ }));
    await expect(screen.findByRole("cell", { name: "000004" })).resolves.toBeInTheDocument();
    expect(screen.getByText("pending")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "BestPrice" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Electronet" }));
    expect(screen.getByRole("checkbox", { name: "Skroutz" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "BestPrice" })).not.toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Resolve URLs" }));

    await waitFor(() => expect(mockFetch.requests.some((request) => request.pathname === "/commerce-api/product-factory-batches/7/resolve")).toBe(true));
    expect(screen.getByText("Search sources: Skroutz")).toBeInTheDocument();
    expect(screen.getByText("Resolving rows... table refreshes automatically.")).toBeInTheDocument();
    expect(screen.getByText("resolving")).toBeInTheDocument();
    await waitFor(
      () => expect(screen.getAllByRole("cell", { name: "skroutz" }).length).toBeGreaterThan(0),
      { timeout: 3500 },
    );
    for (const label of ["auto selected", "manual", "needs review", "no usable source", "failed", "skipped"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText("source_resolution_error: Brave unavailable")).toBeInTheDocument();
  });

  it("polls rows every 2 seconds while the resolve request is still pending and stops at terminal state", async () => {
    const resolveStart = deferred<unknown>();
    let resolveStarted = false;
    let pollCount = 0;
    const resolvingBatch = {
      ...batch,
      status: "resolving",
      pending_count: 0,
      metadata: { selected_source_names: ["skroutz"], selected_source_labels: ["Skroutz"] },
    };
    const resolvedBatch = { ...resolvingBatch, status: "resolved", auto_selected_count: 2 };
    const liveRows = [
      row(71, 2, "000001", "resolving_source"),
      row(72, 3, "000002", "auto_selected", {
        selected_source: "skroutz",
        selected_url: "https://www.skroutz.gr/s/123/live-alpha.html",
        confidence: 88,
      }),
      ...rows.slice(2),
    ];
    const terminalRows = [
      row(71, 2, "000001", "auto_selected", {
        selected_source: "skroutz",
        selected_url: "https://www.skroutz.gr/s/123/final-alpha.html",
        confidence: 91,
      }),
      ...liveRows.slice(1),
    ];
    const mockFetch = installMockFetch(baseRoutes([
      {
        method: "GET",
        path: "/commerce-api/product-factory-batches/7",
        response: () => {
          if (!resolveStarted) {
            return batch;
          }
          return pollCount >= 1 ? resolvedBatch : resolvingBatch;
        },
      },
      {
        method: "GET",
        path: "/commerce-api/product-factory-batches/7/rows",
        response: () => {
          if (!resolveStarted) {
            return { items: rows };
          }
          pollCount += 1;
          return { items: pollCount >= 2 ? terminalRows : liveRows };
        },
      },
      {
        method: "POST",
        path: "/commerce-api/product-factory-batches/7/resolve",
        response: () => {
          resolveStarted = true;
          return resolveStart.promise;
        },
      },
    ]));
    renderWithRouter("/product-factory/batch-intake");
    fireEvent.click(await screen.findByRole("button", { name: /Batch #7/ }));
    await screen.findByRole("cell", { name: "000004" });
    vi.useFakeTimers();

    const initialRowGetCount = mockFetch.requests.filter((request) => request.method === "GET" && request.pathname.endsWith("/rows")).length;
    fireEvent.click(screen.getByRole("button", { name: "Resolve URLs" }));
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByRole("button", { name: "Resolving..." })).toBeDisabled();
    expect(screen.getByText("Resolving rows... table refreshes automatically.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Resolving..." }));
    expect(mockFetch.requests.filter((request) => request.method === "POST" && request.pathname.endsWith("/resolve")).length).toBe(1);

    await act(async () => {
      vi.advanceTimersByTime(1999);
      await Promise.resolve();
    });
    expect(mockFetch.requests.filter((request) => request.method === "GET" && request.pathname.endsWith("/rows")).length).toBe(initialRowGetCount);

    await act(async () => {
      vi.advanceTimersByTime(1);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(mockFetch.requests.filter((request) => request.method === "GET" && request.pathname.endsWith("/rows")).length).toBe(initialRowGetCount + 1);
    expect(screen.getByText("resolving")).toBeInTheDocument();
    expect(screen.getAllByRole("cell", { name: "skroutz" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("cell", { name: "88" })).toBeInTheDocument();
    expect(screen.getByText("Resolved").closest("div")).toHaveTextContent("6 / 7");
    expect(screen.getAllByRole("cell", { name: /^00000/ }).map((cell) => cell.textContent)).toEqual([
      "000001",
      "000002",
      "000003",
      "000004",
      "000005",
      "000006",
      "000007",
    ]);

    await act(async () => {
      resolveStart.resolve({ ...resolvingBatch, rows: liveRows });
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByRole("button", { name: "Resolve URLs" })).toBeDisabled();

    await act(async () => {
      vi.advanceTimersByTime(2000);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByRole("cell", { name: "91" })).toBeInTheDocument();
    expect(screen.getByText("Resolved").closest("div")).toHaveTextContent("7 / 7");

    const terminalRowGetCount = mockFetch.requests.filter((request) => request.method === "GET" && request.pathname.endsWith("/rows")).length;
    await act(async () => {
      vi.advanceTimersByTime(4000);
      await Promise.resolve();
    });
    expect(mockFetch.requests.filter((request) => request.method === "GET" && request.pathname.endsWith("/rows")).length).toBe(terminalRowGetCount);
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
    fireEvent.click(within(rowEl as HTMLElement).getByRole("button", { name: "Review URL" }));

    await expect(screen.findByRole("heading", { name: "Row 5: 000004" })).resolves.toBeInTheDocument();
    const detailRow = (rowEl as HTMLElement).nextElementSibling as HTMLElement;
    expect(detailRow).toHaveClass("product-factory-batch-detail-row");
    expect(within(detailRow).getByRole("heading", { name: "Row 5: 000004" })).toBeInTheDocument();
    expect(within(detailRow).getByText("Brand Gamma Toaster")).toBeInTheDocument();
    expect(within(detailRow).getByText("Queries used (1)")).toBeInTheDocument();
    expect(within(detailRow).getByRole("button", { name: "Skip row" })).toBeInTheDocument();
    expect(detailRow).not.toHaveTextContent("source_name");
    expect(detailRow).not.toHaveTextContent("result_rank");
    const candidateCard = within(detailRow).getByText("Brand Gamma Toaster").closest("article");
    expect(candidateCard).not.toBeNull();
    fireEvent.click(within(candidateCard as HTMLElement).getByRole("button", { name: "Select" }));

    await waitFor(() => expect(mockFetch.requests.some((request) => request.method === "POST" && request.pathname.endsWith("/select-source"))).toBe(true));
  });

  it("opens one inline review row at a time and shows selected URL details", async () => {
    installMockFetch(baseRoutes());
    renderWithRouter("/product-factory/batch-intake");
    fireEvent.click(await screen.findByRole("button", { name: /Batch #7/ }));

    const needsReviewRow = (await screen.findByRole("cell", { name: "000004" })).closest("tr") as HTMLElement;
    fireEvent.click(within(needsReviewRow).getByRole("button", { name: "Review URL" }));
    expect(needsReviewRow.nextElementSibling).toHaveClass("product-factory-batch-detail-row");
    expect(screen.getByRole("heading", { name: "Row 5: 000004" })).toBeInTheDocument();

    const autoSelectedRow = (await screen.findByRole("cell", { name: "000002" })).closest("tr") as HTMLElement;
    fireEvent.click(within(autoSelectedRow).getByRole("button", { name: "Review URL" }));
    expect(screen.queryByRole("heading", { name: "Row 5: 000004" })).not.toBeInTheDocument();
    const detailRow = autoSelectedRow.nextElementSibling as HTMLElement;
    expect(detailRow).toHaveClass("product-factory-batch-detail-row");
    expect(within(detailRow).getByRole("heading", { name: "Row 3: 000002" })).toBeInTheDocument();
    expect(within(detailRow).getByText("Auto-selected source URL")).toBeInTheDocument();
    expect(within(detailRow).getByText("www.electronet.gr/a/b/c/brand-alpha")).toBeInTheDocument();
    expect(within(detailRow).getByText("electronet")).toBeInTheDocument();
    expect(within(detailRow).getByText("92")).toBeInTheDocument();
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
    fireEvent.click(within(reviewRow).getByRole("button", { name: "Review URL" }));

    const manualInput = await screen.findByLabelText("Manual URL");
    expect(screen.getByRole("button", { name: "Save manual URL" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Skip row" })).toBeInTheDocument();
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
