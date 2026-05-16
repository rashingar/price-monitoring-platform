"""Source URL Agent readiness API route."""

from __future__ import annotations

from fastapi import APIRouter

from ecommerce.source_url_agent.readiness import (
    SourceUrlAgentReadinessResponse,
    get_source_url_agent_readiness as collect_source_url_agent_readiness,
)

router = APIRouter()


@router.get("/readiness", response_model=SourceUrlAgentReadinessResponse)
def get_source_url_agent_readiness() -> SourceUrlAgentReadinessResponse:
    return collect_source_url_agent_readiness()
