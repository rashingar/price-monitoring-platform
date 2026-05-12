import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  PRICE_MONITORING_STATE_KEY,
  initialPriceMonitoringWorkflowState,
} from "../../api/priceMonitoringUtils";
import {
  catalogDbImportRequiredFixtureRoutes,
  catalogProductsEmptyImportWarning,
  commerceDbRequiredFixtureRoutes,
  commerceFixtureRoutes,
  dbStatusUnavailable,
  priceMonitoringMissingSourceUrlError,
  priceMonitoringMissingSourceUrlSelectionResult,
} from "../fixtures/commerceApi";
import {
  productFactoryFilterRevision,
  productFactoryFixtureRoutes,
  productFactoryHealth,
  productFactorySettings,
} from "../fixtures/productFactoryApi";
import { installMockFetch, type MockRoute } from "../mockFetch";
import { SOURCE_URL_CANDIDATE_REVIEW_LAYOUT_STORAGE_KEY } from "../../pages/SourceUrlCandidatesPage";
import { renderWithRouter } from "../renderWithRouter";

const allRoutes = [...productFactoryFixtureRoutes, ...commerceFixtureRoutes];

function makeGenericWorkflowRoutes(model: string, authoring: unknown): MockRoute[] {
  return [
    { method: "GET", path: "/api/health", response: productFactoryHealth },
    { method: "GET", path: "/api/settings", response: productFactorySettings },
    { method: "GET", path: /^\/api\/jobs\/by-model\/[^/]+$/, response: { jobs: [] } },
    { method: "GET", path: `/api/authoring/${model}`, response: authoring },
  ];
}

function genericAuthoringStatus(overrides: Record<string, unknown> = {}) {
  return {
    model: "GENERIC-001",
    llm_dir: "runs/GENERIC-001/llm",
    intro_text: {
      status: "valid",
      output_path: "runs/GENERIC-001/intro.txt",
      word_count: 96,
      min_words: 80,
      max_words: 140,
      max_attempts: 3,
      errors: [],
    },
    seo_meta: {
      status: "valid",
      output_path: "runs/GENERIC-001/seo.json",
      errors: [],
    },
    ready_for_render: true,
    render_block_reasons: [],
    warnings: [],
    ...overrides,
  };
}

