import { DEFAULT_LIMIT } from "./sourceUrlCandidateConstants";

interface SourceUrlCandidatesPaginationProps {
  offset: number;
  total: number;
  isLoading: boolean;
  currentPage: number;
  totalPages: number;
  onOffsetChange: (nextOffset: number | ((current: number) => number)) => void;
}

export function SourceUrlCandidatesPagination({
  offset,
  total,
  isLoading,
  currentPage,
  totalPages,
  onOffsetChange,
}: SourceUrlCandidatesPaginationProps) {
  return (
    <div className="pagination-row">
      <button
        className="button secondary"
        type="button"
        disabled={offset <= 0 || isLoading}
        onClick={() => onOffsetChange((current) => Math.max(0, current - DEFAULT_LIMIT))}
      >
        Previous
      </button>
      <span className="muted">
        Page {currentPage} of {totalPages}
      </span>
      <button
        className="button secondary"
        type="button"
        disabled={offset + DEFAULT_LIMIT >= total || isLoading}
        onClick={() => onOffsetChange((current) => current + DEFAULT_LIMIT)}
      >
        Next
      </button>
    </div>
  );
}
