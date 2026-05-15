import { describe, expect, it } from "vitest";
import type { SourceUrlCandidate } from "../../api/commerceTypes";
import {
  DEFAULT_COLUMNS,
  SOURCE_URL_CANDIDATE_REVIEW_LAYOUT_STORAGE_KEY,
  initialFilters,
} from "../../features/source-url-candidates/sourceUrlCandidateConstants";
import { buildParams, passesCreatedDateFilter } from "../../features/source-url-candidates/sourceUrlCandidateHelpers";
import {
  columnKey,
  getColumnWidth,
  loadLocalSourceUrlCandidateReviewLayout,
  makeFallbackLayout,
  normalizeColumns,
  resetLocalSourceUrlCandidateReviewLayout,
  saveLocalSourceUrlCandidateReviewLayout,
} from "../../features/source-url-candidates/sourceUrlCandidateLayout";

describe("source URL candidate helpers", () => {
  it("maps candidate filters to backend list params", () => {
    expect(
      buildParams(
        {
          ...initialFilters,
          status: "all",
          sourceName: " skroutz ",
          runId: " run-1 ",
          model: " 001234 ",
          catalogProductId: " 42 ",
          minConfidence: " 0.4 ",
          maxConfidence: " 0.95 ",
          matchMethod: "mpn",
          createdFrom: "2026-05-01",
          createdTo: "2026-05-15",
        },
        50,
      ),
    ).toEqual({
      status: null,
      source_name: "skroutz",
      run_id: "run-1",
      model: "001234",
      catalog_product_id: "42",
      min_confidence: "0.4",
      max_confidence: "0.95",
      limit: 50,
      offset: 50,
    });
  });

  it("keeps created date filtering inclusive and ignores invalid candidate dates", () => {
    const candidate: SourceUrlCandidate = {
      id: 1,
      created_at: "2026-05-15T12:00:00Z",
    };

    expect(
      passesCreatedDateFilter(candidate, {
        ...initialFilters,
        createdFrom: "2026-05-15",
        createdTo: "2026-05-15",
      }),
    ).toBe(true);
    expect(
      passesCreatedDateFilter(candidate, {
        ...initialFilters,
        createdFrom: "2026-05-16",
      }),
    ).toBe(false);
    expect(passesCreatedDateFilter({ id: 2 }, { ...initialFilters, createdFrom: "2026-05-01" })).toBe(false);
    expect(
      passesCreatedDateFilter(
        { id: 3, created_at: "not-a-date" },
        { ...initialFilters, createdTo: "2026-05-01" },
      ),
    ).toBe(true);
  });
});

describe("source URL candidate review layout", () => {
  it("load save and reset preserve local columns and widths under the stable storage key", () => {
    const layout = makeFallbackLayout();
    const nextColumns = normalizeColumns(layout.columns).map((column, index) => {
      if (columnKey(column) === "confidence_score") {
        return { ...column, visible: false, table_column_visible: false, width_px: 123, order: index };
      }
      if (columnKey(column) === "candidate_title") {
        return { ...column, width_px: 900, order: index };
      }
      return { ...column, order: index };
    });

    const saved = saveLocalSourceUrlCandidateReviewLayout({ ...layout, columns: nextColumns });
    const stored = window.localStorage.getItem(SOURCE_URL_CANDIDATE_REVIEW_LAYOUT_STORAGE_KEY);
    const loaded = loadLocalSourceUrlCandidateReviewLayout();
    const loadedConfidence = loaded.columns.find((column) => columnKey(column) === "confidence_score");
    const loadedTitle = loaded.columns.find((column) => columnKey(column) === "candidate_title");

    expect(stored).not.toBeNull();
    expect(saved.columns.map(columnKey)).toEqual(loaded.columns.map(columnKey));
    expect(loadedConfidence).toMatchObject({ visible: false, table_column_visible: false, width_px: 123 });
    expect(getColumnWidth(loadedTitle!)).toBe(800);

    const reset = resetLocalSourceUrlCandidateReviewLayout();
    expect(window.localStorage.getItem(SOURCE_URL_CANDIDATE_REVIEW_LAYOUT_STORAGE_KEY)).toBeNull();
    expect(reset.columns.map(columnKey)).toEqual(normalizeColumns(DEFAULT_COLUMNS).map(columnKey));
  });

  it("normalizes defaults and removes actions and unknown columns", () => {
    const columns = normalizeColumns([
      { key: "actions", label: "Actions", visible: true, table_column_visible: true, order: 0 },
      { key: "status", label: "Old status", visible: false, table_column_visible: false, width_px: 101, order: 8 },
      { key: "unknown", label: "Unknown", visible: true, table_column_visible: true, order: 1 },
    ]);

    expect(new Set(columns.map(columnKey))).toEqual(new Set(normalizeColumns(DEFAULT_COLUMNS).map(columnKey)));
    expect(columns.some((column) => columnKey(column) === "actions")).toBe(false);
    expect(columns.some((column) => columnKey(column) === "unknown")).toBe(false);
    expect(columns.find((column) => columnKey(column) === "status")).toMatchObject({
      label: "Status",
      visible: false,
      table_column_visible: false,
      width_px: 101,
    });
  });
});
