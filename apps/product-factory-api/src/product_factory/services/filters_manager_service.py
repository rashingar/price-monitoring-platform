from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import repo_paths
from ..api.schemas import (
    AddFilterGroupRequest,
    AddFilterValueRequest,
    FilterBackupItem,
    FilterBackupRestoreResponse,
    FilterBackupsResponse,
    FilterCategoriesResponse,
    FilterCategoryListItem,
    FilterCategoryResponse,
    FilterGroupResponse,
    FilterStatusResponse,
    FilterSyncReportResponse,
    FilterSyncResponse,
    FilterValueResponse,
    UpdateFilterGroupRequest,
    UpdateFilterValueRequest,
)
from ..normalize import normalize_label_key
from ..tools.sync_filter_map import (
    INVALID_MANUAL_OVERRIDES_MESSAGE,
    VALID_STATUSES,
    InvalidFilterOverrideJsonError,
    apply_manual_overrides,
    load_manual_overrides,
    new_report,
    read_filter_map_json,
    read_json_file,
    stable_group_id,
    stable_value_id,
    write_filter_map_json,
    write_json_file,
    write_manual_overrides,
)

FILTER_PERSISTENCE_LOCK_TIMEOUT_SECONDS = 5.0
FILTER_PERSISTENCE_LOCK_RETRY_SECONDS = 0.05
FILTER_MANUAL_METADATA_SCHEMA_VERSION = 1
FILTER_OVERRIDE_BACKUP_RETENTION = 20
FILTER_OVERRIDE_BACKUP_PREFIX = "filter_map.manual_overrides"
FILTER_OVERRIDE_BACKUP_PATTERN = f"{FILTER_OVERRIDE_BACKUP_PREFIX}.*.json"
FILTER_OVERRIDE_BACKUP_NAME_RE = re.compile(
    r"^filter_map\.manual_overrides\.(?P<created>\d{8}-\d{6})\.(?P<revision>[A-Za-z0-9_-]+)(?:\.\d+)?\.json$"
)


class FilterManagerError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(slots=True)
class _FilterMaps:
    base: dict[str, Any]
    manual: dict[str, Any]
    effective: dict[str, Any]
    revision: str


class _FilterPersistenceLock:
    def __init__(
        self,
        lock_path: Path,
        *,
        purpose: str,
        timeout_seconds: float = FILTER_PERSISTENCE_LOCK_TIMEOUT_SECONDS,
        retry_seconds: float = FILTER_PERSISTENCE_LOCK_RETRY_SECONDS,
    ) -> None:
        self.lock_path = lock_path
        self.purpose = purpose
        self.timeout_seconds = timeout_seconds
        self.retry_seconds = retry_seconds
        self.token = uuid.uuid4().hex
        self._acquired = False

    def __enter__(self) -> _FilterPersistenceLock:
        deadline = time.monotonic() + self.timeout_seconds
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {
            "pid": os.getpid(),
            "created_at": _utc_now(),
            "purpose": self.purpose,
            "token": self.token,
        }
        content = (
            json.dumps(metadata, ensure_ascii=False, sort_keys=True) + "\n"
        ).encode("utf-8")

        while True:
            try:
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as exc:
                if time.monotonic() >= deadline:
                    raise FilterManagerError(
                        409,
                        f"Filter manager persistence lock timed out for {self.purpose}. "
                        "Another filter write may be in progress; refresh and retry.",
                    ) from exc
                time.sleep(self.retry_seconds)
                continue

            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
            self._acquired = True
            return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        self.release()

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            if self._owns_lock_file():
                self.lock_path.unlink(missing_ok=True)
        finally:
            self._acquired = False

    def _owns_lock_file(self) -> bool:
        try:
            payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return payload.get("token") == self.token and payload.get("pid") == os.getpid()


def list_filter_categories() -> FilterCategoriesResponse:
    maps = _load_maps()
    categories = [
        _category_list_item(category, maps=maps)
        for category in _iter_categories(maps.effective)
    ]
    categories.sort(key=lambda item: (item.path, item.category_id))
    return FilterCategoriesResponse(categories=categories)


def get_filter_category(category_id: str) -> FilterCategoryResponse:
    maps = _load_maps()
    category = _find_category(maps.effective, category_id)
    if category is None:
        raise FilterManagerError(404, f"category_id not found: {category_id}")
    return _category_response(category, maps=maps)


