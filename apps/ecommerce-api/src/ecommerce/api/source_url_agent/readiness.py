"""Readiness diagnostics for Source URL Agent search providers."""

from __future__ import annotations

import os
import re
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ecommerce.source_url_agent.brave_search import BRAVE_SEARCH_API_KEY_ENV_VAR, BRAVE_SEARCH_PROVIDER_NAME
from ecommerce.source_url_agent.search_providers import (
    BROWSER_FALLBACK_PROVIDER_NAME,
    SearchProviderDefinition,
    SearchProviderRegistry,
    load_search_provider_registry,
)

router = APIRouter()

ReadinessStatus = Literal["ready", "warning", "blocked"]


class SourceUrlAgentProviderReadiness(BaseModel):
    provider_name: str
    provider_type: str
    enabled: bool
    configured: bool
    required_env_keys: list[str] = Field(default_factory=list)
    missing_env_keys: list[str] = Field(default_factory=list)
    allow_high_confidence_auto_apply: bool
    notes: str = ""


class SourceUrlAgentReadinessResponse(BaseModel):
    status: ReadinessStatus
    providers: list[SourceUrlAgentProviderReadiness] = Field(default_factory=list)
    default_provider_order: list[str] = Field(default_factory=list)
    source_cascades: dict[str, list[str]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)


@router.get("/readiness", response_model=SourceUrlAgentReadinessResponse)
def get_source_url_agent_readiness() -> SourceUrlAgentReadinessResponse:
    try:
        registry = load_search_provider_registry()
    except Exception:
        return SourceUrlAgentReadinessResponse(
            status="blocked",
            providers=[],
            default_provider_order=[],
            source_cascades={},
            warnings=[],
            blocking_reasons=["Source URL Agent search provider registry could not be loaded."],
        )

    return source_url_agent_readiness(registry)


def source_url_agent_readiness(registry: SearchProviderRegistry) -> SourceUrlAgentReadinessResponse:
    providers = [_provider_readiness(definition) for definition in registry.providers.values()]
    provider_by_name = {provider.provider_name: provider for provider in providers}
    warnings = _provider_warnings(providers)
    warnings.extend(_source_cascade_warnings(registry))
    blocking_reasons = _blocking_reasons(registry, provider_by_name)
    status: ReadinessStatus
    if blocking_reasons:
        status = "blocked"
    elif warnings:
        status = "warning"
    else:
        status = "ready"
    return SourceUrlAgentReadinessResponse(
        status=status,
        providers=providers,
        default_provider_order=list(registry.default_cascade),
        source_cascades=_serialized_source_cascades(registry),
        warnings=warnings,
        blocking_reasons=blocking_reasons,
    )


def _provider_readiness(definition: SearchProviderDefinition) -> SourceUrlAgentProviderReadiness:
    required_env_keys = _required_env_keys(definition)
    missing_env_keys = [key for key in required_env_keys if not _env_key_is_present(key)]
    configured = _configured(definition, required_env_keys=required_env_keys, missing_env_keys=missing_env_keys)
    return SourceUrlAgentProviderReadiness(
        provider_name=definition.provider_name,
        provider_type=definition.provider_type,
        enabled=definition.enabled,
        configured=configured,
        required_env_keys=required_env_keys,
        missing_env_keys=missing_env_keys,
        allow_high_confidence_auto_apply=definition.allow_high_confidence_auto_apply,
        notes=_safe_text(definition.notes),
    )


def _required_env_keys(definition: SearchProviderDefinition) -> list[str]:
    if definition.provider_name == BRAVE_SEARCH_PROVIDER_NAME and definition.provider_type == "brave":
        return [BRAVE_SEARCH_API_KEY_ENV_VAR]
    if definition.provider_name == BROWSER_FALLBACK_PROVIDER_NAME and definition.provider_type == "browser":
        return []
    return []


def _configured(
    definition: SearchProviderDefinition,
    *,
    required_env_keys: list[str],
    missing_env_keys: list[str],
) -> bool:
    if definition.provider_name == BRAVE_SEARCH_PROVIDER_NAME and definition.provider_type == "brave":
        return not missing_env_keys
    if definition.provider_name == BROWSER_FALLBACK_PROVIDER_NAME and definition.provider_type == "browser":
        return bool(definition.enabled)
    if _is_known_provider_type(definition):
        return not missing_env_keys
    return False


def _provider_warnings(providers: list[SourceUrlAgentProviderReadiness]) -> list[str]:
    warnings: list[str] = []
    for provider in providers:
        if provider.enabled and not _is_known_provider_readiness(provider):
            warnings.append(
                f"Unsupported Source URL Agent search provider type for {provider.provider_name}: {provider.provider_type}."
            )
    return warnings


def _source_cascade_warnings(registry: SearchProviderRegistry) -> list[str]:
    warnings: list[str] = []
    for source_name, cascade in registry.source_cascades.items():
        if not cascade:
            warnings.append(f"Source URL Agent source cascade for {source_name} is empty.")
    return warnings


def _blocking_reasons(
    registry: SearchProviderRegistry,
    provider_by_name: dict[str, SourceUrlAgentProviderReadiness],
) -> list[str]:
    enabled_default_providers = [
        provider_by_name[name]
        for name in registry.default_cascade
        if name in provider_by_name and provider_by_name[name].enabled
    ]
    if any(provider.configured for provider in enabled_default_providers):
        return []
    if not enabled_default_providers:
        return ["No enabled Source URL Agent search provider is present in the default provider order."]

    missing_keys = _ordered_missing_env_keys(enabled_default_providers)
    if missing_keys:
        return [
            "No enabled configured Source URL Agent search provider is available in the default provider order; "
            f"missing required environment keys: {', '.join(missing_keys)}."
        ]
    return ["No enabled configured Source URL Agent search provider is available in the default provider order."]


def _ordered_missing_env_keys(providers: list[SourceUrlAgentProviderReadiness]) -> list[str]:
    keys: list[str] = []
    for provider in providers:
        for key in provider.missing_env_keys:
            if key not in keys:
                keys.append(key)
    return keys


def _serialized_source_cascades(registry: SearchProviderRegistry) -> dict[str, list[str]]:
    return {source_name: list(cascade) for source_name, cascade in registry.source_cascades.items()}


def _env_key_is_present(key: str) -> bool:
    return bool(str(os.environ.get(key) or "").strip())


def _is_known_provider_type(definition: SearchProviderDefinition) -> bool:
    return (
        definition.provider_name == BRAVE_SEARCH_PROVIDER_NAME
        and definition.provider_type == "brave"
        or definition.provider_name == BROWSER_FALLBACK_PROVIDER_NAME
        and definition.provider_type == "browser"
    )


def _is_known_provider_readiness(provider: SourceUrlAgentProviderReadiness) -> bool:
    return (
        provider.provider_name == BRAVE_SEARCH_PROVIDER_NAME
        and provider.provider_type == "brave"
        or provider.provider_name == BROWSER_FALLBACK_PROVIDER_NAME
        and provider.provider_type == "browser"
    )


def _safe_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*\S+", r"\1=<redacted>", text)
    text = re.sub(r"(?i)\b[a-z][a-z0-9+.-]*://[^@\s]+@[^/\s]+", "<redacted-connection-string>", text)
    return text[:500]

