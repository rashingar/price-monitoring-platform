"""Repository functions for optional price monitoring persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session, aliased

from ecommerce.catalog.source_catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.models import CatalogSnapshot, MonitoringRun, PriceObservation, Product
from ecommerce.price_monitoring.fetch_run import PriceMonitoringFetchResult
from ecommerce.price_monitoring.observations import ParsedPriceObservation
from ecommerce.price_monitoring.runs import PriceMonitoringRunRecord
from ecommerce.price_monitoring.selection import SelectedPriceMonitoringProduct


@dataclass(frozen=True)
class ObservationReplacementResult:
    observation_count: int
    replaced_observation_count: int
    matched_observation_count: int
    unmatched_observation_count: int
    was_refetch: bool
    fetch_attempt: int


def persist_monitoring_run_creation(
    session: Session,
    record: PriceMonitoringRunRecord,
    *,
    trigger_type: str = "manual",
    catalog_source: str = DEFAULT_CATALOG_SOURCE,
) -> MonitoringRun:
    now = _now()
    created_at = _parse_datetime(record.created_at) or now
    monitoring_run = get_monitoring_run(session, record.run_id)
    if monitoring_run is None:
        monitoring_run = MonitoringRun(
            run_id=record.run_id,
            source=record.source,
            status=record.status,
            trigger_type=trigger_type,
            created_at=created_at,
            updated_at=now,
        )
        session.add(monitoring_run)
        session.flush()

    monitoring_run.source = record.source
    monitoring_run.status = record.status
    monitoring_run.trigger_type = trigger_type
    monitoring_run.output_dir = str(record.output_dir)
    monitoring_run.input_csv_path = str(record.input_csv_path)
    monitoring_run.selection_summary_path = str(record.selection_summary_path)
    monitoring_run.selected_count = record.selection_result.selected_count
    monitoring_run.skipped_count = record.selection_result.skipped_count
    monitoring_run.error_message = None
    monitoring_run.updated_at = now

    replace_catalog_snapshots(
        session,
        monitoring_run,
        record.selection_result.items,
        catalog_source=catalog_source,
        created_at=now,
    )
    return monitoring_run


def update_monitoring_run_from_fetch(
    session: Session,
    result: PriceMonitoringFetchResult,
    *,
    trigger_type: str | None = None,
) -> MonitoringRun:
    now = _now()
    monitoring_run = get_monitoring_run(session, result.run_id)
    if monitoring_run is None:
        monitoring_run = MonitoringRun(
            run_id=result.run_id,
            source=result.source,
            status=result.status,
            trigger_type=trigger_type or "manual",
            output_dir=str(Path(result.input_csv_path).parent),
            input_csv_path=str(result.input_csv_path),
            created_at=_parse_datetime(result.started_at) or now,
            updated_at=now,
        )
        session.add(monitoring_run)
        session.flush()

    monitoring_run.source = result.source
    monitoring_run.status = result.status
    if trigger_type is not None:
        monitoring_run.trigger_type = trigger_type
    monitoring_run.output_dir = str(Path(result.input_csv_path).parent)
    monitoring_run.input_csv_path = str(result.input_csv_path)
    selection_summary_path = Path(result.input_csv_path).parent / "selection_summary.json"
    if selection_summary_path.exists():
        monitoring_run.selection_summary_path = str(selection_summary_path)
    monitoring_run.fetch_result_path = str(result.fetch_result_path)
    monitoring_run.enriched_csv_path = str(result.enriched_csv_path) if result.enriched_csv_path is not None else None
    monitoring_run.fetch_summary_path = str(result.fetch_summary_path) if result.fetch_summary_path is not None else None
    monitoring_run.started_at = _parse_datetime(result.started_at)
    monitoring_run.completed_at = _parse_datetime(result.completed_at)
    monitoring_run.error_message = result.error or None
    monitoring_run.updated_at = now
    return monitoring_run


def upsert_product_from_catalog_row(
    session: Session,
    row: dict[str, Any],
    *,
    catalog_source: str = DEFAULT_CATALOG_SOURCE,
    updated_at: datetime | None = None,
) -> Product | None:
    model = _empty_to_none(_first_text(row, ("model", "product_model", "sku")))
    mpn = _empty_to_none(_first_text(row, ("mpn", "manufacturer_part_number", "matched_mpn")))
    if not model and not mpn:
        return None

    timestamp = updated_at or _now()
    product = find_product_by_identity(session, catalog_source=catalog_source, model=model, mpn=mpn)
    if product is None:
        product = Product(
            catalog_source=catalog_source,
            model=model,
            mpn=mpn,
            created_at=timestamp,
            updated_at=timestamp,
        )
        session.add(product)
        session.flush()

    product.catalog_source = catalog_source
    product.model = model or product.model
    product.mpn = mpn or product.mpn
    product.name = _empty_to_none(_first_text(row, ("name", "product_name", "title")))
    product.manufacturer = _empty_to_none(_first_text(row, ("manufacturer", "brand")))
    product.family = _empty_to_none(_first_text(row, ("family",)))
    product.category_name = _empty_to_none(_first_text(row, ("category_name", "category")))
    product.sub_category = _empty_to_none(_first_text(row, ("sub_category", "subcategory")))
    product.current_price = _decimal_or_none(_first_text(row, ("own_price", "price", "current_price", "internal_price", "catalog_price")))
    product.currency = _first_text(row, ("currency",)) or "EUR"
    product.active = True
    product.raw_catalog_row = _json_safe(row)
    product.updated_at = timestamp
    return product


def find_product_by_identity(
    session: Session,
    *,
    catalog_source: str,
    model: str | None,
    mpn: str | None,
) -> Product | None:
    if model:
        return session.execute(
            select(Product).where(Product.catalog_source == catalog_source, Product.model == model).limit(1)
        ).scalar_one_or_none()
    if mpn:
        return session.execute(
            select(Product).where(Product.catalog_source == catalog_source, Product.mpn == mpn).limit(1)
        ).scalar_one_or_none()
    return None


def match_product_for_observation(
    session: Session,
    *,
    catalog_source: str,
    model: str | None,
    mpn: str | None,
) -> tuple[Product | None, str | None]:
    if model:
        product = session.execute(
            select(Product).where(Product.catalog_source == catalog_source, Product.model == model).limit(1)
        ).scalar_one_or_none()
        if product is not None:
            return product, "model"
    if mpn:
        product = session.execute(
            select(Product).where(Product.catalog_source == catalog_source, Product.mpn == mpn).limit(1)
        ).scalar_one_or_none()
        if product is not None:
            return product, "mpn"
    return None, None


def replace_catalog_snapshots(
    session: Session,
    monitoring_run: MonitoringRun,
    products: list[SelectedPriceMonitoringProduct],
    *,
    catalog_source: str = DEFAULT_CATALOG_SOURCE,
    created_at: datetime | None = None,
) -> int:
    session.execute(delete(CatalogSnapshot).where(CatalogSnapshot.monitoring_run_id == monitoring_run.id))
    timestamp = created_at or _now()
    inserted = 0
    seen: set[tuple[str, str, str]] = set()
    for product in products:
        row = product.to_dict()
        key = _snapshot_identity_key(row, catalog_source)
        if key is None or key in seen:
            continue
        seen.add(key)
        db_product = upsert_product_from_catalog_row(session, row, catalog_source=catalog_source, updated_at=timestamp)
        session.add(_catalog_snapshot_from_row(monitoring_run, row, catalog_source, db_product, timestamp))
        inserted += 1
    return inserted


def ensure_catalog_snapshots_from_rows(
    session: Session,
    monitoring_run: MonitoringRun,
    rows: list[dict[str, Any]],
    *,
    catalog_source: str = DEFAULT_CATALOG_SOURCE,
    created_at: datetime | None = None,
) -> int:
    existing_count = count_catalog_snapshots(session, monitoring_run.id)
    if existing_count > 0:
        return existing_count
    timestamp = created_at or _now()
    inserted = 0
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = _snapshot_identity_key(row, catalog_source)
        if key is None or key in seen:
            continue
        seen.add(key)
        db_product = upsert_product_from_catalog_row(session, row, catalog_source=catalog_source, updated_at=timestamp)
        session.add(_catalog_snapshot_from_row(monitoring_run, row, catalog_source, db_product, timestamp))
        inserted += 1
    return inserted


def replace_price_observations(
    session: Session,
    monitoring_run: MonitoringRun,
    observations: list[ParsedPriceObservation],
    *,
    created_at: datetime | None = None,
) -> ObservationReplacementResult:
    previous_count = count_price_observations(session, monitoring_run.run_id)
    timestamp = created_at or _now()
    next_fetch_attempt = int(monitoring_run.fetch_attempt or 0) + 1
    was_refetch = previous_count > 0
    matched = 0
    unmatched = 0
    for observation in observations:
        product, matched_by = match_product_for_observation(
            session,
            catalog_source=observation.catalog_source,
            model=observation.model,
            mpn=observation.mpn,
        )
        if product is None:
            unmatched += 1
        else:
            matched += 1
        session.add(
            _price_observation_from_parsed(
                monitoring_run,
                observation,
                product,
                matched_by,
                timestamp,
                fetch_attempt=next_fetch_attempt,
                was_refetch=was_refetch,
            )
        )

    monitoring_run.fetch_attempt = next_fetch_attempt
    monitoring_run.last_was_refetch = was_refetch
    monitoring_run.updated_at = timestamp
    return ObservationReplacementResult(
        observation_count=len(observations),
        replaced_observation_count=previous_count,
        matched_observation_count=matched,
        unmatched_observation_count=unmatched,
        was_refetch=was_refetch,
        fetch_attempt=monitoring_run.fetch_attempt,
    )


def get_monitoring_run(session: Session, run_id: str) -> MonitoringRun | None:
    return session.execute(select(MonitoringRun).where(MonitoringRun.run_id == run_id)).scalar_one_or_none()


def list_monitoring_runs(session: Session, *, limit: int = 500, offset: int = 0) -> list[dict[str, Any]]:
    statement = (
        select(MonitoringRun)
        .order_by(MonitoringRun.created_at.desc(), MonitoringRun.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [monitoring_run_to_dict(run) for run in session.execute(statement).scalars().all()]


def count_catalog_snapshots(session: Session, monitoring_run_id: int) -> int:
    statement = select(func.count(CatalogSnapshot.id)).where(CatalogSnapshot.monitoring_run_id == monitoring_run_id)
    return int(session.execute(statement).scalar_one())


def count_price_observations(session: Session, run_id: str) -> int:
    statement = _latest_run_attempt_filter(
        select(func.count(PriceObservation.id)).where(PriceObservation.run_id == run_id),
        run_id=run_id,
    )
    return int(session.execute(statement).scalar_one())


def list_price_observations(
    session: Session,
    *,
    run_id: str | None = None,
    source: str | None = None,
    catalog_source: str | None = None,
    model: str | None = None,
    mpn: str | None = None,
    product_id: int | None = None,
    match_status: str | None = None,
    include_unmatched: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    statement = _observation_filters(
        select(PriceObservation),
        run_id=run_id,
        source=source,
        catalog_source=catalog_source,
        model=model,
        mpn=mpn,
        product_id=product_id,
        match_status=match_status,
        include_unmatched=include_unmatched,
    )
    statement = _latest_run_attempt_filter(statement, run_id=run_id)
    count_statement = _observation_filters(
        select(func.count(PriceObservation.id)),
        run_id=run_id,
        source=source,
        catalog_source=catalog_source,
        model=model,
        mpn=mpn,
        product_id=product_id,
        match_status=match_status,
        include_unmatched=include_unmatched,
    )
    count_statement = _latest_run_attempt_filter(count_statement, run_id=run_id)
    statement = statement.order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc()).limit(limit).offset(offset)
    items = [price_observation_to_dict(item) for item in session.execute(statement).scalars().all()]
    count = int(session.execute(count_statement).scalar_one())
    return items, count


def count_run_observations_by_match_status(session: Session, run_id: str) -> tuple[int, int]:
    matched = int(
        session.execute(
            _latest_run_attempt_filter(
                select(func.count(PriceObservation.id)).where(
                    PriceObservation.run_id == run_id,
                    PriceObservation.match_status == "matched",
                ),
                run_id=run_id,
            )
        ).scalar_one()
    )
    unmatched = int(
        session.execute(
            _latest_run_attempt_filter(
                select(func.count(PriceObservation.id)).where(
                    PriceObservation.run_id == run_id,
                    PriceObservation.match_status == "unmatched",
                ),
                run_id=run_id,
            )
        ).scalar_one()
    )
    return matched, unmatched


def list_catalog_snapshot(session: Session, run_id: str) -> list[dict[str, Any]]:
    statement = select(CatalogSnapshot).where(CatalogSnapshot.run_id == run_id).order_by(
        CatalogSnapshot.model.asc().nullslast(),
        CatalogSnapshot.mpn.asc().nullslast(),
        CatalogSnapshot.id.asc(),
    )
    return [catalog_snapshot_to_dict(item) for item in session.execute(statement).scalars().all()]


def list_product_price_history(session: Session, product_id: int, *, limit: int = 1000, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    statement = (
        select(PriceObservation)
        .where(PriceObservation.product_id == product_id)
        .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    count_statement = select(func.count(PriceObservation.id)).where(PriceObservation.product_id == product_id)
    return [price_observation_to_dict(item) for item in session.execute(statement).scalars().all()], int(
        session.execute(count_statement).scalar_one()
    )


def list_model_price_history(
    session: Session,
    model: str,
    *,
    catalog_source: str | None = None,
    include_unmatched: bool = True,
    limit: int = 1000,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    statement = _observation_filters(
        select(PriceObservation),
        run_id=None,
        source=None,
        catalog_source=catalog_source,
        model=model,
        mpn=None,
        product_id=None,
        match_status=None,
        include_unmatched=include_unmatched,
    )
    count_statement = _observation_filters(
        select(func.count(PriceObservation.id)),
        run_id=None,
        source=None,
        catalog_source=catalog_source,
        model=model,
        mpn=None,
        product_id=None,
        match_status=None,
        include_unmatched=include_unmatched,
    )
    statement = statement.order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc()).limit(limit).offset(offset)
    return [price_observation_to_dict(item) for item in session.execute(statement).scalars().all()], int(
        session.execute(count_statement).scalar_one()
    )


def monitoring_run_to_dict(run: MonitoringRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "run_id": run.run_id,
        "source": run.source,
        "status": run.status,
        "trigger_type": run.trigger_type,
        "output_dir": run.output_dir,
        "input_csv_path": run.input_csv_path,
        "selection_summary_path": run.selection_summary_path,
        "fetch_result_path": run.fetch_result_path,
        "enriched_csv_path": run.enriched_csv_path,
        "fetch_summary_path": run.fetch_summary_path,
        "selected_count": run.selected_count,
        "skipped_count": run.skipped_count,
        "fetch_attempt": run.fetch_attempt,
        "last_was_refetch": run.last_was_refetch,
        "error_message": run.error_message,
        "created_at": json_safe_value(run.created_at),
        "started_at": json_safe_value(run.started_at),
        "completed_at": json_safe_value(run.completed_at),
        "updated_at": json_safe_value(run.updated_at),
    }


def product_to_dict(product: Product) -> dict[str, Any]:
    return {
        "id": product.id,
        "catalog_source": product.catalog_source,
        "model": product.model,
        "mpn": product.mpn,
        "name": product.name,
        "manufacturer": product.manufacturer,
        "family": product.family,
        "category_name": product.category_name,
        "sub_category": product.sub_category,
        "current_price": json_safe_value(product.current_price),
        "currency": product.currency,
        "active": product.active,
        "raw_catalog_row": json_safe_value(product.raw_catalog_row),
        "created_at": json_safe_value(product.created_at),
        "updated_at": json_safe_value(product.updated_at),
    }


def catalog_snapshot_to_dict(snapshot: CatalogSnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "product_id": snapshot.product_id,
        "run_id": snapshot.run_id,
        "catalog_source": snapshot.catalog_source,
        "model": snapshot.model,
        "mpn": snapshot.mpn,
        "name": snapshot.name,
        "manufacturer": snapshot.manufacturer,
        "family": snapshot.family,
        "category_name": snapshot.category_name,
        "sub_category": snapshot.sub_category,
        "marketplace": snapshot.marketplace,
        "own_price": json_safe_value(snapshot.own_price),
        "currency": snapshot.currency,
        "raw_catalog_row": json_safe_value(snapshot.raw_catalog_row),
        "created_at": json_safe_value(snapshot.created_at),
    }


def price_observation_to_dict(observation: PriceObservation) -> dict[str, Any]:
    return {
        "id": observation.id,
        "product_id": observation.product_id,
        "run_id": observation.run_id,
        "observation_batch_id": observation.observation_batch_id,
        "catalog_source": observation.catalog_source,
        "source": observation.source,
        "model": observation.model,
        "mpn": observation.mpn,
        "product_name": observation.product_name,
        "competitor_name": observation.competitor_name,
        "competitor_price": json_safe_value(observation.competitor_price),
        "own_price": json_safe_value(observation.own_price),
        "price_delta": json_safe_value(observation.price_delta),
        "price_delta_percent": json_safe_value(observation.price_delta_percent),
        "currency": observation.currency,
        "availability": observation.availability,
        "product_url": observation.product_url,
        "matched_by": observation.matched_by,
        "match_status": observation.match_status,
        "is_matched": observation.match_status == "matched",
        "observed_at": json_safe_value(observation.observed_at),
        "created_at": json_safe_value(observation.created_at),
        "raw_observation": json_safe_value(observation.raw_observation),
    }


def _observation_filters(
    statement: Select,
    *,
    run_id: str | None,
    source: str | None,
    catalog_source: str | None,
    model: str | None,
    mpn: str | None,
    product_id: int | None,
    match_status: str | None,
    include_unmatched: bool,
) -> Select:
    if run_id:
        statement = statement.where(PriceObservation.run_id == run_id)
    if source:
        statement = statement.where(PriceObservation.source == source)
    if catalog_source:
        statement = statement.where(PriceObservation.catalog_source == catalog_source)
    if model:
        statement = statement.where(PriceObservation.model == model)
    if mpn:
        statement = statement.where(PriceObservation.mpn == mpn)
    if product_id is not None:
        statement = statement.where(PriceObservation.product_id == product_id)
    if match_status:
        statement = statement.where(PriceObservation.match_status == match_status)
    elif not include_unmatched:
        statement = statement.where(PriceObservation.match_status == "matched")
    return statement


def _latest_run_attempt_filter(statement: Select, *, run_id: str | None) -> Select:
    if not run_id:
        return statement
    latest_observation = aliased(PriceObservation)
    latest_created_at = (
        select(func.max(latest_observation.created_at))
        .where(latest_observation.run_id == run_id)
        .scalar_subquery()
    )
    return statement.where(PriceObservation.created_at == latest_created_at)


def _catalog_snapshot_from_row(
    monitoring_run: MonitoringRun,
    row: dict[str, Any],
    catalog_source: str,
    product: Product | None,
    created_at: datetime,
) -> CatalogSnapshot:
    return CatalogSnapshot(
        monitoring_run_id=monitoring_run.id,
        product_id=product.id if product is not None else None,
        run_id=monitoring_run.run_id,
        catalog_source=catalog_source,
        model=_empty_to_none(_first_text(row, ("model", "product_model", "sku"))),
        mpn=_empty_to_none(_first_text(row, ("mpn", "manufacturer_part_number", "matched_mpn"))),
        name=_empty_to_none(_first_text(row, ("name", "product_name", "title"))),
        manufacturer=_empty_to_none(_first_text(row, ("manufacturer", "brand"))),
        family=_empty_to_none(_first_text(row, ("family",))),
        category_name=_empty_to_none(_first_text(row, ("category_name", "category"))),
        sub_category=_empty_to_none(_first_text(row, ("sub_category", "subcategory"))),
        marketplace=_empty_to_none(_first_text(row, ("marketplace", "source"))) or monitoring_run.source,
        own_price=_decimal_or_none(_first_text(row, ("own_price", "price", "current_price", "internal_price", "catalog_price"))),
        currency=_first_text(row, ("currency",)) or "EUR",
        raw_catalog_row=_json_safe(row),
        created_at=created_at,
    )


def _price_observation_from_parsed(
    monitoring_run: MonitoringRun,
    observation: ParsedPriceObservation,
    product: Product | None,
    matched_by: str | None,
    created_at: datetime,
    *,
    fetch_attempt: int,
    was_refetch: bool,
) -> PriceObservation:
    raw_observation = _json_safe(observation.raw_observation or {})
    raw_observation.setdefault(
        "persistence",
        {
            "fetch_attempt": fetch_attempt,
            "was_refetch": was_refetch,
        },
    )
    return PriceObservation(
        monitoring_run_id=monitoring_run.id,
        product_id=product.id if product is not None else None,
        run_id=observation.run_id,
        catalog_source=observation.catalog_source,
        source=observation.source,
        model=observation.model,
        mpn=observation.mpn,
        product_name=observation.product_name,
        competitor_name=observation.competitor_name,
        competitor_price=observation.competitor_price,
        currency=observation.currency,
        availability=observation.availability,
        product_url=observation.product_url,
        own_price=observation.own_price,
        price_delta=observation.price_delta,
        price_delta_percent=observation.price_delta_percent,
        raw_observation=raw_observation,
        matched_by=matched_by,
        match_status="matched" if product is not None else "unmatched",
        observed_at=observation.observed_at,
        created_at=created_at,
    )


def _snapshot_identity_key(row: dict[str, Any], catalog_source: str) -> tuple[str, str, str] | None:
    model = _empty_to_none(_first_text(row, ("model", "product_model", "sku")))
    mpn = _empty_to_none(_first_text(row, ("mpn", "manufacturer_part_number", "matched_mpn")))
    if model:
        return catalog_source, "model", model
    if mpn:
        return catalog_source, "mpn", mpn
    return None


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text.replace("EUR", "").replace("€", "").replace(" ", "").replace(",", "."))
    except Exception:
        return None


def _first_text(row: dict[str, Any], aliases: tuple[str, ...]) -> str:
    normalized = {_normalize_key(key): key for key in row.keys()}
    for alias in aliases:
        key = normalized.get(_normalize_key(alias))
        if key is not None:
            return str(row.get(key) or "").strip()
    return ""


def _normalize_key(value: object) -> str:
    return str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")


def _empty_to_none(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def json_safe_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, list):
        return [json_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe_value(item) for key, item in value.items()}
    return value


def _json_safe(row: dict[str, Any]) -> dict[str, Any]:
    return json_safe_value(dict(row))  # type: ignore[return-value]


def _now() -> datetime:
    return datetime.now(timezone.utc)
