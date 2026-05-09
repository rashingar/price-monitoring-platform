import { describe, expect, it } from "vitest";
import { getAuthoringJobSubtype, getJobStage } from "../../api/jobUtils";

describe("Product Factory job utilities", () => {
  it("maps authoring job types to the Authoring workflow tab and subtype", () => {
    const introJob = {
      job_id: "000001-authoring_intro-abc",
      job_type: "authoring_intro",
      status: "succeeded",
    };
    const seoJob = {
      job_id: "000001-authoring_seo-abc",
      job_type: "authoring_seo",
      status: "succeeded",
    };

    expect(getJobStage(introJob)).toBe("authoring");
    expect(getAuthoringJobSubtype(introJob)).toBe("intro_text");
    expect(getJobStage(seoJob)).toBe("authoring");
    expect(getAuthoringJobSubtype(seoJob)).toBe("seo_meta");
  });
});
