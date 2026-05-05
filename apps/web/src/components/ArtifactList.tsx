import { useState } from "react";
import type { ArtifactItem } from "../api/commerceTypes";
import { EmptyState } from "./layout/StateBlocks";
import { parseCsvPreview } from "../utils/csvPreview";

interface ArtifactListProps {
  title: string;
  items: ArtifactItem[];
  onPreview: (path: string) => Promise<string>;
  getDownloadUrl: (path: string) => string;
}

const TEXT_EXTENSIONS = new Set([".csv", ".json", ".txt", ".log"]);
const CSV_VISIBLE_ROWS = 500;

interface PreviewState {
  item: ArtifactItem;
  content: string | null;
  viewAsText: boolean;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return String(value);
}

function formatSize(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }

  if (value < 1024) {
    return `${value.toLocaleString()} B`;
  }

  if (value < 1024 * 1024) {
    return `${(value / 1024).toLocaleString(undefined, { maximumFractionDigits: 1 })} KB`;
  }

  return `${(value / (1024 * 1024)).toLocaleString(undefined, { maximumFractionDigits: 1 })} MB`;
}

function getExtension(item: ArtifactItem): string {
  if (item.extension) {
    return item.extension.toLowerCase();
  }

  const dotIndex = item.name.lastIndexOf(".");
  return dotIndex >= 0 ? item.name.slice(dotIndex).toLowerCase() : "";
}

function formatArtifactWarning(warning: string | null | undefined): string {
  if (!warning) {
    return "Unavailable";
  }

  if (warning === "outside_configured_artifact_roots") {
    return "Outside configured artifact roots";
  }

  return warning
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^\w/, (first) => first.toUpperCase());
}

function getArtifactStatus(item: ArtifactItem): string {
  return item.is_allowed ? "Available" : `Disabled - ${formatArtifactWarning(item.warning)}`;
}