def add_filter_group(
    category_id: str, request: AddFilterGroupRequest
) -> FilterCategoryResponse:
    with _filter_persistence_lock("add_filter_group"):
        maps = _load_maps()
        _validate_expected_revision(request.expected_revision, maps.revision)
        category = _require_category_for_edit(maps, category_id)
        group_name = request.name.strip()
        group_id = stable_group_id(category_id, group_name)

        if _find_group(category, group_id=group_id) is not None:
            raise FilterManagerError(
                409, f"Group already exists with group_id: {group_id}"
            )
        if _find_group(category, name=group_name) is not None:
            raise FilterManagerError(
                409, f"Group already exists with name: {group_name}"
            )
        if _find_group(category, name=group_name, normalized=True) is not None:
            raise FilterManagerError(
                409, f"Normalized duplicate group exists for name: {group_name}"
            )

        manual = deepcopy(maps.manual)
        updated_at = _utc_now()
        category_override = _ensure_category_override(manual, category)
        _set_override_metadata(
            category_override, operation="add_group", updated_at=updated_at
        )
        groups = category_override.setdefault("groups", {})
        groups[group_id] = {
            "group_id": group_id,
            "name": group_name,
            "required": request.required,
            "status": request.status,
            "values": {},
            "metadata": _override_metadata(
                operation="add_group", updated_at=updated_at
            ),
        }
        return _write_manual_sync_and_category(
            manual, category_id, operation="add_group", updated_at=updated_at
        )


def update_filter_group(
    category_id: str,
    group_id: str,
    request: UpdateFilterGroupRequest,
) -> FilterCategoryResponse:
    with _filter_persistence_lock("update_filter_group"):
        maps = _load_maps()
        _validate_expected_revision(request.expected_revision, maps.revision)
        category = _require_category_for_edit(maps, category_id)
        group = _find_group(category, group_id=group_id)
        if group is None:
            raise FilterManagerError(404, f"group_id not found: {group_id}")

        if request.name is not None:
            conflicting = _find_group(
                category, name=request.name, exclude_group_id=group_id
            )
            if conflicting is not None:
                raise FilterManagerError(
                    409, f"Group already exists with name: {request.name}"
                )
            normalized_conflict = _find_group(
                category,
                name=request.name,
                normalized=True,
                exclude_group_id=group_id,
            )
            if normalized_conflict is not None:
                raise FilterManagerError(
                    409, f"Normalized duplicate group exists for name: {request.name}"
                )

        manual = deepcopy(maps.manual)
        updated_at = _utc_now()
        category_override = _ensure_category_override(manual, category)
        _set_override_metadata(
            category_override, operation="update_group", updated_at=updated_at
        )
        group_override = _ensure_group_override(category_override, group)
        if request.name is not None:
            group_override["name"] = request.name
        if request.required is not None:
            group_override["required"] = request.required
        if request.status is not None:
            group_override["status"] = request.status
        _set_override_metadata(
            group_override, operation="update_group", updated_at=updated_at
        )
        return _write_manual_sync_and_category(
            manual, category_id, operation="update_group", updated_at=updated_at
        )


def add_filter_value(
    category_id: str,
    group_id: str,
    request: AddFilterValueRequest,
) -> FilterCategoryResponse:
    with _filter_persistence_lock("add_filter_value"):
        maps = _load_maps()
        _validate_expected_revision(request.expected_revision, maps.revision)
        category = _require_category_for_edit(maps, category_id)
        group = _find_group(category, group_id=group_id)
        if group is None:
            raise FilterManagerError(404, f"group_id not found: {group_id}")

        display_value = request.value.strip()
        value_id = stable_value_id(group_id, display_value)
        if _find_value(group, value_id=value_id) is not None:
            raise FilterManagerError(
                409, f"Value already exists with value_id: {value_id}"
            )
        if _find_value(group, value=display_value) is not None:
            raise FilterManagerError(409, f"Value already exists: {display_value}")
        if _find_value(group, value=display_value, normalized=True) is not None:
            raise FilterManagerError(
                409, f"Normalized duplicate value exists for value: {display_value}"
            )

        manual = deepcopy(maps.manual)
        updated_at = _utc_now()
        category_override = _ensure_category_override(manual, category)
        _set_override_metadata(
            category_override, operation="add_value", updated_at=updated_at
        )
        group_override = _ensure_group_override(category_override, group)
        _set_override_metadata(
            group_override, operation="add_value", updated_at=updated_at
        )
        group_override.setdefault("values", {})[value_id] = {
            "value_id": value_id,
            "value": display_value,
            "status": request.status,
            "metadata": _override_metadata(
                operation="add_value", updated_at=updated_at
            ),
        }
        return _write_manual_sync_and_category(
            manual, category_id, operation="add_value", updated_at=updated_at
        )


