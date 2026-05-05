"""Lightweight API health route."""

from __future__ import annotations

from fastapi import APIRouter

from pricefetcher import __version__
from pricefetcher.db.config import is_database_configured

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def get_health() -> dict:
    database_configured = is_database_configured()
    return {
        "status": "ok",
        "service": "price-fetcher",
        "api": "commerce",
        "version": __version__,
        "price_monitoring_requires_database": True,
        "database_configured": database_configured,
        "database_required_for_startup": False,
        "checks": {
            "app": "ok",
            "database": "configured" if database_configured else "not_configured",
        },
    }
