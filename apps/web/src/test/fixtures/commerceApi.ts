import type { MockRequest, MockRoute } from "../mockFetch";

export const commerceHealth = {
  status: "ok",
  service: "ecommerce-api",
  version: "test-fixture",
};

export const platformHealth = {
  status: "warning",
  updated_at: "2026-05-15T10:30:00+00:00",
  groups: [
    {
      id: "ecommerce_api",
      label: "Ecommerce API",
      status: "ready",
      summary: "Ecommerce API is responding.",
      details: [],
      blocking_reasons: [],
      warnings: [],
      links: [],
    },
    {
      id: "ecommerce_database",
      label: "Ecommerce DB",
      status: "ready",
      summary: "Ecommerce database is ready for catalog and price monitoring workflows.",
      details: ["Configured: yes.", "Reachable: yes.", "Required tables present: yes."],
      blocking_reasons: [],
      warnings: [],
      links: [
        { label: "Catalog", url: "/catalog" },
        { label: "Price Monitoring", url: "/price-monitoring" },
      ],
    },
    {
      id: "catalog",
      label: "Catalog",
      status: "ready",
      summary: "Active catalog is available.",
      details: ["Active catalog rows: 2."],
      blocking_reasons: [],
      warnings: [],
      links: [{ label: "Catalog", url: "/catalog" }],
    },
    {
      id: "catalog_update_opencart",
      label: "Catalog Update / OpenCart",
      status: "ready",
      summary: "OpenCart catalog update configuration is present.",
      details: ["Required config keys: OPENCART_STORE_BASE, OPENCART_ADMIN_PATH, OPENCART_ADMIN_USER, OPENCART_ADMIN_PASS."],
      blocking_reasons: [],
      warnings: [],
      links: [
        { label: "Jobs", url: "/jobs" },
        { label: "Catalog", url: "/catalog" },
      ],
    },
    {
      id: "source_url_agent",
      label: "Source URL Agent",
      status: "ready",
      summary: "Source URL Agent providers are ready.",
      details: ["Provider brave_search: enabled, configured."],
      blocking_reasons: [],
      warnings: [],
      links: [
        { label: "Find Source", url: "/find-source/runs" },
        { label: "Candidates", url: "/find-source/candidates" },
      ],
    },
    {
      id: "price_monitoring",
      label: "Price Monitoring",
      status: "ready",
      summary: "Price Monitoring database readiness is available.",
      details: ["Price monitoring DB ready: yes."],
      blocking_reasons: [],
      warnings: [],
      links: [{ label: "Price Monitoring", url: "/price-monitoring" }],
    },
    {
      id: "vendor_sources_capture",
      label: "Vendor Sources Capture",
      status: "ready",
      summary: "Vendor Sources capture configuration is ready.",
      details: [
        "Skroutz capture strategy: Firecrawl.",
        "Firecrawl API key configured: yes.",
        "Direct JSON fallback: removed.",
        "Supported capture vendors: bestprice, electronet, skroutz.",
      ],
      blocking_reasons: [],
      warnings: [],
      links: [
        { label: "Source Health", url: "/vendor-sources/source-health" },
        { label: "Capture Runs", url: "/vendor-sources/captures" },
      ],
    },
    {
      id: "product_factory_api",
      label: "Product Factory API",
      status: "warning",
      summary: "Product Factory API base URL is not configured for backend health checks.",
      details: ["Checked configuration keys: PRODUCT_FACTORY_API_BASE_URL, VITE_API_PROXY_TARGET."],
      blocking_reasons: [],
      warnings: ["Product Factory API health could not be checked because no base URL key is configured."],
      links: [{ label: "Product Factory", url: "/product-factory" }],
    },
  ],
};

export const catalogSummary = {
  total_products: 3,
  active_products: 3,
  atomic_products: 2,
  composite_or_invalid_models: 1,
  bestprice_products: 2,
  skroutz_products: 2,
  missing_mpn: 1,
  manufacturer_count: 3,
};

export const catalogBrands = {
  items: [
    { manufacturer: "Midea", count: 1 },
    { manufacturer: "Inventor", count: 1 },
    { manufacturer: "ΓΕΡΜΑΝΟΣ", count: 1 },
  ],
  manufacturers: [
    { manufacturer: "Midea", count: 1 },
    { manufacturer: "Inventor", count: 1 },
    { manufacturer: "ΓΕΡΜΑΝΟΣ", count: 1 },
  ],
};

export const catalogCategoryHierarchy = {
  items: [
    {
      family: "Σπίτι",
      count: 2,
      categories: [
        {
          category_name: "Κλιματισμός",
          count: 2,
          sub_categories: [
            {
              sub_category: "Αφυγραντήρες",
              count: 2,
              raw_categories: ["Σπίτι > Κλιματισμός > Αφυγραντήρες"],
            },
          ],
        },
      ],
    },
    {
      family: "Τεχνολογία",
      count: 1,
      categories: [
        {
          category_name: "Περιφερειακά",
          count: 1,
          sub_categories: [{ sub_category: "Πληκτρολόγια", count: 1 }],
        },
      ],
    },
  ],
  families: [
    {
      family: "Σπίτι",
      count: 2,
      categories: [
        {
          category_name: "Κλιματισμός",
          count: 2,
          sub_categories: [
            {
              sub_category: "Αφυγραντήρες",
              count: 2,
              raw_categories: ["Σπίτι > Κλιματισμός > Αφυγραντήρες"],
            },
          ],
        },
      ],
    },
    {
      family: "Τεχνολογία",
      count: 1,
      categories: [
        {
          category_name: "Περιφερειακά",
          count: 1,
          sub_categories: [{ sub_category: "Πληκτρολόγια", count: 1 }],
        },
      ],
    },
  ],
};

export const catalogProducts = {
  items: [
    {
      catalog_product_id: 1,
      model: "005606",
      mpn: "MD-20L",
      name: "Midea Αφυγραντήρας 20L",
      manufacturer: "Midea",
      family: "Σπίτι",
      category_name: "Κλιματισμός",
      sub_category: "Αφυγραντήρες",
      raw_category: "Σπίτι > Κλιματισμός > Αφυγραντήρες",
      category_levels: ["Σπίτι", "Κλιματισμός", "Αφυγραντήρες"],
      price: 199.9,
      quantity: 12,
      bestprice_status: 1,
      skroutz_status: 1,
      is_atomic_model: true,
      automation_eligible: true,
      ignored: false,
      warnings: [],
      source_url_coverage: {
        source: "bestprice",
        has_active_source_url: true,
        active_source_url_count: 1,
        needs_review_source_url_count: 0,
        status_counts: { active: 1, needs_review: 0, broken: 0, disabled: 0, redirected: 0 },
      },
      status: 1,
    },
    {
      catalog_product_id: 2,
      model: "AB-123",
      mpn: null,
      name: "Σετ πληκτρολόγιο και ποντίκι",
      manufacturer: "ΓΕΡΜΑΝΟΣ",
      family: "Τεχνολογία",
      category_name: "Περιφερειακά",
      sub_category: "Πληκτρολόγια",
      raw_category: "Τεχνολογία > Περιφερειακά > Πληκτρολόγια",
      price: 39.9,
      quantity: 4,
      bestprice_status: 0,
      skroutz_status: 1,
      is_atomic_model: false,
      automation_eligible: false,
      ignored: false,
      warnings: ["Composite model"],
      source_url_coverage: {
        source: "bestprice",
        has_active_source_url: false,
        active_source_url_count: 0,
        needs_review_source_url_count: 1,
        status_counts: { active: 0, needs_review: 1, broken: 0, disabled: 0, redirected: 0 },
      },
      status: 1,
    },
  ],
  page: 1,
  page_size: 100,
  total: 2,
  filtered_total: 2,
};

export const sourceUrlSummary = {
  source_url_count: 6,
  catalog_product_count: 2,
  products_with_active_source_urls: 1,
  products_without_active_source_urls: 1,
  by_url_type: {
    manual: 3,
    imported: 2,
    discovered: 1,
  },
  by_source_name: {
    skroutz: 1,
    bestprice: 1,
    electronet: 1,
    public: 1,
    plaisio: 1,
    kotsovolos: 1,
  },
  total_count: 6,
  active_count: 3,
  needs_review_count: 1,
  broken_count: 0,
  disabled_count: 2,
  redirected_count: 0,
  manual_count: 3,
  imported_count: 2,
  discovered_count: 1,
  products_with_urls_count: 1,
  products_without_urls_count: 1,
  coverage_percent: 50,
  missing_source_url_models: ["AB-123"],
  missing_source_url_catalog_product_ids: [2],
  missing_active_source_url_products: [
    {
      catalog_product_id: 2,
      model: "AB-123",
      mpn: null,
      manufacturer: "Ξ“Ξ•Ξ΅ΞΞ‘ΞΞΞ£",
      name: "Ξ£ΞµΟ„ Ο€Ξ»Ξ·ΞΊΟ„ΟΞΏΞ»ΟΞ³ΞΉΞΏ ΞΊΞ±ΞΉ Ο€ΞΏΞ½Ο„Ξ―ΞΊΞΉ",
      reason: "missing_active_source_url",
    },
  ],
  by_status: {
    active: 3,
    needs_review: 1,
    broken: 0,
    disabled: 2,
    redirected: 0,
  },
  by_type: {
    manual: 3,
    imported: 2,
    discovered: 1,
  },
  by_source: {
    skroutz: 1,
    bestprice: 1,
    electronet: 1,
    public: 1,
    plaisio: 1,
    kotsovolos: 1,
  },
};

export const vendorSourceUrlSummary = {
  ...sourceUrlSummary,
  summary_scope: "vendor_sources",
};

export const vendorSourceHealth = {
  items: [
    {
      product_source_id: 1001,
      product_id: 501,
      model: "005606",
      mpn: "MD-20L",
      vendor: "skroutz",
      source_url: "https://www.skroutz.gr/s/123/midea-md-20l.html",
      canonical_url: "https://www.skroutz.gr/s/123/midea-md-20l.html",
      active: true,
      health: "failing",
      last_fetch_status: "failed",
      last_success_at: "2026-05-02T08:00:00Z",
      last_error_at: "2026-05-15T08:00:00Z",
      last_error_code: "FIRECRAWL_PARSE_FAILED",
      last_error_message: "Firecrawl returned content but no Skroutz offers were parsed.",
      health_reason: "firecrawl_parse_failed",
      consecutive_failures: 2,
      data_quality_flags: ["FIRECRAWL_PARSE_FAILED", "firecrawl_parse_failed"],
      updated_at: "2026-05-15T08:00:00Z",
    },
    {
      product_source_id: 1002,
      product_id: 502,
      model: "EL-100",
      mpn: "EL-100",
      vendor: "electronet",
      source_url: "https://www.electronet.gr/p/el-100",
      canonical_url: "https://www.electronet.gr/p/el-100",
      active: true,
      health: "healthy",
      last_fetch_status: "success",
      last_success_at: "2026-05-15T07:00:00Z",
      last_error_at: null,
      last_error_code: null,
      last_error_message: null,
      health_reason: null,
      consecutive_failures: 0,
      data_quality_flags: [],
      updated_at: "2026-05-15T07:00:00Z",
    },
  ],
  limit: 100,
  offset: 0,
  count: 2,
};