def update_filter_value(
    category_id: str,
    group_id: str,
    value_id: str,
    request: UpdateFilterValueRequest,
) -> FilterCategoryResponse:
    with _filter_persistence_lock("update_filter_value"):
        maps = _load_maps()
        _validate_expected_revision(request.expected_revision, maps.revision)
        category = _require_category_for_edit(maps, category_id)
        group = _find_group(category, group_id=group_id)
        if group is None:
            raise FilterManagerError(404, f"group_id not found: {group_id}")
        value = _find_value(group, value_id=value_id)
        if value is None:
            raise FilterManagerError(404, f"value_id not found: {value_id}")

        if request.value is not None:
            conflicting = _find_value(
                group, value=request.value, exclude_value_id=value_id
            )
            if conflicting is not None:
                raise FilterManagerError(409, f"Value already exists: {request.value}")
            normalized_conflict = _find_value(
                group,
                value=request.value,
                normalized=True,
                exclude_value_id=value_id,
            )
            if normalized_conflict is not None:
                raise FilterManagerError(
                    409, f"Normalized duplicate value exists for value: {request.value}"
                )

        manual = deepcopy(maps.manual)
        updated_at = _utc_now()
        category_override = _ensure_category_override(manual, category)
        _set_override_metadata(
            category_override, operation="update_value", updated_at=updated_at
        )
        group_override = _ensure_group_override(category_override, group)
        _set_override_metadata(
            group_override, operation="update_value", updated_at=updated_at
        )
        value_override = _ensure_value_override(group_override, value)
        if request.value is not None:
            value_override["value"] = request.value
        if request.status is not None:
            value_override["status"] = request.status
        _set_override_metadata(
            value_override, operation="update_value", updated_at=updated_at
        )
        return _write_manual_sync_and_category(
            manual, category_id, operation="update_value", updated_at=updated_at
        )


def sync_filter_map() -> FilterSyncResponse:
    with _filter_persistence_lock("sync_filter_map"):
        try:
            manual = load_manual_overrides(repo_paths.FILTER_MAP_MANUAL_OVERRIDES_PATH)
            updated_at = _utc_now()
            final_payload, revision = _persist_manual_and_sync(
                manual,
                operation="sync_filter_map",
                updated_at=updated_at,
            )
            report = (
                read_json_file(repo_paths.FILTER_MAP_SYNC_REPORT_PATH, default={}) or {}
            )
        except FilterManagerError:
            raise
        except InvalidFilterOverrideJsonError as exc:
            raise FilterManagerError(409, INVALID_MANUAL_OVERRIDES_MESSAGE) from exc
        except (
            Exception
        ) as exc:  # pragma: no cover - defensive boundary for API callers
            raise FilterManagerError(500, f"Filter map sync failed: {exc}") from exc
    return _sync_response(final_payload, report, revision=revision)


def get_filter_sync_report() -> FilterSyncReportResponse:
    if not repo_paths.FILTER_MAP_SYNC_REPORT_PATH.exists():
        raise FilterManagerError(404, "Filter sync report not found.")
    try:
        report = (
            read_json_file(repo_paths.FILTER_MAP_SYNC_REPORT_PATH, default={}) or {}
        )
    except Exception as exc:  # pragma: no cover - defensive boundary for API callers
        raise FilterManagerError(
            500, f"Could not read filter sync report: {exc}"
        ) from exc
    return FilterSyncReportResponse.model_validate(report)


def get_filter_status() -> FilterStatusResponse:
    try:
        revision = _load_maps().revision
    except FilterManagerError:
        revision = None
    return FilterStatusResponse(
        filter_map_base_path=str(repo_paths.FILTER_MAP_BASE_PATH),
        filter_map_manual_overrides_path=str(
            repo_paths.FILTER_MAP_MANUAL_OVERRIDES_PATH
        ),
        filter_map_path=str(repo_paths.FILTER_MAP_PATH),
        sync_report_path=str(repo_paths.FILTER_MAP_SYNC_REPORT_PATH),
        valid_statuses=sorted(VALID_STATUSES),
        revision=revision,
    )


def list_filter_override_backups() -> FilterBackupsResponse:
    items = [_backup_item(path) for path in _iter_filter_override_backups()]
    return FilterBackupsResponse(items=items)


