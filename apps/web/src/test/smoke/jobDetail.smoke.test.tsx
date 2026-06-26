import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { installMockFetch, type MockRoute } from "../mockFetch";
import { renderWithRouter } from "../renderWithRouter";

const LONG_JOB_ID = "415638-full_pipeline-a78dd79ab441";
const LONG_URL =
  "https://www.example.com/products/" +
  "very-long-product-slug-that-should-wrap-without-forcing-horizontal-overflow".repeat(4);

function jobRoutes(job: Record<string, unknown>, logs: unknown[] = [], artifacts: unknown[] = []): MockRoute[] {
  const jobId = String(job.job_id);
  return [
    { method: "GET", path: `/api/jobs/${jobId}`, response: job },
    { method: "GET", path: `/api/jobs/${jobId}/logs`, response: { lines: logs } },
    { method: "GET", path: `/api/jobs/${jobId}/artifacts`, response: { artifacts } },
  ];
}

function installClipboard() {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  return writeText;
}

describe("Product Factory job detail page", () => {
  it("renders a running job with status, activity, progress, payload, and logs", async () => {
    installMockFetch(
      jobRoutes(
        {
          job_id: LONG_JOB_ID,
          job_type: "full_pipeline",
          model: "415638",
          status: "running",
          message: "Downloading gallery images.",
          created_at: "2026-06-26T06:39:12Z",
          started_at: "2026-06-26T06:39:14Z",
          payload: { model: "415638", source_url: LONG_URL, sections: 20 },
          result: {
            progress: {
              current_step: "prepare",
              current_step_label: "Prepare source",
              steps_completed: 2,
              elapsed_seconds: 12,
              current_step_elapsed_seconds: 4,
              details: { model: "415638", latest_message: "Normalizing source data." },
            },
          },
        },
        ["Full pipeline stage prepare starting.", "Downloading gallery images."],
      ),
    );

    renderWithRouter(`/jobs/${LONG_JOB_ID}`);

    await expect(screen.findByRole("heading", { name: "Full pipeline job" })).resolves.toBeInTheDocument();
    expect(screen.getAllByText("running").length).toBeGreaterThan(0);
    expect(screen.getByText("415638...79ab441")).toHaveAttribute("title", LONG_JOB_ID);
    expect(screen.getAllByText("Downloading gallery images.").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Prepare source" })).toBeInTheDocument();
    expect(screen.getByText("Pipeline step")).toBeInTheDocument();
    expect(screen.getByText("415638")).toBeInTheDocument();
    expect(screen.getByText("Full pipeline stage prepare starting.")).toBeInTheDocument();
  });

  it("renders a successful job with compact timing metadata", async () => {
    installMockFetch(
      jobRoutes({
        job_id: "233541-full_pipeline-success",
        job_type: "full_pipeline",
        model: "233541",
        status: "succeeded",
        created_at: "2026-06-26T06:00:00Z",
        started_at: "2026-06-26T06:01:00Z",
        finished_at: "2026-06-26T06:03:05Z",
        payload: { model: "233541", source_url: "https://www.electronet.gr/example" },
      }),
    );

    renderWithRouter("/jobs/233541-full_pipeline-success");

    await expect(screen.findByRole("heading", { name: "Full pipeline job" })).resolves.toBeInTheDocument();
    expect(screen.getAllByText("succeeded").length).toBeGreaterThan(0);
    expect(screen.getByText("Created")).toBeInTheDocument();
    expect(screen.getByText("Started")).toBeInTheDocument();
    expect(screen.getByText("Finished")).toBeInTheDocument();
    expect(screen.getByText("Duration")).toBeInTheDocument();
    expect(screen.getByText("2m 5s")).toBeInTheDocument();
  });

  it("shows a failed job concise error above technical details", async () => {
    installMockFetch(
      jobRoutes({
        job_id: "233541-full_pipeline-failed",
        job_type: "full_pipeline",
        model: "233541",
        status: "failed",
        message: "Full pipeline failed during render.",
        error: {
          message: "Candidate validation failed",
          exception_type: "ValidationError",
          traceback: "Traceback with long diagnostic detail",
        },
        error_code: "validation_failed",
        created_at: "2026-06-26T06:00:00Z",
        started_at: "2026-06-26T06:01:00Z",
        finished_at: "2026-06-26T06:02:00Z",
      }),
    );

    renderWithRouter("/jobs/233541-full_pipeline-failed");

    await expect(screen.findByRole("heading", { name: "Job failed" })).resolves.toBeInTheDocument();
    expect(screen.getByText("Candidate validation failed")).toBeInTheDocument();
    const details = screen.getByText("Technical details").closest("details");
    expect(details).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("Technical details"));
    expect(details).toHaveAttribute("open");
    expect(screen.getAllByText(/validation_failed/).length).toBeGreaterThan(0);
  });

  it("uses a compact empty state when no request payload exists", async () => {
    installMockFetch(
      jobRoutes({
        job_id: "job-empty-payload",
        job_type: "render",
        model: "233541",
        status: "succeeded",
        created_at: "2026-06-26T06:00:00Z",
      }),
    );

    renderWithRouter("/jobs/job-empty-payload");

    await expect(screen.findByText("No request payload was stored for this job.")).resolves.toBeInTheDocument();
    expect(screen.queryByText("No payload")).not.toBeInTheDocument();
  });

  it("renders formatted request payload JSON and supports payload copy", async () => {
    const writeText = installClipboard();
    installMockFetch(
      jobRoutes({
        job_id: "job-json-payload",
        job_type: "prepare",
        model: "233541",
        status: "succeeded",
        created_at: "2026-06-26T06:00:00Z",
        payload: { model: "233541", source_url: LONG_URL, nested: { sections: 20 } },
      }),
    );

    renderWithRouter("/jobs/job-json-payload");

    await expect(screen.findByText(/"source_url"/)).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Copy payload" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining('"source_url"')));
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("shortens long job IDs while keeping the complete ID accessible and copyable", async () => {
    const writeText = installClipboard();
    installMockFetch(
      jobRoutes({
        job_id: LONG_JOB_ID,
        job_type: "full_pipeline",
        model: "415638",
        status: "succeeded",
        created_at: "2026-06-26T06:00:00Z",
      }),
    );

    renderWithRouter(`/jobs/${LONG_JOB_ID}`);

    await expect(screen.findByText("415638...79ab441")).resolves.toHaveAttribute("title", LONG_JOB_ID);
    expect(screen.queryByRole("heading", { name: LONG_JOB_ID })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Copy job ID" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(LONG_JOB_ID));
  });

  it("keeps long payload and log content in wrapping containers", async () => {
    installMockFetch(
      jobRoutes(
        {
          job_id: "job-long-content",
          job_type: "full_pipeline",
          model: "233541",
          status: "running",
          created_at: "2026-06-26T06:00:00Z",
          started_at: "2026-06-26T06:00:05Z",
          payload: { source_url: LONG_URL, token: "x".repeat(300) },
        },
        [`log-line-${"y".repeat(300)}`],
      ),
    );

    const { container } = renderWithRouter("/jobs/job-long-content");

    await expect(screen.findByText(/log-line-/)).resolves.toBeInTheDocument();
    expect(container.querySelector(".job-detail-page")).toBeInTheDocument();
    expect(container.querySelector(".json-block-wrap")).toBeInTheDocument();
    expect(container.querySelector(".log-list")).toBeInTheDocument();
    expect(container.querySelector(".summary-grid.job-detail-summary-grid")).toBeInTheDocument();
  });

  it("copies loaded logs as diagnostic text", async () => {
    const writeText = installClipboard();
    installMockFetch(
      jobRoutes(
        {
          job_id: "job-copy-logs",
          job_type: "publish",
          model: "233541",
          status: "succeeded",
          created_at: "2026-06-26T06:00:00Z",
        },
        ["Publish started", "Publish succeeded"],
      ),
    );

    renderWithRouter("/jobs/job-copy-logs");

    await expect(screen.findByText("Publish started")).resolves.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Copy logs" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("Publish started\nPublish succeeded"));
  });

  it("renders queued, cancelled, and killed job statuses without changing routes", async () => {
    for (const status of ["queued", "cancelled", "killed"]) {
      installMockFetch(
        jobRoutes({
          job_id: `job-${status}`,
          job_type: "render",
          model: "233541",
          status,
          created_at: "2026-06-26T06:00:00Z",
        }),
      );

      const view = renderWithRouter(`/jobs/job-${status}`);

      await expect(screen.findByRole("heading", { name: "Render job" })).resolves.toBeInTheDocument();
      expect(screen.getAllByText(status).length).toBeGreaterThan(0);
      view.unmount();
    }
  });

  it("preserves active job polling interval and stops after terminal status", async () => {
    vi.useFakeTimers();
    let jobPollCount = 0;
    const mockFetch = installMockFetch([
      {
        method: "GET",
        path: "/api/jobs/job-polling",
        response: () => {
          jobPollCount += 1;
          return {
            job_id: "job-polling",
            job_type: "render",
            model: "233541",
            status: jobPollCount >= 2 ? "succeeded" : "running",
            created_at: "2026-06-26T06:00:00Z",
            started_at: "2026-06-26T06:00:05Z",
            finished_at: jobPollCount >= 2 ? "2026-06-26T06:00:30Z" : null,
          };
        },
      },
      { method: "GET", path: "/api/jobs/job-polling/logs", response: { lines: [] } },
      { method: "GET", path: "/api/jobs/job-polling/artifacts", response: { artifacts: [] } },
    ]);

    renderWithRouter("/jobs/job-polling");

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByText("Refreshing every 2.5 seconds")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });

    expect(mockFetch.requests.filter((request) => request.pathname === "/api/jobs/job-polling").length).toBe(2);
    expect(screen.getByText("Polling stopped")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(mockFetch.requests.filter((request) => request.pathname === "/api/jobs/job-polling").length).toBe(2);
  });

  it("collapses large request payloads by default and expands on demand", async () => {
    installMockFetch(
      jobRoutes({
        job_id: "job-large-payload",
        job_type: "full_pipeline",
        model: "233541",
        status: "succeeded",
        created_at: "2026-06-26T06:00:00Z",
        payload: {
          model: "233541",
          source_url: LONG_URL,
          notes: Array.from({ length: 30 }, (_, index) => `large line ${index}`),
        },
      }),
    );

    renderWithRouter("/jobs/job-large-payload");

    const summary = await screen.findByText("Submitted input");
    const details = summary.closest("details");
    expect(details).not.toHaveAttribute("open");

    fireEvent.click(summary);
    expect(details).toHaveAttribute("open");
    expect(within(details as HTMLElement).getByText(/large line 29/)).toBeInTheDocument();
  });
});
