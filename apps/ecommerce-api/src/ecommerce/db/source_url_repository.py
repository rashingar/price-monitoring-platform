"""Repository helpers for manual product source URLs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecommerce.db.models.catalog import CatalogProductRow
from ecommerce.db.models.source_urls import SourceUrl
from ecommerce.db.repositories import json_safe_value
from ecommerce.db.source_convergence import sync_source_url_to_product_source
from ecommerce.source_urls import (
    SourceUrlValidationResult,
    extract_source_domain,
    infer_source_name,
    normalize_source_url,
)

SOURCE_URL_STATUSES = {"active", "disabled", "broken", "redirected", "needs_review"}
SOURCE_URL_TYPES = {"manual", "imported", "discovered"}


@dataclass(frozen=True)
class ImportedSourceUrlUpsertResult:
    row: SourceUrl | None
    action: str
    source_url_id: int | None
    changed_fields: list[str]


def get_active_catalog_product(session: Session, catalog_product_id: int) -> CatalogProductRow | None:
    return session.execute(
        select(CatalogProductRow).where(
            CatalogProductRow.id == catalog_product_id,
            CatalogProductRow.active.is_(True),
        )
    ).scalar_one_or_none()


def get_source_url(session: Session, source_url_id: int) -> SourceUrl | None:
    return session.get(SourceUrl, source_url_id)


def list_source_urls_for_catalog_product(session: Session, catalog_product_id: int) -> list[SourceUrl]:
    statement = (
        select(SourceUrl)
        .where(SourceUrl.catalog_product_id == catalog_product_id)
        .order_by(SourceUrl.updated_at.desc(), SourceUrl.id.desc())
    )
    return list(session.execute(statement).scalars().all())


def list_active_source_urls_for_catalog_products(
    session: Session,
    catalog_product_ids: list[int],
    *,
    source_name: str | None = None,
) -> list[SourceUrl]:
    if not catalog_product_ids:
        return []
    statement = (
        select(SourceUrl)
        .join(CatalogProductRow, CatalogProductRow.id == SourceUrl.catalog_product_id)
        .where(
            SourceUrl.catalog_product_id.in_([int(item) for item in catalog_product_ids]),
            SourceUrl.status == "active",
            CatalogProductRow.active.is_(True),
        )
        .order_by(SourceUrl.catalog_product_id.asc(), SourceUrl.id.asc())
    )
    if source_name:
        statement = statement.where(SourceUrl.source_name == source_name)
    return list(session.execute(statement).scalars().all())


def create_or_update_manual_source_url(
    session: Session,
    catalog_product_id: int,
    payload: dict[str, Any],
) -> SourceUrl:
    product = get_active_catalog_product(session, catalog_product_id)
    if product is None:
        raise LookupError("Catalog product not found.")

    url = _required_text(payload.get("url"), "url")
    normalized_url = normalize_source_url(url)
    domain = extract_source_domain(normalized_url)
    supplied_source_name = _optional_text(payload.get("source_name"))
    source_name = supplied_source_name or infer_source_name(domain)
    url_type = _validated_url_type(_optional_text(payload.get("url_type")) or "manual")
    trust_level = _optional_text(payload.get("trust_level")) or "manual"
    timestamp = _now()

    existing = _find_source_url_by_normalized_url(session, catalog_product_id, normalized_url)
    if existing is not None:
        existing.source_name = source_name
        existing.source_domain = domain
        existing.url = url.strip()
        existing.url_type = url_type
        existing.trust_level = trust_level
        if "added_by" in payload:
            existing.added_by = _optional_text(payload.get("added_by"))
        if "notes" in payload:
            existing.notes = _optional_text(payload.get("notes"))
        _sync_catalog_fields(existing, product)
        existing.updated_at = timestamp
        session.flush()
        sync_source_url_to_product_source(session, existing)
        return existing

    row = SourceUrl(
        catalog_product_id=product.id,
        catalog_source=product.catalog_source,
        model=product.model,
        mpn=product.mpn or "",
        manufacturer=product.manufacturer or "",
        source_name=source_name,
        source_domain=domain,
        url=url.strip(),
        url_normalized=normalized_url,
        status="active",
        url_type=url_type,
        trust_level=trust_level,
        added_by=_optional_text(payload.get("added_by")),
        notes=_optional_text(payload.get("notes")),
        failure_count=0,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(row)
    session.flush()
    sync_source_url_to_product_source(session, row)
    return row


def create_or_update_imported_source_url(
    session: Session,
    *,
    catalog_product_id: int,
    url: str,
    source_name: str | None = None,
    url_type: str = "imported",
    trust_level: str = "imported",
    status: str = "needs_review",
    last_seen_at: datetime | None = None,
    last_success_at: datetime | None = None,
    last_error: str | None = None,
    notes: str | None = None,
    apply: bool = True,
) -> ImportedSourceUrlUpsertResult:
    product = get_active_catalog_product(session, catalog_product_id)
    if product is None:
        raise LookupError("Catalog product not found.")

    clean_url = _required_text(url, "url")
    normalized_url = normalize_source_url(clean_url)
    domain = extract_source_domain(normalized_url)
    resolved_source_name = _optional_text(source_name) or infer_source_name(domain)
    resolved_url_type = _validated_url_type(url_type)
    resolved_trust_level = _optional_text(trust_level) or "imported"
    resolved_status = _validated_status(status)
    timestamp = _now()

    existing = _find_source_url_by_normalized_url(session, catalog_product_id, normalized_url)
    if existing is None:
        if not apply:
            return ImportedSourceUrlUpsertResult(row=None, action="created", source_url_id=None, changed_fields=[])
        row = SourceUrl(
            catalog_product_id=product.id,
            catalog_source=product.catalog_source,
            model=product.model,
            mpn=product.mpn or "",
            manufacturer=product.manufacturer or "",
            source_name=resolved_source_name,
            source_domain=domain,
            url=clean_url.strip(),
            url_normalized=normalized_url,
            status=resolved_status,
            url_type=resolved_url_type,
            trust_level=resolved_trust_level,
            notes=_optional_text(notes),
            last_seen_at=_timestamp_or_none(last_seen_at),
            last_success_at=_timestamp_or_none(last_success_at),
            last_error=_short_text(last_error) if last_error else None,
            failure_count=0,
            created_at=timestamp,
            updated_at=timestamp,
        )
        session.add(row)
        session.flush()
        sync_source_url_to_product_source(session, row)
        return ImportedSourceUrlUpsertResult(row=row, action="created", source_url_id=row.id, changed_fields=[])

    updates = _imported_source_url_updates(
        existing,
        product,
        source_name=resolved_source_name,
        source_domain=domain,
        url=clean_url.strip(),
        url_type=resolved_url_type,
        trust_level=resolved_trust_level,
        status=resolved_status,
        last_seen_at=_timestamp_or_none(last_seen_at),
        last_success_at=_timestamp_or_none(last_success_at),
        last_error=_short_text(last_error) if last_error else None,
        notes=_optional_text(notes),
    )
    changed_fields = list(updates.keys())
    if not changed_fields:
        if apply:
            sync_source_url_to_product_source(session, existing)
        return ImportedSourceUrlUpsertResult(row=existing, action="duplicate", source_url_id=existing.id, changed_fields=[])
    if not apply:
        return ImportedSourceUrlUpsertResult(row=existing, action="updated", source_url_id=existing.id, changed_fields=changed_fields)

    for field_name, value in updates.items():
        setattr(existing, field_name, value)
    existing.updated_at = timestamp
    session.flush()
    sync_source_url_to_product_source(session, existing)
    return ImportedSourceUrlUpsertResult(row=existing, action="updated", source_url_id=existing.id, changed_fields=changed_fields)


def update_source_url(session: Session, source_url_id: int, payload: dict[str, Any]) -> SourceUrl | None:
    row = get_source_url(session, source_url_id)
    if row is None:
        return None

    explicit_source_name = "source_name" in payload
    if "status" in payload:
        row.status = _validated_status(_optional_text(payload.get("status")) or "")
    if explicit_source_name:
        row.source_name = _required_text(payload.get("source_name"), "source_name")
    if "trust_level" in payload:
        row.trust_level = _required_text(payload.get("trust_level"), "trust_level")
    if "notes" in payload:
        row.notes = _optional_text(payload.get("notes"))
    if "url" in payload:
        url = _required_text(payload.get("url"), "url")
        normalized_url = normalize_source_url(url)
        duplicate = _find_source_url_by_normalized_url(session, row.catalog_product_id, normalized_url)
        if duplicate is not None and duplicate.id != row.id:
            raise ValueError("Source URL already exists for this catalog product.")
        row.url = url.strip()
        row.url_normalized = normalized_url
        row.source_domain = extract_source_domain(normalized_url)
        if not explicit_source_name:
            row.source_name = infer_source_name(row.source_domain)

    product = get_active_catalog_product(session, row.catalog_product_id)
    if product is not None:
        _sync_catalog_fields(row, product)
    row.updated_at = _now()
    session.flush()
    sync_source_url_to_product_source(session, row)
    return row


def apply_source_url_validation_result(
    session: Session,
    source_url_id: int,
    result: SourceUrlValidationResult,
) -> SourceUrl | None:
    row = get_source_url(session, source_url_id)
    if row is None:
        return None

    timestamp = _now()
    row.last_seen_at = timestamp
    if result.status == "success":
        row.last_success_at = timestamp
        row.last_error = None
        row.failure_count = 0
        if row.status != "disabled":
            row.status = "active"
    elif result.status == "failed":
        row.last_failed_at = timestamp
        row.failure_count = int(row.failure_count or 0) + 1
        row.last_error = _short_text(result.message)
        row.status = "broken"
    else:
        row.last_error = _short_text(result.message)
    row.updated_at = timestamp
    session.flush()
    sync_source_url_to_product_source(session, row)
    return row


def source_url_to_dict(row: SourceUrl) -> dict[str, Any]:
    return {
        "id": row.id,
        "catalog_product_id": row.catalog_product_id,
        "catalog_source": row.catalog_source,
        "model": row.model,
        "mpn": row.mpn,
        "manufacturer": row.manufacturer,
        "source_name": row.source_name,
        "source_domain": row.source_domain,
        "url": row.url,
        "url_normalized": row.url_normalized,
        "status": row.status,
        "url_type": row.url_type,
        "trust_level": row.trust_level,
        "added_by": row.added_by,
        "notes": row.notes,
        "last_seen_at": json_safe_value(row.last_seen_at),
        "last_success_at": json_safe_value(row.last_success_at),
        "last_failed_at": json_safe_value(row.last_failed_at),
        "failure_count": row.failure_count,
        "last_error": row.last_error,
        "created_at": json_safe_value(row.created_at),
        "updated_at": json_safe_value(row.updated_at),
    }


def _find_source_url_by_normalized_url(session: Session, catalog_product_id: int, normalized_url: str) -> SourceUrl | None:
    return session.execute(
        select(SourceUrl).where(
            SourceUrl.catalog_product_id == catalog_product_id,
            SourceUrl.url_normalized == normalized_url,
        )
    ).scalar_one_or_none()


def _sync_catalog_fields(row: SourceUrl, product: CatalogProductRow) -> None:
    row.catalog_source = product.catalog_source
    row.model = product.model
    row.mpn = product.mpn or ""
    row.manufacturer = product.manufacturer or ""


def _imported_source_url_updates(
    row: SourceUrl,
    product: CatalogProductRow,
    *,
    source_name: str,
    source_domain: str,
    url: str,
    url_type: str,
    trust_level: str,
    status: str,
    last_seen_at: datetime | None,
    last_success_at: datetime | None,
    last_error: str | None,
    notes: str | None,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    _set_if_changed(updates, row, "catalog_source", product.catalog_source)
    _set_if_changed(updates, row, "model", product.model)
    _set_if_changed(updates, row, "mpn", product.mpn or "")
    _set_if_changed(updates, row, "manufacturer", product.manufacturer or "")
    _set_if_changed(updates, row, "source_name", source_name)
    _set_if_changed(updates, row, "source_domain", source_domain)
    _set_if_changed(updates, row, "url", url)

    if row.url_type != "manual":
        _set_if_changed(updates, row, "url_type", url_type)
        _set_if_changed(updates, row, "trust_level", trust_level)

    if row.status != "disabled":
        next_status = row.status
        if row.status == "broken" and status == "active" and last_success_at is not None:
            next_status = "active"
        elif row.status == "needs_review" and status == "active":
            next_status = "active"
        elif row.status not in {"active", "broken", "redirected"}:
            next_status = status
        _set_if_changed(updates, row, "status", next_status)

    seen_at = _newer_datetime(row.last_seen_at, last_seen_at)
    success_at = _newer_datetime(row.last_success_at, last_success_at)
    if seen_at is not row.last_seen_at:
        updates["last_seen_at"] = seen_at
    if success_at is not row.last_success_at:
        updates["last_success_at"] = success_at
    if last_error is not None and row.last_error != last_error:
        updates["last_error"] = last_error
    if notes is not None and row.notes != notes:
        updates["notes"] = notes
    return updates


def _set_if_changed(updates: dict[str, Any], row: SourceUrl, field_name: str, value: Any) -> None:
    if getattr(row, field_name) != value:
        updates[field_name] = value


def _newer_datetime(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    current_cmp = current if current.tzinfo is not None else current.replace(tzinfo=timezone.utc)
    candidate_cmp = candidate if candidate.tzinfo is not None else candidate.replace(tzinfo=timezone.utc)
    return candidate if candidate_cmp > current_cmp else current


def _validated_status(value: str) -> str:
    text = value.strip()
    if text not in SOURCE_URL_STATUSES:
        raise ValueError("status must be one of: active, disabled, broken, redirected, needs_review")
    return text


def _validated_url_type(value: str) -> str:
    text = value.strip()
    if text not in SOURCE_URL_TYPES:
        raise ValueError("url_type must be one of: manual, imported, discovered")
    return text


def _required_text(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _short_text(value: object, *, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _timestamp_or_none(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