def restore_filter_override_backup(
    backup_name: str | None = None,
) -> FilterBackupRestoreResponse:
    with _filter_persistence_lock("restore_filter_override_backup"):
        updated_at = _utc_now()
        backup_path = _select_restore_backup_path(backup_name)
        try:
            manual = load_manual_overrides(backup_path)
        except InvalidFilterOverrideJsonError as exc:
            raise FilterManagerError(
                400, f"Filter override backup JSON is invalid: {backup_path.name}"
            ) from exc

        restored_backup_name = backup_path.name
        _create_filter_override_backup(
            operation="restore_filter_override_backup", updated_at=updated_at
        )
        _touch_manual_metadata(
            manual, operation="restore_filter_override_backup", updated_at=updated_at
        )
        _sort_manual_overrides(manual)
        try:
            final_payload, revision = _persist_manual_and_sync(
                manual,
                operation="restore_filter_override_backup",
                updated_at=updated_at,
                create_backup=False,
            )
            report = (
                read_json_file(repo_paths.FILTER_MAP_SYNC_REPORT_PATH, default={}) or {}
            )
            report["rollback"] = {
                "status": "restored",
                "restored_backup_name": restored_backup_name,
                "restored_at": updated_at,
            }
            write_json_file(repo_paths.FILTER_MAP_SYNC_REPORT_PATH, report)
        except FilterManagerError as exc:
            if exc.status_code >= 500:
                raise FilterManagerError(
                    500, f"Filter override restore sync failed: {exc.detail}"
                ) from exc
            raise
        except (
            Exception
        ) as exc:  # pragma: no cover - defensive boundary for API callers
            raise FilterManagerError(
                500, f"Filter override restore sync failed: {exc}"
            ) from exc
    return FilterBackupRestoreResponse(
        status="ok",
        restored_backup_name=restored_backup_name,
        revision=revision,
        filter_map_path=str(repo_paths.FILTER_MAP_PATH),
        manual_overrides_path=str(repo_paths.FILTER_MAP_MANUAL_OVERRIDES_PATH),
        sync_report_path=str(repo_paths.FILTER_MAP_SYNC_REPORT_PATH),
    )


def _load_maps() -> _FilterMaps:
    try:
        maps = _FilterMaps(
            base=read_filter_map_json(repo_paths.FILTER_MAP_BASE_PATH),
            manual=load_manual_overrides(repo_paths.FILTER_MAP_MANUAL_OVERRIDES_PATH),
            effective=read_filter_map_json(repo_paths.FILTER_MAP_PATH),
            revision="",
        )
        maps.revision = compute_filter_revision(maps.manual, maps.effective)
        return maps
    except FileNotFoundError as exc:
        raise FilterManagerError(500, str(exc)) from exc
    except InvalidFilterOverrideJsonError as exc:
        raise FilterManagerError(409, INVALID_MANUAL_OVERRIDES_MESSAGE) from exc
    except Exception as exc:  # pragma: no cover - defensive boundary for API callers
        raise FilterManagerError(500, f"Could not load filter maps: {exc}") from exc


def _write_manual_sync_and_category(
    manual: dict[str, Any],
    category_id: str,
    *,
    operation: str,
    updated_at: str,
) -> FilterCategoryResponse:
    final_payload, revision = _persist_manual_and_sync(
        manual, operation=operation, updated_at=updated_at
    )
    maps = _FilterMaps(
        base=read_filter_map_json(repo_paths.FILTER_MAP_BASE_PATH),
        manual=manual,
        effective=final_payload,
        revision=revision,
    )
    category = _find_category(final_payload, category_id)
    if category is None:
        raise FilterManagerError(
            500, f"Persisted filter category disappeared: {category_id}"
        )
    return _category_response(category, maps=maps)


