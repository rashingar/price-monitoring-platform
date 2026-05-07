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
} from "../fixtures/productFactoryApi";
import { installMockFetch, type MockRoute } from "../mockFetch";
import { renderWithRouter } from "../renderWithRouter";

const allRoutes = [...productFactoryFixtureRoutes, ...commerceFixtureRoutes];

function makeGenericWorkflowRoutes(model: string, authoring: unknown): MockRoute[] {
  return [
    { method: "GET", path: "/api/health", response: productFactoryHealth },
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
    installMockFetch(allRoutes);

    renderWithRouter("/catalog");

    await expect(screen.findByRole("heading", { name: "Commerce catalog" })).resolves.toBeInTheDocument();
    await expect(screen.findByText("005606")).resolves.toBeInTheDocument();
    await expect(screen.findByText("Midea Αφυγραντήρας 20L")).resolves.toBeInTheDocument();
    expect(screen.getByText("Αφυγραντήρες")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Source URLs for 005606" })).toBeInTheDocument();
    await expect(screen.findByText("Source URL Import")).resolves.toBeInTheDocument();
    await expect(screen.findByText(/Coverage:/)).resolves.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Preview import" })).not.toBeInTheDocument();
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

  it("renders Vendor Source Candidate Review table", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/vendor-sources/candidates");

    await expect(screen.findByRole("heading", { name: "Vendor Source Candidate Review" })).resolves.toBeInTheDocument();
    await expect(screen.findByText("Midea MD-20L Αφυγραντήρας 20L")).resolves.toBeInTheDocument();
    expect(screen.getByText("Table settings")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Status" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Confidence" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Model" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "MPN" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Manufacturer" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Source" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Candidate price" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Own price" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Candidate title" })).toBeInTheDocument();
    expect(screen.getByText("0.9823")).toBeInTheDocument();
    expect(screen.getAllByText("needs review").length).toBeGreaterThan(0);
    expect(screen.getByText("electronet")).toBeInTheDocument();
    expect(screen.getByText("public")).toBeInTheDocument();
    expect(screen.getByText("plaisio")).toBeInTheDocument();
    expect(screen.getByText("kotsovolos")).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Actions" })).not.toBeInTheDocument();
  });

  it("renders Vendor Source discovery runs with backend source capabilities and candidate review links", async () => {
    const mockFetch = installMockFetch(allRoutes);

    renderWithRouter("/vendor-sources/runs");

    await expect(screen.findByRole("heading", { name: "Vendor Source Discovery Runs" })).resolves.toBeInTheDocument();
    const vendorSourcesNav = screen.getByRole("navigation", { name: "Vendor Sources navigation" });
    expect(vendorSourcesNav).toBeInTheDocument();
    expect(within(vendorSourcesNav).getByRole("link", { name: "Discovery Runs" })).toHaveAttribute(
      "href",
      "/vendor-sources/runs",
    );
    expect(within(vendorSourcesNav).getByRole("link", { name: "Candidates" })).toHaveAttribute(
      "href",
      "/vendor-sources/candidates",
    );
    expect(within(vendorSourcesNav).getByRole("link", { name: "Source URLs / Coverage" })).toHaveAttribute(
      "href",
      "/vendor-sources/source-urls",
    );
    expect(within(vendorSourcesNav).getByRole("link", { name: "Capture Runs" })).toHaveAttribute(
      "href",
      "/vendor-sources/captures",
    );
    expect(within(vendorSourcesNav).getByRole("link", { name: "Imports" })).toHaveAttribute(
      "href",
      "/vendor-sources/imports",
    );
    expect(screen.getByLabelText("Mode")).toHaveValue("catalog");
    expect(screen.getByLabelText("Vendor source filter")).toHaveValue("all");
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
      "/vendor-sources/candidates?run_id=source-run-001",
    );

    fireEvent.click(within(row as HTMLTableRowElement).getByRole("button", { name: "Open artifacts" }));
    await expect(screen.findByText("summary.json")).resolves.toBeInTheDocument();
    expect(screen.getByText("candidates.csv")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Launch run" }));
    await expect(screen.findByText("Vendor source discovery run source-run-002 launched.")).resolves.toBeInTheDocument();
    expect(
      mockFetch.requests.some(
        (request) =>
          request.method === "POST" &&
          request.pathname === "/commerce-api/vendor-sources/agent/runs" &&
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
    expect(screen.getByText("Use Vendor Sources discovery/candidate review/imports to create source URLs.")).toBeInTheDocument();
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
    expect(screen.getAllByRole("link", { name: "Review candidates" })[0]).toHaveAttribute(
      "href",
      "/vendor-sources/candidates",
    );
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

  it("applies run_id query params to Vendor Source Candidate Review", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/vendor-sources/candidates?run_id=source-run-001");

    await expect(screen.findByRole("heading", { name: "Vendor Source Candidate Review" })).resolves.toBeInTheDocument();
    expect(screen.getByLabelText("Run id filter")).toHaveValue("source-run-001");
    await expect(screen.findAllByText(/Midea MD-20L/)).resolves.not.toHaveLength(0);
  });

  it("filters Vendor Source candidates by status and source", async () => {
    installMockFetch(allRoutes);

    renderWithRouter("/vendor-sources/candidates");

    await expect(screen.findByText("Midea MD-20L Αφυγραντήρας 20L")).resolves.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Candidate source name"), { target: { value: "bestprice" } });

    await expect(screen.findByText("Keyboard mouse bundle")).resolves.toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Midea MD-20L Αφυγραντήρας 20L")).not.toBeInTheDocument());
    expect(screen.getByLabelText("Review status")).toHaveValue("needs_review");
  });

  it("expands Vendor Source candidate inline review panel with decision details", async () => {
    const mockFetch = installMockFetch(allRoutes);

    renderWithRouter("/vendor-sources/candidates");

    await expect(screen.findByText("Midea MD-20L Αφυγραντήρας 20L")).resolves.toBeInTheDocument();
    const row = screen.getByText("Midea MD-20L Αφυγραντήρας 20L").closest("tr");
    expect(row).not.toBeNull();
    fireEvent.click(row as HTMLTableRowElement);

    const panel = await screen.findByRole("region", { name: "Vendor source candidate 501 review" });
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
          request.pathname === "/commerce-api/vendor-sources/candidates/501/review",
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

    renderWithRouter("/vendor-sources/candidates");

    await expect(screen.findAllByText(/Midea MD-20L/)).resolves.not.toHaveLength(0);
    const firstRow = screen.getAllByText(/Midea MD-20L/)[0].closest("tr");
    const secondRow = screen.getByText("Keyboard mouse bundle").closest("tr");
    expect(firstRow).not.toBeNull();
    expect(secondRow).not.toBeNull();

    fireEvent.click(firstRow as HTMLTableRowElement);
    await expect(screen.findByRole("region", { name: "Vendor source candidate 501 review" })).resolves.toBeInTheDocument();

    fireEvent.click(secondRow as HTMLTableRowElement);
    await expect(screen.findByRole("region", { name: "Vendor source candidate 502 review" })).resolves.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Vendor source candidate 501 review" })).not.toBeInTheDocument();
  });

  it("submits Vendor Source candidate accept and reject actions", async () => {
    const mockFetch = installMockFetch(allRoutes);

    renderWithRouter("/vendor-sources/candidates");

    await expect(screen.findByText("Midea MD-20L Αφυγραντήρας 20L")).resolves.toBeInTheDocument();
    const row = screen.getByText("Midea MD-20L Αφυγραντήρας 20L").closest("tr");
    expect(row).not.toBeNull();
    fireEvent.click(row as HTMLTableRowElement);
    const panel = await screen.findByRole("region", { name: "Vendor source candidate 501 review" });
    fireEvent.click(within(panel).getByRole("button", { name: "Accept" }));

    await expect(screen.findByText("Candidate 501 marked accepted.")).resolves.toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("accepted").length).toBeGreaterThan(0));
    expect(
      mockFetch.requests.some(
        (request) =>
          request.method === "PATCH" &&
          request.pathname === "/commerce-api/vendor-sources/candidates/501/review" &&
          typeof request.body === "object" &&
          request.body !== null &&
          !Array.isArray(request.body) &&
          request.body.decision === "accept",
      ),
    ).toBe(true);

    const secondPanel = await screen.findByRole("region", { name: "Vendor source candidate 501 review" });
    await waitFor(() => expect(within(secondPanel).getByRole("button", { name: "Reject" })).toBeEnabled());
    fireEvent.click(within(secondPanel).getByRole("button", { name: "Reject" }));

    await expect(screen.findByText("Candidate 501 marked rejected.")).resolves.toBeInTheDocument();
    expect(
      mockFetch.requests.some(
        (request) =>
          request.method === "PATCH" &&
          request.pathname === "/commerce-api/vendor-sources/candidates/501/review" &&
          typeof request.body === "object" &&
          request.body !== null &&
          !Array.isArray(request.body) &&
          request.body.decision === "reject",
      ),
    ).toBe(true);
  });

  it("keeps Replace URL hidden until requested and submits the replacement URL", async () => {
    const mockFetch = installMockFetch(allRoutes);

    renderWithRouter("/vendor-sources/candidates");

    await expect(screen.findAllByText(/Midea MD-20L/)).resolves.not.toHaveLength(0);
    const row = screen.getAllByText(/Midea MD-20L/)[0].closest("tr");
    expect(row).not.toBeNull();
    fireEvent.click(row as HTMLTableRowElement);

    const panel = await screen.findByRole("region", { name: "Vendor source candidate 501 review" });
    expect(within(panel).queryByLabelText("Replacement URL")).not.toBeInTheDocument();

    fireEvent.click(within(panel).getByRole("button", { name: "Replace URL" }));
    const replacementInput = within(panel).getByLabelText("Replacement URL");
    const submitButton = within(panel).getByRole("button", { name: "Submit replacement" });
    expect(submitButton).toBeDisabled();

    fireEvent.change(replacementInput, { target: { value: "https://www.public.gr/product/midea-md-20l-fixed" } });
    await waitFor(() => expect(submitButton).toBeEnabled());
    fireEvent.click(submitButton);

    await expect(screen.findByText("Candidate 501 marked needs review.")).resolves.toBeInTheDocument();
    expect(
      mockFetch.requests.some(
        (request) =>
          request.method === "PATCH" &&
          request.pathname === "/commerce-api/vendor-sources/candidates/501/review" &&
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

    renderWithRouter("/vendor-sources/candidates");

    await expect(screen.findAllByText(/Midea MD-20L/)).resolves.not.toHaveLength(0);
    const row = screen.getAllByText(/Midea MD-20L/)[0].closest("tr");
    expect(row).not.toBeNull();

    fireEvent.click(row as HTMLTableRowElement);
    await expect(screen.findByRole("region", { name: "Vendor source candidate 501 review" })).resolves.toBeInTheDocument();
    fireEvent.click(row as HTMLTableRowElement);

    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Vendor source candidate 501 review" })).not.toBeInTheDocument(),
    );
    expect(within(row as HTMLTableRowElement).getByText("needs review")).toBeInTheDocument();
    expect(
      mockFetch.requests.some(
        (request) =>
          request.method === "PATCH" &&
          request.pathname === "/commerce-api/vendor-sources/candidates/501/review",
      ),
    ).toBe(false);
  });

  it("handles empty Vendor Source candidate filters", async () => {
    installMockFetch([
      {
        method: "GET",
        path: "/commerce-api/vendor-sources/candidates",
        response: { items: [], total: 0, limit: 50, offset: 0 },
      },
      ...allRoutes,
    ]);

    renderWithRouter("/vendor-sources/candidates");

    await expect(screen.findByText("No vendor source candidates")).resolves.toBeInTheDocument();
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
    expect(screen.getByText(/CSV\/Bridge, files, paths, artifacts, or general commerce health/)).toBeInTheDocument();
    expect(screen.queryByText(/Commerce API unreachable/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview selection" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Create price monitoring run" })).toBeDisabled();
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
    expect(screen.getAllByRole("link", { name: "Create/review source URLs in Vendor Sources" })[0]).toHaveAttribute(
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
    expect(screen.getByRole("link", { name: "Create/review source URLs in Vendor Sources" })).toHaveAttribute(
      "href",
      "/vendor-sources/source-urls",
    );
    expect(screen.getByRole("link", { name: "Run Vendor Sources discovery" })).toHaveAttribute(
      "href",
      "/vendor-sources/runs",
    );
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
    expect(screen.getAllByRole("link", { name: "Create/review source URLs in Vendor Sources" })[0]).toHaveAttribute(
      "href",
      "/vendor-sources/source-urls",
    );
    expect(screen.getAllByRole("link", { name: "Run Vendor Sources discovery" })[0]).toHaveAttribute(
      "href",
      "/vendor-sources/runs",
    );
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
        "PostgreSQL is required for Price Monitoring. CSV/Bridge, files, paths, artifacts, and general commerce health may still be available.",
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

  it("keeps CSV/Bridge usable when Price Monitoring DB is not ready", async () => {
    installMockFetch([
      {
        method: "GET",
        path: "/commerce-api/price-monitoring/db/status",
        response: dbStatusUnavailable,
      },
      ...commerceDbRequiredFixtureRoutes,
      ...allRoutes,
    ]);

    renderWithRouter("/csv-bridge");

    await expect(screen.findByRole("heading", { name: "CSV bridge workspace" })).resolves.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Safe file browser" })).toBeInTheDocument();
    expect(screen.queryByText("Database not ready")).not.toBeInTheDocument();
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

  it("does not render intro emphasis warning when diagnostics are missing", async () => {
    installMockFetch(makeGenericWorkflowRoutes("GENERIC-001", genericAuthoringStatus()));

    renderWithRouter("/product-factory/GENERIC-001");

    await expect(screen.findByText("Product Factory API available")).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Authoring/i }));
    const refreshButton = screen.getByRole("button", { name: "Refresh Authoring" });
    await waitFor(() => expect(refreshButton).not.toBeDisabled());
    fireEvent.click(refreshButton);

    await expect(screen.findByText("Authoring status loaded.")).resolves.toBeInTheDocument();
    expect(screen.queryByText("Intro emphasis missing")).not.toBeInTheDocument();
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
