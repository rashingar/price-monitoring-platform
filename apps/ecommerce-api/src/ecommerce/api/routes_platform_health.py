"""Combined read-only platform health endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from ecommerce.platform_health.models import PlatformHealthResponse
from ecommerce.platform_health.service import get_platform_health_response

router = APIRouter(prefix="/api/platform", tags=["platform-health"])


@router.get("/health", response_model=PlatformHealthResponse)
def get_platform_health() -> PlatformHealthResponse:
    return get_platform_health_response()
