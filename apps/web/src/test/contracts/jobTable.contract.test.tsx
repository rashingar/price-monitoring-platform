import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { JobTable } from "../../components/jobs/JobTable";
import type { Job } from "../../api/types";

const RETRY_LABEL = "\u21bb Retry";
const RETRYING_LABEL = "\u21bb Retrying...";
const START_LABEL = "\u25b6 Start";
const STARTING_LABEL = "\u25b6 Starting...";

const activeJob: Job = {
  job_id: "job-running",
  job_type: "full_pipeline",
  status: "running",
  created_at: "2026-05-02T08:00:00Z",
  updated_at: "2026-05-02T08:00:00Z",
};

const terminalFullPipelineJob: Job = {
  job_id: "job-full-pipeline",
  job_type: "full_pipeline",
  status: "succeeded",
  created_at: "2026-05-02T07:00:00Z",
  updated_at: "2026-05-02T07:10:00Z",
};

const terminalRenderJob: Job = {
  job_id: "job-render",
  job_type: "render",
  status: "failed",
  created_at: "2026-05-02T06:00:00Z",
  updated_at: "2026-05-02T06:10:00Z",
};

function renderTable(props: Partial<Parameters<typeof JobTable>[0]> = {}) {
  return render(
    <MemoryRouter>
      <JobTable
        jobs={[activeJob, terminalFullPipelineJob, terminalRenderJob]}
        onStopJob={() => undefined}
        onRetryJob={() => undefined}
        onStartJob={() => undefined}
        {...props}
      />
    </MemoryRouter>,
  );
}

describe("JobTable actions", () => {
  it("shows Stop for active jobs and Retry/Start for terminal full pipeline jobs only", () => {
    renderTable();

    const activeRow = screen.getByText("job-running").closest("tr");
    const fullPipelineRow = screen.getByText("job-full-pipeline").closest("tr");
    const renderRow = screen.getByText("job-render").closest("tr");

    expect(activeRow).not.toBeNull();
    expect(fullPipelineRow).not.toBeNull();
    expect(renderRow).not.toBeNull();
    expect(within(activeRow as HTMLTableRowElement).getByRole("button", { name: "Stop" })).toBeInTheDocument();
    expect(within(activeRow as HTMLTableRowElement).queryByText(RETRY_LABEL)).not.toBeInTheDocument();
    expect(within(activeRow as HTMLTableRowElement).queryByText(START_LABEL)).not.toBeInTheDocument();
    expect(within(fullPipelineRow as HTMLTableRowElement).getByRole("button", { name: RETRY_LABEL })).toHaveClass("warning");
    expect(within(fullPipelineRow as HTMLTableRowElement).getByRole("button", { name: START_LABEL })).toBeInTheDocument();
    expect(within(renderRow as HTMLTableRowElement).queryByText(RETRY_LABEL)).not.toBeInTheDocument();
    expect(within(renderRow as HTMLTableRowElement).queryByText(START_LABEL)).not.toBeInTheDocument();
  });

  it("shows compact loading labels for retry and start actions", () => {
    renderTable({
      retryingJobIds: ["job-full-pipeline"],
      startingJobIds: ["job-full-pipeline"],
    });

    expect(screen.getByText(RETRYING_LABEL)).toHaveClass("compact-button", "warning");
    expect(screen.getByText(STARTING_LABEL)).toHaveClass("compact-button");
  });
});
