import { commerceClient, getArtifactPath } from "../../api/commerceClient";
import type { ArtifactPayload } from "../../api/commerceTypes";
import type { SourceUrl } from "./catalogProductDetailTypes";
import {
  formatDateTime,
  formatDetailValue,
  sourceUrlCaptureStatus,
  statusTone,
} from "./catalogProductDetailFormatters";

export function ProductSourceUrlLifecycleTable({ sourceUrls }: { sourceUrls: SourceUrl[] }) {
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
          </tr>
        </thead>
        <tbody>
          {sourceUrls.map((sourceUrl) => {
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