export const vendorSourceRecaptureResponse = {
  product_source_id: 1001,
  vendor: "skroutz",
  status: "failed",
  snapshot_id: 9002,
  error_code: "FIRECRAWL_PARSE_FAILED",
  health_reason: "firecrawl_parse_failed",
  capture_run_id: "capture-run-rec-001",
  observation_batch_id: "capture-run-rec-001",
};

export const sourceUrlsForCatalogProduct = {
  items: [
    {
      id: 101,
      product_source_id: 1001,
      catalog_product_id: 1,
      catalog_source: "sourceCata",
      model: "005606",
      mpn: "MD-20L",
      manufacturer: "Midea",
      source_name: "skroutz",
      source_domain: "skroutz.gr",
      url: "https://www.skroutz.gr/s/123/midea-md-20l.html",
      url_normalized: "https://www.skroutz.gr/s/123/midea-md-20l.html",
      status: "active",
      url_type: "manual",
      trust_level: "manual",
      added_by: "operator",
      notes: "Primary manual product URL.",
      last_seen_at: "2026-05-02T08:00:00Z",
      last_success_at: "2026-05-02T08:00:00Z",
      last_failed_at: null,
      failure_count: 0,
      last_error: null,
      capture_status: "success",
      last_capture_status: "success",
      last_capture_strategy: "scheduled-test",
      last_capture_at: "2026-05-02T08:05:00Z",
      last_capture_snapshot_id: 9001,
      source_capture_snapshot_id: 9001,
      full_snapshot_ref: {
        name: "source-capture-9001.json",
        path: "source-captures/9001/full-snapshot.json",
        is_allowed: true,
        can_read: true,
        can_download: true,
      },
      created_at: "2026-05-02T08:00:00Z",
      updated_at: "2026-05-02T08:00:00Z",
    },
    {
      id: 102,
      catalog_product_id: 1,
      catalog_source: "sourceCata",
      model: "005606",
      mpn: "MD-20L",
      manufacturer: "Midea",
      source_name: "bestprice",
      source_domain: "bestprice.gr",
      url: "https://www.bestprice.gr/item/456/midea-md-20l.html",
      url_normalized: "https://www.bestprice.gr/item/456/midea-md-20l.html",
      status: "needs_review",
      url_type: "imported",
      trust_level: "medium",
      added_by: "source-url-import",
      notes: "Imported from enriched artifact; promote after review.",
      last_seen_at: "2026-05-02T07:40:00Z",
      last_success_at: null,
      last_failed_at: null,
      failure_count: 0,
      last_error: null,
      created_at: "2026-05-02T07:40:00Z",
      updated_at: "2026-05-02T07:40:00Z",
    },
    {
      id: 103,
      catalog_product_id: 1,
      catalog_source: "sourceCata",
      model: "005606",
      mpn: "MD-20L",
      manufacturer: "Midea",
      source_name: "electronet",
      source_domain: "electronet.gr",
      url: "https://www.electronet.gr/midea-md-20l",
      url_normalized: "https://www.electronet.gr/midea-md-20l",
      status: "active",
      url_type: "manual",
      trust_level: "manual",
      added_by: "operator",
      notes: "Direct vendor URL.",
      last_seen_at: "2026-05-02T08:20:00Z",
      last_success_at: "2026-05-02T08:20:00Z",
      failure_count: 0,
      last_error: null,
      capture_status: "success",
      last_capture_status: "success",
      source_capture_snapshot_id: 9003,
      full_snapshot_ref: {
        name: "source-capture-9003.json",
        path: "source-captures/9003/full-snapshot.json",
        is_allowed: true,
        can_read: true,
        can_download: true,
      },
      created_at: "2026-05-02T08:20:00Z",
      updated_at: "2026-05-02T08:20:00Z",
    },
    {
      id: 104,
      catalog_product_id: 1,
      catalog_source: "sourceCata",
      model: "005606",
      mpn: "MD-20L",
      manufacturer: "Midea",
      source_name: "public",
      source_domain: "public.gr",
      url: "https://www.public.gr/product/midea-md-20l",
      url_normalized: "https://www.public.gr/product/midea-md-20l",
      status: "active",
      url_type: "manual",
      trust_level: "manual",
      added_by: "operator",
      notes: "Direct vendor URL.",
      last_seen_at: "2026-05-02T08:30:00Z",
      last_success_at: "2026-05-02T08:30:00Z",
      failure_count: 0,
      last_error: null,
      created_at: "2026-05-02T08:30:00Z",
      updated_at: "2026-05-02T08:30:00Z",
    },
    {
      id: 105,
      catalog_product_id: 1,
      catalog_source: "sourceCata",
      model: "005606",
      mpn: "MD-20L",
      manufacturer: "Midea",
      source_name: "plaisio",
      source_domain: "plaisio.gr",
      url: "https://www.plaisio.gr/midea-md-20l",
      url_normalized: "https://www.plaisio.gr/midea-md-20l",
      status: "disabled",
      url_type: "discovered",
      trust_level: "medium",
      added_by: "source-url-agent",
      notes: "Inactive registry vendor URL retained for review.",
      last_seen_at: "2026-05-02T08:40:00Z",
      last_success_at: null,
      failure_count: 0,
      last_error: null,
      created_at: "2026-05-02T08:40:00Z",
      updated_at: "2026-05-02T08:40:00Z",
    },
    {
      id: 106,
      catalog_product_id: 1,
      catalog_source: "sourceCata",
      model: "005606",
      mpn: "MD-20L",
      manufacturer: "Midea",
      source_name: "kotsovolos",
      source_domain: "kotsovolos.gr",
      url: "https://www.kotsovolos.gr/midea-md-20l",
      url_normalized: "https://www.kotsovolos.gr/midea-md-20l",
      status: "disabled",
      url_type: "imported",
      trust_level: "low",
      added_by: "source-url-import",
      notes: "Inactive registry vendor URL retained for review.",
      last_seen_at: "2026-05-02T08:50:00Z",
      last_success_at: null,
      failure_count: 0,
      last_error: null,
      created_at: "2026-05-02T08:50:00Z",
      updated_at: "2026-05-02T08:50:00Z",
    },
  ],
  count: 6,
};

export const catalogProductDetail = {
  product: catalogProducts.items[0],
  source_urls: sourceUrlsForCatalogProduct.items,
  source_url_summary: {
    total_count: sourceUrlsForCatalogProduct.items.length,
    by_status: {
      active: 3,
      needs_review: 1,
      disabled: 2,
    },
    by_source: {
      skroutz: 1,
      bestprice: 1,
      electronet: 1,
      public: 1,
      plaisio: 1,
      kotsovolos: 1,
    },
    by_type: {
      manual: 3,
      imported: 2,
      discovered: 1,
    },
  },
  warnings: [],
};

export const catalogProductDetailWithoutSourceUrls = {
  product: catalogProducts.items[1],
  source_urls: [],
  source_url_summary: {
    total_count: 0,
    by_status: {},
    by_source: {},
    by_type: {},
  },
  warnings: ["Composite model"],
};

export const sourceUrlCoverage = {
  source: "skroutz",
  selected_count: 2,
  products_with_active_source_urls: 1,
  products_without_active_source_urls: 1,
  coverage_percent: 50,
  active_source_url_count: 1,
  needs_review_source_url_count: 1,
  broken_source_url_count: 0,
  disabled_source_url_count: 0,
  redirected_source_url_count: 0,
  missing_source_url_models: ["AB-123"],
  missing_source_url_catalog_product_ids: [2],
  warning: "Products without active source URLs are not eligible for Price Monitoring.",
};

export const createdSourceUrl = {
  id: 103,
  catalog_product_id: 1,
  catalog_source: "sourceCata",
  model: "005606",
  mpn: "MD-20L",
  manufacturer: "Midea",
  source_name: "public",
  source_domain: "public.gr",
  url: "https://www.public.gr/product/midea-md-20l",
  url_normalized: "https://www.public.gr/product/midea-md-20l",
  status: "active",
  url_type: "manual",
  trust_level: "manual",
  added_by: "operator",
  notes: null,
  last_seen_at: null,
  last_success_at: null,
  last_failed_at: null,
  failure_count: 0,
  last_error: null,
  created_at: "2026-05-02T09:00:00Z",
  updated_at: "2026-05-02T09:00:00Z",
};

export const sourceUrlValidationSuccess = {
  item: {
    ...sourceUrlsForCatalogProduct.items[0],
    status: "active",
    last_success_at: "2026-05-02T09:10:00Z",
    failure_count: 0,
    last_error: null,
  },
  validation: {
    status: "success",
    message: "URL is reachable.",
    http_status_code: 200,
  },
};

export const sourceUrlValidationBroken = {
  item: {
    ...sourceUrlsForCatalogProduct.items[0],
    status: "broken",
    last_failed_at: "2026-05-02T09:15:00Z",
    failure_count: 1,
    last_error: "URL returned HTTP 404.",
  },
  validation: {
    status: "failed",
    message: "URL returned HTTP 404.",
    http_status_code: 404,
  },
};

export const sourceUrlImportPreview = {
  mode: "preview",
  applied: false,
  summary: {
    candidates_found: 4,
    imported_count: 2,
    updated_count: 1,
    skipped_count: 1,
    active_count: 2,
    needs_review_count: 1,
    invalid_url_count: 0,
    duplicate_count: 1,
    unresolved_identity_count: 0,
    ambiguous_identity_count: 1,
    would_import_count: 2,
    would_update_count: 1,
  },
  warnings: ["Ambiguous identity for artifact row model MIXED-001."],
  skipped_reasons: {
    ambiguous_identity: 1,
  },
  changed_source_urls: [],
  sources: {
    observations: { candidates_found: 2 },
    artifacts: { candidates_found: 2 },
  },
  candidate_evidence: [],
  items: [
    {
      action: "created",
      status: "active",
      source_name: "skroutz",
      source_domain: "skroutz.gr",
      catalog_source: "sourceCata",
      model: "005606",
      mpn: "MD-20L",
      url: "https://www.skroutz.gr/s/123/midea-md-20l.html",
      evidence_source: "price_observations",
      evidence_detail: "run pm-run-001 matched by model",
      reason: null,
      confidence: "high",
      catalog_product_id: 1,
      source_url_id: null,
    },
    {
      action: "created",
      status: "needs_review",
      source_name: "bestprice",
      source_domain: "bestprice.gr",
      catalog_source: "sourceCata",
      model: "005606",
      mpn: "MD-20L",
      url: "https://www.bestprice.gr/item/456/midea-md-20l.html",
      evidence_source: "enriched_artifact",
      evidence_detail: "enriched CSV artifact",
      reason: null,
      confidence: "medium",
      catalog_product_id: 1,
      source_url_id: null,
    },
    {
      action: "skipped",
      status: "needs_review",
      source_name: "unknown",
      source_domain: "example.test",
      catalog_source: "sourceCata",
      model: "MIXED-001",
      mpn: null,
      url: "https://example.test/mixed",
      evidence_source: "enriched_csv_artifact",
      evidence_detail: "enriched CSV output",
      reason: "ambiguous_identity",
      confidence: "low",
      catalog_product_id: null,
      source_url_id: null,
    },
  ],
  truncated: false,
};

