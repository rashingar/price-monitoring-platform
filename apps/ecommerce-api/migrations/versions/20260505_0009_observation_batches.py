"""vendor source observation batches

Revision ID: 20260505_0009
Revises: 20260505_0008
Create Date: 2026-05-05 00:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260505_0009"
down_revision = "20260505_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("vendor_source_capture_runs") as batch:
        batch.add_column(sa.Column("observation_batch_id", sa.String(), nullable=True))
        batch.create_index(
            "ix_vendor_source_capture_runs_observation_batch_id",
            ["observation_batch_id"],
        )
    with op.batch_alter_table("price_observations") as batch:
        batch.add_column(sa.Column("observation_batch_id", sa.String(), nullable=True))
        batch.create_index(
            "ix_price_observations_observation_batch_id", ["observation_batch_id"]
        )
    with op.batch_alter_table("offer_observations") as batch:
        batch.add_column(sa.Column("observation_batch_id", sa.String(), nullable=True))
        batch.create_index(
            "ix_offer_observations_observation_batch_id", ["observation_batch_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("offer_observations") as batch:
        batch.drop_index("ix_offer_observations_observation_batch_id")
        batch.drop_column("observation_batch_id")
    with op.batch_alter_table("price_observations") as batch:
        batch.drop_index("ix_price_observations_observation_batch_id")
        batch.drop_column("observation_batch_id")
    with op.batch_alter_table("vendor_source_capture_runs") as batch:
        batch.drop_index("ix_vendor_source_capture_runs_observation_batch_id")
        batch.drop_column("observation_batch_id")
