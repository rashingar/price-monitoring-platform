import type { Artifact } from "../../api/types";
import { EmptyState } from "../layout/StateBlocks";
import { JsonBlock } from "./JsonBlock";

interface ArtifactListProps {
  artifacts: Artifact[];
}

function isArtifactRecord(artifact: Artifact): artifact is Exclude<Artifact, string> {
  return typeof artifact === "object" && artifact !== null;
}

function getArtifactLabel(artifact: Artifact): string {
  if (typeof artifact === "string") {
    return artifact;
  }

  return artifact.name ?? artifact.path ?? artifact.url ?? "artifact";
}

export function ArtifactList({ artifacts }: ArtifactListProps) {
  if (artifacts.length === 0) {
    return (
      <EmptyState title="No artifacts yet" message="The backend returned an empty artifact list." />
    );
  }

  return (
    <ul className="artifact-list">
      {artifacts.map((artifact, index) => (
        <li key={`${getArtifactLabel(artifact)}-${index}`}>
          {isArtifactRecord(artifact) && artifact.url ? (
            <a href={artifact.url} target="_blank" rel="noreferrer">
              {getArtifactLabel(artifact)}
            </a>
          ) : (
            <strong>{getArtifactLabel(artifact)}</strong>
          )}
          {isArtifactRecord(artifact) ? <JsonBlock value={artifact} /> : null}
        </li>
      ))}
    </ul>
  );
}
