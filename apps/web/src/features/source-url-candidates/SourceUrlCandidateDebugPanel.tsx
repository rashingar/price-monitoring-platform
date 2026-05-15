import type { SourceUrlCandidate } from "../../api/commerceTypes";
import { JsonDetail } from "./JsonDetail";
import {
  formatConfidence,
  formatDate,
  formatValue,
  normalizeLabel,
  statusClass,
} from "./sourceUrlCandidateFormatters";
import { getJsonSection } from "./sourceUrlCandidateHelpers";
import { SourceUrlCandidateEvidenceSection } from "./SourceUrlCandidateEvidenceSection";

interface SourceUrlCandidateDebugPanelProps {
  candidate: SourceUrlCandidate;
}

export function SourceUrlCandidateDebugPanel({ candidate }: SourceUrlCandidateDebugPanelProps) {
  const evidence = candidate.evidence_json;
  const searchedQueries = candidate.searched_queries_json;
  const errorValue =
    getJsonSection(evidence, ["error", "error_message", "message", "error_code"]) ??
    getJsonSection(candidate, ["error", "error_message", "error_code"]);

  return (
    <div className="source-url-debug-panel">
      <dl className="candidate-detail-list source-url-debug-detail-list">
        <div>
          <dt>Status</dt>
          <dd>
            <span className={`status-badge ${statusClass(candidate.status)}`}>
              {normalizeLabel(candidate.status ?? null)}
            </span>
          </dd>
        </div>
        <div>
          <dt>Candidate URL</dt>
          <dd className="source-url-cell">{formatValue(candidate.candidate_url)}</dd>
        </div>
        <div>
          <dt>Canonical URL</dt>
          <dd className="source-url-cell">{formatValue(candidate.canonical_url)}</dd>
        </div>
        <div>
          <dt>Review notes</dt>
          <dd>{formatValue(candidate.notes)}</dd>
        </div>
        <div>
          <dt>Match method</dt>
          <dd>{formatValue(candidate.match_method)}</dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd>{formatConfidence(candidate.confidence_score)}</dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{formatDate(candidate.created_at)}</dd>
        </div>
        <div>
          <dt>Run id</dt>
          <dd>{formatValue(candidate.run_id)}</dd>
        </div>
        <div>
          <dt>Source candidate id</dt>
          <dd>{formatValue(candidate.id)}</dd>
        </div>
      </dl>
      <section className="source-url-debug-json-section">
        <h4>Searched queries</h4>
        <JsonDetail value={searchedQueries} />
      </section>
      <section className="source-url-debug-json-section">
        <h4>Matching details</h4>
        <dl className="candidate-evidence-grid">
          <SourceUrlCandidateEvidenceSection
            title="MPN evidence"
            value={getJsonSection(evidence, ["mpn_evidence", "mpn", "mpn_match"])}
          />
          <SourceUrlCandidateEvidenceSection
            title="Model evidence"
            value={getJsonSection(evidence, ["model_evidence", "model", "model_match"])}
          />
          <SourceUrlCandidateEvidenceSection
            title="Brand evidence"
            value={getJsonSection(evidence, ["brand_evidence", "brand", "manufacturer"])}
          />
          <SourceUrlCandidateEvidenceSection
            title="Category evidence"
            value={getJsonSection(evidence, ["category_evidence", "category"])}
          />
          <SourceUrlCandidateEvidenceSection
            title="Price evidence"
            value={getJsonSection(evidence, ["price_evidence", "price"])}
          />
          <SourceUrlCandidateEvidenceSection
            title="Title similarity"
            value={getJsonSection(evidence, ["title_similarity", "similarity"])}
          />
          <SourceUrlCandidateEvidenceSection
            title="Title-only flag"
            value={getJsonSection(evidence, ["title_only", "title_only_match"])}
          />
          <SourceUrlCandidateEvidenceSection title="Error" value={errorValue} />
        </dl>
      </section>
      <section className="source-url-debug-json-section">
        <h4>Raw evidence JSON</h4>
        <JsonDetail value={evidence} />
      </section>
    </div>
  );
}
