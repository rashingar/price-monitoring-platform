interface SourceUrlCandidatesToolbarProps {
  visibleCount: number;
  totalCount: number;
  onResetFilters: () => void;
}

export function SourceUrlCandidatesToolbar({
  visibleCount,
  totalCount,
  onResetFilters,
}: SourceUrlCandidatesToolbarProps) {
  return (
    <div className="toolbar">
      <p className="muted">
        Showing {visibleCount.toLocaleString()} of {totalCount.toLocaleString()} candidates.
        Match method and created date are narrowed in the UI for the loaded page.
      </p>
      <button className="button secondary" type="button" onClick={onResetFilters}>
        Reset filters
      </button>
    </div>
  );
}
