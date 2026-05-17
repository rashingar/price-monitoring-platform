"""Shared state hooks for Source URL Agent API orchestration."""

from __future__ import annotations

from ecommerce.source_url_agent.options import Resolver

SOURCE_URL_AGENT_API_RESOLVER: Resolver | None = None


def get_api_resolver() -> Resolver | None:
    return SOURCE_URL_AGENT_API_RESOLVER


def set_api_resolver(resolver: Resolver | None) -> None:
    global SOURCE_URL_AGENT_API_RESOLVER
    SOURCE_URL_AGENT_API_RESOLVER = resolver
