"""Durable job execution policy for API-triggered Ecommerce jobs."""

from __future__ import annotations

import os
from collections.abc import Mapping

API_EXECUTE_DURABLE_JOBS_INLINE_ENV_VAR = "ECOMMERCE_API_EXECUTE_DURABLE_JOBS_INLINE"
DEFAULT_API_EXECUTE_DURABLE_JOBS_INLINE = True

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def api_execute_durable_jobs_inline_enabled(
    env: Mapping[str, str] | None = None,
) -> bool:
    """Return whether API routes should immediately start queued durable jobs.

    The durable worker is the canonical executor. This policy keeps the local
    API fallback explicit and configurable while preserving the historical
    default behavior.
    """

    source = os.environ if env is None else env
    raw_value = (
        str(source.get(API_EXECUTE_DURABLE_JOBS_INLINE_ENV_VAR, "") or "")
        .strip()
        .lower()
    )
    if not raw_value:
        return DEFAULT_API_EXECUTE_DURABLE_JOBS_INLINE
    if raw_value in _TRUE_VALUES:
        return True
    if raw_value in _FALSE_VALUES:
        return False
    return DEFAULT_API_EXECUTE_DURABLE_JOBS_INLINE
