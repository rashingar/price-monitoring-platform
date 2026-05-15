import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";
import { SourceUrlAgentReadinessCard } from "../features/source-url-agent-readiness/SourceUrlAgentReadinessCard";
import { SourceUrlAgentArtifactsPanel } from "../features/source-url-agent-runs/SourceUrlAgentArtifactsPanel";
import { SourceUrlAgentHandoffPanel } from "../features/source-url-agent-runs/SourceUrlAgentHandoffPanel";
import { SourceUrlAgentLaunchPanel } from "../features/source-url-agent-runs/SourceUrlAgentLaunchPanel";
import { SourceUrlAgentRunHistoryTable } from "../features/source-url-agent-runs/SourceUrlAgentRunHistoryTable";
import { SourceUrlAgentRunSummary } from "../features/source-url-agent-runs/SourceUrlAgentRunSummary";
import { SourceUrlAgentRunsHeader } from "../features/source-url-agent-runs/SourceUrlAgentRunsHeader";
import { SourceUrlAgentWarningPanel } from "../features/source-url-agent-runs/SourceUrlAgentWarningPanel";
import { parseSelectedModelsParam } from "../features/source-url-agent-runs/sourceUrlAgentRunHandoff";
import { useSourceUrlAgentArtifacts } from "../features/source-url-agent-runs/useSourceUrlAgentArtifacts";
import { useSourceUrlAgentLaunch } from "../features/source-url-agent-runs/useSourceUrlAgentLaunch";
import { useSourceUrlAgentRuns } from "../features/source-url-agent-runs/useSourceUrlAgentRuns";
import { useSourceUrlAgentSources } from "../features/source-url-agent-runs/useSourceUrlAgentSources";

export function SourceUrlAgentRunsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const handoffModels = useMemo(() => parseSelectedModelsParam(searchParams.get("models")), [searchParams]);
  const runs = useSourceUrlAgentRuns();
  const sources = useSourceUrlAgentSources();
  const artifacts = useSourceUrlAgentArtifacts();
  const launch = useSourceUrlAgentLaunch({
    searchParams,
    setSearchParams,
    handoffModelCount: handoffModels.length,
    onRunCreated: runs.mergeRun,
  });

  const notices = [launch.notice, runs.notice].filter((notice): notice is string => Boolean(notice));

  return (
    <div className="page-stack source-url-agent-page">
      <SourceUrlAgentRunsHeader />
      <div className="source-url-agent-top-row">
        <SourceUrlAgentWarningPanel />
        <SourceUrlAgentReadinessCard
          blockLaunch
          collapsed
          className="source-url-readiness-launch-card"
          onReadinessStateChange={launch.handleReadinessStateChange}
        />
      </div>
      <SourceUrlAgentHandoffPanel
        handoffModels={handoffModels}
        isLaunching={launch.isLaunching}
        onClear={() => setSearchParams(new URLSearchParams(), { replace: true })}
      />

      <SourceUrlAgentLaunchPanel
        form={launch.form}
        discoverySourceOptions={sources.discoverySourceOptions}
        isSourcesLoading={sources.isSourcesLoading}
        sourceError={sources.sourceError}
        isLaunching={launch.isLaunching}
        isLaunchDisabled={launch.isLaunchDisabled}
        launchBlockReason={launch.launchBlockReason}
        updateForm={launch.updateForm}
        onResetDefaults={launch.resetDefaults}
        onLaunch={() => void launch.launchRun()}
      />

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">History</p>
            <h3>Run history</h3>
          </div>
          <button className="button secondary" type="button" onClick={() => void runs.loadRuns()}>
            Refresh
          </button>
        </div>

        <SourceUrlAgentRunSummary runs={runs.runs} totals={runs.totals} />

        {notices.map((notice) => (
          <p className="form-warning" key={notice}>
            {notice}
          </p>
        ))}
        {runs.isLoading ? <LoadingState label="Loading Find Source runs..." /> : null}
        {runs.error ? <ErrorState message={runs.error} onRetry={() => void runs.loadRuns()} /> : null}
        {!runs.isLoading && !runs.error && runs.runs.length === 0 ? (
          <EmptyState
            title="No Find Source runs"
            message="Launch a bounded dry-run to create candidate URLs for review."
          />
        ) : null}

        {!runs.isLoading && !runs.error ? (
          <SourceUrlAgentRunHistoryTable
            runs={runs.runs}
            refreshingRunId={runs.refreshingRunId}
            onRefreshRun={(run) => void runs.refreshRun(run)}
            onOpenArtifacts={(run) => void artifacts.openArtifacts(run)}
          />
        ) : null}
      </section>

      <SourceUrlAgentArtifactsPanel
        artifactRunId={artifacts.artifactRunId}
        artifacts={artifacts.artifacts}
        isLoading={artifacts.isArtifactsLoading}
        error={artifacts.artifactError}
        onClose={artifacts.closeArtifacts}
        onPreview={artifacts.previewArtifact}
      />
    </div>
  );
}
