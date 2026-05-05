"""Best-effort import of legacy Product-Agent scrape artifacts."""

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

from pricefetcher.catalog.source_catalog import DEFAULT_CATALOG_SOURCE
from pricefetcher.db.models import ProductSource, SourceCaptureSnapshot
from pricefetcher.db.product_source_repository import (
    create_or_reuse_product_source,
    find_or_create_product_from_model,
    persist_capture_result,
)
from pricefetcher.db.repositories import json_safe_value
from pricefetcher.source_capture.canonicalize_url import canonicalize_url
from pricefetcher.source_capture.detect_vendor import detect_vendor_slug
from pricefetcher.source_capture.sanitize import content_hash, sanitize_json
from pricefetcher.source_capture.types import CaptureResult, CaptureSnapshotPayload, ParsedPriceObservation


DEFAULT_PRODUCT_AGENT_WORK_ROOT = Path("..") / "Product-Agent" / "work"
PRODUCT_AGENT_ARTIFACT_IMPORT_VERSION = "product_agent_artifact_import_v1"
RELIABLE_PRICE_CONFIDENCE_THRESHOLD = 0.85


@dataclass(frozen=True)
class ProductAgentArtifactCandidate:
    model: str
    source_json_path: Path
    report_json_path: Path | None
    raw_html_path: Path | None
    source_payload: dict[str, Any]
    report_payload: dict[str, Any]
    source_json_text: str
    raw_html: str | None
    source_url: str
    canonical_url: str
    final_url: str
    vendor_slug: str
    capture_strategy: str
    fetch_status_code: int | None
    captured_at: datetime
    timestamp_source: str
    timestamp_quality: str
    price: Decimal | None
    price_reliable: bool
    price_flags: list[str]
    price_confidence: float | None
    data_quality_flags: list[str]


@dataclass
class ProductAgentArtifactImportResult:
    apply: bool
    artifact_root: str
    counters: Counter[str] = field(default_factory=Counter)
    warnings: list[str] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self, *, include_items: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "apply": self.apply,
            "artifact_root": self.artifact_root,
            "counters": {key: int(value) for key, value in sorted(self.counters.items())},
            "warnings": list(self.warnings),
        }
        if include_items:
            payload["items"] = list(self.items)
        return payload


def import_product_agent_artifacts(
    session: Session,
    *,
    artifact_root: Path | str = DEFAULT_PRODUCT_AGENT_WORK_ROOT,
    apply: bool = False,
    catalog_source: str = DEFAULT_CATALOG_SOURCE,
    limit: int | None = None,
) -> ProductAgentArtifactImportResult:
    root = Path(artifact_root).expanduser().resolve(strict=False)
    result = ProductAgentArtifactImportResult(apply=apply, artifact_root=str(root))
    if not root.exists() or not root.is_dir():
        result.warnings.append(f"Product-Agent artifact root not found: {root}")
        result.counters["missing_root_count"] += 1
        return result

    remaining = limit
    for candidate in _iter_artifact_candidates(root, result):
        if remaining is not None and remaining <= 0:
            break
        remaining = remaining - 1 if remaining is not None else None
        _process_candidate(session, candidate, result, catalog_source=catalog_source, apply=apply)
    return result


def _iter_artifact_candidates(
    root: Path,
    result: ProductAgentArtifactImportResult,
) -> Iterable[ProductAgentArtifactCandidate]:
    for source_json_path in sorted(root.glob("*/scrape/*.source.json")):
        result.counters["artifacts_discovered"] += 1
        try:
            candidate = _load_candidate(source_json_path)
        except ValueError as exc:
            result.counters["skipped_count"] += 1
            result.counters["parse_error_count"] += 1
            result.warnings.append(str(exc))
            result.items.append(
                {
                    "source_json_path": str(source_json_path),
                    "action": "skipped",
                    "reason": "parse_error",
                    "message": str(exc),
                }
            )
            continue
        if not candidate.source_url:
            result.counters["skipped_count"] += 1
            result.counters["missing_url_count"] += 1
            result.items.append(_candidate_item(candidate, action="skipped", reason="missing_url"))
            continue
        yield candidate