export const sourceUrlImportApply = {
  ...sourceUrlImportPreview,
  mode: "apply",
  applied: true,
  changed_source_urls: [
    {
      action: "created",
      changed_fields: [],
      source_url: {
        ...sourceUrlsForCatalogProduct.items[1],
        id: 104,
      },
    },
  ],
};

export const productFactoryHandoffImportPreview = {
  mode: "preview",
  applied: false,
  apply: false,
  handoff_summary: {
    handoff_path: "work/005606/integrations/ecommerce_source_handoff.json",
    source_url_count: 2,
    capture_count: 1,
  },
  summary: {
    candidates_found: 2,
    imported_count: 1,
    updated_count: 1,
    skipped_count: 1,
    active_count: 1,
    needs_review_count: 1,
    invalid_url_count: 0,
    duplicate_count: 0,
    unresolved_identity_count: 0,
    ambiguous_identity_count: 0,
    would_import_count: 1,
    would_update_count: 1,
  },
  warnings: ["One handoff URL needs review before monitoring."],
  skipped_reasons: {
    duplicate: 1,
  },
  changed_source_urls: [],
  source_stats: {
    product_factory_handoff: { candidates_found: 2 },
  },
  candidate_evidence: [],
  items: [
    {
      action: "created",
      status: "active",
      source_name: "electronet",
      source_domain: "electronet.gr",
      catalog_source: "sourceCata",
      model: "005606",
      mpn: "MD-20L",
      url: "https://www.electronet.gr/midea-md-20l",
      evidence_source: "product_factory_handoff",
      evidence_detail: "work/005606/integrations/ecommerce_source_handoff.json",
      reason: null,
      confidence: "high",
      catalog_product_id: 1,
      source_url_id: null,
    },
    {
      action: "updated",
      status: "needs_review",
      source_name: "public",
      source_domain: "public.gr",
      catalog_source: "sourceCata",
      model: "005606",
      mpn: "MD-20L",
      url: "https://www.public.gr/product/midea-md-20l",
      evidence_source: "product_factory_handoff",
      evidence_detail: "capture artifact included",
      reason: "needs_review",
      confidence: "medium",
      catalog_product_id: 1,
      source_url_id: 104,
    },
  ],
  truncated: false,
};

export const productFactoryHandoffImportApply = {
  ...productFactoryHandoffImportPreview,
  mode: "apply",
  applied: true,
  apply: true,
  changed_source_urls: [
    {
      action: "created",
      changed_fields: [],
      source_url: sourceUrlsForCatalogProduct.items[2],
    },
  ],
};

export const sourceUrlAgentRuns = {
  items: [
    {
      run_id: "source-run-001",
      source: "all",
      mode: "catalog",
      status: "succeeded",
      selected_count: 2,
      candidate_count: 6,
      matched_count: 5,
      needs_review_count: 6,
      not_found_count: 0,
      error_count: 0,
      dry_run: true,
      apply_high_confidence: false,
      missing_only: true,
      active_only: true,
      limit: 20,
      rate_limit_seconds: 2,
      created_at: "2026-05-02T09:55:00Z",
      started_at: "2026-05-02T10:00:00Z",
      completed_at: "2026-05-02T10:30:00Z",
      artifacts: [
        {
          name: "source-url-agent-summary.json",
          path: "source-url-agent/source-run-001/summary.json",
          download_url: "/api/artifacts/source-url-agent/source-run-001/summary.json",
          read_url: "/api/artifacts/source-url-agent/source-run-001/summary.json/read",
          is_allowed: true,
          can_read: true,
          can_download: true,
        },
      ],
    },
  ],
};

export const sourceUrlAgentReadinessReady = {
  status: "ready",
  providers: [
    {
      provider_name: "brave_search",
      provider_type: "brave",
      enabled: true,
      configured: true,
      required_env_keys: ["BRAVE_SEARCH_API_KEY"],
      missing_env_keys: [],
      allow_high_confidence_auto_apply: false,
      notes: "Brave Web Search API provider.",
    },
  ],
  default_provider_order: ["brave_search"],
  source_cascades: {},
  warnings: [],
  blocking_reasons: [],
};

export const sourceUrlAgentReadinessWarning = {
  ...sourceUrlAgentReadinessReady,
  status: "warning",
  warnings: ["Unsupported Source URL Agent search provider type for custom_search: custom."],
};

export const sourceUrlAgentReadinessBlocked = {
  status: "blocked",
  providers: [
    {
      provider_name: "brave_search",
      provider_type: "brave",
      enabled: true,
      configured: false,
      required_env_keys: ["BRAVE_SEARCH_API_KEY"],
      missing_env_keys: ["BRAVE_SEARCH_API_KEY"],
      allow_high_confidence_auto_apply: false,
      notes: "Brave Web Search API provider.",
    },
  ],
  default_provider_order: ["brave_search"],
  source_cascades: {},
  warnings: [],
  blocking_reasons: ["BRAVE_SEARCH_API_KEY is missing."],
};

export const sourceUrlAgentRunDetail = {
  run: {
    ...sourceUrlAgentRuns.items[0],
    status: "succeeded",
    summary: {
      selected_count: 2,
      candidate_count: 6,
      matched_count: 5,
      needs_review_count: 6,
      not_found_count: 0,
      error_count: 0,
    },
  },
};

export const sourceUrlAgentArtifacts = {
  root: "source-url-agent",
  run_id: "source-run-001",
  items: [
    {
      name: "summary.json",
      path: "source-url-agent/source-run-001/summary.json",
      download_url: "/api/artifacts/source-url-agent/source-run-001/summary.json",
      read_url: "/api/artifacts/source-url-agent/source-run-001/summary.json/read",
      is_allowed: true,
      can_read: true,
      can_download: true,
    },
    {
      name: "candidates.csv",
      path: "source-url-agent/source-run-001/candidates.csv",
      download_url: "/api/artifacts/source-url-agent/source-run-001/candidates.csv",
      read_url: "/api/artifacts/source-url-agent/source-run-001/candidates.csv/read",
      is_allowed: true,
      can_read: true,
      can_download: true,
    },
  ],
};

export const vendorSourceCaptureRuns = {
  items: [
    {
      run_id: "capture-run-001",
      source_filter: "electronet",
      observation_batch_id: "batch-capture-001",
      status: "succeeded",
      selected_source_url_count: 3,
      succeeded_count: 2,
      failed_count: 1,
      skipped_count: 0,
      limit: 50,
      include_not_due: false,
      refresh_after_minutes: 1440,
      catalog_product_ids: [],
      started_at: "2026-05-03T08:00:00Z",
      completed_at: "2026-05-03T08:03:00Z",
      created_at: "2026-05-03T07:59:00Z",
      output_dir: "vendor-source-captures/capture-run-001",
      artifacts: [
        {
          name: "summary.json",
          path: "vendor-source-captures/capture-run-001/summary.json",
          download_url: "/api/artifacts/vendor-source-captures/capture-run-001/summary.json",
          read_url: "/api/artifacts/vendor-source-captures/capture-run-001/summary.json/read",
          is_allowed: true,
          can_read: true,
          can_download: true,
        },
      ],
      summary: {
        selected_source_url_count: 3,
        succeeded_count: 2,
        failed_count: 1,
        skipped_count: 0,
      },
    },
  ],
};

export const createVendorSourceCaptureRunResponse = {
  run: {
    run_id: "capture-run-002",
    source_filter: "electronet",
    observation_batch_id: "batch-capture-002",
    status: "queued",
    selected_source_url_count: 0,
    succeeded_count: 0,
    failed_count: 0,
    skipped_count: 0,
    limit: 50,
    include_not_due: false,
    refresh_after_minutes: 1440,
    catalog_product_ids: [],
    created_at: "2026-05-03T09:00:00Z",
  },
};

export const vendorSourceCaptureRunDetail = {
  run: {
    ...vendorSourceCaptureRuns.items[0],
    warnings: [],
  },
};

export const vendorSourceCaptureArtifacts = {
  root: "vendor-source-captures",
  run_id: "capture-run-001",
  observation_batch_id: "batch-capture-001",
  items: [
    {
      name: "summary.json",
      path: "vendor-source-captures/capture-run-001/summary.json",
      download_url: "/api/artifacts/vendor-source-captures/capture-run-001/summary.json",
      read_url: "/api/artifacts/vendor-source-captures/capture-run-001/summary.json/read",
      is_allowed: true,
      can_read: true,
      can_download: true,
    },
    {
      name: "captures.jsonl",
      path: "vendor-source-captures/capture-run-001/captures.jsonl",
      download_url: "/api/artifacts/vendor-source-captures/capture-run-001/captures.jsonl",
      read_url: "/api/artifacts/vendor-source-captures/capture-run-001/captures.jsonl/read",
      is_allowed: true,
      can_read: true,
      can_download: true,
    },
  ],
};

