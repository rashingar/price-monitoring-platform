import type { SourceUrl, SourceUrlStatus } from "../../api/commerceTypes";
import {
  formatArtifactReference,
  formatDate,
  formatValue,
  hasCaptureMetadata,
  normalizeActionLabel,
  sourceUrlId,
  sourceUrlProvenanceLabel,
  sourceUrlStatusClass,
} from "./sourceUrlDrawerUtils";

export type SourceUrlEditDraft = {
  url: string;
  source_name: string;
  notes: string;
};

export function SourceUrlTable({
  items,
  disabled,
  pendingActionId,
  editingId,
  editDraft,
  onEditDraftChange,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onValidate,
  onUpdateStatus,
}: {
  items: SourceUrl[];
  disabled: boolean;
  pendingActionId: string | number | null;
  editingId: string | number | null;
  editDraft: SourceUrlEditDraft;
  onEditDraftChange: (draft: SourceUrlEditDraft) => void;
  onStartEdit: (sourceUrl: SourceUrl) => void;
  onCancelEdit: () => void;
  onSaveEdit: (sourceUrl: SourceUrl) => void;
  onValidate: (sourceUrl: SourceUrl) => void;
  onUpdateStatus: (sourceUrl: SourceUrl, status: SourceUrlStatus) => void;
}) {
  const showCaptureColumns = items.some(hasCaptureMetadata);
  return (
    <div className="table-wrap source-url-table-wrap">
      <table>
        <thead>
          <tr>
            <th>Source name</th>
            <th>Domain</th>
            <th>URL</th>
            <th>Status</th>
            <th>Origin</th>
            <th>Type</th>
            <th>Trust</th>
            <th>Failures</th>
            <th>Last success</th>
            <th>Last failed</th>
            <th>Last error</th>
            {showCaptureColumns ? <th>Product source</th> : null}
            {showCaptureColumns ? <th>Capture</th> : null}
            {showCaptureColumns ? <th>Snapshot</th> : null}
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.length > 0 ? (
            items.map((sourceUrl, index) => {
              const id = sourceUrlId(sourceUrl);
              const isPending = pendingActionId !== null && pendingActionId === id;
              const isEditing = editingId !== null && editingId === id;
              return (
                <tr key={`${id ?? sourceUrl.url}-${index}`}>
                  <td>
                    {isEditing ? (
                      <input
                        className="table-input"
                        type="text"
                        value={editDraft.source_name}
                        onChange={(event) => onEditDraftChange({ ...editDraft, source_name: event.target.value })}
                        disabled={isPending}
                        aria-label={`Edit source name for ${sourceUrl.url}`}
                      />
                    ) : (
                      formatValue(sourceUrl.source_name)
                    )}
                  </td>
                  <td>{formatValue(sourceUrl.source_domain)}</td>
                  <td className="source-url-cell">
                    {isEditing ? (
                      <div className="source-url-edit-form">
                        <label>
                          URL
                          <textarea
                            value={editDraft.url}
                            onChange={(event) => onEditDraftChange({ ...editDraft, url: event.target.value })}
                            disabled={isPending}
                            aria-label={`Edit URL for ${sourceUrl.url}`}
                          />
                        </label>
                        <label>
                          Notes
                          <textarea
                            value={editDraft.notes}
                            onChange={(event) => onEditDraftChange({ ...editDraft, notes: event.target.value })}
                            disabled={isPending}
                            aria-label={`Edit notes for ${sourceUrl.url}`}
                          />
                        </label>
                      </div>
                    ) : (
                      <>
                        <a href={sourceUrl.url} target="_blank" rel="noreferrer">
                          {sourceUrl.url}
                        </a>
                        {sourceUrl.url_normalized && sourceUrl.url_normalized !== sourceUrl.url ? (
                          <span className="artifact-path">Normalized: {sourceUrl.url_normalized}</span>
                        ) : null}
                      </>
                    )}
                  </td>
                  <td>
                    <span className={`status-badge ${sourceUrlStatusClass(sourceUrl.status)}`}>
                      {normalizeActionLabel(sourceUrl.status)}
                    </span>
                  </td>
                  <td>
                    <span className="status-badge neutral">{sourceUrlProvenanceLabel(sourceUrl)}</span>
                  </td>
                  <td>{formatValue(sourceUrl.url_type)}</td>
                  <td>{formatValue(sourceUrl.trust_level)}</td>
                  <td>{formatValue(sourceUrl.failure_count)}</td>
                  <td>{formatDate(sourceUrl.last_success_at)}</td>
                  <td>{formatDate(sourceUrl.last_failed_at)}</td>
                  <td>{formatValue(sourceUrl.last_error)}</td>
                  {showCaptureColumns ? <td>{formatValue(sourceUrl.product_source_id)}</td> : null}
                  {showCaptureColumns ? (
                    <td>
                      <span className={`status-badge ${sourceUrlStatusClass(sourceUrl.capture_status ?? sourceUrl.last_capture_status ?? sourceUrl.last_fetch_status ?? null)}`}>
                        {normalizeActionLabel(
                          sourceUrl.capture_status ?? sourceUrl.last_capture_status ?? sourceUrl.last_fetch_status ?? "-",
                        )}
                      </span>
                      <small className="artifact-path">
                        {formatValue(sourceUrl.last_capture_strategy)} /{" "}
                        {formatDate(sourceUrl.last_capture_at ?? sourceUrl.last_fetched_at ?? sourceUrl.last_success_at)}
                      </small>
                    </td>
                  ) : null}
                  {showCaptureColumns ? (
                    <td>
                      {formatValue(sourceUrl.source_capture_snapshot_id ?? sourceUrl.last_capture_snapshot_id)}
                      <small className="artifact-path">
                        {formatArtifactReference(sourceUrl.full_snapshot_ref ?? sourceUrl.snapshot_ref)}
                      </small>
                    </td>
                  ) : null}
                  <td>
                    <div className="button-row source-url-actions">
                      {isEditing ? (
                        <>
                          <button
                            className="button primary compact-button"
                            type="button"
                            onClick={() => onSaveEdit(sourceUrl)}
                            disabled={disabled || isPending || id === null || editDraft.url.trim().length === 0}
                          >
                            Save
                          </button>
                          <button
                            className="button secondary compact-button"
                            type="button"
                            onClick={onCancelEdit}
                            disabled={isPending}
                          >
                            Cancel
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            className="button secondary compact-button"
                            type="button"
                            onClick={() => onStartEdit(sourceUrl)}
                            disabled={disabled || isPending || id === null}
                          >
                            Edit
                          </button>
                          <button
                            className="button secondary compact-button"
                            type="button"
                            onClick={() => onValidate(sourceUrl)}
                            disabled={disabled || isPending || id === null}
                          >
                            Validate
                          </button>
                          {sourceUrl.status === "active" ? (
                            <button
                              className="button secondary compact-button"
                              type="button"
                              onClick={() => onUpdateStatus(sourceUrl, "disabled")}
                              disabled={disabled || isPending || id === null}
                            >
                              Disable
                            </button>
                          ) : (
                            <button
                              className="button secondary compact-button"
                              type="button"
                              onClick={() => onUpdateStatus(sourceUrl, "active")}
                              disabled={disabled || isPending || id === null}
                            >
                              {sourceUrl.status === "needs_review" ? "Promote to active" : "Reactivate"}
                            </button>
                          )}
                          {sourceUrl.status !== "needs_review" ? (
                            <button
                              className="button secondary compact-button"
                              type="button"
                              onClick={() => onUpdateStatus(sourceUrl, "needs_review")}
                              disabled={disabled || isPending || id === null}
                            >
                              Mark needs_review
                            </button>
                          ) : null}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })
          ) : (
            <tr>
              <td colSpan={showCaptureColumns ? 15 : 12}>No source URLs for this product yet.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
