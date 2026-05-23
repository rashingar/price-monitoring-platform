export function SourceUrlDrawerActions({
  canLoad,
  isLoading,
  canFindUrl,
  isDiscoveryStarting,
  findUrlDisabledReason,
  discoverySource,
  onRefresh,
  onFindUrl,
}: {
  canLoad: boolean;
  isLoading: boolean;
  canFindUrl: boolean;
  isDiscoveryStarting: boolean;
  findUrlDisabledReason: string | null;
  discoverySource: string;
  onRefresh: () => void;
  onFindUrl: () => void;
}) {
  return (
    <div className="toolbar source-url-drawer-toolbar">
      <p className="muted">Manage monitored source URLs attached to this catalog product.</p>
      <div className="button-row">
        <button
          className="button secondary"
          type="button"
          onClick={onRefresh}
          disabled={!canLoad || isLoading}
        >
          Refresh URLs
        </button>
        <button
          className="button primary"
          type="button"
          onClick={onFindUrl}
          disabled={!canFindUrl || isDiscoveryStarting}
          title={findUrlDisabledReason ?? `Search ${discoverySource}`}
        >
          {isDiscoveryStarting ? "Starting..." : "Find URL"}
        </button>
      </div>
    </div>
  );
}
