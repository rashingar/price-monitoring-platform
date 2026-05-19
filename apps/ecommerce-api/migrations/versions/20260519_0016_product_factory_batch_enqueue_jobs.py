"""product factory batch enqueue job fields

Revision ID: 20260519_0016
Revises: 20260519_0015
Create Date: 2026-05-19 18:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260519_0016"
down_revision = "20260519_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("product_factory_batch_rows", sa.Column("product_factory_job_id", sa.String(), nullable=True))
    op.add_column("product_factory_batch_rows", sa.Column("product_factory_job_status", sa.String(), nullable=True))
    op.add_column("product_factory_batch_rows", sa.Column("product_factory_job_message", sa.Text(), nullable=True))
    op.add_column("product_factory_batch_rows", sa.Column("product_factory_error_code", sa.String(), nullable=True))
    op.add_column("product_factory_batch_rows", sa.Column("product_factory_error_message", sa.Text(), nullable=True))
    op.add_column("product_factory_batch_rows", sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("product_factory_batch_rows", sa.Column("job_status_refreshed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("product_factory_batch_rows", "job_status_refreshed_at")
    op.drop_column("product_factory_batch_rows", "enqueued_at")
    op.drop_column("product_factory_batch_rows", "product_factory_error_message")
    op.drop_column("product_factory_batch_rows", "product_factory_error_code")
    op.drop_column("product_factory_batch_rows", "product_factory_job_message")
    op.drop_column("product_factory_batch_rows", "product_factory_job_status")
    op.drop_column("product_factory_batch_rows", "product_factory_job_id")
