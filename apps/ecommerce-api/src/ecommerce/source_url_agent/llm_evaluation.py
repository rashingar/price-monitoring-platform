"""Optional LLM-assisted evaluation for BestPrice source URL candidates."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy.orm import Session

from ecommerce.db.repositories.common import json_safe_value
from ecommerce.source_urls import SourceUrlValidationError, normalize_source_url
from ecommerce.source_url_agent.candidates import SourceUrlAgentCandidate
from ecommerce.source_url_agent.llm_config import SourceUrlLLMConfig
from ecommerce.source_url_agent.persistence import (
    SourceUrlWriteResult,
    write_candidate_source_url,
)

OPENAI_API_KEY_ENV_VAR = "OPENAI_API_KEY"
VALID_VERDICTS = {"same_product", "different_product", "insufficient_evidence"}
VALID_APPLY_RECOMMENDATIONS = {"auto_apply", "needs_review", "reject"}
LLM_EVALUATION_KEY = "llm_evaluation"


class SourceUrlLLMEvaluationError(ValueError):
    """Raised when an LLM evaluation response cannot be trusted."""


@dataclass(frozen=True)
class SourceUrlLLMEvaluation:
    verdict: str
    confidence: Decimal
    apply_recommendation: str
    reasons: list[str]
    positive_evidence: list[str]
    negative_evidence: list[str]
    selected_candidate_url: str
    warnings: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "confidence": str(self.confidence),
            "apply_recommendation": self.apply_recommendation,
            "reasons": list(self.reasons),
            "positive_evidence": list(self.positive_evidence),
            "negative_evidence": list(self.negative_evidence),
            "selected_candidate_url": self.selected_candidate_url,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class SourceUrlLLMEvaluationRunResult:
    candidates: list[SourceUrlAgentCandidate]
    write_results: list[SourceUrlWriteResult]
    warnings: list[str]
    evaluated_count: int
    auto_applied_count: int
    needs_review_count: int
    rejected_count: int
    malformed_count: int


LLMEvaluator = Callable[
    [SourceUrlAgentCandidate, SourceUrlLLMConfig], SourceUrlLLMEvaluation
]

# Test hook and future adapter seam. Production runs use the OpenAI adapter below.
SOURCE_URL_LLM_EVALUATOR: LLMEvaluator | None = None


def evaluate_bestprice_candidates(
    session: Session | None,
    candidates: list[SourceUrlAgentCandidate],
    *,
    config: SourceUrlLLMConfig,
    auto_apply: bool,
) -> SourceUrlLLMEvaluationRunResult:
    if not config.enabled:
        return SourceUrlLLMEvaluationRunResult(candidates, [], [], 0, 0, 0, 0, 0)

    selected_indexes = _candidate_indexes_for_llm(candidates, config=config)
    updated = list(candidates)
    write_results: list[SourceUrlWriteResult] = []
    warnings: list[str] = []
    evaluated_count = 0
    auto_applied_count = 0
    needs_review_count = 0
    rejected_count = 0
    malformed_count = 0

    for index in selected_indexes:
        candidate = updated[index]
        try:
            evaluation = _evaluate_candidate(candidate, config)
        except SourceUrlLLMEvaluationError as exc:
            malformed_count += 1
            warnings.append(
                f"llm_evaluation_failed:{candidate.product.model}:{candidate.source_name}:{exc}"
            )
            continue

        evaluated_count += 1
        next_candidate = _candidate_with_llm_evaluation(candidate, evaluation)
        guard_reason = _auto_apply_guard_reason(next_candidate, evaluation, config)
        should_apply = (
            auto_apply
            and session is not None
            and not guard_reason
            and evaluation.confidence >= config.auto_apply_min_confidence
        )
        if should_apply:
            apply_candidate = _candidate_with_selected_url(next_candidate, evaluation)
            write_result = write_candidate_source_url(
                session,
                apply_candidate,
                trust_level="llm_high_confidence",
                apply=True,
                candidate_index=index,
            )
            write_results.append(write_result)
            if write_result.action in {"created", "updated", "duplicate"}:
                next_candidate = replace(apply_candidate, status="accepted")
                auto_applied_count += 1
            elif write_result.reason:
                warnings.append(f"llm_source_url_write_skipped:{write_result.reason}")
                next_candidate = _review_candidate(
                    next_candidate,
                    f"LLM auto-apply skipped: {write_result.reason}",
                )
                needs_review_count += 1
        elif evaluation.verdict == "different_product":
            next_candidate = _rejected_candidate(next_candidate)
            rejected_count += 1
        elif not auto_apply:
            next_candidate = _review_candidate(
                next_candidate, "LLM evaluation captured; auto-apply is disabled."
            )
            needs_review_count += 1
        elif auto_apply and guard_reason:
            next_candidate = _review_candidate(
                next_candidate, f"LLM auto-apply guard failed: {guard_reason}"
            )
            needs_review_count += 1
        elif evaluation.confidence >= config.review_min_confidence:
            next_candidate = _review_candidate(
                next_candidate, "LLM evaluation recommends manual review."
            )
            needs_review_count += 1

        updated[index] = next_candidate

    return SourceUrlLLMEvaluationRunResult(
        updated,
        write_results,
        warnings,
        evaluated_count,
        auto_applied_count,
        needs_review_count,
        rejected_count,
        malformed_count,
    )


def parse_llm_evaluation_payload(payload: object) -> SourceUrlLLMEvaluation:
    if not isinstance(payload, dict):
        raise SourceUrlLLMEvaluationError("LLM output must be a JSON object.")
    verdict = _required_choice(payload, "verdict", VALID_VERDICTS)
    recommendation = _required_choice(
        payload, "apply_recommendation", VALID_APPLY_RECOMMENDATIONS
    )
    confidence = _confidence(payload.get("confidence"))
    return SourceUrlLLMEvaluation(
        verdict=verdict,
        confidence=confidence,
        apply_recommendation=recommendation,
        reasons=_string_list(payload.get("reasons")),
        positive_evidence=_string_list(payload.get("positive_evidence")),
        negative_evidence=_string_list(payload.get("negative_evidence")),
        selected_candidate_url=str(payload.get("selected_candidate_url") or "").strip(),
        warnings=_string_list(payload.get("warnings")),
    )


def compact_candidate_payload(candidate: SourceUrlAgentCandidate) -> dict[str, Any]:
    evidence = candidate.evidence_json
    provider_provenance = evidence.get("provider_provenance")
    return {
        "product": {
            "model": _bounded_text(candidate.product.model),
            "mpn": _bounded_text(candidate.product.mpn),
            "manufacturer": _bounded_text(candidate.product.manufacturer),
            "product_name": _bounded_text(candidate.product.name),
            "category": _bounded_text(candidate.product.category),
            "own_price": json_safe_value(candidate.product.price),
        },
        "candidate": {
            "candidate_url": _bounded_text(candidate.candidate_url, limit=500),
            "canonical_url": _bounded_text(candidate.canonical_url, limit=500),
            "candidate_title": _bounded_text(candidate.candidate_title),
            "candidate_price": json_safe_value(candidate.candidate_price),
            "source_name": candidate.source_name,
            "source_domain": candidate.source_domain,
            "deterministic_match_status": candidate.match_status,
            "deterministic_confidence_score": candidate.confidence_score,
            "deterministic_match_method": candidate.match_method,
            "competing_candidates_count": candidate.competing_candidates_count,
            "searched_queries": [
                _bounded_text(query) for query in list(candidate.searched_queries)[:10]
            ],
            "provider_provenance": _compact_provider_provenance(provider_provenance),
        },
        "evidence_summary": _compact_evidence(evidence),
    }


def _candidate_indexes_for_llm(
    candidates: list[SourceUrlAgentCandidate], *, config: SourceUrlLLMConfig
) -> list[int]:
    indexes: list[int] = []
    call_limit = min(config.max_candidates, config.max_calls_per_run)
    if call_limit <= 0:
        return []
    for index, candidate in enumerate(candidates):
        if len(indexes) >= call_limit:
            break
        if _candidate_is_llm_eligible(candidate):
            indexes.append(index)
    return indexes


def _candidate_is_llm_eligible(candidate: SourceUrlAgentCandidate) -> bool:
    if candidate.status == "accepted":
        return False
    if candidate.source_name != "bestprice":
        return False
    if candidate.match_status not in {"matched", "needs_review"}:
        return False
    if candidate.confidence_score < 0.50:
        return False
    if not (candidate.candidate_url or candidate.canonical_url):
        return False
    return _has_meaningful_product_evidence(candidate)


def _evaluate_candidate(
    candidate: SourceUrlAgentCandidate, config: SourceUrlLLMConfig
) -> SourceUrlLLMEvaluation:
    if SOURCE_URL_LLM_EVALUATOR is not None:
        return SOURCE_URL_LLM_EVALUATOR(candidate, config)
    return _evaluate_candidate_with_openai(candidate, config)


def _evaluate_candidate_with_openai(
    candidate: SourceUrlAgentCandidate, config: SourceUrlLLMConfig
) -> SourceUrlLLMEvaluation:
    api_key = str(os.environ.get(OPENAI_API_KEY_ENV_VAR) or "").strip()
    if not api_key:
        raise SourceUrlLLMEvaluationError("OPENAI_API_KEY is required.")
    prompt = _evaluation_prompt(compact_candidate_payload(candidate))
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SourceUrlLLMEvaluationError("OpenAI Python SDK is not installed.") from exc
    client = OpenAI(api_key=api_key)
    request_payload: dict[str, Any] = {"model": config.model, "input": prompt}
    if config.reasoning_effort:
        request_payload["reasoning"] = {"effort": config.reasoning_effort}
    response = client.responses.create(**request_payload)
    output_text = getattr(response, "output_text", "")
    if not isinstance(output_text, str) or not output_text.strip():
        raise SourceUrlLLMEvaluationError("LLM returned empty output.")
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise SourceUrlLLMEvaluationError("LLM output was not valid JSON.") from exc
    return parse_llm_evaluation_payload(payload)


def _evaluation_prompt(payload: dict[str, Any]) -> str:
    return (
        "Evaluate whether this BestPrice candidate URL is the same product as the "
        "catalog product. Return only JSON with keys: verdict, confidence, "
        "apply_recommendation, reasons, positive_evidence, negative_evidence, "
        "selected_candidate_url, warnings. Use verdict same_product, different_product, "
        "or insufficient_evidence. Use apply_recommendation auto_apply, needs_review, "
        "or reject. Be conservative.\n\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
    )


def _candidate_with_llm_evaluation(
    candidate: SourceUrlAgentCandidate, evaluation: SourceUrlLLMEvaluation
) -> SourceUrlAgentCandidate:
    evidence_json = dict(candidate.evidence_json)
    evidence_json[LLM_EVALUATION_KEY] = evaluation.to_json()
    note = "LLM evaluation: " + "; ".join(
        item for item in evaluation.reasons[:3] if item
    )
    return replace(
        candidate,
        evidence_json=evidence_json,
        notes=_append_note(candidate.notes, note) if note.strip() else candidate.notes,
    )


def _candidate_with_selected_url(
    candidate: SourceUrlAgentCandidate, evaluation: SourceUrlLLMEvaluation
) -> SourceUrlAgentCandidate:
    selected = evaluation.selected_candidate_url.strip()
    if not selected:
        return candidate
    canonical = candidate.source.canonical_candidate_url(selected)
    return replace(candidate, candidate_url=selected, canonical_url=canonical)


def _auto_apply_guard_reason(
    candidate: SourceUrlAgentCandidate,
    evaluation: SourceUrlLLMEvaluation,
    config: SourceUrlLLMConfig,
) -> str:
    if candidate.source_name != "bestprice":
        return "source_not_bestprice"
    selected_url = evaluation.selected_candidate_url or candidate.canonical_url or candidate.candidate_url
    if not selected_url:
        return "candidate_url_missing"
    if not _selected_url_matches_candidate(candidate, selected_url):
        return "selected_url_not_candidate"
    if not candidate.source.is_product_url(selected_url):
        return "not_bestprice_product_url"
    canonical = candidate.source.canonical_candidate_url(selected_url)
    if not canonical or not candidate.source.is_product_url(canonical):
        return "canonical_url_invalid"
    try:
        normalize_source_url(canonical)
    except SourceUrlValidationError:
        return "url_normalization_failed"
    if evaluation.verdict != "same_product":
        return "verdict_not_same_product"
    if evaluation.apply_recommendation != "auto_apply":
        return "recommendation_not_auto_apply"
    if evaluation.confidence < config.auto_apply_min_confidence:
        return "confidence_below_auto_apply_threshold"
    if not _has_meaningful_product_evidence(candidate):
        return "weak_product_evidence"
    return ""


def _has_meaningful_product_evidence(candidate: SourceUrlAgentCandidate) -> bool:
    evidence = candidate.evidence_json
    if bool(evidence.get("title_only")):
        return False
    mpn = evidence.get("mpn")
    model = evidence.get("model")
    brand = evidence.get("brand")
    if isinstance(mpn, dict) and mpn.get("found"):
        return True
    if isinstance(model, dict) and model.get("found"):
        return True
    if isinstance(brand, dict) and brand.get("found") and candidate.confidence_score >= 0.75:
        return True
    return False


def _review_candidate(
    candidate: SourceUrlAgentCandidate, note: str
) -> SourceUrlAgentCandidate:
    return replace(
        candidate,
        match_status=(
            "needs_review" if candidate.match_status == "matched" else candidate.match_status
        ),
        status="needs_review",
        notes=_append_note(candidate.notes, note),
    )


def _rejected_candidate(candidate: SourceUrlAgentCandidate) -> SourceUrlAgentCandidate:
    return replace(
        candidate,
        status="rejected",
        notes=_append_note(candidate.notes, "LLM evaluation marked a different product."),
    )


def _append_note(current: str, note: str) -> str:
    text = str(note or "").strip()
    if not text:
        return current
    existing = str(current or "").strip()
    return f"{existing} {text}".strip() if existing else text


def _compact_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    allowed_scalars = {
        "requested_url",
        "final_url",
        "canonical_url",
        "title",
        "candidate_price",
        "mpn",
        "model",
        "brand",
        "category",
        "price",
        "title_similarity",
        "title_only",
        "blocked_or_captcha",
        "error_code",
        "error_message",
        "matched_identifier_variant",
        "evidence_source",
    }
    out: dict[str, Any] = {
        key: _compact_value(value)
        for key, value in evidence.items()
        if key in allowed_scalars
    }
    for key in ("mpn", "model", "brand", "category", "price"):
        value = evidence.get(key)
        if isinstance(value, dict):
            out[key] = _compact_dict(
                value,
                allowed_keys={
                    "found",
                    "expected",
                    "matched",
                    "raw",
                    "source",
                    "score",
                    "value",
                },
            )
    matched_tokens = evidence.get("title_matched_tokens")
    if isinstance(matched_tokens, list):
        out["title_matched_tokens"] = [
            _bounded_text(item, limit=100) for item in matched_tokens[:20]
        ]
    out["provider_provenance"] = _compact_provider_provenance(
        evidence.get("provider_provenance")
    )
    body = str(evidence.get("body_text_sample") or "").strip()
    if body:
        out["body_text_sample"] = body[:500]
    jsonld = evidence.get("jsonld_products")
    if isinstance(jsonld, list):
        out["jsonld_products"] = [
            _compact_dict(
                item,
                allowed_keys={"name", "brand", "mpn", "model", "sku", "category"},
            )
            for item in jsonld[:2]
            if isinstance(item, dict)
        ]
    return json_safe_value(out)


def _selected_url_matches_candidate(
    candidate: SourceUrlAgentCandidate, selected_url: str
) -> bool:
    selected = candidate.source.canonical_candidate_url(selected_url)
    if not selected:
        return False
    candidates = {
        candidate.source.canonical_candidate_url(url)
        for url in (candidate.candidate_url, candidate.canonical_url)
        if str(url or "").strip()
    }
    return selected in {url for url in candidates if url}


def _compact_provider_provenance(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return _compact_dict(
        value,
        allowed_keys={
            "provider_name",
            "source_name",
            "original_query",
            "search_url",
            "candidate_url",
            "result_index",
            "discovery_method",
            "allow_high_confidence_auto_apply",
        },
    )


def _compact_dict(value: dict[str, Any], *, allowed_keys: set[str]) -> dict[str, Any]:
    return {
        key: _compact_value(item)
        for key, item in value.items()
        if key in allowed_keys and _compact_value(item) not in ("", [], {})
    }


def _compact_value(value: object) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [_compact_value(item) for item in value[:20]]
    if isinstance(value, dict):
        return {
            _bounded_text(key, limit=100): _compact_value(item)
            for key, item in list(value.items())[:20]
        }
    return _bounded_text(value)


def _bounded_text(value: object, *, limit: int = 300) -> str:
    return str(value or "").strip()[:limit]


def _required_choice(payload: dict[str, Any], field_name: str, choices: set[str]) -> str:
    value = str(payload.get(field_name) or "").strip()
    if value not in choices:
        raise SourceUrlLLMEvaluationError(
            f"{field_name} must be one of: {', '.join(sorted(choices))}."
        )
    return value


def _confidence(value: object) -> Decimal:
    try:
        confidence = Decimal(str(value).strip())
    except Exception as exc:
        raise SourceUrlLLMEvaluationError("confidence must be a number.") from exc
    if confidence < 0 or confidence > 1:
        raise SourceUrlLLMEvaluationError("confidence must be between 0 and 1.")
    return confidence


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        raise SourceUrlLLMEvaluationError("LLM list fields must be arrays.")
    return [str(item).strip()[:500] for item in value if str(item or "").strip()]
