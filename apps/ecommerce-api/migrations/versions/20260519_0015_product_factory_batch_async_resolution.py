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
    with op.batch_alter_table("product_factory_batches", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_product_factory_batches_status", type_="check")
        batch_op.create_check_constraint(
            "ck_product_factory_batches_status",
            "status IN ('uploaded', 'resolving', 'resolved', 'partially_resolved', 'failed')",
        )

    with op.batch_alter_table("product_factory_batch_rows", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_product_factory_batch_rows_status", type_="check")
        batch_op.create_check_constraint(
            "ck_product_factory_batch_rows_status",
            "status IN ('pending', 'resolving_source', 'auto_selected', 'manually_selected', 'needs_review', 'no_usable_source', 'resolution_failed', 'skipped')",
        )


def downgrade() -> None:
    with op.batch_alter_table("product_factory_batch_rows", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_product_factory_batch_rows_status", type_="check")
        batch_op.create_check_constraint(
            "ck_product_factory_batch_rows_status",
            "status IN ('pending', 'auto_selected', 'manually_selected', 'needs_review', 'no_usable_source', 'resolution_failed', 'skipped')",
        )

    with op.batch_alter_table("product_factory_batches", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_product_factory_batches_status", type_="check")
        batch_op.create_check_constraint(
            "ck_product_factory_batches_status",
            "status IN ('uploaded', 'resolving', 'resolved', 'resolved_with_errors')",
        )
