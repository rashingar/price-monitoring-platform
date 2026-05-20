import { describe, expect, it } from "vitest";
import {
  canRetryWithoutScraping,
  canStartFromScratch,
  getAuthoringJobSubtype,
  getJobStage,
} from "../../api/jobUtils";

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

  it("allows retry without scraping and start only for terminal full pipeline jobs", () => {
    const terminalFullPipeline = {
      job_id: "job-full-pipeline",
      job_type: "full_pipeline",
      status: "succeeded",
    };
    const activeFullPipeline = {
      job_id: "job-running",
      job_type: "full_pipeline",
      status: "running",
    };
    const terminalPrepare = {
      job_id: "job-prepare",
      job_type: "prepare",
      status: "failed",
    };

    expect(canRetryWithoutScraping(terminalFullPipeline)).toBe(true);
    expect(canStartFromScratch(terminalFullPipeline)).toBe(true);
    expect(canRetryWithoutScraping(activeFullPipeline)).toBe(false);
    expect(canStartFromScratch(activeFullPipeline)).toBe(false);
    expect(canRetryWithoutScraping(terminalPrepare)).toBe(false);
    expect(canStartFromScratch(terminalPrepare)).toBe(false);
  });
});
