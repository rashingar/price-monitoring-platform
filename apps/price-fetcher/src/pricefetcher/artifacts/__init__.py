"""Safe access helpers for generated PriceFetcher artifacts."""

from pricefetcher.artifacts.artifact_store import (
    ARTIFACT_ROOTS_ENV_VAR,
    TEXT_ARTIFACT_EXTENSIONS,
    ArtifactItem,
    ArtifactListResult,
    ArtifactPathError,
    ArtifactPathForbiddenError,
    ArtifactTextResult,
    UnsupportedArtifactExtensionError,
    artifact_link_payload,
    get_artifact_root_entries,
    get_artifact_roots,
    is_artifact_path_allowed,
    list_run_artifacts,
    read_text_artifact,
    resolve_artifact_path,
)

__all__ = [
    "ARTIFACT_ROOTS_ENV_VAR",
    "TEXT_ARTIFACT_EXTENSIONS",
    "ArtifactItem",
    "ArtifactListResult",
    "ArtifactPathError",
    "ArtifactPathForbiddenError",
    "ArtifactTextResult",
    "UnsupportedArtifactExtensionError",
    "artifact_link_payload",
    "get_artifact_root_entries",
    "get_artifact_roots",
    "is_artifact_path_allowed",
    "list_run_artifacts",
    "read_text_artifact",
    "resolve_artifact_path",
]
