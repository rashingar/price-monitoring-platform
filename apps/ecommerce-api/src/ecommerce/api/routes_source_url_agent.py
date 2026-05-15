"""Source URL Agent API router facade."""

from __future__ import annotations

from fastapi import APIRouter

from ecommerce.source_url_agent.job_handler import execute_source_url_agent_job

from .source_url_agent.candidates import (
    _candidate_filters,
    _matching_source_url_id,
    _require_catalog_database_ready,
    _safe_db_error,
    get_source_url_agent_candidate,
    list_source_url_agent_candidates,
    review_source_url_agent_candidate,
    router as candidates_router,
)
from .source_url_agent.runs import (
    _api_run_limit,
    _create_queued_discovery_run,
    _create_queued_discovery_tasks,
    _make_api_run_id,
    _now,
    _optional_text,
    _require_source_url_agent_run_database_ready,
    _selected_models,
    _source_url_agent_input_path,
    _validate_source_choice,
    enqueue_source_url_agent_run,
    get_source_url_agent_run,
    get_source_url_agent_run_artifacts,
    launch_source_url_agent_run,
    list_source_url_agent_runs,
    list_source_url_agent_sources,
    router as runs_router,
)
from .source_url_agent.schemas import (
    DEFAULT_API_MAX_PRODUCTS_PER_BATCH,
    MAX_API_SOURCE_URL_AGENT_LIMIT,
    ReviewDecision,
    SourceUrlAgentRunMode,
    SourceUrlAgentRunRequest,
    SourceUrlCandidateReviewRequest,
)
from .source_url_agent.serializers import (
    artifact_refs_from_paths as _artifact_refs_from_paths,
    candidate_review_panel_payload as _candidate_review_panel_payload,
    candidate_to_dict as _candidate_to_dict,
    discovery_run_to_dict as _discovery_run_to_dict,
    discovery_task_counts as _discovery_task_counts,
    discovery_task_items as _discovery_task_items,
    source_definition_to_dict as _source_definition_to_dict,
    source_url_agent_result_payload as _source_url_agent_result_payload,
)
from .source_url_agent.state import SOURCE_URL_AGENT_API_RESOLVER
from .source_url_agent.validation import (
    contains_parent_reference as _contains_parent_reference,
    like_value as _like_value,
    optional_decimal as _optional_decimal,
    same_or_child as _same_or_child,
)
from .source_url_agent.artifacts import (
    display_path as _display_path,
    source_url_agent_artifact_items as _source_url_agent_artifact_items,
    source_url_agent_artifact_listing as _source_url_agent_artifact_listing,
)

router = APIRouter(prefix="/api/source-url-agent", tags=["source-url-agent"])
router.include_router(runs_router)
router.include_router(candidates_router)

__all__ = [
    "DEFAULT_API_MAX_PRODUCTS_PER_BATCH",
    "MAX_API_SOURCE_URL_AGENT_LIMIT",
    "ReviewDecision",
    "SOURCE_URL_AGENT_API_RESOLVER",
    "SourceUrlAgentRunMode",
    "SourceUrlAgentRunRequest",
    "SourceUrlCandidateReviewRequest",
    "router",
]
