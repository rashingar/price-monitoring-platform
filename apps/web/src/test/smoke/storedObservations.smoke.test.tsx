import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  CatalogSnapshotResponse,
  FetchPriceMonitoringResult,
  PriceMonitoringDbStatus,
  RunPriceObservationsResponse,
} from "../../api/commerceTypes";
import { StoredObservationsSection } from "../../pages/PriceMonitoringPage";

const readyDbStatus: PriceMonitoringDbStatus = {
  configured: true,
  reachable: true,
  ready_for_price_monitoring: true,
  required_tables_present: true,
  alembic_up_to_date: true,
};

const observations: RunPriceObservationsResponse = {
  run_id: "20260513-082508-276376e4",
  count: 22,
  matched_count: 22,
  unmatched_count: 0,
  items: [],
};

const fetchResult: FetchPriceMonitoringResult = {
  run_id: "20260513-082508-276376e4",
  observation_count: 22,
  matched_observation_count: 22,
  unmatched_observation_count: 0,
  fetch_attempt: 1,
  observation_batch_id: "batch-1",
  observation_history_count: 22,
  persistence_status: "stored",
};

const catalogSnapshot: CatalogSnapshotResponse = {
  run_id: "20260513-082508-276376e4",
  count: 0,
  items: [],
};

function renderStoredObservations() {
  return render(
    <StoredObservationsSection
      runId="20260513-082508-276376e4"
      dbStatus={readyDbStatus}
      isLoading={false}
      observations={observations}
      catalogSnapshot={catalogSnapshot}
      observationError={null}
      catalogSnapshotError={null}
      fetchResult={fetchResult}
      matchStatus="all"
      includeUnmatched={false}
      modelFilter=""
      mpnFilter=""
      onMatchStatusChange={vi.fn()}
      onIncludeUnmatchedChange={vi.fn()}
      onModelFilterChange={vi.fn()}
      onMpnFilterChange={vi.fn()}
      onRefresh={vi.fn()}
    />,
  );
}

describe("Stored Observations card", () => {
  it("shows only the summary fields while collapsed and reveals the rest from Details", () => {
    renderStoredObservations();

    expect(screen.getByText("Run ID")).toBeInTheDocument();
    expect(screen.getByText("20260513-082508-276376e4")).toBeInTheDocument();
    expect(screen.getByText("Total observations")).toBeInTheDocument();
    expect(screen.getByText("Matched")).toBeInTheDocument();
    expect(screen.getByText("Unmatched")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeInTheDocument();

    expect(screen.queryByText("Stored observation debugging")).not.toBeInTheDocument();
    expect(screen.queryByText("Match status")).not.toBeInTheDocument();
    expect(screen.queryByText("Observation batch")).not.toBeInTheDocument();
    expect(screen.queryByText("Catalog Snapshot")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Details" }));

    expect(screen.getByText("Stored observation debugging")).toBeInTheDocument();
    expect(screen.getByText("Match status")).toBeInTheDocument();
    expect(screen.getByText("Observation batch")).toBeInTheDocument();
    expect(screen.getByText("Catalog Snapshot")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Hide details" }));

    expect(screen.queryByText("Stored observation debugging")).not.toBeInTheDocument();
    expect(screen.queryByText("Match status")).not.toBeInTheDocument();
  });
});
