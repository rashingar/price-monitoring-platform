import { Fragment, useEffect, useState } from "react";
import {
  commerceClient,
  getCommerceApiErrorMessage,
} from "../../api/commerceClient";
import type {
  SourceUrlCandidate,
  SkroutzNetworkDiagnosticReport,
  SkroutzNetworkDiagnosticSummary,
} from "../../api/commerceTypes";
import { formatValue } from "./sourceUrlCandidateFormatters";
import {
  diagnosticSourceUrlId,
  diagnosticTone,
  endpointKeySummary,
  isSkroutzCandidate,
  yesNo,
} from "./sourceUrlCandidateHelpers";
import { SourceUrlCandidateEvidenceSection } from "./SourceUrlCandidateEvidenceSection";

interface SkroutzNetworkDiagnosticPanelProps {
  candidate: SourceUrlCandidate;
}

export function SkroutzNetworkDiagnosticPanel({ candidate }: SkroutzNetworkDiagnosticPanelProps) {
  const sourceUrlId = diagnosticSourceUrlId(candidate);
  const [summary, setSummary] = useState<SkroutzNetworkDiagnosticSummary | null>(null);
  const [detail, setDetail] = useState<SkroutzNetworkDiagnosticReport | null>(null);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSummary(null);
    setDetail(null);
    setExpandedIndex(null);
    setError(null);
    setIsRunning(false);
    setIsLoadingDetail(false);
  }, [candidate.id]);

  if (!isSkroutzCandidate(candidate)) {
    return null;
  }

  const runDiagnostic = async () => {
    if (sourceUrlId === null) {
      setError("This candidate is not linked to an active Skroutz source URL yet.");
      return;
    }

    setIsRunning(true);
    setError(null);
    setDetail(null);
    setExpandedIndex(null);
    try {
      const nextSummary = await commerceClient.runSkroutzNetworkDiagnostic(sourceUrlId, {
        headed: false,
        timeout_seconds: 60,
      });
      setSummary(nextSummary);
    } catch (diagnosticError) {
      setSummary(null);
      setError(getCommerceApiErrorMessage(diagnosticError));
    } finally {
      setIsRunning(false);
    }
  };

  const loadDetails = async () => {
    if (sourceUrlId === null) {
      return;
    }

    setIsLoadingDetail(true);
    setError(null);
    try {
      const report = await commerceClient.getLatestSkroutzNetworkDiagnostic(sourceUrlId);
      setDetail(report);
    } catch (detailError) {
      setError(getCommerceApiErrorMessage(detailError));
    } finally {
      setIsLoadingDetail(false);
    }
  };

  const activeSummary = summary ?? detail?.summary ?? null;
  const endpoints = detail?.captured_responses ?? [];
  const blocked = activeSummary?.blocked_or_challenge_detected === true;
  const noProductEndpoint = activeSummary && !activeSummary.best_product_data_endpoint && !activeSummary.product_data_candidate_url;

  return (
    <section className="candidate-detail-card skroutz-network-diagnostic-panel">
      <div className="section-heading compact-section-heading">
        <div>
          <p className="eyebrow">Skroutz</p>
          <h4>Browser network diagnostic</h4>
        </div>
        <button
          className="button secondary compact-button"
          type="button"
          disabled={isRunning || sourceUrlId === null}
          onClick={() => void runDiagnostic()}
        >
          {isRunning ? "Running..." : "Run browser diagnostic"}
        </button>
      </div>
      {sourceUrlId === null ? (
        <p className="form-warning">Diagnostics require an existing active Skroutz source URL.</p>
      ) : null}
      {error ? <p className="form-warning">{error}</p> : null}
      {activeSummary ? (
        <>
          <dl className="candidate-evidence-grid skroutz-diagnostic-summary-grid">
            <div>
              <dt>Best endpoint</dt>
              <dd>{formatValue(activeSummary.best_product_data_endpoint ?? activeSummary.product_data_candidate_url)}</dd>
            </div>
            <div>
              <dt>filter_products.json</dt>
              <dd>{yesNo(activeSummary.observed_filter_products_url)}</dd>
            </div>
            <div>
              <dt>shops_details.json</dt>
              <dd>{yesNo(activeSummary.observed_shops_details_url)}</dd>
            </div>
            <div>
              <dt>Captured</dt>
              <dd>{formatValue(activeSummary.captured_response_count)}</dd>
            </div>
          </dl>
          {blocked ? <p className="form-warning">Blocked or challenge-like response detected.</p> : null}
          {noProductEndpoint ? <p className="form-warning">No likely product or offer endpoint was found.</p> : null}
          {activeSummary.product_data_candidate_reason ? (
            <p className="muted">{activeSummary.product_data_candidate_reason}</p>
          ) : null}
          <button
            className="button secondary compact-button"
            type="button"
            disabled={isLoadingDetail || sourceUrlId === null}
            onClick={() => void loadDetails()}
          >
            {isLoadingDetail ? "Loading details..." : "View captured endpoint details"}
          </button>
        </>
      ) : null}
      {detail ? (
        <div className="table-wrap skroutz-diagnostic-table-wrap">
          <table>
            <thead>
              <tr>
                <th>classification</th>
                <th>status</th>
                <th>method</th>
                <th>URL</th>
                <th>content type</th>
                <th>body size</th>
                <th>derived</th>
                <th>JSON</th>
                <th>keys</th>
              </tr>
            </thead>
            <tbody>
              {endpoints.map((endpoint, index) => (
                <Fragment key={`${endpoint.url ?? "endpoint"}-${index}`}>
                  <tr>
                    <td>
                      <span className={`status-badge ${diagnosticTone(endpoint.classification)}`}>
                        {formatValue(endpoint.classification)}
                      </span>
                    </td>
                    <td>{formatValue(endpoint.status)}</td>
                    <td>{formatValue(endpoint.method)}</td>
                    <td className="source-url-candidate-cell">
                      <span className="source-url-candidate-cell-content">{formatValue(endpoint.url)}</span>
                    </td>
                    <td>{formatValue(endpoint.content_type)}</td>
                    <td>{formatValue(endpoint.body_size)}</td>
                    <td>{formatValue(endpoint.matched_derived_endpoint)}</td>
                    <td>{yesNo(endpoint.parsed_json_valid)}</td>
                    <td>
                      <button
                        className="button secondary compact-button"
                        type="button"
                        onClick={() => setExpandedIndex((current) => (current === index ? null : index))}
                      >
                        {endpointKeySummary(endpoint)}
                      </button>
                    </td>
                  </tr>
                  {expandedIndex === index ? (
                    <tr className="source-url-expanded-row">
                      <td colSpan={9}>
                        <dl className="candidate-evidence-grid">
                          <SourceUrlCandidateEvidenceSection title="Top-level keys" value={endpoint.json_summary?.top_level_keys ?? []} />
                          <SourceUrlCandidateEvidenceSection title="Body sample" value={endpoint.body_sample} />
                          <SourceUrlCandidateEvidenceSection title="Parse error" value={endpoint.json_parse_error} />
                        </dl>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
