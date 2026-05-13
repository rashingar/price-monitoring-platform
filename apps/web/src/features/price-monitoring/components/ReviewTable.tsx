import { useEffect, useState } from "react";
import type { PriceMonitoringReviewItem } from "../../../api/commerceTypes";
import { reviewColumnIds } from "../columns/reviewColumns";
import type { RowActionState } from "../types";
import { CompetitorResultCard } from "./CompetitorResultCard";

export function ReviewResultsTable({
  items,
  rowActions,
  dbAvailable,
  onUpdateRowAction,
}: {
  items: PriceMonitoringReviewItem[];
  rowActions: Record<string, RowActionState>;
  dbAvailable: boolean;
  onUpdateRowAction: (model: string, patch: Partial<RowActionState>) => void;
}) {
  const [selectedModel, setSelectedModel] = useState<string | null>(items[0]?.model ?? null);
  const [expandedTopListings, setExpandedTopListings] = useState<Record<string, boolean>>({});
  const [expandedExtraDetailsModel, setExpandedExtraDetailsModel] = useState<string | null>(null);

  useEffect(() => {
    if (items.length === 0) {
      setSelectedModel(null);
      return;
    }
    if (!selectedModel || !items.some((item) => item.model === selectedModel)) {
      setSelectedModel(items[0].model);
    }
  }, [items, selectedModel]);

  useEffect(() => {
    setExpandedExtraDetailsModel(null);
  }, [selectedModel]);

  const clearRowAction = (model: string) => {
    onUpdateRowAction(model, { selected_action: "", undercut_amount: "", reason: "" });
  };

  return (
    <div className="price-review-list" role="list" data-review-columns={reviewColumnIds.length}>
      {items.map((item) => (
        <CompetitorResultCard
          key={item.model}
          item={item}
          isSelected={selectedModel === item.model}
          rowActions={rowActions}
          dbAvailable={dbAvailable}
          showTopListings={Boolean(expandedTopListings[item.model])}
          showExtraDetails={expandedExtraDetailsModel === item.model}
          onSelect={setSelectedModel}
          onUpdateRowAction={onUpdateRowAction}
          onClearRowAction={clearRowAction}
          onToggleTopListings={(model) =>
            setExpandedTopListings((current) => ({
              ...current,
              [model]: !current[model],
            }))
          }
          onToggleExtraDetails={(model) =>
            setExpandedExtraDetailsModel((current) => (current === model ? null : model))
          }
        />
      ))}
    </div>
  );
}
