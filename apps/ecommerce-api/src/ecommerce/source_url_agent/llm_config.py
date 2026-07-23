"""Configuration for optional Source URL Agent LLM evaluation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping


SOURCE_URL_LLM_ENABLED_ENV_VAR = "ECOMMERCE_SOURCE_URL_LLM_ENABLED"
SOURCE_URL_LLM_MODEL_ENV_VAR = "ECOMMERCE_SOURCE_URL_LLM_MODEL"
SOURCE_URL_LLM_ESCALATION_MODEL_ENV_VAR = "ECOMMERCE_SOURCE_URL_LLM_ESCALATION_MODEL"
SOURCE_URL_LLM_REASONING_EFFORT_ENV_VAR = "ECOMMERCE_SOURCE_URL_LLM_REASONING_EFFORT"
SOURCE_URL_LLM_MAX_CANDIDATES_ENV_VAR = "ECOMMERCE_SOURCE_URL_LLM_MAX_CANDIDATES"
SOURCE_URL_LLM_MAX_CALLS_PER_RUN_ENV_VAR = "ECOMMERCE_SOURCE_URL_LLM_MAX_CALLS_PER_RUN"
SOURCE_URL_LLM_AUTO_APPLY_MIN_CONFIDENCE_ENV_VAR = (
    "ECOMMERCE_SOURCE_URL_LLM_AUTO_APPLY_MIN_CONFIDENCE"
)
SOURCE_URL_LLM_REVIEW_MIN_CONFIDENCE_ENV_VAR = (
    "ECOMMERCE_SOURCE_URL_LLM_REVIEW_MIN_CONFIDENCE"
)


@dataclass(frozen=True)
class SourceUrlLLMConfig:
    enabled: bool = False
    model: str = "gpt-5.4-mini"
    escalation_model: str = "gpt-5.5"
    reasoning_effort: str = "low"
    max_candidates: int = 3
    max_calls_per_run: int = 25
    auto_apply_min_confidence: Decimal = Decimal("0.92")
    review_min_confidence: Decimal = Decimal("0.75")


def load_source_url_llm_config(
    *, env: Mapping[str, str] | None = None
) -> SourceUrlLLMConfig:
    source_env = os.environ if env is None else env
    return SourceUrlLLMConfig(
        enabled=_bool_value(source_env.get(SOURCE_URL_LLM_ENABLED_ENV_VAR), False),
        model=_text_value(source_env.get(SOURCE_URL_LLM_MODEL_ENV_VAR), "gpt-5.4-mini"),
        escalation_model=_text_value(
            source_env.get(SOURCE_URL_LLM_ESCALATION_MODEL_ENV_VAR), "gpt-5.5"
        ),
        reasoning_effort=_text_value(
            source_env.get(SOURCE_URL_LLM_REASONING_EFFORT_ENV_VAR), "low"
        ),
        max_candidates=max(
            0, _int_value(source_env.get(SOURCE_URL_LLM_MAX_CANDIDATES_ENV_VAR), 3)
        ),
        max_calls_per_run=max(
            0, _int_value(source_env.get(SOURCE_URL_LLM_MAX_CALLS_PER_RUN_ENV_VAR), 25)
        ),
        auto_apply_min_confidence=_decimal_value(
            source_env.get(SOURCE_URL_LLM_AUTO_APPLY_MIN_CONFIDENCE_ENV_VAR),
            Decimal("0.92"),
        ),
        review_min_confidence=_decimal_value(
            source_env.get(SOURCE_URL_LLM_REVIEW_MIN_CONFIDENCE_ENV_VAR),
            Decimal("0.75"),
        ),
    )


def _bool_value(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _int_value(value: object, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _decimal_value(value: object, default: Decimal) -> Decimal:
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return default


def _text_value(value: object, default: str) -> str:
    text = str(value or "").strip()
    return text or default
