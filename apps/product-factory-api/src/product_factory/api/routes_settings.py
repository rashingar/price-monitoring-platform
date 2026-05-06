from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from ..services.settings_service import (
    ProductFactorySettingsError,
    load_product_factory_settings,
    patch_product_factory_settings,
)
from .schemas import ErrorResponse, SettingsPatchRequest, SettingsResponse


router = APIRouter(prefix="/settings", tags=["settings"])

_ERROR_RESPONSES = {
    status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse, "description": "Invalid settings."},
}

_ALLOWED_PATCH_PATHS = {
    ("authoring", "intro_text", "default", "min_words"),
    ("authoring", "intro_text", "default", "max_words"),
    ("authoring", "intro_text", "default", "max_attempts"),
    ("authoring", "seo_meta", "default", "meta_description_max_chars"),
}


@router.get("", response_model=SettingsResponse, responses=_ERROR_RESPONSES)
def get_settings() -> SettingsResponse:
    try:
        return SettingsResponse(**load_product_factory_settings().to_dict())
    except ProductFactorySettingsError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.patch("", response_model=SettingsResponse, responses=_ERROR_RESPONSES)
def patch_settings(request: SettingsPatchRequest) -> SettingsResponse:
    patch = request.model_dump(exclude_unset=True)
    invalid_paths = _invalid_patch_paths(patch)
    if invalid_paths:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported settings patch path: {invalid_paths[0]}",
        )
    try:
        return SettingsResponse(**patch_product_factory_settings(patch).to_dict())
    except ProductFactorySettingsError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


def _invalid_patch_paths(payload: dict[str, Any]) -> list[str]:
    leaf_paths: list[tuple[str, ...]] = []
    _collect_leaf_paths(payload, (), leaf_paths)
    return [".".join(path) for path in leaf_paths if path not in _ALLOWED_PATCH_PATHS]


def _collect_leaf_paths(payload: Any, prefix: tuple[str, ...], out: list[tuple[str, ...]]) -> None:
    if isinstance(payload, dict) and payload:
        for key, value in payload.items():
            _collect_leaf_paths(value, (*prefix, str(key)), out)
        return
    out.append(prefix)
