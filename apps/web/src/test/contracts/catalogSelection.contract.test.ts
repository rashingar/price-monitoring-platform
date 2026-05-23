import { describe, expect, it } from "vitest";
import type { CatalogProduct, PriceMonitoringSelectionResult } from "../../api/commerceTypes";
import {
  getAutomationBlockerBadges,
  getCatalogWarningBadges,
  getSelectionBlocker,
  getSkippedMissingSourceUrlModels,
  getSourceUrlEligibility,
  makeSelectionBody,
} from "../../features/catalog/catalogSelection";

describe("catalog selection helpers", () => {
  it("keeps active source URL products eligible for selection", () => {
    const product: CatalogProduct = {
      model: " 001234 ",
      is_atomic_model: true,
      automation_eligible: true,
      ignored: false,
      source_url_coverage: {
        has_active_source_url: true,
      },
    };

    expect(getSelectionBlocker(product)).toBeNull();
    expect(getSourceUrlEligibility(product)).toEqual({
      label: "Eligible",
      className: "success",
      blocker: null,
    });
  });

  it("blocks composite, ignored, and missing source URL products in the same order as Catalog", () => {
    expect(getSelectionBlocker({ model: "1", is_atomic_model: false, automation_eligible: false })).toBe("Composite");
    expect(getSelectionBlocker({ model: "2", automation_eligible: false })).toBe("Missing MPN");
    expect(getSelectionBlocker({ model: "3", ignored: true })).toBe("Ignored");
    expect(getSelectionBlocker({ model: "4" })).toBe("Missing source URL");
  });

  it("derives automation blocker and non-blocking catalog warning badges", () => {
    expect(
      getAutomationBlockerBadges({
        model: "AB-123",
        mpn: "",
        is_atomic_model: false,
        automation_eligible: false,
      }),
    ).toEqual([
      { label: "Composite", className: "danger" },
      { label: "Missing MPN", className: "danger" },
    ]);
    expect(
      getCatalogWarningBadges({
        model: "001234",
        mpn: "MPN-1",
        is_atomic_model: true,
        automation_eligible: true,
        status: 0,
        price: 0,
      }),
    ).toEqual([
      { label: "Disabled", className: "warning" },
      { label: "Zero price", className: "warning" },
    ]);
    expect(
      getSelectionBlocker({
        model: "001234",
        mpn: "MPN-1",
        is_atomic_model: true,
        automation_eligible: true,
        status: 0,
        price: 0,
        source_url_coverage: { has_active_source_url: true },
      }),
    ).toBeNull();
  });

  it("builds the Price Monitoring selection body from selected models and current filters", () => {
    const body = makeSelectionBody(
      "bestprice",
      new Set(["001234", "005678"]),
      {
        q: " keyboard ",
        family: "Peripherals",
        categoryName: "Keyboards",
        subCategory: "Mechanical",
        manufacturer: "Acme",
        marketplace: "bestprice",
        includeIgnored: true,
      },
      true,
    );

    expect(body).toMatchObject({
      source: "bestprice",
      selected_models: ["001234", "005678"],
      excluded_models: [],
      include_ignored: true,
      dry_run: true,
      filters: {
        q: "keyboard",
        family: "Peripherals",
        category_name: "Keyboards",
        sub_category: "Mechanical",
        manufacturer: "Acme",
        marketplace: "bestprice",
        has_mpn: true,
        atomic_only: true,
        automation_eligible_only: true,
      },
    });
  });

  it("extracts unique missing source URL models from preview results", () => {
    const result: PriceMonitoringSelectionResult = {
      skipped_items: [
        { model: "001234", skip_reason: "missing_active_source_url" },
        { model: "001234", reason: "no_active_source_url" },
        { model: "005678", source_url_coverage: { has_active_source_url: false } },
        { model: "009999", reason: "ignored" },
      ],
      source_url_coverage: {
        missing_source_url_models: ["005678", "000111"],
      },
    };

    expect(getSkippedMissingSourceUrlModels(result)).toEqual(["001234", "005678", "000111"]);
  });
});