export function ArtifactList({
  title,
  items,
  onPreview,
  getDownloadUrl,
}: ArtifactListProps) {
  const [previewTitle, setPreviewTitle] = useState<string | null>(null);
  const [previewState, setPreviewState] = useState<PreviewState | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  const preview = async (item: ArtifactItem) => {
    if (!item.is_allowed || !item.can_read) {
      return;
    }

    setIsPreviewLoading(true);
    setPreviewTitle(item.name);
    setPreviewState({ item, content: null, viewAsText: false });
    setPreviewError(null);

    try {
      const content = await onPreview(item.path);
      setPreviewState({ item, content, viewAsText: false });
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsPreviewLoading(false);
    }
  };

  return (
    <div className="artifact-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Artifacts</p>
          <h3>{title}</h3>
        </div>
      </div>

      {items.length === 0 ? (
        <EmptyState title="No artifacts yet" message="The backend returned no artifacts for this run." />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Extension</th>
                <th>Size</th>
                <th>Modified</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => {
                const extension = getExtension(item);
                const canPreview =
                  item.is_allowed &&
                  item.can_read &&
                  TEXT_EXTENSIONS.has(extension) &&
                  Boolean(item.read_url || item.path);
                const canDownload =
                  item.is_allowed &&
                  item.can_download &&
                  Boolean(item.download_url || item.path);
                const downloadUrl = item.download_url || getDownloadUrl(item.path);

                return (
                  <tr key={`${item.path}-${index}`}>
                    <td>
                      <strong>{item.name}</strong>
                      <small className="artifact-path">{item.path}</small>
                    </td>
                    <td>
                      <span className={`status-badge ${item.is_allowed ? "ok" : "warning"}`}>
                        {getArtifactStatus(item)}
                      </span>
                    </td>
                    <td>{formatValue(extension)}</td>
                    <td>{formatSize(item.size_bytes)}</td>
                    <td>{formatValue(item.modified_at)}</td>
                    <td>
                      <div className="button-row">
                        <button
                          className="button secondary"
                          type="button"
                          disabled={!canPreview || isPreviewLoading}
                          onClick={() => void preview(item)}
                        >
                          Preview
                        </button>
                        {canDownload ? (
                          <a
                            className="button secondary"
                            href={downloadUrl}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Download
                          </a>
                        ) : (
                          <span className="button secondary disabled-link" aria-disabled="true">
                            Download
                          </span>
                        )}
                      </div>
                      {!item.is_allowed ? (
                        <small className="artifact-warning">
                          {formatArtifactWarning(item.warning)}
                        </small>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {previewTitle ? (
        <div className="artifact-preview">
          <div className="section-heading">
            <strong>{previewTitle}</strong>
            <button
              className="button secondary"
              type="button"
              onClick={() => {
                setPreviewTitle(null);
                setPreviewState(null);
                setPreviewError(null);
              }}
            >
              Close
            </button>
          </div>
          {isPreviewLoading ? <p className="muted">Loading preview...</p> : null}
          {previewError ? <p className="form-error">{previewError}</p> : null}
          {previewState?.content !== null && previewState?.content !== undefined ? (
            <ArtifactPreviewContent
              item={previewState.item}
              content={previewState.content}
              viewAsText={previewState.viewAsText}
              onToggleText={() =>
                setPreviewState((current) =>
                  current ? { ...current, viewAsText: !current.viewAsText } : current,
                )
              }
              downloadUrl={getDownloadUrl(previewState.item.download_url || previewState.item.path)}
            />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function ArtifactPreviewContent({
  item,
  content,
  viewAsText,
  onToggleText,
  downloadUrl,
}: {
  item: ArtifactItem;
  content: string;
  viewAsText: boolean;
  onToggleText: () => void;
  downloadUrl: string;
}) {
  const extension = getExtension(item);
  const canDownload = item.is_allowed && item.can_download && downloadUrl.trim().length > 0;

  if (extension === ".csv" && !viewAsText) {
    const preview = parseCsvPreview(content);
    const visibleRows = preview.rows.slice(0, CSV_VISIBLE_ROWS);
    const isTruncated = preview.rowCount > visibleRows.length;

    if (preview.columns.length > 0) {
      return (
        <div className="artifact-preview-content">
          <div className="toolbar">
            <dl className="artifact-preview-meta">
              <div>
                <dt>Path</dt>
                <dd>{item.path}</dd>
              </div>
              <div>
                <dt>Delimiter</dt>
                <dd>{preview.delimiter === "\t" ? "tab" : preview.delimiter}</dd>
              </div>
              <div>
                <dt>Rows</dt>
                <dd>{preview.rowCount.toLocaleString()}</dd>
              </div>
              <div>
                <dt>Visible</dt>
                <dd>{visibleRows.length.toLocaleString()}</dd>
              </div>
            </dl>
            <div className="button-row">
              <button className="button secondary" type="button" onClick={onToggleText}>
                View as text
              </button>
              {canDownload ? (
                <a className="button secondary" href={downloadUrl} target="_blank" rel="noreferrer">
                  Download
                </a>
              ) : null}
            </div>
          </div>

          {preview.parseWarning ? <p className="form-error">{preview.parseWarning}</p> : null}
          {isTruncated ? (
            <p className="muted">Showing first {CSV_VISIBLE_ROWS.toLocaleString()} rows.</p>
          ) : null}

          <div className="table-wrap csv-preview-table-wrap">
            <table>
              <thead>
                <tr>
                  {preview.columns.map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {preview.columns.map((column) => (
                      <td key={column}>{row[column]}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      );
    }
  }

  if (extension === ".json" && !viewAsText) {
    let formatted = content;
    try {
      formatted = JSON.stringify(JSON.parse(content) as unknown, null, 2);
    } catch {
      formatted = content;
    }

    return (
      <div className="artifact-preview-content">
        <div className="button-row">
          <button className="button secondary" type="button" onClick={onToggleText}>
            View raw text
          </button>
          {canDownload ? (
            <a className="button secondary" href={downloadUrl} target="_blank" rel="noreferrer">
              Download
            </a>
          ) : null}
        </div>
        <pre className="json-block">{formatted}</pre>
      </div>
    );
  }

  return (
    <div className="artifact-preview-content">
      <div className="button-row">
        {extension === ".csv" || extension === ".json" ? (
          <button className="button secondary" type="button" onClick={onToggleText}>
            {viewAsText ? "View parsed" : "View as text"}
          </button>
        ) : null}
        {canDownload ? (
          <a className="button secondary" href={downloadUrl} target="_blank" rel="noreferrer">
            Download
          </a>
        ) : null}
      </div>
      <pre className="json-block">{content}</pre>
    </div>
  );
}