def _persist_manual_and_sync(
    manual: dict[str, Any],
    *,
    operation: str,
    updated_at: str,
    create_backup: bool = True,
) -> tuple[dict[str, Any], str]:
    try:
        _touch_manual_metadata(manual, operation=operation, updated_at=updated_at)
        _sort_manual_overrides(manual)
        base_payload = read_filter_map_json(repo_paths.FILTER_MAP_BASE_PATH)
        report = _build_apply_overrides_report(base_payload)
        final_payload = apply_manual_overrides(base_payload, manual, report)
        revision = compute_filter_revision(manual, final_payload)
        manual.setdefault("metadata", {})["revision"] = revision
        _sort_manual_overrides(manual)
        if create_backup:
            _create_filter_override_backup(operation=operation, updated_at=updated_at)
        write_manual_overrides(repo_paths.FILTER_MAP_MANUAL_OVERRIDES_PATH, manual)
        write_filter_map_json(repo_paths.FILTER_MAP_PATH, final_payload)
        write_filter_map_json(repo_paths.FILTER_MAP_SYNC_REPORT_PATH, report)
        return final_payload, revision
    except InvalidFilterOverrideJsonError as exc:
        raise FilterManagerError(409, INVALID_MANUAL_OVERRIDES_MESSAGE) from exc
    except Exception as exc:  # pragma: no cover - defensive boundary for API callers
        raise FilterManagerError(
            500, f"Could not persist filter override: {exc}"
        ) from exc


def _build_apply_overrides_report(base_payload: dict[str, Any]) -> dict[str, Any]:
    report = new_report("apply-overrides")
    report["base_path"] = str(repo_paths.FILTER_MAP_BASE_PATH)
    report["manual_overrides_path"] = str(repo_paths.FILTER_MAP_MANUAL_OVERRIDES_PATH)
    report["filter_map_path"] = str(repo_paths.FILTER_MAP_PATH)
    report["categories_seen"] = len(base_payload.get("subcategories", []))
    report["groups_seen"] = sum(
        len(category.get("filter_groups", []))
        for category in base_payload.get("subcategories", [])
    )
    report["values_seen"] = sum(
        len(group.get("values", []))
        for category in base_payload.get("subcategories", [])
        for group in category.get("filter_groups", [])
    )
    return report


def _backup_dir() -> Path:
    return repo_paths.FILTER_MAP_MANUAL_OVERRIDES_BACKUP_DIR


def _iter_filter_override_backups() -> list[Path]:
    backup_dir = _backup_dir()
    if not backup_dir.exists():
        return []
    return sorted(
        (
            path
            for path in backup_dir.glob(FILTER_OVERRIDE_BACKUP_PATTERN)
            if path.is_file() and FILTER_OVERRIDE_BACKUP_NAME_RE.match(path.name)
        ),
        key=lambda path: path.name,
        reverse=True,
    )


def _backup_item(path: Path) -> FilterBackupItem:
    created_at = ""
    revision = ""
    match = FILTER_OVERRIDE_BACKUP_NAME_RE.match(path.name)
    if match:
        raw_created = match.group("created")
        created_at = f"{raw_created[:4]}-{raw_created[4:6]}-{raw_created[6:8]}T{raw_created[9:11]}:{raw_created[11:13]}:{raw_created[13:15]}Z"
        revision = match.group("revision")
    return FilterBackupItem(
        backup_name=path.name,
        created_at=created_at,
        revision=revision,
        size_bytes=path.stat().st_size,
    )


