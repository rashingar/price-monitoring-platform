"""Repository helpers for Product Factory batch intake."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ecommerce.db.models.product_factory_batch import ProductFactoryBatch, ProductFactoryBatchRow
from ecommerce.db.repositories.common import _now
from ecommerce.product_factory_batch.models import ParsedBatchCsv


def create_batch(session: Session, *, parsed: ParsedBatchCsv, filename: str | None) -> ProductFactoryBatch:
    now = _now()
    batch = ProductFactoryBatch(
        filename=filename,
        status="uploaded",
        total_rows=len(parsed.rows),
        pending_count=len(parsed.rows),
        metadata_json={"delimiter": parsed.delimiter},
        created_at=now,
        updated_at=now,
    )
    session.add(batch)
    session.flush()
    for parsed_row in parsed.rows:
        session.add(
            ProductFactoryBatchRow(
                batch_id=batch.id,
                row_number=parsed_row.row_number,
                model=parsed_row.model,
                brand=parsed_row.brand,
                name=parsed_row.name,
                status="pending",
                created_at=now,
                updated_at=now,
            )
        )
    session.flush()
    session.refresh(batch, attribute_names=["rows"])
    return batch


def list_batches(session: Session, *, limit: int = 100, offset: int = 0) -> list[ProductFactoryBatch]:
    return list(
        session.execute(
            select(ProductFactoryBatch)
            .order_by(ProductFactoryBatch.created_at.desc(), ProductFactoryBatch.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )


def get_batch(session: Session, batch_id: int, *, with_rows: bool = False) -> ProductFactoryBatch | None:
    statement = select(ProductFactoryBatch).where(ProductFactoryBatch.id == batch_id)
    if with_rows:
        statement = statement.options(selectinload(ProductFactoryBatch.rows))
    return session.execute(statement).scalar_one_or_none()


def list_batch_rows(session: Session, batch_id: int) -> list[ProductFactoryBatchRow]:
    return list(
        session.execute(
            select(ProductFactoryBatchRow)
            .where(ProductFactoryBatchRow.batch_id == batch_id)
            .order_by(ProductFactoryBatchRow.row_number.asc(), ProductFactoryBatchRow.id.asc())
        )
        .scalars()
        .all()
    )


def get_batch_row(session: Session, *, batch_id: int, row_id: int) -> ProductFactoryBatchRow | None:
    return session.execute(
        select(ProductFactoryBatchRow).where(
            ProductFactoryBatchRow.batch_id == batch_id,
            ProductFactoryBatchRow.id == row_id,
        )
    ).scalar_one_or_none()


def refresh_batch_counts(session: Session, batch: ProductFactoryBatch) -> ProductFactoryBatch:
    counts = Counter(
        str(status)
        for status in session.execute(
            select(ProductFactoryBatchRow.status).where(ProductFactoryBatchRow.batch_id == batch.id)
        )
        .scalars()
        .all()
    )
    batch.total_rows = int(session.execute(select(func.count(ProductFactoryBatchRow.id)).where(ProductFactoryBatchRow.batch_id == batch.id)).scalar_one())
    batch.pending_count = counts.get("pending", 0)
    batch.auto_selected_count = counts.get("auto_selected", 0)
    batch.manually_selected_count = counts.get("manually_selected", 0)
    batch.needs_review_count = counts.get("needs_review", 0)
    batch.no_usable_source_count = counts.get("no_usable_source", 0)
    batch.resolution_failed_count = counts.get("resolution_failed", 0)
    batch.skipped_count = counts.get("skipped", 0)
    resolving_count = counts.get("resolving_source", 0)
    if batch.status == "failed":
        pass
    elif resolving_count or (batch.status == "resolving" and batch.pending_count):
        batch.status = "resolving"
    elif batch.resolution_failed_count:
        batch.status = "partially_resolved"
    elif batch.pending_count:
        batch.status = "uploaded"
    else:
        batch.status = "resolved"
    batch.updated_at = _now()
    session.flush()
    return batch


def batch_to_dict(batch: ProductFactoryBatch) -> dict[str, Any]:
    return {
        "id": batch.id,
        "filename": batch.filename,
        "status": batch.status,
        "total_rows": batch.total_rows,
        "pending_count": batch.pending_count,
        "auto_selected_count": batch.auto_selected_count,
        "manually_selected_count": batch.manually_selected_count,
        "needs_review_count": batch.needs_review_count,
        "no_usable_source_count": batch.no_usable_source_count,
        "resolution_failed_count": batch.resolution_failed_count,
        "skipped_count": batch.skipped_count,
        "metadata": batch.metadata_json,
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
    }


def row_to_dict(row: ProductFactoryBatchRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "batch_id": row.batch_id,
        "row_number": row.row_number,
        "model": row.model,
        "brand": row.brand,
        "name": row.name,
        "queries": list(row.queries_json or []),
        "status": row.status,
        "selected_url": row.selected_url,
        "selected_source": row.selected_source,
        "confidence": row.confidence,
        "candidates": list(row.candidate_urls_json or []),
        "error_code": row.error_code,
        "error_message": row.error_message,
        "selection_metadata": row.selection_metadata_json,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
