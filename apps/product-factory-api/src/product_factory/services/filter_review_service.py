from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from .. import repo_paths
from ..api.schemas import (
    FilterReviewGroup,
    FilterReviewGroupUpdate,
    FilterReviewNewGroup,
    FilterReviewResponse,
    FilterReviewUpdateRequest,
    FilterReviewValue,
    FilterReviewValueUpdate,
)
from ..category_filters import (
    canonical_taxonomy_path,
    coerce_category_filter_review_values,
    find_filter_category,
    load_category_filter_review_payload,
    resolve_category_filter_values,
)
from ..models import SourceProductData, SpecItem, SpecSection, TaxonomyResolution
from ..normalize import normalize_for_match
from ..tools.sync_filter_map import (
    load_manual_overrides,
    stable_group_id,
    stable_value_id,
)
from ..utils import ensure_directory, read_json, utcnow_iso, write_json
from .execution_models import PreparedProductContext
from .filters_manager_service import (
    _filter_persistence_lock,
    _persist_manual_and_sync,
    _utc_now,
)


class PreparedArtifactsNotFoundError(RuntimeError):
    pass


@dataclass(slots=True)
class _PreparedReviewContext:
    model: str
    model_root: Path
    source: SourceProductData
    taxonomy: TaxonomyResolution
    filter_map: dict[str, Any]
    filter_category: dict[str, Any] | None
    category_id: str
    taxonomy_path: str
    review_path: Path


@dataclass(slots=True)
class _ManualUpdateResult:
    filter_map: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    changed: bool = False


@dataclass(frozen=True, slots=True)
class FilterReviewRenderGate:
    may_render: bool
    blocking_reasons: list[str]
    missing_required_labels: list[str]
    review_artifact_path: str | None = None


def get_filter_review_state(model: str) -> FilterReviewResponse:
    context = _load_prepared_review_context(model)
    review_payload = load_category_filter_review_payload(context.model_root)
    return _build_state(context, review_payload=review_payload)


def evaluate_filter_review_render_gate(
    review: FilterReviewResponse,
) -> FilterReviewRenderGate:
    blocking_reasons = _filter_review_blocking_reasons(review)
    missing_required_labels = _filter_review_missing_required_labels(review)
    may_render = not (
        bool(getattr(review, "render_blocked", False))
        or missing_required_labels
        or (getattr(review, "approved", False) is not True and blocking_reasons)
    )
    review_artifact_path = getattr(review, "review_artifact_path", None)
    return FilterReviewRenderGate(
        may_render=may_render,
        blocking_reasons=blocking_reasons,
        missing_required_labels=missing_required_labels,
        review_artifact_path=(
            str(review_artifact_path) if review_artifact_path else None
        ),
    )


def save_filter_review(
    model: str, request: FilterReviewUpdateRequest
) -> FilterReviewResponse:
    context = _load_prepared_review_context(model)
    if context.filter_category is None:
        raise ValueError(f"Filter category not found for model {model}.")

    previous_payload = load_category_filter_review_payload(context.model_root)
    previous_values = _canonical_review_values(
        previous_payload, context.filter_category
    )
    warnings = (
        list(previous_payload.get("warnings", []))
        if isinstance(previous_payload, dict)
        else []
    )

    manual_result = _apply_global_updates(context, request)
    context.filter_map = manual_result.filter_map
    context.filter_category = find_filter_category(
        context.filter_map,
        category_id=context.category_id,
        taxonomy_path=context.taxonomy_path,
    )
    warnings.extend(manual_result.warnings)

    next_values = dict(previous_values)
    for update in request.values:
        group = _find_group(
            context.filter_category,
            group_id=update.group_id or "",
            group_name=update.group_name,
        )
        group_id = str(
            update.group_id
            or (group or {}).get("group_id")
            or stable_group_id(context.category_id, update.group_name)
        )
        group_name = str((group or {}).get("name") or update.group_name)
        value = update.value.strip()
        next_values[group_id] = {
            "group_id": group_id,
            "group_name": group_name,
            "value_id": _value_id_for(
                group,
                group_id=group_id,
                value=value,
                requested_value_id=update.value_id,
            ),
            "value": value,
            "source": "manual_review",
        }
    for new_group in request.new_groups:
        group_id = stable_group_id(context.category_id, new_group.group_name)
        value = new_group.value.strip()
        group = _find_group(
            context.filter_category, group_id=group_id, group_name=new_group.group_name
        )
        next_values[group_id] = {
            "group_id": group_id,
            "group_name": str((group or {}).get("name") or new_group.group_name),
            "value_id": _value_id_for(
                group, group_id=group_id, value=value, requested_value_id=None
            ),
            "value": value,
            "source": "manual_review",
        }

    values_changed = next_values != previous_values
    review_changed = values_changed or manual_result.changed
    approved = bool(previous_payload.get("approved")) and not review_changed
    approved_at = previous_payload.get("approved_at") if approved else None
    review_payload = _canonical_review_payload(
        context,
        values=next_values,
        approved=approved,
        approved_at=str(approved_at) if approved_at else None,
        warnings=warnings,
    )
    _write_review_payload(context.review_path, review_payload)
    return _build_state(context, review_payload=review_payload)


