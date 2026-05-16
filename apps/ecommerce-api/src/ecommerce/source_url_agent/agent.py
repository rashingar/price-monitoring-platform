"""Compatibility facade for Source URL Agent runtime imports.

New code should import options from ``ecommerce.source_url_agent.options`` and
execution from ``ecommerce.source_url_agent.runner``. This module remains for
existing scripts, tests, and operator imports that use the historical
``ecommerce.source_url_agent.agent`` path.
"""

from __future__ import annotations

from ecommerce.source_url_agent.options import (
    ProgressCallback,
    Resolver,
    SourceUrlAgentOptions,
    SourceUrlAgentResult,
)
from ecommerce.source_url_agent.runner import run_source_url_agent

__all__ = [
    "ProgressCallback",
    "Resolver",
    "SourceUrlAgentOptions",
    "SourceUrlAgentResult",
    "run_source_url_agent",
]
