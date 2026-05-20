"""Import existing product URLs into DB-backed source URLs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ecommerce.catalog.source_catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.models.catalog import CatalogProductRow
from ecommerce.db.models.products import Product
from ecommerce.db.models.price_monitoring import MonitoringRun, PriceObservation
from ecommerce.db.repositories.common import json_safe_value
from ecommerce.db.repositories.source_urls import (
    create_or_update_imported_source_url,
    source_url_to_dict,
)
from ecommerce.price_monitoring.observations import (
    ParsedPriceObservation,
    parse_price_observations_csv,
)
from ecommerce.source_urls import (
    SourceUrlValidationError,
    extract_source_domain,
    infer_source_name,
    normalize_source_url,
)


@dataclass(frozen=True)
class CatalogProductResolution:
    product: CatalogProductRow | None
    match_type: str
    confidence: str
    warning: str | None = None


@dataclass(frozen=True)
class SourceUrlImportCandidate:
    url: str
    source_name: str | None
    catalog_source: str
    model: str | None
    mpn: str | None
    catalog_product_id: int
    status: str
    url_type: str
    trust_level: str
    evidence_source: str
    evidence_detail: str
    confidence: str
    observed_at: datetime | None
    notes: str
    successful_evidence: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "source_name": self.source_name,
            "catalog_source": self.catalog_source,
            "model": self.model,
            "mpn": self.mpn,
            "catalog_product_id": self.catalog_product_id,
            "status": self.status,
            "url_type": self.url_type,
            "trust_level": self.trust_level,
            "evidence_source": self.evidence_source,
            "evidence_detail": self.evidence_detail,
            "confidence": self.confidence,
            "observed_at": json_safe_value(self.observed_at),
            "notes": self.notes,
            "successful_evidence": self.successful_evidence,
        }


@dataclass
class SourceUrlImportResult:
    apply: bool
    counters: Counter[str] = field(default_factory=Counter)
    sources_processed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped_reasons: Counter[str] = field(default_factory=Counter)
    candidate_evidence: list[dict[str, Any]] = field(default_factory=list)
    changed_source_urls: list[dict[str, Any]] = field(default_factory=list)
    report_items: list[dict[str, Any]] = field(default_factory=list)
    source_stats: dict[str, Counter[str]] = field(default_factory=dict)

    def to_dict(self, *, include_candidates: bool = True) -> dict[str, Any]:
        summary = {key: int(self.counters.get(key, 0)) for key in SUMMARY_COUNTERS}
        payload: dict[str, Any] = {
            **summary,
            "apply": self.apply,
            "sources_processed": list(self.sources_processed),
            "warnings": list(self.warnings),
            "skipped_reasons": dict(self.skipped_reasons),
            "changed_source_urls": list(self.changed_source_urls),
            "source_stats": {
                key: dict(value) for key, value in self.source_stats.items()
            },
        }
        if include_candidates:
            payload["candidate_evidence"] = list(self.candidate_evidence)
            payload["report_items"] = list(self.report_items)
        return payload


SUMMARY_COUNTERS = (
    "candidates_found",
    "imported_count",
    "updated_count",
    "skipped_count",
    "active_count",
    "needs_review_count",
    "invalid_url_count",
    "duplicate_count",
    "unresolved_identity_count",
    "ambiguous_identity_count",
)


def import_source_urls(
    session: Session,
    *,
    apply: bool = False,
    catalog_source: str | None = None,
    include_observations: bool = True,
    include_artifacts: bool = True,
    limit: int | None = None,
) -> SourceUrlImportResult:
    result = SourceUrlImportResult(apply=apply)
    seen_keys: set[tuple[int, str]] = set()
    remaining = limit

    for candidate in _iter_candidates(
        session,
        catalog_source=catalog_source,
        include_observations=include_observations,
        include_artifacts=include_artifacts,
        result=result,
    ):
        if remaining is not None and remaining <= 0:
            break
        remaining = remaining - 1 if remaining is not None else None
        _process_candidate(session, candidate, result, seen_keys, apply=apply)

    return result


def resolve_catalog_product_for_import(
    session: Session,
    *,
    catalog_source: str,
    model: str | None,
    mpn: str | None,
    product_id: int | None = None,
) -> CatalogProductResolution:
    observation_product = (
        session.get(Product, product_id) if product_id is not None else None
    )
    resolved_catalog_source = (
        _text(catalog_source)
        or _text(getattr(observation_product, "catalog_source", None))
        or DEFAULT_CATALOG_SOURCE
    )
    resolved_model = _empty_to_none(model) or _empty_to_none(
        getattr(observation_product, "model", None)
    )
    resolved_mpn = _empty_to_none(mpn) or _empty_to_none(
        getattr(observation_product, "mpn", None)
    )

    if resolved_model and not _looks_composite_model(resolved_model):
        product = session.execute(
            select(CatalogProductRow).where(
                CatalogProductRow.catalog_source == resolved_catalog_source,
                CatalogProductRow.model == resolved_model,
                CatalogProductRow.active.is_(True),
            )
        ).scalar_one_or_none()
        if product is not None:
            return CatalogProductResolution(
                product=product, match_type="model", confidence="strong"
            )

    if resolved_mpn:
        matches = list(
            session.execute(
                select(CatalogProductRow)
                .where(
                    CatalogProductRow.catalog_source == resolved_catalog_source,
                    CatalogProductRow.mpn == resolved_mpn,
                    CatalogProductRow.active.is_(True),
                )
                .limit(2)
            )
            .scalars()
            .all()
        )
        if len(matches) == 1:
            return CatalogProductResolution(
                product=matches[0], match_type="mpn", confidence="strong"
            )
        if len(matches) > 1:
            return CatalogProductResolution(
                product=None,
                match_type="ambiguous_mpn",
                confidence="none",
                warning="multiple active catalog products matched MPN",
            )

    if not resolved_model and not resolved_mpn:
        return CatalogProductResolution(
            product=None,
            match_type="missing_identity",
            confidence="none",
            warning="missing model and MPN",
        )
    return CatalogProductResolution(
        product=None,
        match_type="unresolved",
        confidence="none",
        warning="no active catalog product matched",
    )


def _iter_candidates(
    session: Session,
    *,
    catalog_source: str | None,
    include_observations: bool,
    include_artifacts: bool,
    result: SourceUrlImportResult,
) -> Iterable[SourceUrlImportCandidate]:
    if include_observations:
        result.sources_processed.append("price_observations")
        yield from _iter_observation_candidates(
            session, catalog_source=catalog_source, result=result
        )
    if include_artifacts:
        result.sources_processed.append("monitoring_runs.enriched_csv_path")
        yield from _iter_artifact_candidates(
            session, catalog_source=catalog_source, result=result
        )


def _iter_observation_candidates(
    session: Session,
    *,
    catalog_source: str | None,
    result: SourceUrlImportResult,
) -> Iterable[SourceUrlImportCandidate]:
    statement = select(PriceObservation).where(
        PriceObservation.product_url.is_not(None),
        func.trim(PriceObservation.product_url) != "",
    )
    if catalog_source:
        statement = statement.where(PriceObservation.catalog_source == catalog_source)
    statement = statement.order_by(
        PriceObservation.observed_at.desc(), PriceObservation.id.desc()
    )

    for observation in session.execute(statement).scalars().all():
        _increment_source_stat(result, "observations", "processed")
        resolution = resolve_catalog_product_for_import(
            session,
            catalog_source=observation.catalog_source,
            model=observation.model,
            mpn=observation.mpn,
            product_id=observation.product_id,
        )
        if resolution.product is None:
            reason = (
                "ambiguous_identity"
                if resolution.match_type == "ambiguous_mpn"
                else "unresolved_identity"
            )
            _skip(
                result,
                reason,
                f"price_observation {observation.id}: {resolution.warning or resolution.match_type}",
                item={
                    "url": observation.product_url,
                    "source_name": _empty_to_none(observation.source),
                    "catalog_source": observation.catalog_source,
                    "model": observation.model,
                    "mpn": observation.mpn,
                    "catalog_product_id": None,
                    "status": None,
                    "action": "skipped",
                    "confidence": "none",
                    "evidence_source": "price_observations",
                    "evidence_detail": f"price_observation_id={observation.id}",
                    "reason": reason,
                },
            )
            continue
        _increment_source_stat(result, "observations", "candidates")
        successful = (
            observation.competitor_price is not None
            or observation.match_status == "matched"
        )
        yield SourceUrlImportCandidate(
            url=observation.product_url or "",
            source_name=_empty_to_none(observation.source),
            catalog_source=resolution.product.catalog_source,
            model=observation.model,
            mpn=observation.mpn,
            catalog_product_id=resolution.product.id,
            status="active",
            url_type="imported",
            trust_level="imported",
            evidence_source="price_observations",
            evidence_detail=f"price_observation_id={observation.id} match={resolution.match_type}",
            confidence=resolution.confidence,
            observed_at=observation.observed_at,
            notes="Imported from price_observations",
            successful_evidence=successful,
        )


def _iter_artifact_candidates(
    session: Session,
    *,
    catalog_source: str | None,
    result: SourceUrlImportResult,
) -> Iterable[SourceUrlImportCandidate]:
    statement = select(MonitoringRun).where(
        MonitoringRun.enriched_csv_path.is_not(None),
        func.trim(MonitoringRun.enriched_csv_path) != "",
    )
    statement = statement.order_by(MonitoringRun.id.desc())
    seen_paths: set[Path] = set()
    for run in session.execute(statement).scalars().all():
        path = Path(str(run.enriched_csv_path or "")).expanduser()
        resolved = path.resolve(strict=False)
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        _increment_source_stat(result, "artifacts", "processed")
        yield from _parse_artifact_path(
            session,
            path,
            run_id=run.run_id,
            source=run.source,
            catalog_source=catalog_source or DEFAULT_CATALOG_SOURCE,
            default_observed_at=run.completed_at or run.created_at,
            evidence_detail=f"monitoring_run_id={run.id} path={path}",
            result=result,
        )


def _parse_artifact_path(
    session: Session,
    path: Path,
    *,
    run_id: str,
    source: str,
    catalog_source: str,
    default_observed_at: datetime | None,
    evidence_detail: str,
    result: SourceUrlImportResult,
) -> Iterable[SourceUrlImportCandidate]:
    if not path.exists() or not path.is_file():
        result.warnings.append(f"Enriched CSV artifact not found: {path}")
        return
    parsed = parse_price_observations_csv(
        path,
        run_id=run_id,
        source=source,
        catalog_source=catalog_source,
        default_observed_at=default_observed_at,
    )
    result.warnings.extend(parsed.warnings)
    for observation in parsed.observations:
        if not observation.product_url:
            continue
        candidate = _artifact_observation_to_candidate(
            session, observation, evidence_detail, result
        )
        if candidate is not None:
            yield candidate


def _artifact_observation_to_candidate(
    session: Session,
    observation: ParsedPriceObservation,
    evidence_detail: str,
    result: SourceUrlImportResult,
) -> SourceUrlImportCandidate | None:
    resolution = resolve_catalog_product_for_import(
        session,
        catalog_source=observation.catalog_source,
        model=observation.model,
        mpn=observation.mpn,
    )
    if resolution.product is None:
        reason = (
            "ambiguous_identity"
            if resolution.match_type == "ambiguous_mpn"
            else "unresolved_identity"
        )
        _skip(
            result,
            reason,
            f"artifact row {observation.run_id}: {resolution.warning or resolution.match_type}",
            item={
                "url": observation.product_url,
                "source_name": _empty_to_none(observation.source),
                "catalog_source": observation.catalog_source,
                "model": observation.model,
                "mpn": observation.mpn,
                "catalog_product_id": None,
                "status": None,
                "action": "skipped",
                "confidence": "none",
                "evidence_source": "enriched_csv_artifact",
                "evidence_detail": evidence_detail,
                "reason": reason,
            },
        )
        return None
    _increment_source_stat(result, "artifacts", "candidates")
    status = "active" if resolution.match_type == "model" else "needs_review"
    return SourceUrlImportCandidate(
        url=observation.product_url or "",
        source_name=_empty_to_none(observation.source),
        catalog_source=resolution.product.catalog_source,
        model=observation.model,
        mpn=observation.mpn,
        catalog_product_id=resolution.product.id,
        status=status,
        url_type="imported",
        trust_level="imported",
        evidence_source="enriched_csv_artifact",
        evidence_detail=evidence_detail,
        confidence=resolution.confidence,
        observed_at=observation.observed_at,
        notes="Imported from enriched CSV artifact",
        successful_evidence=observation.competitor_price is not None,
    )


def _process_candidate(
    session: Session,
    candidate: SourceUrlImportCandidate,
    result: SourceUrlImportResult,
    seen_keys: set[tuple[int, str]],
    *,
    apply: bool,
) -> None:
    try:
        normalized = normalize_source_url(candidate.url)
    except SourceUrlValidationError as exc:
        _skip(
            result,
            "invalid_url",
            f"{candidate.evidence_detail}: {exc}",
            item={
                **candidate.to_dict(),
                "catalog_product_id": candidate.catalog_product_id,
                "action": "skipped",
                "reason": "invalid_url",
            },
        )
        return

    result.counters["candidates_found"] += 1
    domain = extract_source_domain(normalized)
    source_name = candidate.source_name or infer_source_name(domain)
    key = (candidate.catalog_product_id, normalized)
    result.candidate_evidence.append(
        {**candidate.to_dict(), "url_normalized": normalized, "source_domain": domain}
    )
    if key in seen_keys:
        result.counters["duplicate_count"] += 1
        result.report_items.append(
            _candidate_report_item(
                candidate,
                normalized_url=normalized,
                source_domain=domain,
                action="duplicate",
                source_url_id=None,
                reason="duplicate_candidate",
            )
        )
        return
    seen_keys.add(key)

    upsert = create_or_update_imported_source_url(
        session,
        catalog_product_id=candidate.catalog_product_id,
        url=candidate.url,
        source_name=source_name,
        url_type=candidate.url_type,
        trust_level=candidate.trust_level,
        status=candidate.status,
        last_seen_at=candidate.observed_at,
        last_success_at=(
            candidate.observed_at if candidate.successful_evidence else None
        ),
        notes=candidate.notes,
        apply=apply,
    )
    if upsert.action == "created":
        result.counters["imported_count"] += 1
    elif upsert.action == "updated":
        result.counters["updated_count"] += 1
    elif upsert.action == "duplicate":
        result.counters["duplicate_count"] += 1

    if candidate.status == "active":
        result.counters["active_count"] += 1
    elif candidate.status == "needs_review":
        result.counters["needs_review_count"] += 1
    if upsert.row is not None and upsert.action in {"created", "updated"}:
        result.changed_source_urls.append(
            {
                "action": upsert.action,
                "changed_fields": upsert.changed_fields,
                "source_url": source_url_to_dict(upsert.row),
            }
        )
    elif upsert.action in {"created", "updated"}:
        result.changed_source_urls.append(
            {
                "action": upsert.action,
                "changed_fields": upsert.changed_fields,
                "source_url_id": upsert.source_url_id,
                "catalog_product_id": candidate.catalog_product_id,
                "url_normalized": normalized,
            }
        )
    result.report_items.append(
        _candidate_report_item(
            candidate,
            normalized_url=normalized,
            source_domain=domain,
            action=upsert.action,
            source_url_id=upsert.source_url_id,
            reason=None if upsert.action != "duplicate" else "already_exists",
        )
    )


def _skip(
    result: SourceUrlImportResult,
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


def _candidate_report_item(
    candidate: SourceUrlImportCandidate,
    *,
    normalized_url: str,
    source_domain: str,
    action: str,
    source_url_id: int | None,
    reason: str | None,
) -> dict[str, Any]:
    return {
        **candidate.to_dict(),
        "url_normalized": normalized_url,
        "source_domain": source_domain,
        "source_url_id": source_url_id,
        "action": action,
        "reason": reason,
    }


def _increment_source_stat(
    result: SourceUrlImportResult, source_key: str, field_name: str
) -> None:
    stats = result.source_stats.setdefault(source_key, Counter())
    stats[field_name] += 1


def _looks_composite_model(value: str) -> bool:
    text = value.strip()
    return any(separator in text for separator in (";", "|", "\n"))


def _empty_to_none(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()