def approve_filter_review(model: str) -> FilterReviewResponse:
    context = _load_prepared_review_context(model)
    review_payload = load_category_filter_review_payload(context.model_root)

    payload = _canonical_review_payload(
        context,
        values=_canonical_review_values(review_payload, context.filter_category),
        approved=True,
        approved_at=utcnow_iso(),
        warnings=(
            list(review_payload.get("warnings", []))
            if isinstance(review_payload, dict)
            else []
        ),
    )
    _write_review_payload(context.review_path, payload)
    return _build_state(context, review_payload=payload)


def _load_prepared_review_context(model: str) -> _PreparedReviewContext:
    model_root = repo_paths.model_root_path(model)
    prepared = PreparedProductContext.from_model(model, model_root=model_root)
    if (
        not prepared.source_json_path.exists()
        or not prepared.scrape_normalized_json_path.exists()
    ):
        raise PreparedArtifactsNotFoundError(
            f"Prepared product artifacts not found for model {model}. Run prepare first."
        )

    source = _load_source_product(prepared.source_json_path)
    normalized = read_json(prepared.scrape_normalized_json_path)
    taxonomy = TaxonomyResolution(**normalized.get("taxonomy", {}))
    taxonomy_path = canonical_taxonomy_path(taxonomy)
    filter_map = read_json(repo_paths.FILTER_MAP_PATH)
    filter_category = find_filter_category(
        filter_map,
        category_id=taxonomy.category_id,
        taxonomy_path=taxonomy_path,
    )
    category_id = str(
        (filter_category or {}).get("category_id") or taxonomy.category_id or ""
    )
    if filter_category and not taxonomy_path:
        taxonomy_path = str(filter_category.get("path", "") or "")
    return _PreparedReviewContext(
        model=model,
        model_root=model_root,
        source=source,
        taxonomy=taxonomy,
        filter_map=filter_map,
        filter_category=filter_category,
        category_id=category_id,
        taxonomy_path=taxonomy_path,
        review_path=repo_paths.category_filter_review_path(model),
    )


def _build_state(
    context: _PreparedReviewContext,
    *,
    review_payload: dict[str, Any],
) -> FilterReviewResponse:
    approved = bool(review_payload.get("approved"))
    approved_at = str(review_payload.get("approved_at") or "") or None
    review_values = coerce_category_filter_review_values(review_payload)
    warnings = (
        list(review_payload.get("warnings", []))
        if isinstance(review_payload.get("warnings"), list)
        else []
    )
    if context.filter_category is None:
        warnings.append("category_filter_map_entry_not_found")
        return FilterReviewResponse(
            model=context.model,
            category_id=context.category_id,
            taxonomy_path=context.taxonomy_path,
            filter_category_found=False,
            approved=approved,
            approved_at=approved_at,
            render_blocked=False,
            render_block_reasons=[],
            missing_required_groups=[],
            groups=[],
            warnings=warnings,
            review_artifact_path=str(context.review_path),
        )

    display_resolution = resolve_category_filter_values(
        context.source,
        context.taxonomy,
        context.filter_category,
        review_values=review_values,
    )
    render_resolution = resolve_category_filter_values(
        context.source,
        context.taxonomy,
        context.filter_category,
        review_values=review_values,
    )
    render_missing = {
        group.group_id for group in render_resolution.groups if group.missing_required
    }

    groups = [
        _build_group_response(
            group,
            context.filter_category,
            review_values=review_values,
            render_missing=render_missing,
        )
        for group in display_resolution.groups
    ]
    render_block_reasons: list[str] = []
    render_blocked = False
    missing_required_groups = [
        group for group in groups if group.group_id in render_missing
    ]
    merged_warnings = [*warnings, *display_resolution.warnings]
    if review_values and not approved:
        merged_warnings.append("category_filter_review_not_approved")

    return FilterReviewResponse(
        model=context.model,
        category_id=display_resolution.category_id or context.category_id,
        taxonomy_path=display_resolution.taxonomy_path or context.taxonomy_path,
        filter_category_found=True,
        approved=approved,
        approved_at=approved_at,
        render_blocked=render_blocked,
        render_block_reasons=render_block_reasons,
        missing_required_groups=missing_required_groups,
        groups=groups,
        warnings=list(dict.fromkeys(merged_warnings)),
        review_artifact_path=str(context.review_path),
    )