describe("platform mocked page smoke tests", () => {
  it("renders the app shell and main platform navigation", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/");

    expect(screen.getByRole("heading", { name: "Product Factory Platform" })).toBeInTheDocument();
    const primaryNav = screen.getByRole("navigation", { name: "Primary navigation" });
    expect(within(primaryNav).getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(within(primaryNav).getByRole("link", { name: "Catalog" })).toBeInTheDocument();
    expect(within(primaryNav).getByRole("link", { name: "Price Monitoring" })).toBeInTheDocument();
    expect(within(primaryNav).getByRole("link", { name: "Find Source" })).toBeInTheDocument();
    expect(within(primaryNav).queryByRole("link", { name: "CSV/Bridge" })).not.toBeInTheDocument();
    expect(within(primaryNav).queryByRole("link", { name: "Price Alerts" })).not.toBeInTheDocument();
    expect(within(primaryNav).getByRole("link", { name: "Vendor Sources" })).toBeInTheDocument();
    expect(within(primaryNav).getByRole("link", { name: "Product Factory" })).toBeInTheDocument();
    await expect(screen.findByRole("heading", { name: "Local backend control surface" })).resolves.toBeInTheDocument();
  });

  it("renders Dashboard with mocked health and diagnostics responses", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/");

    await expect(screen.findByRole("heading", { name: "ok" })).resolves.toBeInTheDocument();
    await expect(screen.findByText(/Product Factory API health endpoint responded/)).resolves.toBeInTheDocument();
    await expect(screen.findByText(/Commerce API health endpoint responded/)).resolves.toBeInTheDocument();
  });

  it("renders Catalog summary filters and product rows", async () => {
    const mockFetch = installMockFetch(allRoutes);

    renderWithRouter("/catalog");

    await expect(screen.findByRole("heading", { name: "Commerce catalog" })).resolves.toBeInTheDocument();
    expect(screen.getByText("Composite/invalid").closest("div")).toHaveTextContent("1");
    await expect(screen.findByText("005606")).resolves.toBeInTheDocument();
    await expect(screen.findByText("Midea Αφυγραντήρας 20L")).resolves.toBeInTheDocument();
    expect(screen.getByText("Αφυγραντήρες")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Source URLs for 005606" })).toBeInTheDocument();
    await expect(screen.findByText("Source URL Import")).resolves.toBeInTheDocument();
    await expect(screen.findByText(/Coverage:/)).resolves.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Preview import" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Include ignored")).toBeInTheDocument();
    expect(screen.getByLabelText("Show composite models")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Source URLs"));
    await waitFor(() =>
      expect(
        mockFetch.requests.some(
          (request) =>
            request.pathname === "/commerce-api/catalog/products" &&
            request.searchParams.get("has_source_url") === "true",
        ),
      ).toBe(true),
    );
  });

  it("expands source URL import and keeps apply guarded by preview and confirmation", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/catalog");

    await expect(screen.findByText("Source URL Import")).resolves.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Preview import" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Expand" }));

    await expect(screen.findByText("Total URLs")).resolves.toBeInTheDocument();
    const applyButton = screen.getByRole("button", { name: "Apply import" });
    expect(applyButton).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Preview import" }));

    await expect(screen.findByText("Dry-run report")).resolves.toBeInTheDocument();
    await expect(screen.findByText("Ambiguous identity for artifact row model MIXED-001.")).resolves.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply import" })).toBeDisabled();

    fireEvent.click(screen.getByLabelText("I reviewed the dry-run report"));

    await waitFor(() => expect(screen.getByRole("button", { name: "Apply import" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Apply import" }));

    await expect(screen.findByText("Applied import report")).resolves.toBeInTheDocument();
    expect(screen.getAllByText("Imported").length).toBeGreaterThan(0);
  });

  it("opens and closes the Catalog source URL drawer with product context", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/catalog");

    fireEvent.click(await screen.findByRole("button", { name: "Source URLs for 005606" }));

    let drawer = await screen.findByRole("dialog", { name: "Source URLs" });
    expect(drawer).toBeInTheDocument();
    expect(within(drawer).getByText("005606")).toBeInTheDocument();
    expect(within(drawer).getByText("Midea Αφυγραντήρας 20L")).toBeInTheDocument();
    expect(within(drawer).getByText("Midea")).toBeInTheDocument();
    expect(within(drawer).getByText("MD-20L")).toBeInTheDocument();
    expect(within(drawer).getByText("1")).toBeInTheDocument();
    await expect(within(drawer).findByText("https://www.skroutz.gr/s/123/midea-md-20l.html")).resolves.toBeInTheDocument();
    expect(within(drawer).getByText("Product source")).toBeInTheDocument();
    expect(within(drawer).getByText(/scheduled-test/)).toBeInTheDocument();
    expect(within(drawer).getByText(/source-captures\/9001\/full-snapshot\.json/)).toBeInTheDocument();
    expect(within(drawer).getByText("electronet")).toBeInTheDocument();
    expect(within(drawer).getByText("public")).toBeInTheDocument();
    expect(within(drawer).getByText("plaisio")).toBeInTheDocument();
    expect(within(drawer).getByText("kotsovolos")).toBeInTheDocument();

    fireEvent.click(within(drawer).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Source URLs" })).not.toBeInTheDocument());
  });

  it("renders Find Source table", async () => {
    localStorage.removeItem(SOURCE_URL_CANDIDATE_REVIEW_LAYOUT_STORAGE_KEY);
    const mockFetch = installMockFetch(allRoutes);

    renderWithRouter("/find-source/candidates");

    await expect(screen.findByRole("heading", { name: "Find Source" })).resolves.toBeInTheDocument();
    await expect(screen.findByText("Midea MD-20L Αφυγραντήρας 20L")).resolves.toBeInTheDocument();
    expect(screen.getByText("Table settings")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Status" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Confidence" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Model" })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "MPN" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Manufacturer" })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Brand" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Source" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Candidate price" })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Source price" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Own price" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Candidate title" })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Source title" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("Table settings"));
    const settingsPanel = screen.getByText("Table settings").closest("details") as HTMLElement;
    expect(within(settingsPanel).getByLabelText("Status")).toBeChecked();
    expect(within(settingsPanel).getByLabelText("Confidence")).toBeChecked();
    expect(within(settingsPanel).getByLabelText("Model")).not.toBeChecked();
    expect(within(settingsPanel).getByLabelText("Brand")).toBeChecked();
    expect(within(settingsPanel).getByLabelText("Source")).toBeChecked();
    const widthInputs = within(settingsPanel).getAllByLabelText("Width") as HTMLInputElement[];
    expect(widthInputs.map((input) => input.value)).toEqual(["56", "32", "28", "48", "32", "32", "32", "32", "260"]);
    expect(widthInputs.every((input) => input.getAttribute("min") === "28")).toBe(true);
    fireEvent.click(within(settingsPanel).getByRole("button", { name: "Move Status down" }));
    expect((within(settingsPanel).getAllByLabelText("Width") as HTMLInputElement[]).map((input) => input.value)).toEqual([
      "32",
      "56",
      "28",
      "48",
      "32",
      "32",
      "32",
      "32",
      "260",
    ]);
    expect(screen.getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
      "Confidence",
      "Status",
      "MPN",
      "Brand",
      "Source",
      "Source price",
      "Own price",
      "Source title",
    ]);
    fireEvent.click(within(settingsPanel).getByRole("button", { name: "Move Status up" }));
    fireEvent.click(within(settingsPanel).getByRole("button", { name: "Save layout" }));
    await waitFor(() =>
      expect(localStorage.getItem(SOURCE_URL_CANDIDATE_REVIEW_LAYOUT_STORAGE_KEY)).toContain('"columns"'),
    );
    expect(mockFetch.requests.map((request) => request.pathname)).not.toContain(
      "/commerce-api/source-url-agent/candidates/review-layout",
    );
    expect(mockFetch.requests.map((request) => request.pathname)).not.toContain(
      "/commerce-api/source-url-agent/candidates/review-layout/reset",
    );
    expect(screen.getByText("0.9823")).toBeInTheDocument();
    expect(screen.getAllByText("needs review").length).toBeGreaterThan(0);
    expect(screen.getByText("Midea MD-20L Electronet")).toBeInTheDocument();
    expect(screen.getByText("Midea MD-20L Public")).toBeInTheDocument();
    expect(screen.getByText("Midea MD-20L Plaisio")).toBeInTheDocument();
    expect(screen.getByText("Midea MD-20L Kotsovolos")).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Actions" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Midea MD-20L Αφυγραντήρας 20L"));

    const reviewPanel = await screen.findByRole("region", { name: "Find Source candidate 501 review" });
    expect(reviewPanel).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(within(reviewPanel).getByRole("link", { name: "Open candidate URL" })).toBeInTheDocument();
    expect(within(reviewPanel).getByRole("button", { name: "Accept" })).toBeInTheDocument();
    expect(within(reviewPanel).getByRole("button", { name: "Reject" })).toBeInTheDocument();
    expect(within(reviewPanel).getByRole("button", { name: "Replace URL" })).toBeInTheDocument();
    expect(within(reviewPanel).getByRole("button", { name: "Debug" })).toBeInTheDocument();
    expect(within(reviewPanel).queryByRole("button", { name: /not found/i })).not.toBeInTheDocument();
    expect(within(reviewPanel).queryByRole("button", { name: /needs manual review/i })).not.toBeInTheDocument();
    expect(within(reviewPanel).queryByText("Catalog product")).not.toBeInTheDocument();
    expect(within(reviewPanel).queryByText("Candidate source")).not.toBeInTheDocument();

    fireEvent.click(within(settingsPanel).getByRole("button", { name: "Reset layout" }));
    await waitFor(() => expect(localStorage.getItem(SOURCE_URL_CANDIDATE_REVIEW_LAYOUT_STORAGE_KEY)).toBeNull());
  });

  it("runs Skroutz browser diagnostics from candidate review and renders endpoint details", async () => {
    const mockFetch = installMockFetch(allRoutes);

    renderWithRouter("/find-source/candidates");

    fireEvent.click(await screen.findByText("Midea MD-20L Αφυγραντήρας 20L"));

    const runButton = await screen.findByRole("button", { name: "Run browser diagnostic" });
    expect(runButton).toBeEnabled();
    fireEvent.click(runButton);

    await expect(screen.findByText("https://www.skroutz.gr/s/123/filter_products.json")).resolves.toBeInTheDocument();
    expect(screen.getByText("Blocked or challenge-like response detected.")).toBeInTheDocument();
    expect(screen.getAllByText("yes").length).toBeGreaterThan(0);
    expect(screen.getAllByText("no").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "View captured endpoint details" }));
    await expect(screen.findByText("PRIMARY_CANDIDATE_PRODUCT_OFFERS")).resolves.toBeInTheDocument();
    expect(screen.getByText("BLOCKED_OR_CHALLENGE")).toBeInTheDocument();
    expect(screen.getByText("product_cards, pagination")).toBeInTheDocument();
    expect(
      mockFetch.requests.some(
        (request) =>
          request.method === "POST" &&
          request.pathname === "/commerce-api/vendor-sources/source-urls/101/diagnostics/skroutz-network",
      ),
    ).toBe(true);
  });

  it("does not show Skroutz browser diagnostics for non-Skroutz candidates", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/find-source/candidates");

    await expect(screen.findByText("Keyboard mouse bundle")).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByText("Keyboard mouse bundle"));

    await expect(screen.findByText("Open candidate URL")).resolves.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run browser diagnostic" })).not.toBeInTheDocument();
  });

  it("shows Skroutz diagnostic running state", async () => {
    installMockFetch([
      {
        method: "POST",
        path: "/commerce-api/vendor-sources/source-urls/101/diagnostics/skroutz-network",
        response: async () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  source_url_id: 101,
                  vendor_slug: "skroutz",
                  status: "success",
                  captured_response_count: 0,
                  observed_filter_products_url: false,
                  observed_shops_details_url: false,
                  classifications_summary: {},
                }),
              50,
            ),
          ),
      },
      ...allRoutes,
    ]);

    renderWithRouter("/find-source/candidates");

    fireEvent.click(await screen.findByText("Midea MD-20L Αφυγραντήρας 20L"));
    fireEvent.click(await screen.findByRole("button", { name: "Run browser diagnostic" }));

    expect(await screen.findByRole("button", { name: "Running..." })).toBeDisabled();
  });

  it("renders Find Source runs with backend source capabilities and candidate review links", async () => {
    const mockFetch = installMockFetch(allRoutes);

    renderWithRouter("/find-source/runs");

    await expect(screen.findByRole("heading", { name: "Find Source" })).resolves.toBeInTheDocument();
    const findSourceNav = screen.getByRole("navigation", { name: "Find Source navigation" });
    expect(findSourceNav).toBeInTheDocument();
    expect(within(findSourceNav).getByRole("link", { name: "Runs" })).toHaveAttribute(
      "href",
      "/find-source/runs",
    );
    expect(within(findSourceNav).getByRole("link", { name: "Candidates" })).toHaveAttribute(
      "href",
      "/find-source/candidates",
    );
    expect(screen.getByLabelText("Mode")).toHaveValue("catalog");
    expect(screen.getByLabelText("Source filter")).toHaveValue("all");
    await expect(screen.findByRole("option", { name: "electronet" })).resolves.toBeInTheDocument();
    expect(screen.getByRole("option", { name: "skroutz" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "bestprice" })).toBeInTheDocument();
    expect(screen.getAllByText("direct vendor").length).toBeGreaterThan(0);
    expect(screen.getAllByText("capture ready").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Missing only")).toBeChecked();
    expect(screen.getByLabelText("Active only")).toBeChecked();
    expect(screen.getByLabelText("Dry-run")).toBeChecked();
    expect(screen.getByLabelText("Apply high confidence")).not.toBeChecked();
    expect(screen.getByLabelText("Limit")).toHaveValue(20);
    expect(screen.getByLabelText("Rate limit seconds")).toHaveValue(2);
    await expect(screen.findByText("source-run-001")).resolves.toBeInTheDocument();
    expect(screen.getByText("Dry-run does not activate URLs.")).toBeInTheDocument();
    expect(screen.getByText("Apply-high-confidence writes DB rows.")).toBeInTheDocument();
    expect(screen.getByText("Do not run full catalog until a 5-product dry-run is verified.")).toBeInTheDocument();

    const row = screen.getByText("source-run-001").closest("tr");
    expect(row).not.toBeNull();
    expect(within(row as HTMLTableRowElement).getByRole("link", { name: "Review candidates" })).toHaveAttribute(
      "href",
      "/find-source/candidates?run_id=source-run-001",
    );

    fireEvent.click(within(row as HTMLTableRowElement).getByRole("button", { name: "Open artifacts" }));
    await expect(screen.findByText("summary.json")).resolves.toBeInTheDocument();
    expect(screen.getByText("candidates.csv")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Launch run" }));
    await expect(screen.findByText("Find Source run source-run-002 launched.")).resolves.toBeInTheDocument();
    expect(
      mockFetch.requests.some(
        (request) =>
          request.method === "POST" &&
          request.pathname === "/commerce-api/source-url-agent/runs" &&
          typeof request.body === "object" &&
          request.body !== null &&
          !Array.isArray(request.body) &&
          request.body.dry_run === true &&
          request.body.limit === 20,
      ),
    ).toBe(true);
  });

  it("renders Vendor Sources source URL coverage and capabilities", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/vendor-sources/source-urls");

    await expect(screen.findByRole("heading", { name: "Source URLs / Coverage" })).resolves.toBeInTheDocument();
    expect(screen.getByText("Price Monitoring requires at least one active source URL.")).toBeInTheDocument();
    expect(screen.getByText("Use Find Source to discover and review candidate URLs before capture.")).toBeInTheDocument();
    expect(screen.getByText("Broken, disabled, redirected, and needs-review URLs are not monitorable.")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Vendor Sources navigation" })).toHaveTextContent("Source URLs / Coverage");
    expect(
      within(screen.getByRole("navigation", { name: "Vendor Sources navigation" })).getByRole("link", {
        name: "Source URLs / Coverage",
      }),
    ).not.toHaveAttribute("href", "/catalog");
    expect(screen.getByText("Total catalog products")).toBeInTheDocument();
    expect(screen.getByText("Products with active source URLs")).toBeInTheDocument();
    expect(screen.getAllByText("Products without active source URLs").length).toBeGreaterThan(0);
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Counts by status" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Counts by source_name" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Counts by url_type" })).toBeInTheDocument();

    const missingRow = screen.getByText("AB-123").closest("tr");
    expect(missingRow).not.toBeNull();
    expect(within(missingRow as HTMLTableRowElement).getByText("not monitorable")).toBeInTheDocument();

    const electronetRow = screen
      .getAllByText("electronet")
      .map((node) => node.closest("tr"))
      .find((row): row is HTMLTableRowElement => row !== null && within(row).queryByText("direct_vendor") !== null);
    expect(electronetRow).not.toBeNull();
    expect(within(electronetRow as HTMLTableRowElement).getByText("direct_vendor")).toBeInTheDocument();
    expect(within(electronetRow as HTMLTableRowElement).getByText("capture ready")).toBeInTheDocument();
    expect(within(electronetRow as HTMLTableRowElement).getByText("yes")).toBeInTheDocument();

    for (const sourceName of ["plaisio", "public", "kotsovolos"]) {
      const row = screen
        .getAllByText(sourceName)
        .map((node) => node.closest("tr"))
        .find((candidate): candidate is HTMLTableRowElement =>
          candidate !== null && within(candidate).queryByText("direct_vendor") !== null,
        );
      expect(row).not.toBeNull();
      expect(within(row as HTMLTableRowElement).getByText("capture not implemented")).toBeInTheDocument();
    }
  });

  it("renders Vendor Sources capture runs and opens capture artifacts", async () => {
    const mockFetch = installMockFetch(allRoutes);

    renderWithRouter("/vendor-sources/captures");

    await expect(screen.findByRole("heading", { name: "Vendor Source Capture Runs" })).resolves.toBeInTheDocument();
    const vendorSourcesNav = screen.getByRole("navigation", { name: "Vendor Sources navigation" });
    expect(within(vendorSourcesNav).getByRole("link", { name: "Source URLs / Coverage" })).toHaveAttribute(
      "href",
      "/vendor-sources/source-urls",
    );
    expect(within(vendorSourcesNav).getByRole("link", { name: "Capture Runs" })).toHaveAttribute(
      "href",
      "/vendor-sources/captures",
    );
    expect(screen.getAllByText("One capture run writes one observation batch.").length).toBeGreaterThan(0);
    expect(screen.getByText("Choose one concrete source/vendor per capture run.")).toBeInTheDocument();
    expect(screen.getByLabelText("Source/vendor")).toHaveValue("");
    expect(screen.queryByRole("option", { name: /all active source URLs/i })).not.toBeInTheDocument();
    await expect(screen.findByRole("option", { name: /electronet.*direct vendor.*capture ready/i })).resolves.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "plaisio" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "public" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "kotsovolos" })).not.toBeInTheDocument();
    expect(screen.getAllByText("direct vendor").length).toBeGreaterThan(0);
    expect(screen.getAllByText("capture ready").length).toBeGreaterThan(0);

    await expect(screen.findByText("capture-run-001")).resolves.toBeInTheDocument();
    const row = screen.getByText("capture-run-001").closest("tr");
    expect(row).not.toBeNull();
    expect(within(row as HTMLTableRowElement).getByText("electronet")).toBeInTheDocument();
    expect(within(row as HTMLTableRowElement).getByText("batch-capture-001")).toBeInTheDocument();
    expect(within(row as HTMLTableRowElement).getByText("succeeded")).toBeInTheDocument();
    expect(within(row as HTMLTableRowElement).getByRole("button", { name: "Open artifacts" })).toBeInTheDocument();

    fireEvent.click(within(row as HTMLTableRowElement).getByRole("button", { name: "Open artifacts" }));
    await expect(screen.findByText("summary.json")).resolves.toBeInTheDocument();
    expect(screen.getByText("captures.jsonl")).toBeInTheDocument();

    expect(screen.getByRole("button", { name: "Launch capture run" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Source/vendor"), { target: { value: "electronet" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Launch capture run" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Launch capture run" }));
    await expect(screen.findByText("Vendor source capture run capture-run-002 launched.")).resolves.toBeInTheDocument();
    expect(
      mockFetch.requests.some(
        (request) =>
          request.method === "POST" &&
          request.pathname === "/commerce-api/vendor-sources/captures/runs" &&
          typeof request.body === "object" &&
          request.body !== null &&
          !Array.isArray(request.body) &&
          request.body.source_filter === "electronet" &&
          request.body.limit === 50,
      ),
    ).toBe(true);
  });

  it("previews and applies Product Factory handoff imports under Vendor Sources", async () => {
    const mockFetch = installMockFetch(allRoutes);

    renderWithRouter("/vendor-sources/imports");

    await expect(screen.findByRole("heading", { name: "Product Factory Handoff Imports" })).resolves.toBeInTheDocument();
    expect(screen.getByText("Preview does not write database rows.")).toBeInTheDocument();
    expect(screen.getByText("Apply writes source URLs only; capture runs are launched separately.")).toBeInTheDocument();
    expect(screen.getByText("Only import handoff files produced by Product Factory.")).toBeInTheDocument();
    expect(screen.getByLabelText("Handoff file path")).toHaveValue("work/{model}/integrations/ecommerce_source_handoff.json");
    expect(screen.getByLabelText("catalog_source")).toHaveValue("sourceCata");
    expect(screen.queryByLabelText("Persist initial capture")).not.toBeInTheDocument();
    expect(screen.getByLabelText("report_items_limit")).toHaveValue(200);
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Handoff file path"), {
      target: { value: "work/005606/integrations/ecommerce_source_handoff.json" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));

    await expect(screen.findByRole("heading", { name: "Preview report" })).resolves.toBeInTheDocument();
    expect(screen.getByText("One handoff URL needs review before monitoring.")).toBeInTheDocument();
    expect(screen.getByText("https://www.electronet.gr/midea-md-20l")).toBeInTheDocument();
    expect(screen.getByText("electronet")).toBeInTheDocument();
    expect(screen.getAllByText("005606").length).toBeGreaterThan(0);
    expect(screen.getAllByText("MD-20L").length).toBeGreaterThan(0);
    expect(screen.getByText("high")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();

    fireEvent.click(screen.getByLabelText("I reviewed the preview report"));
    await waitFor(() => expect(screen.getByRole("button", { name: "Apply" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    await expect(screen.findByRole("heading", { name: "Applied import report" })).resolves.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Source URL coverage" })[0]).toHaveAttribute(
      "href",
      "/vendor-sources/source-urls",
    );
    expect(
      screen
        .getAllByRole("link", { name: "Find Source" })
        .some((link) => link.getAttribute("href") === "/find-source/candidates"),
    ).toBe(true);
    expect(
      mockFetch.requests.some(
        (request) =>
          request.method === "POST" &&
          request.pathname === "/commerce-api/catalog/source-urls/import/product-factory/preview" &&
          typeof request.body === "object" &&
          request.body !== null &&
          !Array.isArray(request.body) &&
          request.body.handoff_path === "work/005606/integrations/ecommerce_source_handoff.json" &&
          request.body.persist_initial_capture === false,
      ),
    ).toBe(true);
    expect(
      mockFetch.requests.some(
        (request) =>
          request.method === "POST" &&
          request.pathname === "/commerce-api/catalog/source-urls/import/product-factory/apply",
      ),
    ).toBe(true);
  });

  it("applies run_id query params to Find Source", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/find-source/candidates?run_id=source-run-001");

    await expect(screen.findByRole("heading", { name: "Find Source" })).resolves.toBeInTheDocument();
    expect(screen.getByLabelText("Run id filter")).toHaveValue("source-run-001");
    await expect(screen.findAllByText(/Midea MD-20L/)).resolves.not.toHaveLength(0);
  });

  it("filters Vendor Source candidates by status and source", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/find-source/candidates");

    await expect(screen.findByText("Midea MD-20L Αφυγραντήρας 20L")).resolves.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Candidate source name"), { target: { value: "bestprice" } });

    await expect(screen.findByText("Keyboard mouse bundle")).resolves.toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Midea MD-20L Αφυγραντήρας 20L")).not.toBeInTheDocument());
    expect(screen.getByLabelText("Review status")).toHaveValue("needs_review");
  });

  it("expands Vendor Source candidate inline review panel with decision details", async () => {
    const mockFetch = installMockFetch(allRoutes);

    renderWithRouter("/find-source/candidates");

    await expect(screen.findByText("Midea MD-20L Αφυγραντήρας 20L")).resolves.toBeInTheDocument();
    const row = screen.getByText("Midea MD-20L Αφυγραντήρας 20L").closest("tr");
    expect(row).not.toBeNull();
    fireEvent.click(row as HTMLTableRowElement);

    const panel = await screen.findByRole("region", { name: "Find Source candidate 501 review" });
    expect(row?.nextElementSibling).toBe(panel.closest("tr"));
    expect(screen.queryByRole("dialog", { name: /Vendor source candidate/i })).not.toBeInTheDocument();
    expect(within(panel).queryByText("Decision")).not.toBeInTheDocument();
    expect(within(panel).queryByRole("heading", { name: "Review" })).not.toBeInTheDocument();
    expect(within(panel).queryByText("Catalog product")).not.toBeInTheDocument();
    expect(within(panel).queryByText("Candidate source")).not.toBeInTheDocument();
    expect(within(panel).queryByText("MPN")).not.toBeInTheDocument();
    expect(within(panel).queryByText("Manufacturer")).not.toBeInTheDocument();
    expect(within(panel).queryByText("Candidate price")).not.toBeInTheDocument();
    expect(within(panel).queryByText("Own price")).not.toBeInTheDocument();
    expect(within(panel).queryByText("Debug details")).not.toBeInTheDocument();
    expect(within(panel).queryByText("Matching details")).not.toBeInTheDocument();
    const openCandidateLink = within(panel).getByRole("link", { name: "Open candidate URL" });
    expect(openCandidateLink).toHaveAttribute(
      "href",
      "https://www.skroutz.gr/s/999/midea-md-20l-candidate.html",
    );
    expect(openCandidateLink).toHaveAttribute("target", "_blank");
    expect(openCandidateLink).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
    expect(openCandidateLink).toHaveAttribute("rel", expect.stringContaining("noopener"));
    fireEvent.click(openCandidateLink);
    expect(
      mockFetch.requests.some(
        (request) =>
          request.method === "PATCH" &&
          request.pathname === "/commerce-api/source-url-agent/candidates/501/review",
      ),
    ).toBe(false);
    expect(within(panel).getByRole("button", { name: "Accept" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Reject" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Replace URL" })).toBeInTheDocument();
    fireEvent.click(within(panel).getByRole("button", { name: "Debug" }));
    expect(within(panel).getByText("Matching details")).toBeInTheDocument();
    expect(within(panel).getByText("Raw evidence JSON")).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: /Needs/i })).not.toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: /Not found/i })).not.toBeInTheDocument();
    expect(within(panel).queryByLabelText("Replacement URL")).not.toBeInTheDocument();
  });

  it("selecting another Vendor Source candidate closes the previous expanded row", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/find-source/candidates");

    await expect(screen.findAllByText(/Midea MD-20L/)).resolves.not.toHaveLength(0);
    const firstRow = screen.getAllByText(/Midea MD-20L/)[0].closest("tr");
    const secondRow = screen.getByText("Keyboard mouse bundle").closest("tr");
    expect(firstRow).not.toBeNull();
    expect(secondRow).not.toBeNull();

    fireEvent.click(firstRow as HTMLTableRowElement);
    await expect(screen.findByRole("region", { name: "Find Source candidate 501 review" })).resolves.toBeInTheDocument();

    fireEvent.click(secondRow as HTMLTableRowElement);
    await expect(screen.findByRole("region", { name: "Find Source candidate 502 review" })).resolves.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Find Source candidate 501 review" })).not.toBeInTheDocument();
  });

  it("submits Vendor Source candidate accept and reject actions", async () => {
    const mockFetch = installMockFetch(allRoutes);

    renderWithRouter("/find-source/candidates");

    await expect(screen.findByText("Midea MD-20L Αφυγραντήρας 20L")).resolves.toBeInTheDocument();
    const row = screen.getByText("Midea MD-20L Αφυγραντήρας 20L").closest("tr");
    expect(row).not.toBeNull();
    fireEvent.click(row as HTMLTableRowElement);
    const panel = await screen.findByRole("region", { name: "Find Source candidate 501 review" });
    fireEvent.click(within(panel).getByRole("button", { name: "Accept" }));

    await expect(screen.findByText("Candidate 501 marked accepted.")).resolves.toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("accepted").length).toBeGreaterThan(0));
    expect(
      mockFetch.requests.some(
        (request) =>
          request.method === "PATCH" &&
          request.pathname === "/commerce-api/source-url-agent/candidates/501/review" &&
          typeof request.body === "object" &&
          request.body !== null &&
          !Array.isArray(request.body) &&
          request.body.decision === "accept",
      ),
    ).toBe(true);

    const secondPanel = await screen.findByRole("region", { name: "Find Source candidate 501 review" });
    await waitFor(() => expect(within(secondPanel).getByRole("button", { name: "Reject" })).toBeEnabled());
    fireEvent.click(within(secondPanel).getByRole("button", { name: "Reject" }));

    await expect(screen.findByText("Candidate 501 marked rejected.")).resolves.toBeInTheDocument();
    expect(
      mockFetch.requests.some(
        (request) =>
          request.method === "PATCH" &&
          request.pathname === "/commerce-api/source-url-agent/candidates/501/review" &&
          typeof request.body === "object" &&
          request.body !== null &&
          !Array.isArray(request.body) &&
          request.body.decision === "reject",
      ),
    ).toBe(true);
  });

  it("keeps Replace URL hidden until requested and submits the replacement URL", async () => {
    const mockFetch = installMockFetch(allRoutes);

    renderWithRouter("/find-source/candidates");

    await expect(screen.findAllByText(/Midea MD-20L/)).resolves.not.toHaveLength(0);
    const row = screen.getAllByText(/Midea MD-20L/)[0].closest("tr");
    expect(row).not.toBeNull();
    fireEvent.click(row as HTMLTableRowElement);

    const panel = await screen.findByRole("region", { name: "Find Source candidate 501 review" });
    expect(within(panel).queryByLabelText("Replacement URL")).not.toBeInTheDocument();

    fireEvent.click(within(panel).getByRole("button", { name: "Replace URL" }));
    const replacementInput = within(panel).getByLabelText("Replacement URL");
    const submitButton = within(panel).getByRole("button", { name: "Submit replacement" });
    expect(submitButton).toBeDisabled();

    fireEvent.change(replacementInput, { target: { value: "https://www.public.gr/product/midea-md-20l-fixed" } });
    await waitFor(() => expect(submitButton).toBeEnabled());
    fireEvent.click(submitButton);

    await expect(screen.findByText("Candidate 501 marked accepted.")).resolves.toBeInTheDocument();
    expect(
      mockFetch.requests.some(
        (request) =>
          request.method === "PATCH" &&
          request.pathname === "/commerce-api/source-url-agent/candidates/501/review" &&
          typeof request.body === "object" &&
          request.body !== null &&
          !Array.isArray(request.body) &&
          request.body.decision === "replace_url" &&
          request.body.reviewed_url === "https://www.public.gr/product/midea-md-20l-fixed",
      ),
    ).toBe(true);
  });

  it("collapses a Vendor Source candidate without changing its needs-review status", async () => {
    const mockFetch = installMockFetch(allRoutes);

    renderWithRouter("/find-source/candidates");

    await expect(screen.findAllByText(/Midea MD-20L/)).resolves.not.toHaveLength(0);
    const row = screen.getAllByText(/Midea MD-20L/)[0].closest("tr");
    expect(row).not.toBeNull();

    fireEvent.click(row as HTMLTableRowElement);
    await expect(screen.findByRole("region", { name: "Find Source candidate 501 review" })).resolves.toBeInTheDocument();
    fireEvent.click(row as HTMLTableRowElement);

    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Find Source candidate 501 review" })).not.toBeInTheDocument(),
    );
    expect(within(row as HTMLTableRowElement).getByText("needs review")).toBeInTheDocument();
    expect(
      mockFetch.requests.some(
        (request) =>
          request.method === "PATCH" &&
          request.pathname === "/commerce-api/source-url-agent/candidates/501/review",
      ),
    ).toBe(false);
  });

  it("handles empty Vendor Source candidate filters", async () => {
    installMockFetch([
      {
        method: "GET",
        path: "/commerce-api/source-url-agent/candidates",
        response: { items: [], total: 0, limit: 50, offset: 0 },
      },
      ...allRoutes,
    ]);

    renderWithRouter("/find-source/candidates");

    await expect(screen.findByText("No Find Source candidates")).resolves.toBeInTheDocument();
    expect(screen.getByText("There are no candidates for the active filters.")).toBeInTheDocument();
  });

  it("supports adding validating editing and promoting source URLs in the drawer", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/catalog");

    fireEvent.click(await screen.findByRole("button", { name: "Source URLs for 005606" }));
    let drawer = await screen.findByRole("dialog", { name: "Source URLs" });
    await expect(within(drawer).findByText("https://www.skroutz.gr/s/123/midea-md-20l.html")).resolves.toBeInTheDocument();
    expect(within(drawer).getByText("needs review")).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Promote to active" })).toBeInTheDocument();

    fireEvent.click(within(drawer).getAllByRole("button", { name: "Edit" })[0]);
    fireEvent.change(within(drawer).getByLabelText(/Edit URL for https:\/\/www\.skroutz\.gr/), {
      target: { value: "https://www.public.gr/product/midea-md-20l-edited" },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Save" }));

    drawer = await screen.findByRole("dialog", { name: "Source URLs" });
    await expect(within(drawer).findByText("https://www.public.gr/product/midea-md-20l-edited")).resolves.toBeInTheDocument();

    fireEvent.click(within(drawer).getByRole("button", { name: "Promote to active" }));
    drawer = await screen.findByRole("dialog", { name: "Source URLs" });
    await waitFor(() => expect(within(drawer).queryByRole("button", { name: "Promote to active" })).not.toBeInTheDocument());
    expect(within(drawer).getAllByText("active").length).toBeGreaterThan(1);

    fireEvent.change(within(drawer).getByLabelText("Manual URL"), {
      target: { value: "https://www.public.gr/product/midea-md-20l" },
    });
    fireEvent.change(within(drawer).getByLabelText("Source name"), {
      target: { value: "public" },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Add URL" }));

    await expect(within(drawer).findByText("https://www.public.gr/product/midea-md-20l")).resolves.toBeInTheDocument();

    fireEvent.click(within(drawer).getAllByRole("button", { name: "Validate" })[1]);

    await expect(screen.findAllByText("URL returned HTTP 404.")).resolves.not.toHaveLength(0);
    await expect(screen.findAllByText("broken")).resolves.not.toHaveLength(0);
  });

  it("shows Catalog database/import-required state for structured Catalog 503 responses", async () => {
    installMockFetch([...catalogDbImportRequiredFixtureRoutes, ...allRoutes]);

    renderWithRouter("/catalog");

    await expect(screen.findByRole("heading", { name: "Catalog database/import required" })).resolves.toBeInTheDocument();
    expect(screen.getAllByText(/Catalog database\/import required/).length).toBeGreaterThan(0);
    expect(screen.getByText("Run alembic upgrade head.")).toBeInTheDocument();
    expect(screen.getByText("Run python -m ecommerce.jobs.ingest_catalog.")).toBeInTheDocument();
    expect(screen.getByText(/files, paths, artifacts, or general commerce health/)).toBeInTheDocument();
    expect(screen.queryByText(/Commerce API unreachable/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Create run" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Find more" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Expand" }));
    expect(screen.getByRole("button", { name: "Preview import" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Apply import" })).toBeDisabled();
    expect(screen.getByText("Source URL import is locked until Catalog database/import readiness is restored.")).toBeInTheDocument();
  });

  it("shows Catalog import-required language for empty successful Catalog product warnings", async () => {
    installMockFetch([
      {
        method: "GET",
        path: "/commerce-api/catalog/products",
        response: catalogProductsEmptyImportWarning,
      },
      ...allRoutes,
    ]);

    renderWithRouter("/catalog");

    await expect(screen.findByRole("heading", { name: "Catalog database/import required" })).resolves.toBeInTheDocument();
    expect(screen.getByText("Active catalog is empty or the catalog import is missing.")).toBeInTheDocument();
    expect(screen.getByText("Run python -m ecommerce.jobs.ingest_catalog.")).toBeInTheDocument();
  });

  it("renders Price Monitoring workflow with DB status and run list", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/price-monitoring");

    await expect(screen.findByRole("heading", { name: "Competitor price workflow" })).resolves.toBeInTheDocument();
    await expect(screen.findAllByText("Database ready")).resolves.not.toHaveLength(0);
    const sourceUrlFilter = screen.getByLabelText("Source/vendor");
    expect(sourceUrlFilter).toHaveValue("");
    expect(screen.getByText("Choose one source/vendor to monitor.")).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /All active source URLs/i })).not.toBeInTheDocument();
    await expect(within(sourceUrlFilter).findByRole("option", { name: /electronet/i })).resolves.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Create run" })).toBeDisabled();
    expect(screen.queryByText(/fallback/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/marketplace search/i)).not.toBeInTheDocument();
    await expect(screen.findByText("pm-run-001")).resolves.toBeInTheDocument();
    expect(screen.getByText("exec-success")).toBeInTheDocument();

    const runRow = screen.getByText("pm-run-001").closest("tr");
    expect(runRow).not.toBeNull();
    fireEvent.click(within(runRow as HTMLTableRowElement).getByRole("button", { name: "Use" }));

    await expect(screen.findAllByText("Monitoring URL eligibility")).resolves.not.toHaveLength(0);
    expect(screen.getAllByText("Skipped missing active URL").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Source URL monitoring").length).toBeGreaterThan(0);
    await expect(screen.findAllByText("Prior observations")).resolves.not.toHaveLength(0);
    expect(screen.queryByText("Replaced observations")).not.toBeInTheDocument();
  });

  it("shows Price Monitoring URL eligibility and skipped missing URL products in preview", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/price-monitoring");

    await expect(screen.findAllByText("Database ready")).resolves.not.toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Source/vendor"), { target: { value: "electronet" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));

    await expect(screen.findAllByText("Monitoring URL eligibility")).resolves.not.toHaveLength(0);
    expect(screen.getByText("Skipped missing active URL")).toBeInTheDocument();
    expect(screen.getByText("Products missing active source URLs were skipped. Price Monitoring consumes only existing active source URLs.")).toBeInTheDocument();
    expect(screen.getAllByText("electronet").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "View source URL coverage" })[0]).toHaveAttribute(
      "href",
      "/vendor-sources/source-urls",
    );
    expect(screen.getByText("Monitorable products")).toBeInTheDocument();
    expect(screen.getByText("Skipped products")).toBeInTheDocument();

    const skippedRow = screen.getByText("AB-123").closest("tr");
    expect(skippedRow).not.toBeNull();
    expect(within(skippedRow as HTMLTableRowElement).getByText("Not monitorable")).toBeInTheDocument();
    expect(within(skippedRow as HTMLTableRowElement).getByText("missing_active_source_url")).toBeInTheDocument();
    expect(within(skippedRow as HTMLTableRowElement).getByText("electronet")).toBeInTheDocument();
  });

  it("shows Vendor Sources action when Price Monitoring rejects missing active source URLs", async () => {
    installMockFetch([
      {
        method: "POST",
        path: "/commerce-api/price-monitoring/selection/preview",
        response: priceMonitoringMissingSourceUrlError,
      },
      ...allRoutes,
    ]);

    renderWithRouter("/price-monitoring");

    await expect(screen.findAllByText("Database ready")).resolves.not.toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Source/vendor"), { target: { value: "electronet" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));

    await expect(
      screen.findAllByText("This product cannot be monitored until it has an active URL for electronet."),
    ).resolves.not.toHaveLength(0);
    expect(screen.getByRole("link", { name: "View source URL coverage" })).toHaveAttribute(
      "href",
      "/vendor-sources/source-urls",
    );
    expect(
      screen
        .getAllByRole("link", { name: "Find Source" })
        .some((link) => link.getAttribute("href") === "/find-source/runs"),
    ).toBe(true);
  });

  it("shows no monitorable products when run creation returns only missing source URL skips", async () => {
    installMockFetch([
      {
        method: "POST",
        path: "/commerce-api/price-monitoring/runs",
        response: priceMonitoringMissingSourceUrlSelectionResult,
      },
      ...allRoutes,
    ]);

    renderWithRouter("/price-monitoring");

    await expect(screen.findAllByText("Database ready")).resolves.not.toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Source/vendor"), { target: { value: "electronet" } });
    fireEvent.click(screen.getByRole("button", { name: "Create run" }));

    await waitFor(() =>
      expect(
        screen.getAllByText("This product cannot be monitored until it has an active URL for electronet.").length,
      ).toBeGreaterThan(0),
    );
    expect(screen.getByText("No products with active source URLs were selected.")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "View source URL coverage" })[0]).toHaveAttribute(
      "href",
      "/vendor-sources/source-urls",
    );
    expect(
      screen
        .getAllByRole("link", { name: "Find Source" })
        .some((link) => link.getAttribute("href") === "/find-source/runs"),
    ).toBe(true);
  });

  it("shows the Price Monitoring DB-required banner and disables primary actions when DB is not ready", async () => {
    installMockFetch([
      {
        method: "GET",
        path: "/commerce-api/price-monitoring/db/status",
        response: dbStatusUnavailable,
      },
      ...commerceDbRequiredFixtureRoutes,
      ...allRoutes,
    ]);

    renderWithRouter("/price-monitoring");

    await expect(
      screen.findAllByText(
        "PostgreSQL is required for Price Monitoring. Files, paths, artifacts, and general commerce health may still be available.",
      ),
    ).resolves.not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Create run" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Monitor prices" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Load review" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Export OpenCart price update CSV" })).toBeDisabled();
  });

  it("enables Price Monitoring primary actions when DB is ready", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/price-monitoring");

    await expect(screen.findAllByText("Database ready")).resolves.not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Create run" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Source/vendor"), { target: { value: "electronet" } });
    expect(screen.getByRole("button", { name: "Preview" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Create run" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Monitor prices" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Load review" })).toBeEnabled();
  });

  it("renders Price Monitoring Executions for a selected run", async () => {
    window.sessionStorage.setItem(
      PRICE_MONITORING_STATE_KEY,
      JSON.stringify({
        version: 1,
        state: {
          ...initialPriceMonitoringWorkflowState,
          currentRunId: "pm-run-001",
          currentExecutionId: "exec-success",
        },
      }),
    );
    installMockFetch(allRoutes);

    renderWithRouter("/price-monitoring/executions");

    await expect(screen.findByRole("heading", { name: "Fetch executions" })).resolves.toBeInTheDocument();
    await expect(screen.findByText("exec-success")).resolves.toBeInTheDocument();
    expect(screen.getByText("exec-killed")).toBeInTheDocument();
    expect(screen.getAllByText("Succeeded").length).toBeGreaterThan(0);
  });

  it("renders Price Monitoring Alerts available rules and events", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/price-monitoring/alerts");

    await expect(screen.findByRole("heading", { name: "Price Monitoring Alerts" })).resolves.toBeInTheDocument();
    await expect(screen.findAllByText("Database ready")).resolves.not.toHaveLength(0);
    await expect(screen.findByText("Competitor price is below own price")).resolves.toBeInTheDocument();
    expect(screen.getByText("005606 below own price")).toBeInTheDocument();
  });

  it("renders Price Monitoring Executions DB-required state", async () => {
    window.sessionStorage.setItem(
      PRICE_MONITORING_STATE_KEY,
      JSON.stringify({
        version: 1,
        state: {
          ...initialPriceMonitoringWorkflowState,
          currentRunId: "pm-run-001",
          currentExecutionId: "exec-success",
        },
      }),
    );
    installMockFetch([
      {
        method: "GET",
        path: "/commerce-api/price-monitoring/db/status",
        response: dbStatusUnavailable,
      },
      ...commerceDbRequiredFixtureRoutes,
      ...allRoutes,
    ]);

    renderWithRouter("/price-monitoring/executions");

    await expect(screen.findByRole("heading", { name: "Fetch executions" })).resolves.toBeInTheDocument();
    await expect(screen.findAllByText("Database not ready")).resolves.not.toHaveLength(0);
    await expect(screen.findByText("Execution history locked")).resolves.toBeInTheDocument();
  });

  it("renders Price Monitoring Alerts DB-required state", async () => {
    installMockFetch([
      {
        method: "GET",
        path: "/commerce-api/price-monitoring/db/status",
        response: dbStatusUnavailable,
      },
      ...commerceDbRequiredFixtureRoutes,
      ...allRoutes,
    ]);

    renderWithRouter("/price-monitoring/alerts");

    await expect(screen.findAllByText("Database not ready")).resolves.not.toHaveLength(0);
    await expect(screen.findByText("Alert events locked")).resolves.toBeInTheDocument();
    expect(screen.getByText("Not reachable")).toBeInTheDocument();
    expect(screen.getAllByText("connection refused").length).toBeGreaterThan(0);
  });

  it("keeps Catalog usable when Price Monitoring DB is not ready", async () => {
    installMockFetch([
      {
        method: "GET",
        path: "/commerce-api/price-monitoring/db/status",
        response: dbStatusUnavailable,
      },
      ...commerceDbRequiredFixtureRoutes,
      ...allRoutes,
    ]);

    renderWithRouter("/catalog");

    await expect(screen.findByRole("heading", { name: "Commerce catalog" })).resolves.toBeInTheDocument();
    await expect(screen.findByText("005606")).resolves.toBeInTheDocument();
    expect(screen.queryByText("Database not ready")).not.toBeInTheDocument();
  });

  it("finds more source URLs for skipped Catalog products missing source URLs", async () => {
    const mockFetch = installMockFetch([
      {
        method: "POST",
        path: "/commerce-api/source-url-agent/runs",
        response: {
          run_id: "source-run-002",
          source: "bestprice",
          mode: "catalog",
          dry_run: true,
          apply_high_confidence: false,
          limit: 1,
          status: "queued",
          selected_count: 1,
          candidate_count: 0,
          needs_review_count: 0,
          task_total_count: 1,
          task_finished_count: 0,
          summary: {
            selected_count: 1,
            candidate_count: 0,
            needs_review_count: 0,
            task_total_count: 1,
            task_finished_count: 0,
          },
        },
      },
      {
        method: "GET",
        path: "/commerce-api/source-url-agent/runs/source-run-002",
        response: {
          run_id: "source-run-002",
          source: "bestprice",
          mode: "catalog",
          dry_run: true,
          apply_high_confidence: false,
          limit: 1,
          status: "succeeded",
          selected_count: 1,
          candidate_count: 1,
          needs_review_count: 1,
          task_total_count: 1,
          task_finished_count: 1,
          summary: {
            selected_count: 1,
            candidate_count: 1,
            needs_review_count: 1,
            task_total_count: 1,
            task_finished_count: 1,
          },
        },
      },
      ...allRoutes,
    ]);

    renderWithRouter("/catalog");

    await expect(screen.findByRole("heading", { name: "Commerce catalog" })).resolves.toBeInTheDocument();
    await expect(screen.findByText("005606")).resolves.toBeInTheDocument();
    expect(screen.getByLabelText("Marketplace source (BestPrice / Skroutz)")).toHaveValue("bestprice");
    const discoveryButton = screen.getByRole("button", { name: "Find more" });
    expect(discoveryButton).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    await expect(screen.findByText("Selection preview")).resolves.toBeInTheDocument();
    expect(screen.getByText("missing_active_source_url: 1")).toBeInTheDocument();

    fireEvent.click(discoveryButton);

    await expect(screen.findByText("source-run-002")).resolves.toBeInTheDocument();
    await expect(screen.findByText("succeeded")).resolves.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review candidates" })).toHaveAttribute(
      "href",
      "/find-source/candidates?run_id=source-run-002",
    );
    expect(
      mockFetch.requests.some(
        (request) =>
          request.method === "POST" &&
          request.pathname === "/commerce-api/source-url-agent/runs" &&
          typeof request.body === "object" &&
          request.body !== null &&
          !Array.isArray(request.body) &&
          Array.isArray(request.body.selected_models) &&
          request.body.selected_models.length === 1 &&
          request.body.selected_models.includes("AB-123") &&
          request.body.source === "bestprice" &&
          request.body.missing_only === true &&
          request.body.dry_run === true &&
          request.body.limit === request.body.selected_models.length,
      ),
    ).toBe(true);
  });

  it("renders Jobs with active and terminal statuses", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/jobs");

    await expect(screen.findByRole("heading", { name: "Recent jobs" })).resolves.toBeInTheDocument();
    await expect(screen.findByText("job-queued-1")).resolves.toBeInTheDocument();
    expect(screen.getByText("job-running-1")).toBeInTheDocument();
    expect(screen.getByText("job-succeeded-1")).toBeInTheDocument();
    expect(screen.getByText("job-failed-1")).toBeInTheDocument();
    expect(screen.getByText("job-cancelled-1")).toBeInTheDocument();
    expect(screen.getByText("job-killed-1")).toBeInTheDocument();
  });

  it("renders Filters Manager categories and selected category detail", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/product-factory/filters?category_id=310");

    await expect(screen.findByRole("heading", { name: "Filters Manager" })).resolves.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Pipeline" })).not.toBeInTheDocument();
    await expect(screen.findByRole("heading", { name: "Filters API ready" })).resolves.toBeInTheDocument();
    await expect(screen.findByText(`Revision ${productFactoryFilterRevision.slice(0, 12)}`)).resolves.toBeInTheDocument();
    await expect(screen.findByText("Χωρητικότητα")).resolves.toBeInTheDocument();
    expect(screen.getAllByText("Αφυγραντήρες").length).toBeGreaterThan(0);
    expect(screen.getByText("Wi-Fi")).toBeInTheDocument();
  });

  it("renders Product Factory Workflow initial shell without backend side effects", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/product-factory");

    await expect(screen.findByRole("heading", { name: "Pipeline" })).resolves.toBeInTheDocument();
    await expect(screen.findByText("Product Factory API available")).resolves.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Prepare" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Authoring/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Filter Review/i })).toBeInTheDocument();
  });

  it("starts Authoring jobs automatically after Prepare succeeds", async () => {
    let authoringReads = 0;
    const mockFetch = installMockFetch([
      { method: "GET", path: "/api/health", response: productFactoryHealth },
      { method: "GET", path: "/api/settings", response: productFactorySettings },
      { method: "GET", path: "/api/jobs/by-model/005606", response: { jobs: [] } },
      {
        method: "POST",
        path: "/api/jobs/prepare",
        response: { job: { job_id: "prepare-1", job_type: "prepare", model: "005606", status: "succeeded" } },
      },
      {
        method: "GET",
        path: "/api/authoring/005606",
        response: () => {
          authoringReads += 1;
          return {
            model: "005606",
            intro_text: { status: authoringReads >= 2 ? "valid" : "missing", errors: [] },
            seo_meta: { status: authoringReads >= 2 ? "valid" : "missing", errors: [] },
            ready_for_render: authoringReads >= 2,
            render_block_reasons: authoringReads >= 2 ? [] : ["intro_text_missing", "seo_meta_missing"],
            warnings: [],
          };
        },
      },
      {
        method: "POST",
        path: "/api/authoring/005606/intro-text",
        response: { job: { job_id: "005606-authoring_intro-a1", job_type: "authoring_intro", model: "005606", status: "succeeded" } },
      },
      {
        method: "POST",
        path: "/api/authoring/005606/seo-meta",
        response: { job: { job_id: "005606-authoring_seo-a1", job_type: "authoring_seo", model: "005606", status: "succeeded" } },
      },
      {
        method: "GET",
        path: "/api/filter-review/005606",
        response: {
          model: "005606",
          approved: false,
          render_blocked: false,
          missing_required_groups: [],
          groups: [],
          warnings: [],
        },
      },
      {
        method: "POST",
        path: "/api/jobs/render",
        response: { job: { job_id: "005606-render-a1", job_type: "render", model: "005606", status: "succeeded" } },
      },
      {
        method: "POST",
        path: "/api/jobs/publish",
        response: { job: { job_id: "005606-publish-a1", job_type: "publish", model: "005606", status: "succeeded" } },
      },
    ]);

    renderWithRouter("/product-factory");

    await expect(screen.findByText("Product Factory API available")).resolves.toBeInTheDocument();
    fireEvent.change(screen.getAllByLabelText("Model")[1], { target: { value: "005606" } });
    fireEvent.change(screen.getByLabelText("URL"), { target: { value: "https://example.invalid/product" } });
    fireEvent.click(screen.getByRole("button", { name: "Run Prepare" }));

    await expect(screen.findByText("Publish succeeded.")).resolves.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Publish" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Preparesucceeded/i })).toBeInTheDocument();
    expect(mockFetch.requests.some((request) => request.method === "POST" && request.pathname === "/api/authoring/005606/intro-text")).toBe(true);
    expect(mockFetch.requests.some((request) => request.method === "POST" && request.pathname === "/api/authoring/005606/seo-meta")).toBe(true);
    expect(mockFetch.requests.some((request) => request.method === "POST" && request.pathname === "/api/jobs/render")).toBe(true);
    expect(mockFetch.requests.some((request) => request.method === "POST" && request.pathname === "/api/jobs/publish")).toBe(true);
  });

  it("queues separate Authoring jobs, shows previews, and advances to Filter Review when ready", async () => {
    let authoringReads = 0;
    const mockFetch = installMockFetch([
      { method: "GET", path: "/api/health", response: productFactoryHealth },
      { method: "GET", path: "/api/settings", response: productFactorySettings },
      { method: "GET", path: "/api/jobs/by-model/005606", response: { jobs: [] } },
      {
        method: "GET",
        path: "/api/authoring/005606",
        response: () => {
          authoringReads += 1;
          return {
            model: "005606",
            intro_text: { status: authoringReads >= 1 ? "valid" : "missing", errors: [] },
            seo_meta: { status: authoringReads >= 2 ? "valid" : "missing", errors: [] },
            ready_for_render: authoringReads >= 2,
            render_block_reasons: authoringReads >= 2 ? [] : ["seo_meta_missing"],
            warnings: [],
          };
        },
      },
      {
        method: "POST",
        path: "/api/authoring/005606/intro-text",
        response: { job: { job_id: "005606-authoring_intro-a1", job_type: "authoring_intro", model: "005606", status: "succeeded" } },
      },
      { method: "GET", path: "/api/jobs/005606-authoring_intro-a1/logs", response: { lines: ["Intro text authoring succeeded."] } },
      {
        method: "GET",
        path: "/api/jobs/005606-authoring_intro-a1/artifacts",
        response: {
          artifacts: [
            { name: "intro_text_preview_path", kind: "text_preview", content_type: "text/html", content: "Generated <strong>intro</strong> text." },
          ],
        },
      },
      {
        method: "POST",
        path: "/api/authoring/005606/seo-meta",
        response: { job: { job_id: "005606-authoring_seo-a1", job_type: "authoring_seo", model: "005606", status: "succeeded" } },
      },
      { method: "GET", path: "/api/jobs/005606-authoring_seo-a1/logs", response: { lines: ["SEO meta authoring succeeded."] } },
      {
        method: "GET",
        path: "/api/jobs/005606-authoring_seo-a1/artifacts",
        response: {
          artifacts: [
            {
              name: "seo_meta_preview_path",
              kind: "json_preview",
              content_type: "application/json",
              content: JSON.stringify({ meta_description: "Generated <strong>description</strong>", meta_keywords: ["tv", "oled"] }),
            },
          ],
        },
      },
      {
        method: "GET",
        path: "/api/filter-review/005606",
        response: {
          model: "005606",
          approved: false,
          render_blocked: false,
          missing_required_groups: [],
          groups: [],
          warnings: [],
        },
      },
      {
        method: "POST",
        path: "/api/jobs/render",
        response: { job: { job_id: "005606-render-a1", job_type: "render", model: "005606", status: "succeeded" } },
      },
      {
        method: "POST",
        path: "/api/jobs/publish",
        response: { job: { job_id: "005606-publish-a1", job_type: "publish", model: "005606", status: "succeeded" } },
      },
    ]);

    renderWithRouter("/product-factory/005606");

    await expect(screen.findByText("Product Factory API available")).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Authoring/i }));
    fireEvent.click(screen.getByRole("button", { name: "Run Intro Text" }));
    await expect(screen.findByText("Intro text job succeeded.")).resolves.toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("005606-authoring_intro-a1").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByText(/Generated/).length).toBeGreaterThan(0));

    fireEvent.click(screen.getByRole("button", { name: "Run SEO Meta" }));
    await expect(screen.findByText("Publish succeeded.")).resolves.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Publish" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Authoring/i }));
    await waitFor(() => expect(screen.getAllByText("005606-authoring_seo-a1").length).toBeGreaterThan(0));
    const metaDescriptionCard = screen.getByText("Meta description").closest(".authoring-preview-card");
    const metaKeywordsCard = screen.getByText("Meta keywords").closest(".authoring-preview-card");
    expect(metaDescriptionCard).not.toBeNull();
    expect(metaKeywordsCard).not.toBeNull();
    expect(within(metaDescriptionCard as HTMLElement).getByText("Generated")).toBeInTheDocument();
    expect(within(metaDescriptionCard as HTMLElement).getByText("description").tagName).toBe("STRONG");
    expect(metaDescriptionCard?.nextElementSibling).toBe(metaKeywordsCard);
    expect(mockFetch.requests.some((request) => request.method === "POST" && request.pathname === "/api/jobs/render")).toBe(true);
    expect(mockFetch.requests.some((request) => request.method === "POST" && request.pathname === "/api/jobs/publish")).toBe(true);
  });

  it("starts Publish automatically after Render succeeds", async () => {
    let rendered = false;
    const mockFetch = installMockFetch([
      { method: "GET", path: "/api/health", response: productFactoryHealth },
      { method: "GET", path: "/api/settings", response: productFactorySettings },
      {
        method: "GET",
        path: "/api/jobs/by-model/005606",
        response: () => ({
          jobs: rendered
            ? [{ job_id: "render-1", job_type: "render", model: "005606", status: "succeeded" }]
            : [],
        }),
      },
      {
        method: "POST",
        path: "/api/jobs/render",
        response: () => {
          rendered = true;
          return { job: { job_id: "render-1", job_type: "render", model: "005606", status: "succeeded" } };
        },
      },
      {
        method: "POST",
        path: "/api/jobs/publish",
        response: { job: { job_id: "publish-1", job_type: "publish", model: "005606", status: "succeeded" } },
      },
    ]);

    renderWithRouter("/product-factory/005606");

    await expect(screen.findByText("Product Factory API available")).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Render/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Render" })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Render" }));

    await expect(screen.findByText("Publish succeeded.")).resolves.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Publish" })).toBeInTheDocument();
    expect(mockFetch.requests.some((request) => request.method === "POST" && request.pathname === "/api/jobs/publish")).toBe(true);
  });

  it("stops on Filter Review when values are outside supported filters", async () => {
    const mockFetch = installMockFetch([
      { method: "GET", path: "/api/health", response: productFactoryHealth },
      { method: "GET", path: "/api/settings", response: productFactorySettings },
      { method: "GET", path: "/api/jobs/by-model/005606", response: { jobs: [] } },
      {
        method: "POST",
        path: "/api/jobs/prepare",
        response: { job: { job_id: "prepare-1", job_type: "prepare", model: "005606", status: "succeeded" } },
      },
      {
        method: "GET",
        path: "/api/authoring/005606",
        response: {
          model: "005606",
          intro_text: { status: "valid", errors: [] },
          seo_meta: { status: "valid", errors: [] },
          ready_for_render: true,
          render_block_reasons: [],
          warnings: [],
        },
      },
      {
        method: "GET",
        path: "/api/filter-review/005606",
        response: {
          model: "005606",
          approved: false,
          render_blocked: false,
          missing_required_groups: [],
          groups: [
            {
              group_id: "screen-size",
              group_name: "Screen size",
              required: true,
              resolved_value: "55 inch",
              reviewed_value: "55 inch",
              effective_value: "55 inch",
              outside_allowed: true,
            },
          ],
          warnings: ["category_filter_review_not_approved"],
        },
      },
    ]);

    renderWithRouter("/product-factory");

    await expect(screen.findByText("Product Factory API available")).resolves.toBeInTheDocument();
    fireEvent.change(screen.getAllByLabelText("Model")[1], { target: { value: "005606" } });
    fireEvent.change(screen.getByLabelText("URL"), { target: { value: "https://example.invalid/product" } });
    fireEvent.click(screen.getByRole("button", { name: "Run Prepare" }));

    await expect(screen.findByText(/Filter Review requires manual review/)).resolves.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Filter Review" })).toBeInTheDocument();
    expect(screen.getByText("Screen size: Outside allowed")).toBeInTheDocument();
    expect(screen.queryByText("category_filter_review_not_approved")).not.toBeInTheDocument();
    expect(mockFetch.requests.some((request) => request.method === "POST" && request.pathname === "/api/jobs/render")).toBe(false);
  });

  it("treats approved Filter Review object-shaped missing groups as non-blocking and hides Authoring defaults outside Authoring", async () => {
    installMockFetch([
      { method: "GET", path: "/api/health", response: productFactoryHealth },
      { method: "GET", path: "/api/settings", response: productFactorySettings },
      { method: "GET", path: "/api/jobs/by-model/005606", response: { jobs: [] } },
      {
        method: "GET",
        path: "/api/filter-review/005606",
        response: {
          model: "005606",
          category_id: "cat_tv",
          taxonomy_path: "TV > OLED",
          filter_category_found: true,
          approved: true,
          approved_at: "2026-05-09T08:34:19+00:00",
          render_blocked: false,
          render_block_reasons: [],
          missing_required_groups: [
            { group_id: "resolution", group_name: "Ανάλυση", required: true, status: "active" },
          ],
          groups: [
            {
              group_id: "resolution",
              group_name: "Ανάλυση",
              required: true,
              status: "active",
              resolved_value: "",
              reviewed_value: "4K UHD",
              effective_value: "4K UHD",
              source: "manual_review",
            },
          ],
          warnings: [],
          review_artifact_path: "work/005606/review/category_filters.override.json",
        },
      },
      {
        method: "POST",
        path: "/api/jobs/render",
        response: { job: { job_id: "005606-render-a1", job_type: "render", model: "005606", status: "succeeded" } },
      },
      {
        method: "POST",
        path: "/api/jobs/publish",
        response: { job: { job_id: "005606-publish-a1", job_type: "publish", model: "005606", status: "succeeded" } },
      },
    ]);

    renderWithRouter("/product-factory/005606");

    await expect(screen.findByText("Product Factory API available")).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Filter Review/i }));
    expect(screen.queryByText("Authoring defaults")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load Filter Review" }));

    await expect(screen.findByText("Publish succeeded.")).resolves.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Publish" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Filter Reviewsucceeded/i })).toBeInTheDocument();
    expect(screen.queryByText(/\[object Object\]/)).not.toBeInTheDocument();
    expect(screen.queryByText("Missing required groups")).not.toBeInTheDocument();

    expect(screen.queryByText("Authoring defaults")).not.toBeInTheDocument();
  });

  it("keeps SEO Meta runnable when Intro Text job fails", async () => {
    const mockFetch = installMockFetch([
      { method: "GET", path: "/api/health", response: productFactoryHealth },
      { method: "GET", path: "/api/settings", response: productFactorySettings },
      { method: "GET", path: "/api/jobs/by-model/005606", response: { jobs: [] } },
      {
        method: "GET",
        path: "/api/authoring/005606",
        response: {
          model: "005606",
          intro_text: { status: "missing", errors: [] },
          seo_meta: { status: "valid", errors: [] },
          ready_for_render: false,
          render_block_reasons: ["intro_text_missing"],
          warnings: [],
        },
      },
      {
        method: "POST",
        path: "/api/authoring/005606/intro-text",
        response: { job: { job_id: "005606-authoring_intro-failed", job_type: "authoring_intro", model: "005606", status: "failed", error: "LLM stage validation failed." } },
      },
      { method: "GET", path: "/api/jobs/005606-authoring_intro-failed/logs", response: { lines: ["Intro text authoring failed."] } },
      { method: "GET", path: "/api/jobs/005606-authoring_intro-failed/artifacts", response: { artifacts: [] } },
    ]);

    renderWithRouter("/product-factory/005606");

    await expect(screen.findByText("Product Factory API available")).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Authoring/i }));
    fireEvent.click(screen.getByRole("button", { name: "Run Intro Text" }));

    await expect(screen.findByText(/LLM stage validation failed/, {}, { timeout: 4_000 })).resolves.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Authoring" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run SEO Meta" })).not.toBeDisabled();
    expect(mockFetch.requests.some((request) => request.method === "POST" && request.pathname === "/api/jobs/render")).toBe(false);
  });

  it("clears stale authoring validation errors after a later Intro Text success", async () => {
    const validationError = "LLM stage validation failed: stage=intro_text; error_code=llm_intro_text_emphasis_overused; attempt_count=1; reason=intro validation failed with a non-retryable error";
    let introValid = false;
    installMockFetch([
      { method: "GET", path: "/api/health", response: productFactoryHealth },
      { method: "GET", path: "/api/settings", response: productFactorySettings },
      { method: "GET", path: "/api/jobs/by-model/005606", response: { jobs: [] } },
      {
        method: "GET",
        path: "/api/authoring/005606",
        response: () => ({
          model: "005606",
          intro_text: { status: introValid ? "valid" : "missing", errors: [] },
          seo_meta: { status: "valid", errors: [] },
          ready_for_render: introValid,
          render_block_reasons: introValid ? [] : ["intro_text_missing"],
          warnings: [],
        }),
      },
      {
        method: "POST",
        path: "/api/authoring/005606/intro-text",
        response: { job: { job_id: "005606-authoring_intro-failed", job_type: "authoring_intro", model: "005606", status: "failed", error: validationError } },
      },
      { method: "GET", path: "/api/jobs/005606-authoring_intro-failed/logs", response: { lines: ["Intro text authoring failed."] } },
      { method: "GET", path: "/api/jobs/005606-authoring_intro-failed/artifacts", response: { artifacts: [] } },
      {
        method: "POST",
        path: "/api/authoring/005606/intro-text/retry",
        response: () => {
          introValid = true;
          return { job: { job_id: "005606-authoring_intro-succeeded", job_type: "authoring_intro", model: "005606", status: "succeeded" } };
        },
      },
      { method: "GET", path: "/api/jobs/005606-authoring_intro-succeeded/logs", response: { lines: ["Intro text authoring succeeded."] } },
      { method: "GET", path: "/api/jobs/005606-authoring_intro-succeeded/artifacts", response: { artifacts: [] } },
      {
        method: "GET",
        path: "/api/filter-review/005606",
        response: {
          model: "005606",
          approved: true,
          render_blocked: false,
          missing_required_groups: [],
          groups: [],
          warnings: [],
        },
      },
      {
        method: "POST",
        path: "/api/jobs/render",
        response: { job: { job_id: "005606-render-a1", job_type: "render", model: "005606", status: "succeeded" } },
      },
      {
        method: "POST",
        path: "/api/jobs/publish",
        response: { job: { job_id: "005606-publish-a1", job_type: "publish", model: "005606", status: "succeeded" } },
      },
    ]);

    renderWithRouter("/product-factory/005606");

    await expect(screen.findByText("Product Factory API available")).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Authoring/i }));
    fireEvent.click(screen.getByRole("button", { name: "Run Intro Text" }));
    await expect(screen.findByText(validationError, {}, { timeout: 4_000 })).resolves.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry Intro Text" }));
    await expect(screen.findByText("Publish succeeded.")).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Authoring/i }));

    expect(screen.queryByText(validationError)).not.toBeInTheDocument();
  });

  it("does not render intro emphasis warning when diagnostics are missing", async () => {
    installMockFetch(makeGenericWorkflowRoutes("GENERIC-001", genericAuthoringStatus()));

    renderWithRouter("/product-factory/GENERIC-001");

    await expect(screen.findByText("Product Factory API available")).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Authoring/i }));
    const refreshButton = screen.getByRole("button", { name: "Refresh Authoring" });
    await waitFor(() => expect(refreshButton).not.toBeDisabled());
    fireEvent.click(refreshButton);

    await expect(screen.findByText("Authoring is ready. Advanced to Filter Review.")).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Authoring/i }));
    expect(screen.getByText("Authoring status loaded.")).toBeInTheDocument();
    expect(screen.queryByText("Intro emphasis missing")).not.toBeInTheDocument();
    expect(screen.queryByText("Output path")).not.toBeInTheDocument();
    expect(screen.queryByText("Trace path")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Max emphasized words (%)")).toHaveValue(35));
  });

  it("renders a yellow intro emphasis warning without blocking render", async () => {
    installMockFetch(
      makeGenericWorkflowRoutes(
        "GENERIC-001",
        genericAuthoringStatus({
          intro_text: {
            status: "valid",
            output_path: "runs/GENERIC-001/intro.txt",
            word_count: 96,
            min_words: 80,
            max_words: 140,
            max_attempts: 3,
            errors: [],
            emphasis_warning_codes: ["llm_intro_text_emphasis_missing"],
            strong_span_count: 0,
            emphasized_word_count: 0,
            visible_word_count: 96,
            emphasized_word_ratio: 0,
          },
        }),
      ),
    );

    renderWithRouter("/product-factory/GENERIC-001");

    await expect(screen.findByText("Product Factory API available")).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Authoring/i }));
    const refreshButton = screen.getByRole("button", { name: "Refresh Authoring" });
    await waitFor(() => expect(refreshButton).not.toBeDisabled());
    fireEvent.click(refreshButton);

    await expect(screen.findByText("Authoring is ready. Advanced to Filter Review.")).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Authoring/i }));
    const warningBadge = await screen.findByText("Intro emphasis missing");
    expect(warningBadge).toHaveClass("status-badge", "warning");
    expect(warningBadge).toHaveAttribute(
      "title",
      "Intro Text is valid, but no key facts are bolded yet.",
    );
    expect(screen.getByText("Strong span count")).toBeInTheDocument();
    expect(screen.getByText("Warning codes")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Render/i }));
    expect(screen.getByRole("button", { name: "Render" })).not.toBeDisabled();
    expect(screen.queryByText(/Render requires model, backend health, and authoring readiness/)).not.toBeInTheDocument();
  });

  it("renders hard intro emphasis validation codes as errors", async () => {
    installMockFetch(
      makeGenericWorkflowRoutes(
        "GENERIC-001",
        genericAuthoringStatus({
          intro_text: {
            status: "llm_intro_text_emphasis_invalid",
            output_path: "runs/GENERIC-001/intro.txt",
            errors: [],
            emphasis_warning_codes: ["llm_intro_text_emphasis_missing"],
          },
          ready_for_render: false,
          render_block_reasons: ["intro_text_invalid"],
        }),
      ),
    );

    renderWithRouter("/product-factory/GENERIC-001");

    await expect(screen.findByText("Product Factory API available")).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Authoring/i }));
    const refreshButton = screen.getByRole("button", { name: "Refresh Authoring" });
    await waitFor(() => expect(refreshButton).not.toBeDisabled());
    fireEvent.click(refreshButton);

    await expect(screen.findByText("Validation errors")).resolves.toBeInTheDocument();
    expect(screen.getAllByText("llm_intro_text_emphasis_invalid").length).toBeGreaterThan(0);
    expect(screen.queryByText("Intro emphasis missing")).not.toBeInTheDocument();
  });
});