def _load_candidate(source_json_path: Path) -> ProductAgentArtifactCandidate:
    try:
        source_json_text = source_json_path.read_text(encoding="utf-8-sig")
        source_payload = json.loads(source_json_text)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read Product-Agent source artifact {source_json_path}: {exc}") from exc
    if not isinstance(source_payload, dict):
        raise ValueError(f"Product-Agent source artifact is not a JSON object: {source_json_path}")

    model = _model_from_path(source_json_path)
    report_path = source_json_path.with_name(f"{model}.report.json")
    report_payload = _read_optional_json(report_path)
    raw_html_path = _discover_raw_html_path(source_json_path, source_payload, model)
    raw_html = _read_optional_text(raw_html_path)

    source_url = _first_text(
        source_payload.get("canonical_url"),
        source_payload.get("url"),
        _nested(report_payload, ("source_resolution", "resolved_url")),
        _nested(report_payload, ("input", "url")),
    )
    canonical_url = canonicalize_url(source_url) if source_url else ""
    vendor_slug = _vendor_slug(source_payload, report_payload, canonical_url)
    timestamp, timestamp_source, timestamp_quality = _artifact_timestamp(source_payload, source_json_path, raw_html_path)
    price_recovery = _recover_price(source_payload, report_payload, vendor_slug)
    scope_ok = _scope_ok(report_payload)
    data_quality_flags = list(dict.fromkeys([*price_recovery["flags"], *(["URL_SCOPE_NOT_OK"] if not scope_ok else [])]))
    if raw_html is None:
        data_quality_flags.append("RAW_HTML_MISSING")
    capture_strategy = _capture_strategy(report_payload, vendor_slug)
    final_url = _first_text(_nested(report_payload, ("source_resolution", "resolved_url")), source_payload.get("canonical_url"), source_url)
    return ProductAgentArtifactCandidate(
        model=model,
        source_json_path=source_json_path,
        report_json_path=report_path if report_path.exists() else None,
        raw_html_path=raw_html_path if raw_html_path is not None and raw_html_path.exists() else None,
        source_payload=source_payload,
        report_payload=report_payload,
        source_json_text=source_json_text,
        raw_html=raw_html,
        source_url=source_url,
        canonical_url=canonical_url,
        final_url=final_url,
        vendor_slug=vendor_slug,
        capture_strategy=capture_strategy,
        fetch_status_code=_optional_int(_nested(report_payload, ("fetch", "status_code")) or source_payload.get("status_code")),
        captured_at=timestamp,
        timestamp_source=timestamp_source,
        timestamp_quality=timestamp_quality,
        price=price_recovery["price"],
        price_reliable=bool(price_recovery["reliable"]) and scope_ok,
        price_flags=data_quality_flags,
        price_confidence=price_recovery["confidence"],
        data_quality_flags=data_quality_flags,
    )