export const vendorSourceCapabilities = {
  items: [
    {
      source_name: "skroutz",
      source_domain: "skroutz.gr",
      source_type: "marketplace",
      discovery_enabled: true,
      capture_enabled: false,
      capture_implemented: false,
      supports_search: true,
      supports_direct_product_url: true,
      supports_xhr_capture: false,
      expected_listing_field: "url",
      notes: "Marketplace monitoring source.",
    },
    {
      source_name: "bestprice",
      source_domain: "bestprice.gr",
      source_type: "marketplace",
      discovery_enabled: true,
      capture_enabled: false,
      capture_implemented: false,
      supports_search: true,
      supports_direct_product_url: true,
      supports_xhr_capture: false,
      expected_listing_field: "url",
      notes: "Marketplace monitoring source.",
    },
    {
      source_name: "electronet",
      source_domain: "electronet.gr",
      source_type: "direct_vendor",
      discovery_enabled: true,
      capture_enabled: true,
      capture_implemented: true,
      supports_search: true,
      supports_direct_product_url: true,
      supports_xhr_capture: true,
      expected_listing_field: "product_url",
      notes: "First direct-vendor discovery test case.",
    },
    {
      source_name: "plaisio",
      source_domain: "plaisio.gr",
      source_type: "direct_vendor",
      discovery_enabled: true,
      capture_enabled: false,
      capture_implemented: false,
      supports_search: true,
      supports_direct_product_url: true,
      supports_xhr_capture: false,
      expected_listing_field: "product_url",
      notes: "Discovery-only source.",
    },
    {
      source_name: "public",
      source_domain: "public.gr",
      source_type: "direct_vendor",
      discovery_enabled: true,
      capture_enabled: false,
      capture_implemented: false,
      supports_search: true,
      supports_direct_product_url: true,
      supports_xhr_capture: false,
      expected_listing_field: "product_url",
      notes: "Discovery-only source.",
    },
    {
      source_name: "kotsovolos",
      source_domain: "kotsovolos.gr",
      source_type: "direct_vendor",
      discovery_enabled: true,
      capture_enabled: false,
      capture_implemented: false,
      supports_search: true,
      supports_direct_product_url: true,
      supports_xhr_capture: false,
      expected_listing_field: "product_url",
      notes: "Discovery-only source.",
    },
  ],
};

export const sourceUrlCandidates = {
  items: [
    {
      id: 501,
      run_id: "source-run-001",
      catalog_product_id: 1,
      model: "005606",
      mpn: "MD-20L",
      manufacturer: "Midea",
      product_name: "Midea Αφυγραντήρας 20L",
      category: "Αφυγραντήρες",
      own_price: 199.9,
      source_name: "skroutz",
      source_domain: "skroutz.gr",
      source_type: "marketplace",
      expected_listing: true,
      candidate_url: "https://www.skroutz.gr/s/999/midea-md-20l-candidate.html",
      canonical_url: "https://www.skroutz.gr/s/999/midea-md-20l-candidate.html",
      candidate_title: "Midea MD-20L Αφυγραντήρας 20L",
      candidate_price: 189.9,
      match_status: "strong_match",
      confidence_score: 0.9823,
      match_method: "mpn_model_title",
      evidence_json: {
        mpn_evidence: { expected: "MD-20L", found: true },
        model_evidence: { expected: "005606", found: true },
        brand_evidence: { expected: "Midea", found: true },
        category_evidence: { expected: "Αφυγραντήρες", found: true },
        price_evidence: { own_price: 199.9, candidate_price: 189.9 },
        title_similarity: 0.94,
        title_only: false,
      },
      competing_candidates_count: 2,
      searched_queries_json: ["Midea MD-20L", "005606 Midea"],
      status: "needs_review",
      reviewed_by: null,
      reviewed_at: null,
      notes: "High confidence candidate.",
      created_at: "2026-05-02T10:00:00Z",
      updated_at: "2026-05-02T10:00:00Z",
    },
    {
      id: 502,
      run_id: "source-run-001",
      catalog_product_id: 2,
      model: "AB-123",
      mpn: null,
      manufacturer: "ΓΕΡΜΑΝΟΣ",
      product_name: "Σετ πληκτρολόγιο και ποντίκι",
      category: "Πληκτρολόγια",
      own_price: 39.9,
      source_name: "bestprice",
      source_domain: "bestprice.gr",
      candidate_url: "https://www.bestprice.gr/item/999/keyboard-mouse.html",
      candidate_title: "Keyboard mouse bundle",
      candidate_price: 38.9,
      match_status: "weak_match",
      confidence_score: 0.6211,
      match_method: "title_only",
      evidence_json: {
        title_similarity: 0.52,
        title_only: true,
        error_code: null,
      },
      searched_queries_json: ["AB-123 keyboard"],
      status: "needs_review",
      created_at: "2026-05-02T10:20:00Z",
    },
    {
      id: 503,
      run_id: "source-run-001",
      catalog_product_id: 1,
      model: "005606",
      mpn: "MD-20L",
      manufacturer: "Midea",
      product_name: "Midea Ξ‘Ο†Ο…Ξ³ΟΞ±Ξ½Ο„Ξ®ΟΞ±Ο‚ 20L",
      category: "Ξ‘Ο†Ο…Ξ³ΟΞ±Ξ½Ο„Ξ®ΟΞµΟ‚",
      own_price: 199.9,
      source_name: "electronet",
      source_domain: "electronet.gr",
      source_type: "direct_vendor",
      expected_listing: true,
      candidate_url: "https://www.electronet.gr/midea-md-20l",
      candidate_title: "Midea MD-20L Electronet",
      candidate_price: 198.9,
      match_status: "strong_match",
      confidence_score: 0.9123,
      match_method: "mpn_model_title",
      evidence_json: { registry_source: "electronet", title_similarity: 0.91 },
      searched_queries_json: ["electronet Midea MD-20L"],
      status: "needs_review",
      created_at: "2026-05-02T10:30:00Z",
    },
    {
      id: 504,
      run_id: "source-run-001",
      catalog_product_id: 1,
      model: "005606",
      mpn: "MD-20L",
      manufacturer: "Midea",
      product_name: "Midea Ξ‘Ο†Ο…Ξ³ΟΞ±Ξ½Ο„Ξ®ΟΞ±Ο‚ 20L",
      source_name: "public",
      source_domain: "public.gr",
      source_type: "direct_vendor",
      candidate_url: "https://www.public.gr/product/midea-md-20l",
      candidate_title: "Midea MD-20L Public",
      candidate_price: 201.9,
      match_status: "strong_match",
      confidence_score: 0.9023,
      match_method: "mpn_model_title",
      evidence_json: { registry_source: "public", title_similarity: 0.9 },
      searched_queries_json: ["public Midea MD-20L"],
      status: "needs_review",
      created_at: "2026-05-02T10:40:00Z",
    },
    {
      id: 505,
      run_id: "source-run-001",
      catalog_product_id: 1,
      model: "005606",
      mpn: "MD-20L",
      manufacturer: "Midea",
      product_name: "Midea Ξ‘Ο†Ο…Ξ³ΟΞ±Ξ½Ο„Ξ®ΟΞ±Ο‚ 20L",
      source_name: "plaisio",
      source_domain: "plaisio.gr",
      source_type: "direct_vendor",
      candidate_url: "https://www.plaisio.gr/midea-md-20l",
      candidate_title: "Midea MD-20L Plaisio",
      candidate_price: 202.9,
      match_status: "possible_match",
      confidence_score: 0.7723,
      match_method: "model_title",
      evidence_json: { registry_source: "plaisio", title_similarity: 0.77 },
      searched_queries_json: ["plaisio Midea MD-20L"],
      status: "needs_review",
      created_at: "2026-05-02T10:50:00Z",
    },
    {
      id: 506,
      run_id: "source-run-001",
      catalog_product_id: 1,
      model: "005606",
      mpn: "MD-20L",
      manufacturer: "Midea",
      product_name: "Midea Ξ‘Ο†Ο…Ξ³ΟΞ±Ξ½Ο„Ξ®ΟΞ±Ο‚ 20L",
      source_name: "kotsovolos",
      source_domain: "kotsovolos.gr",
      source_type: "direct_vendor",
      candidate_url: "https://www.kotsovolos.gr/midea-md-20l",
      candidate_title: "Midea MD-20L Kotsovolos",
      candidate_price: 205.9,
      match_status: "possible_match",
      confidence_score: 0.7023,
      match_method: "model_title",
      evidence_json: { registry_source: "kotsovolos", title_similarity: 0.7 },
      searched_queries_json: ["kotsovolos Midea MD-20L"],
      status: "needs_review",
      created_at: "2026-05-02T11:00:00Z",
    },
    {
      id: 507,
      run_id: "source-run-001",
      catalog_product_id: 2,
      model: "DV90DG52A0ABLE",
      mpn: "DV90DG52A0ABLE",
      manufacturer: "Samsung",
      product_name: "Samsung DV90DG52A0ABLE Dryer",
      source_name: "bestprice",
      source_domain: "bestprice.gr",
      source_type: "marketplace",
      candidate_url: "https://www.bestprice.gr/item/998/samsung-dv90dg52a0able.html",
      candidate_title: "Samsung DV90DG52A0ABLE Dryer",
      candidate_price: 620,
      match_status: "strong_match",
      confidence_score: 1,
      match_method: "mpn_model_title",
      evidence_json: { title_similarity: 1, title_only: false },
      searched_queries_json: ["Samsung DV90DG52A0ABLE"],
      status: "pending",
      created_at: "2026-05-02T11:10:00Z",
    },
  ],
  total: 7,
  limit: 50,
  offset: 0,
};

export const skroutzNetworkDiagnosticSummary = {
  source_url_id: 101,
  vendor_slug: "skroutz",
  source_url: "https://www.skroutz.gr/s/123/midea-md-20l.html",
  status: "success",
  captured_response_count: 3,
  derived_endpoints: {
    filter_products: "https://www.skroutz.gr/s/123/filter_products.json",
    shops_details: "https://www.skroutz.gr/s/123/shops_details.json",
  },
  derived_filter_products_url: "https://www.skroutz.gr/s/123/filter_products.json",
  derived_shops_details_url: "https://www.skroutz.gr/s/123/shops_details.json",
  observed_derived_endpoints: { filter_products: true, shops_details: false },
  observed_filter_products_url: true,
  observed_shops_details_url: false,
  exact_match_count: 1,
  best_product_data_endpoint: "https://www.skroutz.gr/s/123/filter_products.json",
  product_data_candidate_url: "https://www.skroutz.gr/s/123/filter_products.json",
  product_data_candidate_reason: "PRIMARY_CANDIDATE_PRODUCT_OFFERS: exact derived filter_products endpoint observed",
  classifications_summary: {
    PRIMARY_CANDIDATE_PRODUCT_OFFERS: 1,
    BLOCKED_OR_CHALLENGE: 1,
    OTHER_JSON: 1,
  },
  blocked_or_challenge_detected: true,
  diagnostic_report_id: 90001,
  created_at: "2026-05-07T12:00:00Z",
};

export const skroutzNetworkDiagnosticReport = {
  ...skroutzNetworkDiagnosticSummary,
  summary: skroutzNetworkDiagnosticSummary,
  started_at: "2026-05-07T11:59:00Z",
  completed_at: "2026-05-07T12:00:00Z",
  captured_responses: [
    {
      method: "GET",
      url: "https://www.skroutz.gr/s/123/filter_products.json",
      status: 200,
      resource_type: "xhr",
      content_type: "application/json",
      body_size: 512,
      parsed_json_valid: true,
      json_summary: {
        top_level_type: "object",
        top_level_keys: ["product_cards", "pagination"],
        top_level_key_count: 2,
        has_product_cards: true,
        product_cards_count: 2,
      },
      classification: "PRIMARY_CANDIDATE_PRODUCT_OFFERS",
      matched_derived_endpoint: "filter_products",
      body_sample: "{\"product_cards\":[{\"price\":189.9}]}",
    },
    {
      method: "GET",
      url: "https://www.skroutz.gr/challenge",
      status: 403,
      resource_type: "fetch",
      content_type: "text/html",
      body_size: 300,
      parsed_json_valid: false,
      json_summary: { top_level_type: "none", top_level_keys: [], top_level_key_count: 0 },
      classification: "BLOCKED_OR_CHALLENGE",
      matched_derived_endpoint: null,
      body_sample: "<html>captcha challenge</html>",
      json_parse_error: "JSONDecodeError",
    },
  ],
};

