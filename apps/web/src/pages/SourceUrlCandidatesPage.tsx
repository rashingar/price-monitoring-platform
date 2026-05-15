import { useMemo, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../components/layout/StateBlocks";
import { DEFAULT_LIMIT } from "../features/source-url-candidates/sourceUrlCandidateConstants";
import { passesCreatedDateFilter } from "../features/source-url-candidates/sourceUrlCandidateHelpers";
import {
  isColumnVisible,
  normalizeColumns,
} from "../features/source-url-candidates/sourceUrlCandidateLayout";
import { SourceUrlCandidateFiltersPanel } from "../features/source-url-candidates/SourceUrlCandidateFiltersPanel";
import { SourceUrlCandidateLayoutSettingsCard } from "../features/source-url-candidates/SourceUrlCandidateLayoutSettingsCard";
import { SourceUrlCandidatesHeader } from "../features/source-url-candidates/SourceUrlCandidatesHeader";
import { SourceUrlCandidatesPagination } from "../features/source-url-candidates/SourceUrlCandidatesPagination";
import { SourceUrlCandidatesTable } from "../features/source-url-candidates/SourceUrlCandidatesTable";
import { SourceUrlCandidatesToolbar } from "../features/source-url-candidates/SourceUrlCandidatesToolbar";
import { SourceUrlAgentReadinessCard } from "../features/source-url-agent-readiness/SourceUrlAgentReadinessCard";
import { useSourceUrlCandidateFilters } from "../features/source-url-candidates/useSourceUrlCandidateFilters";
import { useSourceUrlCandidateLayout } from "../features/source-url-candidates/useSourceUrlCandidateLayout";
import { useSourceUrlCandidateReview } from "../features/source-url-candidates/useSourceUrlCandidateReview";
import { useSourceUrlCandidates } from "../features/source-url-candidates/useSourceUrlCandidates";

export function SourceUrlCandidatesPage() {
  const [notice, setNotice] = useState<string | null>(null);
  const {
    filters,
    offset,
    setOffset,
    setFilter,
    resetFilters,
  } = useSourceUrlCandidateFilters();
  const {
    response,
    isLoading,
    error,
    refresh,
    updateCandidateInResponse,
  } = useSourceUrlCandidates(filters, offset);
  const {
    layout,
    setLayout,
    isLayoutSaving,
    layoutError,
    saveLayout,
    resetLayout,
  } = useSourceUrlCandidateLayout(setNotice);
  const {
    pendingCandidateId,
    selectedCandidateId,
    selectedCandidate,
    isDetailLoading,
    toggleCandidateReview,
    reviewCandidate,
  } = useSourceUrlCandidateReview({
    updateCandidateInState: updateCandidateInResponse,
    setNotice,
  });

  const visibleCandidates = useMemo(
    () =>
      response.items.filter((candidate) => {
        const matchesMethod =
          filters.matchMethod.trim().length === 0 ||
          (candidate.match_method ?? "")
            .toLowerCase()
            .includes(filters.matchMethod.trim().toLowerCase());
        return matchesMethod && passesCreatedDateFilter(candidate, filters);
      }),
    [filters, response.items],
  );

  const tableColumns = useMemo(
    () => normalizeColumns(layout.columns).filter(isColumnVisible),
    [layout.columns],
  );
  const totalPages = Math.max(1, Math.ceil(response.total / DEFAULT_LIMIT));
  const currentPage = Math.floor(offset / DEFAULT_LIMIT) + 1;

  return (
    <div className="page-stack source-url-candidates-page">
      <SourceUrlCandidatesHeader />

      <SourceUrlAgentReadinessCard compact />

      <SourceUrlCandidateLayoutSettingsCard
        layout={layout}
        error={layoutError}
        isSaving={isLayoutSaving}
        onChange={setLayout}
        onSave={() => void saveLayout()}
        onReset={() => void resetLayout()}
      />

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Filters</p>
            <h3>Candidate queue</h3>
          </div>
          <button className="button secondary" type="button" onClick={() => void refresh()}>
            Refresh
          </button>
        </div>

        <SourceUrlCandidateFiltersPanel filters={filters} onFilterChange={setFilter} />

        <SourceUrlCandidatesToolbar
          visibleCount={visibleCandidates.length}
          totalCount={response.total}
          onResetFilters={resetFilters}
        />

        {notice ? <p className="form-warning">{notice}</p> : null}
        {isLoading ? <LoadingState label="Loading Find Source candidates..." /> : null}
        {error ? <ErrorState message={error} onRetry={() => void refresh()} /> : null}
        {!isLoading && !error && visibleCandidates.length === 0 ? (
          <EmptyState
            title="No Find Source candidates"
            message="There are no candidates for the active filters."
          />
        ) : null}

        {!isLoading && !error && visibleCandidates.length > 0 ? (
          <>
            <SourceUrlCandidatesTable
              candidates={visibleCandidates}
              tableColumns={tableColumns}
              selectedCandidateId={selectedCandidateId}
              selectedCandidate={selectedCandidate}
              layout={layout}
              isDetailLoading={isDetailLoading}
              pendingCandidateId={pendingCandidateId}
              onToggleCandidateReview={(candidate) => void toggleCandidateReview(candidate)}
              onReviewCandidate={(candidate, decision, reviewedUrl, notes) =>
                void reviewCandidate(candidate, decision, reviewedUrl, notes)
              }
            />

            <SourceUrlCandidatesPagination
              offset={offset}
              total={response.total}
              isLoading={isLoading}
              currentPage={currentPage}
              totalPages={totalPages}
              onOffsetChange={setOffset}
            />
          </>
        ) : null}
      </section>
    </div>
  );
}
