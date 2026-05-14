"""Source capture snapshot and observation persistence."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from ecommerce.db.models.products import Product, ProductSource, SourceCaptureSnapshot
from ecommerce.db.repositories.observation_persistence import (
    add_price_observation_listings,
    offer_observation_row,
    price_observation_from_offer,
    price_observation_row,
    rank_parsed_offer_observations,
)
from ecommerce.db.repositories.source_convergence import sync_product_source_to_source_url
from ecommerce.db.repositories.source_health import update_source_health
from ecommerce.source_capture.sanitize import content_hash, sanitize_json
from ecommerce.source_capture.types import CaptureResult


def persist_capture_result(
    session: Session,
    *,
    product: Product,
    source: ProductSource,
    result: CaptureResult,
    run_id: str | None = None,
    observation_batch_id: str | None = None,
    monitoring_run_id: int | None = None,
) -> SourceCaptureSnapshot:
    vendor_id = source.vendor_id
    now = _now()
    payload = result.snapshot
    response_text_hash = content_hash(payload.response_body_text or payload.raw_html)
    snapshot = SourceCaptureSnapshot(
        product_id=product.id,
        product_source_id=source.id,
        vendor_id=vendor_id,
        capture_strategy=payload.capture_strategy,
        page_url=payload.page_url,
        final_url=payload.final_url,
        request_url=payload.request_url,
        request_method=payload.request_method,
        response_status=payload.response_status,
        response_content_type=payload.response_content_type,
        response_body_json=sanitize_json(payload.response_body_json) if payload.response_body_json is not None else None,
        response_body_text_ref=_inline_text_ref(payload.response_body_text, kind="response_body_text"),
        raw_html_ref=_inline_text_ref(payload.raw_html, kind="raw_html"),
        artifact_ref=payload.artifact_ref,
        content_hash=payload.content_hash or response_text_hash,
        parser_version=payload.parser_version,
        capture_version=payload.capture_version,
        playwright_version=payload.playwright_version,
        fetch_status_code=payload.fetch_status_code,
        fetch_latency_ms=payload.fetch_latency_ms,
        candidate_score=payload.candidate_score,
        candidate_reason=payload.candidate_reason,
        network_event_type=payload.network_event_type,
        trigger_action=payload.trigger_action,
        data_quality_flags=payload.data_quality_flags,
        error_code=payload.error_code or result.error_code,
        error_message=payload.error_message or result.error_message,
        captured_at=payload.captured_at,
        fetched_at=payload.fetched_at,
        parsed_at=payload.parsed_at,
        imported_at=payload.imported_at,
        created_at=now,
    )
    session.add(snapshot)
    session.flush()
    price_observations = tuple(result.price_observations)
    if not price_observations:
        primary_offer = next(iter(rank_parsed_offer_observations(tuple(result.offer_observations))), None)
        if primary_offer is not None:
            price_observations = (price_observation_from_offer(primary_offer),)

    price_rows = []
    for observation in price_observations:
        row = price_observation_row(
            product,
            source,
            snapshot,
            vendor_id,
            result.vendor_slug,
            observation,
            now,
            run_id=run_id,
            observation_batch_id=observation_batch_id,
            monitoring_run_id=monitoring_run_id,
        )
        session.add(row)
        price_rows.append(row)
    if price_rows:
        session.flush()

    for observation in result.offer_observations:
        session.add(offer_observation_row(product, source, snapshot, vendor_id, observation, now, observation_batch_id=observation_batch_id))
    if price_rows:
        add_price_observation_listings(
            session,
            price_rows[0],
            product=product,
            source=source,
            snapshot=snapshot,
            vendor_id=vendor_id,
            vendor_slug=result.vendor_slug,
            offers=tuple(result.offer_observations),
            now=now,
            observation_batch_id=observation_batch_id,
        )
    update_source_health(source, result, snapshot)
    session.flush()
    sync_product_source_to_source_url(session, source)
    return snapshot


def _inline_text_ref(text: str | None, *, kind: str, limit: int = 100_000) -> str | None:
    if not text:
        return None
    del limit
    sanitized = _sanitize_text_content(text)
    digest = content_hash(sanitized)
    if digest is None:
        return None
    artifact_dir = Path(os.environ.get("ECOMMERCE_SOURCE_CAPTURE_ARTIFACT_DIR", "output/source_capture/artifacts"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".html" if kind == "raw_html" else ".txt"
    artifact_path = artifact_dir / f"{kind}_{digest}{suffix}"
    if not artifact_path.exists():
        artifact_path.write_text(sanitized, encoding="utf-8")
    return str(artifact_path)


def _sanitize_text_content(text: str) -> str:
    sensitive_markers = ("authorization", "cookie", "set-cookie", "csrf", "token", "session", "password")
    clean_lines: list[str] = []
    for line in str(text).splitlines():
        lowered = line.lower()
        if any(marker in lowered for marker in sensitive_markers):
            continue
        clean_lines.append(line)
    return "\n".join(clean_lines)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
