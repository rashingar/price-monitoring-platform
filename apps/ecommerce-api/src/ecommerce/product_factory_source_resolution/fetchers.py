"""Brave Search fetching for Product Factory source resolution."""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Any, Protocol

import httpx

from ecommerce.product_factory_source_resolution.exceptions import SourceResolutionError
from ecommerce.source_url_agent.brave_search import (
    BRAVE_SEARCH_API_KEY_ENV_VAR,
    DEFAULT_BRAVE_SEARCH_ENDPOINT_URL,
    BraveSearchHttpClient,
    HttpxBraveSearchClient,
    brave_web_results,
)
from ecommerce.source_url_agent.search_providers import SearchProviderDefinition


class BraveResultFetcher(Protocol):
    def search(self, query: str, *, max_results: int) -> list[Any]: ...


class BraveSearchResultFetcher:
    def __init__(
        self,
        *,
        definition: SearchProviderDefinition | None = None,
        client: BraveSearchHttpClient | None = None,
    ) -> None:
        self.definition = definition or default_brave_definition()
        self.client = client or HttpxBraveSearchClient()

    def search(self, query: str, *, max_results: int) -> list[Any]:
        api_key = str(os.environ.get(BRAVE_SEARCH_API_KEY_ENV_VAR) or "").strip()
        if not api_key:
            raise SourceResolutionError("Missing Brave Search API key.")
        definition = replace(self.definition, count=min(20, max(1, max_results)))
        try:
            response = self.client.search(
                definition=definition, query=query, api_key=api_key
            )
        except httpx.TimeoutException as exc:
            raise SourceResolutionError("Brave Search API request timed out.") from exc
        except Exception as exc:
            raise SourceResolutionError(
                str(exc).strip() or exc.__class__.__name__
            ) from exc
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code >= 400:
            raise SourceResolutionError(
                f"Brave Search API returned HTTP {status_code}."
            )
        try:
            payload = response.json()
        except Exception as exc:
            raise SourceResolutionError(
                "Brave Search API returned invalid JSON."
            ) from exc
        return brave_web_results(payload, max_results=max_results)


def default_brave_definition() -> SearchProviderDefinition:
    return SearchProviderDefinition(
        provider_name="brave_search",
        provider_type="brave",
        enabled=True,
        allow_high_confidence_auto_apply=False,
        endpoint_url=DEFAULT_BRAVE_SEARCH_ENDPOINT_URL,
        country="GR",
        search_lang="el",
        ui_lang="el-GR",
        count=10,
        safesearch="moderate",
        result_filter="web",
        spellcheck=False,
        extra_snippets=True,
        text_decorations=False,
        include_fetch_metadata=True,
        operators=True,
        timeout_seconds=10.0,
    )
