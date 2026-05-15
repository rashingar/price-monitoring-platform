"""Conservative source URL candidate scoring."""

from __future__ import annotations

from dataclasses import dataclass

from ecommerce.source_url_agent.composite import CompositeMismatchResult, detect_composite_mismatch
from ecommerce.source_url_agent.evidence import PageEvidence
from ecommerce.source_url_agent.products import AgentProduct
from ecommerce.source_url_agent.sources import SourceDefinition


BLOCKED_REVIEW_CONFIDENCE = 0.80
BLOCKED_REVIEW_ERROR_CODES = {"blocked_or_captcha", "http_403"}
URL_EVIDENCE_REVIEW_CONFIDENCE = 0.80
URL_EVIDENCE_ERROR_CODES = {"inaccessible", "timeout"}
URL_OR_META_IDENTIFIER_SOURCES = {"url", "meta"}
PROVIDER_SEARCH_RESULT_REVIEW_CONFIDENCE = 0.80


@dataclass(frozen=True)
class CandidateScore:
    confidence_score: float
    match_status: str
    match_method: str
    notes: str
    composite: CompositeMismatchResult | None = None


def score_candidate(
    *,
    product: AgentProduct,
    source: SourceDefinition,
    evidence: PageEvidence,
    competing_candidates_count: int = 0,
) -> CandidateScore:
    if evidence.error_code:
        if (
            evidence.error_code in URL_EVIDENCE_ERROR_CODES
            and _evidence_has_valid_product_url(source, evidence)
            and evidence.exact_mpn_found
            and evidence.brand_found
        ):
            return CandidateScore(
                URL_EVIDENCE_REVIEW_CONFIDENCE,
                "needs_review",
                "url_identifier_and_brand_inaccessible",
                "Candidate URL contains exact MPN and brand evidence but the page could not be fetched.",
            )
        if evidence.error_code in BLOCKED_REVIEW_ERROR_CODES and _evidence_has_valid_product_url(source, evidence):
            return CandidateScore(
                BLOCKED_REVIEW_CONFIDENCE,
                "needs_review",
                "blocked_product_url",
                "Candidate URL matches source product URL rules but the page was blocked during fetch.",
            )
        return CandidateScore(0.0, "error", evidence.error_code, evidence.error_message)
    if evidence.blocked_or_captcha:
        if _evidence_has_valid_product_url(source, evidence):
            return CandidateScore(
                BLOCKED_REVIEW_CONFIDENCE,
                "needs_review",
                "blocked_product_url",
                "Candidate URL matches source product URL rules but the page was blocked during fetch.",
            )
        return CandidateScore(0.0, "error", "blocked_or_captcha", "Blocked page or CAPTCHA marker detected.")

    composite = detect_composite_mismatch(product, evidence)
    if composite.is_mismatch:
        return CandidateScore(
            0.0,
            "not_found",
            "composite_product_mismatch",
            _composite_notes(composite),
            composite,
        )

    confidence = 0.0
    method = "manual_review_required"
    notes: list[str] = []

    if evidence.exact_mpn_found and evidence.brand_found:
        confidence = 1.0
        method = "exact_mpn_and_brand"
    else:
        if evidence.exact_mpn_found:
            confidence = 0.85
            notes.append("Exact MPN found without matching brand evidence.")
        elif evidence.exact_model_found:
            confidence = 0.60
            notes.append("Exact model evidence is not enough for Source URL Agent auto-approval.")
        elif evidence.title_similarity >= 0.50 or evidence.brand_found or evidence.category_compatible:
            confidence = max(0.50, min(0.75, evidence.title_similarity))
            notes.append("Candidate does not satisfy exact MPN and brand matching.")
        else:
            notes.append("Candidate does not satisfy exact MPN and brand matching.")

    if (
        source.source_type == "marketplace"
        and evidence.exact_mpn_found
        and evidence.exact_mpn_source == "body"
        and evidence.evidence_source != "provider_search_result"
    ):
        confidence = min(confidence, 0.60)
        notes.append("Marketplace MPN evidence was found only in body text, not title or structured data.")
    if (
        source.source_type == "marketplace"
        and evidence.exact_mpn_found
        and evidence.exact_mpn_source in URL_OR_META_IDENTIFIER_SOURCES
    ):
        confidence = min(confidence, 0.88 if evidence.exact_mpn_source == "meta" else 0.80)
        notes.append(
            "Marketplace MPN evidence was found only in metadata or the product URL, not title or structured data."
        )
    if evidence.evidence_source == "provider_search_result" and confidence > 0:
        confidence = min(confidence, PROVIDER_SEARCH_RESULT_REVIEW_CONFIDENCE)
        notes.append("Evidence came from provider search result title/snippets, not a fetched product page.")
    if evidence.price_compatible is True and confidence > 0:
        confidence = min(1.0, confidence + 0.02)
    elif evidence.price_compatible is False:
        confidence = max(0.0, confidence - 0.10)
        notes.append("Visible price is far from own price.")

    if evidence.title_only:
        confidence = min(confidence, 0.50)
        notes.append("Title-only matches are never auto-applied.")

    confidence = round(confidence, 4)
    if competing_candidates_count > 1 and confidence >= 0.50:
        return CandidateScore(
            confidence,
            "needs_review",
            method,
            _notes([*notes, f"{competing_candidates_count} plausible candidates found."]),
        )
    if confidence > 0.90 and method == "exact_mpn_and_brand" and not evidence.title_only:
        return CandidateScore(confidence, "matched", method, _notes(notes))
    return CandidateScore(confidence, "needs_review", method, _notes(notes))


def _notes(values: list[str]) -> str:
    return " ".join(dict.fromkeys(value for value in values if value))


def _composite_notes(result: CompositeMismatchResult) -> str:
    parts = [f"Composite product mismatch: {result.reason}."]
    if result.markers:
        parts.append(f"markers={', '.join(result.markers)}.")
    if result.extra_identifiers:
        parts.append(f"extra_identifiers={', '.join(result.extra_identifiers)}.")
    return " ".join(parts)


def _evidence_has_valid_product_url(source: SourceDefinition, evidence: PageEvidence) -> bool:
    return any(
        source.is_product_url(url)
        for url in (evidence.requested_url, evidence.canonical_url, evidence.final_url)
        if url
    )