def _process_candidate(
    session: Session,
    candidate: ProductAgentArtifactCandidate,
    result: ProductAgentArtifactImportResult,
    *,
    catalog_source: str,
    apply: bool,
) -> None:
    if not apply:
        result.counters["would_import_snapshot_count"] += 1
        if candidate.price_reliable:
            result.counters["would_import_price_observation_count"] += 1
        elif candidate.price is not None:
            result.counters["unreliable_price_count"] += 1
        result.items.append(_candidate_item(candidate, action="would_import", reason=None))
        return

    try:
        product = find_or_create_product_from_model(
            session,
            model=candidate.model,
            catalog_source=catalog_source,
            enrichment=_product_enrichment(candidate.source_payload),
        )
        source, created = create_or_reuse_product_source(
            session,
            product=product,
            source_url=candidate.source_url,
            confidence_score=Decimal("0.95") if "URL_SCOPE_NOT_OK" not in candidate.data_quality_flags else Decimal("0.70"),
        )
    except ValueError as exc:
        result.counters["skipped_count"] += 1
        result.counters["invalid_url_count"] += 1
        result.warnings.append(f"{candidate.source_json_path}: {exc}")
        result.items.append(_candidate_item(candidate, action="skipped", reason="invalid_url"))
        return

    artifact_ref = _artifact_ref(candidate)
    digest = content_hash(candidate.raw_html or candidate.source_json_text)
    if _snapshot_already_imported(session, source=source, artifact_ref=artifact_ref, digest=digest):
        result.counters["duplicate_snapshot_count"] += 1
        result.items.append(_candidate_item(candidate, action="duplicate", reason="snapshot_already_imported", source_id=source.id))
        return

    capture_result = _candidate_to_capture_result(candidate, artifact_ref=artifact_ref, digest=digest)
    snapshot = persist_capture_result(session, product=product, source=source, result=capture_result)
    result.counters["imported_snapshot_count"] += 1
    result.counters["source_created_count" if created else "source_reused_count"] += 1
    if candidate.raw_html_path is not None:
        result.counters["raw_html_found_count"] += 1
    if candidate.price_reliable:
        result.counters["price_observation_count"] += 1
    elif candidate.price is not None:
        result.counters["unreliable_price_count"] += 1
    result.items.append(_candidate_item(candidate, action="imported", reason=None, source_id=source.id, snapshot_id=snapshot.id))


def _candidate_to_capture_result(
    candidate: ProductAgentArtifactCandidate,
    *,
    artifact_ref: str,
    digest: str | None,
) -> CaptureResult:
    observations: tuple[ParsedPriceObservation, ...] = ()
    if candidate.price_reliable and candidate.price is not None:
        observations = (
            ParsedPriceObservation(
                price=candidate.price,
                currency="EUR",
                availability=_first_text(candidate.source_payload.get("delivery_text"), candidate.source_payload.get("pickup_text")),
                stock_status=_first_text(candidate.source_payload.get("delivery_text"), candidate.source_payload.get("pickup_text")),
                delivery_text=_first_text(candidate.source_payload.get("delivery_text")),
                product_name=_first_text(candidate.source_payload.get("name")),
                raw_observation={
                    "source": "product_agent_artifact",
                    "price_text": _first_text(candidate.source_payload.get("price_text")),
                    "price_confidence": candidate.price_confidence,
                    "source_json_path": str(candidate.source_json_path),
                },
                timestamp_source=candidate.timestamp_source,
                timestamp_quality=candidate.timestamp_quality,
            ),
        )
    payload = CaptureSnapshotPayload(
        capture_strategy=candidate.capture_strategy,
        page_url=candidate.source_url,
        final_url=candidate.final_url,
        response_status=candidate.fetch_status_code,
        response_content_type="text/html; charset=utf-8" if candidate.raw_html is not None else "application/json",
        response_body_json={
            "source": sanitize_json(candidate.source_payload),
            "report": sanitize_json(_compact_report(candidate.report_payload)),
            "importer": {
                "name": "product_agent_artifact_import",
                "version": PRODUCT_AGENT_ARTIFACT_IMPORT_VERSION,
                "source_json_path": str(candidate.source_json_path),
                "report_json_path": str(candidate.report_json_path) if candidate.report_json_path is not None else "",
                "raw_html_path": str(candidate.raw_html_path) if candidate.raw_html_path is not None else "",
                "timestamp_source": candidate.timestamp_source,
                "timestamp_quality": candidate.timestamp_quality,
                "price_reliable": candidate.price_reliable,
                "price_confidence": candidate.price_confidence,
            },
        },
        raw_html=candidate.raw_html,
        artifact_ref=artifact_ref,
        content_hash=digest,
        parser_version=PRODUCT_AGENT_ARTIFACT_IMPORT_VERSION,
        fetch_status_code=candidate.fetch_status_code,
        data_quality_flags=list(dict.fromkeys(candidate.data_quality_flags)),
        captured_at=candidate.captured_at,
        fetched_at=candidate.captured_at,
        parsed_at=candidate.captured_at,
        imported_at=datetime.now(timezone.utc).replace(microsecond=0),
    )
    return CaptureResult(
        vendor_slug=candidate.vendor_slug or "unknown",
        status="success",
        snapshot=payload,
        price_observations=observations,
    )


