"""Product Factory batch intake API and domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel


BATCH_ROW_STATUSES = {
    "pending",
    "auto_selected",
    "manually_selected",
    "needs_review",
    "no_usable_source",
    "resolution_failed",
    "skipped",
}


@dataclass(frozen=True)
class ParsedBatchRow:
    row_number: int
    model: str
    brand: str
    name: str


@dataclass(frozen=True)
class ParsedBatchCsv:
    delimiter: str
    rows: tuple[ParsedBatchRow, ...]


class ProductFactoryBatchRowResponse(BaseModel):
    id: int
    batch_id: int
    row_number: int
    model: str
    brand: str
    name: str
    queries: list[str] = []
    status: str
    selected_url: str | None = None
    selected_source: str | None = None
    confidence: int | None = None
    candidates: list[dict[str, Any]] = []
    error_code: str | None = None
    error_message: str | None = None
    selection_metadata: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class ProductFactoryBatchResponse(BaseModel):
    id: int
    filename: str | None = None
    status: str
    total_rows: int
    pending_count: int
    auto_selected_count: int
    manually_selected_count: int
    needs_review_count: int
    no_usable_source_count: int
    resolution_failed_count: int
    skipped_count: int
    metadata: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class ProductFactoryBatchUploadResponse(ProductFactoryBatchResponse):
    preview_rows: list[ProductFactoryBatchRowResponse]


class ProductFactoryBatchListResponse(BaseModel):
    items: list[ProductFactoryBatchResponse]


class ProductFactoryBatchRowsResponse(BaseModel):
    items: list[ProductFactoryBatchRowResponse]


class SelectSourceRequest(BaseModel):
    candidate_url: str | None = None
    manual_url: str | None = None


class ProductFactoryBatchResolveResponse(ProductFactoryBatchResponse):
    rows: list[ProductFactoryBatchRowResponse]