def _filter_review_blocking_reasons(review: FilterReviewResponse) -> list[str]:
    values = [
        *list(getattr(review, "warnings", []) or []),
        *list(getattr(review, "render_block_reasons", []) or []),
    ]
    for group in list(getattr(review, "groups", []) or []):
        group_name = str(getattr(group, "group_name", "") or "").strip()
        for label, attr in (
            ("Missing required", "missing_required"),
            ("Outside allowed", "outside_allowed"),
            ("Deprecated", "deprecated_value"),
            ("Inactive group", "inactive_group"),
            ("Not emitted", "emitted_if_rendered"),
        ):
            if attr == "emitted_if_rendered":
                active = getattr(group, attr, None) is False
            else:
                active = bool(getattr(group, attr, False))
            if active:
                values.append(f"{group_name}: {label}" if group_name else label)
    return [
        item
        for item in dict.fromkeys(str(value).strip() for value in values)
        if item and item != "category_filter_review_not_approved"
    ]


def _filter_review_missing_required_labels(
    review: FilterReviewResponse,
) -> list[str]:
    if bool(getattr(review, "approved", False)) and not bool(
        getattr(review, "render_blocked", False)
    ):
        return []
    labels: list[str] = []
    for group in list(getattr(review, "missing_required_groups", []) or []):
        label = str(
            getattr(group, "group_name", None)
            or getattr(group, "group_id", None)
            or group
            or ""
        ).strip()
        if label:
            labels.append(label)
    return list(dict.fromkeys(labels))


def _build_group_response(
    group_resolution: Any,
    filter_category: dict[str, Any],
    *,
    review_values: dict[str, str],
    render_missing: set[str],
) -> FilterReviewGroup:
    group = (
        _find_group(
            filter_category,
            group_id=group_resolution.group_id,
            group_name=group_resolution.group_name,
        )
        or {}
    )
    reviewed_value = (
        review_values.get(group_resolution.group_id)
        or review_values.get(group_resolution.group_name)
        or ""
    )
    allowed_values = [
        FilterReviewValue(
            value_id=str(value.get("value_id", "") or ""),
            value=str(value.get("value", "") or ""),
            status=str(value.get("status", "active") or "active"),
        )
        for value in group.get("values", [])
        if isinstance(value, dict)
    ]
    return FilterReviewGroup(
        group_id=group_resolution.group_id,
        group_name=group_resolution.group_name,
        required=group_resolution.required,
        status=group_resolution.group_status,
        allowed_values=allowed_values,
        resolved_value=(
            group_resolution.resolved_value
            if group_resolution.resolved_from != "approved_review"
            else ""
        ),
        reviewed_value=reviewed_value,
        effective_value=group_resolution.resolved_value,
        effective_value_id=_value_id_for(
            group,
            group_id=group_resolution.group_id,
            value=group_resolution.resolved_value,
        ),
        value_status=group_resolution.value_status or None,
        source=(
            "manual_review"
            if group_resolution.resolved_from == "approved_review"
            else group_resolution.resolved_from
        ),
        missing_required=group_resolution.group_id in render_missing,
        outside_allowed=group_resolution.outside_allowed,
        deprecated_value=group_resolution.deprecated_value,
        inactive_group=group_resolution.inactive_group,
        emitted_if_rendered=group_resolution.emitted,
    )


