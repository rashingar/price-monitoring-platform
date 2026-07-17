"""Safe, filesystem-only foundations for Product Factory SEO migration."""

from .approval import (
    APPROVAL_SCHEMA_VERSION,
    ApprovalValidationError,
    approved_product_map,
    load_approval_manifest,
    validate_approval_manifest,
)
from .snapshot import (
    SNAPSHOT_PRODUCT_FIELDS,
    SNAPSHOT_SCHEMA_VERSION,
    SnapshotError,
    SnapshotExistsError,
    SnapshotIntegrityError,
    SnapshotValidationError,
    compute_snapshot_content_hash,
    compute_catalog_export_hash,
    create_catalog_snapshot,
    load_catalog_snapshot,
    normalize_catalog_export,
    snapshot_directory,
    snapshot_file_path,
    verify_catalog_snapshot,
)

__all__ = [
    "APPROVAL_SCHEMA_VERSION",
    "ApprovalValidationError",
    "SNAPSHOT_PRODUCT_FIELDS",
    "SNAPSHOT_SCHEMA_VERSION",
    "SnapshotError",
    "SnapshotExistsError",
    "SnapshotIntegrityError",
    "SnapshotValidationError",
    "approved_product_map",
    "compute_snapshot_content_hash",
    "compute_catalog_export_hash",
    "create_catalog_snapshot",
    "load_approval_manifest",
    "load_catalog_snapshot",
    "normalize_catalog_export",
    "snapshot_directory",
    "snapshot_file_path",
    "validate_approval_manifest",
    "verify_catalog_snapshot",
]
