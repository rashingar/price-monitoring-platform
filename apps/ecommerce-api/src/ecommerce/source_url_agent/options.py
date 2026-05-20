"""Public options and result types for Source URL Agent runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ecommerce.source_url_agent.artifacts import SourceUrlAgentArtifactPaths
from ecommerce.source_url_agent.candidates import SourceUrlAgentCandidate
from ecommerce.source_url_agent.products import AgentProduct
from ecommerce.source_url_agent.progress import SourceUrlAgentProgressReporter
from ecommerce.source_url_agent.search import SourceSearchResult
from ecommerce.source_url_agent.sources import SourceDefinition

Resolver = Callable[[AgentProduct, SourceDefinition], SourceSearchResult]
ProgressCallback = Callable[
    [str, AgentProduct, SourceDefinition, list[SourceUrlAgentCandidate], str | None],
    None,
]


@dataclass(frozen=True)
class SourceUrlAgentOptions:
    mode: str
    run_id: str | None = None
    source: str = "all"
    input_path: Path | None = None
    output_dir: Path | None = None
    limit: int | None = None
    offset: int = 0
    catalog_product_id: int | None = None
    model: str | None = None
    selected_models: list[str] | None = None
    missing_only: bool = False
    active_only: bool = True
    dry_run: bool = True
    apply_high_confidence: bool = False
    max_products_per_batch: int | None = None
    max_searches_per_product_source: int | None = None
    rate_limit_seconds: float | None = None
    headed: bool = False
    no_browser_cache: bool = False
    progress_callback: ProgressCallback | None = None
    progress_reporter: SourceUrlAgentProgressReporter | None = None


@dataclass(frozen=True)
class SourceUrlAgentResult:
    run_id: str
    summary: dict
    candidates: list[SourceUrlAgentCandidate]
    artifacts: SourceUrlAgentArtifactPaths
    warnings: list[str]