def _apply_global_updates(
    context: _PreparedReviewContext, request: FilterReviewUpdateRequest
) -> _ManualUpdateResult:
    should_update = request.add_new_values_globally
    candidate_updates = [
        update for update in request.values if update.add_to_global and should_update
    ]
    if not candidate_updates and not request.group_updates and not request.new_groups:
        return _ManualUpdateResult(filter_map=context.filter_map)

    with _filter_persistence_lock("filter_review_global_update"):
        manual = load_manual_overrides(repo_paths.FILTER_MAP_MANUAL_OVERRIDES_PATH)
        category = (
            deepcopy(context.filter_category) if context.filter_category else None
        )
        if category is None:
            return _ManualUpdateResult(
                filter_map=context.filter_map,
                warnings=["category_filter_global_update_skipped_missing_category"],
            )

        category_override = manual.setdefault("categories", {}).setdefault(
            context.category_id,
            {
                "category_id": context.category_id,
                "path": context.taxonomy_path or category.get("path", ""),
                "groups": {},
            },
        )
        category_override.setdefault("category_id", context.category_id)
        category_override.setdefault(
            "path", context.taxonomy_path or category.get("path", "")
        )
        groups_override = category_override.setdefault("groups", {})
        warnings: list[str] = []
        changed = False

        for update in candidate_updates:
            group = _find_group(
                category, group_id=update.group_id or "", group_name=update.group_name
            )
            if group is None:
                continue
            added, duplicate_warning = _ensure_manual_value(
                groups_override, group, update.value, update.value_id
            )
            changed = changed or added
            if duplicate_warning:
                warnings.append(duplicate_warning)

        for group_update in request.group_updates:
            group = _find_group(
                category,
                group_id=group_update.group_id or "",
                group_name=group_update.group_name,
            )
            if group is None:
                warnings.append(
                    f"category_filter_group_update_skipped_missing_group:{group_update.group_name}"
                )
                continue
            updated = _ensure_manual_group_update(groups_override, group, group_update)
            changed = changed or updated

        for new_group in request.new_groups:
            group_id = stable_group_id(context.category_id, new_group.group_name)
            group = _find_group(
                category, group_id=group_id, group_name=new_group.group_name
            )
            if group is None:
                group = {
                    "group_id": group_id,
                    "name": new_group.group_name,
                    "required": new_group.required,
                    "status": new_group.status,
                    "values": [],
                }
                changed = True
            group_override = groups_override.setdefault(
                group_id,
                {
                    "group_id": group_id,
                    "name": new_group.group_name,
                    "required": new_group.required,
                    "status": new_group.status,
                    "values": {},
                },
            )
            for field_name, value in {
                "name": new_group.group_name,
                "required": new_group.required,
                "status": new_group.status,
            }.items():
                if group_override.get(field_name) != value:
                    group_override[field_name] = value
                    changed = True
            value_id = stable_value_id(group_id, new_group.value)
            if value_id not in group_override.setdefault("values", {}):
                group_override["values"][value_id] = {
                    "value_id": value_id,
                    "value": new_group.value,
                    "status": new_group.value_status,
                }
                changed = True

        if not changed:
            return _ManualUpdateResult(filter_map=context.filter_map, warnings=warnings)

        final_map, _revision = _persist_manual_and_sync(
            manual,
            operation="filter_review_global_update",
            updated_at=_utc_now(),
        )
    return _ManualUpdateResult(filter_map=final_map, warnings=warnings, changed=True)


def _ensure_manual_value(
    groups_override: dict[str, Any],
    group: dict[str, Any],
    display_value: str,
    requested_value_id: str | None,
) -> tuple[bool, str | None]:
    display_value = display_value.strip()
    existing = _find_value(group, value=display_value, value_id=requested_value_id)
    if existing is not None:
        return False, None
    normalized_duplicate = _find_value(
        group, value=display_value, value_id=None, normalized=True
    )
    warning = (
        f"normalized_duplicate_value_detected:{group.get('name')}:{display_value}"
        if normalized_duplicate
        else None
    )
    group_id = str(group.get("group_id", "") or "")
    value_id = requested_value_id or stable_value_id(group_id, display_value)
    group_override = groups_override.setdefault(
        group_id,
        {
            "group_id": group_id,
            "name": group.get("name", ""),
            "required": bool(group.get("required", True)),
            "status": group.get("status", "active"),
            "values": {},
        },
    )
    values_override = group_override.setdefault("values", {})
    if value_id in values_override:
        return False, warning
    values_override[value_id] = {
        "value_id": value_id,
        "value": display_value,
        "status": "active",
    }
    return True, warning


def _ensure_manual_group_update(
    groups_override: dict[str, Any],
    group: dict[str, Any],
    update: FilterReviewGroupUpdate,
) -> bool:
    group_id = str(group.get("group_id", "") or update.group_id or "")
    if not group_id:
        return False
    group_override = groups_override.setdefault(
        group_id,
        {
            "group_id": group_id,
            "name": group.get("name", update.group_name),
            "required": bool(group.get("required", True)),
            "status": group.get("status", "active"),
            "values": {},
        },
    )
    changed = False
    desired = {
        "name": str(group.get("name") or update.group_name),
    }
    if update.required is not None:
        desired["required"] = update.required
    if update.status is not None:
        desired["status"] = update.status
    for field_name, value in desired.items():
        if group_override.get(field_name) != value:
            group_override[field_name] = value
            changed = True
    group_override.setdefault("values", {})
    return changed