export const productSourceUrlCandidateHistory = {
  catalog_product_id: 1,
  total_candidates: 4,
  warnings: [],
  items: [
    {
      run_id: "source-run-002",
      run: {
        run_id: "source-run-002",
        source: "bestprice",
        source_name: "bestprice",
        mode: "catalog",
        status: "succeeded",
        created_at: "2026-05-03T09:55:00Z",
        started_at: "2026-05-03T10:00:00Z",
        completed_at: "2026-05-03T10:08:00Z",
      },
      counts: {
        accepted: 1,
        needs_review: 1,
        pending: 0,
        rejected: 0,
        not_found: 0,
        error: 0,
      },
      candidates: [
        {
          ...sourceUrlCandidates.items[0],
          id: 601,
          run_id: "source-run-002",
          status: "accepted",
          reviewed_by: "operator",
          reviewed_at: "2026-05-03T10:10:00Z",
          notes: "Accepted from latest run.",
          created_at: "2026-05-03T10:05:00Z",
          updated_at: "2026-05-03T10:10:00Z",
        },
        {
          ...sourceUrlCandidates.items[2],
          id: 602,
          run_id: "source-run-002",
          status: "needs_review",
          created_at: "2026-05-03T10:06:00Z",
        },
      ],
    },
    {
      run_id: "source-run-001",
      run: sourceUrlAgentRuns.items[0],
      counts: {
        accepted: 0,
        needs_review: 2,
        pending: 0,
        rejected: 0,
        not_found: 0,
        error: 0,
      },
      candidates: [sourceUrlCandidates.items[0], sourceUrlCandidates.items[2]],
    },
  ],
};

export const emptyProductSourceUrlCandidateHistory = {
  catalog_product_id: 2,
  total_candidates: 0,
  warnings: [],
  items: [],
};

export const sourceUrlCandidateReviewLayout = {
  user_key: "default",
  columns: [
    { key: "status", label: "Status", visible: true, table_column_visible: true, width_px: 56, order: 0 },
    { key: "confidence_score", label: "Confidence", visible: true, table_column_visible: true, width_px: 32, order: 1 },
    { key: "model", label: "Model", visible: false, table_column_visible: false, width_px: 28, order: 2 },
    { key: "mpn", label: "MPN", visible: true, table_column_visible: true, width_px: 48, order: 3 },
    { key: "manufacturer", label: "Brand", visible: true, table_column_visible: true, width_px: 32, order: 4 },
    { key: "source_name", label: "Source", visible: true, table_column_visible: true, width_px: 32, order: 5 },
    { key: "candidate_price", label: "Source price", visible: true, table_column_visible: true, width_px: 32, order: 6 },
    { key: "own_price", label: "Own price", visible: true, table_column_visible: true, width_px: 32, order: 7 },
    { key: "candidate_title", label: "Source title", visible: true, table_column_visible: true, width_px: 260, order: 8 },
  ],
  actions: { table_column_visible: false, replacement: "inline_review_panel" },
  review_panel: {
    mode: "inline_row",
    open_on: "row_single_click",
    review_actions: [
      { decision: "accept", label: "Accept", style: "primary" },
      { decision: "replace_url", label: "Replace URL", style: "secondary", requires_url: true },
      { decision: "reject", label: "Reject", style: "danger" },
    ],
  },
};

export const catalogProductsEmptyImportWarning = {
  items: [],
  page: 1,
  page_size: 100,
  total: 0,
  filtered_total: 0,
  warning: "Active catalog is empty. Run python -m ecommerce.jobs.ingest_catalog.",
};

export const catalogDbImportRequiredError = {
  status: 503,
  body: {
    detail: "Catalog database/import required. Configure PostgreSQL, run migrations, and import sourceCata.csv.",
    code: "catalog_database_import_required",
    required_for: ["catalog"],
    ready_for_catalog: false,
    configured: true,
    reachable: true,
    required_tables_present: true,
    alembic_up_to_date: true,
    active_catalog_empty: true,
    blocking_reasons: ["Active catalog is empty. Run python -m ecommerce.jobs.ingest_catalog."],
    non_catalog_workflows_available: true,
    setup_hints: [
      "Set ECOMMERCE_DATABASE_URL.",
      "Run alembic upgrade head.",
      "Run python -m ecommerce.jobs.ingest_catalog.",
    ],
  },
};

export const dbStatusAvailable = {
  configured: true,
  reachable: true,
  price_monitoring_requires_database: true,
  ready_for_price_monitoring: true,
  blocking_reasons: [],
  non_db_workflows_available: true,
  required_for: ["price-monitoring", "price-monitoring-alerts", "price-monitoring-history"],
  error: null,
  dialect: "postgresql",
  required_tables_present: true,
  alembic_up_to_date: true,
  alembic_current_revision: "202605020001",
  alembic_head_revision: "202605020001",
  setup_hints: [],
};

export const dbStatusNotConfigured = {
  configured: false,
  reachable: false,
  price_monitoring_requires_database: true,
  ready_for_price_monitoring: false,
  blocking_reasons: ["ECOMMERCE_DATABASE_URL is not configured."],
  non_db_workflows_available: true,
  required_for: ["price-monitoring", "price-monitoring-alerts", "price-monitoring-history"],
  dialect: null,
  error: "database URL is not configured",
  required_tables_present: null,
  alembic_up_to_date: null,
  setup_hints: ["Set ECOMMERCE_DATABASE_URL.", "Run alembic upgrade head.", "Restart ecommerce-api."],
};

export const dbStatusUnavailable = {
  configured: true,
  reachable: false,
  price_monitoring_requires_database: true,
  ready_for_price_monitoring: false,
  blocking_reasons: ["PostgreSQL is configured but not reachable."],
  non_db_workflows_available: true,
  required_for: ["price-monitoring", "price-monitoring-alerts", "price-monitoring-history"],
  dialect: "postgresql",
  error: "connection refused",
  required_tables_present: null,
  alembic_up_to_date: null,
  setup_hints: ["Start PostgreSQL.", "Run alembic upgrade head."],
};

export const dbStatusMigrationMissing = {
  configured: true,
  reachable: true,
  price_monitoring_requires_database: true,
  ready_for_price_monitoring: false,
  blocking_reasons: ["Required Price Monitoring tables are missing.", "Alembic migrations are not up to date."],
  non_db_workflows_available: true,
  required_for: ["price-monitoring", "price-monitoring-alerts", "price-monitoring-history"],
  dialect: "postgresql",
  error: null,
  required_tables_present: false,
  alembic_up_to_date: false,
  alembic_current_revision: "202604010001",
  alembic_head_revision: "202605020001",
  setup_hints: ["Run alembic upgrade head."],
};

export const priceMonitoringExecutions = [
  {
    run_id: "pm-run-001",
    execution_id: "exec-running",
    status: "running",
    source: "skroutz",
    fetch_input_mode: "source_urls",
    queued_at: "2026-05-02T09:00:00Z",
    started_at: "2026-05-02T09:01:00Z",
    queue_position: 1,
    process_id: 4242,
    catalog_url: null,
  },
  {
    run_id: "pm-run-001",
    execution_id: "exec-success",
    status: "fetch_completed",
    source: "skroutz",
    fetch_input_mode: "source_urls",
    queued_at: "2026-05-02T08:00:00Z",
    started_at: "2026-05-02T08:01:00Z",
    completed_at: "2026-05-02T08:10:00Z",
    exit_code: 0,
    input_csv_path: {
      name: "input.csv",
      path: "price-monitoring/pm-run-001/input.csv",
      download_url: "/api/artifacts/price-monitoring/pm-run-001/input.csv",
      read_url: "/api/artifacts/price-monitoring/pm-run-001/input.csv/read",
      is_allowed: true,
      can_read: true,
      can_download: true,
    },
    enriched_csv_path: "price-monitoring/pm-run-001/enriched.csv",
    fetch_result_path: "price-monitoring/pm-run-001/fetch-result.json",
    log_path: "price-monitoring/pm-run-001/fetch.log",
    artifacts: [
      {
        name: "enriched.csv",
        path: "price-monitoring/pm-run-001/enriched.csv",
        download_url: "/api/artifacts/price-monitoring/pm-run-001/enriched.csv",
        read_url: "/api/artifacts/price-monitoring/pm-run-001/enriched.csv/read",
        is_allowed: true,
        can_read: true,
        can_download: true,
        warning: null,
      },
    ],
    observation_count: 2,
    appended_observation_count: 2,
    prior_observation_count: 1,
    catalog_snapshot_count: 2,
    matched_observation_count: 1,
    unmatched_observation_count: 1,
    was_refetch: true,
    fetch_attempt: 2,
    observation_batch_id: "exec-success",
    observation_history_count: 3,
    stale: false,
    queue_position: null,
  },
  {
    run_id: "pm-run-001",
    execution_id: "exec-failed",
    status: "failed",
    source: "bestprice",
    queued_at: "2026-05-02T07:00:00Z",
    started_at: "2026-05-02T07:01:00Z",
    completed_at: "2026-05-02T07:03:00Z",
    exit_code: 1,
    artifacts_are_diagnostic: true,
    artifact_warning: "Failure artifacts are diagnostic only.",
  },
  {
    run_id: "pm-run-001",
    execution_id: "exec-cancelled",
    status: "cancelled",
    source: "skroutz",
    queued_at: "2026-05-02T06:00:00Z",
    cancelled_at: "2026-05-02T06:02:00Z",
    cancel_reason: "operator cancelled",
  },
  {
    run_id: "pm-run-001",
    execution_id: "exec-killed",
    status: "killed",
    source: "skroutz",
    queued_at: "2026-05-02T05:00:00Z",
    started_at: "2026-05-02T05:01:00Z",
    killed_at: "2026-05-02T05:05:00Z",
    killed_reason: "timeout",
    termination_mode: "kill",
    exit_code: 137,
  },
];

