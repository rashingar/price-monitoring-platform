"""Neutral source-resolution domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceResolutionProduct:
    model: str
    name: str
    brand: str | None = None
    mpn: str | None = None
    barcode: str | None = None
    category: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceResolutionCandidate:
    source_name: str
    url: str
    title: str
    description: str
    confidence: int
    result_rank: int | None = None

    def to_metadata(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_name": self.source_name,
            "url": self.url,
            "confidence": self.confidence,
        }
        if self.title:
            payload["title"] = self.title
        if self.result_rank is not None:
            payload["result_rank"] = self.result_rank
        return payload


@dataclass(frozen=True)
class SourceResolutionResult:
    method: str
    selected: SourceResolutionCandidate | None
    candidates: tuple[SourceResolutionCandidate, ...]
    config: Any
    queries: tuple[str, ...] = ()

    @property
    def status(self) -> str:
        if (
            self.selected is not None
            and self.selected.confidence >= self.config.minimum_confidence
        ):
            return "selected"
        if self.candidates:
            return "suggestions"
        return "no_usable_source"

    def metadata_for(self, candidate: SourceResolutionCandidate) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "method": self.method,
            "selected_source": candidate.source_name,
            "selected_url": candidate.url,
            "confidence": candidate.confidence,
            "candidate_count": len(self.candidates),
            "preferred_sources": self.config.preferred_source_names,
        }
        if candidate.title:
            payload["selected_title"] = candidate.title
        if self.queries:
            payload["queries"] = list(self.queries)
        return payload
