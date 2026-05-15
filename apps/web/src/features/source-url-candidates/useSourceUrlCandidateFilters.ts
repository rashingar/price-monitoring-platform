import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { initialFilters } from "./sourceUrlCandidateConstants";
import type { CandidateFilters } from "./sourceUrlCandidateTypes";

export function useSourceUrlCandidateFilters() {
  const location = useLocation();
  const initialRunId = useMemo(() => new URLSearchParams(location.search).get("run_id") ?? "", []);
  const [filters, setFilters] = useState<CandidateFilters>({
    ...initialFilters,
    runId: initialRunId,
  });
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const runId = new URLSearchParams(location.search).get("run_id") ?? "";
    if (!runId) {
      return;
    }

    setFilters((current) => (current.runId === runId ? current : { ...current, runId }));
    setOffset(0);
  }, [location.search]);

  const setFilter = <Key extends keyof CandidateFilters>(key: Key, value: CandidateFilters[Key]) => {
    setFilters((current) => ({ ...current, [key]: value }));
    setOffset(0);
  };

  const resetFilters = () => {
    setFilters(initialFilters);
    setOffset(0);
  };

  return {
    filters,
    offset,
    setOffset,
    setFilter,
    resetFilters,
  };
}
