"""product factory batch async resolution statuses

Revision ID: 20260519_0015
Revises: 20260519_0014
Create Date: 2026-05-19 16:10:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260519_0015"
down_revision = "20260519_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_product_factory_batches_status", "product_factory_batches", type_="check")
    op.create_check_constraint(
        "ck_product_factory_batches_status",
        "product_factory_batches",
        "status IN ('uploaded', 'resolving', 'resolved', 'partially_resolved', 'failed')",
    )

    op.drop_constraint("ck_product_factory_batch_rows_status", "product_factory_batch_rows", type_="check")
    op.create_check_constraint(
        "ck_product_factory_batch_rows_status",
        "product_factory_batch_rows",
        "status IN ('pending', 'resolving_source', 'auto_selected', 'manually_selected', 'needs_review', 'no_usable_source', 'resolution_failed', 'skipped')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_product_factory_batch_rows_status", "product_factory_batch_rows", type_="check")
    op.create_check_constraint(
        "ck_product_factory_batch_rows_status",
        "product_factory_batch_rows",
        "status IN ('pending', 'auto_selected', 'manually_selected', 'needs_review', 'no_usable_source', 'resolution_failed', 'skipped')",
    )

    op.drop_constraint("ck_product_factory_batches_status", "product_factory_batches", type_="check")
    op.create_check_constraint(
        "ck_product_factory_batches_status",
        "product_factory_batches",
        "status IN ('uploaded', 'resolving', 'resolved', 'resolved_with_errors')",
    )
