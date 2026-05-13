import type { PriceMonitoringAction, PriceMonitoringSource } from "../../api/commerceTypes";

export type SourceOverride = "" | PriceMonitoringSource;
export type PriceMonitoringSourceFilter = string;

export interface RowActionState {
  selected_action: "" | PriceMonitoringAction;
  undercut_amount: string;
  reason: string;
}
