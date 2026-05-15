import type { SourceUrlAgentRunRequest } from "../../api/commerceTypes";
import { DEFAULT_RUN_REQUEST } from "./sourceUrlAgentRunConstants";

export function parseSelectedModelsParam(value: string | null): string[] {
  if (!value) {
    return [];
  }

  const seen = new Set<string>();
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => {
      if (!item || seen.has(item)) {
        return false;
      }
      seen.add(item);
      return true;
    });
}

export function buildRunRequestFromHandoff(searchParams: URLSearchParams): SourceUrlAgentRunRequest {
  const selectedModels = parseSelectedModelsParam(searchParams.get("models"));
  const source = searchParams.get("source")?.trim() || DEFAULT_RUN_REQUEST.source;
  const selectedCount = selectedModels.length;

  return {
    ...DEFAULT_RUN_REQUEST,
    source,
    selected_models: selectedModels,
    limit: selectedCount > 0 ? selectedCount : DEFAULT_RUN_REQUEST.limit,
    max_products_per_batch: selectedCount > 0 ? selectedCount : undefined,
  };
}

export function makeRunRequest(form: SourceUrlAgentRunRequest): SourceUrlAgentRunRequest {
  const selectedModels = Array.isArray(form.selected_models)
    ? parseSelectedModelsParam(form.selected_models.join(","))
    : [];
  const selectedCount = selectedModels.length;

  return {
    ...form,
    mode: String(form.mode || "catalog"),
    source: String(form.source || "all"),
    selected_models: selectedModels,
    limit:
      form.limit === null
        ? null
        : Math.max(selectedCount || 1, Number(form.limit) || DEFAULT_RUN_REQUEST.limit || 20),
    max_products_per_batch:
      selectedCount > 0
        ? Math.max(selectedCount, Number(form.max_products_per_batch) || selectedCount)
        : form.max_products_per_batch,
    rate_limit_seconds:
      form.rate_limit_seconds === null
        ? null
        : Math.max(0, Number(form.rate_limit_seconds) || DEFAULT_RUN_REQUEST.rate_limit_seconds || 2),
  };
}

export function clearAutoLaunchParam(searchParams: URLSearchParams): URLSearchParams {
  const nextParams = new URLSearchParams(searchParams);
  nextParams.delete("auto_launch");
  return nextParams;
}
