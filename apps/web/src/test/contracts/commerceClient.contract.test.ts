import { describe, expect, it } from "vitest";
import { CommerceApiError, commerceClient } from "../../api/commerceClient";
import {
  catalogDbImportRequiredFixtureRoutes,
  catalogProductsEmptyImportWarning,
  alertEvents,
  commerceDbUnavailableError,
  commerceDbRequiredFixtureRoutes,
  commerceFixtureRoutes,
  dbStatusMigrationMissing,
  dbStatusNotConfigured,
  dbStatusUnavailable,
  priceMonitoringExecutions,
  productFactoryHandoffImportApply,
  productFactoryHandoffImportPreview,
  sourceUrlImportApply,
  sourceUrlImportPreview,
  sourceUrlAgentArtifacts,
  sourceUrlAgentRuns,
  sourceUrlSummary,
  sourceUrlValidationSuccess,
  sourceUrlsForCatalogProduct,
  vendorSourceCaptureArtifacts,
  vendorSourceCaptureRuns,
  vendorSourceCapabilities,
  vendorSourceUrlSummary,
} from "../fixtures/commerceApi";
import { installMockFetch } from "../mockFetch";

describe("commerce API client contract fixtures", () => {
  it("preserves catalog product model strings with leading zeroes", async () => {
    installMockFetch(commerceFixtureRoutes);

    const products = await commerceClient.listCatalogProducts({ page: 1, page_size: 100 });
    expect(products.items[0]).toMatchObject({
      model: "005606",
      manufacturer: "Midea",
      family: "Σπίτι",
    });
    expect(typeof products.items[0].model).toBe("string");
    expect(products.items[0].catalog_product_id).toBe(1);
  });

  it("lists creates updates and validates Catalog source URLs", async () => {
    installMockFetch([
      ...commerceFixtureRoutes,
      {
        method: "POST",
        path: "/commerce-api/catalog/source-urls/102/validate",
        response: sourceUrlValidationSuccess,
      },
    ]);

    await expect(commerceClient.listCatalogProductSourceUrls(1)).resolves.toMatchObject({
      items: expect.arrayContaining([
        expect.objectContaining({
          id: 101,
          catalog_product_id: 1,
          url: sourceUrlsForCatalogProduct.items[0].url,
          status: "active",
          url_type: "manual",
          product_source_id: 1001,
          capture_status: "success",
          source_capture_snapshot_id: 9001,
          full_snapshot_ref: expect.objectContaining({ path: "source-captures/9001/full-snapshot.json" }),
        }),
        expect.objectContaining({
          id: 102,
          status: "needs_review",
          url_type: "imported",
        }),
        expect.objectContaining({
          source_name: "electronet",
          source_domain: "electronet.gr",
          status: "active",
        }),
        expect.objectContaining({
          source_name: "public",
          source_domain: "public.gr",
          status: "active",
        }),
        expect.objectContaining({
          source_name: "plaisio",
          source_domain: "plaisio.gr",
          status: "disabled",
        }),
        expect.objectContaining({
          source_name: "kotsovolos",
          source_domain: "kotsovolos.gr",
          status: "disabled",
        }),
      ]),
    });

    await expect(
      commerceClient.createCatalogProductSourceUrl(1, {
        url: "https://www.public.gr/product/midea-md-20l",
        url_type: "manual",
      }),
    ).resolves.toMatchObject({
      catalog_product_id: 1,
      status: "active",
      url_type: "manual",
    });

    await expect(commerceClient.updateCatalogSourceUrl(101, { status: "disabled" })).resolves.toMatchObject({
      id: 101,
      status: "disabled",
    });

    await expect(commerceClient.validateCatalogSourceUrl(102)).resolves.toMatchObject({
      item: expect.objectContaining({ status: "active" }),
      validation: expect.objectContaining({ status: "success", http_status_code: 200 }),
    });
  });

  it("loads source URL summary and import preview/apply reports", async () => {
    installMockFetch(commerceFixtureRoutes);

    await expect(commerceClient.getSourceUrlSummary()).resolves.toMatchObject({
      total_count: sourceUrlSummary.total_count,
      active_count: sourceUrlSummary.active_count,
      needs_review_count: sourceUrlSummary.needs_review_count,
      by_status: expect.objectContaining({ active: sourceUrlSummary.active_count }),
      products_with_urls_count: sourceUrlSummary.products_with_active_source_urls,
      products_without_urls_count: sourceUrlSummary.products_without_active_source_urls,
      by_type: expect.objectContaining({ imported: sourceUrlSummary.imported_count }),
      by_source: expect.objectContaining({ bestprice: 1 }),
    });

    await expect(commerceClient.getVendorSourceUrlSummary()).resolves.toMatchObject({
      total_count: vendorSourceUrlSummary.total_count,
      active_count: vendorSourceUrlSummary.active_count,
      summary_source: "vendor-sources",
      missing_source_url_models: ["AB-123"],
      missing_active_source_url_products: [
        expect.objectContaining({
          catalog_product_id: 2,
          model: "AB-123",
          reason: "missing_active_source_url",
        }),
      ],
    });

    const body = {
      catalog_source: "sourceCata",
      include_observations: true,
      include_artifacts: true,
      report_items_limit: 200,
    };

    await expect(commerceClient.previewSourceUrlImport(body)).resolves.toMatchObject({
      apply: false,
      applied: false,
      summary: expect.objectContaining({
        candidates_found: sourceUrlImportPreview.summary.candidates_found,
        would_import_count: sourceUrlImportPreview.summary.would_import_count,
      }),
      report_items: expect.arrayContaining([
        expect.objectContaining({ action: "created", status: "active", model: "005606" }),
      ]),
      sources: expect.objectContaining({ observations: expect.objectContaining({ candidates_found: 2 }) }),
    });

    await expect(commerceClient.applySourceUrlImport(body)).resolves.toMatchObject({
      apply: true,
      applied: true,
      summary: expect.objectContaining({
        imported_count: sourceUrlImportApply.summary.imported_count,
      }),
      changed_source_urls: expect.arrayContaining([
        expect.objectContaining({ action: "created" }),
      ]),
    });

    const handoffBody = {
      handoff_path: "work/005606/integrations/ecommerce_source_handoff.json",
      catalog_source: "sourceCata",
      persist_initial_capture: true,
      report_items_limit: 200,
    };

    await expect(commerceClient.previewProductFactoryHandoffImport(handoffBody)).resolves.toMatchObject({
      apply: false,
      applied: false,
      handoff_summary: expect.objectContaining({
        handoff_path: productFactoryHandoffImportPreview.handoff_summary.handoff_path,
      }),
      summary: expect.objectContaining({
        candidates_found: productFactoryHandoffImportPreview.summary.candidates_found,
        would_import_count: productFactoryHandoffImportPreview.summary.would_import_count,
      }),
      report_items: expect.arrayContaining([
        expect.objectContaining({ source_name: "electronet", status: "active", confidence: "high" }),
      ]),
    });

    await expect(commerceClient.applyProductFactoryHandoffImport(handoffBody)).resolves.toMatchObject({
      apply: true,
      applied: true,
      summary: expect.objectContaining({
        imported_count: productFactoryHandoffImportApply.summary.imported_count,
      }),
      changed_source_urls: expect.arrayContaining([
        expect.objectContaining({ action: "created" }),
      ]),
    });
  });

  it("constructs Source URL Agent run URLs and normalizes run artifacts", async () => {
    const mockFetch = installMockFetch(commerceFixtureRoutes);

    await expect(commerceClient.listSourceUrlAgentSources()).resolves.toEqual([
      expect.objectContaining({
        source_name: "skroutz",
        source_type: "marketplace",
        discovery_enabled: true,
      }),
      expect.objectContaining({
        source_name: "bestprice",
        source_type: "marketplace",
        discovery_enabled: true,
      }),
      expect.objectContaining({
        source_name: "electronet",
        source_type: "direct_vendor",
        discovery_enabled: true,
        capture_enabled: true,
        capture_implemented: true,
      }),
      ...vendorSourceCapabilities.items.slice(3).map((source) => expect.objectContaining({
        source_name: source.source_name,
        discovery_enabled: true,
      })),
    ]);

    await expect(commerceClient.listSourceUrlAgentRuns()).resolves.toEqual([
      expect.objectContaining({
        run_id: "source-run-001",
        source: "all",
        mode: "catalog",
        selected_count: sourceUrlAgentRuns.items[0].selected_count,
        candidate_count: sourceUrlAgentRuns.items[0].candidate_count,
      }),
    ]);

    await expect(
      commerceClient.createSourceUrlAgentRun({
        mode: "catalog",
        source: "all",
        missing_only: true,
        active_only: true,
        dry_run: true,
        apply_high_confidence: false,
        limit: 20,
        rate_limit_seconds: 2,
      }),
    ).resolves.toMatchObject({
      run_id: "source-run-002",
      status: "queued",
      dry_run: true,
    });

    await expect(commerceClient.getSourceUrlAgentRun("source-run-001")).resolves.toMatchObject({
      run_id: "source-run-001",
      summary: expect.objectContaining({ candidate_count: 6 }),
    });

    await expect(commerceClient.listSourceUrlAgentRunArtifacts("source-run-001")).resolves.toMatchObject({
      run_id: "source-run-001",
      items: [
        expect.objectContaining({
          path: sourceUrlAgentArtifacts.items[0].path,
          download_url: "/commerce-api/artifacts/source-url-agent/source-run-001/summary.json",
        }),
        expect.objectContaining({ path: sourceUrlAgentArtifacts.items[1].path }),
      ],
    });

    expect(mockFetch.requests.map((request) => `${request.method} ${request.pathname}`)).toEqual(
      expect.arrayContaining([
        "GET /commerce-api/source-url-agent/sources",
        "GET /commerce-api/source-url-agent/runs",
        "POST /commerce-api/source-url-agent/runs",
        "GET /commerce-api/source-url-agent/runs/source-run-001",
        "GET /commerce-api/source-url-agent/runs/source-run-001/artifacts",
      ]),
    );
  });

  it("does not require a backend Source URL Candidate Review layout preference endpoint", () => {
    expect("getSourceUrlCandidateReviewLayout" in commerceClient).toBe(false);
    expect("updateSourceUrlCandidateReviewLayout" in commerceClient).toBe(false);
    expect("resetSourceUrlCandidateReviewLayout" in commerceClient).toBe(false);
    expect(commerceFixtureRoutes.some((route) => String(route.path).includes("candidates/review-layout"))).toBe(false);
  });

  it("constructs Vendor Sources capture run URLs and normalizes capture artifacts", async () => {
    const mockFetch = installMockFetch(commerceFixtureRoutes);

    await expect(commerceClient.listVendorSourceCaptureRuns()).resolves.toEqual([
      expect.objectContaining({
        run_id: "capture-run-001",
        source_filter: "electronet",
        observation_batch_id: "batch-capture-001",
        status: "succeeded",
        selected_source_url_count: vendorSourceCaptureRuns.items[0].selected_source_url_count,
        succeeded_count: vendorSourceCaptureRuns.items[0].succeeded_count,
        failed_count: vendorSourceCaptureRuns.items[0].failed_count,
      }),
    ]);

    await expect(
      commerceClient.createVendorSourceCaptureRun({
        source_filter: "electronet",
        limit: 50,
        include_not_due: false,
        refresh_after_minutes: 1440,
        catalog_product_ids: [],
      }),
    ).resolves.toMatchObject({
      run_id: "capture-run-002",
      status: "queued",
      source_filter: "electronet",
      observation_batch_id: "batch-capture-002",
    });

    await expect(commerceClient.getVendorSourceCaptureRun("capture-run-001")).resolves.toMatchObject({
      run_id: "capture-run-001",
      summary: expect.objectContaining({ succeeded_count: 2 }),
    });

    await expect(commerceClient.listVendorSourceCaptureRunArtifacts("capture-run-001")).resolves.toMatchObject({
      observation_batch_id: "batch-capture-001",
      items: [
        expect.objectContaining({
          path: vendorSourceCaptureArtifacts.items[0].path,
          download_url: "/commerce-api/artifacts/vendor-source-captures/capture-run-001/summary.json",
        }),
        expect.objectContaining({ path: vendorSourceCaptureArtifacts.items[1].path }),
      ],
    });

    expect(mockFetch.requests.map((request) => `${request.method} ${request.pathname}`)).toEqual(
      expect.arrayContaining([
        "GET /commerce-api/vendor-sources/captures/runs",
        "POST /commerce-api/vendor-sources/captures/runs",
        "GET /commerce-api/vendor-sources/captures/runs/capture-run-001",
        "GET /commerce-api/vendor-sources/captures/runs/capture-run-001/artifacts",
      ]),
    );
  });

  it("normalizes malformed source URL payloads to stable empty shapes", async () => {
    installMockFetch([
      { method: "GET", path: "/commerce-api/catalog/products/1/source-urls", response: { items: [null, { nope: true }] } },
      { method: "GET", path: "/commerce-api/catalog/source-urls/summary", response: null },
      { method: "GET", path: "/commerce-api/vendor-sources/source-urls/summary", response: null },
      { method: "POST", path: "/commerce-api/catalog/source-urls/import/preview", response: { report_items: [null, "bad"] } },
    ]);

    await expect(commerceClient.listCatalogProductSourceUrls(1)).resolves.toMatchObject({
      items: [],
      count: 0,
    });
    await expect(commerceClient.getSourceUrlSummary()).resolves.toMatchObject({
      total_count: 0,
      active_count: 0,
    });
    await expect(commerceClient.getVendorSourceUrlSummary()).resolves.toMatchObject({
      total_count: 0,
      active_count: 0,
      summary_source: "vendor-sources",
    });
    await expect(commerceClient.previewSourceUrlImport({})).resolves.toMatchObject({
      apply: false,
      summary: expect.objectContaining({ candidates_found: 0, skipped_count: 0 }),
      report_items: [],
    });
  });

  it("keeps CommerceApiError path and message useful for source URL errors", async () => {
    installMockFetch([
      {
        method: "GET",
        path: "/commerce-api/catalog/products/1/source-urls",
        response: { status: 500, body: { detail: "Source URL query failed." } },
      },
    ]);

    await expect(commerceClient.listCatalogProductSourceUrls(1)).rejects.toMatchObject({
      status: 500,
      path: "/catalog/products/1/source-urls",
      message: expect.stringContaining("Source URL query failed"),
    } satisfies Partial<CommerceApiError>);
  });

  it("normalizes category hierarchy and brands", async () => {
    installMockFetch(commerceFixtureRoutes);

    const hierarchy = await commerceClient.getCatalogCategoryHierarchy();
    expect(hierarchy.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          family: "Σπίτι",
          categories: expect.arrayContaining([
            expect.objectContaining({
              category_name: "Κλιματισμός",
              sub_categories: expect.arrayContaining([
                expect.objectContaining({ sub_category: "Αφυγραντήρες" }),
              ]),
            }),
          ]),
        }),
      ]),
    );

    await expect(commerceClient.listCatalogBrandOptions()).resolves.toEqual(
      expect.arrayContaining([
        expect.objectContaining({ manufacturer: "Midea", count: 1 }),
        expect.objectContaining({ manufacturer: "ΓΕΡΜΑΝΟΣ", count: 1 }),
      ]),
    );
  });

  it("normalizes DB-ready status to ready for Price Monitoring", async () => {
    installMockFetch(commerceFixtureRoutes);
    await expect(commerceClient.getPriceMonitoringDbStatus()).resolves.toMatchObject({
      configured: true,
      reachable: true,
      ready_for_price_monitoring: true,
      price_monitoring_requires_database: true,
      non_db_workflows_available: true,
      dialect: "postgresql",
    });
  });

  it("normalizes DB-not-configured status to not ready for Price Monitoring", async () => {
    installMockFetch([
      {
        method: "GET",
        path: "/commerce-api/price-monitoring/db/status",
        response: dbStatusNotConfigured,
      },
    ]);

    await expect(commerceClient.getPriceMonitoringDbStatus()).resolves.toMatchObject({
      configured: false,
      reachable: false,
      ready_for_price_monitoring: false,
      price_monitoring_requires_database: true,
      non_db_workflows_available: true,
      blocking_reasons: expect.arrayContaining(["ECOMMERCE_DATABASE_URL is not configured."]),
    });
  });

  it("normalizes DB-unreachable status to not ready for Price Monitoring", async () => {
    installMockFetch([
      {
        method: "GET",
        path: "/commerce-api/price-monitoring/db/status",
        response: dbStatusUnavailable,
      },
    ]);

    await expect(commerceClient.getPriceMonitoringDbStatus()).resolves.toMatchObject({
      configured: true,
      reachable: false,
      ready_for_price_monitoring: false,
      error: "connection refused",
    });
  });

  it("normalizes missing migration/table status to not ready for Price Monitoring", async () => {
    installMockFetch([
      {
        method: "GET",
        path: "/commerce-api/price-monitoring/db/status",
        response: dbStatusMigrationMissing,
      },
    ]);

    await expect(commerceClient.getPriceMonitoringDbStatus()).resolves.toMatchObject({
      configured: true,
      reachable: true,
      required_tables_present: false,
      alembic_up_to_date: false,
      ready_for_price_monitoring: false,
    });
  });

  it("infers old-backend DB status conservatively when ready field is absent", async () => {
    installMockFetch([
      {
        method: "GET",
        path: "/commerce-api/price-monitoring/db/status",
        response: {
          configured: true,
          reachable: true,
          error: null,
          required_tables_present: true,
          alembic_up_to_date: true,
        },
      },
    ]);

    await expect(commerceClient.getPriceMonitoringDbStatus()).resolves.toMatchObject({
      ready_for_price_monitoring: true,
      price_monitoring_requires_database: true,
    });

    installMockFetch([
      {
        method: "GET",
        path: "/commerce-api/price-monitoring/db/status",
        response: {
          configured: true,
          reachable: true,
          error: null,
          required_tables_present: false,
        },
      },
    ]);

    await expect(commerceClient.getPriceMonitoringDbStatus()).resolves.toMatchObject({
      ready_for_price_monitoring: false,
    });
  });

  it("normalizes run list run detail fetch status and execution history", async () => {
    installMockFetch(commerceFixtureRoutes);

    await expect(commerceClient.previewPriceMonitoringSelection({ source: "skroutz" })).resolves.toMatchObject({
      selected_count: 1,
      skipped_count: 1,
      skipped_by_reason: expect.objectContaining({ missing_active_source_url: 1 }),
      source_url_coverage: expect.objectContaining({
        products_with_active_source_urls: 1,
        products_without_active_source_urls: 1,
      }),
      selected_items: expect.arrayContaining([
        expect.objectContaining({
          model: "005606",
          source_url_coverage: expect.objectContaining({ has_active_source_url: true }),
        }),
      ]),
      skipped_items: expect.arrayContaining([
        expect.objectContaining({
          model: "AB-123",
          skip_reason: "missing_active_source_url",
          source_url_coverage: expect.objectContaining({ has_active_source_url: false }),
        }),
      ]),
    });

    const runs = await commerceClient.listPriceMonitoringRuns();
    expect(runs[0]).toMatchObject({
      run_id: "pm-run-001",
      latest_fetch: expect.objectContaining({ status: "succeeded" }),
    });

    await expect(commerceClient.getPriceMonitoringRun("pm-run-001")).resolves.toMatchObject({
      run_id: "pm-run-001",
      latest_fetch: expect.objectContaining({ execution_id: "exec-success" }),
    });

    await expect(commerceClient.getPriceMonitoringFetch("pm-run-001")).resolves.toMatchObject({
      execution_id: "exec-success",
      status: "succeeded",
      fetch_input_mode: "source_urls",
      appended_observation_count: 2,
      prior_observation_count: 1,
      was_refetch: true,
      observation_batch_id: "exec-success",
    });

    await expect(commerceClient.getPriceMonitoringRunObservations("pm-run-001")).resolves.toMatchObject({
      count: 2,
      items: expect.arrayContaining([
        expect.objectContaining({
          execution_id: "exec-success",
          fetch_attempt: 2,
          was_refetch: true,
          product_source_id: 1001,
          source_capture_snapshot_id: 9001,
        }),
      ]),
    });

    const executions = await commerceClient.listPriceMonitoringFetchExecutions("pm-run-001");
    expect(executions.map((execution) => execution.status)).toEqual(
      expect.arrayContaining(["running", "succeeded", "failed", "cancelled", "killed"]),
    );
    expect(executions).toHaveLength(priceMonitoringExecutions.length);
  });

  it("normalizes fetch logs review rows and artifact URLs", async () => {
    installMockFetch(commerceFixtureRoutes);

    await expect(commerceClient.getPriceMonitoringFetchLogs("pm-run-001")).resolves.toMatchObject({
      lines: expect.arrayContaining(["matched model 005606"]),
    });

    const review = await commerceClient.getPriceMonitoringReview("pm-run-001");
    expect(review.items[0]).toMatchObject({
      model: "005606",
      warnings: ["Competitor below own price"],
    });
    expect(review.review_csv_path).toMatchObject({
      download_url: "/commerce-api/artifacts/price-monitoring/pm-run-001/review.csv",
    });

    const artifacts = await commerceClient.listPriceMonitoringRunArtifacts("pm-run-001");
    expect(artifacts.items[0]).toMatchObject({
      download_url: "/commerce-api/artifacts/price-monitoring/pm-run-001/enriched.csv",
      can_download: true,
    });
    expect(artifacts.items[1]).toMatchObject({
      is_allowed: false,
      can_read: false,
      can_download: false,
      warning: "Path is outside configured artifact roots.",
    });
  });

  it("normalizes alert rules and events", async () => {
    installMockFetch(commerceFixtureRoutes);

    await expect(commerceClient.listPriceMonitoringAlertRules()).resolves.toMatchObject({
      count: 1,
      items: [expect.objectContaining({ model: "005606", active: true })],
    });

    await expect(commerceClient.listPriceMonitoringAlertEvents({ status: "all" })).resolves.toMatchObject({
      count: alertEvents.count,
      items: expect.arrayContaining([
        expect.objectContaining({
          model: "005606",
          status: "open",
          message: "Competitor price is below own price",
        }),
      ]),
    });
  });

  it("adds useful context for structured 503 DB-required errors", async () => {
    installMockFetch([
      ...commerceDbRequiredFixtureRoutes,
    ]);

    await expect(commerceClient.previewPriceMonitoringSelection({ source: "skroutz" })).rejects.toMatchObject({
      status: 503,
      message: expect.stringContaining("PostgreSQL is required for Price Monitoring"),
    } satisfies Partial<CommerceApiError>);
  });

  it("adds Catalog-specific context for structured Catalog DB/import-required errors", async () => {
    installMockFetch(catalogDbImportRequiredFixtureRoutes);

    await expect(commerceClient.listCatalogProducts({ page: 1, page_size: 100 })).rejects.toMatchObject({
      status: 503,
      message: expect.stringContaining("Catalog database/import required"),
    } satisfies Partial<CommerceApiError>);
  });

  it("preserves empty active Catalog import warnings on product responses", async () => {
    installMockFetch([
      {
        method: "GET",
        path: "/commerce-api/catalog/products",
        response: catalogProductsEmptyImportWarning,
      },
    ]);

    await expect(commerceClient.listCatalogProducts({ page: 1, page_size: 100 })).resolves.toMatchObject({
      items: [],
      warning: "Active catalog is empty. Run python -m ecommerce.jobs.ingest_catalog.",
    });
  });

  it("does not treat DB-not-ready as the commerce backend being fully down", async () => {
    installMockFetch([
      { method: "GET", path: "/commerce-api/health", response: { status: "ok", service: "ecommerce-api" } },
      { method: "GET", path: "/commerce-api/price-monitoring/db/status", response: dbStatusUnavailable },
      {
        method: "GET",
        path: "/commerce-api/price-monitoring/runs",
        response: commerceDbUnavailableError,
      },
    ]);

    await expect(commerceClient.getCommerceHealth()).resolves.toMatchObject({ status: "ok" });
    await expect(commerceClient.getPriceMonitoringDbStatus()).resolves.toMatchObject({
      ready_for_price_monitoring: false,
      non_db_workflows_available: true,
    });
    await expect(commerceClient.listPriceMonitoringRuns()).rejects.toMatchObject({
      status: 503,
    } satisfies Partial<CommerceApiError>);
  });
});
