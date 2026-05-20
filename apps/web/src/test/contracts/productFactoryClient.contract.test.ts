import { describe, expect, it } from "vitest";
import { ApiError, apiClient } from "../../api/client";
import type {
  PrepareJobRequest,
  ProductFactoryContractPrepareJobRequest,
  ProductFactoryContractPublishJobRequest,
  ProductFactoryContractRenderJobRequest,
  ProductFactoryContractStopJobRequest,
  PublishJobRequest,
  RenderJobRequest,
  StopJobRequest,
} from "../../api/types";
import { installMockFetch } from "../mockFetch";
import {
  productFactoryConflictError,
  productFactoryFilterCategoryWriteDetail,
  productFactoryFilterRevision,
  productFactoryFixtureRoutes,
  productFactoryJobs,
  productFactoryValidationError,
} from "../fixtures/productFactoryApi";

describe("Product Factory API client contract fixtures", () => {
  it("passes through health responses", async () => {
    installMockFetch(productFactoryFixtureRoutes);

    await expect(apiClient.getHealth()).resolves.toMatchObject({
      status: "ok",
      service: "product-factory",
    });
  });

  it("normalizes wrapped and direct job list shapes", async () => {
    installMockFetch([
      { method: "GET", path: "/api/jobs", response: { jobs: productFactoryJobs } },
    ]);
    await expect(apiClient.listJobs()).resolves.toHaveLength(productFactoryJobs.length);

    installMockFetch([{ method: "GET", path: "/api/jobs", response: productFactoryJobs }]);
    await expect(apiClient.listJobs()).resolves.toEqual(productFactoryJobs);
  });

  it("preserves terminal job statuses", async () => {
    installMockFetch(productFactoryFixtureRoutes);

    const jobs = await apiClient.listJobs();
    expect(jobs.map((job) => job.status)).toEqual(
      expect.arrayContaining(["succeeded", "failed", "cancelled", "killed"]),
    );
  });

  it("normalizes job detail logs and artifacts from backend wrapper shapes", async () => {
    installMockFetch(productFactoryFixtureRoutes);

    await expect(apiClient.getJob("job-succeeded-1")).resolves.toMatchObject({
      job_id: "job-succeeded-1",
      status: "succeeded",
    });
    await expect(apiClient.getJobLogs("job-succeeded-1")).resolves.toEqual(
      expect.arrayContaining([expect.objectContaining({ message: "Render succeeded" })]),
    );
    await expect(apiClient.getJobArtifacts("job-succeeded-1")).resolves.toEqual(
      expect.arrayContaining([expect.objectContaining({ name: "product-page.html" })]),
    );
  });

  it("normalizes settings filter categories details and sync report", async () => {
    installMockFetch(productFactoryFixtureRoutes);

    await expect(apiClient.getSettings()).resolves.toMatchObject({
      authoring: { intro_text: { default: { min_words: 80 } } },
    });

    await expect(apiClient.getFilterStatus()).resolves.toMatchObject({
      status: "ready",
      category_count: 2,
      revision: productFactoryFilterRevision,
    });

    const categories = await apiClient.listFilterCategories();
    expect(categories[0]).toMatchObject({
      category_id: 310,
      leaf_category: "Αφυγραντήρες",
    });

    const category = await apiClient.getFilterCategory(310);
    expect(category).toMatchObject({ category_id: 310, revision: productFactoryFilterRevision });
    expect(category.groups).toEqual(
      expect.arrayContaining([expect.objectContaining({ group_id: "grp-capacity" })]),
    );

    await expect(apiClient.getFilterSyncReport()).resolves.toMatchObject({
      mode: "mocked",
      warnings: [expect.objectContaining({ category_id: 310 })],
    });
  });

  it("includes expected_revision in add group requests", async () => {
    const mock = installMockFetch([
      {
        method: "PUT",
        path: "/api/filters/categories/310/groups",
        response: productFactoryFilterCategoryWriteDetail,
      },
    ]);

    await apiClient.addFilterGroup(310, {
      expected_revision: "rev-client-add-group",
      name: "Ενεργειακή κλάση",
      required: false,
      status: "active",
    });

    expect(mock.requests[0].body).toMatchObject({
      expected_revision: "rev-client-add-group",
      name: "Ενεργειακή κλάση",
    });
  });

  it("includes expected_revision in update group requests", async () => {
    const mock = installMockFetch([
      {
        method: "PATCH",
        path: "/api/filters/categories/310/groups/grp-capacity",
        response: productFactoryFilterCategoryWriteDetail,
      },
    ]);

    await apiClient.updateFilterGroup(310, "grp-capacity", {
      expected_revision: "rev-client-update-group",
      name: "Χωρητικότητα",
      required: true,
      status: "active",
    });

    expect(mock.requests[0].body).toMatchObject({
      expected_revision: "rev-client-update-group",
      name: "Χωρητικότητα",
    });
  });

  it("includes expected_revision in add value requests", async () => {
    const mock = installMockFetch([
      {
        method: "PUT",
        path: "/api/filters/categories/310/groups/grp-wifi/values",
        response: productFactoryFilterCategoryWriteDetail,
      },
    ]);

    await apiClient.addFilterValue(310, "grp-wifi", {
      expected_revision: "rev-client-add-value",
      value: "Μερικώς",
      status: "active",
    });

    expect(mock.requests[0].body).toMatchObject({
      expected_revision: "rev-client-add-value",
      value: "Μερικώς",
    });
  });

  it("includes expected_revision in update value requests", async () => {
    const mock = installMockFetch([
      {
        method: "PATCH",
        path: "/api/filters/categories/310/groups/grp-wifi/values/val-yes",
        response: productFactoryFilterCategoryWriteDetail,
      },
    ]);

    await apiClient.updateFilterValue(310, "grp-wifi", "val-yes", {
      expected_revision: "rev-client-update-value",
      value: "Ναι",
      status: "active",
    });

    expect(mock.requests[0].body).toMatchObject({
      expected_revision: "rev-client-update-value",
      value: "Ναι",
    });
  });

  it("normalizes authoring and filter review responses for leading-zero models", async () => {
    installMockFetch(productFactoryFixtureRoutes);

    await expect(apiClient.getAuthoringStatus("005606")).resolves.toMatchObject({
      model: "005606",
      ready_for_render: true,
    });
    await expect(apiClient.getFilterReview("005606")).resolves.toMatchObject({
      model: "005606",
      category_id: 310,
      groups: [expect.objectContaining({ group_name: "Χωρητικότητα" })],
    });
  });

  it("normalizes optional intro emphasis diagnostics safely", async () => {
    installMockFetch([
      {
        method: "GET",
        path: "/api/authoring/GENERIC-001",
        response: {
          authoring: {
            model: "GENERIC-001",
            intro_text: {
              status: "valid",
              emphasis_warning_codes: ["llm_intro_text_emphasis_missing", "", 42],
              strong_span_count: 0,
              emphasized_word_count: "invalid",
              visible_word_count: 96,
              emphasized_word_ratio: 0,
            },
            seo_meta: { status: "valid" },
            ready_for_render: true,
            render_block_reasons: [],
            warnings: [],
          },
        },
      },
    ]);

    const status = await apiClient.getAuthoringStatus("GENERIC-001");

    expect(status.intro_text).toMatchObject({
      status: "valid",
      emphasis_warning_codes: ["llm_intro_text_emphasis_missing"],
      strong_span_count: 0,
      visible_word_count: 96,
      emphasized_word_ratio: 0,
    });
    expect(status.intro_text?.emphasized_word_count).toBeUndefined();
  });

  it("normalizes queued authoring job responses", async () => {
    installMockFetch([
      {
        method: "POST",
        path: "/api/authoring/005606/intro-text",
        response: { job: { job_id: "005606-authoring_intro-abc", job_type: "authoring_intro", model: "005606", status: "queued" } },
      },
      {
        method: "POST",
        path: "/api/authoring/005606/intro-text/retry",
        response: { job: { job_id: "005606-authoring_intro-retry", job_type: "authoring_intro", model: "005606", status: "queued" } },
      },
      {
        method: "POST",
        path: "/api/authoring/005606/seo-meta",
        response: { job: { job_id: "005606-authoring_seo-abc", job_type: "authoring_seo", model: "005606", status: "queued" } },
      },
      {
        method: "POST",
        path: "/api/authoring/005606/seo-meta/retry",
        response: { job: { job_id: "005606-authoring_seo-retry", job_type: "authoring_seo", model: "005606", status: "queued" } },
      },
    ]);

    await expect(apiClient.runIntroText("005606")).resolves.toMatchObject({
      job_id: "005606-authoring_intro-abc",
      job_type: "authoring_intro",
      client_stage: "authoring",
    });
    await expect(apiClient.retryIntroText("005606")).resolves.toMatchObject({
      job_id: "005606-authoring_intro-retry",
      job_type: "authoring_intro",
      client_stage: "authoring",
    });
    await expect(apiClient.runSeoMeta("005606")).resolves.toMatchObject({
      job_id: "005606-authoring_seo-abc",
      job_type: "authoring_seo",
      client_stage: "authoring",
    });
    await expect(apiClient.retrySeoMeta("005606")).resolves.toMatchObject({
      job_id: "005606-authoring_seo-retry",
      job_type: "authoring_seo",
      client_stage: "authoring",
    });
  });

  it("sends backend-valid prepare payloads", async () => {
    const mock = installMockFetch([
      {
        method: "POST",
        path: "/api/jobs/prepare",
        response: { job: { job_id: "prepare-1", job_type: "prepare", status: "queued" } },
      },
    ]);
    const payload = {
      model: "005606",
      url: "https://example.invalid/product",
      photos: 1,
      sections: 0,
      skroutz_status: 0,
      boxnow: 0,
      price: 0,
      gallery_url: "https://example.invalid/gallery",
      characteristics_url: "https://example.invalid/specs",
      second_opencart_image_index: 4,
    } satisfies PrepareJobRequest;
    const generatedPayload: ProductFactoryContractPrepareJobRequest = payload;

    await apiClient.createPrepareJob(generatedPayload);

    expect(mock.requests[0]?.body).toEqual(payload);
    expect(mock.requests[0]?.body).not.toMatchObject({ price: null });
  });

  it("sends generated Product Factory job request payloads unchanged", async () => {
    const mock = installMockFetch([
      {
        method: "POST",
        path: "/api/jobs/render",
        response: { job: { job_id: "render-1", job_type: "render", status: "queued" } },
      },
      {
        method: "POST",
        path: "/api/jobs/publish",
        response: { job: { job_id: "publish-1", job_type: "publish", status: "queued" } },
      },
      {
        method: "POST",
        path: "/api/jobs/job-succeeded-1/stop",
        response: { job: { job_id: "job-succeeded-1", status: "cancelled" } },
      },
      {
        method: "POST",
        path: "/api/jobs/job-full-pipeline-succeeded-1/retry",
        response: { job: { job_id: "full-pipeline-retry-1", status: "queued" } },
      },
      {
        method: "POST",
        path: "/api/jobs/job-full-pipeline-succeeded-1/start",
        response: { job: { job_id: "full-pipeline-start-1", status: "queued" } },
      },
    ]);

    const renderPayload = { model: "005606" } satisfies RenderJobRequest;
    const generatedRenderPayload: ProductFactoryContractRenderJobRequest = renderPayload;
    const publishPayload = {
      model: "005606",
      current_job_product_file: "apps/product-factory-api/products/005606.csv",
    } satisfies PublishJobRequest;
    const generatedPublishPayload: ProductFactoryContractPublishJobRequest = publishPayload;
    const stopPayload = { reason: "operator requested" } satisfies StopJobRequest;
    const generatedStopPayload: ProductFactoryContractStopJobRequest = stopPayload;

    await apiClient.createRenderJob(generatedRenderPayload);
    await apiClient.createPublishJob(generatedPublishPayload);
    await apiClient.stopJob("job-succeeded-1", generatedStopPayload.reason ?? undefined);
    await apiClient.retryJob("job-full-pipeline-succeeded-1");
    await apiClient.startJob("job-full-pipeline-succeeded-1");

    expect(mock.requests[0]?.body).toEqual(renderPayload);
    expect(mock.requests[1]?.body).toEqual(publishPayload);
    expect(mock.requests[2]?.body).toEqual(stopPayload);
    expect(mock.requests[3]?.pathname).toBe("/api/jobs/job-full-pipeline-succeeded-1/retry");
    expect(mock.requests[4]?.pathname).toBe("/api/jobs/job-full-pipeline-succeeded-1/start");
  });

  it("exposes useful API error messages for 409 and 422 responses", async () => {
    installMockFetch([
      { method: "POST", path: "/api/jobs/prepare", response: productFactoryConflictError },
      { method: "POST", path: "/api/jobs/render", response: productFactoryValidationError },
    ]);

    await expect(
      apiClient.createPrepareJob({
        model: "005606",
        url: "https://example.invalid/product",
        photos: 1,
        sections: 1,
        skroutz_status: 1,
        boxnow: 0,
        price: 199.9,
      }),
    ).rejects.toMatchObject({
      status: 409,
      message: expect.stringContaining("already running"),
    } satisfies Partial<ApiError>);

    await expect(apiClient.createRenderJob({ model: "" })).rejects.toMatchObject({
      status: 422,
      message: expect.stringContaining("Model is required"),
    } satisfies Partial<ApiError>);
  });
});