def _snapshot_already_imported(
    session: Session,
    *,
    source: ProductSource,
    artifact_ref: str,
    digest: str | None,
) -> bool:
    statement = select(SourceCaptureSnapshot.id).where(
        SourceCaptureSnapshot.product_source_id == source.id,
        SourceCaptureSnapshot.capture_strategy.like("product_agent_artifact%"),
        SourceCaptureSnapshot.artifact_ref == artifact_ref,
    )
    if digest:
        statement = statement.where(SourceCaptureSnapshot.content_hash == digest)
    return session.execute(statement.limit(1)).scalar_one_or_none() is not None


def _recover_price(source_payload: dict[str, Any], report_payload: dict[str, Any], vendor_slug: str) -> dict[str, Any]:
    flags: list[str] = []
    price = _decimal_value(source_payload.get("price_value")) or _decimal_value(source_payload.get("price_text"))
    if price is None or price <= 0:
        return {"price": None, "reliable": False, "confidence": None, "flags": ["PRICE_MISSING"]}

    diagnostics = _nested(report_payload, ("field_diagnostics", "price"))
    confidence = _optional_float(diagnostics.get("confidence") if isinstance(diagnostics, dict) else None)
    value_present = diagnostics.get("value_present") if isinstance(diagnostics, dict) else None
    selected_strategy = _first_text(diagnostics.get("selected_strategy") if isinstance(diagnostics, dict) else None)
    critical_extractor = _first_text(_nested(report_payload, ("critical_extractors", "price")))
    missing_fields = {_normalize_text(item) for item in _list_value(report_payload.get("missing_fields"))}
    critical_missing = {_normalize_text(item) for item in _list_value(report_payload.get("critical_missing"))}
    page_type = _normalize_text(source_payload.get("page_type"))
    has_price_text = "€" in _first_text(source_payload.get("price_text")).lower() or "eur" in _first_text(source_payload.get("price_text")).lower()

    if "price" in missing_fields or "price" in critical_missing:
        flags.append("PRICE_MARKED_MISSING")
    if page_type and page_type != "product":
        flags.append("NON_PRODUCT_PAGE")
    if value_present is False:
        flags.append("PRICE_DIAGNOSTIC_VALUE_MISSING")
    if confidence is not None and confidence < RELIABLE_PRICE_CONFIDENCE_THRESHOLD:
        flags.append("PRICE_CONFIDENCE_LOW")
    if confidence is None and not critical_extractor:
        flags.append("PRICE_CONFIDENCE_UNKNOWN")
    if not has_price_text:
        flags.append("PRICE_TEXT_MISSING")
    if not vendor_slug or vendor_slug == "unknown":
        flags.append("UNKNOWN_VENDOR")

    reliable = not flags and (
        (confidence is not None and confidence >= RELIABLE_PRICE_CONFIDENCE_THRESHOLD)
        or (critical_extractor not in {"", "missing"} and bool(selected_strategy))
    )
    if not reliable:
        flags.append("PRICE_UNRELIABLE")
    return {"price": price, "reliable": reliable, "confidence": confidence, "flags": list(dict.fromkeys(flags))}


def _artifact_timestamp(
    source_payload: dict[str, Any],
    source_json_path: Path,
    raw_html_path: Path | None,
) -> tuple[datetime, str, str]:
    scraped_at = _parse_datetime(source_payload.get("scraped_at"))
    if scraped_at is not None:
        return scraped_at, "product_agent.source.scraped_at", "exact"
    for path in (raw_html_path, source_json_path):
        if path is None or not path.exists():
            continue
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0), "artifact_mtime", "derived"
    return datetime.now(timezone.utc).replace(microsecond=0), "import_time", "fallback"


def _discover_raw_html_path(source_json_path: Path, source_payload: dict[str, Any], model: str) -> Path | None:
    declared = _first_text(source_payload.get("raw_html_path"))
    if declared:
        declared_path = Path(declared).expanduser()
        if declared_path.exists() and declared_path.is_file():
            return declared_path
    sibling = source_json_path.with_name(f"{model}.raw.html")
    if sibling.exists() and sibling.is_file():
        return sibling
    return sibling


