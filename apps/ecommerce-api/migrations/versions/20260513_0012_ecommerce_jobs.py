"""ecommerce durable jobs

Revision ID: 20260513_0012
Revises: 20260513_0011
Create Date: 2026-05-13 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260513_0012"
down_revision = "20260513_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ecommerce_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column(
            "payload_json",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "result_json",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_ecommerce_jobs_status",
        ),
    )
    op.create_index(
        "uq_ecommerce_jobs_job_id", "ecommerce_jobs", ["job_id"], unique=True
    )
    op.create_index("ix_ecommerce_jobs_job_type", "ecommerce_jobs", ["job_type"])
    op.create_index("ix_ecommerce_jobs_status", "ecommerce_jobs", ["status"])
    op.create_index("ix_ecommerce_jobs_created_at", "ecommerce_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ecommerce_jobs_created_at", table_name="ecommerce_jobs")
    op.drop_index("ix_ecommerce_jobs_status", table_name="ecommerce_jobs")
    op.drop_index("ix_ecommerce_jobs_job_type", table_name="ecommerce_jobs")
    op.drop_index("uq_ecommerce_jobs_job_id", table_name="ecommerce_jobs")
    op.drop_table("ecommerce_jobs")
