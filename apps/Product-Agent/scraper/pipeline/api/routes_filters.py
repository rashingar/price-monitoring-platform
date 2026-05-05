from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..services.filters_manager_service import (
    FilterManagerError,
    add_filter_group,
    add_filter_value,
    get_filter_category,
    get_filter_status,
    get_filter_sync_report,
    list_filter_override_backups,
    restore_filter_override_backup,
    list_filter_categories,
    sync_filter_map,
    update_filter_group,
    update_filter_value,
)
from .schemas import (
    AddFilterGroupRequest,
    AddFilterValueRequest,
    ErrorResponse,
    FilterBackupRestoreResponse,
    FilterBackupsResponse,
    FilterCategoriesResponse,
    FilterCategoryResponse,
    FilterStatusResponse,
    FilterSyncReportResponse,
    FilterSyncResponse,
    RestoreFilterBackupRequest,
    UpdateFilterGroupRequest,
    UpdateFilterValueRequest,
)


router = APIRouter(prefix="/filters", tags=["filters"])

_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Invalid filter recovery request."},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Filter resource not found."},
    status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Filter conflict."},
    status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse, "description": "Invalid filter request."},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Filter manager failure."},
}


def _raise_http(exc: FilterManagerError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/categories", response_model=FilterCategoriesResponse, responses=_ERROR_RESPONSES)
def get_filter_categories() -> FilterCategoriesResponse:
    try:
        return list_filter_categories()
    except FilterManagerError as exc:
        _raise_http(exc)


@router.get("/categories/{category_id}", response_model=FilterCategoryResponse, responses=_ERROR_RESPONSES)
def get_filter_category_detail(category_id: str) -> FilterCategoryResponse:
    try:
        return get_filter_category(category_id)
    except FilterManagerError as exc:
        _raise_http(exc)


@router.put("/categories/{category_id}/groups", response_model=FilterCategoryResponse, responses=_ERROR_RESPONSES)
def put_filter_group(category_id: str, request: AddFilterGroupRequest) -> FilterCategoryResponse:
    try:
        return add_filter_group(category_id, request)
    except FilterManagerError as exc:
        _raise_http(exc)


@router.patch("/categories/{category_id}/groups/{group_id}", response_model=FilterCategoryResponse, responses=_ERROR_RESPONSES)
def patch_filter_group(
    category_id: str,
    group_id: str,
    request: UpdateFilterGroupRequest,
) -> FilterCategoryResponse:
    try:
        return update_filter_group(category_id, group_id, request)
    except FilterManagerError as exc:
        _raise_http(exc)


@router.put(
    "/categories/{category_id}/groups/{group_id}/values",
    response_model=FilterCategoryResponse,
    responses=_ERROR_RESPONSES,
)
def put_filter_value(category_id: str, group_id: str, request: AddFilterValueRequest) -> FilterCategoryResponse:
    try:
        return add_filter_value(category_id, group_id, request)
    except FilterManagerError as exc:
        _raise_http(exc)


@router.patch(
    "/categories/{category_id}/groups/{group_id}/values/{value_id}",
    response_model=FilterCategoryResponse,
    responses=_ERROR_RESPONSES,
)
def patch_filter_value(
    category_id: str,
    group_id: str,
    value_id: str,
    request: UpdateFilterValueRequest,
) -> FilterCategoryResponse:
    try:
        return update_filter_value(category_id, group_id, value_id, request)
    except FilterManagerError as exc:
        _raise_http(exc)


@router.post("/sync", response_model=FilterSyncResponse, responses=_ERROR_RESPONSES)
def post_filter_sync() -> FilterSyncResponse:
    try:
        return sync_filter_map()
    except FilterManagerError as exc:
        _raise_http(exc)


@router.get("/sync-report", response_model=FilterSyncReportResponse, responses=_ERROR_RESPONSES)
def get_filter_sync_report_route() -> FilterSyncReportResponse:
    try:
        return get_filter_sync_report()
    except FilterManagerError as exc:
        _raise_http(exc)


@router.get("/status", response_model=FilterStatusResponse, responses=_ERROR_RESPONSES)
def get_filter_manager_status() -> FilterStatusResponse:
    return get_filter_status()


@router.get("/backups", response_model=FilterBackupsResponse, responses=_ERROR_RESPONSES)
def get_filter_backups() -> FilterBackupsResponse:
    try:
        return list_filter_override_backups()
    except FilterManagerError as exc:
        _raise_http(exc)


@router.post("/backups/restore", response_model=FilterBackupRestoreResponse, responses=_ERROR_RESPONSES)
def post_filter_backup_restore(request: RestoreFilterBackupRequest) -> FilterBackupRestoreResponse:
    try:
        return restore_filter_override_backup(request.backup_name)
    except FilterManagerError as exc:
        _raise_http(exc)
