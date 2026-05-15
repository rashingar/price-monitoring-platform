import { commerceClient } from "../../api/commerceClient";
import type { ArtifactItem } from "../../api/commerceTypes";
import { ArtifactList } from "../../components/ArtifactList";
import { LoadingState } from "../../components/layout/StateBlocks";

type SourceUrlAgentArtifactsPanelProps = {
  artifactRunId: string | null;
  artifacts: ArtifactItem[];
  isLoading: boolean;
  error: string | null;
  onClose: () => void;
  onPreview: (path: string) => Promise<string>;
};

export function SourceUrlAgentArtifactsPanel({
  artifactRunId,
  artifacts,
  isLoading,
  error,
  onClose,
  onPreview,
}: SourceUrlAgentArtifactsPanelProps) {
  if (!artifactRunId) {
    return null;
  }

  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Artifacts</p>
          <h3>Run {artifactRunId}</h3>
        </div>
        <button className="button secondary" type="button" onClick={onClose}>
          Close
        </button>
      </div>
      {isLoading ? <LoadingState label="Loading run artifacts..." /> : null}
      {error ? <p className="form-warning">{error}</p> : null}
      {!isLoading ? (
        <ArtifactList
          title={`Find Source artifacts for ${artifactRunId}`}
          items={artifacts}
          onPreview={onPreview}
          getDownloadUrl={commerceClient.getArtifactDownloadUrl}
        />
      ) : null}
    </section>
  );
}