export const priceMonitoringRunItems = [
    {
      run_id: "pm-run-001",
      status: "created",
      source: "skroutz",
      selected_count: 1,
      skipped_count: 1,
      skipped_by_reason: { missing_active_source_url: 1 },
      source_url_coverage: sourceUrlCoverage,
      created_at: "2026-05-02T08:00:00Z",
      latest_fetch: priceMonitoringExecutions[1],
    },
    {
      run_id: "pm-run-queued",
      status: "queued",
      source: "bestprice",
      selected_count: 1,
      skipped_count: 0,
      source_url_coverage: {
        ...sourceUrlCoverage,
        source: "bestprice",
        selected_count: 1,
        products_with_active_source_urls: 1,
        products_without_active_source_urls: 0,
        coverage_percent: 100,
        missing_source_url_models: [],
        missing_source_url_catalog_product_ids: [],
        warning: null,
      },
      created_at: "2026-05-02T09:00:00Z",
      latest_fetch: {
        run_id: "pm-run-queued",
        execution_id: "exec-queued",
        status: "queued",
        source: "bestprice",
        queued_at: "2026-05-02T09:05:00Z",
      },
    },
  ];

export const priceMonitoringRuns = {
  items: priceMonitoringRunItems,
  runs: priceMonitoringRunItems,
};

export const priceMonitoringRunDetail = {
  run_id: "pm-run-001",
  status: "created",
  source: "skroutz",
  selected_count: 1,
  skipped_count: 1,
  skipped_by_reason: { missing_active_source_url: 1 },
  source_url_coverage: sourceUrlCoverage,
  created_at: "2026-05-02T08:00:00Z",
  latest_fetch: priceMonitoringExecutions[1],
  db: {
    persisted: true,
    reachable: true,
  },
};

export const priceMonitoringSelectionResult = {
  run_id: "pm-run-001",
  status: "selection_created",
  source: "electronet",
  output_dir: "price-monitoring/pm-run-001",
  input_csv_path: "price-monitoring/pm-run-001/input.csv",
  selection_summary_path: "price-monitoring/pm-run-001/selection-summary.json",
  selected_count: 1,
  skipped_count: 1,
  skipped_by_reason: { missing_active_source_url: 1 },
  source_url_coverage: { ...sourceUrlCoverage, source: "electronet" },
  selected_items: [
    {
      ...catalogProducts.items[0],
      source_url_coverage: {
        source: "electronet",
        has_active_source_url: true,
        active_source_url_count: 1,
        status_counts: { active: 1, needs_review: 1, broken: 0, disabled: 0, redirected: 0 },
        active_source_urls: [sourceUrlsForCatalogProduct.items[2]],
      },
    },
  ],
  skipped_items: [
    {
      ...catalogProducts.items[1],
      skip_reason: "missing_active_source_url",
      source_url_coverage: {
        source: "electronet",
        has_active_source_url: false,
        active_source_url_count: 0,
        status_counts: { active: 0, needs_review: 0, broken: 0, disabled: 0, redirected: 0 },
        active_source_urls: [],
        warning: "No active source URLs for this product.",
      },
    },
  ],
};

(priceMonitoringSelectionResult as { items?: unknown }).items = priceMonitoringSelectionResult.selected_items;

export const priceMonitoringMissingSourceUrlSelectionResult = {
  ...priceMonitoringSelectionResult,
  run_id: null,
  status: "selection_blocked",
  selected_count: 0,
  skipped_count: 1,
  selected_items: [],
  selected: [],
  items: [],
  skipped_items: [
    {
      ...catalogProducts.items[1],
      skip_reason: "missing_active_source_url",
      source_url_coverage: {
        source: "skroutz",
        has_active_source_url: false,
        active_source_url_count: 0,
        status_counts: { active: 0, needs_review: 0, broken: 0, disabled: 0, redirected: 0 },
        active_source_urls: [],
      },
    },
  ],
};

export const priceMonitoringMissingSourceUrlError = {
  status: 400,
  body: {
    detail: "missing_active_source_url",
    code: "missing_active_source_url",
    source: "electronet",
    skipped_by_reason: { missing_active_source_url: 1 },
  },
};

export const priceMonitoringRunObservations = {
  run_id: "pm-run-001",
  items: [
    {
      id: 301,
      product_id: 1,
      product_source_id: 1001,
      source_capture_snapshot_id: 9001,
      run_id: "pm-run-001",
      execution_id: "exec-success",
      fetch_attempt: 2,
      was_refetch: true,
      observation_batch_id: "exec-success",
      catalog_source: "sourceCata",
      source: "skroutz",
      model: "005606",
      mpn: "MD-20L",
      product_name: "Midea Αφυγραντήρας 20L",
      competitor_name: "Mock Store",
      competitor_price: 189.9,
      own_price: 199.9,
      price_delta: -10,
      price_delta_percent: -5,
      currency: "EUR",
      availability: "available",
      product_url: "https://www.skroutz.gr/s/123/midea-md-20l.html",
      matched_by: "model",
      match_status: "matched",
      is_matched: true,
      observed_at: "2026-05-02T08:09:00Z",
      created_at: "2026-05-02T08:10:00Z",
      raw_observation: { persistence: { fetch_attempt: 2, was_refetch: true, execution_id: "exec-success" } },
    },
    {
      id: 300,
      product_id: 1,
      run_id: "pm-run-001",
      execution_id: "exec-old",
      fetch_attempt: 1,
      was_refetch: false,
      observation_batch_id: "exec-old",
      catalog_source: "sourceCata",
      source: "skroutz",
      model: "005606",
      mpn: "MD-20L",
      product_name: "Midea Αφυγραντήρας 20L",
      competitor_name: "Older Store",
      competitor_price: 199.9,
      own_price: 199.9,
      price_delta: 0,
      price_delta_percent: 0,
      currency: "EUR",
      availability: "available",
      product_url: "https://www.skroutz.gr/s/old/midea-md-20l.html",
      matched_by: "model",
      match_status: "matched",
      is_matched: true,
      observed_at: "2026-05-02T07:09:00Z",
      created_at: "2026-05-02T07:10:00Z",
      raw_observation: { persistence: { fetch_attempt: 1, was_refetch: false, execution_id: "exec-old" } },
    },
  ],
  count: 2,
  matched_count: 2,
  unmatched_count: 0,
};

export const priceMonitoringFetchLogs = {
  run_id: "pm-run-001",
  execution_id: "exec-success",
  lines: ["fetch started", "matched model 005606", "fetch completed"],
  logs: ["fetch started", "matched model 005606", "fetch completed"],
};

export const priceMonitoringReview = {
  run_id: "pm-run-001",
  items: [
    {
      model: "005606",
      mpn: "MD-20L",
      name: "Midea Αφυγραντήρας 20L",
      source: "skroutz",
      current_price: 199.9,
      competitor_store: "Mock Store",
      competitor_price: 189.9,
      price_delta: -10,
      price_delta_percent: -5,
      recommended_action: "match_price",
      selected_action: "",
      warnings: ["Competitor below own price"],
    },
  ],
  summary: { match_price: 1, undercut: 0, ignore: 0 },
  review_csv_path: {
    name: "review.csv",
    path: "price-monitoring/pm-run-001/review.csv",
    download_url: "/api/artifacts/price-monitoring/pm-run-001/review.csv",
    read_url: "/api/artifacts/price-monitoring/pm-run-001/review.csv/read",
    is_allowed: true,
    can_read: true,
    can_download: true,
  },
  enriched_csv_path: "price-monitoring/pm-run-001/enriched.csv",
};

export const priceMonitoringArtifacts = {
  root: "price-monitoring",
  run_id: "pm-run-001",
  items: [
    {
      name: "enriched.csv",
      path: "price-monitoring/pm-run-001/enriched.csv",
      download_url: "/api/artifacts/price-monitoring/pm-run-001/enriched.csv",
      read_url: "/api/artifacts/price-monitoring/pm-run-001/enriched.csv/read",
      is_allowed: true,
      can_read: true,
      can_download: true,
      warning: null,
    },
    {
      name: "secret.env",
      path: "C:/outside/secret.env",
      download_url: null,
      read_url: null,
      is_allowed: false,
      can_read: false,
      can_download: false,
      warning: "Path is outside configured artifact roots.",
    },
  ],
};

export const pathRoots = {
  artifact_roots: {
    roots: [
      {
        path: "D:/mock/artifacts",
        exists: true,
        name: "mock-artifacts",
        source: "fixture",
        is_default: true,
        is_configured: true,
      },
    ],
  },
  file_roots: { roots: [] },
  output_roots: { roots: [] },
  env: { ECOMMERCE_ARTIFACT_ROOTS: "D:/mock/artifacts" },
  path_separator: "\\",
  platform: "Windows",
};

export const alertRules = {
  items: [
    {
      id: 101,
      name: "005606 below own price",
      rule_type: "competitor_below_own_price",
      product_id: null,
      catalog_source: "sourceCata",
      model: "005606",
      mpn: "MD-20L",
      threshold_amount: 1,
      threshold_percent: 3,
      active: true,
      created_at: "2026-05-02T08:00:00Z",
      updated_at: "2026-05-02T08:00:00Z",
    },
  ],
  count: 1,
  limit: 100,
  offset: 0,
};

export const alertEvents = {
  items: [
    {
      id: 201,
      alert_rule_id: 101,
      monitoring_run_id: "pm-run-001",
      run_id: "pm-run-001",
      product_id: 5606,
      catalog_source: "sourceCata",
      model: "005606",
      mpn: "MD-20L",
      source: "skroutz",
      competitor_name: "Mock Store",
      own_price: 199.9,
      competitor_price: 189.9,
      price_delta: -10,
      price_delta_percent: -5,
      severity: "warning",
      status: "open",
      message: "Competitor price is below own price",
      triggered_at: "2026-05-02T08:11:00Z",
    },
    {
      id: 202,
      alert_rule_id: 101,
      monitoring_run_id: "pm-run-001",
      run_id: "pm-run-001",
      model: "AB-123",
      source: "bestprice",
      competitor_name: "Another Store",
      own_price: 39.9,
      competitor_price: 38.9,
      price_delta: -1,
      price_delta_percent: -2.5,
      severity: "info",
      status: "acknowledged",
      message: "Acknowledged fixture event",
      triggered_at: "2026-05-02T08:12:00Z",
    },
  ],
  count: 2,
  limit: 100,
  offset: 0,
};

function alertEventsResponse(request: MockRequest) {
  const status = request.searchParams.get("status");
  if (!status || status === "all") {
    return alertEvents;
  }

  const items = alertEvents.items.filter((event) => event.status === status);
  return {
    items,
    count: status === "open" ? 1 : items.length,
    limit: Number(request.searchParams.get("limit") ?? 100),
    offset: Number(request.searchParams.get("offset") ?? 0),
  };
}

