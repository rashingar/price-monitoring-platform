"""Persistence and API-facing orchestration for Skroutz network diagnostics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecommerce.db.models.source_urls import SourceUrl
from ecommerce.db.models.vendor_sources import Vendor
from ecommerce.db.models.products import Product, ProductSource, SourceCaptureSnapshot
from ecommerce.db.repositories.source_convergence import (
    sync_source_url_to_product_source,
)
from ecommerce.db.repositories.source_urls import get_source_url
from ecommerce.source_capture.canonicalize_url import (
    canonical_url_hash,
    canonicalize_url,
)
from ecommerce.source_capture.detect_vendor import detect_vendor_slug
from ecommerce.source_capture.sanitize import content_hash
from ecommerce.source_capture.skroutz_network_diagnostic import (
    BLOCKED_OR_CHALLENGE,
    CAPTURE_STRATEGY,
    PlaywrightUnavailableError,
    SkroutzNetworkDiagnosticReport,
    derived_skroutz_endpoint_urls,
    run_skroutz_network_diagnostic,
)

SKROUTZ_NETWORK_DIAGNOSTICS_DIR = (
    Path("output") / "vendor_sources" / "diagnostics" / "skroutz-network"
)

DiagnosticRunner = Callable[..., SkroutzNetworkDiagnosticReport]


@dataclass(frozen=True)
class PersistedSkroutzDiagnostic:
    source_url_id: int
    vendor_slug: str
    source_url: str
    report: dict[str, Any]
    diagnostic_report_id: int | None
    artifact_path: str | None

    def summary_response(self) -> dict[str, Any]:
        return _summary_payload(
            source_url_id=self.source_url_id,
            vendor_slug=self.vendor_slug,
            source_url=self.source_url,
            report=self.report,
            diagnostic_report_id=self.diagnostic_report_id,
            artifact_path=self.artifact_path,
        )

    def detail_response(self) -> dict[str, Any]:
        summary = self.summary_response()
        report = dict(self.report)
        report["source_url_id"] = self.source_url_id
        report["vendor_slug"] = self.vendor_slug
        report["diagnostic_report_id"] = self.diagnostic_report_id
        report["artifact_path"] = self.artifact_path
        report["summary"] = summary
        return report


def run_and_persist_skroutz_network_diagnostic(
    session: Session,
    *,
    source_url_id: int,
    headed: bool = False,
    timeout_seconds: int = 60,
    runner: DiagnosticRunner | None = None,
    artifact_root: Path = SKROUTZ_NETWORK_DIAGNOSTICS_DIR,
) -> PersistedSkroutzDiagnostic:
    source_url = _get_skroutz_source_url(session, source_url_id)
    product_source = sync_source_url_to_product_source(session, source_url)
    if product_source is None:
        raise ValueError(
            "Skroutz source URL must be active before a browser diagnostic can be run."
        )
    product = session.get(Product, product_source.product_id)
    vendor = (
        session.get(Vendor, product_source.vendor_id)
        if product_source.vendor_id is not None
        else None
    )
    active_runner = runner or run_skroutz_network_diagnostic
    safe_timeout = max(5, min(int(timeout_seconds), 180))
    diagnostic_url = source_url.url_normalized or source_url.url
    try:
        report = active_runner(
            diagnostic_url,
            headed=bool(headed),
            timeout_seconds=safe_timeout,
        )
        report_payload = _report_payload_with_comparison(report.to_dict())
    except PlaywrightUnavailableError:
        raise
    except Exception as exc:
        report_payload = failed_skroutz_network_report(
            diagnostic_url,
            error_code="browser_diagnostic_failed",
            error_message=str(exc).strip() or exc.__class__.__name__,
            timeout_seconds=safe_timeout,
            headed=bool(headed),
        )
    artifact_path = _write_report_artifact(artifact_root, source_url_id, report_payload)
    snapshot = _persist_report_snapshot(
        session,
        source_url=source_url,
        product_source=product_source,
        product=product,
        vendor=vendor,
        report_payload=report_payload,
        artifact_path=artifact_path,
    )
    return PersistedSkroutzDiagnostic(
        source_url_id=int(source_url.id),
        vendor_slug="skroutz",
        source_url=source_url.url,
        report=report_payload,
        diagnostic_report_id=int(snapshot.id) if snapshot.id is not None else None,
        artifact_path=str(artifact_path),
    )


def latest_skroutz_network_diagnostic(
    session: Session,
    *,
    source_url_id: int,
) -> PersistedSkroutzDiagnostic | None:
    source_url = _get_skroutz_source_url(session, source_url_id)
    product_source = _find_product_source_for_source_url(session, source_url)
    if product_source is None:
        return None
    statement = (
        select(SourceCaptureSnapshot)
        .where(
            SourceCaptureSnapshot.product_source_id == product_source.id,
            SourceCaptureSnapshot.capture_strategy == CAPTURE_STRATEGY,
        )
        .order_by(
            SourceCaptureSnapshot.created_at.desc(), SourceCaptureSnapshot.id.desc()
        )
        .limit(1)
    )
    snapshot = session.execute(statement).scalar_one_or_none()
    if snapshot is None:
        return None
    report = snapshot.response_body_json or {}
    if not isinstance(report, dict):
        report = {}
    return PersistedSkroutzDiagnostic(
        source_url_id=int(source_url.id),
        vendor_slug="skroutz",
        source_url=source_url.url,
        report=_report_payload_with_comparison(report),
        diagnostic_report_id=int(snapshot.id) if snapshot.id is not None else None,
        artifact_path=snapshot.artifact_ref,
    )


def failed_skroutz_network_report(
    source_url: str,
    *,
    error_code: str,
    error_message: str,
    timeout_seconds: int,
    headed: bool,
) -> dict[str, Any]:
    now = _now().isoformat()
    return _report_payload_with_comparison(
        {
            "source_url": source_url,
            "status": "failed",
            "started_at": now,
            "completed_at": now,
            "timeout_seconds": timeout_seconds,
            "headed": headed,
            "derived_endpoints": derived_skroutz_endpoint_urls(source_url),
            "captured_responses": [],
            "observed_filter_products_url": False,
            "observed_shops_details_url": False,
            "exact_match_count": 0,
            "product_data_candidate_url": None,
            "product_data_candidate_reason": None,
            "classifications_summary": {},
            "error_code": error_code,
            "error_message": error_message,
        }
    )


def _get_skroutz_source_url(session: Session, source_url_id: int) -> SourceUrl:
    source_url = get_source_url(session, int(source_url_id))
    if source_url is None:
        raise LookupError("Source URL not found.")
    vendor_slug = (source_url.source_name or "").strip().lower() or (
        detect_vendor_slug(source_url.url_normalized or source_url.url) or ""
    )
    if vendor_slug != "skroutz":
        raise ValueError(
            "Skroutz browser network diagnostics are only available for Skroutz source URLs."
        )
    return source_url


def _find_product_source_for_source_url(
    session: Session, source_url: SourceUrl
) -> ProductSource | None:
    canonical = canonicalize_url(source_url.url_normalized or source_url.url)
    digest = canonical_url_hash(canonical)
    statement = (
        select(ProductSource)
        .join(Product, Product.id == ProductSource.product_id)
        .where(
            Product.catalog_source == source_url.catalog_source,
            Product.model == source_url.model,
            ProductSource.canonical_url_hash == digest,
        )
        .limit(1)
    )
    return session.execute(statement).scalar_one_or_none()


def _persist_report_snapshot(
    session: Session,
    *,
    source_url: SourceUrl,
    product_source: ProductSource,
    product: Product | None,
    vendor: Vendor | None,
    report_payload: dict[str, Any],
    artifact_path: Path,
) -> SourceCaptureSnapshot:
    now = _now()
    captured_responses = report_payload.get("captured_responses")
    first_response = (
        captured_responses[0]
        if isinstance(captured_responses, list) and captured_responses
        else {}
    )
    snapshot = SourceCaptureSnapshot(
        product_id=product.id if product is not None else None,
        product_source_id=product_source.id,
        vendor_id=vendor.id if vendor is not None else product_source.vendor_id,
        capture_strategy=CAPTURE_STRATEGY,
        page_url=source_url.url,
        final_url=(
            report_payload.get("source_url")
            if isinstance(report_payload.get("source_url"), str)
            else source_url.url
        ),
        request_url=(
            first_response.get("url") if isinstance(first_response, dict) else None
        ),
        request_method=(
            first_response.get("method") if isinstance(first_response, dict) else None
        ),
        response_status=(
            first_response.get("status") if isinstance(first_response, dict) else None
        ),
        response_content_type=(
            first_response.get("content_type")
            if isinstance(first_response, dict)
            else None
        ),
        response_body_json=report_payload,
        artifact_ref=str(artifact_path),
        content_hash=content_hash(
            json.dumps(report_payload, sort_keys=True, ensure_ascii=False)
        ),
        parser_version="skroutz_network_diagnostic_v1",
        capture_version="source-capture-diagnostic-v1",
        candidate_reason=report_payload.get("product_data_candidate_reason"),
        network_event_type="browser_response_summary",
        trigger_action="operator_skroutz_network_diagnostic",
        data_quality_flags=_data_quality_flags(report_payload),
        error_code=report_payload.get("error_code"),
        error_message=report_payload.get("error_message"),
        captured_at=now,
        fetched_at=now,
        parsed_at=now,
        created_at=now,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def _write_report_artifact(
    root: Path, source_url_id: int, payload: dict[str, Any]
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = Path(root) / str(source_url_id) / f"{timestamp}-skroutz-network.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def _report_payload_with_comparison(report: dict[str, Any]) -> dict[str, Any]:
    derived = (
        report.get("derived_endpoints")
        if isinstance(report.get("derived_endpoints"), dict)
        else {}
    )
    payload = dict(report)
    payload["derived_filter_products_url"] = derived.get("filter_products")
    payload["derived_shops_details_url"] = derived.get("shops_details")
    payload["observed_filter_products_url"] = bool(
        payload.get("observed_filter_products_url")
    )
    payload["observed_shops_details_url"] = bool(
        payload.get("observed_shops_details_url")
    )
    payload["exact_match_count"] = int(payload.get("exact_match_count") or 0)
    payload["product_data_candidate_url"] = payload.get("product_data_candidate_url")
    payload["product_data_candidate_reason"] = payload.get(
        "product_data_candidate_reason"
    )
    return payload


def _summary_payload(
    *,
    source_url_id: int,
    vendor_slug: str,
    source_url: str,
    report: dict[str, Any],
    diagnostic_report_id: int | None,
    artifact_path: str | None,
) -> dict[str, Any]:
    captured = report.get("captured_responses")
    classifications_summary = (
        report.get("classifications_summary")
        if isinstance(report.get("classifications_summary"), dict)
        else {}
    )
    observed = {
        "filter_products": bool(report.get("observed_filter_products_url")),
        "shops_details": bool(report.get("observed_shops_details_url")),
    }
    return {
        "source_url_id": source_url_id,
        "vendor_slug": vendor_slug,
        "source_url": source_url,
        "status": report.get("status") or "unknown",
        "captured_response_count": len(captured) if isinstance(captured, list) else 0,
        "derived_endpoints": report.get("derived_endpoints") or {},
        "derived_filter_products_url": report.get("derived_filter_products_url"),
        "derived_shops_details_url": report.get("derived_shops_details_url"),
        "observed_derived_endpoints": observed,
        "observed_filter_products_url": observed["filter_products"],
        "observed_shops_details_url": observed["shops_details"],
        "exact_match_count": int(report.get("exact_match_count") or 0),
        "best_product_data_endpoint": report.get("product_data_candidate_url"),
        "product_data_candidate_url": report.get("product_data_candidate_url"),
        "product_data_candidate_reason": report.get("product_data_candidate_reason"),
        "classifications_summary": classifications_summary,
        "blocked_or_challenge_detected": int(
            classifications_summary.get(BLOCKED_OR_CHALLENGE, 0) or 0
        )
        > 0,
        "diagnostic_report_id": diagnostic_report_id,
        "artifact_path": artifact_path,
        "error_code": report.get("error_code"),
        "error_message": report.get("error_message"),
        "created_at": report.get("completed_at") or report.get("started_at"),
    }


def _data_quality_flags(report_payload: dict[str, Any]) -> list[str]:
    flags = ["diagnostic_only"]
    if report_payload.get("observed_filter_products_url"):
        flags.append("observed_filter_products")
    if report_payload.get("observed_shops_details_url"):
        flags.append("observed_shops_details")
    summary = report_payload.get("classifications_summary")
    if isinstance(summary, dict) and int(summary.get(BLOCKED_OR_CHALLENGE, 0) or 0) > 0:
        flags.append("blocked_or_challenge_detected")
    if not report_payload.get("product_data_candidate_url"):
        flags.append("no_product_data_candidate")
    return flags


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
