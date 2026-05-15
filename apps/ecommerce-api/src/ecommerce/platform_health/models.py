"""Response models for the combined platform health endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

HealthStatus = Literal["ready", "warning", "blocked", "unknown"]


class PlatformHealthLink(BaseModel):
    label: str
    url: str


class PlatformHealthGroup(BaseModel):
    id: str
    label: str
    status: HealthStatus
    summary: str
    details: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    links: list[PlatformHealthLink] = Field(default_factory=list)


class PlatformHealthResponse(BaseModel):
    status: HealthStatus
    groups: list[PlatformHealthGroup]
    updated_at: str
