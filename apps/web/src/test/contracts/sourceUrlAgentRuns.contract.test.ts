import { describe, expect, it } from "vitest";
import type { SourceUrlAgentRunRequest } from "../../api/commerceTypes";
import {
  buildRunRequestFromHandoff,
  makeRunRequest,
  parseSelectedModelsParam,
} from "../../features/source-url-agent-runs/sourceUrlAgentRunHandoff";
import {
  formatNumber,
  formatTaskProgress,
  getRunId,
} from "../../features/source-url-agent-runs/sourceUrlAgentRunFormatters";

describe("source URL agent runs handoff helpers", () => {
  it("parses selected models by trimming empty entries and preserving first-seen order", () => {
    expect(parseSelectedModelsParam(" 005606,123456,005606,, 233374 ")).toEqual([
      "005606",
      "123456",
      "233374",
    ]);
  });

  it("builds handoff run requests with selected model count as the launch limit", () => {
    const params = new URLSearchParams({
      models: "005606,123456",
      source: " skroutz ",
    });

    expect(buildRunRequestFromHandoff(params)).toMatchObject({
      source: "skroutz",
      selected_models: ["005606", "123456"],
      limit: 2,
      max_products_per_batch: 2,
      missing_only: true,
      active_only: true,
      dry_run: true,
    });
  });

  it("normalizes manual launch requests without shrinking selected model batches", () => {
    const request: SourceUrlAgentRunRequest = {
      mode: "",
      source: "",
      selected_models: ["005606", " 005606 ", "123456"],
      missing_only: true,
      active_only: true,
      dry_run: true,
      apply_high_confidence: false,
      limit: 1,
      rate_limit_seconds: -1,
    };

    expect(makeRunRequest(request)).toMatchObject({
      mode: "catalog",
      source: "all",
      selected_models: ["005606", "123456"],
      limit: 2,
      max_products_per_batch: 2,
      rate_limit_seconds: 0,
    });
  });
});

describe("source URL agent runs formatting helpers", () => {
  it("formats run identifiers, counters, and task progress defensively", () => {
    expect(getRunId({ run_id: "" })).toBe("-");
    expect(formatNumber("12")).toBe("12");
    expect(
      formatTaskProgress({
        summary: {
          task_finished_count: 2,
          task_total_count: 5,
        },
      }),
    ).toBe("2 / 5");
  });
});
