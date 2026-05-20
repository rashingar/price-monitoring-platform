"""Config loading for Product Factory source resolution."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

PRODUCT_FACTORY_SOURCE_RESOLUTION_CONFIG_ENV = (
    "PRODUCT_FACTORY_SOURCE_RESOLUTION_CONFIG_PATH"
)
DEFAULT_SOURCE_RESOLUTION_CONFIG_PATH = (
    Path(__file__).resolve().parents[5]
    / "config"
    / "product_factory_source_resolution.json"
)


class SourceResolutionConfigError(ValueError):
    """Raised when the source resolution config is invalid."""


@dataclass(frozen=True)
class PreferredSourceConfig:
    source_name: str
    weight: int
    domains: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    product_url_patterns: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PreferredSourceConfig":
        source_name = _required_text(
            payload.get("source_name"), "preferred_sources.source_name"
        ).casefold()
        domains = tuple(_text_list(payload.get("domains")))
        if not domains:
            raise SourceResolutionConfigError(
                f"preferred source {source_name} must define at least one domain."
            )
        patterns = tuple(_text_list(payload.get("product_url_patterns")))
        if not patterns:
            raise SourceResolutionConfigError(
                f"preferred source {source_name} must define product_url_patterns."
            )
        try:
            weight = int(payload.get("weight"))
        except (TypeError, ValueError) as exc:
            raise SourceResolutionConfigError(
                f"preferred source {source_name} has an invalid weight."
            ) from exc
        if weight < 0:
            raise SourceResolutionConfigError(
                f"preferred source {source_name} weight must be non-negative."
            )
        aliases = tuple(item.casefold() for item in _text_list(payload.get("aliases")))
        return cls(
            source_name=source_name,
            weight=weight,
            domains=tuple(
                domain.casefold()
                .removeprefix("https://")
                .removeprefix("http://")
                .strip("/")
                for domain in domains
            ),
            aliases=aliases,
            product_url_patterns=patterns,
        )

    def matches_host(self, host: str) -> bool:
        normalized = host.casefold().removeprefix("www.")
        return any(
            normalized == domain.casefold().removeprefix("www.")
            for domain in self.domains
        )

    @property
    def primary_domain(self) -> str:
        return self.domains[0].casefold().removeprefix("www.")


@dataclass(frozen=True)
class SourceResolutionConfig:
    minimum_confidence: int
    suggestion_confidence: int
    max_suggestions: int
    pending_choice_ttl_minutes: int
    preferred_sources: tuple[PreferredSourceConfig, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SourceResolutionConfig":
        if not isinstance(payload, dict):
            raise SourceResolutionConfigError(
                "Source resolution config must be a JSON object."
            )
        minimum_confidence = _int_range(
            payload.get("minimum_confidence"),
            "minimum_confidence",
            minimum=1,
            maximum=100,
        )
        suggestion_confidence = _int_range(
            payload.get("suggestion_confidence"),
            "suggestion_confidence",
            minimum=1,
            maximum=100,
        )
        if suggestion_confidence > minimum_confidence:
            raise SourceResolutionConfigError(
                "suggestion_confidence must be less than or equal to minimum_confidence."
            )
        max_suggestions = _int_range(
            payload.get("max_suggestions"), "max_suggestions", minimum=1, maximum=10
        )
        pending_choice_ttl_minutes = _int_range(
            payload.get("pending_choice_ttl_minutes"),
            "pending_choice_ttl_minutes",
            minimum=1,
            maximum=1440,
        )
        raw_sources = payload.get("preferred_sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise SourceResolutionConfigError(
                "preferred_sources must contain at least one source."
            )
        sources = tuple(
            PreferredSourceConfig.from_dict(item)
            for item in raw_sources
            if isinstance(item, dict)
        )
        if len(sources) != len(raw_sources):
            raise SourceResolutionConfigError(
                "preferred_sources must contain only objects."
            )
        names = [source.source_name for source in sources]
        if len(set(names)) != len(names):
            raise SourceResolutionConfigError(
                "preferred_sources contains duplicate source_name values."
            )
        return cls(
            minimum_confidence=minimum_confidence,
            suggestion_confidence=suggestion_confidence,
            max_suggestions=max_suggestions,
            pending_choice_ttl_minutes=pending_choice_ttl_minutes,
            preferred_sources=sources,
        )

    @property
    def pending_choice_ttl(self) -> timedelta:
        return timedelta(minutes=self.pending_choice_ttl_minutes)

    @property
    def preferred_source_names(self) -> list[str]:
        return [source.source_name for source in self.preferred_sources]

    def classify_url(self, url: str) -> PreferredSourceConfig | None:
        host = str(urlsplit(url).hostname or "")
        for source in self.preferred_sources:
            if source.matches_host(host):
                return source
        return None

    def source_for_alias(self, value: str) -> PreferredSourceConfig | None:
        normalized = value.strip().casefold()
        for source in self.preferred_sources:
            if normalized == source.source_name or normalized in source.aliases:
                return source
        return None

    def with_preferred_sources(
        self, source_names: tuple[str, ...]
    ) -> "SourceResolutionConfig":
        allowed = {name.casefold() for name in source_names}
        sources = tuple(
            source for source in self.preferred_sources if source.source_name in allowed
        )
        missing = allowed - {source.source_name for source in sources}
        if missing:
            raise SourceResolutionConfigError(
                f"configured preferred_sources missing required sources: {', '.join(sorted(missing))}"
            )
        return SourceResolutionConfig(
            minimum_confidence=self.minimum_confidence,
            suggestion_confidence=self.suggestion_confidence,
            max_suggestions=self.max_suggestions,
            pending_choice_ttl_minutes=self.pending_choice_ttl_minutes,
            preferred_sources=sources,
        )


def load_source_resolution_config(
    path: str | Path | None = None,
) -> SourceResolutionConfig:
    raw_path = str(
        path or os.environ.get(PRODUCT_FACTORY_SOURCE_RESOLUTION_CONFIG_ENV) or ""
    ).strip()
    config_path = (
        Path(raw_path).expanduser()
        if raw_path
        else DEFAULT_SOURCE_RESOLUTION_CONFIG_PATH
    )
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SourceResolutionConfigError(
            f"Source resolution config file was not found: {config_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise SourceResolutionConfigError(
            f"Source resolution config is invalid JSON: {config_path}"
        ) from exc
    except OSError as exc:
        raise SourceResolutionConfigError(
            f"Source resolution config file is not readable: {config_path}"
        ) from exc
    return SourceResolutionConfig.from_dict(payload)


def _required_text(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SourceResolutionConfigError(f"{field_name} is required.")
    return text


def _text_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _int_range(value: object, field_name: str, *, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise SourceResolutionConfigError(f"{field_name} must be an integer.") from exc
    if number < minimum or number > maximum:
        raise SourceResolutionConfigError(
            f"{field_name} must be between {minimum} and {maximum}."
        )
    return number
