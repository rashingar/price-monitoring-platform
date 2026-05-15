"""Candidate conversion and retention helpers for Source URL Agent runs."""

from __future__ import annotations

from ecommerce.source_url_agent.candidates import SourceUrlAgentCandidate, candidate_from_evidence, keep_candidate, synthetic_candidate
from ecommerce.source_url_agent.evidence import PageEvidence
from ecommerce.source_url_agent.products import AgentProduct
from ecommerce.source_url_agent.scoring import score_candidate
from ecommerce.source_url_agent.search import SourceSearchResult, generate_search_queries
from ecommerce.source_url_agent.sources import SourceDefinition


def candidates_from_search_result(
    *,
    run_id: str,
    product: AgentProduct,
    source: SourceDefinition,
    expected_listing: str,
    result: SourceSearchResult,
) -> list[SourceUrlAgentCandidate]:
    evidence_items = [item for item in result.evidence if isinstance(item, PageEvidence)]
    if not evidence_items:
        queries = result.searched_queries or generate_search_queries(product, source)
        if result.errors:
            return [
                synthetic_candidate(
                    run_id=run_id,
                    product=product,
                    source=source,
                    expected_listing=expected_listing,
                    match_status="error",
                    status="error",
                    match_method="search_error",
                    searched_queries=queries,
                    notes="; ".join(result.errors),
                    extra_evidence_json={"provider_summary": result.provider_summary} if result.provider_summary else None,
                )
            ]
        return [
            synthetic_candidate(
                run_id=run_id,
                product=product,
                source=source,
                expected_listing=expected_listing,
                match_status="not_found",
                status="not_found",
                match_method="no_candidate_urls",
                searched_queries=queries,
                notes="No credible product page found.",
                extra_evidence_json={"provider_summary": result.provider_summary} if result.provider_summary else None,
            )
        ]

    first_scores = [
        score_candidate(product=product, source=source, evidence=evidence, competing_candidates_count=0)
        for evidence in evidence_items
    ]
    plausible_count = sum(1 for score in first_scores if score.confidence_score >= 0.50 and score.match_status != "error")
    candidates: list[SourceUrlAgentCandidate] = []
    for evidence in evidence_items:
        score = score_candidate(product=product, source=source, evidence=evidence, competing_candidates_count=plausible_count)
        candidates.append(
            candidate_from_evidence(
                run_id=run_id,
                product=product,
                source=source,
                evidence=evidence,
                score=score,
                expected_listing=expected_listing,
                competing_candidates_count=plausible_count,
                searched_queries=result.searched_queries,
                status=candidate_status(score.match_status),
            )
        )
    return candidates


def candidate_status(match_status: str) -> str:
    if match_status == "matched":
        return "pending"
    if match_status == "needs_review":
        return "needs_review"
    if match_status == "not_found":
        return "not_found"
    if match_status == "error":
        return "error"
    return "pending"


def candidates_for_candidate_storage(
    candidates: list[SourceUrlAgentCandidate],
    *,
    apply_source_urls: bool,
    apply_high_confidence_requested: bool,
) -> list[SourceUrlAgentCandidate]:
    del apply_source_urls, apply_high_confidence_requested
    return [candidate for candidate in candidates if keep_candidate(candidate)]
