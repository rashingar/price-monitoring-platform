"""Shared state hooks for Source URL Agent API orchestration."""

from __future__ import annotations

import sys

from ecommerce.source_url_agent.agent import Resolver

SOURCE_URL_AGENT_API_RESOLVER: Resolver | None = None
_FACADE_MODULE = "ecommerce.api.routes_source_url_agent"


def get_api_resolver() -> Resolver | None:
    facade = sys.modules.get(_FACADE_MODULE)
    if facade is not None and hasattr(facade, "SOURCE_URL_AGENT_API_RESOLVER"):
        return getattr(facade, "SOURCE_URL_AGENT_API_RESOLVER")
    return SOURCE_URL_AGENT_API_RESOLVER


def set_api_resolver(resolver: Resolver | None) -> None:
    global SOURCE_URL_AGENT_API_RESOLVER
    SOURCE_URL_AGENT_API_RESOLVER = resolver
    facade = sys.modules.get(_FACADE_MODULE)
    if facade is not None:
        setattr(facade, "SOURCE_URL_AGENT_API_RESOLVER", resolver)