def _create_filter_override_backup(*, operation: str, updated_at: str) -> Path | None:
    source_path = repo_paths.FILTER_MAP_MANUAL_OVERRIDES_PATH
    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    if not source_path.exists():
        return _write_missing_override_marker(
            backup_dir, operation=operation, updated_at=updated_at
        )

    revision = _backup_revision_token(source_path)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = _unique_backup_path(
        backup_dir / f"{FILTER_OVERRIDE_BACKUP_PREFIX}.{timestamp}.{revision}.json"
    )
    temp_path = backup_path.with_name(f".{backup_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with source_path.open("rb") as source, temp_path.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temp_path, backup_path)
    finally:
        temp_path.unlink(missing_ok=True)
    _prune_filter_override_backups()
    return backup_path


def _write_missing_override_marker(
    backup_dir: Path, *, operation: str, updated_at: str
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    marker_path = _unique_backup_path(
        backup_dir
        / f"{FILTER_OVERRIDE_BACKUP_PREFIX}.{timestamp}.no-previous.marker.json"
    )
    write_json_file(
        marker_path,
        {
            "marker": "manual_overrides_missing",
            "created_at": updated_at,
            "operation": operation,
            "manual_overrides_file": repo_paths.FILTER_MAP_MANUAL_OVERRIDES_PATH.name,
        },
    )
    return marker_path


def _backup_revision_token(source_path: Path) -> str:
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return "invalid-json"
    metadata = payload.get("metadata") if isinstance(payload, dict) else None
    revision = metadata.get("revision") if isinstance(metadata, dict) else None
    if not revision:
        return "no-revision"
    return _safe_filename_part(str(revision).replace(":", "-", 1))[:32] or "no-revision"


def _safe_filename_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")


def _unique_backup_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}.{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise FilterManagerError(
        500, "Could not allocate a unique filter override backup filename."
    )


def _prune_filter_override_backups() -> None:
    for stale_path in _iter_filter_override_backups()[
        FILTER_OVERRIDE_BACKUP_RETENTION:
    ]:
        stale_path.unlink(missing_ok=True)


def _select_restore_backup_path(backup_name: str | None) -> Path:
    if backup_name:
        return _resolve_named_backup_path(backup_name)

    backups = _iter_filter_override_backups()
    if not backups:
        raise FilterManagerError(404, "No filter override backups are available.")
    for backup_path in backups:
        try:
            load_manual_overrides(backup_path)
        except InvalidFilterOverrideJsonError:
            continue
        return backup_path
    raise FilterManagerError(400, "No valid filter override backups are available.")


def _resolve_named_backup_path(backup_name: str) -> Path:
    if (
        not backup_name
        or Path(backup_name).name != backup_name
        or "/" in backup_name
        or "\\" in backup_name
    ):
        raise FilterManagerError(400, "Invalid filter override backup name.")
    backup_dir = _backup_dir().resolve(strict=False)
    backup_path = (backup_dir / backup_name).resolve(strict=False)
    if backup_dir != backup_path and backup_dir not in backup_path.parents:
        raise FilterManagerError(400, "Invalid filter override backup name.")
    if not backup_path.exists() or not backup_path.is_file():
        raise FilterManagerError(
            404, f"Filter override backup not found: {backup_name}"
        )
    return backup_path


def _require_category_for_edit(maps: _FilterMaps, category_id: str) -> dict[str, Any]:
    category = _find_category(maps.effective, category_id) or _find_category(
        maps.base, category_id
    )
    if category is None:
        raise FilterManagerError(404, f"category_id not found: {category_id}")
    return category


def _category_list_item(
    category: dict[str, Any], *, maps: _FilterMaps
) -> FilterCategoryListItem:
    groups = category.get("filter_groups", [])
    return FilterCategoryListItem(
        category_id=str(category.get("category_id", "")),
        path=str(category.get("path", "")),
        parent_category=str(category.get("parent_category", "")),
        leaf_category=str(category.get("leaf_category", "")),
        sub_category=str(category.get("sub_category", "")),
        key=str(category.get("key", "")),
        group_count=len(groups),
        active_group_count=sum(
            1 for group in groups if group.get("status", "active") == "active"
        ),
        required_group_count=sum(
            1 for group in groups if bool(group.get("required", True))
        ),
        inactive_group_count=sum(
            1 for group in groups if group.get("status") == "inactive"
        ),
        deprecated_group_count=sum(
            1 for group in groups if group.get("status") == "deprecated"
        ),
        source=_source(
            _find_category(maps.base, str(category.get("category_id", ""))) is not None,
            _manual_category(maps.manual, str(category.get("category_id", "")))
            is not None,
        ),
    )


def _category_response(
    category: dict[str, Any], *, maps: _FilterMaps
) -> FilterCategoryResponse:
    category_id = str(category.get("category_id", ""))
    groups = [
        _group_response(group, category_id=category_id, maps=maps)
        for group in category.get("filter_groups", [])
    ]
    return FilterCategoryResponse(
        category_id=category_id,
        path=str(category.get("path", "")),
        parent_category=str(category.get("parent_category", "")),
        leaf_category=str(category.get("leaf_category", "")),
        sub_category=str(category.get("sub_category", "")),
        revision=maps.revision,
        groups=groups,
    )


def _group_response(
    group: dict[str, Any], *, category_id: str, maps: _FilterMaps
) -> FilterGroupResponse:
    group_id = str(group.get("group_id", ""))
    values = [
        _value_response(value, category_id=category_id, group_id=group_id, maps=maps)
        for value in group.get("values", [])
    ]
    return FilterGroupResponse(
        group_id=group_id,
        name=str(group.get("name", "")),
        required=bool(group.get("required", True)),
        status=group.get("status", "active"),
        source=_source(
            _find_group(_find_category(maps.base, category_id), group_id=group_id)
            is not None,
            _manual_group(maps.manual, category_id, group_id) is not None,
        ),
        values=values,
    )


def _value_response(
    value: dict[str, Any],
    *,
    category_id: str,
    group_id: str,
    maps: _FilterMaps,
) -> FilterValueResponse:
    value_id = str(value.get("value_id", ""))
    base_group = _find_group(_find_category(maps.base, category_id), group_id=group_id)
    return FilterValueResponse(
        value_id=value_id,
        value=str(value.get("value", "")),
        status=value.get("status", "active"),
        source=_source(
            _find_value(base_group, value_id=value_id) is not None,
            _manual_value(maps.manual, category_id, group_id, value_id) is not None,
        ),
    )


def _sync_response(
    final_payload: dict[str, Any],
    report: dict[str, Any],
    *,
    revision: str | None = None,
) -> FilterSyncResponse:
    categories = list(_iter_categories(final_payload))
    groups = [
        group for category in categories for group in category.get("filter_groups", [])
    ]
    return FilterSyncResponse(
        status="ok",
        filter_map_path=str(repo_paths.FILTER_MAP_PATH),
        sync_report_path=str(repo_paths.FILTER_MAP_SYNC_REPORT_PATH),
        revision=revision
        or compute_filter_revision(
            load_manual_overrides(repo_paths.FILTER_MAP_MANUAL_OVERRIDES_PATH),
            final_payload,
        ),
        category_count=len(categories),
        group_count=len(groups),
        value_count=sum(len(group.get("values", [])) for group in groups),
        warning_count=len(report.get("warnings", [])),
        overridden_group_count=len(report.get("overridden_groups", [])),
        overridden_value_count=len(report.get("overridden_values", [])),
    )


def _iter_categories(payload: dict[str, Any]) -> list[dict[str, Any]]:
    categories = payload.get("subcategories", [])
    return [category for category in categories if isinstance(category, dict)]


def _find_category(
    payload: dict[str, Any] | None, category_id: str
) -> dict[str, Any] | None:
    if not payload:
        return None
    by_id = payload.get("by_category_id", {})
    category = by_id.get(category_id) if isinstance(by_id, dict) else None
    if isinstance(category, dict):
        return category
    return next(
        (
            item
            for item in _iter_categories(payload)
            if item.get("category_id") == category_id
        ),
        None,
    )


def _find_group(
    category: dict[str, Any] | None,
    *,
    group_id: str | None = None,
    name: str | None = None,
    normalized: bool = False,
    exclude_group_id: str | None = None,
) -> dict[str, Any] | None:
    if not category:
        return None
    needle = normalize_label_key(name) if normalized else name
    for group in category.get("filter_groups", []):
        if exclude_group_id and group.get("group_id") == exclude_group_id:
            continue
        if group_id and group.get("group_id") == group_id:
            return group
        if name is not None:
            candidate = (
                normalize_label_key(group.get("name"))
                if normalized
                else group.get("name")
            )
            if candidate == needle:
                return group
    return None


def _find_value(
    group: dict[str, Any] | None,
    *,
    value_id: str | None = None,
    value: str | None = None,
    normalized: bool = False,
    exclude_value_id: str | None = None,
) -> dict[str, Any] | None:
    if not group:
        return None
    needle = normalize_label_key(value) if normalized else value
    for item in group.get("values", []):
        if exclude_value_id and item.get("value_id") == exclude_value_id:
            continue
        if value_id and item.get("value_id") == value_id:
            return item
        if value is not None:
            candidate = (
                normalize_label_key(item.get("value"))
                if normalized
                else item.get("value")
            )
            if candidate == needle:
                return item
    return None


def _ensure_category_override(
    manual: dict[str, Any], category: dict[str, Any]
) -> dict[str, Any]:
    category_id = str(category.get("category_id", ""))
    categories = manual.setdefault("categories", {})
    category_override = categories.setdefault(
        category_id,
        {
            "category_id": category_id,
            "path": category.get("path", ""),
            "groups": {},
        },
    )
    category_override["category_id"] = category_id
    category_override["path"] = category.get("path", category_override.get("path", ""))
    category_override.setdefault("groups", {})
    return category_override


def _ensure_group_override(
    category_override: dict[str, Any], group: dict[str, Any]
) -> dict[str, Any]:
    group_id = str(group.get("group_id", ""))
    groups = category_override.setdefault("groups", {})
    group_override = groups.setdefault(
        group_id,
        {
            "group_id": group_id,
            "name": group.get("name", ""),
            "required": bool(group.get("required", True)),
            "status": group.get("status", "active"),
            "values": {},
        },
    )
    group_override.setdefault("group_id", group_id)
    group_override.setdefault("name", group.get("name", ""))
    group_override.setdefault("required", bool(group.get("required", True)))
    group_override.setdefault("status", group.get("status", "active"))
    group_override.setdefault("values", {})
    return group_override


def _ensure_value_override(
    group_override: dict[str, Any], value: dict[str, Any]
) -> dict[str, Any]:
    value_id = str(value.get("value_id", ""))
    values = group_override.setdefault("values", {})
    value_override = values.setdefault(
        value_id,
        {
            "value_id": value_id,
            "value": value.get("value", ""),
            "status": value.get("status", "active"),
        },
    )
    value_override.setdefault("value_id", value_id)
    value_override.setdefault("value", value.get("value", ""))
    value_override.setdefault("status", value.get("status", "active"))
    return value_override


def _manual_category(manual: dict[str, Any], category_id: str) -> dict[str, Any] | None:
    item = manual.get("categories", {}).get(category_id)
    return item if isinstance(item, dict) else None


def _manual_group(
    manual: dict[str, Any], category_id: str, group_id: str
) -> dict[str, Any] | None:
    category = _manual_category(manual, category_id)
    if not category:
        return None
    item = category.get("groups", {}).get(group_id)
    return item if isinstance(item, dict) else None


def _manual_value(
    manual: dict[str, Any], category_id: str, group_id: str, value_id: str
) -> dict[str, Any] | None:
    group = _manual_group(manual, category_id, group_id)
    if not group:
        return None
    item = group.get("values", {}).get(value_id)
    return item if isinstance(item, dict) else None


def _source(base_exists: bool, manual_exists: bool) -> str:
    if base_exists and manual_exists:
        return "merged"
    if manual_exists:
        return "manual"
    return "base"


def _filter_persistence_lock(purpose: str) -> _FilterPersistenceLock:
    return _FilterPersistenceLock(_filter_lock_path(), purpose=purpose)


def _filter_lock_path() -> Path:
    return repo_paths.FILTER_MAP_MANUAL_OVERRIDES_PATH.with_name(
        f"{repo_paths.FILTER_MAP_MANUAL_OVERRIDES_PATH.name}.lock"
    )


def _validate_expected_revision(
    expected_revision: str | None, current_revision: str
) -> None:
    if expected_revision is None:
        return
    if expected_revision != current_revision:
        raise FilterManagerError(
            409,
            "Stale filter revision: expected_revision does not match the current filter revision. "
            "Refresh filters and retry.",
        )


def compute_filter_revision(manual: dict[str, Any], effective: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(b"manual\0")
    digest.update(_canonical_json_bytes(_manual_payload_for_revision(manual)))
    digest.update(b"\neffective\0")
    digest.update(_canonical_json_bytes(effective))
    return f"sha256:{digest.hexdigest()}"


def _manual_payload_for_revision(manual: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(manual)
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        metadata.pop("revision", None)
    return payload


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _touch_manual_metadata(
    manual: dict[str, Any], *, operation: str, updated_at: str
) -> None:
    metadata = manual.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
        manual["metadata"] = metadata
    metadata["schema_version"] = FILTER_MANUAL_METADATA_SCHEMA_VERSION
    metadata["updated_at"] = updated_at
    metadata["last_operation"] = operation


def _override_metadata(*, operation: str, updated_at: str) -> dict[str, str]:
    return {
        "updated_at": updated_at,
        "operation": operation,
    }


def _set_override_metadata(
    payload: dict[str, Any], *, operation: str, updated_at: str
) -> None:
    payload["metadata"] = _override_metadata(operation=operation, updated_at=updated_at)


def _sort_manual_overrides(manual: dict[str, Any]) -> None:
    categories = manual.setdefault("categories", {})
    sorted_categories: dict[str, Any] = {}
    for category_id, category in sorted(
        categories.items(),
        key=lambda item: (str(item[1].get("path", "")), item[0]),
    ):
        groups = category.setdefault("groups", {})
        sorted_groups: dict[str, Any] = {}
        for group_id, group in sorted(
            groups.items(),
            key=lambda item: (str(item[1].get("name", "")), item[0]),
        ):
            values = group.setdefault("values", {})
            group["values"] = {
                value_id: value
                for value_id, value in sorted(
                    values.items(),
                    key=lambda item: (str(item[1].get("value", "")), item[0]),
                )
            }
            sorted_groups[group_id] = group
        category["groups"] = sorted_groups
        sorted_categories[category_id] = category
    manual["categories"] = sorted_categories