function createSourceUrlResponse(request: MockRequest) {
  const body = typeof request.body === "object" && request.body !== null && !Array.isArray(request.body)
    ? request.body as Record<string, unknown>
    : {};
  return {
    ...createdSourceUrl,
    url: typeof body.url === "string" && body.url.trim().length > 0 ? body.url : createdSourceUrl.url,
    url_normalized:
      typeof body.url === "string" && body.url.trim().length > 0 ? body.url.trim() : createdSourceUrl.url_normalized,
    source_name: typeof body.source_name === "string" ? body.source_name : createdSourceUrl.source_name,
    notes: typeof body.notes === "string" ? body.notes : createdSourceUrl.notes,
  };
}

function updateSourceUrlResponse(request: MockRequest) {
  const body = typeof request.body === "object" && request.body !== null && !Array.isArray(request.body)
    ? request.body as Record<string, unknown>
    : {};
  return {
    ...sourceUrlsForCatalogProduct.items[0],
    url: typeof body.url === "string" ? body.url : sourceUrlsForCatalogProduct.items[0].url,
    url_normalized:
      typeof body.url === "string" ? body.url.trim().replace(/#.*$/, "") : sourceUrlsForCatalogProduct.items[0].url_normalized,
    source_name:
      typeof body.source_name === "string" || body.source_name === null
        ? body.source_name
        : sourceUrlsForCatalogProduct.items[0].source_name,
    source_domain: typeof body.url === "string" && body.url.includes("public.gr") ? "public.gr" : sourceUrlsForCatalogProduct.items[0].source_domain,
    status: typeof body.status === "string" ? body.status : sourceUrlsForCatalogProduct.items[0].status,
    notes: typeof body.notes === "string" || body.notes === null ? body.notes : sourceUrlsForCatalogProduct.items[0].notes,
    updated_at: "2026-05-02T09:20:00Z",
  };
}

function promoteSourceUrlResponse() {
  return {
    ...sourceUrlsForCatalogProduct.items[1],
    status: "active",
    updated_at: "2026-05-02T09:25:00Z",
  };
}

function createSourceUrlAgentRunResponse(request: MockRequest) {
  const body =
    typeof request.body === "object" && request.body !== null && !Array.isArray(request.body)
      ? (request.body as Record<string, unknown>)
      : {};

  return {
    ...sourceUrlAgentRuns.items[0],
    run_id: "source-run-002",
    source: typeof body.source === "string" ? body.source : "all",
    mode: typeof body.mode === "string" ? body.mode : "catalog",
    dry_run: body.dry_run === false ? false : true,
    apply_high_confidence: body.apply_high_confidence === true,
    limit: typeof body.limit === "number" ? body.limit : 20,
    status: "queued",
    selected_count: Array.isArray(body.selected_models) ? body.selected_models.length : 0,
    candidate_count: 0,
    matched_count: 0,
    needs_review_count: 0,
    summary: {
      selected_count: Array.isArray(body.selected_models) ? body.selected_models.length : 0,
      candidate_count: 0,
      needs_review_count: 0,
    },
    created_at: "2026-05-02T12:00:00Z",
    started_at: null,
    completed_at: null,
  };
}

function sourceUrlCandidatesResponse(request: MockRequest) {
  const status = request.searchParams.get("status");
  const sourceName = request.searchParams.get("source_name");
  const runId = request.searchParams.get("run_id");
  const items = sourceUrlCandidates.items.filter((candidate) => {
    const matchesStatus = !status || candidate.status === status;
    const matchesSource =
      !sourceName || candidate.source_name.toLowerCase().includes(sourceName.toLowerCase());
    const matchesRun = !runId || candidate.run_id === runId;
    return matchesStatus && matchesSource && matchesRun;
  });

  return {
    items,
    total: items.length,
    limit: Number(request.searchParams.get("limit") ?? 50),
    offset: Number(request.searchParams.get("offset") ?? 0),
  };
}

function reviewSourceUrlCandidateResponse(request: MockRequest) {
  const body =
    typeof request.body === "object" && request.body !== null && !Array.isArray(request.body)
      ? (request.body as Record<string, unknown>)
      : {};
  const decision = typeof body.decision === "string" ? body.decision : "";
  if (!["accept", "reject", "replace_url"].includes(decision)) {
    return {
      status: 422,
      body: {
        detail: [
          {
            type: "literal_error",
            loc: ["body", "decision"],
            msg: "Input should be 'accept', 'reject' or 'replace_url'",
            input: decision,
          },
        ],
      },
    };
  }
  const status =
    decision === "accept"
      ? "accepted"
      : decision === "reject"
        ? "rejected"
        : "accepted";

  return {
    ...sourceUrlCandidates.items[0],
    candidate_url:
      decision === "replace_url" && typeof body.reviewed_url === "string"
        ? body.reviewed_url
        : sourceUrlCandidates.items[0].candidate_url,
    status,
    reviewed_by: body.reviewed_by ?? "operator",
    reviewed_at: "2026-05-02T11:00:00Z",
    notes:
      typeof body.review_notes === "string" ? body.review_notes : sourceUrlCandidates.items[0].notes,
    updated_at: "2026-05-02T11:00:00Z",
  };
}

export const commerceDbUnavailableError = {
  status: 503,
  body: {
    detail: "PostgreSQL is required for Price Monitoring.",
    status: dbStatusUnavailable,
    ready_for_price_monitoring: false,
    blocking_reasons: dbStatusUnavailable.blocking_reasons,
    non_db_workflows_available: true,
  },
};

export const commerceDbRequiredFixtureRoutes: MockRoute[] = [
  { method: "POST", path: "/commerce-api/price-monitoring/selection/preview", response: commerceDbUnavailableError },
  { method: "POST", path: "/commerce-api/price-monitoring/runs", response: commerceDbUnavailableError },
  { method: "GET", path: "/commerce-api/price-monitoring/runs", response: commerceDbUnavailableError },
  { method: "GET", path: "/commerce-api/price-monitoring/runs/pm-run-001", response: commerceDbUnavailableError },
  { method: "POST", path: "/commerce-api/price-monitoring/runs/pm-run-001/fetch", response: commerceDbUnavailableError },
  { method: "GET", path: "/commerce-api/price-monitoring/runs/pm-run-001/fetch", response: commerceDbUnavailableError },
  {
    method: "GET",
    path: "/commerce-api/price-monitoring/runs/pm-run-001/fetch/executions",
    response: commerceDbUnavailableError,
  },
  {
    method: "GET",
    path: "/commerce-api/price-monitoring/runs/pm-run-001/fetch/logs",
    response: commerceDbUnavailableError,
  },
  {
    method: "GET",
    path: "/commerce-api/price-monitoring/runs/pm-run-001/fetch/exec-success",
    response: commerceDbUnavailableError,
  },
  {
    method: "GET",
    path: "/commerce-api/price-monitoring/runs/pm-run-001/fetch/exec-success/logs",
    response: commerceDbUnavailableError,
  },
  {
    method: "POST",
    path: "/commerce-api/price-monitoring/runs/pm-run-001/fetch/cancel",
    response: commerceDbUnavailableError,
  },
  {
    method: "POST",
    path: "/commerce-api/price-monitoring/runs/pm-run-001/fetch/exec-success/cancel",
    response: commerceDbUnavailableError,
  },
  { method: "GET", path: "/commerce-api/price-monitoring/runs/pm-run-001/review", response: commerceDbUnavailableError },
  {
    method: "POST",
    path: "/commerce-api/price-monitoring/runs/pm-run-001/review/actions",
    response: commerceDbUnavailableError,
  },
  {
    method: "POST",
    path: "/commerce-api/price-monitoring/runs/pm-run-001/export-price-update",
    response: commerceDbUnavailableError,
  },
  { method: "GET", path: "/commerce-api/price-monitoring/alerts/rules", response: commerceDbUnavailableError },
  { method: "POST", path: "/commerce-api/price-monitoring/alerts/rules", response: commerceDbUnavailableError },
  { method: "PATCH", path: "/commerce-api/price-monitoring/alerts/rules/101", response: commerceDbUnavailableError },
  {
    method: "POST",
    path: "/commerce-api/price-monitoring/alerts/rules/101/deactivate",
    response: commerceDbUnavailableError,
  },
  { method: "GET", path: "/commerce-api/price-monitoring/alerts/events", response: commerceDbUnavailableError },
  {
    method: "POST",
    path: "/commerce-api/price-monitoring/alerts/events/201/acknowledge",
    response: commerceDbUnavailableError,
  },
  {
    method: "POST",
    path: "/commerce-api/price-monitoring/alerts/events/201/resolve",
    response: commerceDbUnavailableError,
  },
  {
    method: "POST",
    path: "/commerce-api/price-monitoring/alerts/evaluate/pm-run-001",
    response: commerceDbUnavailableError,
  },
];

export const catalogDbImportRequiredFixtureRoutes: MockRoute[] = [
  { method: "GET", path: "/commerce-api/catalog/products", response: catalogDbImportRequiredError },
  { method: "GET", path: "/commerce-api/catalog/summary", response: catalogDbImportRequiredError },
  { method: "GET", path: "/commerce-api/catalog/brands", response: catalogDbImportRequiredError },
  { method: "GET", path: "/commerce-api/catalog/category-hierarchy", response: catalogDbImportRequiredError },
  { method: "GET", path: "/commerce-api/catalog/products/1", response: catalogDbImportRequiredError },
  { method: "GET", path: "/commerce-api/catalog/products/1/source-urls", response: catalogDbImportRequiredError },
  { method: "POST", path: "/commerce-api/catalog/products/1/source-urls", response: catalogDbImportRequiredError },
  { method: "PATCH", path: "/commerce-api/catalog/source-urls/101", response: catalogDbImportRequiredError },
  { method: "PATCH", path: "/commerce-api/catalog/source-urls/102", response: catalogDbImportRequiredError },
  { method: "POST", path: "/commerce-api/catalog/source-urls/101/validate", response: catalogDbImportRequiredError },
  { method: "GET", path: "/commerce-api/catalog/source-urls/summary", response: catalogDbImportRequiredError },
  { method: "POST", path: "/commerce-api/catalog/source-urls/import/preview", response: catalogDbImportRequiredError },
  { method: "POST", path: "/commerce-api/catalog/source-urls/import/apply", response: catalogDbImportRequiredError },
];

export const commerceFixtureRoutes: MockRoute[] = [
  { method: "GET", path: "/commerce-api/health", response: commerceHealth },
  { method: "GET", path: "/commerce-api/platform/health", response: platformHealth },
  { method: "GET", path: "/commerce-api/catalog/summary", response: catalogSummary },
  { method: "GET", path: "/commerce-api/catalog/brands", response: catalogBrands },
  { method: "GET", path: "/commerce-api/catalog/category-hierarchy", response: catalogCategoryHierarchy },
  { method: "GET", path: "/commerce-api/catalog/products", response: catalogProducts },
  { method: "GET", path: "/commerce-api/catalog/products/1", response: catalogProductDetail },
  { method: "GET", path: "/commerce-api/catalog/products/2", response: catalogProductDetailWithoutSourceUrls },
  {
    method: "GET",
    path: "/commerce-api/catalog/products/1/source-url-candidates",
    response: productSourceUrlCandidateHistory,
  },
  {
    method: "GET",
    path: "/commerce-api/catalog/products/2/source-url-candidates",
    response: emptyProductSourceUrlCandidateHistory,
  },
  { method: "GET", path: "/commerce-api/catalog/update-db/latest", response: null },
  { method: "GET", path: "/commerce-api/catalog/products/1/source-urls", response: sourceUrlsForCatalogProduct },
  {
    method: "POST",
    path: "/commerce-api/catalog/products/1/source-urls",
    requestExample: { url: "https://www.public.gr/product/midea-md-20l", url_type: "manual" },
    response: createSourceUrlResponse,
  },
  {
    method: "PATCH",
    path: "/commerce-api/catalog/source-urls/101",
    requestExample: { status: "disabled" },
    response: updateSourceUrlResponse,
  },
  {
    method: "PATCH",
    path: "/commerce-api/catalog/source-urls/102",
    requestExample: { status: "active" },
    response: promoteSourceUrlResponse,
  },
  { method: "POST", path: "/commerce-api/catalog/source-urls/101/validate", response: sourceUrlValidationBroken },
  { method: "GET", path: "/commerce-api/catalog/source-urls/summary", response: sourceUrlSummary },
  { method: "GET", path: "/commerce-api/vendor-sources/source-urls/summary", response: vendorSourceUrlSummary },
  { method: "GET", path: "/commerce-api/vendor-sources/source-health", response: vendorSourceHealth },
  {
    method: "POST",
    path: "/commerce-api/vendor-sources/source-health/1001/recapture",
    response: vendorSourceRecaptureResponse,
  },
  {
    method: "POST",
    path: "/commerce-api/source-url-agent/runs",
    requestExample: {
      mode: "catalog",
      source: "all",
      missing_only: true,
      active_only: true,
      dry_run: true,
      apply_high_confidence: false,
      limit: 20,
      rate_limit_seconds: 2,
    },
    response: createSourceUrlAgentRunResponse,
  },
  { method: "GET", path: "/commerce-api/vendor-sources/sources", response: vendorSourceCapabilities },
  { method: "GET", path: "/commerce-api/source-url-agent/sources", response: vendorSourceCapabilities },
  { method: "GET", path: "/commerce-api/source-url-agent/readiness", response: sourceUrlAgentReadinessReady },
  { method: "GET", path: "/commerce-api/source-url-agent/runs", response: sourceUrlAgentRuns },
  {
    method: "GET",
    path: "/commerce-api/source-url-agent/runs/source-run-001",
    response: sourceUrlAgentRunDetail,
  },
  {
    method: "GET",
    path: "/commerce-api/source-url-agent/runs/source-run-001/artifacts",
    response: sourceUrlAgentArtifacts,
  },
  {
    method: "POST",
    path: "/commerce-api/vendor-sources/captures/runs",
    requestExample: {
      source_filter: "electronet",
      limit: 50,
      include_not_due: false,
      refresh_after_minutes: 1440,
      catalog_product_ids: [],
    },
    response: createVendorSourceCaptureRunResponse,
  },
  { method: "GET", path: "/commerce-api/vendor-sources/captures/runs", response: vendorSourceCaptureRuns },
  {
    method: "GET",
    path: "/commerce-api/vendor-sources/captures/runs/capture-run-001",
    response: vendorSourceCaptureRunDetail,
  },
  {
    method: "GET",
    path: "/commerce-api/vendor-sources/captures/runs/capture-run-001/artifacts",
    response: vendorSourceCaptureArtifacts,
  },
  { method: "GET", path: "/commerce-api/source-url-agent/candidates", response: sourceUrlCandidatesResponse },
  {
    method: "GET",
    path: "/commerce-api/source-url-agent/candidates/501",
    response: { candidate: { ...sourceUrlCandidates.items[0], source_url_id: 101, review_panel: sourceUrlCandidateReviewLayout.review_panel } },
  },
  {
    method: "GET",
    path: "/commerce-api/source-url-agent/candidates/502",
    response: { candidate: { ...sourceUrlCandidates.items[1], review_panel: sourceUrlCandidateReviewLayout.review_panel } },
  },
  {
    method: "PATCH",
    path: "/commerce-api/source-url-agent/candidates/501/review",
    requestExample: {
      decision: "accept",
      reviewed_url: null,
      review_notes: "High confidence candidate.",
      reviewed_by: "operator",
    },
    response: reviewSourceUrlCandidateResponse,
  },
  {
    method: "POST",
    path: "/commerce-api/vendor-sources/source-urls/101/diagnostics/skroutz-network",
    requestExample: { headed: false, timeout_seconds: 60 },
    response: skroutzNetworkDiagnosticSummary,
  },
  {
    method: "GET",
    path: "/commerce-api/vendor-sources/source-urls/101/diagnostics/skroutz-network/latest",
    response: skroutzNetworkDiagnosticReport,
  },
  {
    method: "POST",
    path: "/commerce-api/source-url-agent/runs",
    requestExample: {
      mode: "catalog",
      source: "all",
      missing_only: true,
      active_only: true,
      dry_run: true,
      apply_high_confidence: false,
      limit: 20,
      rate_limit_seconds: 2,
    },
    response: createSourceUrlAgentRunResponse,
  },
  { method: "GET", path: "/commerce-api/source-url-agent/runs", response: sourceUrlAgentRuns },
  {
    method: "GET",
    path: "/commerce-api/source-url-agent/runs/source-run-001",
    response: sourceUrlAgentRunDetail,
  },
  {
    method: "GET",
    path: "/commerce-api/source-url-agent/runs/source-run-001/artifacts",
    response: sourceUrlAgentArtifacts,
  },
  { method: "GET", path: "/commerce-api/source-url-agent/candidates", response: sourceUrlCandidatesResponse },
  {
    method: "GET",
    path: "/commerce-api/source-url-agent/candidates/501",
    response: { candidate: { ...sourceUrlCandidates.items[0], source_url_id: 101, review_panel: sourceUrlCandidateReviewLayout.review_panel } },
  },
  {
    method: "GET",
    path: "/commerce-api/source-url-agent/candidates/502",
    response: { candidate: { ...sourceUrlCandidates.items[1], review_panel: sourceUrlCandidateReviewLayout.review_panel } },
  },
  {
    method: "PATCH",
    path: "/commerce-api/source-url-agent/candidates/501/review",
    requestExample: {
      decision: "accept",
      reviewed_url: null,
      review_notes: "High confidence candidate.",
      reviewed_by: "operator",
    },
    response: reviewSourceUrlCandidateResponse,
  },
  {
    method: "POST",
    path: "/commerce-api/catalog/source-urls/import/preview",
    requestExample: {
      catalog_source: "sourceCata",
      include_observations: true,
      include_artifacts: true,
      limit: 100,
      report_items_limit: 200,
    },
    response: sourceUrlImportPreview,
  },
  {
    method: "POST",
    path: "/commerce-api/catalog/source-urls/import/apply",
    requestExample: {
      catalog_source: "sourceCata",
      include_observations: true,
      include_artifacts: true,
      limit: 100,
      report_items_limit: 200,
    },
    response: sourceUrlImportApply,
  },
  {
    method: "POST",
    path: "/commerce-api/catalog/source-urls/import/product-factory/preview",
    requestExample: {
      handoff_path: "work/005606/integrations/ecommerce_source_handoff.json",
      catalog_source: "sourceCata",
      persist_initial_capture: true,
      limit: null,
      report_items_limit: 200,
    },
    response: productFactoryHandoffImportPreview,
  },
  {
    method: "POST",
    path: "/commerce-api/catalog/source-urls/import/product-factory/apply",
    requestExample: {
      handoff_path: "work/005606/integrations/ecommerce_source_handoff.json",
      catalog_source: "sourceCata",
      persist_initial_capture: true,
      limit: null,
      report_items_limit: 200,
    },
    response: productFactoryHandoffImportApply,
  },
  { method: "GET", path: "/commerce-api/price-monitoring/db/status", response: dbStatusAvailable },
  {
    method: "POST",
    path: "/commerce-api/price-monitoring/selection/preview",
    requestExample: { source: "electronet", source_name: "electronet", source_filter: "electronet", selected_models: ["005606", "AB-123"], dry_run: true },
    response: priceMonitoringSelectionResult,
  },
  {
    method: "POST",
    path: "/commerce-api/price-monitoring/runs",
    requestExample: { source: "electronet", source_name: "electronet", source_filter: "electronet", selected_models: ["005606", "AB-123"], dry_run: false },
    response: priceMonitoringSelectionResult,
  },
  { method: "GET", path: "/commerce-api/price-monitoring/runs", response: priceMonitoringRuns },
  { method: "GET", path: "/commerce-api/price-monitoring/runs/pm-run-001", response: priceMonitoringRunDetail },
  { method: "GET", path: "/commerce-api/price-monitoring/runs/pm-run-001/fetch", response: priceMonitoringExecutions[1] },
  {
    method: "GET",
    path: "/commerce-api/price-monitoring/runs/pm-run-001/fetch/executions",
    response: {
      items: priceMonitoringExecutions,
      executions: priceMonitoringExecutions,
      count: priceMonitoringExecutions.length,
      run_id: "pm-run-001",
    },
  },
  {
    method: "GET",
    path: "/commerce-api/price-monitoring/runs/pm-run-001/fetch/logs",
    response: priceMonitoringFetchLogs,
  },
  {
    method: "GET",
    path: "/commerce-api/price-monitoring/runs/pm-run-001/fetch/exec-success/logs",
    response: priceMonitoringFetchLogs,
  },
  { method: "GET", path: "/commerce-api/price-monitoring/runs/pm-run-001/review", response: priceMonitoringReview },
  { method: "GET", path: "/commerce-api/price-monitoring/alerts/rules", response: alertRules },
  { method: "GET", path: "/commerce-api/price-monitoring/alerts/events", response: alertEventsResponse },
  {
    method: "GET",
    path: "/commerce-api/artifacts/price-monitoring/runs/pm-run-001",
    response: priceMonitoringArtifacts,
  },
  { method: "GET", path: "/commerce-api/files/roots", response: { roots: [] } },
  { method: "GET", path: "/commerce-api/artifacts/roots", response: { roots: pathRoots.artifact_roots.roots } },
  { method: "GET", path: "/commerce-api/paths/roots", response: pathRoots },
  {
    method: "GET",
    path: "/commerce-api/price-monitoring/runs/pm-run-001/observations",
    response: priceMonitoringRunObservations,
  },
  {
    method: "GET",
    path: "/commerce-api/price-monitoring/runs/pm-run-001/catalog-snapshot",
    response: { run_id: "pm-run-001", items: [], count: 0 },
  },
];