def _canonical_review_payload(
    context: _PreparedReviewContext,
    *,
    values: dict[str, dict[str, str]],
    approved: bool,
    approved_at: str | None,
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "model": context.model,
        "category_id": context.category_id,
        "taxonomy_path": context.taxonomy_path,
        "approved": approved,
        "approved_at": approved_at,
        "updated_at": utcnow_iso(),
        "values": values,
        "warnings": list(dict.fromkeys(warnings)),
    }


def _canonical_review_values(
    payload: dict[str, Any],
    filter_category: dict[str, Any] | None,
) -> dict[str, dict[str, str]]:
    values = payload.get("values", {}) if isinstance(payload, dict) else {}
    if not isinstance(values, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for key, item in values.items():
        if isinstance(item, dict):
            group_name = str(item.get("group_name", "") or "").strip()
            group = _find_group(
                filter_category,
                group_id=str(item.get("group_id") or key or ""),
                group_name=group_name,
            )
            group_id = str(
                (group or {}).get("group_id") or item.get("group_id") or key or ""
            ).strip()
            group_name = str((group or {}).get("name") or group_name).strip()
            value = str(item.get("value", "") or "").strip()
            if group_id and value:
                out[group_id] = {
                    "group_id": group_id,
                    "group_name": group_name,
                    "value_id": str(item.get("value_id", "") or "").strip(),
                    "value": value,
                    "source": str(
                        item.get("source", "manual_review") or "manual_review"
                    ),
                }
            continue
        group_name = str(key or "").strip()
        value = str(item or "").strip()
        if group_name and value:
            group = _find_group(filter_category, group_id="", group_name=group_name)
            group_id = str((group or {}).get("group_id") or group_name)
            canonical_name = str((group or {}).get("name") or group_name)
            out[group_id] = {
                "group_id": group_id,
                "group_name": canonical_name,
                "value_id": _value_id_for(group, group_id=group_id, value=value) or "",
                "value": value,
                "source": "manual_review",
            }
    return out


def _write_review_payload(path: Path, payload: dict[str, Any]) -> None:
    ensure_directory(path.parent)
    write_json(path, payload)


def _find_group(
    category: dict[str, Any] | None, *, group_id: str = "", group_name: str = ""
) -> dict[str, Any] | None:
    if not category:
        return None
    normalized_name = normalize_for_match(group_name)
    for group in category.get("filter_groups", []):
        if not isinstance(group, dict):
            continue
        if group_id and group.get("group_id") == group_id:
            return group
        if group_name and group.get("name") == group_name:
            return group
    for group in category.get("filter_groups", []):
        if (
            isinstance(group, dict)
            and normalized_name
            and normalize_for_match(group.get("name", "")) == normalized_name
        ):
            return group
    return None


def _find_value(
    group: dict[str, Any] | None,
    *,
    value: str,
    value_id: str | None,
    normalized: bool = False,
) -> dict[str, Any] | None:
    if not group:
        return None
    normalized_value = normalize_for_match(value)
    for item in group.get("values", []):
        if not isinstance(item, dict):
            continue
        if value_id and item.get("value_id") == value_id:
            return item
        item_value = str(item.get("value", "") or "")
        if not normalized and item_value == value:
            return item
        if normalized and normalize_for_match(item_value) == normalized_value:
            return item
    return None


def _value_id_for(
    group: dict[str, Any] | None,
    *,
    group_id: str,
    value: str,
    requested_value_id: str | None = None,
) -> str | None:
    if not value:
        return requested_value_id
    existing = _find_value(group, value=value, value_id=requested_value_id)
    if existing is not None:
        return str(existing.get("value_id", "") or "") or None
    return requested_value_id or stable_value_id(group_id, value)


def _load_source_product(path: Path) -> SourceProductData:
    payload = read_json(path)
    source_fields = {field.name for field in fields(SourceProductData)}
    clean_payload = {
        key: value for key, value in payload.items() if key in source_fields
    }
    return SourceProductData(
        **{
            **clean_payload,
            "key_specs": [SpecItem(**item) for item in payload.get("key_specs", [])],
            "spec_sections": [
                SpecSection(
                    section=section.get("section", ""),
                    items=[SpecItem(**item) for item in section.get("items", [])],
                )
                for section in payload.get("spec_sections", [])
            ],
            "manufacturer_spec_sections": [
                SpecSection(
                    section=section.get("section", ""),
                    items=[SpecItem(**item) for item in section.get("items", [])],
                )
                for section in payload.get("manufacturer_spec_sections", [])
            ],
        }
    )
