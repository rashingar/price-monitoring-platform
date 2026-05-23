import type { FormEvent } from "react";

export function SourceUrlManualForm({
  canLoad,
  isCreating,
  newUrl,
  newSourceName,
  onNewUrlChange,
  onNewSourceNameChange,
  onSubmit,
}: {
  canLoad: boolean;
  isCreating: boolean;
  newUrl: string;
  newSourceName: string;
  onNewUrlChange: (value: string) => void;
  onNewSourceNameChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  return (
    <form className="source-url-add-form" onSubmit={onSubmit}>
      <label className="inline-field wide">
        Manual URL
        <input
          type="url"
          value={newUrl}
          onChange={(event) => onNewUrlChange(event.target.value)}
          placeholder="https://example.com/product"
          disabled={!canLoad || isCreating}
        />
      </label>
      <label
        className="inline-field"
        title="Source name identifies the vendor or registry source used for source URL capture."
      >
        Source name
        <input
          type="text"
          value={newSourceName}
          onChange={(event) => onNewSourceNameChange(event.target.value)}
          placeholder="electronet, public, plaisio, kotsovolos"
          disabled={!canLoad || isCreating}
        />
      </label>
      <button className="button primary" type="submit" disabled={!canLoad || isCreating || newUrl.trim().length === 0}>
        {isCreating ? "Adding..." : "Add URL"}
      </button>
    </form>
  );
}
