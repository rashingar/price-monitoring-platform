"""Source URL Agent API router."""

from __future__ import annotations

from fastapi import APIRouter

from .source_url_agent.candidates import router as candidates_router
from .source_url_agent.readiness import router as readiness_router
from .source_url_agent.runs import router as runs_router
from .source_url_agent.schemas import (
    DEFAULT_API_MAX_PRODUCTS_PER_BATCH,
    MAX_API_SOURCE_URL_AGENT_LIMIT,
    ReviewDecision,
    SourceUrlAgentRunMode,
    SourceUrlAgentRunRequest,
    SourceUrlCandidateReviewRequest,
)

router = APIRouter(prefix="/api/source-url-agent", tags=["source-url-agent"])
router.include_router(readiness_router)
router.include_router(runs_router)
router.include_router(candidates_router)

__all__ = [
    "DEFAULT_API_MAX_PRODUCTS_PER_BATCH",
    "MAX_API_SOURCE_URL_AGENT_LIMIT",
    "ReviewDecision",
    "SourceUrlAgentRunMode",
    "SourceUrlAgentRunRequest",
    "SourceUrlCandidateReviewRequest",
    "router",
]
