import { JsonDetail } from "./JsonDetail";

interface SourceUrlCandidateEvidenceSectionProps {
  title: string;
  value: unknown;
}

export function SourceUrlCandidateEvidenceSection({
  title,
  value,
}: SourceUrlCandidateEvidenceSectionProps) {
  return (
    <div className="candidate-evidence-section">
      <dt>{title}</dt>
      <dd>
        <JsonDetail value={value} />
      </dd>
    </div>
  );
}
