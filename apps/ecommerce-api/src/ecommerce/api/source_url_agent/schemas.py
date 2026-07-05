"""Request schemas for the Source URL Agent API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ReviewDecision = Literal["accept", "reject", "replace_url"]
SourceUrlAgentRunMode = Literal["catalog", "csv"]
DEFAULT_API_MAX_PRODUCTS_PER_BATCH = 25
MAX_API_SOURCE_URL_AGENT_LIMIT = 500


class SourceUrlCandidateReviewRequest(BaseModel):
    decision: ReviewDecision
    reviewed_url: str | None = None
    review_notes: str | None = None
    reviewed_by: str | None = None


class SourceUrlAgentRunRequest(BaseModel):
    source: str = "all"
    mode: SourceUrlAgentRunMode = "catalog"
    input_path: str | None = None
    limit: int | None = Field(default=None, ge=1, le=MAX_API_SOURCE_URL_AGENT_LIMIT)
    offset: int = Field(default=0, ge=0)
    catalog_product_id: int | None = Field(default=None, ge=1)
    model: str | None = None
    selected_models: list[str] = Field(default_factory=list)
    missing_only: bool = False
    active_only: bool = True
    dry_run: bool = True
    apply_high_confidence: bool = False
    max_products_per_batch: int | None = Field(
        default=None, ge=1, le=MAX_API_SOURCE_URL_AGENT_LIMIT
    )
    max_searches_per_product_source: int | None = Field(default=None, ge=1, le=20)
    rate_limit_seconds: float | None = Field(default=None, ge=0)
    headed: bool = False
    no_browser_cache: bool = False
    llm_evaluate_candidates: bool = False
    llm_auto_apply_candidates: bool = False