def _candidate_item(
    candidate: ProductAgentArtifactCandidate,
    *,
    action: str,
    reason: str | None,
    source_id: int | None = None,
    snapshot_id: int | None = None,
) -> dict[str, Any]:
    return {
        "model": candidate.model,
        "source_json_path": str(candidate.source_json_path),
        "raw_html_path": str(candidate.raw_html_path) if candidate.raw_html_path is not None else "",
        "source_url": candidate.source_url,
        "canonical_url": candidate.canonical_url,
        "vendor": candidate.vendor_slug,
        "action": action,
        "reason": reason,
        "product_source_id": source_id,
        "source_capture_snapshot_id": snapshot_id,
        "price": json_safe_value(candidate.price),
        "price_reliable": candidate.price_reliable,
        "price_confidence": candidate.price_confidence,
        "timestamp_source": candidate.timestamp_source,
        "timestamp_quality": candidate.timestamp_quality,
        "data_quality_flags": list(candidate.data_quality_flags),
    }


def _artifact_ref(candidate: ProductAgentArtifactCandidate) -> str:
    payload = {
        "source_json": str(candidate.source_json_path),
        "report_json": str(candidate.report_json_path) if candidate.report_json_path is not None else "",
        "raw_html": str(candidate.raw_html_path) if candidate.raw_html_path is not None else "",
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _compact_report(report_payload: dict[str, Any]) -> dict[str, Any]:
    if not report_payload:
        return {}
    return {
        "input": report_payload.get("input"),
        "source": report_payload.get("source"),
        "fetch_mode": report_payload.get("fetch_mode"),
        "source_resolution": report_payload.get("source_resolution"),
        "identity_checks": report_payload.get("identity_checks"),
        "url_scope_validation": report_payload.get("url_scope_validation"),
        "critical_extractors": report_payload.get("critical_extractors"),
        "price_diagnostics": _nested(report_payload, ("field_diagnostics", "price")),
        "missing_fields": report_payload.get("missing_fields"),
        "critical_missing": report_payload.get("critical_missing"),
        "warnings": report_payload.get("warnings"),
    }


def _product_enrichment(source_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": source_payload.get("name"),
        "brand": source_payload.get("brand"),
        "manufacturer": source_payload.get("brand"),
    }


def _capture_strategy(report_payload: dict[str, Any], vendor_slug: str) -> str:
    fetch_mode = _normalize_text(report_payload.get("fetch_mode")) or "artifact"
    vendor = _normalize_text(vendor_slug) or "unknown"
    return f"product_agent_artifact_{vendor}_{fetch_mode}"


def _vendor_slug(source_payload: dict[str, Any], report_payload: dict[str, Any], canonical_url: str) -> str:
    declared = _normalize_text(source_payload.get("source_name")) or _normalize_text(report_payload.get("source"))
    detected = detect_vendor_slug(canonical_url) or ""
    return detected or declared or "unknown"


def _scope_ok(report_payload: dict[str, Any]) -> bool:
    scope_payload = _nested(report_payload, ("url_scope_validation",))
    if not isinstance(scope_payload, dict):
        return True
    ok = scope_payload.get("ok")
    return True if ok is None else bool(ok)


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_optional_text(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _model_from_path(path: Path) -> str:
    name = path.name
    suffix = ".source.json"
    if name.endswith(suffix):
        return name[: -len(suffix)]
    return path.stem


def _parse_datetime(value: object) -> datetime | None:
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


def _decimal_value(value: object) -> Decimal | None:
    text = _first_text(value)
    if not text:
        return None
    normalized = text.replace("€", "").replace("EUR", "").replace("eur", "").replace(" ", "").strip()
    if "," in normalized and "." in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    else:
        normalized = normalized.replace(",", ".")
    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _nested(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _list_value(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_text(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _normalize_text(value: object) -> str:
    return _first_text(value).casefold()
