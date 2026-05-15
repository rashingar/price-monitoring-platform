import { useState } from "react";
import { commerceClient, getArtifactPath } from "../../api/commerceClient";
import type { ArtifactPayload } from "../../api/commerceTypes";
import type { SourceUrl } from "./catalogProductDetailTypes";
import {
  formatDateTime,
  formatDetailValue,
  sourceUrlCaptureStatus,
  statusTone,
} from "./catalogProductDetailFormatters";

export function ProductSourceUrlLifecycleTable({
  sourceUrls,
  pendingSourceUrlId,
  pendingActionLabel,
  onValidate,
  onUpdateStatus,
  onSaveNote,
}: {
  sourceUrls: SourceUrl[];
  pendingSourceUrlId: string | number | null;
  pendingActionLabel: string | null;
  onValidate: (sourceUrl: SourceUrl) => Promise<void>;
  onUpdateStatus: (sourceUrl: SourceUrl, status: string, label: string) => Promise<void>;
  onSaveNote: (sourceUrl: SourceUrl, notes: string | null) => Promise<void>;
}) {
  const [editingNoteId, setEditingNoteId] = useState<string | number | null>(null);
  const [noteDraft, setNoteDraft] = useState("");

  const startEditingNote = (sourceUrl: SourceUrl) => {
    const id = sourceUrlId(sourceUrl);
    if (id === null) {
      return;
    }
    setEditingNoteId(id);
    setNoteDraft(sourceUrl.notes ?? "");
  };

  const cancelEditingNote = () => {
    setEditingNoteId(null);
    setNoteDraft("");
  };

  const saveNote = async (sourceUrl: SourceUrl) => {
    await onSaveNote(sourceUrl, noteDraft.trim().length > 0 ? noteDraft.trim() : null);
    cancelEditingNote();
  };

  return (
    <div className="table-wrap catalog-product-source-url-table-wrap">
      <table>
        <thead>
          <tr>
            <th>Status</th>
            <th>Source</th>
            <th>URL</th>
            <th>Type / trust</th>
            <th>Last seen</th>
            <th>Last success</th>
            <th>Last failed</th>
            <th>Failures</th>
            <th>Error</th>
            <th>Capture</th>
            <th>Strategy</th>
            <th>Snapshot</th>
            <th>Created / updated</th>
            <th>Notes</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {sourceUrls.map((sourceUrl) => {
            const id = sourceUrlId(sourceUrl);
            const isPending = id !== null && String(pendingSourceUrlId) === String(id);
            const isEditingNote = id !== null && String(editingNoteId) === String(id);
            const captureStatus = sourceUrlCaptureStatus(sourceUrl);
            const snapshotPath = getArtifactPath(
              sourceUrl.full_snapshot_ref ?? sourceUrl.snapshot_ref ?? sourceUrl.artifact_ref,
            );
            return (
              <tr key={String(sourceUrl.id ?? sourceUrl.url)}>
                <td>
                  <span className={`status-badge ${statusTone(sourceUrl.status)}`}>
                    {formatDetailValue(sourceUrl.status)}
                  </span>
                </td>
                <td>
                  <strong>{formatDetailValue(sourceUrl.source_name)}</strong>
                  <span className="muted table-cell-subtext">
                    {formatDetailValue(sourceUrl.source_domain)}
                  </span>
                </td>
                <td className="url-cell">
                  <a href={sourceUrl.url} target="_blank" rel="noreferrer">
                    {sourceUrl.url}
                  </a>
                  <span className="muted table-cell-subtext">
                    source_url_id {formatDetailValue(sourceUrl.source_url_id ?? sourceUrl.id)}
                  </span>
                </td>
                <td>
                  {formatDetailValue(sourceUrl.url_type)}
                  <span className="muted table-cell-subtext">
                    {formatDetailValue(sourceUrl.trust_level)}
                  </span>
                </td>
                <td>{formatDateTime(sourceUrl.last_seen_at)}</td>
                <td>{formatDateTime(sourceUrl.last_success_at)}</td>
                <td>{formatDateTime(sourceUrl.last_failed_at)}</td>
                <td>{formatDetailValue(sourceUrl.failure_count ?? 0)}</td>
                <td className="error-cell">{formatDetailValue(sourceUrl.last_error)}</td>
                <td>
                  <span className={`status-badge ${statusTone(captureStatus)}`}>
                    {formatDetailValue(captureStatus)}
                  </span>
                  <span className="muted table-cell-subtext">
                    fetched {formatDateTime(sourceUrl.last_fetched_at)}
                  </span>
                  <span className="muted table-cell-subtext">
                    captured {formatDateTime(sourceUrl.last_capture_at)}
                  </span>
                </td>
                <td>{formatDetailValue(sourceUrl.last_capture_strategy)}</td>
                <td>
                  {snapshotPath ? (
                    <a
                      href={commerceClient.getArtifactDownloadUrl(snapshotPath)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {formatSnapshotLabel(
                        sourceUrl.full_snapshot_ref ?? sourceUrl.snapshot_ref ?? sourceUrl.artifact_ref,
                      )}
                    </a>
                  ) : (
                    "-"
                  )}
                  <span className="muted table-cell-subtext">
                    snapshot {formatDetailValue(sourceUrl.source_capture_snapshot_id)}
                  </span>
                </td>
                <td>
                  {formatDateTime(sourceUrl.created_at)}
                  <span className="muted table-cell-subtext">
                    updated {formatDateTime(sourceUrl.updated_at)}
                  </span>
                </td>
                <td className="notes-cell">
                  {isEditingNote ? (
                    <div className="source-url-note-editor">
                      <textarea
                        aria-label={`Edit note for ${sourceUrl.url}`}
                        value={noteDraft}
                        onChange={(event) => setNoteDraft(event.target.value)}
                        disabled={isPending}
                      />
                      <div className="source-url-action-row">
                        <button
                          className="button primary compact-button"
                          type="button"
                          onClick={() => void saveNote(sourceUrl)}
                          disabled={isPending}
                        >
                          Save note
                        </button>
                        <button
                          className="button secondary compact-button"
                          type="button"
                          onClick={cancelEditingNote}
                          disabled={isPending}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    formatDetailValue(sourceUrl.notes)
                  )}
                </td>
                <td>
                  <div className="source-url-detail-actions">
                    <a
                      className="button secondary compact-button"
                      href={sourceUrl.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open URL
                    </a>
                    <button
                      className="button secondary compact-button"
                      type="button"
                      onClick={() => void onValidate(sourceUrl)}
                      disabled={isPending || id === null}
                    >
                      Validate
                    </button>
                    {sourceUrl.status === "disabled" ? (
                      <button
                        className="button secondary compact-button"
                        type="button"
                        onClick={() => void onUpdateStatus(sourceUrl, "active", "Re-enable")}
                        disabled={isPending || id === null}
                      >
                        Re-enable
                      </button>
                    ) : (
                      <button
                        className="button secondary compact-button"
                        type="button"
                        onClick={() => void onUpdateStatus(sourceUrl, "disabled", "Disable")}
                        disabled={isPending || id === null}
                      >
                        Disable
                      </button>
                    )}
                    {sourceUrl.status === "broken" ? (
                      <button
                        className="button secondary compact-button"
                        type="button"
                        onClick={() => void onUpdateStatus(sourceUrl, "active", "Mark active")}
                        disabled={isPending || id === null}
                      >
                        Mark active
                      </button>
                    ) : (
                      <button
                        className="button secondary compact-button"
                        type="button"
                        onClick={() => void onUpdateStatus(sourceUrl, "broken", "Mark broken")}
                        disabled={isPending || id === null}
                      >
                        Mark broken
                      </button>
                    )}
                    <button
                      className="button secondary compact-button"
                      type="button"
                      onClick={() => startEditingNote(sourceUrl)}
                      disabled={isPending || id === null}
                    >
                      Edit note
                    </button>
                    {isPending ? (
                      <span className="status-badge queued">
                        {pendingActionLabel ?? "Updating"}...
                      </span>
                    ) : null}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function formatSnapshotLabel(value: ArtifactPayload | string | null | undefined): string {
  if (typeof value === "object" && value !== null && typeof value.name === "string") {
    return value.name;
  }
  return getArtifactPath(value) || "Snapshot";
}

export function sourceUrlId(sourceUrl: SourceUrl): string | number | null {
  return sourceUrl.source_url_id ?? sourceUrl.id ?? null;
}
