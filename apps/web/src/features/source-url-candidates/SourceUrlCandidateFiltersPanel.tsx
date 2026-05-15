import { REVIEW_STATUSES } from "./sourceUrlCandidateConstants";
import { normalizeLabel } from "./sourceUrlCandidateFormatters";
import type { CandidateFilters } from "./sourceUrlCandidateTypes";

interface SourceUrlCandidateFiltersPanelProps {
  filters: CandidateFilters;
  onFilterChange: <Key extends keyof CandidateFilters>(key: Key, value: CandidateFilters[Key]) => void;
}

export function SourceUrlCandidateFiltersPanel({
  filters,
  onFilterChange,
}: SourceUrlCandidateFiltersPanelProps) {
  return (
    <div className="filter-grid source-url-candidate-filters">
      <label>
        Review status
        <select
          value={filters.status}
          onChange={(event) => onFilterChange("status", event.target.value as CandidateFilters["status"])}
        >
          {REVIEW_STATUSES.map((status) => (
            <option key={status} value={status}>
              {normalizeLabel(status)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Candidate source name
        <input
          type="search"
          value={filters.sourceName}
          onChange={(event) => onFilterChange("sourceName", event.target.value)}
          placeholder="electronet, public, plaisio, kotsovolos"
          title="Filters candidate source_name/source_domain values from the vendor/source registry."
        />
      </label>
      <label>
        Run id filter
        <input
          type="search"
          value={filters.runId}
          onChange={(event) => onFilterChange("runId", event.target.value)}
        />
      </label>
      <label>
        Model
        <input
          type="search"
          value={filters.model}
          onChange={(event) => onFilterChange("model", event.target.value)}
        />
      </label>
      <label>
        Catalog product id
        <input
          type="search"
          value={filters.catalogProductId}
          onChange={(event) => onFilterChange("catalogProductId", event.target.value)}
        />
      </label>
      <label>
        Min confidence
        <input
          type="number"
          min={0}
          max={1}
          step={0.0001}
          value={filters.minConfidence}
          onChange={(event) => onFilterChange("minConfidence", event.target.value)}
        />
      </label>
      <label>
        Max confidence
        <input
          type="number"
          min={0}
          max={1}
          step={0.0001}
          value={filters.maxConfidence}
          onChange={(event) => onFilterChange("maxConfidence", event.target.value)}
        />
      </label>
      <label>
        Match method
        <input
          type="search"
          value={filters.matchMethod}
          onChange={(event) => onFilterChange("matchMethod", event.target.value)}
          placeholder="mpn, model, title"
        />
      </label>
      <label>
        Created from
        <input
          type="date"
          value={filters.createdFrom}
          onChange={(event) => onFilterChange("createdFrom", event.target.value)}
        />
      </label>
      <label>
        Created to
        <input
          type="date"
          value={filters.createdTo}
          onChange={(event) => onFilterChange("createdTo", event.target.value)}
        />
      </label>
    </div>
  );
}
