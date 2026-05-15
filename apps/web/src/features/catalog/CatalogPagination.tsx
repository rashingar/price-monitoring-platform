export function CatalogPagination({
  page,
  totalPages,
  isLoading,
  onPrevious,
  onNext,
}: {
  page: number;
  totalPages: number;
  isLoading: boolean;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    <div className="pagination-row">
      <button
        className="button secondary"
        type="button"
        disabled={page <= 1 || isLoading}
        onClick={onPrevious}
      >
        Previous
      </button>
      <span className="muted">
        Page {page} of {totalPages}
      </span>
      <button
        className="button secondary"
        type="button"
        disabled={page >= totalPages || isLoading}
        onClick={onNext}
      >
        Next
      </button>
    </div>
  );
}
