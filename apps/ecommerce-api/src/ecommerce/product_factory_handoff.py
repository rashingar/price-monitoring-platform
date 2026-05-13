"""Import Product Factory source URL handoff artifacts."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecommerce.catalog.source_catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.models import CatalogProductRow, Product, ProductSource, SourceCaptureSnapshot
from ecommerce.db.capture_persistence import persist_capture_result
from ecommerce.db.product_source_repository import product_source_to_dict
from ecommerce.db.repositories import json_safe_value
from ecommerce.db.source_convergence import sync_source_url_to_product_source
from ecommerce.db.source_url_repository import create_or_update_imported_source_url, source_url_to_dict
from ecommerce.source_capture.detect_vendor import detect_vendor_slug
from ecommerce.source_capture.sanitize import content_hash, sanitize_json
from ecommerce.source_capture.types import CaptureResult, CaptureSnapshotPayload, ParsedPriceObservation
from ecommerce.source_capture.vendor_registry import VENDORS_BY_SLUG
from ecommerce.source_urls import SourceUrlValidationError, extract_source_domain, infer_source_name, normalize_source_url


PRODUCT_FACTORY_HANDOFF_IMPORT_VERSION = "product_factory_source_handoff_import_v1"
SOURCE_CONFIDENCE_ACTIVE_THRESHOLD = Decimal("0.85")


@dataclass(frozen=True)
class HandoffIdentity:
    catalog_source: str
    catalog_product_id: int | None
    model: str | None
    mpn: str | None


@dataclass(frozen=True)
class HandoffPriceEvidence:
    price: Decimal | None
    currency: str
    observed_at: datetime | None
    confidence: Decimal | None
    availability: str | None
    stock_status: str | None
    delivery_text: str | None
    product_name: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class HandoffSource:
    url: str
    source_name: str | None
    confidence: Decimal | None
    evidence: dict[str, Any]
    raw: dict[str, Any]
    price: HandoffPriceEvidence | None
    capture_snapshot: dict[str, Any]
    raw_html: str | None


@dataclass(frozen=True)
class ProductFactoryHandoff:
    path: Path
    payload: dict[str, Any]
    identity: HandoffIdentity
    sources: tuple[HandoffSource, ...]


@dataclass(frozen=True)
class CatalogProductResolution:
    product: CatalogProductRow | None
    match_type: str
    confidence: str
    warning: str | None = None


@dataclass
class ProductFactoryHandoffImportResult:
    apply: bool
    file_path: str
    counters: Counter[str] = field(default_factory=Counter)
    warnings: list[str] = field(default_factory=list)
    skipped_reasons: Counter[str] = field(default_factory=Counter)
    report_items: list[dict[str, Any]] = field(default_factory=list)
    changed_source_urls: list[dict[str, Any]] = field(default_factory=list)
    changed_product_sources: list[dict[str, Any]] = field(default_factory=list)
    source_stats: dict[str, Counter[str]] = field(default_factory=dict)

    def to_dict(self, *, include_items: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "apply": self.apply,
            "file_path": self.file_path,
            "counters": {key: int(value) for key, value in sorted(self.counters.items())},
            "warnings": list(self.warnings),
            "skipped_reasons": dict(self.skipped_reasons),
            "changed_source_urls": list(self.changed_source_urls),
            "changed_product_sources": list(self.changed_product_sources),
            "source_stats": {key: dict(value) for key, value in self.source_stats.items()},
        }
        if include_items:
            payload["items"] = list(self.report_items)
        return payload


def parse_product_factory_handoff(path: Path | str) -> ProductFactoryHandoff:
    artifact_path = Path(path).expanduser().resolve(strict=False)
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read Product Factory handoff artifact {artifact_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Product Factory handoff artifact is not a JSON object: {artifact_path}")

    version = _first_text(
        payload.get("schema_version"),
        payload.get("handoff_schema_version"),
        payload.get("ecommerce_source_handoff_schema_version"),
        "v1",
    ).lower()
    if version not in {"1", "v1", "schema_v1"}:
        raise ValueError(f"Unsupported Product Factory handoff schema version: {version}")

    identity = _parse_identity(payload, artifact_path)
    sources = tuple(_iter_handoff_sources(payload))
    if not sources:
        raise ValueError(f"Product Factory handoff contains no source URLs: {artifact_path}")
    return ProductFactoryHandoff(path=artifact_path, payload=payload, identity=identity, sources=sources)


def import_product_factory_handoff(
    session: Session,
    *,
    file_path: Path | str,
    apply: bool = False,
    catalog_source: str | None = None,
    persist_initial_capture: bool = True,
    limit: int | None = None,
) -> ProductFactoryHandoffImportResult:
    handoff = parse_product_factory_handoff(file_path)
    identity = handoff.identity
    if catalog_source:
        identity = HandoffIdentity(
            catalog_source=str(catalog_source).strip() or DEFAULT_CATALOG_SOURCE,
            catalog_product_id=identity.catalog_product_id,
            model=identity.model,
            mpn=identity.mpn,
        )
    result = ProductFactoryHandoffImportResult(apply=apply, file_path=str(handoff.path))
    _source_stat(result, "product_factory_handoff", "processed")

    resolution = resolve_catalog_product_for_handoff(session, identity)
    if resolution.product is None:
        reason = "ambiguous_identity" if resolution.match_type.startswith("ambiguous") else "unresolved_identity"
        for source in handoff.sources[: limit or None]:
            _skip(
                result,
                reason,
                f"{handoff.path}: {resolution.warning or resolution.match_type}",
                item=_report_item(
                    identity=identity,
                    source=source,
                    action="skipped",
                    reason=reason,
                    resolution=resolution,
                ),
            )
        return result

    seen_urls: set[str] = set()
    remaining = limit
    for index, source in enumerate(handoff.sources):
        if remaining is not None and remaining <= 0:
            break
        remaining = remaining - 1 if remaining is not None else None
        _process_source(
            session,
            handoff,
            identity=identity,
            resolution=resolution,
            source=source,
            source_index=index,
            result=result,
            seen_urls=seen_urls,
            apply=apply,
            persist_initial_capture=persist_initial_capture,
        )
    return result


def resolve_catalog_product_for_handoff(session: Session, identity: HandoffIdentity) -> CatalogProductResolution:
    catalog_source = identity.catalog_source or DEFAULT_CATALOG_SOURCE
    if identity.catalog_product_id is not None:
        product = session.get(CatalogProductRow, identity.catalog_product_id)
        if product is None or not product.active:
            return CatalogProductResolution(None, "missing_catalog_product_id", "none", "catalog_product_id not found or inactive")
        if product.catalog_source != catalog_source:
            return CatalogProductResolution(None, "ambiguous_catalog_product_id", "none", "catalog_source does not match catalog_product_id")
        if identity.model and product.model != identity.model:
            return CatalogProductResolution(None, "ambiguous_catalog_product_id", "none", "model does not match catalog_product_id")
        if identity.mpn and product.mpn and product.mpn != identity.mpn:
            return CatalogProductResolution(None, "ambiguous_catalog_product_id", "none", "MPN does not match catalog_product_id")
        return CatalogProductResolution(product, "catalog_product_id", "exact")

    if identity.model:
        product = session.execute(
            select(CatalogProductRow).where(
                CatalogProductRow.catalog_source == catalog_source,
                CatalogProductRow.model == identity.model,
                CatalogProductRow.active.is_(True),
            )
        ).scalar_one_or_none()
        if product is not None:
            return CatalogProductResolution(product, "model", "exact")

    if identity.mpn:
        matches = list(
            session.execute(
                select(CatalogProductRow)
                .where(
                    CatalogProductRow.catalog_source == catalog_source,
                    CatalogProductRow.mpn == identity.mpn,
                    CatalogProductRow.active.is_(True),
                )
                .limit(2)
            )
            .scalars()
            .all()
        )
        if len(matches) == 1:
            return CatalogProductResolution(matches[0], "mpn", "weak")
        if len(matches) > 1:
            return CatalogProductResolution(None, "ambiguous_mpn", "none", "multiple active catalog products matched MPN")

    if not identity.model and not identity.mpn:
        return CatalogProductResolution(None, "missing_identity", "none", "missing catalog_product_id, model, and MPN")
    return CatalogProductResolution(None, "unresolved", "none", "no active catalog product matched")


def _process_source(
    session: Session,
    handoff: ProductFactoryHandoff,
    *,
    identity: HandoffIdentity,
    resolution: CatalogProductResolution,
    source: HandoffSource,
    source_index: int,
    result: ProductFactoryHandoffImportResult,
    seen_urls: set[str],
    apply: bool,
    persist_initial_capture: bool,
) -> None:
    try:
        normalized = normalize_source_url(source.url)
        domain = extract_source_domain(normalized)
    except SourceUrlValidationError as exc:
        _skip(
            result,
            "invalid_url",
            f"{handoff.path}: {exc}",
            item=_report_item(identity=identity, source=source, action="skipped", reason="invalid_url", resolution=resolution),
        )
        return

    vendor_slug = detect_vendor_slug(normalized) or infer_source_name(domain)
    if not _supported_source(vendor_slug):
        _skip(
            result,
            "invalid_url",
            f"{handoff.path}: unsupported source URL host {domain}",
            item=_report_item(identity=identity, source=source, action="skipped", reason="invalid_url", resolution=resolution),
        )
        return

    result.counters["candidates_found"] += 1
    _source_stat(result, "product_factory_handoff", "candidates")
    if normalized in seen_urls:
        result.counters["duplicate_count"] += 1
        result.report_items.append(
            _report_item(
                identity=identity,
                source=source,
                action="duplicate",
                reason="duplicate_candidate",
                resolution=resolution,
                normalized_url=normalized,
                source_domain=domain,
            )
        )
        return
    seen_urls.add(normalized)

    status = _source_status(resolution, source)
    upsert = create_or_update_imported_source_url(
        session,
        catalog_product_id=resolution.product.id,  # type: ignore[union-attr]
        url=source.url,
        source_name=source.source_name or vendor_slug,
        url_type="imported",
        trust_level="high_confidence" if status == "active" else "imported",
        status=status,
        last_seen_at=_observed_at(source),
        last_success_at=_observed_at(source) if source.price is not None and source.price.price is not None else None,
        notes="Imported from Product Factory source handoff",
        apply=apply,
    )
    if upsert.action == "created":
        result.counters["imported_count"] += 1
    elif upsert.action == "updated":
        result.counters["updated_count"] += 1
    elif upsert.action == "duplicate":
        result.counters["duplicate_count"] += 1
    result.counters["active_count" if status == "active" else "needs_review_count"] += 1

    product_source: ProductSource | None = None
    if apply and upsert.row is not None:
        if upsert.action in {"created", "updated"}:
            result.changed_source_urls.append(
                {"action": upsert.action, "changed_fields": upsert.changed_fields, "source_url": source_url_to_dict(upsert.row)}
            )
        if status == "active":
            product_source = sync_source_url_to_product_source(session, upsert.row)
            if product_source is not None and upsert.action in {"created", "updated"}:
                result.changed_product_sources.append(product_source_to_dict(product_source))
    elif upsert.action in {"created", "updated"}:
        result.changed_source_urls.append(
            {
                "action": upsert.action,
                "changed_fields": upsert.changed_fields,
                "source_url_id": upsert.source_url_id,
                "catalog_product_id": resolution.product.id,  # type: ignore[union-attr]
                "url_normalized": normalized,
            }
        )

    snapshot_id = None
    if persist_initial_capture and status == "active" and source.price is not None:
        if apply and product_source is not None:
            snapshot = _persist_initial_capture(session, handoff, source, source_index, product_source)
            if snapshot is not None:
                snapshot_id = snapshot.id
                result.counters["snapshot_count"] += 1
                result.counters["price_observation_count"] += 1 if source.price.price is not None else 0
            else:
                result.counters["duplicate_snapshot_count"] += 1
        else:
            result.counters["would_import_snapshot_count"] += 1
            if source.price.price is not None:
                result.counters["would_import_price_observation_count"] += 1

    result.report_items.append(
        _report_item(
            identity=identity,
            source=source,
            action=upsert.action,
            reason="already_exists" if upsert.action == "duplicate" else None,
            resolution=resolution,
            normalized_url=normalized,
            source_domain=domain,
            source_url_id=upsert.source_url_id,
            product_source_id=product_source.id if product_source is not None else None,
            snapshot_id=snapshot_id,
            status=status,
        )
    )


def _persist_initial_capture(
    session: Session,
    handoff: ProductFactoryHandoff,
    source: HandoffSource,
    source_index: int,
    product_source: ProductSource,
) -> SourceCaptureSnapshot | None:
    artifact_ref = json.dumps({"handoff": str(handoff.path), "source_index": source_index}, sort_keys=True)
    digest = content_hash(source.raw_html or json.dumps(source.raw, ensure_ascii=False, sort_keys=True))
    if _snapshot_already_imported(session, source=product_source, artifact_ref=artifact_ref, digest=digest):
        return None

    db_product = session.get(Product, product_source.product_id)
    if db_product is None:
        return None
    vendor_slug = detect_vendor_slug(product_source.canonical_url) or "unknown"
    price = source.price
    observations: tuple[ParsedPriceObservation, ...] = ()
    if price is not None and price.price is not None:
        observations = (
            ParsedPriceObservation(
                price=price.price,
                currency=price.currency or "EUR",
                availability=price.availability,
                stock_status=price.stock_status,
                delivery_text=price.delivery_text,
                product_name=price.product_name,
                raw_observation={"source": "product_factory_source_handoff", "confidence": json_safe_value(price.confidence), **price.raw},
                timestamp_source="product_factory_handoff.observed_at" if price.observed_at is not None else "import_time",
                timestamp_quality="exact" if price.observed_at is not None else "fallback",
            ),
        )
    snapshot_payload = source.capture_snapshot
    observed_at = price.observed_at if price is not None else None
    now = datetime.now(timezone.utc).replace(microsecond=0)
    capture = CaptureSnapshotPayload(
        capture_strategy=f"product_factory_handoff_{vendor_slug}",
        page_url=source.url,
        final_url=_first_text(snapshot_payload.get("final_url"), snapshot_payload.get("page_url"), source.url),
        request_url=_optional_text(snapshot_payload.get("request_url")),
        request_method=_optional_text(snapshot_payload.get("request_method")) or "GET",
        response_status=_optional_int(snapshot_payload.get("response_status") or snapshot_payload.get("status_code")),
        response_content_type=_optional_text(snapshot_payload.get("response_content_type")) or ("text/html; charset=utf-8" if source.raw_html else "application/json"),
        response_body_json={
            "handoff": sanitize_json(handoff.payload),
            "source": sanitize_json(source.raw),
            "importer": {"name": "product_factory_source_handoff_import", "version": PRODUCT_FACTORY_HANDOFF_IMPORT_VERSION},
        },
        raw_html=source.raw_html,
        artifact_ref=artifact_ref,
        content_hash=digest,
        parser_version=PRODUCT_FACTORY_HANDOFF_IMPORT_VERSION,
        fetch_status_code=_optional_int(snapshot_payload.get("fetch_status_code") or snapshot_payload.get("response_status")),
        data_quality_flags=_data_quality_flags(source),
        captured_at=observed_at or _parse_datetime(snapshot_payload.get("captured_at")),
        fetched_at=observed_at or _parse_datetime(snapshot_payload.get("fetched_at")),
        parsed_at=observed_at or _parse_datetime(snapshot_payload.get("parsed_at")),
        imported_at=now,
    )
    result = CaptureResult(vendor_slug=vendor_slug, status="success", snapshot=capture, price_observations=observations)
    return persist_capture_result(session, product=db_product, source=product_source, result=result)


def _snapshot_already_imported(session: Session, *, source: ProductSource, artifact_ref: str, digest: str | None) -> bool:
    statement = select(SourceCaptureSnapshot.id).where(
        SourceCaptureSnapshot.product_source_id == source.id,
        SourceCaptureSnapshot.capture_strategy.like("product_factory_handoff%"),
        SourceCaptureSnapshot.artifact_ref == artifact_ref,
    )
    if digest:
        statement = statement.where(SourceCaptureSnapshot.content_hash == digest)
    return session.execute(statement.limit(1)).scalar_one_or_none() is not None


def _parse_identity(payload: dict[str, Any], path: Path) -> HandoffIdentity:
    product = _dict_value(payload.get("product"))
    identity = _dict_value(payload.get("identity"))
    catalog = _dict_value(payload.get("catalog"))
    catalog_source = _first_text(
        payload.get("catalog_source"),
        product.get("catalog_source"),
        identity.get("catalog_source"),
        catalog.get("catalog_source"),
        DEFAULT_CATALOG_SOURCE,
    )
    model = _empty_to_none(
        _first_text(
            payload.get("model"),
            product.get("model"),
            identity.get("model"),
            _nested(payload, ("input", "model")),
            path.parent.parent.name if path.parent.name.casefold() == "integrations" else "",
        )
    )
    return HandoffIdentity(
        catalog_source=catalog_source,
        catalog_product_id=_optional_int(
            payload.get("catalog_product_id") or product.get("catalog_product_id") or identity.get("catalog_product_id")
        ),
        model=model,
        mpn=_empty_to_none(_first_text(payload.get("mpn"), product.get("mpn"), identity.get("mpn"), _nested(payload, ("input", "mpn")))),
    )


def _iter_handoff_sources(payload: dict[str, Any]) -> Iterable[HandoffSource]:
    raw_sources: list[Any] = []
    for key in ("sources", "source_urls", "urls"):
        value = payload.get(key)
        if isinstance(value, list):
            raw_sources.extend(value)
    if isinstance(payload.get("source"), dict):
        raw_sources.append(payload["source"])
    for key in ("source_url", "url", "canonical_url", "product_url"):
        value = payload.get(key)
        if value:
            raw_sources.append(value if isinstance(value, dict) else {"url": value})

    top_price = _price_evidence_from_payload(payload)
    for raw in raw_sources:
        source_payload = raw if isinstance(raw, dict) else {"url": raw}
        url = _first_text(
            source_payload.get("url"),
            source_payload.get("source_url"),
            source_payload.get("canonical_url"),
            source_payload.get("final_url"),
            source_payload.get("product_url"),
        )
        if not url:
            continue
        capture_snapshot = _dict_value(source_payload.get("capture_snapshot") or source_payload.get("snapshot") or payload.get("capture_snapshot"))
        raw_html = _optional_text(source_payload.get("raw_html") or capture_snapshot.get("raw_html") or payload.get("raw_html"))
        yield HandoffSource(
            url=url,
            source_name=_empty_to_none(_first_text(source_payload.get("source_name"), source_payload.get("vendor"), source_payload.get("source"))),
            confidence=_decimal_value(
                source_payload.get("confidence")
                or source_payload.get("match_confidence")
                or _nested(source_payload, ("evidence", "confidence"))
            ),
            evidence=_dict_value(source_payload.get("evidence")),
            raw=source_payload,
            price=_price_evidence_from_payload(source_payload) or top_price,
            capture_snapshot=capture_snapshot,
            raw_html=raw_html,
        )


def _price_evidence_from_payload(payload: dict[str, Any]) -> HandoffPriceEvidence | None:
    if isinstance(payload.get("price_evidence"), dict):
        price_payload = _dict_value(payload.get("price_evidence"))
    elif isinstance(payload.get("price"), dict):
        price_payload = _dict_value(payload.get("price"))
    else:
        price_payload = {}
    price = _decimal_value(
        price_payload.get("price")
        or price_payload.get("price_value")
        or payload.get("price_value")
        or (payload.get("price") if not isinstance(payload.get("price"), dict) else None)
    )
    if price is None:
        return None
    return HandoffPriceEvidence(
        price=price,
        currency=_first_text(price_payload.get("currency"), payload.get("currency"), "EUR"),
        observed_at=_parse_datetime(price_payload.get("observed_at") or price_payload.get("scraped_at") or payload.get("observed_at") or payload.get("scraped_at")),
        confidence=_decimal_value(price_payload.get("confidence") or payload.get("price_confidence")),
        availability=_empty_to_none(_first_text(price_payload.get("availability"), payload.get("availability"))),
        stock_status=_empty_to_none(_first_text(price_payload.get("stock_status"), payload.get("stock_status"))),
        delivery_text=_empty_to_none(_first_text(price_payload.get("delivery_text"), payload.get("delivery_text"))),
        product_name=_empty_to_none(_first_text(price_payload.get("product_name"), price_payload.get("name"), payload.get("product_name"), payload.get("name"))),
        raw=price_payload,
    )


def _source_status(resolution: CatalogProductResolution, source: HandoffSource) -> str:
    exact_identity = resolution.match_type in {"catalog_product_id", "model"}
    if not exact_identity:
        return "needs_review"
    if source.confidence is not None and source.confidence >= SOURCE_CONFIDENCE_ACTIVE_THRESHOLD:
        return "active"
    evidence_text = " ".join(str(value).casefold() for value in source.evidence.values())
    if any(token in evidence_text for token in ("exact", "confirmed", "high_confidence", "strong")):
        return "active"
    return "needs_review"


def _observed_at(source: HandoffSource) -> datetime | None:
    if source.price is not None and source.price.observed_at is not None:
        return source.price.observed_at
    return _parse_datetime(source.raw.get("observed_at") or source.raw.get("scraped_at"))


def _supported_source(vendor_slug: str) -> bool:
    definition = VENDORS_BY_SLUG.get(vendor_slug)
    return bool(definition and definition.supports_direct_product_url)


def _data_quality_flags(source: HandoffSource) -> list[str]:
    flags: list[str] = []
    if source.confidence is not None and source.confidence < SOURCE_CONFIDENCE_ACTIVE_THRESHOLD:
        flags.append("SOURCE_CONFIDENCE_LOW")
    if source.price is not None and source.price.confidence is not None and source.price.confidence < SOURCE_CONFIDENCE_ACTIVE_THRESHOLD:
        flags.append("PRICE_CONFIDENCE_LOW")
    if not source.raw_html:
        flags.append("RAW_HTML_MISSING")
    return flags


def _skip(
    result: ProductFactoryHandoffImportResult,
    reason: str,
    warning: str,
    *,
    item: dict[str, Any] | None = None,
) -> None:
    result.counters["skipped_count"] += 1
    result.skipped_reasons[reason] += 1
    if reason == "invalid_url":
        result.counters["invalid_url_count"] += 1
    elif reason == "unresolved_identity":
        result.counters["unresolved_identity_count"] += 1
    elif reason == "ambiguous_identity":
        result.counters["ambiguous_identity_count"] += 1
    result.warnings.append(warning)
    if item is not None:
        result.report_items.append(item)


def _report_item(
    *,
    identity: HandoffIdentity,
    source: HandoffSource,
    action: str,
    reason: str | None,
    resolution: CatalogProductResolution,
    normalized_url: str | None = None,
    source_domain: str | None = None,
    source_url_id: int | None = None,
    product_source_id: int | None = None,
    snapshot_id: int | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    return {
        "url": source.url,
        "url_normalized": normalized_url,
        "source_name": source.source_name,
        "source_domain": source_domain,
        "catalog_source": identity.catalog_source,
        "catalog_product_id": resolution.product.id if resolution.product is not None else identity.catalog_product_id,
        "source_url_id": source_url_id,
        "product_source_id": product_source_id,
        "source_capture_snapshot_id": snapshot_id,
        "model": identity.model,
        "mpn": identity.mpn,
        "status": status,
        "action": action,
        "confidence": str(source.confidence) if source.confidence is not None else resolution.confidence,
        "identity_match_type": resolution.match_type,
        "evidence_source": "product_factory_handoff",
        "evidence_detail": str(source.evidence or {}),
        "reason": reason,
        "price": json_safe_value(source.price.price) if source.price is not None else None,
    }


def _source_stat(result: ProductFactoryHandoffImportResult, key: str, field_name: str) -> None:
    result.source_stats.setdefault(key, Counter())[field_name] += 1


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _nested(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _decimal_value(value: object) -> Decimal | None:
    text = _first_text(value)
    if not text:
        return None
    normalized = text.replace("EUR", "").replace("eur", "").replace("€", "").replace("β‚¬", "").replace(" ", "").strip()
    if "," in normalized and "." in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    else:
        normalized = normalized.replace(",", ".")
    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = _first_text(value)
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc, microsecond=0)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _optional_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _optional_text(value: object) -> str | None:
    text = _first_text(value)
    return text or None


def _empty_to_none(value: object) -> str | None:
    text = _first_text(value)
    return text or None


def _first_text(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
